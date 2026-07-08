from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "candidate_model_selection",
    "candidate_model_metrics",
    "candidate_model_confusion_matrix",
    "candidate_model_predictions",
    "candidate_model_errors",
    "candidate_model_feature_set",
    "candidate_model_feature_importance",
    "candidate_model_comparison_vs_baseline",
    "candidate_model_decision",
    "candidate_model_audit",
]

DEFAULT_CANDIDATE_HORIZON = 35
DEFAULT_CANDIDATE_FEATURE_SET = "stable_only"
DEFAULT_CANDIDATE_MODEL = "logistic_regression"
DEFAULT_SELECTION_MODE = "explicit"
VALID_SELECTION_MODES = {
    "explicit",
    "top_recommendation",
    "best_macro_f1",
    "best_b_recall",
    "balanced_objective",
}
REFINED_INPUTS = {
    "dataset_audit": "ab_refined_dataset_audit",
    "feature_sets": "ab_refined_feature_sets",
    "metrics": "ab_refined_metrics",
    "confusion": "ab_refined_confusion_matrices",
    "predictions": "ab_refined_predictions",
    "importance": "ab_refined_feature_importance",
    "error_summary": "ab_refined_error_summary",
    "comparison": "ab_refined_comparison_vs_baseline",
    "recommendation": "ab_refined_recommendation",
    "audit": "ab_refined_audit",
}
OPTIONAL_INPUTS = {
    "baseline_metrics": ("modeling/t_side_ab_baseline", "ab_model_metrics"),
    "baseline_predictions": ("modeling/t_side_ab_baseline", "ab_model_predictions"),
    "baseline_importance": ("modeling/t_side_ab_baseline", "ab_model_feature_importance"),
    "error_review_queue": ("modeling/t_side_ab_error_analysis", "ab_error_manual_review_queue"),
    "manual_review_template": ("analysis/t_side_manual_review", "manual_review_decision_template"),
    "feature_catalog": ("analysis/t_side_tactical_eda", "t_side_feature_catalog"),
    "training_source": ("round_features", "round_features_t_side_planted"),
}


