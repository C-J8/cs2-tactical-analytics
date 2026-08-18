from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.features.build_round_features import assemble_round_features, run_feature_pipeline
from src.features.feature_audit import build_feature_audit
from src.features.feature_windows import FeatureWindow
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
    assert wide.loc[0, "players_mid_control_0_15"] == 2
    assert set(region_presence["window_type"]) == {"interval", "cumulative"}
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


def test_utility_events_after_round_end_are_excluded() -> None:
    base = build_round_base(_rounds().head(1), _feature_eligible())
    source = pd.DataFrame(
        [
            {"entity_id": 1, "start_tick": 1200, "thrower_X": 1, "thrower_Y": 2, "thrower_Z": 3, "thrower_place": "Middle", "thrower_name": "p1", "thrower_steamid": "1", "thrower_side": "t", "X": 10, "Y": 20, "Z": 30, "round_num": 1, "source_parse_id": "parse1"}
        ]
    )
    lookup = build_place_lookup({"regions": [{"region_name": "Mid", "region_group": "MID_CONTROL", "aliases": ["Middle"]}]})

    smoke_events = events_from_table(source, base, utility_type="smoke", source_table="smokes", region_lookup=lookup, tickrate=64, windows=[FeatureWindow(0, 115, "cumulative")])

    assert smoke_events.empty


def test_short_round_only_populates_available_windows() -> None:
    base = build_round_base(_rounds().head(1), _feature_eligible())
    ticks = pd.DataFrame(
        [
            {"round_feature_id": base.loc[0, "round_feature_id"], "round_id": base.loc[0, "round_id"], "series_id": "series1", "target_team": "Vitality", "map_name": "Mirage", "tick": 100, "seconds_from_freeze_end": 0, "X": 0, "Y": 0, "Z": 0, "steamid": "1", "health": 100, "region_name": "Mid", "region_group": "MID_CONTROL", "place": "Middle"},
        ]
    )
    lookup = build_place_lookup({"regions": [{"region_name": "Mid", "region_group": "MID_CONTROL", "aliases": ["Middle"]}]})

    region_presence, wide = build_position_outputs(ticks, base, region_lookup=lookup, place_column="place", windows=[FeatureWindow(0, 15, "interval"), FeatureWindow(105, 115, "interval")])

    assert len(region_presence) == 1
    assert wide.loc[0, "players_mid_control_0_15"] == 1
    assert wide.loc[0, "players_mid_control_105_115"] == 0


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
    _write_map_ready_inputs(tmp_path)
    silver_dir = tmp_path / "data/silver/parsed_demos"
    silver_dir.mkdir(parents=True)
    _feature_eligible().to_parquet(silver_dir / "feature_eligible_demos.parquet", index=False)
    _rounds().to_parquet(silver_dir / "rounds.parquet", index=False)
    pd.DataFrame(columns=["tick", "event", "round_num", "source_parse_id"]).to_parquet(silver_dir / "bomb.parquet", index=False)
    pd.DataFrame({"source_parse_id": ["parse1"], "round_num": [1], "tick": [100], "X": [0], "Y": [0], "Z": [0], "side": ["t"], "name": ["p1"], "steamid": ["1"], "place": ["Middle"], "health": [100], "inventory": [["Smoke Grenade"]], "series_id": ["series1"], "target_team": ["Vitality"], "map_name": ["Mirage"]}).to_parquet(silver_dir / "ticks.parquet", index=False)
    pd.DataFrame(columns=["entity_id", "tick"]).to_parquet(silver_dir / "grenades.parquet", index=False)
    out = Path("data/gold/round_features/round_features_mvp.csv")
    old_content = out.read_text(encoding="utf-8") if out.exists() else None

    _, outputs, summary = run_feature_pipeline(config_path, dry_run=True, map_registry_path=tmp_path / "configs/maps/map_registry.yaml")

    assert outputs == {}
    assert summary["rounds_generated"] == 2
    if old_content is not None:
        assert out.read_text(encoding="utf-8") == old_content


