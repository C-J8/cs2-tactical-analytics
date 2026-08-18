from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.maps.discover_map_areas import (
    build_mirage_crosswalk,
    build_place_coverage,
    build_place_inventory,
    build_scope_context,
    parse_ids_for_scope,
    prepare_tick_scan,
    run_area_discovery,
)
from src.maps.identity import resolve_map_identity
from src.maps.registry import load_map_registry


def _write_project(tmp_path: Path) -> Path:
    config = tmp_path / "configs/project.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-01-01"
date_end: "2026-12-31"
target_maps: [Mirage]
target_teams: [Vitality]
output_formats: [csv, parquet]
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
parse_manifest_dir: {(tmp_path / 'data/bronze/parse_manifest').as_posix()}
""".strip(),
        encoding="utf-8",
    )
    _write_registry(tmp_path)
    return config


def _write_registry(tmp_path: Path) -> None:
    registry = tmp_path / "configs/maps/map_registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        """
registry_version: v1
maps:
- map_id: mirage
  display_name: Mirage
  game_map_name: de_mirage
  config_path: configs/maps/mirage.yaml
  status: active
- map_id: inferno
  display_name: Inferno
  game_map_name: de_inferno
  config_path: configs/maps/inferno.yaml
  status: onboarding
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "configs/maps/mirage.yaml").write_text(
        """
map_id: mirage
display_name: Mirage
game_map_name: de_mirage
region_schema_version: v1
physical_regions:
- region_id: mid
  display_name: Mid
  geometry:
    type: named_area
    area_names: [Middle]
  semantic_tags: [mid_control]
  site_affinity: []
  region_scope: map_specific
  priority: 1
  boundary_policy: existing_behavior
  aliases: [Middle]
  status: active
- region_id: a_site
  display_name: A Bombsite
  geometry:
    type: named_area
    source_place_aliases: [BombsiteA]
  semantic_tags: [site_a]
  site_affinity: [A]
  region_scope: map_specific
  priority: 1
  boundary_policy: existing_behavior
  aliases: [A Site]
  status: active
- region_id: connector
  display_name: Connector
  geometry:
    type: named_area
    area_names: [Connector]
  semantic_tags: [mid_control]
  site_affinity: []
  region_scope: map_specific
  priority: 1
  boundary_policy: existing_behavior
  aliases: [Shared]
  status: active
- region_id: window
  display_name: Window
  geometry:
    type: named_area
    area_names: [Window]
  semantic_tags: [mid_control]
  site_affinity: []
  region_scope: map_specific
  priority: 1
  boundary_policy: existing_behavior
  aliases: [Shared]
  status: active
semantic_groups: {}
aliases:
  mid: [Middle]
  a_site: [A Site]
  connector: [Shared]
  window: [Shared]
bombsites: {}
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "configs/maps/inferno.yaml").write_text(
        """
map_id: inferno
display_name: Inferno
game_map_name: de_inferno
region_schema_version: v1
physical_regions:
- region_id: inferno_unresolved
  display_name: Inferno Unresolved
  geometry:
    type: named_area
    area_names: []
  semantic_tags: []
  site_affinity: []
  region_scope: map_specific
  priority: 1
  boundary_policy: existing_behavior
  aliases: []
  status: unresolved
semantic_groups: {}
aliases:
  inferno_unresolved: []
bombsites: {}
""".strip(),
        encoding="utf-8",
    )


def _write_parse_manifest(tmp_path: Path) -> None:
    path = tmp_path / "data/bronze/parse_manifest"
    path.mkdir(parents=True)
    pd.DataFrame(
        [
            {"parse_id": "mirage1", "target_team": "Vitality", "map_name": "Mirage", "parse_status": "parsed"},
            {"parse_id": "inferno1", "target_team": "Vitality", "map_name": "de_inferno", "parse_status": "parsed"},
            {"parse_id": "inferno2", "target_team": "Vitality", "map_name": "Inferno", "parse_status": "parsed"},
        ]
    ).to_parquet(path / "parse_manifest.parquet", index=False)


def _write_ticks(tmp_path: Path, *, place_column: str = "place", all_null_place: bool = False, include_place: bool = True, include_xyz: bool = True) -> None:
    path = tmp_path / "data/silver/parsed_demos"
    path.mkdir(parents=True, exist_ok=True)
    rows = []
    def row(parse_id: str, round_num: int, tick: int, steamid: str, place: str | None, x: float, y: float, z: float, side: str) -> dict[str, object]:
        data: dict[str, object] = {"source_parse_id": parse_id, "round_num": round_num, "tick": tick, "steamid": steamid, "side": side}
        if include_place:
            data[place_column] = None if all_null_place else place
        if include_xyz:
            data.update({"X": x, "Y": y, "Z": z})
        return data

    rows.extend(
        [
            row("mirage1", 1, 1, "s1", "Middle", 0, 0, 0, "T"),
            row("mirage1", 1, 2, "s2", "BombsiteA", 100, 100, 10, "CT"),
            row("mirage1", 2, 3, "s3", "Shared", 200, 200, 20, "T"),
            row("inferno1", 1, 1, "s1", "Banana", 0, 10, 0, "T"),
            row("inferno1", 1, 2, "s2", "Banana", 10, 20, 5, "CT"),
            row("inferno1", 2, 3, "s1", "Pit", 100, 110, 15, "T"),
            row("inferno2", 1, 1, "s3", "Rare", 200, 210, 25, "T"),
        ]
    )
    pd.DataFrame(rows).to_parquet(path / "ticks.parquet", index=False)


def test_aliases_use_same_inferno_scope(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path)

    results = [run_area_discovery(config, map_name=value, target_team="Vitality", dry_run=True)[2] for value in ["Inferno", "inferno", "de_inferno"]]

    assert {result["map_id"] for result in results} == {"inferno"}
    assert {result["source_demos"] for result in results} == {2}
    assert {result["unique_places"] for result in results} == {3}


def test_mirage_and_inferno_outputs_are_isolated_and_upserted(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path)

    run_area_discovery(config, map_name="Mirage", target_team="Vitality", force=True)
    run_area_discovery(config, map_name="Inferno", target_team="Vitality", force=True)
    run_area_discovery(config, map_name="de_inferno", target_team="Vitality", force=True)

    inventory = pd.read_parquet(tmp_path / "data/gold/maps/area_discovery/map_place_inventory.parquet")

    assert set(inventory["map_id"]) == {"mirage", "inferno"}
    assert len(inventory[inventory["map_id"].eq("mirage")]) == 3
    assert len(inventory[inventory["map_id"].eq("inferno")]) == 3


def test_unknown_map_fails_clearly(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path)

    with pytest.raises(ValueError, match="Unknown map identity"):
        run_area_discovery(config, map_name="Cache", target_team="Vitality", dry_run=True)


@pytest.mark.parametrize("place_column", ["place", "last_place_name", "place_name"])
def test_place_column_detection_variants(tmp_path: Path, place_column: str) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path, place_column=place_column)

    frames, _, summary = run_area_discovery(config, map_name="Inferno", target_team="Vitality", dry_run=True)

    assert summary["status"] == "ok"
    assert frames["map_area_discovery_summary"].loc[0, "place_column"] == place_column


def test_missing_or_all_null_place_fails(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path, include_place=False)

    frames, _, summary = run_area_discovery(config, map_name="Inferno", target_team="Vitality", dry_run=True)

    assert summary["status"] == "failed"
    assert "no_place_column" in set(frames["map_area_discovery_unknowns"]["unknown_type"])

    _write_ticks(tmp_path, all_null_place=True)
    frames, _, summary = run_area_discovery(config, map_name="Inferno", target_team="Vitality", dry_run=True)

    assert summary["status"] == "failed"
    assert "all_place_null" in set(frames["map_area_discovery_unknowns"]["unknown_type"])


def test_inventory_counts_shares_and_rare_place_are_retained(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path)

    frames, _, _ = run_area_discovery(config, map_name="Inferno", target_team="Vitality", dry_run=True)
    inventory = frames["map_place_inventory"].set_index("raw_place")
    coverage = frames["map_place_coverage"].set_index("raw_place")

    assert inventory.loc["Banana", "tick_count"] == 2
    assert inventory.loc["Banana", "demo_count"] == 1
    assert inventory.loc["Banana", "round_count"] == 1
    assert inventory.loc["Banana", "player_count"] == 2
    assert inventory["tick_share"].sum() == pytest.approx(1.0)
    assert "Rare" in inventory.index
    assert coverage.loc["Rare", "coverage_status"] == "moderate"


def test_coordinate_percentiles_vertical_profile_and_null_coordinates(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path)

    frames, _, _ = run_area_discovery(config, map_name="Inferno", target_team="Vitality", dry_run=True)
    coords = frames["map_place_coordinates"].set_index("raw_place")
    vertical = frames["map_place_vertical_profile"].set_index("raw_place")

    assert coords.loc["Banana", "x_min"] == 0
    assert coords.loc["Banana", "x_max"] == 10
    assert coords.loc["Banana", "x_median"] == pytest.approx(5)
    assert coords.loc["Banana", "x_p25"] == pytest.approx(2.5)
    assert vertical.loc["Banana", "z_range"] == 5

    path = tmp_path / "data/silver/parsed_demos/ticks.parquet"
    data = pd.read_parquet(path)
    data.loc[data["place"].eq("Pit"), "X"] = None
    data.to_parquet(path, index=False)
    frames, _, _ = run_area_discovery(config, map_name="Inferno", target_team="Vitality", dry_run=True)

    assert "invalid_coordinates" in set(frames["map_area_discovery_unknowns"]["unknown_type"])


def test_crosswalk_matches_exact_display_alias_geometry_unmatched_and_ambiguous(tmp_path: Path) -> None:
    _write_project(tmp_path)
    registry_path = tmp_path / "configs/maps/map_registry.yaml"
    registry = load_map_registry("Mirage", registry_path=registry_path)
    inventory = pd.DataFrame(
        [
            {"map_id": "mirage", "map_name": "Mirage", "target_team": "Vitality", "raw_place": "mid", "normalized_place_id": "mid", "tick_count": 10},
            {"map_id": "mirage", "map_name": "Mirage", "target_team": "Vitality", "raw_place": "A Bombsite", "normalized_place_id": "a_bombsite", "tick_count": 9},
            {"map_id": "mirage", "map_name": "Mirage", "target_team": "Vitality", "raw_place": "Middle", "normalized_place_id": "middle", "tick_count": 8},
            {"map_id": "mirage", "map_name": "Mirage", "target_team": "Vitality", "raw_place": "BombsiteA", "normalized_place_id": "bombsitea", "tick_count": 7},
            {"map_id": "mirage", "map_name": "Mirage", "target_team": "Vitality", "raw_place": "Shared", "normalized_place_id": "shared", "tick_count": 6},
            {"map_id": "mirage", "map_name": "Mirage", "target_team": "Vitality", "raw_place": "Unknown", "normalized_place_id": "unknown", "tick_count": 5},
        ]
    )

    crosswalk = build_mirage_crosswalk(inventory, registry=registry, target_team="Vitality").set_index("raw_place")

    assert crosswalk.loc["mid", "match_source"] == "region_id"
    assert crosswalk.loc["A Bombsite", "match_source"] == "display_name"
    assert crosswalk.loc["Middle", "match_source"] == "alias"
    assert crosswalk.loc["BombsiteA", "match_source"] == "geometry_area_name"
    assert bool(crosswalk.loc["Shared", "ambiguous"])
    assert crosswalk.loc["Unknown", "status"] == "unresolved"


def test_scope_helpers_use_canonical_identity(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    parse_manifest = pd.read_parquet(tmp_path / "data/bronze/parse_manifest/parse_manifest.parquet")
    registry_path = tmp_path / "configs/maps/map_registry.yaml"

    assert parse_ids_for_scope(parse_manifest, target_map="inferno", target_team="Vitality", registry_path=registry_path) == {"inferno1", "inferno2"}
    assert resolve_map_identity("de_inferno", registry_path=registry_path).map_id == "inferno"


def test_safety_does_not_modify_map_configs_or_feature_outputs(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path)
    mirage = tmp_path / "configs/maps/mirage.yaml"
    inferno = tmp_path / "configs/maps/inferno.yaml"
    feature_contract = tmp_path / "configs/features/feature_contract.yaml"
    feature_contract.parent.mkdir(parents=True)
    feature_contract.write_text("feature_contract_version: test\n", encoding="utf-8")
    before = {path: path.read_text(encoding="utf-8") for path in [mirage, inferno, feature_contract]}

    run_area_discovery(config, map_name="Inferno", target_team="Vitality", force=True)

    assert {path: path.read_text(encoding="utf-8") for path in [mirage, inferno, feature_contract]} == before
    assert not (tmp_path / "data/gold/modeling").exists()
    assert not (tmp_path / "data/gold/round_features").exists()


def test_missing_xyz_fails(tmp_path: Path) -> None:
    config = _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path, include_xyz=False)

    frames, _, summary = run_area_discovery(config, map_name="Inferno", target_team="Vitality", dry_run=True)

    assert summary["status"] == "failed"
    assert "missing_xyz" in set(frames["map_area_discovery_unknowns"]["unknown_type"])


def test_low_level_builders_work_with_lazy_scans(tmp_path: Path) -> None:
    _write_project(tmp_path)
    _write_parse_manifest(tmp_path)
    _write_ticks(tmp_path)
    ticks_path = tmp_path / "data/silver/parsed_demos/ticks.parquet"
    identity = resolve_map_identity("Inferno", registry_path=tmp_path / "configs/maps/map_registry.yaml")
    context = build_scope_context(ticks_path, parse_ids={"inferno1", "inferno2"}, identity=identity, target_team="Vitality", min_observations=1)
    scan = prepare_tick_scan(context["scan"], context["schema_names"], context["place_column"], parse_ids={"inferno1", "inferno2"})

    inventory = build_place_inventory(scan, identity=identity, target_team="Vitality", total_ticks=context["tick_count"], min_observations=1)
    by_demo = run_area_discovery(tmp_path / "configs/project.yaml", map_name="Inferno", target_team="Vitality", dry_run=True)[0]["map_place_by_demo"]
    coverage = build_place_coverage(inventory, by_demo, identity=identity, target_team="Vitality", context=context)

    assert not inventory.empty
    assert not coverage.empty
