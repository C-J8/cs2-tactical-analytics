from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.modeling.t_side_ab_error_analysis import OUTPUT_NAMES, run_t_side_ab_error_analysis


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
    baseline = gold / "modeling" / "t_side_ab_baseline"
    metrics = _metrics()
    predictions = _predictions()
    _write(baseline, "ab_model_dataset_audit", [{"final_model_rows": 8, "class_A": 4, "class_B": 4, "status": "ok"}])
    _write(
        baseline,
        "ab_model_feature_sets",
        [
            {"horizon_seconds": 15, "model_rows": 8, "total_selected_features": 2},
            {"horizon_seconds": 25, "model_rows": 8, "total_selected_features": 3},
        ],
    )
    _write(baseline, "ab_model_metrics", metrics)
    _write(baseline, "ab_model_confusion_matrices", [{"horizon_seconds": 15, "model_name": "logistic_regression", "true_label": "A", "predicted_label": "A", "count": 3}])
    _write(baseline, "ab_model_predictions", predictions)
    _write(baseline, "ab_model_feature_importance", _importance())
    _write(baseline, "ab_model_horizon_comparison", [{"horizon_seconds": 15, "best_model_by_macro_f1": "logistic_regression"}])
    _write(baseline, "ab_model_readiness_audit", [{"readiness_check": "metrics_generated", "status": "pass"}])

    rounds = [_round_feature(index) for index in range(8)]
    _write(gold / "round_features", "round_features_t_side_planted", rounds)
    _write(
        gold / "round_progression",
        "round_outcome_context",
        [
            {
                "round_feature_id": f"rf_{index}",
                "round_progression_signature": "MID_CONTROL>PLANT_A" if index < 4 else "B_PRESSURE>PLANT_B",
                "round_outcome_type": "plant_A" if index < 4 else "plant_B",
            }
            for index in range(8)
        ],
    )
    manual = gold / "analysis" / "t_side_manual_review"
    _write(manual, "manual_review_rounds", [{"round_feature_id": "rf_4"}])
    _write(manual, "manual_review_decision_template", [{"round_feature_id": "rf_4", "review_decision": "pending"}])
    _write(
        gold / "analysis" / "t_side_tactical_eda",
        "t_side_feature_catalog",
        [
            {"column_name": "feature_0_15", "inferred_feature_group": "region_position"},
            {"column_name": "feature_15_25", "inferred_feature_group": "region_position"},
        ],
    )
    return config


def _metrics() -> list[dict[str, object]]:
    rows = []
    scores = {
        15: {"majority_baseline": 0.33, "logistic_regression": 0.70, "random_forest": 0.65},
        25: {"majority_baseline": 0.33, "logistic_regression": 0.62, "random_forest": 0.72},
    }
    for horizon, models in scores.items():
        for model, macro_f1 in models.items():
            rows.append(
                {
                    "horizon_seconds": horizon,
                    "model_name": model,
                    "accuracy": 0.75,
                    "balanced_accuracy": macro_f1,
                    "macro_f1": macro_f1,
                    "f1_A": 0.8,
                    "f1_B": 0.6,
                    "precision_A": 0.8,
                    "precision_B": 0.6,
                    "recall_A": 0.75,
                    "recall_B": 0.5 if model != "majority_baseline" else 0.0,
                    "roc_auc": 0.75,
                    "support_A": 4,
                    "support_B": 4,
                }
            )
    return rows


