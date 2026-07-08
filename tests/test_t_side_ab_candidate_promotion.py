from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

from src.modeling.t_side_ab_candidate_promotion import (
    OUTPUT_NAMES,
    run_t_side_ab_candidate_promotion,
)


def _write_fixture(tmp_path: Path) -> Path:
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
    gold = tmp_path / "data" / "gold"
    refined = gold / "modeling" / "t_side_ab_refined_experiment"
    _write(refined, "ab_refined_dataset_audit", [_dataset_audit()])
    _write(refined, "ab_refined_feature_sets", _feature_sets())
    _write(refined, "ab_refined_metrics", _metrics())
    _write(refined, "ab_refined_confusion_matrices", _confusion())
    _write(refined, "ab_refined_predictions", _predictions())
    _write(refined, "ab_refined_feature_importance", _importance())
    _write(refined, "ab_refined_error_summary", _error_summary())
    _write(refined, "ab_refined_comparison_vs_baseline", _comparison())
    _write(refined, "ab_refined_recommendation", _recommendation())
    _write(refined, "ab_refined_audit", [_refined_audit()])
    _write(gold / "modeling" / "t_side_ab_baseline", "ab_model_metrics", [{"horizon_seconds": 35}])
    _write(
        gold / "modeling" / "t_side_ab_baseline",
        "ab_model_predictions",
        [{"horizon_seconds": 35, "round_feature_id": "rf_1"}],
    )
    _write(
        gold / "modeling" / "t_side_ab_baseline",
        "ab_model_feature_importance",
        [{"horizon": 35, "feature_name": "players_mid_control_0_35"}],
    )
    _write(
        gold / "modeling" / "t_side_ab_error_analysis",
        "ab_error_manual_review_queue",
        [{"round_feature_id": "rf_2"}],
    )
    _write(
        gold / "analysis" / "t_side_manual_review",
        "manual_review_decision_template",
        [{"round_feature_id": f"rf_{index}", "review_decision": "pending"} for index in range(1, 7)],
    )
    _write(gold / "analysis" / "t_side_tactical_eda", "t_side_feature_catalog", _feature_catalog())
    _write(gold / "round_features", "round_features_t_side_planted", [{"round_feature_id": "rf_1"}])
    return config


def _dataset_audit() -> dict[str, object]:
    return {
        "total_rows_input": 6,
        "final_model_rows": 6,
        "class_A": 3,
        "class_B": 3,
        "manual_review_status": "manual_review_pending; refined experiment remains preliminary",
        "status": "ok",
    }


def _metrics() -> list[dict[str, object]]:
    return [
        {
            "horizon_seconds": 35,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "accuracy": 0.8333,
            "balanced_accuracy": 0.8333,
            "macro_f1": 0.8123,
            "f1_A": 0.80,
            "f1_B": 0.8246,
            "precision_A": 0.75,
            "precision_B": 1.0,
            "recall_A": 1.0,
            "recall_B": 0.6667,
            "roc_auc": 0.90,
            "support_A": 3,
            "support_B": 3,
            "n_splits": 3,
            "notes": "fixture metrics",
            "total_errors": 1,
            "A_predicted_as_B": 0,
            "B_predicted_as_A": 1,
            "high_confidence_errors": 1,
            "high_confidence_B_predicted_as_A": 1,
        },
        {
            "horizon_seconds": 45,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "accuracy": 0.50,
            "balanced_accuracy": 0.50,
            "macro_f1": 0.50,
            "f1_A": 0.50,
            "f1_B": 0.50,
            "precision_A": 0.50,
            "precision_B": 0.50,
            "recall_A": 0.50,
            "recall_B": 0.50,
            "roc_auc": 0.50,
            "support_A": 3,
            "support_B": 3,
            "n_splits": 3,
            "notes": "other row",
            "total_errors": 3,
            "A_predicted_as_B": 1,
            "B_predicted_as_A": 2,
            "high_confidence_errors": 0,
            "high_confidence_B_predicted_as_A": 0,
        },
    ]


def _confusion() -> list[dict[str, object]]:
    rows = []
    counts = {("A", "A"): 3, ("A", "B"): 0, ("B", "A"): 1, ("B", "B"): 2}
    for (true, pred), count in counts.items():
        rows.append(
            {
                "horizon_seconds": 35,
                "feature_set_name": "stable_only",
                "model_name": "logistic_regression",
                "true_label": true,
                "predicted_label": pred,
                "count": count,
            }
        )
    rows.append(
        {
            "horizon_seconds": 45,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "true_label": "A",
            "predicted_label": "A",
            "count": 1,
        }
    )
    return rows


