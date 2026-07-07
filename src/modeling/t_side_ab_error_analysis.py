from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "ab_error_overview",
    "ab_error_by_horizon_model",
    "ab_error_rounds",
    "ab_high_confidence_errors",
    "ab_error_by_opponent",
    "ab_error_by_true_label",
    "ab_error_by_prediction_type",
    "ab_feature_importance_stability",
    "ab_feature_error_contrast",
    "ab_horizon_practical_recommendation",
    "ab_model_interpretation_summary",
    "ab_error_manual_review_queue",
    "ab_error_analysis_audit",
]

BASELINE_INPUTS = [
    "ab_model_dataset_audit",
    "ab_model_feature_sets",
    "ab_model_metrics",
    "ab_model_confusion_matrices",
    "ab_model_predictions",
    "ab_model_feature_importance",
    "ab_model_horizon_comparison",
    "ab_model_readiness_audit",
]

FOCUS_MODELS = {"best_by_horizon", "logistic_regression", "random_forest", "majority_baseline", "all"}
HIGH_CONFIDENCE_THRESHOLD = 0.70
ERROR_COLUMNS = [
    "horizon_seconds",
    "model_name",
    "round_feature_id",
    "round_id",
    "series_id",
    "opponent",
    "round_num",
    "true_label",
    "predicted_label",
    "predicted_proba_A",
    "predicted_proba_B",
    "prediction_confidence",
    "prediction_margin",
    "error_type",
    "fold_id",
    "round_progression_signature",
    "round_outcome_type",
    "manual_review_status",
    "manual_review_decision",
    "suggested_error_reason",
    "review_priority",
]


