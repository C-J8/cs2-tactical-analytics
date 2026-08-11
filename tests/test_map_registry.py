from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.maps.build_map_registry import OUTPUT_NAMES, run_map_registry
from src.maps.registry import VALID_GEOMETRY_TYPES, load_map_registry, registry_from_config, validate_map_registry


def _write_fixture(tmp_path: Path, *, unresolved_candidate: bool = False) -> Path:
    config = tmp_path / "configs" / "project.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-07-07"
target_maps: [Mirage]
target_teams: [Vitality]
output_formats: [csv, parquet]
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
""".strip(),
        encoding="utf-8",
    )
    _write_mirage_regions(tmp_path / "configs" / "maps" / "mirage_regions.yaml")
    _write_feature_contract(tmp_path, unresolved_candidate=unresolved_candidate)
    _write_upstream_round_features(tmp_path)
    return config


def _write_mirage_regions(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
map_name: Mirage
place_column_candidates:
  - last_place_name
regions:
  - region_name: T Spawn
    region_group: T_SPAWN_AREA
    aliases: [T Spawn, TSpawn]
  - region_name: Mid
    region_group: MID_CONTROL
    aliases: [Mid, Middle]
  - region_name: Connector
    region_group: MID_CONTROL
    aliases: [Connector]
  - region_name: A Ramp
    region_group: A_PRESSURE
    aliases: [A Ramp, TRamp, Ramp]
  - region_name: Palace
    region_group: A_PRESSURE
    aliases: [Palace, PalaceInterior]
  - region_name: A Site
    region_group: BOMB_SITE_A
    aliases: [A Site, BombsiteA]
  - region_name: B Apps
    region_group: B_PRESSURE
    aliases: [B Apps, Apartments]
  - region_name: B Site
    region_group: BOMB_SITE_B
    aliases: [B Site, BombsiteB]
  - region_name: Market
    region_group: CT_SPACE
    aliases: [Market, Shop]
  - region_name: Jungle
    region_group: ROTATION_AREA
    aliases: [Jungle, Underpass]
""".strip(),
        encoding="utf-8",
    )


def _write_feature_contract(tmp_path: Path, *, unresolved_candidate: bool) -> None:
    contract_dir = tmp_path / "data" / "gold" / "features" / "feature_contract"
    rows = [
        _feature("team_smokes_start", False, None, "global"),
        _feature("players_mid_control_0_15", True, "mid_control", "map_abstract"),
        _feature("players_a_pressure_0_15", True, "a_pressure", "map_abstract"),
        _feature("players_b_pressure_0_15", True, "b_pressure", "map_abstract"),
        _feature("players_ct_space_0_15", True, "ct_space", "map_abstract"),
        _feature("players_palace_control_0_15", True, "mirage_palace", "map_specific", mirage_specific=True),
    ]
    if unresolved_candidate:
        rows.append(_feature("players_unknown_lane_0_15", True, "unknown_lane", "map_abstract"))
    _write(contract_dir, "feature_contract", rows)
    _write(contract_dir, "feature_contract_map_readiness", [{"feature_name": row["feature_name"]} for row in rows])
    feature_config = tmp_path / "configs" / "features" / "feature_contract.yaml"
    feature_config.parent.mkdir(parents=True, exist_ok=True)
    feature_config.write_text("feature_contract_version: v1\n", encoding="utf-8")
    candidate_rows = [{"feature_name": "players_mid_control_0_15"}]
    if unresolved_candidate:
        candidate_rows.append({"feature_name": "players_unknown_lane_0_15"})
    _write(tmp_path / "data" / "gold" / "modeling" / "t_side_ab_candidate", "candidate_model_feature_set", candidate_rows)


def _feature(
    name: str,
    region_dependency: bool,
    semantic: str | None,
    map_scope: str,
    *,
    mirage_specific: bool = False,
) -> dict[str, object]:
    return {
        "feature_name": name,
        "feature_family": "region_position" if region_dependency else "utility",
        "semantic_role": "map_region_control" if region_dependency else "global_utility",
        "region_dependency": region_dependency,
        "region_semantic": semantic,
        "map_scope": map_scope,
        "mirage_specific": mirage_specific,
    }