def _predictions() -> list[dict[str, object]]:
    rows = []
    labels = ["A", "A", "A", "B", "B", "B"]
    predicted = ["A", "A", "A", "A", "B", "B"]
    for index, (true, pred) in enumerate(zip(labels, predicted, strict=False), start=1):
        confidence = 0.82 if true != pred else 0.76
        rows.append(
            {
                "horizon_seconds": 35,
                "feature_set_name": "stable_only",
                "model_name": "logistic_regression",
                "round_feature_id": f"rf_{index}",
                "round_id": f"round_{index}",
                "series_id": "series_1",
                "opponent": "G2",
                "round_num": index,
                "true_label": true,
                "predicted_label": pred,
                "predicted_proba_A": confidence if pred == "A" else 1 - confidence,
                "predicted_proba_B": confidence if pred == "B" else 1 - confidence,
                "is_correct": true == pred,
                "fold_id": 1,
                "prediction_confidence": confidence,
                "prediction_margin": abs(confidence - (1 - confidence)),
                "error_type": "correct" if true == pred else "B_predicted_as_A",
            }
        )
    rows.append({**rows[0], "horizon_seconds": 45, "round_feature_id": "other"})
    return rows


def _feature_sets() -> list[dict[str, object]]:
    return [
        {
            "horizon_seconds": 35,
            "feature_set_name": "stable_only",
            "total_candidate_features": 12,
            "total_selected_features": 2,
            "numeric_features": 2,
            "categorical_features": 0,
            "excluded_leakage_features": "winner_team",
            "excluded_future_window_features": "players_a_pressure_35_45",
            "excluded_by_feature_set_rule": "round_num",
            "selected_feature_names": "players_mid_control_0_35|smokes_used_0_35",
            "model_rows": 6,
            "rows_excluded_plant_before_horizon": 0,
            "notes": "Stable fixture features.",
        },
        {
            "horizon_seconds": 45,
            "feature_set_name": "stable_only",
            "total_candidate_features": 12,
            "total_selected_features": 1,
            "numeric_features": 1,
            "categorical_features": 0,
            "excluded_leakage_features": "",
            "excluded_future_window_features": "",
            "excluded_by_feature_set_rule": "",
            "selected_feature_names": "players_mid_control_0_35",
            "model_rows": 6,
            "rows_excluded_plant_before_horizon": 0,
            "notes": "Other fixture features.",
        },
    ]


def _feature_catalog() -> list[dict[str, object]]:
    return [
        {
            "column_name": "players_mid_control_0_35",
            "inferred_feature_group": "region_position",
            "window_start": 0,
            "window_end": 35,
            "window_type": "cumulative",
            "usable_for_future_model": True,
        },
        {
            "column_name": "smokes_used_0_35",
            "inferred_feature_group": "utility",
            "window_start": 0,
            "window_end": 35,
            "window_type": "cumulative",
            "usable_for_future_model": True,
        },
    ]


def _importance() -> list[dict[str, object]]:
    return [
        {
            "horizon_seconds": 35,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "feature_name": "players_mid_control_0_35",
            "feature_group": "region_position",
            "window_start": 0,
            "window_end": 35,
            "window_type": "cumulative",
            "importance_value": 0.40,
            "importance_rank": 1,
            "direction": "B",
            "notes": "fixture coefficient",
        },
        {
            "horizon_seconds": 45,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "feature_name": "other_feature",
            "feature_group": "utility",
            "window_start": 0,
            "window_end": 45,
            "window_type": "cumulative",
            "importance_value": 0.10,
            "importance_rank": 1,
            "direction": "A",
            "notes": "other coefficient",
        },
    ]


def _comparison() -> list[dict[str, object]]:
    return [
        {
            "horizon_seconds": 35,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "refined_macro_f1": 0.8123,
            "baseline_macro_f1": 0.7000,
            "delta_macro_f1": 0.1123,
            "refined_recall_B": 0.6667,
            "baseline_recall_B": 0.5000,
            "delta_recall_B": 0.1667,
            "refined_B_predicted_as_A": 1,
            "baseline_B_predicted_as_A": 2,
            "delta_B_predicted_as_A": -1,
            "refined_high_confidence_B_predicted_as_A": 1,
            "baseline_high_confidence_B_predicted_as_A": 2,
            "delta_high_confidence_B_predicted_as_A": -1,
            "comparison_status": "improved",
        },
        {
            "horizon_seconds": 45,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "refined_macro_f1": 0.50,
            "baseline_macro_f1": 0.70,
            "delta_macro_f1": -0.20,
            "refined_recall_B": 0.50,
            "baseline_recall_B": 0.50,
            "delta_recall_B": 0.0,
            "refined_B_predicted_as_A": 2,
            "baseline_B_predicted_as_A": 2,
            "delta_B_predicted_as_A": 0,
            "refined_high_confidence_B_predicted_as_A": 0,
            "baseline_high_confidence_B_predicted_as_A": 0,
            "delta_high_confidence_B_predicted_as_A": 0,
            "comparison_status": "worse",
        },
    ]


