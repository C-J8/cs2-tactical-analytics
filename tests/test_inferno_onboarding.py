from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.maps.onboard_map import build_feature_quality, run_onboarding
from src.maps.registry import load_map_registry


def _write_fixture(tmp_path: Path, *, gate_passed: bool = True, include_demos: bool = True, feature_eligible: bool = False) -> Path:
    config = tmp_path / "configs" / "project.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
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
    _write_gate(tmp_path, gate_passed=gate_passed)
    _write_feature_contract(tmp_path)
    _write_candidate(tmp_path)
    _write_mirage_outputs(tmp_path)
    if include_demos:
        _write_inferno_manifests(tmp_path, feature_eligible=feature_eligible)
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
    (maps_dir / "mirage.yaml").write_text(_map_config("mirage", "Mirage", "de_mirage", active=True), encoding="utf-8")
    (maps_dir / "inferno.yaml").write_text(_map_config("inferno", "Inferno", "de_inferno", active=False), encoding="utf-8")


def _map_config(map_id: str, display_name: str, game_map_name: str, *, active: bool) -> str:
    status = "active" if active else "unresolved"
    return f"""
map_id: {map_id}
display_name: {display_name}
game_map_name: {game_map_name}
region_schema_version: v1
coordinate_system:
  source: test
physical_regions:
- region_id: {map_id}_mid
  display_name: {display_name} Mid
  geometry: {{type: named_area, source: test, area_names: []}}
  semantic_tags: [mid_control]
  site_affinity: []
  region_scope: map_specific
  priority: 10
  boundary_policy: existing_behavior
  aliases: []
  status: {status}
- region_id: {map_id}_a
  display_name: {display_name} A
  geometry: {{type: named_area, source: test, area_names: []}}
  semantic_tags: [a_pressure, site_a]
  site_affinity: [A]
  region_scope: map_specific
  priority: 9
  boundary_policy: existing_behavior
  aliases: []
  status: {status}
- region_id: {map_id}_b
  display_name: {display_name} B
  geometry: {{type: named_area, source: test, area_names: []}}
  semantic_tags: [b_pressure, site_b]
  site_affinity: [B]
  region_scope: map_specific
  priority: 8
  boundary_policy: existing_behavior
  aliases: []
  status: {status}
- region_id: {map_id}_ct
  display_name: {display_name} CT
  geometry: {{type: named_area, source: test, area_names: []}}
  semantic_tags: [ct_space]
  site_affinity: []
  region_scope: map_specific
  priority: 7
  boundary_policy: existing_behavior
  aliases: []
  status: {status}
semantic_groups:
  mid_control:
    description: mid
    member_regions: [{map_id}_mid]
    status: {status}
  a_pressure:
    description: a pressure
    member_regions: [{map_id}_a]
    status: {status}
  b_pressure:
    description: b pressure
    member_regions: [{map_id}_b]
    status: {status}
  ct_space:
    description: ct
    member_regions: [{map_id}_ct]
    status: {status}
  site_a:
    description: site a
    member_regions: [{map_id}_a]
    status: {status}
  site_b:
    description: site b
    member_regions: [{map_id}_b]
    status: {status}
aliases:
  {map_id}_mid: []
  {map_id}_a: []
  {map_id}_b: []
  {map_id}_ct: []
bombsites:
  A:
    region_ids: [{map_id}_a]
  B:
    region_ids: [{map_id}_b]
""".strip()


def _write_gate(tmp_path: Path, *, gate_passed: bool) -> None:
    _write(tmp_path / "data/gold/validation/mirage_regression_gate", "mirage_regression_audit", [{"ready_for_new_map_onboarding": gate_passed}])


def _write_feature_contract(tmp_path: Path) -> None:
    rows = [
        _feature("team_smokes_start", "global", False, None),
        _feature("players_mid_control_0_15", "map_abstract", True, "mid_control"),
        _feature("players_a_pressure_0_15", "map_abstract", True, "a_pressure"),
        _feature("players_b_pressure_0_15", "map_abstract", True, "b_pressure"),
        _feature("players_ct_space_0_15", "map_abstract", True, "ct_space"),
        _feature("players_palace_0_15", "map_specific", True, "mirage_palace"),
    ]
    _write(tmp_path / "data/gold/features/feature_contract", "feature_contract", rows)


