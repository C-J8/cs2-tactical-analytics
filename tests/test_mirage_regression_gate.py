from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.validation.mirage_regression_gate import run_mirage_regression_gate


def _write_fixture(tmp_path: Path) -> Path:
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
    for path in [
        tmp_path / "configs/features/feature_contract.yaml",
        tmp_path / "configs/maps/map_registry.yaml",
        tmp_path / "configs/maps/mirage.yaml",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("version: v1\n", encoding="utf-8")
    _write_all_datasets(tmp_path)
    return config


def _write_all_datasets(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write(data / "silver/parsed_demos", "feature_eligible_demos", [{"parse_id": "p1", "feature_eligible": True, "target_team": "Vitality", "inferred_map_name": "Mirage"}])
    _write(data / "bronze/parse_quality", "parse_quality", [{"parse_id": "p1", "quality_status": "valid_full_map", "feature_eligible": True}])
    round_features = [
        {"round_feature_id": "r1", "round_id": "round1", "target_team": "Vitality", "map_name": "Mirage", "target_site_model_label": "A", "players_mid_control_0_15": 2, "float_feature": 1.0, "string_feature": "x", "bool_feature": True},
        {"round_feature_id": "r2", "round_id": "round2", "target_team": "Vitality", "map_name": "Mirage", "target_site_model_label": "B", "players_mid_control_0_15": 3, "float_feature": 2.0, "string_feature": "y", "bool_feature": False},
    ]
    _write(data / "gold/round_features", "round_features_mvp", round_features)
    _write(data / "gold/region_presence", "region_presence_by_round", [_region_row("r1", "round1", "Mid", "MID_CONTROL"), _region_row("r2", "round2", "A Ramp", "A_PRESSURE")])
    _write(data / "gold/utility_events", "utility_events", [{"utility_event_id": "u1", "round_feature_id": "r1", "utility_type": "smoke"}])
    _write(data / "gold/round_progression", "round_region_timeline", [_region_row("r1", "round1", "Mid", "MID_CONTROL"), _region_row("r2", "round2", "A Ramp", "A_PRESSURE")])
    _write(
        data / "gold/round_state",
        "round_state_resolved",
        [
            {"round_id": "round1", "target_team_side": "T", "target_site_model_label": "A", "bombsite": "A", "label_confidence": "high", "bomb_planted": True},
            {"round_id": "round2", "target_team_side": "T", "target_site_model_label": "B", "bombsite": "B", "label_confidence": "high", "bomb_planted": True},
        ],
    )
    _write(data / "gold/round_features", "round_features_t_side_all", round_features)
    _write(data / "gold/round_features", "round_features_t_side_planted", round_features)
    _write(data / "gold/round_features", "round_features_ct_side", [{"round_feature_id": "r3", "round_id": "round3", "target_site_model_label": None}])
    _write(
        data / "gold/features/feature_contract",
        "feature_contract",
        [
            {"feature_contract_version": "v1", "feature_name": "players_mid_control_0_15", "map_scope": "map_abstract", "region_dependency": True},
            {"feature_contract_version": "v1", "feature_name": "float_feature", "map_scope": "global", "region_dependency": False},
        ],
    )
    _write(data / "gold/maps/map_registry", "map_registry", [{"map_id": "mirage", "registry_version": "v1", "region_schema_version": "v1"}])
    _write(data / "gold/maps/map_registry", "map_feature_semantic_coverage", [{"feature_name": "players_mid_control_0_15", "map_ready": True}])
    candidate_id = "vitality_mirage_t_ab_35s_stable_only_logistic_v1"
    _write(data / "gold/modeling/t_side_ab_candidate", "candidate_model_selection", [{"candidate_id": candidate_id, "candidate_horizon_seconds": 35, "candidate_feature_set": "stable_only", "candidate_model_name": "logistic_regression"}])
    _write(data / "gold/modeling/t_side_ab_candidate", "candidate_model_feature_set", [{"candidate_id": candidate_id, "feature_name": "players_mid_control_0_15"}])
    _write(data / "gold/modeling/t_side_ab_candidate", "candidate_model_metrics", [{"candidate_id": candidate_id, "macro_f1": 0.5}])
    _write(data / "gold/feature_audit", "map_feature_refactor_audit", [{"status": "ok", "map_feature_engine_ready": True}])


def _region_row(round_feature_id: str, round_id: str, region_name: str, region_group: str) -> dict[str, object]:
    return {
        "round_feature_id": round_feature_id,
        "round_id": round_id,
        "window_type": "interval",
        "window_start": 0,
        "window_end": 15,
        "region_name": region_name,
        "region_group": region_group,
        "time_spent_total": 5,
    }


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def _create_baseline(config: Path) -> None:
    run_mirage_regression_gate(config, baseline_mode="create", force=True)


def test_cli_dry_run_works_with_existing_baseline(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)

    result = subprocess.run(
        [sys.executable, "-m", "src.validation.mirage_regression_gate", "--config", str(config), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Mirage regression gate summary" in result.stdout


def test_baseline_create_manifest_and_no_automatic_overwrite(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    manifest = tmp_path / "data/gold/validation/mirage_regression_baseline/baseline_manifest.parquet"

    assert manifest.exists()
    assert "round_features_mvp" in set(pd.read_parquet(manifest)["dataset_name"])
    with pytest.raises(FileExistsError):
        run_mirage_regression_gate(config, baseline_mode="create", force=False)


def test_same_dataset_passes_and_ready_true(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    frames, _, summary = run_mirage_regression_gate(config, force=True)

    assert summary["ready_for_new_map_onboarding"] == 1
    assert frames["mirage_regression_summary"].loc[0, "overall_status"] == "passed"
    assert frames["mirage_regression_failures"].empty


def test_extra_inferno_rows_are_ignored_for_mirage_scope(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    feature_path = tmp_path / "data/gold/round_features/round_features_mvp.parquet"
    features = pd.read_parquet(feature_path)
    inferno = features.iloc[[0]].copy()
    inferno["round_feature_id"] = "inferno_r1"
    inferno["round_id"] = "inferno_round1"
    inferno["map_name"] = "de_inferno"
    pd.concat([features, inferno], ignore_index=True).to_parquet(feature_path, index=False)
    eligible_path = tmp_path / "data/silver/parsed_demos/feature_eligible_demos.parquet"
    eligible = pd.read_parquet(eligible_path)
    inferno_eligible = eligible.iloc[[0]].copy()
    inferno_eligible["parse_id"] = "inferno_parse"
    inferno_eligible["inferred_map_name"] = "de_inferno"
    pd.concat([eligible, inferno_eligible], ignore_index=True).to_parquet(eligible_path, index=False)
    registry_path = tmp_path / "data/gold/maps/map_registry/map_registry.parquet"
    registry = pd.read_parquet(registry_path)
    pd.concat([registry, pd.DataFrame([{"map_id": "inferno", "registry_version": "v1", "region_schema_version": "v1"}])], ignore_index=True).to_parquet(registry_path, index=False)

    frames, _, summary = run_mirage_regression_gate(config, force=True)

    assert summary["ready_for_new_map_onboarding"] == 1
    assert frames["mirage_regression_failures"].empty


def test_row_count_difference_generates_failure(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    path = tmp_path / "data/gold/round_features/round_features_mvp.parquet"
    pd.read_parquet(path).head(1).to_parquet(path, index=False)

    frames, _, summary = run_mirage_regression_gate(config, force=True)

    assert summary["ready_for_new_map_onboarding"] == 0
    assert not frames["mirage_regression_failures"].empty


def test_missing_and_extra_columns_fail_in_strict_mode(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    path = tmp_path / "data/gold/round_features/round_features_mvp.parquet"
    df = pd.read_parquet(path).drop(columns=["string_feature"])
    df["extra_feature"] = 1
    df.to_parquet(path, index=False)

    frames, _, _ = run_mirage_regression_gate(config, force=True, strict=True)

    failed_schema = frames["mirage_schema_comparison"][frames["mirage_schema_comparison"]["status"] == "failed"]
    assert {"string_feature", "extra_feature"} <= set(failed_schema["column_name"])


def test_integer_string_and_candidate_value_differences_fail(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    path = tmp_path / "data/gold/round_features/round_features_mvp.parquet"
    df = pd.read_parquet(path)
    df.loc[0, "players_mid_control_0_15"] = 9
    df.loc[1, "string_feature"] = "changed"
    df.to_parquet(path, index=False)
    planted = tmp_path / "data/gold/round_features/round_features_t_side_planted.parquet"
    planted_df = pd.read_parquet(planted)
    planted_df.loc[0, "players_mid_control_0_15"] = 9
    planted_df.to_parquet(planted, index=False)

    frames, _, _ = run_mirage_regression_gate(config, force=True)

    values = frames["mirage_feature_value_comparison"].set_index("feature_name")
    assert values.loc["players_mid_control_0_15", "status"] == "failed"
    assert frames["mirage_candidate_input_compatibility"].loc[0, "status"] == "failed"


def test_float_tolerance_policy(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    path = tmp_path / "data/gold/round_features/round_features_mvp.parquet"
    df = pd.read_parquet(path)
    df.loc[0, "float_feature"] = 1.0 + 1e-10
    df.to_parquet(path, index=False)

    frames, _, _ = run_mirage_regression_gate(config, force=True, float_atol=1e-9, float_rtol=1e-9)
    assert frames["mirage_feature_value_comparison"].set_index("feature_name").loc["float_feature", "status"] == "ok"

    df.loc[0, "float_feature"] = 1.1
    df.to_parquet(path, index=False)
    frames, _, _ = run_mirage_regression_gate(config, force=True, float_atol=1e-9, float_rtol=1e-9)
    assert frames["mirage_feature_value_comparison"].set_index("feature_name").loc["float_feature", "status"] == "failed"


def test_region_label_side_and_stage_8_2_failures_block_readiness(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    region_path = tmp_path / "data/gold/round_progression/round_region_timeline.parquet"
    region = pd.read_parquet(region_path)
    region.loc[0, "region_group"] = "B_PRESSURE"
    region.to_parquet(region_path, index=False)
    state_path = tmp_path / "data/gold/round_state/round_state_resolved.parquet"
    state = pd.read_parquet(state_path)
    state.loc[0, "target_team_side"] = "CT"
    state.loc[0, "target_site_model_label"] = "B"
    state.to_parquet(state_path, index=False)
    audit_path = tmp_path / "data/gold/feature_audit/map_feature_refactor_audit.parquet"
    pd.DataFrame([{"status": "failed", "map_feature_engine_ready": False}]).to_parquet(audit_path, index=False)

    frames, _, summary = run_mirage_regression_gate(config, force=True)

    assert summary["ready_for_new_map_onboarding"] == 0
    assert frames["mirage_region_timeline_comparison"].loc[1, "status"] == "failed"
    assert frames["mirage_round_state_comparison"].loc[0, "status"] == "failed"
    assert not bool(frames["mirage_regression_audit"].loc[0, "stage_8_2_ready"])


def test_report_notebook_and_upstream_model_outputs_are_not_modified(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _create_baseline(config)
    model_path = tmp_path / "data/gold/modeling/t_side_ab_candidate/candidate_model_metrics.parquet"
    before = model_path.read_bytes()

    _, outputs, _ = run_mirage_regression_gate(config, force=True)

    assert outputs["report"].exists()
    assert outputs["notebook"].exists()
    assert model_path.read_bytes() == before
