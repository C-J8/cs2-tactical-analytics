from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config.schemas import load_project_config
from src.modeling.t_side_ab_baseline import (
    evaluate_horizon,
    feature_window,
    filter_pre_plant_rows,
    prepare_model_dataset,
    select_features_for_horizon,
)
from src.utils.io import ensure_dir, read_catalog, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.reports import markdown_table as report_markdown_table
from src.utils.reports import now_utc, safe_divide


OUTPUT_NAMES = [
    "ab_refined_dataset_audit",
    "ab_refined_feature_sets",
    "ab_refined_metrics",
    "ab_refined_confusion_matrices",
    "ab_refined_predictions",
    "ab_refined_feature_importance",
    "ab_refined_error_summary",
    "ab_refined_comparison_vs_baseline",
    "ab_refined_recommendation",
    "ab_refined_audit",
]

DEFAULT_HORIZONS = [15, 35, 45]
DEFAULT_MODELS = ["logistic", "random_forest"]
DEFAULT_FEATURE_SETS = ["all_safe", "stable_only", "no_preround_context", "region_utility_only", "b_focused"]
VALID_MODELS = set(DEFAULT_MODELS)
VALID_FEATURE_SETS = set(DEFAULT_FEATURE_SETS)
GENERAL_CONTEXT = {"round_num", "half", "score_diff_before_round", "is_pistol_round"}
B_KEYWORDS = ["b_", "b_pressure", "apartments", "market", "short", "underpass", "mid"]
TACTICAL_KEYWORDS = [
    "region",
    "players_",
    "team_center",
    "spread",
    "distance",
    "pressure",
    "utility",
    "smoke",
    "molotov",
    "flash",
    "he_",
]


