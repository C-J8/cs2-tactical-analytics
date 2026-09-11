from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.config.schemas import MapConfig, MapsConfig, ProjectConfig, TeamConfig, TeamsConfig
from src.ingestion.build_match_catalog import build_catalog
from src.ingestion.hltv_client import (
    HltvFetchResult,
    build_results_url,
    is_security_challenge,
    parse_match_page,
    parse_results_page,
    results_has_next_page,
)
from src.ingestion.match_discovery import discover_matches, hltv_map_codes


RESULTS_HTML = """
<div class="results-sublist">
  <div class="result-con">
    <a class="a-reset" href="/matches/42/vitality-vs-navi-example-event">Vitality vs NAVI</a>
  </div>
</div>
<aside><a class="a-reset" href="/matches/999/sidebar-match">Sidebar match</a></aside>
<a href="/results?offset=100&amp;team=9565">Next</a>
"""


MATCH_HTML = """
<div class="timeAndEvent">
  <div class="date" data-unix="1767225600000"></div>
  <div class="event"><a>Example Event</a></div>
</div>
<div class="teamName">Vitality</div>
<div class="teamName">Natus Vincere</div>
<div class="mapholder">
  <div class="mapname">Mirage</div>
  <div class="results-team-score">13</div>
  <div class="results-team-score">9</div>
</div>
<div class="mapholder">
  <div class="optional"><div class="mapname">Inferno</div></div>
  <div class="results-team-score">-</div>
  <div class="results-team-score">-</div>
</div>
<a class="hidden" href="/download/demo/77">Download</a>
"""


def test_results_parser_uses_only_result_cards() -> None:
    matches = parse_results_page(RESULTS_HTML)

    assert matches == [
        {
            "hltv_match_id": "42",
            "match_url": "https://www.hltv.org/matches/42/vitality-vs-navi-example-event",
        }
    ]
    assert results_has_next_page(RESULTS_HTML, next_offset=100)


def test_match_parser_ignores_unplayed_map_and_finds_demo() -> None:
    parsed = parse_match_page(MATCH_HTML)

    assert parsed["event_name"] == "Example Event"
    assert parsed["team_1"] == "Vitality"
    assert parsed["team_2"] == "Natus Vincere"
    assert parsed["maps"] == ["Mirage"]
    assert parsed["demo_link"] == "https://www.hltv.org/download/demo/77"


def test_results_url_contains_team_dates_map_and_offset() -> None:
    url = build_results_url(
        9565,
        date(2026, 1, 1),
        date(2026, 2, 1),
        map_codes=["de_mirage"],
        offset=100,
    )

    assert "team=9565" in url
    assert "startDate=2026-01-01" in url
    assert "endDate=2026-02-01" in url
    assert "map=de_mirage" in url
    assert "offset=100" in url


def test_security_challenge_is_detected() -> None:
    assert is_security_challenge("<title>Just a moment...</title><div id='cf-chl-widget'></div>")


def test_discovery_expands_match_page_into_catalog_rows(monkeypatch, tmp_path: Path) -> None:
    project = ProjectConfig(
        project_name="test",
        mode="hybrid",
        date_start=date(2026, 1, 1),
        date_end=date(2026, 2, 1),
        target_maps=["Mirage"],
        target_teams=["Vitality"],
        rate_limit_seconds=0,
        hltv_cache_dir=tmp_path / "cache",
        discovery_max_pages=1,
    )
    teams = TeamsConfig(teams=[TeamConfig(team_name="Vitality", hltv_team_id=9565)])
    maps = MapsConfig(maps=[MapConfig(map_name="Mirage", aliases=["de_mirage"])])

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def fetch_results_page(self, team_id, date_start, date_end, *, map_codes, offset):
            assert team_id == 9565
            assert map_codes == ["de_mirage"]
            return HltvFetchResult(RESULTS_HTML.replace("offset=100", "offset=200"), None, False)

        def fetch_match_page(self, match_url, match_id):
            assert match_id == "42"
            return HltvFetchResult(MATCH_HTML, tmp_path / "hltv_match_42.html", False)

    monkeypatch.setattr("src.ingestion.match_discovery.HltvClient", FakeClient)

    rows, status = discover_matches(project, teams, maps)

    assert len(rows) == 1
    assert rows.loc[0, "map_name"] == "Mirage"
    assert rows.loc[0, "map_number"] == 1
    assert rows.loc[0, "source_method"] == "scrape"
    assert rows.loc[0, "demo_link"] == "https://www.hltv.org/download/demo/77"
    assert set(status["request_kind"]) == {"results", "match"}
    assert set(status["status"]) == {"ok"}
    assert hltv_map_codes(["Mirage"], maps) == ["de_mirage"]


def test_hybrid_catalog_preserves_manual_seed_when_discovery_is_blocked(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    manual_path = tmp_path / "data/raw/manual/matches_seed.csv"
    manual_path.parent.mkdir(parents=True)
    manual_path.write_text(
        "hltv_match_id,match_url,match_date,event_name,team_1,team_2,map_name,map_number,demo_link\n"
        "42,https://www.hltv.org/matches/42/example,2026-01-01,Example,Vitality,NAVI,Mirage,1,\n",
        encoding="utf-8",
    )
    (config_dir / "teams.yaml").write_text(
        "teams:\n  - team_name: Vitality\n    hltv_team_id: 9565\n",
        encoding="utf-8",
    )
    (config_dir / "maps.yaml").write_text(
        "maps:\n  - map_name: Mirage\n    aliases: [de_mirage]\n",
        encoding="utf-8",
    )
    config_path = config_dir / "project.yaml"
    config_path.write_text(
        f"""
project_name: test
mode: hybrid
date_start: 2026-01-01
date_end: 2026-02-01
target_maps: [Mirage]
target_teams: [Vitality]
output_formats: [csv, parquet]
rate_limit_seconds: 0
manual_seed_path: {manual_path.as_posix()}
hltv_cache_dir: {(tmp_path / 'cache').as_posix()}
match_discovery_manifest_dir: {(tmp_path / 'bronze/discovery').as_posix()}
bronze_output_dir: {(tmp_path / 'bronze/catalog').as_posix()}
silver_output_dir: {(tmp_path / 'silver/catalog').as_posix()}
""".strip(),
        encoding="utf-8",
    )
    blocked = pd.DataFrame(
        [
            {
                "request_kind": "results",
                "target_team": "Vitality",
                "status": "blocked_or_failed",
                "error_message": "403",
            }
        ]
    )
    monkeypatch.setattr("src.ingestion.build_match_catalog.discover_matches", lambda *args: (pd.DataFrame(), blocked))
    monkeypatch.setattr("src.ingestion.build_match_catalog.enrich_with_scraping", lambda frame, project: frame)

    catalog, outputs, summary = build_catalog(config_path)

    assert len(catalog) == 1
    assert catalog.loc[0, "hltv_match_id"] == "42"
    assert summary["discovery_requests_failed"] == 1
    assert outputs["csv"].exists()
    assert outputs["discovery_match_discovery_manifest_csv"].exists()