def _feature(name: str, map_scope: str, region_dependency: bool, semantic: str | None) -> dict[str, object]:
    return {
        "feature_contract_version": "v1",
        "feature_name": name,
        "feature_family": "region_position" if region_dependency else "utility",
        "semantic_role": "spatial_control" if region_dependency else "utility_usage",
        "feature_status": "frozen",
        "map_scope": map_scope,
        "region_dependency": region_dependency,
        "region_semantic": semantic,
        "modeling_allowed": True,
        "dashboard_allowed": True,
    }


def _write_candidate(tmp_path: Path) -> None:
    _write(
        tmp_path / "data/gold/modeling/t_side_ab_candidate",
        "candidate_model_feature_set",
        [
            {"candidate_id": "vitality_mirage_candidate", "feature_name": "team_smokes_start"},
            {"candidate_id": "vitality_mirage_candidate", "feature_name": "players_mid_control_0_15"},
            {"candidate_id": "vitality_mirage_candidate", "feature_name": "players_palace_0_15"},
        ],
    )


def _write_mirage_outputs(tmp_path: Path) -> None:
    _write(tmp_path / "data/gold/round_features", "round_features_t_side_all", [{"round_feature_id": "mirage_r1", "target_team": "Vitality", "map_name": "Mirage"}])


def _write_inferno_manifests(tmp_path: Path, *, feature_eligible: bool) -> None:
    dem_row = {
        "dem_file_id": "d1",
        "local_archive_id": "a1",
        "archive_path": "archive.rar",
        "dem_path": "inferno.dem",
        "target_team": "Vitality",
        "inferred_map_name": "de_inferno",
    }
    quality_row = {
        "parse_id": "p1",
        "dem_file_id": "d1",
        "target_team": "Vitality",
        "inferred_map_name": "de_inferno",
        "parse_status": "map_not_target" if not feature_eligible else "parsed",
        "parse_eligible": True,
        "feature_eligible": feature_eligible,
    }
    _write(tmp_path / "data/bronze/dem_files_manifest", "dem_files_manifest", [dem_row])
    _write(tmp_path / "data/bronze/parse_quality", "parse_quality", [quality_row])
    _write(tmp_path / "data/bronze/parse_manifest", "parse_manifest", [{**quality_row, "map_name": "de_inferno"}])
    _write(tmp_path / "data/silver/parsed_demos", "feature_eligible_demos", [quality_row] if feature_eligible else [])


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def test_gate_false_blocks_onboarding(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path, gate_passed=False)

    with pytest.raises(ValueError, match="Mirage regression gate has not passed"):
        run_onboarding(config)


