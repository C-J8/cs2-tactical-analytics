from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.features.build_round_features import assemble_round_features, run_feature_pipeline
from src.features.feature_audit import build_feature_audit
from src.features.position_features import build_position_outputs
from src.features.region_mapping import build_place_lookup, map_place_to_region
from src.features.round_context import build_round_base
from src.features.utility_features import build_player_round_utility, count_inventory, detect_grenades_granularity, events_from_table


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


def _feature_eligible() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "parse_id": "parse1",
                "dem_file_id": "demo1",
                "series_id": "series1",
                "local_archive_id": "archive1",
                "target_team": "Vitality",
                "opponent": "unknown",
                "inferred_map_name": "Mirage",
                "feature_eligible": True,
            }
        ]
    )


def _rounds() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"round_num": 1, "start": 0, "freeze_end": 100, "end": 1000, "winner": "t", "reason": "bomb_exploded", "bomb_plant": 500, "bomb_site": "bombsite_a", "map_name": "Mirage", "source_parse_id": "parse1"},
            {"round_num": 2, "start": 1000, "freeze_end": 1100, "end": 2000, "winner": "ct", "reason": "t_killed", "bomb_plant": None, "bomb_site": "not_planted", "map_name": "Mirage", "source_parse_id": "parse1"},
        ]
    )


def test_build_round_base_labels_from_bombsite() -> None:
    base = build_round_base(_rounds(), _feature_eligible())

    assert base.loc[0, "target_site_model_label"] == "A"
    assert base.loc[0, "label_source"] == "rounds_bomb_site"


def test_build_round_base_missing_label_without_plant() -> None:
    base = build_round_base(_rounds(), _feature_eligible())

    assert pd.isna(base.loc[1, "target_site_model_label"])
    assert base.loc[1, "label_source"] == "missing"


def test_region_mapping_place_name_and_unknown() -> None:
    lookup = build_place_lookup({"regions": [{"region_name": "Mid", "region_group": "MID_CONTROL", "aliases": ["Middle"]}]})

    assert map_place_to_region("Middle", lookup) == ("Mid", "MID_CONTROL")
    assert map_place_to_region("Nowhere", lookup) == ("UNKNOWN", "UNKNOWN")


def test_position_features_centroid_and_region_presence() -> None:
    base = build_round_base(_rounds().head(1), _feature_eligible())
    ticks = pd.DataFrame(
        [
            {"round_feature_id": base.loc[0, "round_feature_id"], "round_id": base.loc[0, "round_id"], "series_id": "series1", "target_team": "Vitality", "map_name": "Mirage", "tick": 100, "seconds_from_freeze_end": 0, "X": 0, "Y": 0, "Z": 0, "steamid": "1", "health": 100, "region_name": "Mid", "region_group": "MID_CONTROL", "place": "Middle"},
            {"round_feature_id": base.loc[0, "round_feature_id"], "round_id": base.loc[0, "round_id"], "series_id": "series1", "target_team": "Vitality", "map_name": "Mirage", "tick": 100, "seconds_from_freeze_end": 0, "X": 10, "Y": 0, "Z": 0, "steamid": "2", "health": 100, "region_name": "Mid", "region_group": "MID_CONTROL", "place": "Middle"},
        ]
    )
    lookup = build_place_lookup({"regions": [{"region_name": "Mid", "region_group": "MID_CONTROL", "aliases": ["Middle"]}]})

    region_presence, wide = build_position_outputs(ticks, base, region_lookup=lookup, place_column="place")

    assert wide.loc[0, "team_center_x_10s"] == 5
    assert wide.loc[0, "players_mid_0_20"] == 2
    assert not region_presence.empty


def test_count_initial_utility_from_inventory() -> None:
    counts = count_inventory("['Smoke Grenade', 'Flashbang', 'Molotov', 'HE Grenade']")

    assert counts == {"smoke": 1, "flash": 1, "molotov": 1, "he": 1, "decoy": 0}


def test_player_round_utility_aggregates_inventory() -> None:
    base = build_round_base(_rounds().head(1), _feature_eligible())
    ticks = pd.DataFrame(
        [
            {"round_feature_id": base.loc[0, "round_feature_id"], "round_id": base.loc[0, "round_id"], "series_id": "series1", "target_team": "Vitality", "tick": 100, "steamid": "1", "name": "p1", "side": "t", "inventory": ["Smoke Grenade", "Flashbang"]},
            {"round_feature_id": base.loc[0, "round_feature_id"], "round_id": base.loc[0, "round_id"], "series_id": "series1", "target_team": "Vitality", "tick": 101, "steamid": "2", "name": "p2", "side": "t", "inventory": ["Molotov"]},
        ]
    )

    player_utility, aggregates = build_player_round_utility(ticks, base)

    assert len(player_utility) == 2
    assert aggregates.loc[0, "team_smokes_start"] == 1
    assert aggregates.loc[0, "team_molotovs_start"] == 1


