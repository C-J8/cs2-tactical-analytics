from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.features.bomb_context import build_bomb_carrier_timeline
from src.features.death_context import build_death_context
from src.features.region_mapping import build_place_lookup
from src.features.round_progression import build_progression_signature, build_round_outcome_context
from src.features.side_dataset_audit import build_side_dataset_audit
from src.features.side_datasets import apply_round_state, build_side_datasets, run_side_dataset_pipeline


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
            {"round_feature_id": "r1", "parse_id": "p1", "dem_file_id": "d1", "series_id": "s1", "round_id": "r1", "target_team": "Vitality", "opponent": "G2", "map_name": "Mirage", "round_num": 1, "target_team_side": "T", "bomb_planted": True, "target_site_model_label": "A", "label_source": "rounds_bomb_site", "label_confidence": "high", "winner_side": "t"},
            {"round_feature_id": "r2", "parse_id": "p1", "dem_file_id": "d1", "series_id": "s1", "round_id": "r2", "target_team": "Vitality", "opponent": "G2", "map_name": "Mirage", "round_num": 2, "target_team_side": "T", "bomb_planted": False, "target_site_model_label": None, "label_source": "missing", "label_confidence": None, "winner_side": "ct"},
            {"round_feature_id": "r3", "parse_id": "p2", "dem_file_id": "d2", "series_id": "s2", "round_id": "r3", "target_team": "Vitality", "opponent": "NAVI", "map_name": "Mirage", "round_num": 1, "target_team_side": "CT", "bomb_planted": False, "target_site_model_label": None, "label_source": "missing", "label_confidence": None, "winner_side": "ct"},
        ]
    )


def test_side_dataset_split() -> None:
    datasets = build_side_datasets(_round_features())

    assert set(datasets["t_side_all"]["target_team_side"]) == {"T"}
    assert set(datasets["ct_side"]["target_team_side"]) == {"CT"}
    assert len(datasets["t_side_planted"]) == 1
    assert bool(datasets["t_side_planted"].iloc[0]["is_model_ab_candidate"]) is True


def test_side_datasets_use_round_state_resolved() -> None:
    features = _round_features().assign(target_team_side="T", target_site_model_label=None, label_confidence=None)
    round_state = pd.DataFrame(
        [
            {"round_id": "r1", "target_team_side": "T", "bomb_planted": True, "target_site_model_label": "A", "label_source": "target_team_plant", "label_confidence": "high"},
            {"round_id": "r2", "target_team_side": "CT", "bomb_planted": False, "target_site_model_label": None, "label_source": "missing", "label_confidence": None},
            {"round_id": "r3", "target_team_side": "CT", "bomb_planted": False, "target_site_model_label": None, "label_source": "missing", "label_confidence": None},
        ]
    )

    datasets = build_side_datasets(apply_round_state(features, round_state))

    assert len(datasets["t_side_all"]) == 1
    assert len(datasets["ct_side"]) == 2
    assert set(datasets["t_side_planted"]["label_confidence"]) == {"high"}


def test_side_dataset_audit_counts_labels() -> None:
    datasets = build_side_datasets(_round_features())
    audit = build_side_dataset_audit(datasets)

    planted = audit[audit["dataset_type"] == "t_side_planted"].iloc[0]
    assert planted["rounds_with_label_A"] == 1
    assert planted["rounds_without_label"] == 0


def test_progression_signature_uses_dominant_regions() -> None:
    timeline = pd.DataFrame(
        [
            {"round_feature_id": "r1", "window_start": 0, "window_end": 5, "region_group": "MID_CONTROL", "time_spent_total": 10},
            {"round_feature_id": "r1", "window_start": 5, "window_end": 10, "region_group": "A_PRESSURE", "time_spent_total": 20},
        ]
    )

    assert build_progression_signature(timeline, "A") == "MID_CONTROL>A_PRESSURE>PLANT_A"


def test_death_context_marks_order_and_target_death() -> None:
    lookup = build_place_lookup({"regions": [{"region_name": "Mid", "region_group": "MID_CONTROL", "aliases": ["Middle"]}]})
    rounds = _round_features().head(1).assign(freeze_end_tick=100, round_start_tick=0)
    kills = pd.DataFrame(
        [
            {"source_parse_id": "p1", "round_num": 1, "tick": 120, "attacker_name": "ct", "attacker_side": "ct", "victim_name": "t", "victim_side": "t", "victim_place": "Middle", "victim_X": 1, "victim_Y": 2, "victim_Z": 3, "weapon": "ak47"}
        ]
    )

    death_context = build_death_context(kills, rounds, region_lookup=lookup)

    assert death_context.loc[0, "death_order"] == 1
    assert bool(death_context.loc[0, "is_first_death"]) is True
    assert bool(death_context.loc[0, "is_target_team_death"]) is True
    assert death_context.loc[0, "death_region_group"] == "MID_CONTROL"


