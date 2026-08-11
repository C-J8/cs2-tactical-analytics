from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.features.map_refactor_audit import build_compatibility_table
from src.maps.geometry import UnsupportedGeometryError, contains_point
from src.maps.registry import load_map_registry, registry_from_config
from src.maps.semantic import legacy_feature_groups_for_registry, resolve_feature_requirements


def _registry_config() -> dict:
    return {
        "map_id": "mirage",
        "display_name": "Mirage",
        "game_map_name": "de_mirage",
        "region_schema_version": "v1",
        "coordinate_system": {"source": "test"},
        "physical_regions": [
            _region("mid", "Mid", "MID_CONTROL", ["mid_control"]),
            _region("a_ramp", "A Ramp", "A_PRESSURE", ["a_pressure"], site=["A"]),
            _region("palace", "Palace", "A_PRESSURE", ["a_pressure"], site=["A"]),
            _region("a_site", "A Site", "BOMB_SITE_A", ["site_a"], site=["A"]),
            _region("b_site", "B Site", "BOMB_SITE_B", ["site_b"], site=["B"]),
            _region("box", "Box", "BOX", ["box_control"], geometry={"type": "bounding_box", "x_min": 0, "x_max": 10, "y_min": 0, "y_max": 10, "z_min": 0, "z_max": 5}),
        ],
        "semantic_groups": {
            "mid_control": {"description": "Mid.", "member_regions": ["mid"]},
            "a_pressure": {"description": "A pressure.", "member_regions": ["a_ramp", "palace"]},
            "site_a": {"description": "Site A.", "member_regions": ["a_site"]},
            "site_b": {"description": "Site B.", "member_regions": ["b_site"]},
            "box_control": {"description": "Box.", "member_regions": ["box"]},
        },
        "aliases": {"mid": ["Middle"], "a_ramp": ["Ramp"], "palace": ["Palace"], "a_site": ["A Site"], "b_site": ["B Site"], "box": ["Box"]},
        "bombsites": {"A": {"region_ids": ["a_site"]}, "B": {"region_ids": ["b_site"]}},
    }


def _region(
    region_id: str,
    display_name: str,
    legacy_group: str,
    semantic_tags: list[str],
    *,
    site: list[str] | None = None,
    geometry: dict | None = None,
) -> dict:
    return {
        "region_id": region_id,
        "display_name": display_name,
        "geometry": geometry or {"type": "named_area", "source_region_group": legacy_group},
        "semantic_tags": semantic_tags,
        "site_affinity": site or [],
        "region_scope": "map_specific",
        "priority": 100,
        "boundary_policy": "existing_behavior",
        "aliases": [display_name],
        "status": "active",
    }


def _registry():
    return registry_from_config(_registry_config(), registry_version="v1")


def test_map_name_variants_load_same_registry(tmp_path: Path) -> None:
    maps_dir = tmp_path / "configs" / "maps"
    maps_dir.mkdir(parents=True)
    (maps_dir / "map_registry.yaml").write_text(
        "registry_version: v1\nmaps:\n- map_id: mirage\n  display_name: Mirage\n  game_map_name: de_mirage\n  config_path: configs/maps/mirage.yaml\n  region_schema_version: v1\n",
        encoding="utf-8",
    )
    import yaml

    (maps_dir / "mirage.yaml").write_text(yaml.safe_dump(_registry_config(), sort_keys=False), encoding="utf-8")

    assert load_map_registry("Mirage", registry_path=maps_dir / "map_registry.yaml").map_id == "mirage"
    assert load_map_registry("mirage", registry_path=maps_dir / "map_registry.yaml").map_id == "mirage"
    assert load_map_registry("de_mirage", registry_path=maps_dir / "map_registry.yaml").map_id == "mirage"


def test_unknown_map_fails_clearly(tmp_path: Path) -> None:
    maps_dir = tmp_path / "configs" / "maps"
    maps_dir.mkdir(parents=True)
    (maps_dir / "map_registry.yaml").write_text("registry_version: v1\nmaps: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Map registry entry not found"):
        load_map_registry("Inferno", registry_path=maps_dir / "map_registry.yaml")


