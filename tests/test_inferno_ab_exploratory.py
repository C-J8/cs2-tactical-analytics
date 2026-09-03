from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.modeling.build_map_ab_dataset import (
    build_experiment_fingerprint,
    leakage_flags,
    run_build_map_ab_dataset,
)
from src.modeling.inferno_ab_exploratory_baseline import (
    build_error_analysis,
    build_error_summary,
    bootstrap_metric_uncertainty,
    evaluate_dummy_baselines,
    evaluate_feature_set,
    metric_values,
    run_null_permutation,
    validate_logo_feasibility,
)


def test_build_map_ab_dataset_filters_scope_and_uses_series_groups(tmp_path: Path) -> None:
    config, model_config = write_stage_811_fixture(tmp_path)

    frames, _, summary = run_build_map_ab_dataset(
        config_path=config,
        model_config_path=model_config,
        target_map="Inferno",
        target_team="Vitality",
        dry_run=True,
    )
    dataset = frames["inferno_ab_model_dataset"]

    assert summary["rows"] == 6
    assert set(dataset["map_name"]) == {"Inferno"}
    assert set(dataset["target_team"]) == {"Vitality"}
    assert set(dataset["target_team_side"]) == {"T"}
    assert set(dataset["label"]) == {"A", "B"}
    assert set(dataset["model_group_id"]) == {"series_1", "series_2", "series_3"}
    assert frames["inferno_ab_label_audit"].iloc[0]["low_confidence_excluded"] == 1
    assert "inferno_ab_feature_evidence_audit" in frames
    assert "inferno_ab_modeling_preconditions" in frames
    assert not frames["inferno_ab_feature_set_audit"]["exclusion_reason"].astype(str).str.contains("unknown_not_approved").any()


def test_missing_mandatory_quality_artifact_blocks_experiment(tmp_path: Path) -> None:
    config, model_config = write_stage_811_fixture(tmp_path)
    (tmp_path / "data/gold/validation/map_feature_quality/map_feature_quality_profile.parquet").unlink()

    with pytest.raises(FileNotFoundError, match="Mandatory modeling evidence artifact"):
        run_build_map_ab_dataset(config_path=config, model_config_path=model_config, dry_run=True)


def test_feature_missing_from_evidence_is_unknown_not_approved(tmp_path: Path) -> None:
    config, model_config = write_stage_811_fixture(tmp_path, include_smoke_evidence=False)

    frames, _, _ = run_build_map_ab_dataset(config_path=config, model_config_path=model_config, dry_run=True)
    evidence = frames["inferno_ab_feature_evidence_audit"].set_index("feature_name")

    assert evidence.loc["smokes_used_0_35", "quality_status"] == "unknown_not_approved"
    assert bool(evidence.loc["smokes_used_0_35", "approved_for_modeling"]) is False


def test_feature_leakage_rules_block_absolute_exclusions() -> None:
    safe = leakage_flags("smokes_used_0_35", {}, window_end=35, horizon=35)
    future = leakage_flags("smokes_used_35_45", {}, window_end=45, horizon=35)
    label = leakage_flags("target_site_model_label", {}, window_end=None, horizon=35)
    plant = leakage_flags("target_team_planted", {}, window_end=None, horizon=35)
    first_event = leakage_flags("first_smoke_time", {}, window_end=None, horizon=35)
    endpoint = leakage_flags("smokes_to_a_pressure_0_35", {}, window_end=35, horizon=35)
    raw_coord = leakage_flags("team_center_x_15s", {"coordinate_dependency": "raw_coordinate"}, window_end=15, horizon=35)

    assert safe["blocked"] is False
    assert future["reason"] == "after_horizon"
    assert label["reason"] == "label_dependency"
    assert plant["reason"] == "plant_dependency"
    assert first_event["reason"] == "full_round_dependency"
    assert endpoint["reason"] == "unresolved_endpoint"
    assert raw_coord["reason"] == "raw_coordinate_requires_normalization"


def test_leave_one_group_out_predictions_cover_each_row_once(tmp_path: Path) -> None:
    config, model_config = write_stage_811_fixture(tmp_path)
    frames, _, _ = run_build_map_ab_dataset(config_path=config, model_config_path=model_config, dry_run=True)
    dataset = frames["inferno_ab_model_dataset"]
    features = frames["inferno_ab_feature_set_audit"].loc[frames["inferno_ab_feature_set_audit"]["included"], "feature_name"].tolist()
    model_cfg = small_model_config()

    validation = validate_logo_feasibility(dataset)
    result = evaluate_feature_set(dataset, features, model_cfg, "compact_tactical_35s")

    assert validation["training_has_both_classes"].all()
    assert len(result["oof_predictions"]) == len(dataset)
    assert result["oof_predictions"]["round_feature_id"].is_unique
    assert set(result["oof_predictions"]["predicted_label"]) <= {"A", "B"}


