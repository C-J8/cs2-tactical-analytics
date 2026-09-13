from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.config.schemas import MapsConfig, ProjectConfig, TeamConfig, TeamsConfig
from src.ingestion.hltv_client import (
    HltvClient,
    build_results_url,
    parse_match_page,
    parse_results_page,
    results_has_next_page,
)
from src.utils.text import clean_string, normalize_key


DISCOVERY_STATUS_COLUMNS = [
    "request_kind",
    "target_team",
    "hltv_team_id",
    "hltv_match_id",
    "url",
    "status",
    "fetched_from_cache",
    "source_html_path",
    "records_found",
    "error_message",
    "checked_at",
]


def discover_matches(
    project: ProjectConfig,
    teams: TeamsConfig,
    maps: MapsConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    client = HltvClient(
        project.hltv_cache_dir,
        cache_enabled=project.cache_enabled,
        rate_limit_seconds=project.rate_limit_seconds,
    )
    map_codes = hltv_map_codes(project.target_maps, maps)
    references: list[dict[str, object]] = []
    status_rows: list[dict[str, object]] = []

    for target_team in project.target_teams:
        team = find_team_config(target_team, teams)
        if team is None or team.hltv_team_id is None:
            status_rows.append(
                discovery_status_row(
                    request_kind="results",
                    target_team=target_team,
                    status="missing_team_id",
                    error_message="target team has no hltv_team_id in configs/teams.yaml",
                )
            )
            continue

        for page_number in range(project.discovery_max_pages):
            offset = page_number * 100
            url = build_results_url(
                team.hltv_team_id,
                project.date_start,
                project.date_end,
                map_codes=map_codes,
                offset=offset,
            )
            fetch_result = client.fetch_results_page(
                team.hltv_team_id,
                project.date_start,
                project.date_end,
                map_codes=map_codes,
                offset=offset,
            )
            page_references = parse_results_page(fetch_result.html) if fetch_result.html else []
            status_rows.append(
                discovery_status_row(
                    request_kind="results",
                    target_team=team.team_name,
                    hltv_team_id=team.hltv_team_id,
                    url=url,
                    status="ok" if fetch_result.html else "blocked_or_failed",
                    fetched_from_cache=fetch_result.fetched_from_cache,
                    source_html_path=fetch_result.html_path,
                    records_found=len(page_references),
                    error_message=fetch_result.error,
                )
            )
            if not fetch_result.html:
                break
            references.extend({**reference, "discovered_for_team": team.team_name} for reference in page_references)
            if not results_has_next_page(fetch_result.html, next_offset=offset + 100):
                break

    references = deduplicate_references(references)
    if project.discovery_max_matches_per_run is not None:
        references = references[: project.discovery_max_matches_per_run]

    rows: list[dict[str, object]] = []
    for reference in references:
        match_url = str(reference["match_url"])
        match_id = str(reference["hltv_match_id"])
        fetch_result = client.fetch_match_page(match_url, match_id)
        parsed = parse_match_page(fetch_result.html) if fetch_result.html else {}
        parsed_maps = parsed.get("maps") if isinstance(parsed.get("maps"), list) else []
        status_rows.append(
            discovery_status_row(
                request_kind="match",
                target_team=clean_string(reference.get("discovered_for_team")),
                hltv_match_id=match_id,
                url=match_url,
                status="ok" if fetch_result.html else "blocked_or_failed",
                fetched_from_cache=fetch_result.fetched_from_cache,
                source_html_path=fetch_result.html_path,
                records_found=len(parsed_maps),
                error_message=fetch_result.error,
            )
        )
        if not fetch_result.html:
            continue
        rows.extend(discovered_catalog_rows(reference, parsed, fetch_result.html_path))

    return pd.DataFrame(rows), pd.DataFrame(status_rows, columns=DISCOVERY_STATUS_COLUMNS)


def discovered_catalog_rows(
    reference: dict[str, object],
    parsed: dict[str, object],
    html_path: Path | None,
) -> list[dict[str, object]]:
    parsed_maps = parsed.get("maps") if isinstance(parsed.get("maps"), list) else []
    maps = parsed_maps or [None]
    common = {
        "hltv_match_id": reference.get("hltv_match_id"),
        "match_url": reference.get("match_url"),
        "match_date": parsed.get("match_date"),
        "event_name": parsed.get("event_name"),
        "team_1": parsed.get("team_1"),
        "team_2": parsed.get("team_2"),
        "demo_link": parsed.get("demo_link"),
        "source_method": "scrape",
        "source_html_path": str(html_path) if html_path else None,
        "scraped_at": parsed.get("scraped_at"),
    }
    return [
        {
            **common,
            "map_name": map_name,
            "map_number": map_number if map_name else None,
        }
        for map_number, map_name in enumerate(maps, start=1)
    ]


def find_team_config(target_team: str, teams: TeamsConfig) -> TeamConfig | None:
    target_key = normalize_key(target_team)
    for team in teams.teams:
        names = [team.team_name, *team.aliases]
        if target_key in {normalize_key(name) for name in names}:
            return team
    return None


def hltv_map_codes(target_maps: list[str], maps: MapsConfig) -> list[str]:
    requested = {normalize_key(map_name) for map_name in target_maps}
    codes: list[str] = []
    for map_config in maps.maps:
        names = [map_config.map_name, *map_config.aliases]
        if not requested.intersection(normalize_key(name) for name in names):
            continue
        code = next((alias for alias in map_config.aliases if alias.lower().startswith("de_")), None)
        codes.append(code or f"de_{normalize_key(map_config.map_name).replace(' ', '_')}")
    return list(dict.fromkeys(codes))


def deduplicate_references(references: list[dict[str, object]]) -> list[dict[str, object]]:
    deduplicated: list[dict[str, object]] = []
    seen: set[str] = set()
    for reference in references:
        match_id = clean_string(reference.get("hltv_match_id"))
        if not match_id or match_id in seen:
            continue
        seen.add(match_id)
        deduplicated.append(reference)
    return deduplicated


def discovery_status_row(
    *,
    request_kind: str,
    target_team: str | None,
    status: str,
    hltv_team_id: int | None = None,
    hltv_match_id: str | None = None,
    url: str | None = None,
    fetched_from_cache: bool = False,
    source_html_path: Path | None = None,
    records_found: int = 0,
    error_message: str | None = None,
) -> dict[str, object]:
    return {
        "request_kind": request_kind,
        "target_team": target_team,
        "hltv_team_id": hltv_team_id,
        "hltv_match_id": hltv_match_id,
        "url": url,
        "status": status,
        "fetched_from_cache": fetched_from_cache,
        "source_html_path": str(source_html_path) if source_html_path else None,
        "records_found": records_found,
        "error_message": error_message,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