def test_inferno_registered_and_normalized(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    registry_path = config.parent / "maps" / "map_registry.yaml"

    assert load_map_registry("Inferno", registry_path=registry_path).map_id == "inferno"
    assert load_map_registry("inferno", registry_path=registry_path).map_id == "inferno"
    assert load_map_registry("de_inferno", registry_path=registry_path).map_id == "inferno"
    assert load_map_registry("Mirage", registry_path=registry_path).map_id == "mirage"


def test_absence_of_demos_does_not_create_fake_data(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path, include_demos=False)

    frames, _, summary = run_onboarding(config, dry_run=True)

    assert summary["data_status"] == "missing_demos"
    assert frames["inferno_data_availability"].loc[0, "dem_files"] == 0
    assert frames["inferno_dataset_snapshot"].loc[0, "total_rounds"] is None


def test_local_demos_not_feature_eligible_are_blocked_by_data(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)

    frames, _, summary = run_onboarding(config, dry_run=True)

    assert summary["data_status"] == "local_demos_not_feature_eligible"
    assert frames["inferno_data_availability"].loc[0, "dem_files"] == 1
    assert frames["inferno_data_availability"].loc[0, "feature_eligible_demos"] == 0
    assert frames["inferno_onboarding_audit"].loc[0, "demos_available"]


def test_global_map_abstract_and_map_specific_coverage(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)

    frames, _, _ = run_onboarding(config, dry_run=True)
    coverage = frames["inferno_feature_coverage"].set_index("feature_name")

    assert bool(coverage.loc["team_smokes_start", "inferno_supported"])
    assert coverage.loc["team_smokes_start", "support_type"] == "global"
    assert not bool(coverage.loc["players_mid_control_0_15", "inferno_supported"])
    assert coverage.loc["players_mid_control_0_15", "support_type"] == "unresolved"
    assert coverage.loc["players_palace_0_15", "support_type"] == "not_applicable"


def test_unresolved_semantic_generates_unknown_and_blocks_registry_ready(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)

    frames, _, summary = run_onboarding(config, dry_run=True)

    assert summary["registry_status"] == "blocked"
    assert "missing_semantic" in set(frames["inferno_unknowns"]["category"])
    assert not bool(frames["inferno_onboarding_audit"].loc[0, "ready_for_inferno_feature_run"])


def test_pipeline_does_not_run_without_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _write_fixture(tmp_path, feature_eligible=True)
    called = False

    def fake_run_feature_pipeline(*args: object, **kwargs: object) -> tuple[pd.DataFrame, dict[str, Path], dict[str, int]]:
        nonlocal called
        called = True
        return pd.DataFrame(), {}, {}

    monkeypatch.setattr("src.maps.onboard_map.run_feature_pipeline", fake_run_feature_pipeline)
    frames, _, summary = run_onboarding(config, dry_run=True)

    assert not called
    assert summary["pipeline_execution_status"] == "not_requested"
    assert not bool(frames["inferno_onboarding_audit"].loc[0, "pipeline_run_requested"])


def test_pipeline_run_uses_inferno_registry_without_writing_main_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _write_fixture(tmp_path, feature_eligible=True)
    before = (tmp_path / "data/gold/round_features/round_features_t_side_all.parquet").read_bytes()
    calls: list[dict[str, object]] = []

    def fake_run_feature_pipeline(*args: object, **kwargs: object) -> tuple[pd.DataFrame, dict[str, Path], dict[str, int]]:
        calls.append(kwargs)
        return pd.DataFrame([{"round_feature_id": "inferno_r1", "target_team": "Vitality", "map_name": "Inferno", "constant_feature": 1}]), {}, {}

    monkeypatch.setattr("src.maps.onboard_map.run_feature_pipeline", fake_run_feature_pipeline)
    frames, _, summary = run_onboarding(config, dry_run=True, run_pipeline=True)

    assert calls
    assert calls[0]["target_map"] == "Inferno"
    assert calls[0]["dry_run"] is True
    assert (tmp_path / "data/gold/round_features/round_features_t_side_all.parquet").read_bytes() == before
    assert summary["pipeline_execution_status"] == "dry_run_completed"
    assert frames["inferno_dataset_snapshot"].loc[0, "total_rounds"] == 1


def test_feature_quality_detects_all_null_and_constant_features() -> None:
    quality = build_feature_quality(pd.DataFrame({"all_null": [None, None], "constant": [1, 1], "variable": [1, 2]})).set_index("feature_name")

    assert bool(quality.loc["all_null", "all_null_feature"])
    assert bool(quality.loc["constant", "constant_feature"])
    assert not bool(quality.loc["variable", "suspicious_feature"])


def test_outputs_report_and_notebook_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)

    _, outputs, _ = run_onboarding(config, force=True)

    assert outputs["report"].exists()
    assert outputs["notebook"].exists()
    json.loads(outputs["notebook"].read_text(encoding="utf-8"))
    assert (tmp_path / "data/gold/maps/inferno/onboarding/inferno_onboarding_audit.parquet").exists()