def test_utility_events_from_smokes_and_infernos_fake() -> None:
    base = build_round_base(_rounds().head(1), _feature_eligible())
    source = pd.DataFrame(
        [
            {"entity_id": 1, "start_tick": 120, "thrower_X": 1, "thrower_Y": 2, "thrower_Z": 3, "thrower_place": "Middle", "thrower_name": "p1", "thrower_steamid": "1", "thrower_side": "t", "X": 10, "Y": 20, "Z": 30, "round_num": 1, "source_parse_id": "parse1"}
        ]
    )
    lookup = build_place_lookup({"regions": [{"region_name": "Mid", "region_group": "MID_CONTROL", "aliases": ["Middle"]}]})

    smoke_events = events_from_table(source, base, utility_type="smoke", source_table="smokes", region_lookup=lookup, tickrate=64, window_end=20)
    molotov_events = events_from_table(source, base, utility_type="molotov", source_table="infernos", region_lookup=lookup, tickrate=64, window_end=20)

    assert smoke_events.loc[0, "utility_type"] == "smoke"
    assert molotov_events.loc[0, "utility_type"] == "molotov"
    assert smoke_events.loc[0, "throw_region_group"] == "MID_CONTROL"


def test_detect_grenades_trajectory_level(tmp_path: Path) -> None:
    path = tmp_path / "grenades.parquet"
    pd.DataFrame({"entity_id": [1, 1, 1], "tick": [100, 101, 102]}).to_parquet(path, index=False)

    assert detect_grenades_granularity(path) == "trajectory_level"


def test_round_features_and_audit_are_generated() -> None:
    base = build_round_base(_rounds(), _feature_eligible())
    position = pd.DataFrame({"round_feature_id": base["round_feature_id"], "team_center_x_10s": [1, 2]})
    utility_start = pd.DataFrame({"round_feature_id": base["round_feature_id"], "team_smokes_start": [1, 0]})
    utility_events = pd.DataFrame({"round_feature_id": base["round_feature_id"], "smokes_used_0_20": [1, 0]})

    features = assemble_round_features(base, position, utility_start, utility_events)
    audit = build_feature_audit(feature_eligible=_feature_eligible(), round_features=features, utility_events=pd.DataFrame(), region_presence=pd.DataFrame(), diagnostics={"grenades_granularity": "trajectory_level"}, warnings=[])

    assert len(features) == 2
    assert "round_features" not in features.columns
    assert audit.loc[0, "rounds_generated"] == 2


def test_feature_pipeline_dry_run_does_not_overwrite(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    silver_dir = tmp_path / "data/silver/parsed_demos"
    silver_dir.mkdir(parents=True)
    _feature_eligible().to_parquet(silver_dir / "feature_eligible_demos.parquet", index=False)
    _rounds().to_parquet(silver_dir / "rounds.parquet", index=False)
    pd.DataFrame(columns=["tick", "event", "round_num", "source_parse_id"]).to_parquet(silver_dir / "bomb.parquet", index=False)
    pd.DataFrame({"source_parse_id": ["parse1"], "round_num": [1], "tick": [100], "X": [0], "Y": [0], "Z": [0], "side": ["t"], "name": ["p1"], "steamid": ["1"], "place": ["Middle"], "health": [100], "inventory": [["Smoke Grenade"]], "series_id": ["series1"], "target_team": ["Vitality"], "map_name": ["Mirage"]}).to_parquet(silver_dir / "ticks.parquet", index=False)
    pd.DataFrame(columns=["entity_id", "tick"]).to_parquet(silver_dir / "grenades.parquet", index=False)
    out = Path("data/gold/round_features/round_features_mvp.csv")
    old_content = out.read_text(encoding="utf-8") if out.exists() else None

    _, outputs, summary = run_feature_pipeline(config_path, dry_run=True)

    assert outputs == {}
    assert summary["rounds_generated"] == 2
    if old_content is not None:
        assert out.read_text(encoding="utf-8") == old_content
