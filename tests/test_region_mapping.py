from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.maps.build_region_mapping import build_coordinate_validation, run_region_mapping
from src.maps.registry import load_map_registry
from src.maps.semantic import place_lookup_from_registry


def _write_fixture(tmp_path: Path, *, ready: bool = True) -> Path:
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
    _write_registry(tmp_path)
    _write_area_discovery(tmp_path, ready=ready)
    _write_feature_inputs(tmp_path)
    _write_mirage_gate_pass(tmp_path)
    return config


def _write_registry(tmp_path: Path) -> None:
    maps_dir = tmp_path / "configs" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
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
- map_id: inferno
  display_name: Inferno
  game_map_name: de_inferno
  config_path: configs/maps/inferno.yaml
  region_schema_version: v1
  status: onboarding
  is_reference_map: false
""".strip(),
        encoding="utf-8",
    )
    (maps_dir / "mirage.yaml").write_text(
        """
map_id: mirage
display_name: Mirage
game_map_name: de_mirage
region_schema_version: v1
coordinate_system: {source: test}
physical_regions:
- region_id: mid
  display_name: Mid
  geometry: {type: named_area, area_names: [Middle]}
  semantic_tags: [mid_control]
  site_affinity: []
  region_scope: map_specific
  priority: 100
  boundary_policy: existing_behavior
  aliases: [Mid]
  status: active
semantic_groups:
  mid_control:
    member_regions: [mid]
bombsites:
  A: {region_ids: [mid]}
  B: {region_ids: [mid]}
aliases:
  mid: [Mid]
""".strip(),
        encoding="utf-8",
    )
    (maps_dir / "inferno.yaml").write_text(
        """
map_id: inferno
display_name: Inferno
game_map_name: de_inferno
region_schema_version: v1
coordinate_system: {source: pending}
physical_regions:
- region_id: inferno_mid_control_unresolved
  display_name: Inferno Mid Control Unresolved
  geometry: {type: named_area, area_names: []}
  semantic_tags: [mid_control]
  site_affinity: []
  region_scope: map_specific
  priority: 100
  boundary_policy: existing_behavior
  aliases: []
  status: unresolved
semantic_groups:
  mid_control:
    member_regions: [inferno_mid_control_unresolved]
bombsites:
  A: {region_ids: [inferno_mid_control_unresolved]}
  B: {region_ids: [inferno_mid_control_unresolved]}
aliases:
  inferno_mid_control_unresolved: []
""".strip(),
        encoding="utf-8",
    )
    policy_dir = maps_dir / "region_mapping"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "inferno.yaml").write_text(
        """
map_id: inferno
map_name: Inferno
mapping_version: v1
min_mapped_tick_share: 0.95
thresholds:
  absurd_center_spread: 2500.0
  review_center_spread: 1000.0
  review_vertical_spread: 350.0
bombsites:
  A: bombsitea
  B: bombsiteb
place_mappings:
  banana:
    region_id: banana
    display_name: Banana
    mapping_type: direct
    mapping_confidence: high
    review_status: accepted_from_parser_place
    review_basis: [parser_place_name]
    semantic_tags: [b_pressure]
    notes: Direct named-area mapping from observed parser place.
  bombsiteb:
    region_id: bombsiteb
    display_name: Bombsite B
    mapping_type: direct
    mapping_confidence: high
    review_status: accepted_from_parser_place
    review_basis: [parser_place_name]
    semantic_tags: [site_b]
    notes: Direct named-area mapping from observed parser place.
  bombsitea:
    region_id: bombsitea
    display_name: Bombsite A
    mapping_type: direct
    mapping_confidence: high
    review_status: accepted_from_parser_place
    review_basis: [parser_place_name]
    semantic_tags: [site_a]
    notes: Direct named-area mapping from observed parser place.
  middle:
    region_id: middle
    display_name: Middle
    mapping_type: direct
    mapping_confidence: high
    review_status: accepted_from_parser_place
    review_basis: [parser_place_name]
    semantic_tags: [mid_control]
    notes: Direct named-area mapping from observed parser place.
  ctspawn:
    region_id: ctspawn
    display_name: CT Spawn
    mapping_type: direct
    mapping_confidence: high
    review_status: accepted_from_parser_place
    review_basis: [parser_place_name]
    semantic_tags: [ct_space]
    notes: Direct named-area mapping from observed parser place.
  pit:
    region_id: pit
    display_name: Pit
    mapping_type: direct
    mapping_confidence: high
    review_status: accepted_from_parser_place
    review_basis: [parser_place_name]
    semantic_tags: [a_pressure]
    notes: Direct named-area mapping from observed parser place.
  bridge:
    region_id: second_mid_upper
    display_name: Second Mid Upper Route
    mapping_type: grouped
    mapping_confidence: medium
    review_status: accepted_from_coordinate_evidence
    review_basis: [stage_8_6_coordinate_evidence]
    semantic_tags: [mid_control, rotation]
    notes: Grouped with nearby elevated connector places from Stage 8.6 coordinate evidence.
  upstairs:
    region_id: second_mid_upper
    display_name: Second Mid Upper Route
    mapping_type: grouped
    mapping_confidence: medium
    review_status: accepted_from_coordinate_evidence
    review_basis: [stage_8_6_coordinate_evidence]
    semantic_tags: [mid_control, rotation]
    notes: Grouped with nearby elevated connector places from Stage 8.6 coordinate evidence.