def test_bounding_box_boundary_and_z_are_respected() -> None:
    region = _registry().get_region("box")

    assert contains_point(region, 0, 0, 0)
    assert contains_point(region, 10, 10, 5)
    assert not contains_point(region, 10, 10, 6)
    assert not contains_point(region, -1, 5, 1)


def test_polygon_and_named_area_geometry_behaviour() -> None:
    polygon = _region("poly", "Poly", "POLY", ["poly"], geometry={"type": "polygon", "points": [[0, 0], [10, 0], [10, 10], [0, 10]]})
    named = _registry().get_region("mid")

    assert contains_point(registry_from_config({**_registry_config(), "physical_regions": [polygon]}, registry_version="v1").get_region("poly"), 5, 5)
    with pytest.raises(UnsupportedGeometryError, match="place-name based"):
        contains_point(named, 1, 1)


def test_composite_semantic_group_resolves_multiple_regions() -> None:
    registry = _registry()

    assert {region.region_id for region in registry.regions_for_semantic("a_pressure")} == {"a_ramp", "palace"}
    assert {region.region_id for region in registry.regions_for_site("A")} == {"a_site"}
    assert {region.region_id for region in registry.regions_for_site("B")} == {"b_site"}


def test_legacy_feature_groups_are_derived_from_registry() -> None:
    groups = legacy_feature_groups_for_registry(_registry(), ["mid_control", "a_pressure"])

    assert groups == {"A_PRESSURE": "a_pressure", "MID_CONTROL": "mid_control"}


def test_feature_contract_resolution_policy() -> None:
    contract = pd.DataFrame(
        [
            {"feature_name": "team_smokes_start", "feature_family": "utility", "map_scope": "global", "region_dependency": False, "region_semantic": None},
            {"feature_name": "players_mid_control_0_15", "feature_family": "region_position", "map_scope": "map_abstract", "region_dependency": True, "region_semantic": "mid_control"},
            {"feature_name": "players_palace_control_0_15", "feature_family": "region_position", "map_scope": "map_specific", "region_dependency": True, "region_semantic": "mirage_palace"},
            {"feature_name": "players_missing_0_15", "feature_family": "region_position", "map_scope": "map_abstract", "region_dependency": True, "region_semantic": "missing"},
        ]
    )

    usage = resolve_feature_requirements(contract, _registry()).set_index("feature_name")

    assert usage.loc["team_smokes_start", "resolution_source"] == "global"
    assert bool(usage.loc["players_mid_control_0_15", "resolved"])
    assert usage.loc["players_palace_control_0_15", "resolution_source"] == "physical_region"
    assert not bool(usage.loc["players_missing_0_15", "resolved"])


def test_compatibility_table_accepts_identical_feature_outputs() -> None:
    before = pd.DataFrame({"round_feature_id": ["r1"], "players_mid_control_0_15": [2], "target_site_model_label": ["A"]})
    candidates = pd.DataFrame({"feature_name": ["players_mid_control_0_15"]})

    compatibility = build_compatibility_table({"round_features_mvp": before}, {"round_features_mvp": before.copy()}, candidates)

    assert set(compatibility["status"]) <= {"ok", "warning"}
    candidate = compatibility[compatibility["column_name"] == "players_mid_control_0_15"].iloc[0]
    assert candidate["exact_match"]


def test_compatibility_table_detects_candidate_value_change_and_missing_column() -> None:
    before = pd.DataFrame({"round_feature_id": ["r1"], "players_mid_control_0_15": [2], "removed_feature": [1]})
    after = pd.DataFrame({"round_feature_id": ["r1"], "players_mid_control_0_15": [3]})
    candidates = pd.DataFrame({"feature_name": ["players_mid_control_0_15"]})

    compatibility = build_compatibility_table({"round_features_mvp": before}, {"round_features_mvp": after}, candidates)

    changed = compatibility[compatibility["column_name"] == "players_mid_control_0_15"].iloc[0]
    removed = compatibility[compatibility["column_name"] == "removed_feature"].iloc[0]
    assert changed["status"] == "failed"
    assert removed["status"] == "failed"