def _predictions() -> list[dict[str, object]]:
    rows = []
    for horizon in [15, 25]:
        for model in ["majority_baseline", "logistic_regression", "random_forest"]:
            for index in range(8):
                true = "A" if index < 4 else "B"
                if model == "majority_baseline":
                    predicted = "A"
                elif index in {1, 4}:
                    predicted = "B" if true == "A" else "A"
                else:
                    predicted = true
                high_error = index == 4 and predicted != true
                probability_b = 0.1 if predicted == "A" else 0.9
                if predicted != true and not high_error:
                    probability_b = 0.55 if predicted == "B" else 0.45
                rows.append(
                    {
                        "horizon_seconds": horizon,
                        "model_name": model,
                        "round_feature_id": f"rf_{index}",
                        "round_id": f"round_{index}",
                        "series_id": f"series_{index // 2}",
                        "opponent": "G2" if index % 2 else "Spirit",
                        "round_num": index + 1,
                        "true_label": true,
                        "predicted_label": predicted,
                        "predicted_proba_A": 1 - probability_b,
                        "predicted_proba_B": probability_b,
                        "is_correct": predicted == true,
                        "fold_id": index % 2 + 1,
                    }
                )
    return rows


def _importance() -> list[dict[str, object]]:
    rows = []
    for horizon in [15, 25]:
        for model in ["logistic_regression", "random_forest"]:
            for rank, feature in enumerate(["feature_0_15", "round_num", "feature_15_25"], start=1):
                if horizon == 15 and feature == "feature_15_25":
                    continue
                rows.append(
                    {
                        "horizon": horizon,
                        "model_name": model,
                        "feature_name": feature,
                        "feature_group": "context" if feature == "round_num" else "region_position",
                        "window_start": None if feature == "round_num" else 0 if feature == "feature_0_15" else 15,
                        "window_end": None if feature == "round_num" else 15 if feature == "feature_0_15" else 25,
                        "window_type": "pre_round_context" if feature == "round_num" else "interval",
                        "importance_value": 0.5 / rank,
                        "importance_rank": rank,
                        "direction": "B" if model == "logistic_regression" else None,
                        "notes": "fixture",
                    }
                )
    return rows


def _round_feature(index: int) -> dict[str, object]:
    return {
        "round_feature_id": f"rf_{index}",
        "round_num": index + 1,
        "feature_0_15": float(index),
        "feature_15_25": float(index % 3),
        "category_feature": "x" if index % 2 else "y",
    }


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def test_error_analysis_cli_dry_run(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "src.modeling.t_side_ab_error_analysis", "--config", str(config), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "T-side A/B Error Analysis summary" in result.stdout
    assert not (tmp_path / "data/gold/modeling/t_side_ab_error_analysis").exists()


def test_error_tables_preserve_focus_and_only_errors(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_error_analysis(config, dry_run=True)
    errors = frames["ab_error_rounds"]

    assert (errors["true_label"] != errors["predicted_label"]).all()
    assert set(frames["ab_error_by_horizon_model"]["horizon_seconds"]) == {15, 25}
    assert set(frames["ab_error_by_horizon_model"]["model_name"]) == {"logistic_regression", "random_forest"}
    assert set(frames["ab_error_by_true_label"]["true_label"]) == {"A", "B"}


def test_high_confidence_errors_and_manual_queue(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_error_analysis(config, dry_run=True)

    high = frames["ab_high_confidence_errors"]
    assert not high.empty
    assert high["prediction_confidence"].ge(0.70).all()
    assert not frames["ab_error_manual_review_queue"].empty


def test_feature_stability_and_numeric_contrast_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_error_analysis(config, dry_run=True)

    stability = frames["ab_feature_importance_stability"]
    contrast = frames["ab_feature_error_contrast"]
    assert not stability.empty
    assert not contrast.empty
    assert set(contrast["feature_name"]) <= {"feature_0_15", "feature_15_25", "round_num"}
    assert not frames["ab_horizon_practical_recommendation"].empty


def test_outputs_and_markdown_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _, outputs, _ = run_t_side_ab_error_analysis(config, force=True)

    assert len(outputs) == len(OUTPUT_NAMES) * 2 + 1
    assert all(path.exists() for path in outputs.values())
    assert outputs["markdown_report"].read_text(encoding="utf-8").startswith("# T-side A/B Baseline Error Analysis")
