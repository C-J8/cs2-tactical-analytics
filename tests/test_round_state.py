from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.features.round_state import build_round_state, build_round_state_audit, load_player_rosters, run_round_state_pipeline


def _write_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "project.yaml"
    config_path.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-06-05"
target_maps:
  - Mirage
target_teams:
  - Vitality
output_formats:
  - csv
  - parquet
manual_seed_path: {(tmp_path / 'data/raw/manual/matches_seed.csv').as_posix()}
hltv_cache_dir: {(tmp_path / 'data/raw/hltv_pages').as_posix()}
bronze_output_dir: {(tmp_path / 'data/bronze/match_catalog_raw').as_posix()}
silver_output_dir: {(tmp_path / 'data/silver/matches_catalog').as_posix()}
demo_archive_dir: {(tmp_path / 'data/raw/demo_archives').as_posix()}
demo_output_dir: {(tmp_path / 'data/raw/demos').as_posix()}
demo_manifest_dir: {(tmp_path / 'data/bronze/demo_manifest').as_posix()}
local_archive_manifest_dir: {(tmp_path / 'data/bronze/local_archive_manifest').as_posix()}
dem_files_manifest_dir: {(tmp_path / 'data/bronze/dem_files_manifest').as_posix()}
dem_files_manifest_path: {(tmp_path / 'data/bronze/dem_files_manifest/dem_files_manifest.parquet').as_posix()}
parsed_bronze_dir: {(tmp_path / 'data/bronze/parsed_demos').as_posix()}
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
parse_manifest_dir: {(tmp_path / 'data/bronze/parse_manifest').as_posix()}
parser_backend: awpy
parse_player_props:
  - X
parse_tables:
  - ticks
parse_events: true
download_timeout_seconds: 10
download_rate_limit_seconds: 0
extract_archives: true
force_download: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _round_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "round_feature_id": "rf1",
                "round_id": "r1",
                "round_num": 1,
                "parse_id": "p1",
                "dem_file_id": "d1",
                "series_id": "s1",
                "target_team": "Vitality",
                "opponent": "G2",
                "map_name": "Mirage",
            }
        ]
    )


def _round_base() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "round_feature_id": "rf1",
                "round_start_tick": 0,
                "freeze_end_tick": 100,
                "round_end_tick": 1000,
            }
        ]
    )


def _rounds(**updates: object) -> pd.DataFrame:
    row = {
        "source_parse_id": "p1",
        "round_num": 1,
        "winner": "t",
        "reason": "bomb_exploded",
        "bomb_plant": pd.NA,
        "bomb_site": pd.NA,
    }
    row.update(updates)
    return pd.DataFrame([row])


def _bomb(**updates: object) -> pd.DataFrame:
    row = {
        "source_parse_id": "p1",
        "round_num": 1,
        "tick": 500,
        "event": "plant",
        "name": "ZywOo",
        "bombsite": "A",
    }
    row.update(updates)
    return pd.DataFrame([row])


def _state(rounds: pd.DataFrame, bomb: pd.DataFrame | None = None, tmp_path: Path | None = None) -> pd.DataFrame:
    ticks_path = (tmp_path or Path(".")) / "missing_ticks.parquet"
    return build_round_state(
        _round_features(),
        _round_base(),
        rounds,
        bomb if bomb is not None else pd.DataFrame(),
        ticks_path=ticks_path,
        target_team="Vitality",
    )


def test_resolves_t_when_target_team_is_team_t(tmp_path: Path) -> None:
    state = _state(_rounds(team_t="Vitality", team_ct="G2"), tmp_path=tmp_path)

    assert state.loc[0, "target_team_side"] == "T"
    assert state.loc[0, "side_resolution_confidence"] == "high"


def test_resolves_ct_when_target_team_is_team_ct(tmp_path: Path) -> None:
    state = _state(_rounds(team_t="G2", team_ct="Vitality"), tmp_path=tmp_path)

    assert state.loc[0, "target_team_side"] == "CT"
    assert state.loc[0, "opponent_side"] == "T"


def test_returns_unknown_when_no_side_evidence(tmp_path: Path) -> None:
    state = _state(_rounds(), tmp_path=tmp_path)

    assert state.loc[0, "target_team_side"] == "unknown"
    assert state.loc[0, "state_quality_status"] == "side_unknown"