def run_t_side_ab_error_analysis(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    focus_model: str = "best_by_horizon",
    focus_horizon: str | int = "all",
    top_n: int = 20,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    if focus_model not in FOCUS_MODELS:
        raise ValueError(f"focus_model must be one of {sorted(FOCUS_MODELS)}")
    if top_n < 1:
        raise ValueError("top_n must be at least 1")

    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    baseline = load_baseline_inputs(gold_dir / "modeling" / "t_side_ab_baseline")
    auxiliary, missing_optional = load_auxiliary_inputs(gold_dir)
    validate_required_inputs(baseline)

    all_metrics = baseline["ab_model_metrics"].copy()
    enriched_predictions = enrich_prediction_opponents(baseline["ab_model_predictions"], auxiliary)
    all_predictions = add_prediction_fields(enriched_predictions)
    selected_metrics, selected_predictions = select_focus(
        all_metrics,
        all_predictions,
        focus_model=focus_model,
        focus_horizon=focus_horizon,
    )
    errors = build_error_rounds(selected_predictions, auxiliary)
    overview = build_error_overview(all_metrics, all_predictions)
    by_horizon_model = build_error_by_horizon_model(selected_metrics, selected_predictions, all_metrics)
    high_confidence = build_high_confidence_errors(errors)
    by_opponent = build_error_by_opponent(selected_predictions)
    by_true_label = build_error_by_true_label(selected_predictions)
    by_prediction_type = build_error_by_prediction_type(selected_predictions)
    stability = build_feature_importance_stability(
        baseline["ab_model_feature_importance"],
        selected_metrics,
        top_n=top_n,
    )
    contrast, unresolved_features = build_feature_error_contrast(
        selected_predictions,
        auxiliary["round_features"],
        baseline["ab_model_feature_importance"],
        stability,
        top_n=top_n,
    )
    horizon_recommendation = build_horizon_recommendation(
        all_metrics,
        all_predictions,
        baseline["ab_model_feature_sets"],
    )
    interpretation = build_interpretation_summary(
        overview,
        by_horizon_model,
        errors,
        high_confidence,
        stability,
        horizon_recommendation,
        auxiliary["manual_decisions"],
    )
    manual_queue = build_error_manual_review_queue(
        errors,
        by_opponent,
        auxiliary["manual_rounds"],
        top_n=top_n,
    )
    frames = {
        "ab_error_overview": overview,
        "ab_error_by_horizon_model": by_horizon_model,
        "ab_error_rounds": errors,
        "ab_high_confidence_errors": high_confidence,
        "ab_error_by_opponent": by_opponent,
        "ab_error_by_true_label": by_true_label,
        "ab_error_by_prediction_type": by_prediction_type,
        "ab_feature_importance_stability": stability,
        "ab_feature_error_contrast": contrast,
        "ab_horizon_practical_recommendation": horizon_recommendation,
        "ab_model_interpretation_summary": interpretation,
        "ab_error_manual_review_queue": manual_queue,
    }
    frames["ab_error_analysis_audit"] = build_analysis_audit(
        baseline=baseline,
        frames=frames,
        missing_optional=missing_optional,
        unresolved_features=unresolved_features,
    )

    report = build_markdown_report(frames, target_team=target_team, target_map=target_map)
    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = gold_dir / "modeling" / "t_side_ab_error_analysis"
        outputs.update(write_outputs(frames, output_dir, force=force))
        report_path = project_root / "docs" / "t_side_ab_error_analysis_report.md"
        write_markdown_report(report, report_path, force=force)
        outputs["markdown_report"] = report_path

    summary = {
        "selected_prediction_rows": len(selected_predictions),
        "error_rows": len(errors),
        "high_confidence_errors": len(high_confidence),
        "stable_features": int(stability["stability_label"].eq("stable_candidate").sum()) if not stability.empty else 0,
        "manual_review_items": len(manual_queue),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def load_baseline_inputs(directory: Path) -> dict[str, pd.DataFrame]:
    inputs = {}
    for name in BASELINE_INPUTS:
        path = directory / f"{name}.parquet"
        inputs[name] = read_catalog(path) if path.exists() else pd.DataFrame()
    return inputs


def load_auxiliary_inputs(gold_dir: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    paths = {
        "round_features": gold_dir / "round_features" / "round_features_t_side_planted.parquet",
        "outcome_context": gold_dir / "round_progression" / "round_outcome_context.parquet",
        "manual_rounds": gold_dir / "analysis" / "t_side_manual_review" / "manual_review_rounds.parquet",
        "manual_decisions": gold_dir / "analysis" / "t_side_manual_review" / "manual_review_decision_template.parquet",
        "feature_catalog": gold_dir / "analysis" / "t_side_tactical_eda" / "t_side_feature_catalog.parquet",
        "round_state": gold_dir / "round_state" / "round_state_resolved.parquet",
    }
    inputs: dict[str, pd.DataFrame] = {}
    missing = []
    for name, path in paths.items():
        if path.exists():
            inputs[name] = read_catalog(path)
        else:
            inputs[name] = pd.DataFrame()
            missing.append(name)
    return inputs, missing


def enrich_prediction_opponents(
    predictions: pd.DataFrame,
    auxiliary: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    result = predictions.copy()
    unresolved = result["opponent"].isna() | result["opponent"].astype(str).str.casefold().isin(
        {"", "unknown", "none", "nan"}
    )
    round_state = auxiliary["round_state"]
    if unresolved.any() and not round_state.empty and {"round_id", "team_ct"}.issubset(round_state.columns):
        opponent_map = round_state.drop_duplicates("round_id").set_index("round_id")["team_ct"]
        resolved = result["round_id"].map(opponent_map)
        result.loc[unresolved & resolved.notna(), "opponent"] = resolved
    unresolved = result["opponent"].isna() | result["opponent"].astype(str).str.casefold().isin(
        {"", "unknown", "none", "nan"}
    )
    manual_rounds = auxiliary["manual_rounds"]
    if unresolved.any() and not manual_rounds.empty and {"round_feature_id", "opponent"}.issubset(manual_rounds.columns):
        opponent_map = manual_rounds.dropna(subset=["opponent"]).drop_duplicates("round_feature_id").set_index("round_feature_id")["opponent"]
        resolved = result["round_feature_id"].map(opponent_map)
        result.loc[unresolved & resolved.notna(), "opponent"] = resolved
    result["opponent"] = result["opponent"].fillna("unknown")
    return result


def validate_required_inputs(inputs: dict[str, pd.DataFrame]) -> None:
    if inputs["ab_model_predictions"].empty:
        raise ValueError("Stage 6 predictions are required for error analysis.")
    if inputs["ab_model_metrics"].empty:
        raise ValueError("Stage 6 metrics are required for error analysis.")
    if inputs["ab_model_feature_importance"].empty:
        raise ValueError("Stage 6 feature importance is required for error analysis.")


def add_prediction_fields(predictions: pd.DataFrame) -> pd.DataFrame:
    result = predictions.copy()
    result["prediction_confidence"] = result[["predicted_proba_A", "predicted_proba_B"]].max(axis=1)
    result["prediction_margin"] = (result["predicted_proba_A"] - result["predicted_proba_B"]).abs()
    result["error_type"] = np.where(
        result["true_label"].eq(result["predicted_label"]),
        "correct",
        np.where(result["true_label"].eq("A"), "A_predicted_as_B", "B_predicted_as_A"),
    )
    return result


def select_focus(
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    *,
    focus_model: str,
    focus_horizon: str | int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    available_horizons = sorted(int(value) for value in metrics["horizon_seconds"].unique())
    if focus_horizon == "all":
        horizons = available_horizons
    else:
        horizon = int(focus_horizon)
        if horizon not in available_horizons:
            raise ValueError(f"focus_horizon must be one of {available_horizons} or 'all'")
        horizons = [horizon]
    selected_metrics = metrics[metrics["horizon_seconds"].isin(horizons)].copy()
    if focus_model == "best_by_horizon":
        non_baseline = selected_metrics[selected_metrics["model_name"] != "majority_baseline"]
        pool = non_baseline if not non_baseline.empty else selected_metrics
        pairs = (
            pool.sort_values(["horizon_seconds", "macro_f1", "balanced_accuracy"], ascending=[True, False, False])
            .drop_duplicates("horizon_seconds")[["horizon_seconds", "model_name"]]
        )
        selected_metrics = selected_metrics.merge(pairs, on=["horizon_seconds", "model_name"], how="inner")
        selected_predictions = predictions.merge(pairs, on=["horizon_seconds", "model_name"], how="inner")
    elif focus_model == "all":
        selected_predictions = predictions[predictions["horizon_seconds"].isin(horizons)].copy()
    else:
        selected_metrics = selected_metrics[selected_metrics["model_name"] == focus_model].copy()
        selected_predictions = predictions[
            predictions["horizon_seconds"].isin(horizons) & predictions["model_name"].eq(focus_model)
        ].copy()
    if selected_predictions.empty:
        raise ValueError("The selected focus produced no prediction rows.")
    return selected_metrics.reset_index(drop=True), selected_predictions.reset_index(drop=True)


def build_error_overview(metrics: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    candidates = metrics[metrics["model_name"] != "majority_baseline"]
    pool = candidates if not candidates.empty else metrics
    best = pool.sort_values(["macro_f1", "balanced_accuracy"], ascending=False).iloc[0]
    majority = metrics[metrics["model_name"] == "majority_baseline"]
    best_majority_f1 = float(majority["macro_f1"].max()) if not majority.empty else np.nan
    best_predictions = predictions[
        predictions["horizon_seconds"].eq(best["horizon_seconds"])
        & predictions["model_name"].eq(best["model_name"])
    ]
    best_errors = best_predictions[~best_predictions["is_correct"]]
    same_horizon_majority = majority[majority["horizon_seconds"].eq(best["horizon_seconds"])]
    majority_same = float(same_horizon_majority.iloc[0]["macro_f1"]) if not same_horizon_majority.empty else np.nan
    return pd.DataFrame(
        [
            {
                "total_prediction_rows": len(predictions),
                "unique_rounds": predictions["round_feature_id"].nunique(),
                "horizons": predictions["horizon_seconds"].nunique(),
                "models": predictions["model_name"].nunique(),
                "best_overall_horizon": int(best["horizon_seconds"]),
                "best_overall_model": best["model_name"],
                "best_macro_f1": best["macro_f1"],
                "best_balanced_accuracy": best["balanced_accuracy"],
                "majority_baseline_best_macro_f1": best_majority_f1,
                "best_improvement_over_majority": best["macro_f1"] - majority_same,
                "total_errors_best_model": len(best_errors),
                "total_high_confidence_errors_best_model": int(
                    best_errors["prediction_confidence"].ge(HIGH_CONFIDENCE_THRESHOLD).sum()
                ),
                "status": "ok",
            }
        ]
    )


def build_error_by_horizon_model(
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    all_metrics: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for _, metric in metrics.iterrows():
        subset = predictions[
            predictions["horizon_seconds"].eq(metric["horizon_seconds"])
            & predictions["model_name"].eq(metric["model_name"])
        ]
        errors = subset[~subset["is_correct"]]
        majority = all_metrics[
            all_metrics["horizon_seconds"].eq(metric["horizon_seconds"])
            & all_metrics["model_name"].eq("majority_baseline")
        ]
        majority_f1 = float(majority.iloc[0]["macro_f1"]) if not majority.empty else np.nan
        improvement = metric["macro_f1"] - majority_f1 if pd.notna(majority_f1) else np.nan
        rows.append(
            {
                **{column: metric.get(column) for column in metric_output_columns()},
                "total_predictions": len(subset),
                "total_errors": len(errors),
                "error_rate": safe_divide(len(errors), len(subset)),
                "high_confidence_errors": int(errors["prediction_confidence"].ge(HIGH_CONFIDENCE_THRESHOLD).sum()),
                "high_confidence_error_rate": safe_divide(
                    int(errors["prediction_confidence"].ge(HIGH_CONFIDENCE_THRESHOLD).sum()), len(subset)
                ),
                "majority_macro_f1_same_horizon": majority_f1,
                "improvement_over_majority": improvement,
                "interpretation_note": model_interpretation(metric, improvement),
            }
        )
    return pd.DataFrame(rows)


def model_interpretation(metric: pd.Series, improvement: float) -> str:
    notes = []
    if pd.notna(improvement):
        notes.append("beats majority baseline" if improvement > 0 else "does not beat majority baseline")
    if metric.get("recall_A", 0) >= 0.8 and metric.get("recall_B", 0) < 0.5:
        notes.append("good A recall but weak B recall")
    elif metric.get("recall_B", 0) < 0.6:
        notes.append("B class remains unstable")
    return "; ".join(notes) or "requires conservative interpretation"


def build_error_rounds(predictions: pd.DataFrame, auxiliary: dict[str, pd.DataFrame]) -> pd.DataFrame:
    errors = predictions[~predictions["is_correct"]].copy()
    context = auxiliary["outcome_context"]
    if not context.empty and "round_feature_id" in context.columns:
        columns = [
            column
            for column in ["round_feature_id", "round_progression_signature", "round_outcome_type"]
            if column in context.columns
        ]
        errors = errors.merge(context[columns].drop_duplicates("round_feature_id"), on="round_feature_id", how="left")
    for column in ["round_progression_signature", "round_outcome_type"]:
        if column not in errors.columns:
            errors[column] = None

    manual_rounds = auxiliary["manual_rounds"]
    queued_ids = set(manual_rounds.get("round_feature_id", pd.Series(dtype=str)).dropna().astype(str))
    errors["manual_review_status"] = np.where(
        errors["round_feature_id"].astype(str).isin(queued_ids), "already_queued_stage_5_2", "not_previously_queued"
    )
    decisions = auxiliary["manual_decisions"]
    if not decisions.empty and {"round_feature_id", "review_decision"}.issubset(decisions.columns):
        decision_map = decisions.groupby("round_feature_id")["review_decision"].agg(join_unique)
        errors["manual_review_decision"] = errors["round_feature_id"].map(decision_map).fillna("not_reviewed")
    else:
        errors["manual_review_decision"] = "not_available"

    opponent_error_counts = errors["opponent"].value_counts()
    opponent_threshold = max(3, int(opponent_error_counts.quantile(0.75))) if not opponent_error_counts.empty else 3
    errors["suggested_error_reason"] = errors.apply(
        lambda row: suggested_error_reason(row, opponent_error_counts, opponent_threshold), axis=1
    )
    errors["review_priority"] = errors.apply(review_priority, axis=1)
    return errors.reindex(columns=ERROR_COLUMNS).sort_values(
        ["review_priority", "prediction_confidence"],
        key=lambda values: values.map({"high": 0, "medium": 1, "low": 2}) if values.name == "review_priority" else values,
        ascending=[True, False],
    ).reset_index(drop=True)


def suggested_error_reason(row: pd.Series, opponent_counts: pd.Series, threshold: int) -> str:
    if opponent_counts.get(row.get("opponent"), 0) >= threshold:
        return "opponent-specific tendency may need review"
    if row["prediction_margin"] < 0.20:
        return "ambiguous low-margin prediction"
    if row["error_type"] == "B_predicted_as_A" and row["prediction_confidence"] >= HIGH_CONFIDENCE_THRESHOLD:
        return "model may be overusing A-majority pattern"
    if row["error_type"] == "A_predicted_as_B" and row["prediction_confidence"] >= HIGH_CONFIDENCE_THRESHOLD:
        return "model may be overreacting to B-like signal"
    return "requires manual review"


def review_priority(row: pd.Series) -> str:
    if row["prediction_confidence"] >= HIGH_CONFIDENCE_THRESHOLD or row["error_type"] == "B_predicted_as_A":
        return "high"
    if row["true_label"] == "B" or row["predicted_label"] == "B" or row["prediction_margin"] < 0.20:
        return "medium"
    return "low"


def build_high_confidence_errors(errors: pd.DataFrame) -> pd.DataFrame:
    result = errors[errors["prediction_confidence"] >= HIGH_CONFIDENCE_THRESHOLD].copy()
    result["why_high_priority"] = result.apply(
        lambda row: f"Wrong {row['error_type']} prediction at {row['prediction_confidence']:.1%} confidence.", axis=1
    )
    result["recommended_action"] = result.apply(high_confidence_action, axis=1)
    return result.reset_index(drop=True)


def high_confidence_action(row: pd.Series) -> str:
    if row["error_type"] == "B_predicted_as_A":
        return "Review demo for fake/late B execute and verify whether A-majority features dominate."
    if row["manual_review_status"] == "already_queued_stage_5_2":
        return "Compare with the existing manual-review finding and decide whether the round should remain in training."
    return "Review demo and verify whether the model is overreacting to a site-like signal."


def build_error_by_opponent(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["horizon_seconds", "model_name", "opponent"]
    for key, group in predictions.groupby(keys, dropna=False):
        errors = group[~group["is_correct"]]
        error_counts = errors["error_type"].value_counts()
        common = error_counts.index[0] if not error_counts.empty else "none"
        rows.append(
            {
                **dict(zip(keys, key, strict=False)),
                "total_predictions": len(group),
                "total_errors": len(errors),
                "error_rate": safe_divide(len(errors), len(group)),
                "A_errors": int(errors["true_label"].eq("A").sum()),
                "B_errors": int(errors["true_label"].eq("B").sum()),
                "A_predicted_as_B": int(error_counts.get("A_predicted_as_B", 0)),
                "B_predicted_as_A": int(error_counts.get("B_predicted_as_A", 0)),
                "high_confidence_errors": int(errors["prediction_confidence"].ge(HIGH_CONFIDENCE_THRESHOLD).sum()),
                "most_common_error_type": common,
                "interpretation_note": opponent_interpretation(len(group), len(errors), common),
            }
        )
    return pd.DataFrame(rows).sort_values(["error_rate", "total_errors"], ascending=False).reset_index(drop=True)


def opponent_interpretation(total: int, errors: int, common: str) -> str:
    if total < 3:
        return "sparse opponent sample"
    if safe_divide(errors, total) and errors / total >= 0.5:
        return f"high observed error rate; most common {common}"
    return "no strong opponent-specific error concentration"


def build_error_by_true_label(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["horizon_seconds", "model_name", "true_label"]
    for key, group in predictions.groupby(keys):
        errors = group[~group["is_correct"]]
        correct = group[group["is_correct"]]
        recall = safe_divide(len(correct), len(group))
        rows.append(
            {
                **dict(zip(keys, key, strict=False)),
                "total_predictions": len(group),
                "correct_predictions": len(correct),
                "errors": len(errors),
                "error_rate": safe_divide(len(errors), len(group)),
                "avg_prediction_confidence": group["prediction_confidence"].mean(),
                "avg_confidence_when_wrong": errors["prediction_confidence"].mean(),
                "avg_confidence_when_correct": correct["prediction_confidence"].mean(),
                "recall": recall,
                "interpretation_note": true_label_interpretation(key[2], recall, len(group)),
            }
        )
    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)


def true_label_interpretation(label: str, recall: float | None, support: int) -> str:
    if support < 10:
        return f"{label} support is sparse"
    if recall is not None and recall < 0.5:
        return f"{label} recall is weak"
    return f"{label} recall should be read with support={support}"


def build_error_by_prediction_type(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["horizon_seconds", "model_name", "true_label", "predicted_label"]
    for key, group in predictions.groupby(keys):
        rows.append(
            {
                **dict(zip(keys, key, strict=False)),
                "count": len(group),
                "share_of_all_predictions": safe_divide(
                    len(group),
                    len(
                        predictions[
                            predictions["horizon_seconds"].eq(key[0]) & predictions["model_name"].eq(key[1])
                        ]
                    ),
                ),
                "avg_predicted_proba_A": group["predicted_proba_A"].mean(),
                "avg_predicted_proba_B": group["predicted_proba_B"].mean(),
                "avg_prediction_confidence": group["prediction_confidence"].mean(),
                "examples_round_ids": "|".join(group["round_id"].astype(str).head(5)),
                "interpretation_note": "correct classification" if key[2] == key[3] else f"{key[2]} confused with {key[3]}",
            }
        )
    return pd.DataFrame(rows).sort_values(keys).reset_index(drop=True)


def build_feature_importance_stability(
    importance: pd.DataFrame,
    selected_metrics: pd.DataFrame,
    *,
    top_n: int,
) -> pd.DataFrame:
    pairs = selected_metrics[["horizon_seconds", "model_name"]].rename(columns={"horizon_seconds": "horizon"})
    selected = importance.merge(pairs, on=["horizon", "model_name"], how="inner")
    selected = selected[selected["importance_rank"] <= top_n].copy()
    selected["clean_feature_name"] = selected["feature_name"].map(clean_feature_name)
    selected["abs_importance"] = selected["importance_value"].abs()
    rows = []
    keys = ["clean_feature_name", "feature_group", "window_start", "window_end", "window_type"]
    for key, group in selected.groupby(keys, dropna=False):
        directions = [value for value in group["direction"].dropna().astype(str) if value not in {"", "None", "nan"}]
        models = group["model_name"].nunique()
        horizons = group["horizon"].nunique()
        mean_rank = group["importance_rank"].mean()
        rows.append(
            {
                "feature_name": group.iloc[0]["feature_name"],
                "clean_feature_name": key[0],
                "feature_group": key[1],
                "window_start": key[2],
                "window_end": key[3],
                "window_type": key[4],
                "models_appeared": models,
                "horizons_appeared": horizons,
                "appearances": len(group),
                "mean_abs_importance": group["abs_importance"].mean(),
                "max_abs_importance": group["abs_importance"].max(),
                "mean_rank": mean_rank,
                "best_rank": int(group["importance_rank"].min()),
                "direction_summary": ",".join(sorted(set(directions))) if directions else "not_applicable",
                "stability_label": stability_label(horizons, models, mean_rank, int(group["importance_rank"].min())),
            }
        )
    if not rows:
        return empty_stability()
    rank = {"stable_candidate": 0, "model_specific_candidate": 1, "weak_or_unstable": 2}
    result = pd.DataFrame(rows)
    result["_rank"] = result["stability_label"].map(rank)
    return result.sort_values(["_rank", "appearances", "mean_rank"], ascending=[True, False, True]).drop(columns="_rank").reset_index(drop=True)


def clean_feature_name(name: str) -> str:
    return str(name).replace("num__", "").replace("cat__", "")


def stability_label(horizons: int, models: int, mean_rank: float, best_rank: int) -> str:
    if (horizons >= 3 or models >= 2) and mean_rank <= 20:
        return "stable_candidate"
    if models == 1 and best_rank <= 10:
        return "model_specific_candidate"
    return "weak_or_unstable"


def empty_stability() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "feature_name",
            "clean_feature_name",
            "feature_group",
            "window_start",
            "window_end",
            "window_type",
            "models_appeared",
            "horizons_appeared",
            "appearances",
            "mean_abs_importance",
            "max_abs_importance",
            "mean_rank",
            "best_rank",
            "direction_summary",
            "stability_label",
        ]
    )


def build_feature_error_contrast(
    predictions: pd.DataFrame,
    round_features: pd.DataFrame,
    importance: pd.DataFrame,
    stability: pd.DataFrame,
    *,
    top_n: int,
) -> tuple[pd.DataFrame, list[str]]:
    if round_features.empty or stability.empty:
        return empty_contrast(), []
    stable = stability.head(top_n)
    resolved: dict[str, str] = {}
    unresolved = []
    for clean in stable["clean_feature_name"]:
        original = resolve_original_feature(clean, list(round_features.columns))
        if original is None or not pd.api.types.is_numeric_dtype(round_features[original]):
            unresolved.append(clean)
        else:
            resolved[clean] = original
    if not resolved:
        return empty_contrast(), unresolved

    importance_pairs = importance.copy()
    importance_pairs["clean_feature_name"] = importance_pairs["feature_name"].map(clean_feature_name)
    rows = []
    for clean, original in resolved.items():
        feature_meta = stable[stable["clean_feature_name"] == clean].iloc[0]
        pairs = importance_pairs[importance_pairs["clean_feature_name"] == clean][["horizon", "model_name"]].drop_duplicates()
        for _, pair in pairs.iterrows():
            subset = predictions[
                predictions["horizon_seconds"].eq(pair["horizon"])
                & predictions["model_name"].eq(pair["model_name"])
            ].copy()
            if original not in subset.columns:
                subset = subset.merge(
                    round_features[["round_feature_id", original]],
                    on="round_feature_id",
                    how="left",
                )
            if subset.empty:
                continue
            subset["prediction_group"] = subset.apply(prediction_group, axis=1)
            for group_name, group in subset.groupby("prediction_group"):
                values = pd.to_numeric(group[original], errors="coerce")
                rows.append(
                    {
                        "horizon_seconds": int(pair["horizon"]),
                        "model_name": pair["model_name"],
                        "feature_name": original,
                        "feature_group": feature_meta["feature_group"],
                        "prediction_group": group_name,
                        "count": len(group),
                        "mean_value": values.mean(),
                        "median_value": values.median(),
                        "std_value": values.std(),
                        "missing_rate": values.isna().mean(),
                    }
                )
    return pd.DataFrame(rows, columns=contrast_columns()), unresolved


def resolve_original_feature(clean: str, columns: list[str]) -> str | None:
    if clean in columns:
        return clean
    matches = [column for column in columns if clean.startswith(f"{column}_")]
    return max(matches, key=len) if matches else None


def prediction_group(row: pd.Series) -> str:
    if row["true_label"] == row["predicted_label"]:
        return f"correct_{row['true_label']}"
    return "A_predicted_as_B" if row["true_label"] == "A" else "B_predicted_as_A"


def contrast_columns() -> list[str]:
    return [
        "horizon_seconds",
        "model_name",
        "feature_name",
        "feature_group",
        "prediction_group",
        "count",
        "mean_value",
        "median_value",
        "std_value",
        "missing_rate",
    ]


def empty_contrast() -> pd.DataFrame:
    return pd.DataFrame(columns=contrast_columns())


def build_horizon_recommendation(
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    feature_sets: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for horizon, group in metrics.groupby("horizon_seconds"):
        candidates = group[group["model_name"] != "majority_baseline"]
        pool = candidates if not candidates.empty else group
        best = pool.sort_values(["macro_f1", "balanced_accuracy"], ascending=False).iloc[0]
        majority = group[group["model_name"] == "majority_baseline"]
        majority_f1 = float(majority.iloc[0]["macro_f1"]) if not majority.empty else np.nan
        selected_predictions = predictions[
            predictions["horizon_seconds"].eq(horizon) & predictions["model_name"].eq(best["model_name"])
        ]
        errors = selected_predictions[~selected_predictions["is_correct"]]
        feature_row = feature_sets[feature_sets["horizon_seconds"].eq(horizon)]
        model_rows = int(feature_row.iloc[0]["model_rows"]) if not feature_row.empty else len(selected_predictions)
        selected_features = int(feature_row.iloc[0]["total_selected_features"]) if not feature_row.empty else 0
        improvement = best["macro_f1"] - majority_f1 if pd.notna(majority_f1) else np.nan
        tradeoff, recommendation = practical_horizon_labels(int(horizon), improvement, model_rows)
        rows.append(
            {
                "horizon_seconds": int(horizon),
                "best_model": best["model_name"],
                "best_macro_f1": best["macro_f1"],
                "best_balanced_accuracy": best["balanced_accuracy"],
                "improvement_over_majority": improvement,
                "model_rows": model_rows,
                "selected_features": selected_features,
                "total_errors": len(errors),
                "high_confidence_errors": int(errors["prediction_confidence"].ge(HIGH_CONFIDENCE_THRESHOLD).sum()),
                "practical_tradeoff": tradeoff,
                "recommendation": recommendation,
            }
        )
    return pd.DataFrame(rows).sort_values("horizon_seconds").reset_index(drop=True)


def practical_horizon_labels(horizon: int, improvement: float, model_rows: int) -> tuple[str, str]:
    if horizon <= 25:
        recommendation = "keep_for_early_prediction_baseline" if pd.isna(improvement) or improvement > 0 else "inspect_before_using"
        return "early_but_weaker_signal", recommendation
    if horizon == 65:
        return "late_round_less_actionable", "avoid_as_primary_due_to_small_cohort"
    if model_rows >= 70 and (pd.isna(improvement) or improvement > 0.10):
        return "balanced_signal_and_round_count", "use_as_main_next_experiment"
    return "stronger_signal_but_smaller_cohort", "inspect_before_using"


def build_interpretation_summary(
    overview: pd.DataFrame,
    by_model: pd.DataFrame,
    errors: pd.DataFrame,
    high_confidence: pd.DataFrame,
    stability: pd.DataFrame,
    horizons: pd.DataFrame,
    manual_decisions: pd.DataFrame,
) -> pd.DataFrame:
    best = overview.iloc[0]
    b_to_a = int(errors["error_type"].eq("B_predicted_as_A").sum()) if not errors.empty else 0
    decisions = set(manual_decisions.get("review_decision", pd.Series(dtype=str)).dropna().astype(str))
    manual_pending = not decisions or decisions <= {"", "pending"}
    stable = stability[stability["stability_label"] == "stable_candidate"] if not stability.empty else stability
    recommended = horizons[horizons["recommendation"] == "use_as_main_next_experiment"]
    rows = [
        interpretation_row("performance", f"Best observed macro F1 is {best['best_macro_f1']:.3f} at {int(best['best_overall_horizon'])}s with {best['best_overall_model']}, improving {best['best_improvement_over_majority']:.3f} over majority at the same horizon.", "ab_error_overview", "best_macro_f1", "important", True),
        interpretation_row("class_balance", "Plant B has lower support than plant A, so B-specific recall and error counts remain less stable.", "ab_error_by_true_label", "recall", "warning", True),
        interpretation_row("errors", f"The selected focus contains {b_to_a} B-predicted-as-A errors and {len(high_confidence)} high-confidence errors.", "ab_error_rounds", "error_type", "important", len(high_confidence) > 0),
        interpretation_row("features", f"{len(stable)} features are stable descriptive candidates across selected horizons/models; none should be treated as causal.", "ab_feature_importance_stability", "stability_label", "info", False),
        interpretation_row("horizon", f"{len(recommended)} horizons meet the current rule for the main next experiment; larger horizons use smaller post-filter cohorts.", "ab_horizon_practical_recommendation", "recommendation", "warning", True),
        interpretation_row("manual_review", "Manual review remains pending; model interpretation is preliminary." if manual_pending else "Manual decisions are available and should be applied before retraining.", "manual_review_decision_template", "review_decision", "warning", True),
        interpretation_row("limitation", "No-plant rounds are outside this A/B model, and random round-level folds do not provide external or future-series validation.", "ab_model_predictions", "fold_id", "important", True),
    ]
    return pd.DataFrame(rows).assign(interpretation_id=lambda frame: [f"interpretation_{i:03d}" for i in range(1, len(frame) + 1)])[
        ["interpretation_id", "interpretation_category", "interpretation_text", "supporting_table", "supporting_metric", "severity", "needs_action"]
    ]


def interpretation_row(
    category: str,
    text: str,
    table: str,
    metric: str,
    severity: str,
    needs_action: bool,
) -> dict[str, Any]:
    return {
        "interpretation_category": category,
        "interpretation_text": text,
        "supporting_table": table,
        "supporting_metric": metric,
        "severity": severity,
        "needs_action": needs_action,
    }


def build_error_manual_review_queue(
    errors: pd.DataFrame,
    by_opponent: pd.DataFrame,
    manual_rounds: pd.DataFrame,
    *,
    top_n: int,
) -> pd.DataFrame:
    if errors.empty:
        return pd.DataFrame(columns=manual_queue_columns())
    repeated = errors.groupby("round_feature_id").size()
    existing = set(manual_rounds.get("round_feature_id", pd.Series(dtype=str)).dropna().astype(str))
    opponent_rates = by_opponent.groupby("opponent")["error_rate"].mean() if not by_opponent.empty else pd.Series(dtype=float)
    queue = errors.copy()
    queue["repeat_count"] = queue["round_feature_id"].map(repeated)
    queue["already_stage_5_2"] = queue["round_feature_id"].astype(str).isin(existing)
    queue["opponent_error_rate"] = queue["opponent"].map(opponent_rates).fillna(0)
    queue["_priority_score"] = (
        queue["prediction_confidence"].ge(HIGH_CONFIDENCE_THRESHOLD).astype(int) * 4
        + queue["error_type"].eq("B_predicted_as_A").astype(int) * 3
        + queue["repeat_count"].clip(upper=4)
        + queue["opponent_error_rate"].ge(0.5).astype(int) * 2
        + queue["already_stage_5_2"].astype(int)
    )
    queue = queue.sort_values(["_priority_score", "prediction_confidence"], ascending=False).drop_duplicates("round_feature_id").head(top_n)
    rows = []
    for index, (_, row) in enumerate(queue.iterrows(), start=1):
        priority = "high" if row["_priority_score"] >= 7 else "medium" if row["_priority_score"] >= 4 else "low"
        rows.append(
            {
                "review_id": f"error_review_{index:03d}",
                "priority": priority,
                **{column: row.get(column) for column in ["horizon_seconds", "model_name", "round_feature_id", "round_id", "series_id", "opponent", "round_num", "true_label", "predicted_label", "prediction_confidence", "error_type"]},
                "reason": f"{row['suggested_error_reason']}; repeated in {int(row['repeat_count'])} selected predictions",
                "suggested_question": suggested_question(row),
                "recommended_action": "Open the demo round, compare visible intent with model signals, and record whether the row should remain in training.",
            }
        )
    return pd.DataFrame(rows, columns=manual_queue_columns())


def suggested_question(row: pd.Series) -> str:
    if row["error_type"] == "B_predicted_as_A":
        return "Which B intent signal was missing or overwhelmed by the A-majority pattern?"
    return "Which B-like signal caused an A round to be classified as B?"


def manual_queue_columns() -> list[str]:
    return [
        "review_id",
        "priority",
        "horizon_seconds",
        "model_name",
        "round_feature_id",
        "round_id",
        "series_id",
        "opponent",
        "round_num",
        "true_label",
        "predicted_label",
        "prediction_confidence",
        "error_type",
        "reason",
        "suggested_question",
        "recommended_action",
    ]


def build_analysis_audit(
    *,
    baseline: dict[str, pd.DataFrame],
    frames: dict[str, pd.DataFrame],
    missing_optional: list[str],
    unresolved_features: list[str],
) -> pd.DataFrame:
    predictions = baseline["ab_model_predictions"]
    metrics = baseline["ab_model_metrics"]
    importance = baseline["ab_model_feature_importance"]
    critical_empty = predictions.empty or metrics.empty or importance.empty
    output_empty = any(frame.empty for frame in frames.values())
    status = "failed" if critical_empty else "warning" if missing_optional or output_empty else "ok"
    missing_text = "|".join(missing_optional) if missing_optional else "none"
    return pd.DataFrame(
        [
            {
                "audit_id": "t_side_ab_error_analysis",
                "input_prediction_rows": len(predictions),
                "input_metric_rows": len(metrics),
                "input_importance_rows": len(importance),
                "unique_rounds": predictions["round_feature_id"].nunique() if not predictions.empty else 0,
                "horizons": predictions["horizon_seconds"].nunique() if not predictions.empty else 0,
                "models": predictions["model_name"].nunique() if not predictions.empty else 0,
                "error_rows": len(frames["ab_error_rounds"]),
                "high_confidence_error_rows": len(frames["ab_high_confidence_errors"]),
                "feature_contrast_rows": len(frames["ab_feature_error_contrast"]),
                "missing_optional_inputs": missing_text,
                "unresolved_contrast_features": "|".join(unresolved_features) if unresolved_features else "none",
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def build_markdown_report(frames: dict[str, pd.DataFrame], *, target_team: str, target_map: str) -> str:
    overview = frames["ab_error_overview"]
    by_model = frames["ab_error_by_horizon_model"]
    high = frames["ab_high_confidence_errors"]
    by_label = frames["ab_error_by_true_label"]
    by_opponent = frames["ab_error_by_opponent"]
    stability = frames["ab_feature_importance_stability"]
    contrast = frames["ab_feature_error_contrast"]
    horizons = frames["ab_horizon_practical_recommendation"]
    queue = frames["ab_error_manual_review_queue"]
    sections = [
        f"# T-side A/B Baseline Error Analysis -- {target_team} {target_map}",
        "",
        "## Scope",
        "",
        "This stage interprets existing out-of-fold Stage 6 predictions. It does not train or tune a new model.",
        "",
        "## Baseline recap",
        "",
        markdown_table(overview, list(overview.columns)),
        "",
        "## Best models by horizon",
        "",
        markdown_table(by_model, ["horizon_seconds", "model_name", "macro_f1", "balanced_accuracy", "recall_A", "recall_B", "improvement_over_majority", "interpretation_note"]),
        "",
        "## Error overview",
        "",
        markdown_table(by_model, ["horizon_seconds", "model_name", "total_predictions", "total_errors", "error_rate", "high_confidence_errors"]),
        "",
        "## High-confidence errors",
        "",
        markdown_table(high, ["horizon_seconds", "model_name", "opponent", "round_num", "true_label", "predicted_label", "prediction_confidence", "suggested_error_reason"], top_n=10),
        "",
        "## A vs B class behavior",
        "",
        markdown_table(by_label, ["horizon_seconds", "model_name", "true_label", "total_predictions", "errors", "error_rate", "recall", "interpretation_note"]),
        "",
        "## Opponent-level errors",
        "",
        markdown_table(by_opponent, ["horizon_seconds", "model_name", "opponent", "total_predictions", "total_errors", "error_rate", "most_common_error_type", "interpretation_note"], top_n=15),
        "",
        "## Feature importance stability",
        "",
        markdown_table(stability, ["clean_feature_name", "feature_group", "models_appeared", "horizons_appeared", "appearances", "mean_rank", "stability_label", "direction_summary"], top_n=10),
        "",
        "## Feature/error contrast",
        "",
        markdown_table(contrast, ["horizon_seconds", "model_name", "feature_name", "prediction_group", "count", "mean_value", "median_value", "missing_rate"], top_n=20),
        "",
        "## Practical horizon recommendation",
        "",
        markdown_table(horizons, list(horizons.columns)),
        "",
        "## Manual review queue",
        "",
        markdown_table(queue, ["review_id", "priority", "horizon_seconds", "model_name", "opponent", "round_num", "error_type", "prediction_confidence", "reason"], top_n=10),
        "",
        "## Limitations",
        "",
        "- This analysis reuses the same small, imbalanced Stage 6 sample and does not establish production readiness.",
        "- Plant B has lower support than plant A; no-plant rounds remain outside the A/B task.",
        "- Larger horizons use different, smaller cohorts after pre-plant filtering.",
        "- Feature importance and error contrasts are descriptive, not causal.",
        "- Random round-level folds are not external or future-series validation.",
        "",
        "## Next step",
        "",
        "Complete the error review queue, then refine leakage-safe features or run one focused model experiment.",
        "",
    ]
    return "\n".join(sections)


def metric_output_columns() -> list[str]:
    return [
        "horizon_seconds",
        "model_name",
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "f1_A",
        "f1_B",
        "precision_A",
        "precision_B",
        "recall_A",
        "recall_B",
        "roc_auc",
        "support_A",
        "support_B",
    ]


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    if frame.empty:
        return "_No rows available for the current focus._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                frames[name].to_csv(path, index=False) if suffix == "csv" else frames[name].to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def write_markdown_report(report: str, path: Path, *, force: bool) -> None:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(report, encoding="utf-8")


def join_unique(values: pd.Series) -> str:
    return "|".join(sorted(set(values.dropna().astype(str))))


def safe_divide(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator / denominator) if denominator else None


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("T-side A/B Error Analysis summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_focus_horizon(value: str) -> str | int:
    return "all" if value.casefold() == "all" else int(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interpret Stage 6 out-of-fold A/B baseline errors without retraining.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--focus-model", choices=sorted(FOCUS_MODELS), default="best_by_horizon")
    parser.add_argument("--focus-horizon", type=parse_focus_horizon, default="all")
    parser.add_argument("--top-n", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_t_side_ab_error_analysis(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        focus_model=args.focus_model,
        focus_horizon=args.focus_horizon,
        top_n=args.top_n,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