def run_t_side_ab_refined_experiment(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    horizons: list[int] | None = None,
    model_set: list[str] | None = None,
    feature_sets: list[str] | None = None,
    random_seed: int = 42,
    include_opponent: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    horizons = sorted(set(horizons or DEFAULT_HORIZONS))
    model_set = model_set or DEFAULT_MODELS
    feature_sets = feature_sets or DEFAULT_FEATURE_SETS
    validate_options(horizons, model_set, feature_sets)

    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    inputs, missing_optional = load_inputs(gold_dir)
    dataset, base_audit = prepare_model_dataset(
        {
            "dataset": inputs["dataset"],
            "manual_decisions": inputs["manual_decisions"],
            "round_state": inputs["round_state"],
        },
        target_team=target_team,
        target_map=target_map,
    )
    dataset_audit = refined_dataset_audit(base_audit)

    feature_rows: list[dict[str, Any]] = []
    metric_frames: list[pd.DataFrame] = []
    confusion_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    importance_frames: list[pd.DataFrame] = []
    for horizon in horizons:
        horizon_data, plant_excluded = filter_pre_plant_rows(dataset, horizon)
        safe_features, safe_audit = select_features_for_horizon(
            dataset,
            inputs["feature_catalog"],
            horizon=horizon,
            include_opponent=include_opponent,
        )
        for feature_set_name in feature_sets:
            selected, notes = build_feature_set(
                feature_set_name,
                safe_features,
                inputs,
                horizon=horizon,
            )
            selected = [
                column
                for column in selected
                if horizon_data[column].notna().any() and horizon_data[column].nunique(dropna=True) > 1
            ]
            if not selected:
                raise ValueError(f"Feature set {feature_set_name} is empty for horizon {horizon}s.")
            feature_rows.append(
                feature_set_audit(
                    horizon,
                    feature_set_name,
                    selected,
                    safe_features,
                    safe_audit,
                    horizon_data,
                    plant_excluded,
                    notes,
                )
            )
            for model_key in model_set:
                metrics, confusion, predictions, importance = evaluate_horizon(
                    horizon_data,
                    selected,
                    inputs["feature_catalog"],
                    horizon=horizon,
                    model_set=[model_key],
                    random_seed=random_seed,
                    random_forest_estimators=300,
                )
                metrics, predictions = augment_evaluation(metrics, predictions, feature_set_name)
                confusion.insert(1, "feature_set_name", feature_set_name)
                importance = prepare_importance(importance, feature_set_name)
                metric_frames.append(metrics)
                confusion_frames.append(confusion)
                prediction_frames.append(predictions)
                importance_frames.append(importance)

    feature_sets_frame = pd.DataFrame(feature_rows)
    metrics_frame = pd.concat(metric_frames, ignore_index=True)
    confusion_frame = pd.concat(confusion_frames, ignore_index=True)
    predictions_frame = pd.concat(prediction_frames, ignore_index=True)
    importance_frame = pd.concat(importance_frames, ignore_index=True)
    error_summary = build_error_summary(predictions_frame)
    comparison = build_comparison_vs_baseline(
        metrics_frame,
        inputs["baseline_metrics"],
        inputs["baseline_predictions"],
    )
    recommendation = build_recommendation(comparison, metrics_frame)
    frames = {
        "ab_refined_dataset_audit": dataset_audit,
        "ab_refined_feature_sets": feature_sets_frame,
        "ab_refined_metrics": metrics_frame,
        "ab_refined_confusion_matrices": confusion_frame,
        "ab_refined_predictions": predictions_frame,
        "ab_refined_feature_importance": importance_frame,
        "ab_refined_error_summary": error_summary,
        "ab_refined_comparison_vs_baseline": comparison,
        "ab_refined_recommendation": recommendation,
    }
    frames["ab_refined_audit"] = build_audit(
        frames,
        horizons=horizons,
        feature_sets=feature_sets,
        models=model_set,
        input_rows=len(inputs["dataset"]),
        final_rows=len(dataset),
        missing_optional=missing_optional,
    )

    report = build_markdown_report(frames, target_team=target_team, target_map=target_map)
    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = gold_dir / "modeling" / "t_side_ab_refined_experiment"
        outputs.update(write_outputs(frames, output_dir, force=force))
        report_path = project_root / "docs" / "t_side_ab_refined_experiment_report.md"
        write_markdown_report(report, report_path, force=force)
        outputs["markdown_report"] = report_path

    summary = {
        "model_rows": len(dataset),
        "feature_set_rows": len(feature_sets_frame),
        "metric_rows": len(metrics_frame),
        "prediction_rows": len(predictions_frame),
        "recommendation_rows": len(recommendation),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def validate_options(horizons: list[int], model_set: list[str], feature_sets: list[str]) -> None:
    if not horizons or any(value <= 0 or value > 65 for value in horizons):
        raise ValueError("Horizons must be positive and no greater than 65 seconds.")
    unknown_models = set(model_set) - VALID_MODELS
    if unknown_models:
        raise ValueError(f"Unknown models: {sorted(unknown_models)}")
    unknown_sets = set(feature_sets) - VALID_FEATURE_SETS
    if unknown_sets:
        raise ValueError(f"Unknown feature sets: {sorted(unknown_sets)}")


def load_inputs(gold_dir: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    paths = {
        "dataset": gold_dir / "round_features" / "round_features_t_side_planted.parquet",
        "feature_catalog": gold_dir / "analysis" / "t_side_tactical_eda" / "t_side_feature_catalog.parquet",
        "baseline_metrics": gold_dir / "modeling" / "t_side_ab_baseline" / "ab_model_metrics.parquet",
        "baseline_predictions": gold_dir / "modeling" / "t_side_ab_baseline" / "ab_model_predictions.parquet",
        "baseline_feature_sets": gold_dir / "modeling" / "t_side_ab_baseline" / "ab_model_feature_sets.parquet",
        "baseline_importance": gold_dir / "modeling" / "t_side_ab_baseline" / "ab_model_feature_importance.parquet",
        "baseline_horizons": gold_dir / "modeling" / "t_side_ab_baseline" / "ab_model_horizon_comparison.parquet",
        "error_rounds": gold_dir / "modeling" / "t_side_ab_error_analysis" / "ab_error_rounds.parquet",
        "high_confidence_errors": gold_dir / "modeling" / "t_side_ab_error_analysis" / "ab_high_confidence_errors.parquet",
        "stability": gold_dir / "modeling" / "t_side_ab_error_analysis" / "ab_feature_importance_stability.parquet",
        "horizon_recommendation": gold_dir / "modeling" / "t_side_ab_error_analysis" / "ab_horizon_practical_recommendation.parquet",
        "error_queue": gold_dir / "modeling" / "t_side_ab_error_analysis" / "ab_error_manual_review_queue.parquet",
        "manual_decisions": gold_dir / "analysis" / "t_side_manual_review" / "manual_review_decision_template.parquet",
        "round_state": gold_dir / "round_state" / "round_state_resolved.parquet",
        "error_contrast": gold_dir / "modeling" / "t_side_ab_error_analysis" / "ab_feature_error_contrast.parquet",
    }
    required = {"dataset", "feature_catalog", "baseline_metrics", "baseline_predictions", "manual_decisions"}
    inputs = {}
    missing = []
    for name, path in paths.items():
        if path.exists():
            inputs[name] = read_catalog(path)
        elif name in required:
            raise FileNotFoundError(f"Required refined-experiment input not found: {path}")
        else:
            inputs[name] = pd.DataFrame()
            missing.append(name)
    return inputs, missing


def refined_dataset_audit(base_audit: pd.DataFrame) -> pd.DataFrame:
    row = base_audit.iloc[0]
    manual_status = str(row["manual_review_status"]).replace(
        "model is preliminary",
        "refined experiment remains preliminary",
    )
    return pd.DataFrame(
        [
            {
                "total_rows_input": row["total_rows_input"],
                "rows_after_t_side_filter": row["rows_after_t_side_filter"],
                "rows_after_high_confidence_ab_filter": row["rows_after_high_confidence_ab_filter"],
                "rows_excluded_manual_review": row["rows_excluded_manual_review"],
                "final_model_rows": row["final_model_rows"],
                "class_A": row["class_A"],
                "class_B": row["class_B"],
                "class_balance_A": row["class_balance_A"],
                "class_balance_B": row["class_balance_B"],
                "manual_review_status": manual_status,
                "status": row["status"],
            }
        ]
    )


def build_feature_set(
    name: str,
    safe_features: list[str],
    inputs: dict[str, pd.DataFrame],
    *,
    horizon: int,
) -> tuple[list[str], str]:
    catalog = inputs["feature_catalog"].drop_duplicates("column_name").set_index("column_name")
    if name == "all_safe":
        return safe_features.copy(), "All leakage-safe and horizon-safe features."
    if name == "stable_only":
        stable = stable_feature_names(inputs["stability"], inputs["baseline_importance"], horizon)
        selected = [column for column in safe_features if column in stable]
        if len(selected) < 3:
            fallback = fallback_importance_names(inputs["baseline_importance"], horizon)
            selected = [column for column in safe_features if column in fallback][:20]
        return selected, "Stable/model-specific candidates with baseline-importance fallback."
    if name == "no_preround_context":
        selected = []
        for column in safe_features:
            group = catalog_value(catalog, column, "inferred_feature_group")
            window = feature_window(column, catalog)
            if column in GENERAL_CONTEXT or (window is None and group == "context" and not column.startswith("team_")):
                continue
            selected.append(column)
        return selected, "Removes general pre-round context while retaining initial utility inventory."
    if name == "region_utility_only":
        selected = [
            column
            for column in safe_features
            if catalog_value(catalog, column, "inferred_feature_group") in {"region_position", "utility"}
            or any(token in column.casefold() for token in TACTICAL_KEYWORDS)
        ]
        return selected, "Region, position, pressure, and utility signals only."
    stable_b = b_direction_features(inputs["stability"])
    contrast = set(inputs["error_contrast"].get("feature_name", pd.Series(dtype=str)).dropna().astype(str))
    selected = [
        column
        for column in safe_features
        if column in stable_b
        or column in contrast
        or any(token in column.casefold() for token in B_KEYWORDS)
        or catalog_value(catalog, column, "inferred_feature_group") == "utility"
    ]
    return selected, "Existing B-associated, error-contrast, regional-keyword, and utility features."


def stable_feature_names(stability: pd.DataFrame, importance: pd.DataFrame, horizon: int) -> set[str]:
    if not stability.empty:
        selected = stability[stability["stability_label"].isin(["stable_candidate", "model_specific_candidate"])]
        return set(selected["clean_feature_name"].dropna().astype(str))
    return set(fallback_importance_names(importance, horizon))


def fallback_importance_names(importance: pd.DataFrame, horizon: int) -> list[str]:
    if importance.empty:
        return []
    selected = importance[(importance["horizon"] == horizon) & (importance["importance_rank"] <= 20)]
    return selected.sort_values("importance_rank")["feature_name"].dropna().astype(str).tolist()


def b_direction_features(stability: pd.DataFrame) -> set[str]:
    if stability.empty:
        return set()
    selected = stability[stability["direction_summary"].fillna("").str.contains("B")]
    return set(selected["clean_feature_name"].dropna().astype(str))


def catalog_value(catalog: pd.DataFrame, column: str, field: str) -> Any:
    if column not in catalog.index or field not in catalog.columns:
        return None
    value = catalog.at[column, field]
    return value.iloc[0] if isinstance(value, pd.Series) else value


def feature_set_audit(
    horizon: int,
    name: str,
    selected: list[str],
    safe_features: list[str],
    safe_audit: dict[str, Any],
    horizon_data: pd.DataFrame,
    plant_excluded: int,
    notes: str,
) -> dict[str, Any]:
    numeric = [column for column in selected if pd.api.types.is_numeric_dtype(horizon_data[column])]
    excluded_rule = [column for column in safe_features if column not in selected]
    return {
        "horizon_seconds": horizon,
        "feature_set_name": name,
        "total_candidate_features": safe_audit["total_candidate_features"],
        "total_selected_features": len(selected),
        "numeric_features": len(numeric),
        "categorical_features": len(selected) - len(numeric),
        "excluded_leakage_features": safe_audit["excluded_leakage_features"],
        "excluded_future_window_features": safe_audit["excluded_future_window_features"],
        "excluded_by_feature_set_rule": "|".join(excluded_rule),
        "selected_feature_names": "|".join(selected),
        "model_rows": len(horizon_data),
        "rows_excluded_plant_before_horizon": plant_excluded,
        "notes": notes,
    }


def augment_evaluation(
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    feature_set_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions = predictions.copy()
    predictions.insert(1, "feature_set_name", feature_set_name)
    predictions["prediction_confidence"] = predictions[["predicted_proba_A", "predicted_proba_B"]].max(axis=1)
    predictions["prediction_margin"] = (predictions["predicted_proba_A"] - predictions["predicted_proba_B"]).abs()
    predictions["error_type"] = np.where(
        predictions["is_correct"],
        "correct",
        np.where(predictions["true_label"].eq("A"), "A_predicted_as_B", "B_predicted_as_A"),
    )
    errors = predictions[~predictions["is_correct"]]
    metrics = metrics.copy()
    metrics.insert(1, "feature_set_name", feature_set_name)
    metrics["total_errors"] = len(errors)
    metrics["A_predicted_as_B"] = int(errors["error_type"].eq("A_predicted_as_B").sum())
    metrics["B_predicted_as_A"] = int(errors["error_type"].eq("B_predicted_as_A").sum())
    metrics["high_confidence_errors"] = int(errors["prediction_confidence"].ge(0.70).sum())
    metrics["high_confidence_B_predicted_as_A"] = int(
        (errors["prediction_confidence"].ge(0.70) & errors["error_type"].eq("B_predicted_as_A")).sum()
    )
    return metrics, predictions


def prepare_importance(importance: pd.DataFrame, feature_set_name: str) -> pd.DataFrame:
    result = importance.rename(columns={"horizon": "horizon_seconds"}).copy()
    result.insert(1, "feature_set_name", feature_set_name)
    return result


def build_error_summary(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["horizon_seconds", "feature_set_name", "model_name"]
    for key, group in predictions.groupby(keys):
        errors = group[~group["is_correct"]]
        counts = errors["error_type"].value_counts()
        common = counts.index[0] if not counts.empty else "none"
        b_to_a = int(counts.get("B_predicted_as_A", 0))
        high_b = int((errors["error_type"].eq("B_predicted_as_A") & errors["prediction_confidence"].ge(0.70)).sum())
        rows.append(
            {
                **dict(zip(keys, key, strict=False)),
                "total_predictions": len(group),
                "total_errors": len(errors),
                "error_rate": safe_divide(len(errors), len(group)),
                "A_predicted_as_B": int(counts.get("A_predicted_as_B", 0)),
                "B_predicted_as_A": b_to_a,
                "high_confidence_errors": int(errors["prediction_confidence"].ge(0.70).sum()),
                "high_confidence_B_predicted_as_A": high_b,
                "avg_confidence_wrong": errors["prediction_confidence"].mean(),
                "avg_margin_wrong": errors["prediction_margin"].mean(),
                "most_common_error_type": common,
                "interpretation_note": error_interpretation(b_to_a, high_b, len(errors)),
            }
        )
    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)


def error_interpretation(b_to_a: int, high_b: int, total_errors: int) -> str:
    if b_to_a > total_errors / 2:
        return f"B_predicted_as_A dominates; {high_b} are high-confidence"
    return "A/B error directions are mixed"


def build_comparison_vs_baseline(
    refined_metrics: pd.DataFrame,
    baseline_metrics: pd.DataFrame,
    baseline_predictions: pd.DataFrame,
) -> pd.DataFrame:
    baseline_errors = baseline_error_counts(baseline_predictions)
    baseline = baseline_metrics.merge(baseline_errors, on=["horizon_seconds", "model_name"], how="left")
    rows = []
    for _, refined in refined_metrics.iterrows():
        match = baseline[
            baseline["horizon_seconds"].eq(refined["horizon_seconds"])
            & baseline["model_name"].eq(refined["model_name"])
        ]
        if match.empty:
            baseline_row = pd.Series(dtype=object)
        else:
            baseline_row = match.iloc[0]
        delta_macro = delta(refined["macro_f1"], baseline_row.get("macro_f1"))
        delta_recall = delta(refined["recall_B"], baseline_row.get("recall_B"))
        delta_b = delta(refined["B_predicted_as_A"], baseline_row.get("B_predicted_as_A"))
        delta_high_b = delta(
            refined["high_confidence_B_predicted_as_A"],
            baseline_row.get("high_confidence_B_predicted_as_A"),
        )
        rows.append(
            {
                "horizon_seconds": refined["horizon_seconds"],
                "feature_set_name": refined["feature_set_name"],
                "model_name": refined["model_name"],
                "refined_macro_f1": refined["macro_f1"],
                "baseline_macro_f1": baseline_row.get("macro_f1"),
                "delta_macro_f1": delta_macro,
                "refined_recall_B": refined["recall_B"],
                "baseline_recall_B": baseline_row.get("recall_B"),
                "delta_recall_B": delta_recall,
                "refined_B_predicted_as_A": refined["B_predicted_as_A"],
                "baseline_B_predicted_as_A": baseline_row.get("B_predicted_as_A"),
                "delta_B_predicted_as_A": delta_b,
                "refined_high_confidence_B_predicted_as_A": refined["high_confidence_B_predicted_as_A"],
                "baseline_high_confidence_B_predicted_as_A": baseline_row.get(
                    "high_confidence_B_predicted_as_A"
                ),
                "delta_high_confidence_B_predicted_as_A": delta_high_b,
                "comparison_status": comparison_status(delta_macro, delta_recall, delta_b),
            }
        )
    return pd.DataFrame(rows)


def baseline_error_counts(predictions: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame(
            columns=[
                "horizon_seconds",
                "model_name",
                "B_predicted_as_A",
                "high_confidence_B_predicted_as_A",
            ]
        )
    data = predictions.copy()
    data["prediction_confidence"] = data[["predicted_proba_A", "predicted_proba_B"]].max(axis=1)
    data["B_predicted_as_A"] = data["true_label"].eq("B") & data["predicted_label"].eq("A")
    data["high_B_to_A"] = data["B_predicted_as_A"] & data["prediction_confidence"].ge(0.70)
    return (
        data.groupby(["horizon_seconds", "model_name"])
        .agg(
            B_predicted_as_A=("B_predicted_as_A", "sum"),
            high_confidence_B_predicted_as_A=("high_B_to_A", "sum"),
        )
        .reset_index()
    )


def delta(refined: Any, baseline: Any) -> float:
    if baseline is None or pd.isna(baseline):
        return np.nan
    return float(refined - baseline)


def comparison_status(delta_macro: float, delta_recall: float, delta_b: float) -> str:
    if any(pd.isna(value) for value in [delta_macro, delta_recall, delta_b]):
        return "mixed"
    if delta_macro > 0 and delta_b <= 0:
        return "improved"
    if delta_recall >= 0.05:
        return "b_recall_improved"
    if delta_macro < 0 and delta_b > 0:
        return "worse"
    return "mixed"


def build_recommendation(comparison: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    merged = comparison.merge(
        metrics[
            [
                "horizon_seconds",
                "feature_set_name",
                "model_name",
                "macro_f1",
                "recall_B",
                "B_predicted_as_A",
                "high_confidence_B_predicted_as_A",
            ]
        ],
        on=["horizon_seconds", "feature_set_name", "model_name"],
        how="left",
    )
    merged["recommendation"] = merged.apply(recommendation_label, axis=1)
    merged["practical_note"] = merged.apply(practical_note, axis=1)
    priority = {
        "candidate_for_next_baseline": 0,
        "use_as_early_read_baseline": 1,
        "inspect_before_adopting": 2,
        "reject_due_to_no_improvement": 3,
        "reject_due_to_B_errors": 4,
    }
    merged["_priority"] = merged["recommendation"].map(priority)
    merged = merged.sort_values(
        ["_priority", "delta_recall_B", "delta_B_predicted_as_A", "delta_macro_f1"],
        ascending=[True, False, True, False],
    ).reset_index(drop=True)
    merged["rank"] = range(1, len(merged) + 1)
    return merged[
        [
            "rank",
            "horizon_seconds",
            "feature_set_name",
            "model_name",
            "macro_f1",
            "recall_B",
            "B_predicted_as_A",
            "high_confidence_B_predicted_as_A",
            "delta_macro_f1",
            "delta_recall_B",
            "delta_B_predicted_as_A",
            "practical_note",
            "recommendation",
        ]
    ].rename(
        columns={
            "delta_macro_f1": "delta_macro_f1_vs_baseline",
            "delta_recall_B": "delta_recall_B_vs_baseline",
            "delta_B_predicted_as_A": "delta_B_predicted_as_A_vs_baseline",
        }
    )


def recommendation_label(row: pd.Series) -> str:
    delta_macro = row["delta_macro_f1"]
    delta_recall = row["delta_recall_B"]
    delta_b = row["delta_B_predicted_as_A"]
    if pd.notna(delta_b) and (delta_b > 2 or (pd.notna(delta_recall) and delta_recall < -0.05)):
        return "reject_due_to_B_errors"
    if pd.notna(delta_recall) and delta_recall > 0 and pd.notna(delta_b) and delta_b <= 0 and delta_macro >= -0.02:
        return "use_as_early_read_baseline" if row["horizon_seconds"] == 15 else "candidate_for_next_baseline"
    if pd.notna(delta_macro) and delta_macro <= 0 and pd.notna(delta_recall) and delta_recall <= 0:
        return "reject_due_to_no_improvement"
    return "inspect_before_adopting"


def practical_note(row: pd.Series) -> str:
    return (
        f"{int(row['horizon_seconds'])}s {row['feature_set_name']} with {row['model_name']}: "
        f"delta macro F1 {row['delta_macro_f1']:+.3f}, delta recall_B {row['delta_recall_B']:+.3f}, "
        f"delta B->A {row['delta_B_predicted_as_A']:+.0f}."
    )


def build_audit(
    frames: dict[str, pd.DataFrame],
    *,
    horizons: list[int],
    feature_sets: list[str],
    models: list[str],
    input_rows: int,
    final_rows: int,
    missing_optional: list[str],
) -> pd.DataFrame:
    metrics = frames["ab_refined_metrics"]
    predictions = frames["ab_refined_predictions"]
    recommendation = frames["ab_refined_recommendation"]
    failed = metrics.empty or predictions.empty or recommendation.empty
    status = "failed" if failed else "warning" if missing_optional else "ok"
    return pd.DataFrame(
        [
            {
                "audit_id": "t_side_ab_refined_experiment",
                "horizons": "|".join(map(str, horizons)),
                "feature_sets": "|".join(feature_sets),
                "models": "|".join(models),
                "input_rows": input_rows,
                "final_model_rows": final_rows,
                "metric_rows": len(metrics),
                "prediction_rows": len(predictions),
                "recommendation_rows": len(recommendation),
                "missing_optional_inputs": "|".join(missing_optional) if missing_optional else "none",
                "status": status,
                "created_at": now_utc(),
            }
        ]
    )


def build_markdown_report(frames: dict[str, pd.DataFrame], *, target_team: str, target_map: str) -> str:
    audit = frames["ab_refined_dataset_audit"]
    feature_sets = frames["ab_refined_feature_sets"]
    metrics = frames["ab_refined_metrics"]
    errors = frames["ab_refined_error_summary"]
    comparison = frames["ab_refined_comparison_vs_baseline"]
    importance = frames["ab_refined_feature_importance"]
    recommendation = frames["ab_refined_recommendation"]
    top_importance = (
        importance.sort_values(["horizon_seconds", "feature_set_name", "model_name", "importance_rank"])
        .groupby(["horizon_seconds", "feature_set_name", "model_name"], group_keys=False)
        .head(3)
    )
    sections = [
        f"# T-side A/B Refined Experiment -- {target_team} {target_map}",
        "",
        "## Scope",
        "",
        "This focused experiment compares controlled feature sets at 15s, 35s, and 45s. It is not a final model or a hyperparameter search.",
        "",
        "## Why this experiment exists",
        "",
        "Stage 6.1 found many B-predicted-as-A errors. The primary objective is to improve B recall and reduce that error direction without sacrificing macro F1.",
        "",
        "## Dataset",
        "",
        markdown_table(audit, list(audit.columns)),
        "",
        "## Feature sets",
        "",
        markdown_table(feature_sets, ["horizon_seconds", "feature_set_name", "model_rows", "total_selected_features", "numeric_features", "categorical_features", "notes"]),
        "",
        "## Horizons",
        "",
        "The default experiment keeps 15s as the early baseline and evaluates 35s/45s as practical refinement candidates. No 65s model is included by default.",
        "",
        "## Metrics",
        "",
        markdown_table(metrics, ["horizon_seconds", "feature_set_name", "model_name", "macro_f1", "balanced_accuracy", "recall_A", "recall_B", "B_predicted_as_A", "high_confidence_B_predicted_as_A"]),
        "",
        "## B-error analysis",
        "",
        markdown_table(errors, ["horizon_seconds", "feature_set_name", "model_name", "total_errors", "B_predicted_as_A", "high_confidence_B_predicted_as_A", "interpretation_note"]),
        "",
        "## Comparison vs Stage 6 baseline",
        "",
        markdown_table(comparison, ["horizon_seconds", "feature_set_name", "model_name", "delta_macro_f1", "delta_recall_B", "delta_B_predicted_as_A", "comparison_status"]),
        "",
        "## Feature importance",
        "",
        markdown_table(top_importance, ["horizon_seconds", "feature_set_name", "model_name", "feature_name", "feature_group", "importance_value", "importance_rank", "direction"], top_n=45),
        "",
        "## Recommendation",
        "",
        markdown_table(recommendation, list(recommendation.columns), top_n=10),
        "",
        "## Limitations",
        "",
        "- Plant B remains the lower-support class; no-plant rounds remain outside the task.",
        "- Manual review is pending, so every recommendation remains preliminary.",
        "- Comparisons reuse the same small sample and random round-level folds.",
        "- Feature selection and importance are descriptive, not causal.",
        "- No heavy tuning, new algorithm family, or external validation is performed.",
        "",
        "## Next step",
        "",
        "Choose one candidate baseline only if B recall improves without materially worsening B-predicted-as-A errors; otherwise complete manual review first.",
        "",
    ]
    return "\n".join(sections)


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 30) -> str:
    return report_markdown_table(frame, columns, top_n=top_n)


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    return write_dataframe_outputs({name: frames[name] for name in OUTPUT_NAMES}, output_dir, force=force)


def write_markdown_report(report: str, path: Path, *, force: bool) -> None:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(report, encoding="utf-8")


def comma_separated_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def comma_separated_strings(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("T-side A/B Refined Experiment summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a focused leakage-controlled A/B feature refinement experiment.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--horizons", type=comma_separated_ints, default=DEFAULT_HORIZONS)
    parser.add_argument("--model-set", type=comma_separated_strings, default=DEFAULT_MODELS)
    parser.add_argument("--feature-sets", type=comma_separated_strings, default=DEFAULT_FEATURE_SETS)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--include-opponent", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_t_side_ab_refined_experiment(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        horizons=args.horizons,
        model_set=args.model_set,
        feature_sets=args.feature_sets,
        random_seed=args.random_seed,
        include_opponent=args.include_opponent,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