def test_ab_label_only_when_vitality_is_t_side_and_plants(tmp_path: Path) -> None:
    state = _state(_rounds(team_t="Vitality", team_ct="G2"), _bomb(name="apEX", bombsite="B"), tmp_path)

    assert state.loc[0, "target_site_model_label"] == "B"
    assert state.loc[0, "label_source"] == "target_team_plant"
    assert state.loc[0, "label_confidence"] == "high"


def test_opponent_plant_does_not_become_target_label(tmp_path: Path) -> None:
    state = _state(_rounds(team_t="G2", team_ct="Vitality"), _bomb(name="m0NESY", bombsite="A"), tmp_path)

    assert pd.isna(state.loc[0, "target_site_model_label"])
    assert state.loc[0, "planting_team"] == "G2"
    assert state.loc[0, "label_source"] == "opponent_plant"
    assert state.loc[0, "label_confidence"] is None


def test_opponent_plant_uses_roster_when_catalog_opponent_is_unknown(tmp_path: Path) -> None:
    features = _round_features().assign(opponent="unknown")
    state = build_round_state(
        features,
        _round_base(),
        _rounds(team_t="G2", team_ct="Vitality"),
        _bomb(name="m0NESY", bombsite="A"),
        ticks_path=tmp_path / "missing_ticks.parquet",
        target_team="Vitality",
        team_rosters={"Vitality": {"zywoo", "apex"}, "G2": {"m0nesy"}},
    )

    assert state.loc[0, "planting_team"] == "G2"
    assert state.loc[0, "label_source"] == "opponent_plant"
    assert pd.isna(state.loc[0, "target_site_model_label"])


def test_player_rosters_load_from_yaml(tmp_path: Path) -> None:
    roster_path = tmp_path / "player_rosters.yaml"
    roster_path.write_text(
        """
teams:
  - team_name: Vitality
    players:
      - player_name: ZywOo
        aliases:
          - zywoo
      - player_name: apEX
  - team_name: G2
    players:
      - player_name: m0NESY
""".strip(),
        encoding="utf-8",
    )

    rosters = load_player_rosters(roster_path)

    assert rosters["Vitality"] == {"zywoo", "apex"}
    assert rosters["G2"] == {"m0nesy"}


def test_round_without_plant_keeps_null_label(tmp_path: Path) -> None:
    state = _state(_rounds(team_t="Vitality", team_ct="G2"), tmp_path=tmp_path)

    assert bool(state.loc[0, "bomb_planted"]) is False
    assert pd.isna(state.loc[0, "target_site_model_label"])
    assert state.loc[0, "planting_team"] is None
    assert state.loc[0, "label_source"] == "missing"


def test_round_state_audit_is_generated(tmp_path: Path) -> None:
    state = _state(_rounds(team_t="Vitality", team_ct="G2"), _bomb(name="apEX"), tmp_path)
    audit = build_round_state_audit(state)

    assert audit.loc[0, "total_rounds"] == 1
    assert audit.loc[0, "rounds_label_ab_high_confidence"] == 1


def test_round_state_dry_run_does_not_overwrite_outputs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    silver_dir = tmp_path / "data/silver/parsed_demos"
    gold_dir = tmp_path / "data/gold"
    silver_dir.mkdir(parents=True)
    (gold_dir / "round_features").mkdir(parents=True)
    output_dir = gold_dir / "round_state"
    output_dir.mkdir(parents=True)
    csv_path = output_dir / "round_state_resolved.csv"
    csv_path.write_text("old\n", encoding="utf-8")

    _round_features().to_parquet(gold_dir / "round_features/round_features_mvp.parquet", index=False)
    _round_base().to_parquet(gold_dir / "round_features/round_base.parquet", index=False)
    _rounds(team_t="Vitality", team_ct="G2").to_parquet(silver_dir / "rounds.parquet", index=False)

    _, _, outputs, summary = run_round_state_pipeline(config_path, dry_run=True)

    assert outputs == {}
    assert summary["target_team_t"] == 1
    assert csv_path.read_text(encoding="utf-8") == "old\n"
