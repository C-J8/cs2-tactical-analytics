from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.modeling.build_map_ab_dataset import (
    build_experiment_fingerprint,
    leakage_flags,
    run_build_map_ab_dataset,
)
from src.modeling.inferno_ab_exploratory_baseline import (
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


def write_stage_811_fixture(tmp_path: Path) -> tuple[Path, Path]:
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
    return config, model_config


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