def test_bomb_carrier_timeline_identifies_c4() -> None:
    lookup = build_place_lookup({"regions": [{"region_name": "Mid", "region_group": "MID_CONTROL", "aliases": ["Middle"]}]})
    rounds = _round_features().head(1).assign(freeze_end_tick=100, round_start_tick=0)
    ticks = pd.DataFrame(
        [
            {"round_feature_id": "r1", "round_id": "r1", "series_id": "s1", "target_team": "Vitality", "opponent": "G2", "map_name": "Mirage", "target_team_side": "T", "tick": 110, "seconds_from_freeze_end": 0.1, "name": "carrier", "steamid": "1", "inventory": ["C4 Explosive"], "place": "Middle", "X": 1, "Y": 2, "Z": 3}
        ]
    )

    timeline = build_bomb_carrier_timeline(ticks, rounds, pd.DataFrame(), region_lookup=lookup, place_column="place")

    assert timeline.loc[0, "bomb_carrier_player"] == "carrier"
    assert timeline.loc[0, "bomb_carrier_region_group"] == "MID_CONTROL"


def test_outcome_context_classifies_plants_and_no_plant() -> None:
    rounds = _round_features().assign(freeze_end_tick=100, round_start_tick=0)
    outcome = build_round_outcome_context(rounds, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())

    assert outcome.loc[0, "round_outcome_type"] == "plant_A"
    assert outcome.loc[1, "round_outcome_type"] == "no_plant_target_team_loss"
    assert outcome.loc[2, "round_outcome_type"] == "no_plant_target_team_win"


def test_side_pipeline_writes_outputs_and_dry_run_preserves(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    gold_dir = tmp_path / "data/gold"
    silver_dir = tmp_path / "data/silver/parsed_demos"
    (gold_dir / "round_features").mkdir(parents=True)
    (gold_dir / "round_state").mkdir(parents=True)
    (gold_dir / "utility_events").mkdir(parents=True)
    silver_dir.mkdir(parents=True)
    _round_features().to_parquet(gold_dir / "round_features/round_features_mvp.parquet", index=False)
    _round_features().assign(round_start_tick=0, freeze_end_tick=100, round_end_tick=1000).to_parquet(gold_dir / "round_features/round_base.parquet", index=False)
    pd.DataFrame(
        [
            {"round_id": "r1", "target_team_side": "T", "winner_team": "Vitality", "winner_side": "T", "bomb_planted": True, "bombsite": "A", "target_site_model_label": "A", "label_source": "target_team_plant", "label_confidence": "high"},
            {"round_id": "r2", "target_team_side": "T", "winner_team": "G2", "winner_side": "CT", "bomb_planted": False, "bombsite": None, "target_site_model_label": None, "label_source": "missing", "label_confidence": None},
            {"round_id": "r3", "target_team_side": "CT", "winner_team": "Vitality", "winner_side": "CT", "bomb_planted": False, "bombsite": None, "target_site_model_label": None, "label_source": "missing", "label_confidence": None},
        ]
    ).to_parquet(gold_dir / "round_state/round_state_resolved.parquet", index=False)
    pd.DataFrame(columns=["round_feature_id", "seconds_from_freeze_end", "end_region_group"]).to_parquet(gold_dir / "utility_events/utility_events.parquet", index=False)
    pd.DataFrame({"source_parse_id": ["p1"], "round_num": [1], "tick": [110], "X": [0], "Y": [0], "Z": [0], "side": ["t"], "name": ["carrier"], "steamid": ["1"], "place": ["Middle"], "health": [100], "inventory": [["C4 Explosive"]], "series_id": ["s1"], "target_team": ["Vitality"], "map_name": ["Mirage"]}).to_parquet(silver_dir / "ticks.parquet", index=False)
    pd.DataFrame(columns=["source_parse_id", "round_num", "tick"]).to_parquet(silver_dir / "kills.parquet", index=False)
    pd.DataFrame(columns=["source_parse_id", "round_num", "tick", "event"]).to_parquet(silver_dir / "bomb.parquet", index=False)

    _, outputs, summary = run_side_dataset_pipeline(config_path, force=True)
    before = (gold_dir / "round_features/round_features_t_side_all.csv").read_text(encoding="utf-8")
    _, dry_outputs, _ = run_side_dataset_pipeline(config_path, dry_run=True)

    assert summary["t_side_all"] == 2
    assert summary["ct_side"] == 1
    assert outputs["round_features_t_side_all.parquet"].exists()
    assert outputs["round_region_timeline.parquet"].exists()
    assert dry_outputs == {}
    assert (gold_dir / "round_features/round_features_t_side_all.csv").read_text(encoding="utf-8") == before


def test_side_pipeline_requires_round_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    gold_dir = tmp_path / "data/gold"
    silver_dir = tmp_path / "data/silver/parsed_demos"
    (gold_dir / "round_features").mkdir(parents=True)
    silver_dir.mkdir(parents=True)
    _round_features().to_parquet(gold_dir / "round_features/round_features_mvp.parquet", index=False)
    _round_features().assign(round_start_tick=0, freeze_end_tick=100, round_end_tick=1000).to_parquet(gold_dir / "round_features/round_base.parquet", index=False)

    with pytest.raises(FileNotFoundError, match="round_state_resolved.parquet is required"):
        run_side_dataset_pipeline(config_path, dry_run=True)