def test_dummy_null_bootstrap_and_metrics_are_deterministic(tmp_path: Path) -> None:
    config, model_config = write_stage_811_fixture(tmp_path)
    frames, _, _ = run_build_map_ab_dataset(config_path=config, model_config_path=model_config, dry_run=True)
    dataset = frames["inferno_ab_model_dataset"]
    features = frames["inferno_ab_feature_set_audit"].loc[frames["inferno_ab_feature_set_audit"]["included"], "feature_name"].tolist()
    model_cfg = small_model_config(permutations=5, resamples=10)

    dummies_a = evaluate_dummy_baselines(dataset, features, model_cfg)
    dummies_b = evaluate_dummy_baselines(dataset, features, model_cfg)
    null_a = run_null_permutation(dataset, features, model_cfg)
    null_b = run_null_permutation(dataset, features, model_cfg)
    oof = evaluate_feature_set(dataset, features, model_cfg, "compact_tactical_35s")["oof_predictions"]
    uncertainty = bootstrap_metric_uncertainty(oof, model_cfg)

    assert dummies_a.equals(dummies_b)
    assert null_a.equals(null_b)
    assert len(null_a) == 5
    assert set(uncertainty["metric"]) == {"macro_f1", "balanced_accuracy", "recall_A", "recall_B"}
    assert metric_values(pd.Series(["A", "B"]), pd.Series(["A", "A"]))["recall_B"] == 0.0
    metrics = metric_values(pd.Series(["A", "A", "B", "B"]), pd.Series(["A", "B", "B", "A"]), y_proba_b=pd.Series([0.1, 0.8, 0.7, 0.4]))
    assert {"f1_A", "f1_B", "MCC", "ROC_AUC", "Brier_score", "log_loss", "true_A_pred_A", "true_A_pred_B", "true_B_pred_A", "true_B_pred_B"} <= set(metrics)
    fold_metrics = metric_values(pd.Series(["A", "A"]), pd.Series(["A", "B"]), y_proba_b=pd.Series([0.1, 0.8]))
    assert fold_metrics["ROC_AUC"] is None
    assert fold_metrics["metric_availability_notes"] == "undefined_single_class_fold"


def test_error_analysis_is_round_level_and_summary_matches() -> None:
    oof = pd.DataFrame(
        [
            {
                "round_feature_id": "rf_1",
                "round_id": "r1",
                "parse_id": "p1",
                "series_id": "s1",
                "model_group_id": "s1",
                "fold_id": 1,
                "held_out_group": "s1",
                "true_label": "A",
                "predicted_label": "B",
                "predicted_proba_A": 0.25,
                "predicted_proba_B": 0.75,
                "prediction_confidence": 0.75,
                "is_correct": False,
            },
            {
                "round_feature_id": "rf_2",
                "round_id": "r2",
                "parse_id": "p2",
                "series_id": "s2",
                "model_group_id": "s2",
                "fold_id": 2,
                "held_out_group": "s2",
                "true_label": "B",
                "predicted_label": "B",
                "predicted_proba_A": 0.2,
                "predicted_proba_B": 0.8,
                "prediction_confidence": 0.8,
                "is_correct": True,
            },
        ]
    )
    dataset = pd.DataFrame(
        [
            {"round_feature_id": "rf_1", "round_id": "r1", "parse_id": "p1", "series_id": "s1", "model_group_id": "s1", "score_diff_before_round": -1, "smokes_used_0_35": 2},
            {"round_feature_id": "rf_2", "round_id": "r2", "parse_id": "p2", "series_id": "s2", "model_group_id": "s2", "score_diff_before_round": 1, "smokes_used_0_35": 1},
        ]
    )

    errors = build_error_analysis(oof, dataset, ["score_diff_before_round", "smokes_used_0_35"])
    summary = build_error_summary(errors)

    assert len(errors) == 1
    assert errors.iloc[0]["round_feature_id"] == "rf_1"
    assert errors.iloc[0]["probability_true_class"] == 0.25
    assert errors.iloc[0]["feature__smokes_used_0_35"] == 2
    assert summary.iloc[0]["rows"] == 1