def _recommendation() -> list[dict[str, object]]:
    return [
        {
            "rank": 1,
            "horizon_seconds": 35,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "macro_f1": 0.8123,
            "recall_B": 0.6667,
            "B_predicted_as_A": 1,
            "high_confidence_B_predicted_as_A": 1,
            "delta_macro_f1_vs_baseline": 0.1123,
            "delta_recall_B_vs_baseline": 0.1667,
            "delta_B_predicted_as_A_vs_baseline": -1,
            "practical_note": "fixture recommendation",
            "recommendation": "candidate_for_next_baseline",
        }
    ]


def _error_summary() -> list[dict[str, object]]:
    return [
        {
            "horizon_seconds": 35,
            "feature_set_name": "stable_only",
            "model_name": "logistic_regression",
            "total_predictions": 6,
            "total_errors": 1,
            "B_predicted_as_A": 1,
        }
    ]


def _refined_audit() -> dict[str, object]:
    return {
        "audit_id": "t_side_ab_refined_experiment",
        "horizons": "35|45",
        "feature_sets": "stable_only",
        "models": "logistic",
        "input_rows": 6,
        "final_model_rows": 6,
        "metric_rows": 2,
        "prediction_rows": 7,
        "recommendation_rows": 1,
        "missing_optional_inputs": "none",
        "status": "ok",
        "created_at": "2026-07-08T00:00:00+00:00",
    }


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def test_candidate_promotion_cli_dry_run(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.modeling.t_side_ab_candidate_promotion",
            "--config",
            str(config),
            "--dry-run",
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "T-side A/B Candidate Promotion summary" in result.stdout
    assert not (tmp_path / "data/gold/modeling/t_side_ab_candidate").exists()


def test_candidate_promotion_outputs_are_created_with_force(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _, outputs, _ = run_t_side_ab_candidate_promotion(config, force=True)

    assert len(outputs) == len(OUTPUT_NAMES) * 2 + 3
    assert all(path.exists() for path in outputs.values())


def test_selection_contains_exactly_one_default_candidate(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_candidate_promotion(config, dry_run=True)
    selection = frames["candidate_model_selection"]

    assert len(selection) == 1
    row = selection.iloc[0]
    assert row["candidate_horizon_seconds"] == 35
    assert row["candidate_feature_set"] == "stable_only"
    assert row["candidate_model_name"] == "logistic_regression"


def test_metrics_predictions_importance_and_comparison_are_filtered(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_candidate_promotion(config, dry_run=True)

    for name in [
        "candidate_model_metrics",
        "candidate_model_predictions",
        "candidate_model_feature_importance",
        "candidate_model_comparison_vs_baseline",
    ]:
        frame = frames[name]
        assert set(frame["horizon_seconds"]) == {35} if "horizon_seconds" in frame.columns else True
        if "feature_set_name" in frame.columns:
            assert set(frame["feature_set_name"]) == {"stable_only"}
        if "model_name" in frame.columns:
            assert set(frame["model_name"]) == {"logistic_regression"}


def test_errors_are_only_wrong_predictions_with_priority(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_candidate_promotion(config, dry_run=True)
    errors = frames["candidate_model_errors"]

    assert len(errors) == 1
    assert set(errors["error_type"]) == {"B_predicted_as_A"}
    assert set(errors["suggested_review_priority"]) == {"high"}
    assert errors["high_confidence_error"].all()


def test_feature_set_has_summary_and_expanded_features(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_candidate_promotion(config, dry_run=True)
    feature_set = frames["candidate_model_feature_set"]

    assert "__feature_set_summary__" in set(feature_set["feature_name"])
    assert "players_mid_control_0_35" in set(feature_set["feature_name"])
    assert set(feature_set["feature_group"]) >= {"summary", "region_position", "utility"}


def test_config_model_card_report_and_audit_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, outputs, _ = run_t_side_ab_candidate_promotion(config, force=True)
    frozen = yaml.safe_load(outputs["candidate_config"].read_text(encoding="utf-8"))
    card = outputs["model_card"].read_text(encoding="utf-8")
    report = outputs["baseline_report"].read_text(encoding="utf-8")

    assert frozen["candidate_horizon_seconds"] == 35
    assert frozen["candidate_feature_set"] == "stable_only"
    assert frozen["candidate_model_name"] == "logistic_regression"
    assert "# Model Card" in card
    assert "# T-side A/B Candidate Baseline Report" in report
    assert not frames["candidate_model_audit"].empty


def test_markdown_uses_loaded_metrics_not_spec_snapshot(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _, outputs, _ = run_t_side_ab_candidate_promotion(config, force=True)
    combined = (
        outputs["model_card"].read_text(encoding="utf-8")
        + outputs["baseline_report"].read_text(encoding="utf-8")
    )

    assert "0.8123" in combined
    assert "0.671" not in combined