def run_t_side_ab_candidate_promotion(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    candidate_horizon: int = DEFAULT_CANDIDATE_HORIZON,
    candidate_feature_set: str = DEFAULT_CANDIDATE_FEATURE_SET,
    candidate_model: str = DEFAULT_CANDIDATE_MODEL,
    selection_mode: str = DEFAULT_SELECTION_MODE,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    validate_selection_mode(selection_mode)
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"

    inputs, missing_optional = load_inputs(gold_dir)
    selected = select_candidate(
        inputs,
        selection_mode=selection_mode,
        candidate_horizon=candidate_horizon,
        candidate_feature_set=candidate_feature_set,
        candidate_model=candidate_model,
    )
    candidate_id = build_candidate_id(target_team, target_map, selected)
    selected_at = datetime.now(timezone.utc).isoformat()

    frames = build_candidate_frames(
        inputs,
        selected,
        candidate_id=candidate_id,
        target_team=target_team,
        target_map=target_map,
        selection_mode=selection_mode,
        selected_at=selected_at,
        missing_optional=missing_optional,
    )
    docs = build_documents(frames, target_team=target_team, target_map=target_map)
    frozen_config = build_frozen_config(frames, target_team=target_team, target_map=target_map)

    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = gold_dir / "modeling" / "t_side_ab_candidate"
        outputs.update(write_outputs(frames, output_dir, force=force))
        docs_dir = project_root / "docs"
        config_dir = project_root / "configs" / "modeling"
        outputs["model_card"] = write_text(
            docs["model_card"],
            docs_dir / "t_side_ab_candidate_model_card.md",
            force=force,
        )
        outputs["baseline_report"] = write_text(
            docs["baseline_report"],
            docs_dir / "t_side_ab_candidate_baseline_report.md",
            force=force,
        )
        outputs["candidate_config"] = write_yaml(
            frozen_config,
            config_dir / "t_side_ab_candidate_baseline.yaml",
            force=force,
        )

    summary = {
        "selected_candidates": len(frames["candidate_model_selection"]),
        "metric_rows": len(frames["candidate_model_metrics"]),
        "prediction_rows": len(frames["candidate_model_predictions"]),
        "error_rows": len(frames["candidate_model_errors"]),
        "feature_set_rows": len(frames["candidate_model_feature_set"]),
        "importance_rows": len(frames["candidate_model_feature_importance"]),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def validate_selection_mode(selection_mode: str) -> None:
    if selection_mode not in VALID_SELECTION_MODES:
        raise ValueError(f"Unknown selection_mode: {selection_mode}")


def load_inputs(gold_dir: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    refined_dir = gold_dir / "modeling" / "t_side_ab_refined_experiment"
    inputs: dict[str, pd.DataFrame] = {}
    for key, name in REFINED_INPUTS.items():
        path = refined_dir / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Required Stage 6.2 input not found: {path}")
        inputs[key] = read_catalog(path)

    missing_optional: list[str] = []
    for key, (folder, name) in OPTIONAL_INPUTS.items():
        path = gold_dir / Path(folder) / f"{name}.parquet"
        if path.exists():
            inputs[key] = read_catalog(path)
        else:
            inputs[key] = pd.DataFrame()
            missing_optional.append(key)
    return inputs, missing_optional


def select_candidate(
    inputs: dict[str, pd.DataFrame],
    *,
    selection_mode: str,
    candidate_horizon: int,
    candidate_feature_set: str,
    candidate_model: str,
) -> pd.Series:
    metrics = inputs["metrics"]
    comparison = inputs["comparison"]
    recommendation = inputs["recommendation"]
    if selection_mode == "explicit":
        selected = metrics[
            metrics["horizon_seconds"].eq(candidate_horizon)
            & metrics["feature_set_name"].eq(candidate_feature_set)
            & metrics["model_name"].eq(candidate_model)
        ]
        if selected.empty:
            raise ValueError(
                "Explicit candidate not found in Stage 6.2 metrics: "
                f"{candidate_horizon}s / {candidate_feature_set} / {candidate_model}"
            )
        row = selected.iloc[0].copy()
        row["selection_reason"] = "Explicit default/current candidate requested by CLI parameters."
        return row

    if selection_mode == "top_recommendation":
        selected = recommendation.sort_values("rank").iloc[0]
        return metric_row_for_recommendation(metrics, selected, "First row of ab_refined_recommendation.")

    if selection_mode == "best_macro_f1":
        row = metrics.sort_values(["macro_f1", "balanced_accuracy"], ascending=False).iloc[0].copy()
        row["selection_reason"] = "Highest macro F1 in ab_refined_metrics."
        return row

    merged = comparison.merge(
        metrics,
        on=["horizon_seconds", "feature_set_name", "model_name"],
        how="left",
        suffixes=("_comparison", ""),
    )
    if selection_mode == "best_b_recall":
        pool = merged[merged["delta_macro_f1"].fillna(0).ge(0)].copy()
        if pool.empty:
            pool = merged.copy()
        row = pool.sort_values(["recall_B", "macro_f1"], ascending=False).iloc[0].copy()
        row["selection_reason"] = "Highest recall_B with macro F1 not worse than matching baseline when possible."
        return row

    scored = merged.copy()
    scored["_balanced_score"] = balanced_selection_score(scored)
    row = scored.sort_values("_balanced_score", ascending=False).iloc[0].copy()
    row["selection_reason"] = "Best combined score across macro F1, recall_B, and reduced B-predicted-as-A errors."
    return row


def metric_row_for_recommendation(metrics: pd.DataFrame, row: pd.Series, reason: str) -> pd.Series:
    selected = metrics[
        metrics["horizon_seconds"].eq(row["horizon_seconds"])
        & metrics["feature_set_name"].eq(row["feature_set_name"])
        & metrics["model_name"].eq(row["model_name"])
    ]
    if selected.empty:
        raise ValueError("Top recommendation does not exist in ab_refined_metrics.")
    result = selected.iloc[0].copy()
    result["selection_reason"] = reason
    return result


def balanced_selection_score(frame: pd.DataFrame) -> pd.Series:
    macro = normalize(frame["macro_f1"])
    recall = normalize(frame["recall_B"])
    b_reduction = normalize(-frame["delta_B_predicted_as_A"].fillna(0))
    return 0.4 * macro + 0.4 * recall + 0.2 * b_reduction


def normalize(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0)
    span = values.max() - values.min()
    if span == 0:
        return pd.Series(0.0, index=series.index)
    return (values - values.min()) / span


def build_candidate_id(target_team: str, target_map: str, selected: pd.Series) -> str:
    model = str(selected["model_name"]).replace("_regression", "")
    parts = [
        slug(target_team),
        slug(target_map),
        "t",
        "ab",
        f"{int(selected['horizon_seconds'])}s",
        slug(str(selected["feature_set_name"])),
        slug(model),
        "v1",
    ]
    return "_".join(parts)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def build_candidate_frames(
    inputs: dict[str, pd.DataFrame],
    selected: pd.Series,
    *,
    candidate_id: str,
    target_team: str,
    target_map: str,
    selection_mode: str,
    selected_at: str,
    missing_optional: list[str],
) -> dict[str, pd.DataFrame]:
    key = candidate_key(selected)
    metrics = filter_candidate(inputs["metrics"], key)
    predictions = filter_candidate(inputs["predictions"], key)
    confusion = build_confusion(filter_candidate(inputs["confusion"], key), candidate_id)
    feature_set = build_feature_set(inputs["feature_sets"], inputs["feature_catalog"], key, candidate_id)
    importance = add_candidate_id(filter_candidate(inputs["importance"], key), candidate_id)
    comparison = add_candidate_id(filter_candidate(inputs["comparison"], key), candidate_id)
    metrics = add_candidate_id(metrics, candidate_id).reindex(columns=metric_columns())
    predictions = add_candidate_id(predictions, candidate_id).reindex(columns=prediction_columns())
    errors = build_errors(predictions, candidate_id)
    selection = build_selection(
        selected,
        candidate_id=candidate_id,
        target_team=target_team,
        target_map=target_map,
        selection_mode=selection_mode,
        selected_at=selected_at,
    )
    decision = build_decision(comparison, metrics, inputs["manual_review_template"], candidate_id)
    audit = build_audit(
        inputs,
        selected_frames={
            "predictions": predictions,
            "errors": errors,
            "feature_set": feature_set,
            "importance": importance,
        },
        candidate_id=candidate_id,
        missing_optional=missing_optional,
        manual_review_status=str(decision.iloc[0]["decision_status"]),
    )
    return {
        "candidate_model_selection": selection,
        "candidate_model_metrics": metrics,
        "candidate_model_confusion_matrix": confusion,
        "candidate_model_predictions": predictions,
        "candidate_model_errors": errors,
        "candidate_model_feature_set": feature_set,
        "candidate_model_feature_importance": importance.reindex(columns=importance_columns()),
        "candidate_model_comparison_vs_baseline": comparison.reindex(columns=comparison_columns()),
        "candidate_model_decision": decision,
        "candidate_model_audit": audit,
    }


def candidate_key(row: pd.Series) -> dict[str, Any]:
    return {
        "horizon_seconds": int(row["horizon_seconds"]),
        "feature_set_name": str(row["feature_set_name"]),
        "model_name": str(row["model_name"]),
    }


def filter_candidate(frame: pd.DataFrame, key: dict[str, Any]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    mask = pd.Series(True, index=frame.index)
    for column, value in key.items():
        if column in frame.columns:
            mask &= frame[column].eq(value)
    return frame[mask].copy().reset_index(drop=True)


def add_candidate_id(frame: pd.DataFrame, candidate_id: str) -> pd.DataFrame:
    result = frame.copy()
    result.insert(0, "candidate_id", candidate_id)
    return result


def build_confusion(confusion: pd.DataFrame, candidate_id: str) -> pd.DataFrame:
    result = add_candidate_id(confusion, candidate_id)
    if result.empty:
        result["share_of_true_label"] = pd.Series(dtype=float)
        return result.reindex(columns=confusion_columns())
    totals = result.groupby("true_label")["count"].transform("sum")
    result["share_of_true_label"] = np.where(totals > 0, result["count"] / totals, np.nan)
    return result.reindex(columns=confusion_columns())


def build_feature_set(
    feature_sets: pd.DataFrame,
    feature_catalog: pd.DataFrame,
    key: dict[str, Any],
    candidate_id: str,
) -> pd.DataFrame:
    selected = filter_candidate(feature_sets, key)
    if selected.empty:
        return pd.DataFrame(columns=feature_set_columns())
    row = selected.iloc[0].copy()
    feature_names = split_pipe(row.get("selected_feature_names"))
    catalog = catalog_lookup(feature_catalog)
    rows = [feature_set_row(row, candidate_id, "__feature_set_summary__", catalog)]
    rows.extend(feature_set_row(row, candidate_id, feature_name, catalog) for feature_name in feature_names)
    return pd.DataFrame(rows).reindex(columns=feature_set_columns())


def feature_set_row(
    row: pd.Series,
    candidate_id: str,
    feature_name: str,
    catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    info = catalog.get(feature_name, {})
    return {
        "candidate_id": candidate_id,
        "horizon_seconds": row.get("horizon_seconds"),
        "feature_set_name": row.get("feature_set_name"),
        "total_candidate_features": row.get("total_candidate_features"),
        "total_selected_features": row.get("total_selected_features"),
        "numeric_features": row.get("numeric_features"),
        "categorical_features": row.get("categorical_features"),
        "excluded_leakage_features": row.get("excluded_leakage_features"),
        "excluded_future_window_features": row.get("excluded_future_window_features"),
        "excluded_by_feature_set_rule": row.get("excluded_by_feature_set_rule"),
        "selected_feature_names": row.get("selected_feature_names"),
        "model_rows": row.get("model_rows"),
        "rows_excluded_plant_before_horizon": row.get("rows_excluded_plant_before_horizon"),
        "notes": row.get("notes"),
        "feature_name": feature_name,
        "feature_group": info.get("inferred_feature_group", "summary" if feature_name.startswith("__") else "unknown"),
        "window_start": info.get("window_start"),
        "window_end": info.get("window_end"),
        "window_type": info.get("window_type", "summary" if feature_name.startswith("__") else "unknown"),
        "is_temporal_feature": pd.notna(info.get("window_end")),
        "is_pre_round_context": pd.isna(info.get("window_end")) and info.get("inferred_feature_group") == "context",
        "source": "feature_set_summary" if feature_name.startswith("__") else "t_side_feature_catalog",
    }


def catalog_lookup(feature_catalog: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if feature_catalog.empty or "column_name" not in feature_catalog.columns:
        return {}
    return feature_catalog.drop_duplicates("column_name").set_index("column_name").to_dict("index")


def split_pipe(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item for item in str(value).split("|") if item]


def build_selection(
    selected: pd.Series,
    *,
    candidate_id: str,
    target_team: str,
    target_map: str,
    selection_mode: str,
    selected_at: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "candidate_id": candidate_id,
                "target_team": target_team,
                "target_map": target_map,
                "candidate_horizon_seconds": int(selected["horizon_seconds"]),
                "candidate_feature_set": selected["feature_set_name"],
                "candidate_model_name": selected["model_name"],
                "selection_mode": selection_mode,
                "selection_reason": selected.get("selection_reason", "Selected from Stage 6.2 outputs."),
                "source_stage": "Stage 6.2 -- Focused T-side A/B Feature Refinement Experiment",
                "source_table": "ab_refined_metrics",
                "selected_at": selected_at,
                "status": "selected",
            }
        ]
    )


def build_errors(predictions: pd.DataFrame, candidate_id: str) -> pd.DataFrame:
    errors = predictions[~predictions["is_correct"].fillna(False)].copy()
    if errors.empty:
        return pd.DataFrame(columns=error_columns())
    errors["high_confidence_error"] = pd.to_numeric(errors["prediction_confidence"], errors="coerce").ge(0.70)
    errors["suggested_review_priority"] = errors.apply(review_priority, axis=1)
    errors["suggested_review_reason"] = errors.apply(review_reason, axis=1)
    errors["candidate_id"] = candidate_id
    return errors.reindex(columns=error_columns()).reset_index(drop=True)


def review_priority(row: pd.Series) -> str:
    if bool(row["high_confidence_error"]) or row.get("error_type") == "B_predicted_as_A":
        return "high"
    if float(row.get("prediction_margin") or 0) < 0.20 or "B" in {row.get("true_label"), row.get("predicted_label")}:
        return "medium"
    return "low"


def review_reason(row: pd.Series) -> str:
    reasons = []
    if bool(row["high_confidence_error"]):
        reasons.append("high-confidence error")
    if row.get("error_type") == "B_predicted_as_A":
        reasons.append("B plant predicted as A")
    if float(row.get("prediction_margin") or 0) < 0.20:
        reasons.append("low prediction margin")
    if not reasons:
        reasons.append("ordinary out-of-fold error")
    return "; ".join(reasons)


def build_decision(
    comparison: pd.DataFrame,
    metrics: pd.DataFrame,
    manual_review: pd.DataFrame,
    candidate_id: str,
) -> pd.DataFrame:
    comp = comparison.iloc[0] if not comparison.empty else pd.Series(dtype=object)
    metric = metrics.iloc[0] if not metrics.empty else pd.Series(dtype=object)
    review_status = manual_review_state(manual_review)
    delta_macro = value_or_nan(comp.get("delta_macro_f1"))
    delta_recall = value_or_nan(comp.get("delta_recall_B"))
    delta_b_to_a = value_or_nan(comp.get("delta_B_predicted_as_A"))
    if pd.notna(delta_b_to_a) and delta_b_to_a > 0:
        decision = "do_not_promote"
        main_reason = "Candidate increases B-predicted-as-A errors versus the matching baseline."
    elif review_status == "pending":
        decision = "promote_as_exploratory_candidate"
        main_reason = "Metrics improve, but manual review is still pending, so adoption is exploratory."
    elif delta_macro > 0 and delta_recall > 0 and delta_b_to_a <= 0:
        decision = "promote_as_candidate_baseline"
        main_reason = "Macro F1 and recall_B improve while B-predicted-as-A does not increase."
    elif delta_recall > 0 and delta_macro >= -0.02:
        decision = "promote_as_exploratory_candidate"
        main_reason = "Recall_B improves with similar macro F1."
    else:
        decision = "requires_manual_review_first"
        main_reason = "Metrics are mixed and need qualitative review before promotion."

    return pd.DataFrame(
        [
            {
                "candidate_id": candidate_id,
                "decision": decision,
                "decision_status": f"manual_review_{review_status}",
                "main_reason": main_reason,
                "supporting_metrics": supporting_metrics(metric, comp),
                "risks": "small_sample|class_B_lower_support|round_level_cv_only|manual_review_pending",
                "required_before_final_adoption": "complete_manual_review|external_or_temporal_validation",
                "recommended_next_step": "Complete manual review or prepare final project report with limitations.",
            }
        ]
    )


def manual_review_state(manual_review: pd.DataFrame) -> str:
    if manual_review.empty or "review_decision" not in manual_review.columns:
        return "missing"
    values = set(manual_review["review_decision"].fillna("").astype(str).str.strip().str.casefold())
    values.discard("")
    return "pending" if not values or values <= {"pending"} else "applied_or_partial"


def supporting_metrics(metric: pd.Series, comp: pd.Series) -> str:
    parts = [
        f"macro_f1={format_float(metric.get('macro_f1'))}",
        f"recall_B={format_float(metric.get('recall_B'))}",
        f"B_predicted_as_A={format_float(metric.get('B_predicted_as_A'), digits=0)}",
        f"delta_macro_f1={format_float(comp.get('delta_macro_f1'))}",
        f"delta_recall_B={format_float(comp.get('delta_recall_B'))}",
        f"delta_B_predicted_as_A={format_float(comp.get('delta_B_predicted_as_A'), digits=0)}",
    ]
    return "|".join(parts)


def format_float(value: Any, *, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "nan"
    return f"{float(value):.{digits}f}"


def value_or_nan(value: Any) -> float:
    return float(value) if value is not None and not pd.isna(value) else np.nan


def build_audit(
    inputs: dict[str, pd.DataFrame],
    *,
    selected_frames: dict[str, pd.DataFrame],
    candidate_id: str,
    missing_optional: list[str],
    manual_review_status: str,
) -> pd.DataFrame:
    required_frames = ["predictions", "feature_set", "importance"]
    missing_main = [name for name in required_frames if selected_frames[name].empty]
    status = "failed" if missing_main else "warning" if missing_optional or "pending" in manual_review_status else "ok"
    return pd.DataFrame(
        [
            {
                "audit_id": "t_side_ab_candidate_promotion",
                "candidate_id": candidate_id,
                "input_refined_metric_rows": len(inputs["metrics"]),
                "input_refined_prediction_rows": len(inputs["predictions"]),
                "input_refined_importance_rows": len(inputs["importance"]),
                "selected_prediction_rows": len(selected_frames["predictions"]),
                "selected_error_rows": len(selected_frames["errors"]),
                "selected_feature_count": int(selected_frames["feature_set"]["feature_name"].ne("__feature_set_summary__").sum())
                if not selected_frames["feature_set"].empty
                else 0,
                "missing_optional_inputs": "|".join(missing_optional) if missing_optional else "none",
                "manual_review_status": manual_review_status,
                "config_written": True,
                "model_card_written": True,
                "report_written": True,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def build_frozen_config(
    frames: dict[str, pd.DataFrame],
    *,
    target_team: str,
    target_map: str,
) -> dict[str, Any]:
    selection = frames["candidate_model_selection"].iloc[0]
    metrics = frames["candidate_model_metrics"].iloc[0]
    comparison = frames["candidate_model_comparison_vs_baseline"].iloc[0]
    return {
        "candidate_id": selection["candidate_id"],
        "target_team": target_team,
        "target_map": target_map,
        "task": "t_side_ab_site_prediction",
        "label_column": "target_site_model_label",
        "positive_class": "B",
        "candidate_horizon_seconds": int(selection["candidate_horizon_seconds"]),
        "candidate_feature_set": selection["candidate_feature_set"],
        "candidate_model_name": selection["candidate_model_name"],
        "training_source": "data/gold/round_features/round_features_t_side_planted.parquet",
        "feature_source": "data/gold/modeling/t_side_ab_refined_experiment/ab_refined_feature_sets.parquet",
        "selection_source": "data/gold/modeling/t_side_ab_refined_experiment/ab_refined_recommendation.parquet",
        "no_plant_policy": "excluded",
        "label_confidence_required": "high",
        "manual_review_policy": "pending_review_keeps_candidate_exploratory",
        "metrics": {
            "macro_f1": float(metrics["macro_f1"]),
            "recall_B": float(metrics["recall_B"]),
            "B_predicted_as_A": int(metrics["B_predicted_as_A"]),
            "delta_macro_f1": none_if_nan(comparison["delta_macro_f1"]),
            "delta_recall_B": none_if_nan(comparison["delta_recall_B"]),
            "delta_B_predicted_as_A": none_if_nan(comparison["delta_B_predicted_as_A"]),
        },
        "leakage_controls": [
            "feature_catalog_usable_for_future_model",
            "manual_leakage_token_blocklist",
            "identifier_removal",
            "horizon_window_filter",
            "pre_plant_row_filter_when_plant_time_available",
        ],
        "validation": {
            "method": "stratified_kfold_out_of_fold",
            "n_splits": int(metrics["n_splits"]),
            "random_seed": 42,
        },
        "limitations": [
            "small_sample",
            "class_B_lower_support",
            "no_external_validation",
            "no_causal_claims",
            "manual_review_pending",
        ],
    }


def none_if_nan(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def build_documents(
    frames: dict[str, pd.DataFrame],
    *,
    target_team: str,
    target_map: str,
) -> dict[str, str]:
    selection = frames["candidate_model_selection"]
    metrics = frames["candidate_model_metrics"]
    confusion = frames["candidate_model_confusion_matrix"]
    errors = frames["candidate_model_errors"]
    feature_set = frames["candidate_model_feature_set"]
    importance = frames["candidate_model_feature_importance"]
    comparison = frames["candidate_model_comparison_vs_baseline"]
    decision = frames["candidate_model_decision"]
    audit = frames["candidate_model_audit"]
    top_features = importance.sort_values("importance_rank").head(15)
    feature_summary = feature_set[feature_set["feature_name"].eq("__feature_set_summary__")]
    model_card = "\n".join(
        [
            f"# Model Card -- {target_team} {target_map} T-side A/B Candidate Baseline",
            "",
            "## Model identity",
            markdown_table(selection, list(selection.columns)),
            "",
            "## Intended use",
            "Predict A/B only for high-confidence planted T-side rounds in the current MVP scope.",
            "",
            "## Not intended use",
            "This is not a final model, production deployment, causal explanation, CT-side model, or no-plant model.",
            "",
            "## Data",
            markdown_table(audit, ["candidate_id", "selected_prediction_rows", "selected_error_rows", "selected_feature_count", "status"]),
            "",
            "## Target definition",
            "The target is the observed target-team plant site. No-plant rounds are excluded.",
            "",
            "## Candidate configuration",
            markdown_table(selection, ["candidate_horizon_seconds", "candidate_feature_set", "candidate_model_name", "selection_mode", "selection_reason"]),
            "",
            "## Features",
            markdown_table(feature_summary, ["horizon_seconds", "feature_set_name", "total_selected_features", "numeric_features", "categorical_features", "notes"]),
            "",
            "## Leakage controls",
            "Feature catalog exclusions, manual leakage-name blocks, identifier removal, horizon filtering, and pre-plant row filtering are preserved from Stage 6.",
            "",
            "## Evaluation method",
            "Metrics are out-of-fold stratified cross-validation estimates from the existing Stage 6.2 experiment.",
            "",
            "## Metrics",
            markdown_table(metrics, ["accuracy", "balanced_accuracy", "macro_f1", "f1_A", "f1_B", "recall_A", "recall_B", "support_A", "support_B", "total_errors", "B_predicted_as_A"]),
            "",
            "## Comparison against Stage 6 baseline",
            markdown_table(comparison, ["refined_macro_f1", "baseline_macro_f1", "delta_macro_f1", "refined_recall_B", "baseline_recall_B", "delta_recall_B", "delta_B_predicted_as_A", "comparison_status"]),
            "",
            "## Error profile",
            markdown_table(errors, ["round_feature_id", "true_label", "predicted_label", "prediction_confidence", "error_type", "suggested_review_priority"], top_n=12),
            "",
            "## Known limitations",
            "- Small sample and class imbalance remain material limitations.",
            "- Plant B has lower support.",
            "- Validation is still round-level CV, not temporal or external validation.",
            "- Manual review may change confidence in the candidate.",
            "- Feature importance is descriptive and does not establish causality.",
            "",
            "## Manual review status",
            markdown_table(decision, ["decision_status", "required_before_final_adoption"]),
            "",
            "## Ethical / practical cautions",
            "Do not treat predictions as tactical truth without reviewing demos and match context.",
            "",
            "## Recommendation",
            markdown_table(decision, ["decision", "main_reason", "supporting_metrics"]),
            "",
            "## Next step",
            "Complete manual review or prepare a final project report that preserves the limitations above.",
            "",
        ]
    )
    baseline_report = "\n".join(
        [
            f"# T-side A/B Candidate Baseline Report -- {target_team} {target_map}",
            "",
            "## Executive summary",
            markdown_table(decision, ["decision", "decision_status", "main_reason"]),
            "",
            "## Selected candidate",
            markdown_table(selection, ["candidate_id", "candidate_horizon_seconds", "candidate_feature_set", "candidate_model_name"]),
            "",
            "## Why this candidate",
            markdown_table(selection, ["selection_reason"]),
            "",
            "## Metrics",
            markdown_table(metrics, ["macro_f1", "recall_B", "precision_B", "support_A", "support_B", "total_errors", "B_predicted_as_A"]),
            "",
            "## Confusion matrix",
            markdown_table(confusion, ["true_label", "predicted_label", "count", "share_of_true_label"]),
            "",
            "## Error profile",
            markdown_table(errors, ["true_label", "predicted_label", "error_type", "prediction_confidence", "suggested_review_priority"], top_n=12),
            "",
            "## Feature set",
            markdown_table(feature_summary, ["total_selected_features", "numeric_features", "categorical_features", "rows_excluded_plant_before_horizon", "notes"]),
            "",
            "## Top features",
            markdown_table(top_features, ["feature_name", "feature_group", "importance_value", "importance_rank", "direction"], top_n=10),
            "",
            "## Comparison vs previous baseline",
            markdown_table(comparison, ["delta_macro_f1", "delta_recall_B", "delta_B_predicted_as_A", "comparison_status"]),
            "",
            "## Decision",
            markdown_table(decision, ["decision", "required_before_final_adoption", "recommended_next_step"]),
            "",
            "## Limitations",
            "Small sample, lower B support, pending manual review, no external validation, and no causal claims.",
            "",
            "## Next step",
            "Complete manual review or prepare final project report.",
            "",
        ]
    )
    return {"model_card": model_card, "baseline_report": baseline_report}


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 30) -> str:
    if frame.empty:
        return "_No rows available._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                if suffix == "csv":
                    frames[name].to_csv(path, index=False)
                else:
                    frames[name].to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def write_yaml(content: dict[str, Any], path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(yaml.safe_dump(content, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return path


def metric_columns() -> list[str]:
    return [
        "candidate_id",
        "horizon_seconds",
        "feature_set_name",
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
        "total_errors",
        "A_predicted_as_B",
        "B_predicted_as_A",
        "high_confidence_errors",
        "high_confidence_B_predicted_as_A",
        "n_splits",
        "notes",
    ]


def confusion_columns() -> list[str]:
    return ["candidate_id", "true_label", "predicted_label", "count", "share_of_true_label"]


def prediction_columns() -> list[str]:
    return [
        "candidate_id",
        "horizon_seconds",
        "feature_set_name",
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
        "is_correct",
        "error_type",
        "fold_id",
    ]


def error_columns() -> list[str]:
    return [
        "candidate_id",
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
        "high_confidence_error",
        "suggested_review_priority",
        "suggested_review_reason",
    ]


def feature_set_columns() -> list[str]:
    return [
        "candidate_id",
        "horizon_seconds",
        "feature_set_name",
        "total_candidate_features",
        "total_selected_features",
        "numeric_features",
        "categorical_features",
        "excluded_leakage_features",
        "excluded_future_window_features",
        "excluded_by_feature_set_rule",
        "selected_feature_names",
        "model_rows",
        "rows_excluded_plant_before_horizon",
        "notes",
        "feature_name",
        "feature_group",
        "window_start",
        "window_end",
        "window_type",
        "is_temporal_feature",
        "is_pre_round_context",
        "source",
    ]


def importance_columns() -> list[str]:
    return [
        "candidate_id",
        "feature_name",
        "feature_group",
        "window_start",
        "window_end",
        "window_type",
        "importance_value",
        "importance_rank",
        "direction",
        "notes",
    ]


def comparison_columns() -> list[str]:
    return [
        "candidate_id",
        "horizon_seconds",
        "feature_set_name",
        "model_name",
        "refined_macro_f1",
        "baseline_macro_f1",
        "delta_macro_f1",
        "refined_recall_B",
        "baseline_recall_B",
        "delta_recall_B",
        "refined_B_predicted_as_A",
        "baseline_B_predicted_as_A",
        "delta_B_predicted_as_A",
        "refined_high_confidence_B_predicted_as_A",
        "baseline_high_confidence_B_predicted_as_A",
        "delta_high_confidence_B_predicted_as_A",
        "comparison_status",
    ]


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("T-side A/B Candidate Promotion summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote a Stage 6.2 T-side A/B candidate baseline.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--candidate-horizon", type=int, default=DEFAULT_CANDIDATE_HORIZON)
    parser.add_argument("--candidate-feature-set", default=DEFAULT_CANDIDATE_FEATURE_SET)
    parser.add_argument("--candidate-model", default=DEFAULT_CANDIDATE_MODEL)
    parser.add_argument("--selection-mode", default=DEFAULT_SELECTION_MODE, choices=sorted(VALID_SELECTION_MODES))
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_t_side_ab_candidate_promotion(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        candidate_horizon=args.candidate_horizon,
        candidate_feature_set=args.candidate_feature_set,
        candidate_model=args.candidate_model,
        selection_mode=args.selection_mode,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