def test_experiment_fingerprint_is_stable(tmp_path: Path) -> None:
    config, model_config = write_stage_811_fixture(tmp_path)
    frames_a, _, _ = run_build_map_ab_dataset(config_path=config, model_config_path=model_config, dry_run=True)
    frames_b, _, _ = run_build_map_ab_dataset(config_path=config, model_config_path=model_config, dry_run=True)
    cfg = small_model_config()
    contract = {
        "score_diff_before_round": {"feature_name": "score_diff_before_round"},
        "smokes_used_0_35": {"feature_name": "smokes_used_0_35"},
    }

    assert build_experiment_fingerprint(frames_a["inferno_ab_model_dataset"], cfg, contract) == build_experiment_fingerprint(
        frames_b["inferno_ab_model_dataset"], cfg, contract
    )


def write_stage_811_fixture(tmp_path: Path, *, include_smoke_evidence: bool = True) -> tuple[Path, Path]:
    config = tmp_path / "configs" / "project.yaml"
    model_config = tmp_path / "configs" / "modeling" / "inferno_ab_exploratory.yaml"
    feature_contract = tmp_path / "configs" / "features" / "feature_contract.yaml"
    config.parent.mkdir(parents=True)
    model_config.parent.mkdir(parents=True)
    feature_contract.parent.mkdir(parents=True)
    config.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-07-07"
target_maps: [Inferno]
target_teams: [Vitality]
output_formats: [csv, parquet]
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
""".strip(),
        encoding="utf-8",
    )
    model_config.write_text(
        """
experiment:
  experiment_id: vitality_inferno_t_ab_exploratory_v1
  model_id: vitality_inferno_t_ab_35s_exploratory_logistic_v1
  target_map: Inferno
  target_team: Vitality
  target_side: T
  label_column: target_site_model_label
  output_subdir: inferno_ab_exploratory
prediction:
  primary_horizon_seconds: 35
validation:
  strategy: leave_one_group_out
  preferred_group_column: series_id
  fallback_group_column: parse_id
  minimum_valid_groups: 3
model:
  type: logistic_regression
  penalty: l2
  C: 0.1
  solver: liblinear
  max_iter: 5000
  threshold: 0.5
  class_weight:
  random_state: 811
null_test:
  permutations: 5
  preserve_group_class_balance: true
  random_state: 811
bootstrap:
  enabled: true
  cluster_by_model_group: true
  resamples: 10
  confidence_level: 0.95
  random_state: 811
feature_sets:
  primary: compact_tactical_35s
  compact_tactical_35s:
    min_features: 2
    max_features: 4
    features:
      - feature_name: score_diff_before_round
        family: pre_round_context
      - feature_name: smokes_used_0_35
        family: early_utility_usage
      - feature_name: target_site_model_label
        family: label
  ablations: {}
""".strip(),
        encoding="utf-8",
    )
    feature_contract.write_text(
        """
feature_contract_version: test
features:
  - feature_name: score_diff_before_round
    feature_family: context
    window_type: static
    modeling_allowed: true
    coordinate_dependency: none
  - feature_name: smokes_used_0_35
    feature_family: utility
    window_start: 0
    window_end: 35
    window_type: cumulative
    modeling_allowed: true
    coordinate_dependency: none
  - feature_name: target_site_model_label
    feature_family: label
    window_type: static
    modeling_allowed: false
    coordinate_dependency: none