def _write_upstream_round_features(tmp_path: Path) -> None:
    rows = [{"round_feature_id": "rf_1", "players_mid_control_0_15": 2}]
    output_dir = tmp_path / "data" / "gold" / "round_features"
    for name in ["round_features_mvp", "round_features_t_side_all", "round_features_t_side_planted"]:
        _write(output_dir, name, rows)


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_map_registry_cli_dry_run(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "src.maps.build_map_registry", "--config", str(config), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Map Registry summary" in result.stdout
    assert not (tmp_path / "data/gold/maps/map_registry").exists()
    assert not (tmp_path / "configs/maps/map_registry.yaml").exists()


def test_force_generates_outputs_configs_doc_and_notebook(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, outputs, _ = run_map_registry(config, force=True)

    assert len(outputs) == len(OUTPUT_NAMES) * 2 + 4
    assert all(path.exists() for path in outputs.values())
    assert (tmp_path / "configs/maps/map_registry.yaml").exists()
    assert (tmp_path / "configs/maps/mirage.yaml").exists()
    assert outputs["report"].read_text(encoding="utf-8").startswith("# Map Geometry & Region Registry")
    json.loads(outputs["notebook"].read_text(encoding="utf-8"))
    assert set(OUTPUT_NAMES) <= set(frames)


def test_loader_helpers_and_registry_integrity(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    run_map_registry(config, force=True)
    registry = load_map_registry("Mirage", registry_path=tmp_path / "configs" / "maps" / "map_registry.yaml")

    assert registry.map_id == "mirage"
    assert registry.get_region("palace").display_name == "Palace"
    assert {region.region_id for region in registry.regions_for_semantic("a_pressure")} == {"a_ramp", "palace"}
    assert {region.region_id for region in registry.regions_for_site("A")} == {"a_site"}
    assert {region.region_id for region in registry.regions_for_site("B")} == {"b_site"}
    assert set(registry.aliases) <= set(registry.physical_regions)


def test_output_tables_have_unique_ids_valid_refs_geometry_and_priorities(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_map_registry(config, force=True)

    maps = frames["map_registry"]
    regions = frames["map_region_registry"]
    groups = frames["map_semantic_groups"]
    mapping = frames["map_region_semantic_mapping"]
    bombsites = frames["map_bombsite_registry"]

    assert maps["map_id"].is_unique
    assert regions["region_id"].is_unique
    assert groups["semantic_id"].is_unique
    assert set(mapping["region_id"]) <= set(regions["region_id"])
    assert set(mapping["semantic_id"]) <= set(groups["semantic_id"])
    assert {"A", "B"} <= set(bombsites["bombsite"])
    assert set(bombsites["region_id"]) <= set(regions["region_id"])
    assert set(regions["geometry_type"]) <= VALID_GEOMETRY_TYPES
    assert pd.api.types.is_numeric_dtype(regions["priority"])


def test_feature_contract_coverage_resolves_map_abstract_and_map_specific(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_map_registry(config, force=True)
    coverage = frames["map_feature_semantic_coverage"].set_index("feature_name")

    assert bool(coverage.loc["players_mid_control_0_15", "map_ready"])
    assert bool(coverage.loc["players_a_pressure_0_15", "map_ready"])
    assert bool(coverage.loc["players_b_pressure_0_15", "map_ready"])
    assert bool(coverage.loc["players_palace_control_0_15", "map_ready"])
    assert coverage.loc["players_palace_control_0_15", "physical_regions"] == "palace"
    assert bool(coverage.loc["players_palace_control_0_15", "requires_equivalent_decision_for_new_maps"])


def test_unresolved_candidate_feature_blocks_stage_8_2_readiness(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path, unresolved_candidate=True)
    frames, _, _ = run_map_registry(config, dry_run=True)
    audit = frames["map_registry_audit"].iloc[0]
    unknowns = frames["map_region_unknowns"]

    assert int(audit["candidate_region_features_unresolved"]) == 1
    assert not bool(audit["ready_for_map_feature_refactor"])
    assert not unknowns.empty
    assert "unknown_lane" in set(unknowns["reference_name"])


def test_invalid_yaml_fails_with_clear_message() -> None:
    registry = registry_from_config(
        {
            "map_id": "mirage",
            "display_name": "Mirage",
            "game_map_name": "de_mirage",
            "region_schema_version": "v1",
            "physical_regions": [
                {
                    "region_id": "palace",
                    "geometry": {"type": "named_area"},
                    "priority": 100,
                    "boundary_policy": "existing_behavior",
                }
            ],
            "semantic_groups": {"a_pressure": {"member_regions": ["missing_region"]}},
            "bombsites": {"A": {"region_ids": ["palace"]}, "B": {"region_ids": ["palace"]}},
        },
        registry_version="v1",
    )

    with pytest.raises(ValueError, match="references unknown regions"):
        validate_map_registry(registry)


def test_map_registry_does_not_modify_upstream_datasets(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    upstream = [
        tmp_path / "data/gold/round_features/round_features_mvp.parquet",
        tmp_path / "data/gold/round_features/round_features_t_side_all.parquet",
        tmp_path / "data/gold/round_features/round_features_t_side_planted.parquet",
    ]
    before = {path: _sha256(path) for path in upstream}
    run_map_registry(config, force=True)
    after = {path: _sha256(path) for path in upstream}

    assert after == before