def test_feature_pipeline_target_map_uses_canonical_identity(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_map_ready_inputs(tmp_path, include_inferno=True)
    silver_dir = tmp_path / "data/silver/parsed_demos"
    silver_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "parse_id": "inferno_parse",
                "dem_file_id": "inferno_demo",
                "series_id": "series_inferno",
                "local_archive_id": "archive_inferno",
                "target_team": "Vitality",
                "opponent": "unknown",
                "inferred_map_name": "de_inferno",
                "feature_eligible": True,
            }
        ]
    ).to_parquet(silver_dir / "feature_eligible_demos.parquet", index=False)
    pd.DataFrame(
        [
            {"round_num": 1, "start": 0, "freeze_end": 100, "end": 1000, "winner": "t", "reason": "bomb_exploded", "bomb_plant": 500, "bomb_site": "bombsite_a", "map_name": "de_inferno", "source_parse_id": "inferno_parse"}
        ]
    ).to_parquet(silver_dir / "rounds.parquet", index=False)
    pd.DataFrame(columns=["tick", "event", "round_num", "source_parse_id"]).to_parquet(silver_dir / "bomb.parquet", index=False)
    pd.DataFrame(
        {
            "source_parse_id": ["inferno_parse"],
            "round_num": [1],
            "tick": [100],
            "X": [0],
            "Y": [0],
            "Z": [0],
            "side": ["t"],
            "name": ["p1"],
            "steamid": ["1"],
            "place": ["Middle"],
            "health": [100],
            "inventory": [["Smoke Grenade"]],
            "series_id": ["series_inferno"],
            "target_team": ["Vitality"],
            "map_name": ["de_inferno"],
        }
    ).to_parquet(silver_dir / "ticks.parquet", index=False)
    pd.DataFrame(columns=["entity_id", "tick"]).to_parquet(silver_dir / "grenades.parquet", index=False)

    _, _, summary = run_feature_pipeline(config_path, dry_run=True, target_map="Inferno", map_registry_path=tmp_path / "configs/maps/map_registry.yaml")

    assert summary["rounds_generated"] == 1


def _write_map_ready_inputs(tmp_path: Path, *, include_inferno: bool = False) -> None:
    maps_dir = tmp_path / "configs" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    inferno_entry = """
  - map_id: inferno
    display_name: Inferno
    game_map_name: de_inferno
    config_path: configs/maps/inferno.yaml
    region_schema_version: v1
    status: onboarding
    is_reference_map: false
""" if include_inferno else ""
    (maps_dir / "map_registry.yaml").write_text(
        """
registry_version: v1
maps:
  - map_id: mirage
    display_name: Mirage
    game_map_name: de_mirage
    config_path: configs/maps/mirage.yaml
    region_schema_version: v1
    status: active
    is_reference_map: true
""".strip() + inferno_entry,
        encoding="utf-8",
    )
    (maps_dir / "mirage.yaml").write_text(
        """
map_id: mirage
display_name: Mirage
game_map_name: de_mirage
region_schema_version: v1
coordinate_system:
  source: test
physical_regions:
  - region_id: mid
    display_name: Mid
    geometry:
      type: named_area
      source_region_group: MID_CONTROL
    semantic_tags: [mid_control]
    site_affinity: []
    region_scope: map_specific
    priority: 100
    boundary_policy: existing_behavior
    aliases: [Middle]
    status: active
semantic_groups:
  mid_control:
    description: Mid control.
    member_regions: [mid]
aliases:
  mid: [Middle]
bombsites:
  A:
    region_ids: [mid]
  B:
    region_ids: [mid]
""".strip(),
        encoding="utf-8",
    )
    if include_inferno:
        (maps_dir / "inferno.yaml").write_text(
            """
map_id: inferno
display_name: Inferno
game_map_name: de_inferno
region_schema_version: v1
coordinate_system:
  source: test
physical_regions:
  - region_id: mid
    display_name: Mid
    geometry:
      type: named_area
      source_region_group: MID_CONTROL
    semantic_tags: [mid_control]
    site_affinity: []
    region_scope: map_specific
    priority: 100
    boundary_policy: existing_behavior
    aliases: [Middle]
    status: active
semantic_groups:
  mid_control:
    description: Mid control.
    member_regions: [mid]
aliases:
  mid: [Middle]
bombsites:
  A:
    region_ids: [mid]
  B:
    region_ids: [mid]
""".strip(),
            encoding="utf-8",
        )
    contract_dir = tmp_path / "data" / "gold" / "features" / "feature_contract"
    contract_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "feature_contract_version": "v1",
                "feature_name": "players_mid_control_0_15",
                "feature_family": "region_position",
                "map_scope": "map_abstract",
                "region_dependency": True,
                "region_semantic": "mid_control",
            },
            {
                "feature_contract_version": "v1",
                "feature_name": "team_smokes_start",
                "feature_family": "utility",
                "map_scope": "global",
                "region_dependency": False,
                "region_semantic": None,
            },
        ]
    ).to_parquet(contract_dir / "feature_contract.parquet", index=False)
    candidate_dir = tmp_path / "data" / "gold" / "modeling" / "t_side_ab_candidate"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"feature_name": ["players_mid_control_0_15"]}).to_parquet(candidate_dir / "candidate_model_feature_set.parquet", index=False)