""".strip(),
        encoding="utf-8",
    )
    rows = [
        model_row(0, "A", "series_1"),
        model_row(1, "B", "series_1"),
        model_row(2, "A", "series_2"),
        model_row(3, "B", "series_2"),
        model_row(4, "A", "series_3"),
        model_row(5, "B", "series_3"),
        {**model_row(6, "A", "series_4"), "map_name": "Mirage"},
        {**model_row(7, "A", "series_4"), "target_team": "FURIA"},
        {**model_row(8, "A", "series_4"), "target_team_side": "CT"},
        {**model_row(9, "A", "series_4"), "label_confidence": "low"},
        {**model_row(10, "unknown", "series_4"), "target_site_model_label": "unknown"},
    ]
    output = tmp_path / "data" / "gold" / "round_features"
    output.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(output / "round_features_t_side_planted.parquet", index=False)
    write_modeling_evidence_fixture(tmp_path, include_smoke_evidence=include_smoke_evidence)
    return config, model_config


def write_modeling_evidence_fixture(tmp_path: Path, *, include_smoke_evidence: bool = True) -> None:
    gold = tmp_path / "data" / "gold"
    quality_dir = gold / "validation" / "map_feature_quality"
    repair_dir = gold / "validation" / "feature_materialization_repair"
    multi_map_dir = gold / "validation" / "multi_map_gold"
    hardening_dir = gold / "analysis" / "tactical_finding_hardening"
    for path in [quality_dir, repair_dir, multi_map_dir, hardening_dir]:
        path.mkdir(parents=True, exist_ok=True)
    features = ["score_diff_before_round"]
    if include_smoke_evidence:
        features.append("smokes_used_0_35")
    profile_rows = [
        {
            "map_id": "inferno",
            "target_team": "Vitality",
            "feature_name": feature,
            "missing_share": 0.0,
            "quality_status": "ok",
            "constant": False,
            "near_constant": False,
            "all_null": False,
            "all_zero": False,
        }
        for feature in features
    ]
    missingness_rows = [
        {"map_id": "inferno", "target_team": "Vitality", "feature_name": feature, "missing_share": 0.0, "blocking": False, "status": "ok"}
        for feature in features
    ]
    degeneracy_rows = [
        {
            "map_id": "inferno",
            "target_team": "Vitality",
            "feature_name": feature,
            "unique_values": 3,
            "constant": False,
            "near_constant": False,
            "all_null": False,
            "all_zero": False,
            "blocking": False,
            "status": "ok",
        }
        for feature in features
    ]
    audit = pd.DataFrame(
        [
            {
                "map_id": "inferno",
                "target_team": "Vitality",
                "ready_for_inferno_modeling_experiment": True,
                "status": "passed",
            }
        ]
    )
    materialization = pd.DataFrame(
        [
            {"map_id": "inferno", "feature_name": feature, "materialized": True, "status": "ok"}
            for feature in features
        ]
    )
    capabilities = pd.DataFrame(
        [
            {
                "map_id": "inferno",
                "target_team": "Vitality",
                "capability_id": "smoke_usage",
                "capability_status": "supported_materialized",
                "status": "ok",
            },
            {
                "map_id": "inferno",
                "target_team": "Vitality",
                "capability_id": "score_diff_before_round",
                "capability_status": "supported_materialized",
                "status": "ok",
            },
        ]
    )
    final_audit = pd.DataFrame([{"map_id": "inferno", "target_team": "Vitality", "ready_for_stage_8_10": True, "status": "passed"}])
    pd.DataFrame(profile_rows).to_parquet(quality_dir / "map_feature_quality_profile.parquet", index=False)
    pd.DataFrame(missingness_rows).to_parquet(quality_dir / "map_feature_missingness.parquet", index=False)
    pd.DataFrame(degeneracy_rows).to_parquet(quality_dir / "map_feature_degeneracy.parquet", index=False)
    audit.to_parquet(quality_dir / "map_feature_quality_audit.parquet", index=False)
    capabilities.to_parquet(repair_dir / "feature_materialization_capabilities.parquet", index=False)
    final_audit.to_parquet(repair_dir / "feature_materialization_repair_final_audit.parquet", index=False)
    materialization.to_parquet(multi_map_dir / "inferno_feature_materialization.parquet", index=False)
    pd.DataFrame([{"representative_feature": "smokes_used_0_35"}]).to_parquet(hardening_dir / "modeling_context_findings.parquet", index=False)


def model_row(index: int, label: str, series: str) -> dict[str, object]:
    return {
        "round_feature_id": f"rf_{index}",
        "round_id": f"round_{index}",
        "parse_id": f"parse_{series}",
        "series_id": series,
        "dem_file_id": f"demo_{series}",
        "target_team": "Vitality",
        "map_name": "Inferno",
        "target_team_side": "T",
        "label_confidence": "high",
        "target_site_model_label": label,
        "target_team_planted": True,
        "score_diff_before_round": index,
        "smokes_used_0_35": index % 3,
    }


def small_model_config(permutations: int = 5, resamples: int = 10) -> dict[str, object]:
    return {
        "experiment": {"experiment_id": "test", "model_id": "test_model", "target_map": "Inferno", "target_team": "Vitality", "target_side": "T"},
        "prediction": {"primary_horizon_seconds": 35},
        "validation": {"strategy": "leave_one_group_out", "preferred_group_column": "series_id", "fallback_group_column": "parse_id", "minimum_valid_groups": 3},
        "model": {"penalty": "l2", "C": 0.1, "solver": "liblinear", "max_iter": 5000, "threshold": 0.5, "class_weight": None, "random_state": 811},
        "null_test": {"permutations": permutations, "preserve_group_class_balance": True, "random_state": 811},
        "bootstrap": {"resamples": resamples, "confidence_level": 0.95, "random_state": 811},
        "feature_sets": {"primary": "compact_tactical_35s"},
    }