""".strip(),
        encoding="utf-8",
    )


def _write_area_discovery(tmp_path: Path, *, ready: bool) -> None:
    area = tmp_path / "data" / "gold" / "maps" / "area_discovery"
    area.mkdir(parents=True, exist_ok=True)
    places = [
        ("Banana", "banana", 1000, 100.0, 500.0, 0.0),
        ("BombsiteB", "bombsiteb", 900, 200.0, 900.0, 0.0),
        ("BombsiteA", "bombsitea", 850, 800.0, 100.0, 0.0),
        ("Middle", "middle", 750, 450.0, 250.0, 0.0),
        ("CTSpawn", "ctspawn", 650, 900.0, 600.0, 0.0),
        ("Pit", "pit", 350, 850.0, 50.0, 0.0),
        ("Bridge", "bridge", 100, 10.0, 10.0, 150.0),
        ("Upstairs", "upstairs", 100, 20.0, 20.0, 155.0),
    ]
    summary = pd.DataFrame(
        [
            {
                "map_id": "inferno",
                "map_name": "Inferno",
                "target_team": "Vitality",
                "demo_count": 1,
                "round_count": 5,
                "tick_count": sum(row[2] for row in places),
                "place_column": "place",
                "place_non_null_rows": sum(row[2] for row in places),
                "place_non_null_share": 1.0,
                "unique_raw_places": len(places),
                "places_seen_all_demos": len(places),
                "places_seen_multiple_demos": len(places),
                "places_seen_one_demo": 0,
                "xyz_available": True,
                "discovery_status": "ok",
                "ready_for_region_mapping": ready,
                "created_at": "2026-08-18T00:00:00+00:00",
            }
        ]
    )
    _write(area, "map_area_discovery_summary", summary)
    inventory = pd.DataFrame(
        [
            {
                "map_id": "inferno",
                "map_name": "Inferno",
                "target_team": "Vitality",
                "raw_place": raw,
                "normalized_place_id": normalized,
                "tick_count": ticks,
                "demo_count": 1,
                "round_count": 5,
                "player_count": 10,
                "demo_coverage_share": 1.0,
                "round_coverage_share": 1.0,
                "coverage_status": "common",
                "x_median": x,
                "y_median": y,
                "z_median": z,
                "x_p05": x - 1,
                "x_p95": x + 1,
                "y_p05": y - 1,
                "y_p95": y + 1,
                "z_p05": z - 1,
                "z_p95": z + 1,
            }
            for raw, normalized, ticks, x, y, z in places
        ]
    )
    _write(area, "inferno_place_discovery", inventory)
    coordinates = inventory.rename(columns={"tick_count": "n_observations"}).copy()
    for axis in ["x", "y", "z"]:
        coordinates[f"{axis}_min"] = coordinates[f"{axis}_median"] - 1
        coordinates[f"{axis}_max"] = coordinates[f"{axis}_median"] + 1
    _write(area, "map_place_coordinates", coordinates)
    _write(area, "map_place_coverage", inventory[["map_id", "map_name", "target_team", "raw_place", "tick_count", "coverage_status"]])
    _write(
        area,
        "map_place_name_stability",
        pd.DataFrame(
            [
                {
                    "map_id": "inferno",
                    "map_name": "Inferno",
                    "target_team": "Vitality",
                    "raw_place": row[0],
                    "coordinate_consistency_status": "stable",
                }
                for row in places
            ]
        ),
    )
    _write(area, "map_place_vertical_profile", inventory[["map_id", "map_name", "target_team", "raw_place", "z_median"]])
    _write(area, "map_place_coordinate_sample", inventory[["map_id", "map_name", "target_team", "raw_place", "x_median", "y_median", "z_median"]])


def _write_feature_inputs(tmp_path: Path) -> None:
    gold = tmp_path / "data" / "gold"
    catalog = pd.DataFrame(
        [
            _catalog("team_smokes_start", "utility"),
            _catalog("team_center_x_10s", "region_position"),
            _catalog("players_mid_control_0_15", "region_position"),
            _catalog("players_a_pressure_0_15", "region_position"),
            _catalog("players_b_pressure_0_15", "region_position"),
            _catalog("players_ct_space_0_15", "region_position"),
            _catalog("players_palace_control_0_15", "region_position"),
        ]
    )
    _write(gold / "analysis" / "t_side_tactical_eda", "t_side_feature_catalog", catalog)
    round_row = {row["column_name"]: 1 for row in catalog.to_dict("records")}
    round_row["round_feature_id"] = "rf_1"
    for name in ["round_features_mvp", "round_features_t_side_all", "round_features_t_side_planted"]:
        _write(gold / "round_features", name, pd.DataFrame([round_row]))
    candidate = pd.DataFrame(
        [
            {"candidate_id": "c1", "feature_name": "team_smokes_start"},
            {"candidate_id": "c1", "feature_name": "team_center_x_10s"},
            {"candidate_id": "c1", "feature_name": "players_mid_control_0_15"},
            {"candidate_id": "c1", "feature_name": "players_palace_control_0_15"},
        ]
    )
    _write(gold / "modeling" / "t_side_ab_candidate", "candidate_model_feature_set", candidate)


def _catalog(column: str, group: str) -> dict[str, object]:
    return {
        "column_name": column,
        "inferred_feature_group": group,
        "window_start": 0,
        "window_end": 15,
        "window_type": "cumulative",
        "usable_for_future_model": True,
    }


def _write_mirage_gate_pass(tmp_path: Path) -> None:
    output = tmp_path / "data" / "gold" / "validation" / "mirage_regression_gate"
    _write(output, "mirage_regression_summary", pd.DataFrame([{"overall_status": "passed"}]))


def _write(directory: Path, name: str, frame: pd.DataFrame) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(directory / f"{name}.parquet", index=False)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stage_8_6_false_blocks_region_mapping(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path, ready=False)

    with pytest.raises(ValueError, match="ready_for_region_mapping is false"):
        run_region_mapping(config, map_name="Inferno", target_team="Vitality", dry_run=True)


def test_region_mapping_generates_outputs_and_preserves_mirage(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    mirage_hash = _sha(tmp_path / "configs/maps/mirage.yaml")
    frames, outputs, summary = run_region_mapping(config, map_name="Inferno", target_team="Vitality", force=True)

    assert summary["status"] == "ok"
    assert summary["mapped_places"] == 8
    assert all(path.exists() for path in outputs.values())
    assert _sha(tmp_path / "configs/maps/mirage.yaml") == mirage_hash
    assert json.loads(outputs["notebook"].read_text(encoding="utf-8"))
    assert outputs["report"].read_text(encoding="utf-8").startswith("# Inferno Physical Region")

    proposal = frames["inferno_region_mapping_proposal"]
    assert proposal.loc[proposal["raw_place"].eq("Banana"), "proposed_region_id"].iloc[0] == "banana"
    assert set(proposal[proposal["mapping_type"].eq("grouped")]["proposed_region_id"]) == {"second_mid_upper"}

    registry = load_map_registry("Inferno", registry_path=tmp_path / "configs/maps/map_registry.yaml")
    lookup = place_lookup_from_registry(registry)
    assert normalize_lookup(lookup, "Banana") == "Banana"
    assert normalize_lookup(lookup, "Bridge") == "Second Mid Upper Route"
    assert {region.region_id for region in registry.regions_for_site("A")} == {"bombsitea"}
    assert {region.region_id for region in registry.regions_for_site("B")} == {"bombsiteb"}

    index_text = (tmp_path / "configs/maps/map_registry.yaml").read_text(encoding="utf-8")
    assert "status: active" in index_text
    assert "is_reference_map: false" in index_text


def test_candidate_portability_and_contract_v2_metadata(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_region_mapping(config, map_name="Inferno", target_team="Vitality", dry_run=True)
    candidate = frames["inferno_candidate_feature_portability_v2"].set_index("feature_name")

    assert candidate.loc["team_smokes_start", "cross_map_comparison_mode"] == "direct"
    assert candidate.loc["team_center_x_10s", "coordinate_dependency"] == "raw_map_coordinates"
    assert not bool(candidate.loc["team_center_x_10s", "cross_map_comparable"])
    assert candidate.loc["players_mid_control_0_15", "cross_map_comparison_mode"] == "semantic"
    assert candidate.loc["players_palace_control_0_15", "status"] == "map_specific"


def test_absurd_grouping_generates_coordinate_review() -> None:
    proposal = pd.DataFrame(
        [
            {"raw_place": "A", "normalized_place_id": "a", "proposed_region_id": "group", "coordinate_consistency_status": "stable"},
            {"raw_place": "B", "normalized_place_id": "b", "proposed_region_id": "group", "coordinate_consistency_status": "stable"},
        ]
    )
    coordinates = pd.DataFrame(
        [
            {"raw_place": "A", "normalized_place_id": "a", "x_median": 0.0, "y_median": 0.0, "z_median": 0.0, "z_min": 0.0, "z_max": 1.0},
            {"raw_place": "B", "normalized_place_id": "b", "x_median": 5000.0, "y_median": 0.0, "z_median": 0.0, "z_min": 0.0, "z_max": 1.0},
        ]
    )

    validation = build_coordinate_validation(proposal, coordinates)

    assert validation.loc[0, "status"] == "failed"


def normalize_lookup(lookup: dict[str, tuple[str, str]], value: str) -> str:
    return lookup[value.lower()][0]
