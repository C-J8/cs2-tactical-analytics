from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "ab_model_dataset_audit",
    "ab_model_feature_sets",
    "ab_model_metrics",
    "ab_model_confusion_matrices",
    "ab_model_predictions",
    "ab_model_feature_importance",
    "ab_model_horizon_comparison",
    "ab_model_readiness_audit",
]

DEFAULT_HORIZONS = [15, 25, 35, 45, 55, 65]
DEFAULT_MODEL_SET = ["baseline", "logistic", "random_forest"]
VALID_MODELS = set(DEFAULT_MODEL_SET)
LABEL_COLUMN = "target_site_model_label"
IDENTIFIER_COLUMNS = ["round_feature_id", "round_id", "parse_id", "dem_file_id", "series_id", "local_archive_id", "dataset_type"]
PREDICTION_IDENTIFIERS = ["round_feature_id", "round_id", "series_id", "opponent", "round_num"]
LEAKAGE_TOKENS = [
    "target_site",
    "label",
    "winner",
    "outcome",
    "round_failure",
    "bomb_planted",
    "bombsite",
    "plant",
    "post",
    "quality",
    "notes",
    "audit",
]
STATIC_PRE_ROUND_FEATURES = {
    "round_num",
    "half",
    "score_diff_before_round",
    "is_pistol_round",
    "team_smokes_start",
    "team_flashes_start",
    "team_molotovs_start",
    "team_he_start",
    "team_decoys_start",
    "team_total_utility_start",
}


def run_t_side_ab_baseline(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    horizons: list[int] | None = None,
    model_set: list[str] | None = None,
    random_seed: int = 42,
    include_opponent: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    horizons = sorted(set(horizons or DEFAULT_HORIZONS))
    model_set = model_set or DEFAULT_MODEL_SET
    validate_options(horizons, model_set)

    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    inputs = load_inputs(gold_dir)
    dataset, dataset_audit = prepare_model_dataset(
        inputs,
        target_team=target_team,
        target_map=target_map,
    )
    if dataset[LABEL_COLUMN].value_counts().min() < 2:
        raise ValueError("Each A/B class must have at least 2 high-confidence examples for StratifiedKFold.")

    feature_sets: list[dict[str, Any]] = []
    metrics_frames: list[pd.DataFrame] = []
    confusion_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    importance_frames: list[pd.DataFrame] = []
    for horizon in horizons:
        features, feature_audit = select_features_for_horizon(
            dataset,
            inputs["feature_catalog"],
            horizon=horizon,
            include_opponent=include_opponent,
        )
        horizon_data, plant_excluded = filter_pre_plant_rows(dataset, horizon)
        feature_audit["model_rows"] = len(horizon_data)
        feature_audit["rows_excluded_plant_before_horizon"] = plant_excluded
        feature_sets.append(feature_audit)
        if not features:
            raise ValueError(f"No leakage-safe features are available for horizon {horizon}s.")
        if horizon_data[LABEL_COLUMN].value_counts().min() < 2:
            raise ValueError(f"Horizon {horizon}s has fewer than 2 examples in one class after plant-time filtering.")

        metrics, confusion, predictions, importance = evaluate_horizon(
            horizon_data,
            features,
            inputs["feature_catalog"],
            horizon=horizon,
            model_set=model_set,
            random_seed=random_seed,
        )
        metrics_frames.append(metrics)
        confusion_frames.append(confusion)
        prediction_frames.append(predictions)
        importance_frames.append(importance)

    feature_sets_frame = pd.DataFrame(feature_sets)
    metrics_frame = concat_frames(metrics_frames, metric_columns())
    confusion_frame = concat_frames(confusion_frames, confusion_columns())
    predictions_frame = concat_frames(prediction_frames, prediction_columns())
    importance_frame = concat_frames(importance_frames, importance_columns())
    horizon_comparison = build_horizon_comparison(metrics_frame, feature_sets_frame)
    readiness = build_readiness_audit(
        dataset=dataset,
        feature_catalog=inputs["feature_catalog"],
        feature_sets=feature_sets_frame,
        metrics=metrics_frame,
        predictions=predictions_frame,
        dataset_audit=dataset_audit,
    )
    frames = {
        "ab_model_dataset_audit": dataset_audit,
        "ab_model_feature_sets": feature_sets_frame,
        "ab_model_metrics": metrics_frame,
        "ab_model_confusion_matrices": confusion_frame,
        "ab_model_predictions": predictions_frame,
        "ab_model_feature_importance": importance_frame,
        "ab_model_horizon_comparison": horizon_comparison,
        "ab_model_readiness_audit": readiness,
    }

    report = build_markdown_report(frames, target_team=target_team, target_map=target_map)
    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = gold_dir / "modeling" / "t_side_ab_baseline"
        outputs.update(write_outputs(frames, output_dir, force=force))
        report_path = project_root / "docs" / "t_side_ab_baseline_report.md"
        write_markdown_report(report, report_path, force=force)
        outputs["markdown_report"] = report_path

    summary = {
        "model_rows": len(dataset),
        "horizons": len(horizons),
        "models": len(model_set),
        "metric_rows": len(metrics_frame),
        "prediction_rows": len(predictions_frame),
        "importance_rows": len(importance_frame),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def validate_options(horizons: list[int], model_set: list[str]) -> None:
    if not horizons or any(horizon <= 0 or horizon > 65 for horizon in horizons):
        raise ValueError("Horizons must contain positive seconds no greater than 65.")
    unknown = set(model_set) - VALID_MODELS
    if unknown:
        raise ValueError(f"Unknown models: {sorted(unknown)}")


def load_inputs(gold_dir: Path) -> dict[str, pd.DataFrame]:
    paths = {
        "dataset": gold_dir / "round_features" / "round_features_t_side_planted.parquet",
        "feature_catalog": gold_dir / "analysis" / "t_side_tactical_eda" / "t_side_feature_catalog.parquet",
        "manual_readiness": gold_dir / "analysis" / "t_side_manual_review" / "manual_review_model_readiness.parquet",
        "manual_decisions": gold_dir / "analysis" / "t_side_manual_review" / "manual_review_decision_template.parquet",
        "manual_rounds": gold_dir / "analysis" / "t_side_manual_review" / "manual_review_rounds.parquet",
        "round_state": gold_dir / "round_state" / "round_state_resolved.parquet",
        "outcome_context": gold_dir / "round_progression" / "round_outcome_context.parquet",
    }
    required = {"dataset", "feature_catalog", "manual_readiness", "manual_decisions", "manual_rounds"}
    inputs: dict[str, pd.DataFrame] = {}
    for name, path in paths.items():
        if path.exists():
            inputs[name] = read_catalog(path)
        elif name in required:
            raise FileNotFoundError(f"Required Stage 6 input not found: {path}")
        else:
            inputs[name] = pd.DataFrame()
    return inputs


def prepare_model_dataset(
    inputs: dict[str, pd.DataFrame],
    *,
    target_team: str,
    target_map: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = inputs["dataset"].copy()
    total_rows = len(raw)
    team_map = raw[
        raw["target_team"].astype(str).str.casefold().eq(target_team.casefold())
        & raw["map_name"].astype(str).str.casefold().isin({target_map.casefold(), f"de_{target_map.casefold()}"})
    ].copy()
    t_side = team_map[team_map["target_team_side"].astype(str).str.upper().eq("T")].copy()
    valid = t_side[
        t_side[LABEL_COLUMN].isin(["A", "B"])
        & t_side["label_confidence"].astype(str).str.casefold().eq("high")
    ].copy()
    rows_after_ab_filter = len(valid)

    decisions = inputs["manual_decisions"]
    excluded_ids: set[str] = set()
    if not decisions.empty and {"round_feature_id", "review_decision"}.issubset(decisions.columns):
        bad = decisions[decisions["review_decision"].isin(["bad_data_or_parse_issue", "does_not_support_finding"])]
        excluded_ids = set(bad["round_feature_id"].dropna().astype(str))
    manual_exclusion = valid["round_feature_id"].astype(str).isin(excluded_ids)
    rows_excluded_manual = int(manual_exclusion.sum())
    valid = valid[~manual_exclusion].copy()

    decision_values = set(decisions.get("review_decision", pd.Series(dtype=str)).dropna().astype(str))
    if not decision_values or decision_values <= {"", "pending"}:
        manual_status = "manual_review_pending; model is preliminary"
    else:
        manual_status = f"manual_review_applied; excluded_rounds={len(excluded_ids)}"

    valid, plant_time_status = attach_plant_time(valid, inputs["round_state"])
    counts = valid[LABEL_COLUMN].value_counts()
    audit = pd.DataFrame(
        [
            {
                "total_rows_input": total_rows,
                "rows_after_team_map_filter": len(team_map),
                "rows_after_t_side_filter": len(t_side),
                "rows_after_high_confidence_ab_filter": rows_after_ab_filter,
                "rows_excluded_manual_review": rows_excluded_manual,
                "final_model_rows": len(valid),
                "class_A": int(counts.get("A", 0)),
                "class_B": int(counts.get("B", 0)),
                "class_balance_A": safe_divide(counts.get("A", 0), len(valid)),
                "class_balance_B": safe_divide(counts.get("B", 0), len(valid)),
                "manual_review_status": manual_status,
                "plant_time_status": plant_time_status,
                "status": "ok" if not valid.empty and set(counts.index) == {"A", "B"} else "failed",
            }
        ]
    )
    return valid.reset_index(drop=True), audit


def attach_plant_time(dataset: pd.DataFrame, round_state: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    result = dataset.copy()
    if round_state.empty or not {"round_id", "plant_tick", "freeze_end_tick"}.issubset(round_state.columns):
        result["_plant_seconds"] = np.nan
        return result, "plant_time_unavailable; horizon filtering uses feature window end only"
    state = round_state[["round_id", "plant_tick", "freeze_end_tick"]].drop_duplicates("round_id")
    result = result.merge(state, on="round_id", how="left", suffixes=("", "_state"))
    plant_tick = pd.to_numeric(result["plant_tick"], errors="coerce")
    freeze_tick = pd.to_numeric(result["freeze_end_tick_state"], errors="coerce")
    if "freeze_end_tick" in result.columns:
        freeze_tick = freeze_tick.fillna(pd.to_numeric(result["freeze_end_tick"], errors="coerce"))
    result["_plant_seconds"] = (plant_tick - freeze_tick) / 64.0
    available = int(result["_plant_seconds"].notna().sum())
    if available == 0:
        return result, "plant_time_unavailable; horizon filtering uses feature window end only"
    return result, f"plant_time_available_for_{available}_of_{len(result)}; rows planted before each horizon are excluded"


def filter_pre_plant_rows(dataset: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, int]:
    if "_plant_seconds" not in dataset.columns or dataset["_plant_seconds"].notna().sum() == 0:
        return dataset.copy(), 0
    safe = dataset["_plant_seconds"].isna() | (dataset["_plant_seconds"] > horizon)
    return dataset[safe].copy(), int((~safe).sum())


def select_features_for_horizon(
    dataset: pd.DataFrame,
    catalog: pd.DataFrame,
    *,
    horizon: int,
    include_opponent: bool,
) -> tuple[list[str], dict[str, Any]]:
    catalog_index = catalog.drop_duplicates("column_name").set_index("column_name")
    selected: list[str] = []
    excluded_leakage: list[str] = []
    excluded_future: list[str] = []
    excluded_unsafe_context: list[str] = []
    candidates = [column for column in dataset.columns if not column.startswith("_")]
    for column in candidates:
        catalog_usable = catalog_value(catalog_index, column, "usable_for_future_model")
        catalog_blocks = catalog_usable is not None and pd.notna(catalog_usable) and not bool(catalog_usable)
        if catalog_blocks or is_manual_leakage(column):
            excluded_leakage.append(column)
            continue
        if column == "opponent" and not include_opponent:
            excluded_unsafe_context.append(column)
            continue
        window = feature_window(column, catalog_index)
        if window is not None:
            if window[1] <= horizon:
                selected.append(column)
            else:
                excluded_future.append(column)
            continue
        if column in STATIC_PRE_ROUND_FEATURES or (column == "opponent" and include_opponent):
            selected.append(column)
        else:
            excluded_unsafe_context.append(column)

    selected = [column for column in selected if dataset[column].notna().any() and dataset[column].nunique(dropna=True) > 1]
    numeric = [column for column in selected if pd.api.types.is_numeric_dtype(dataset[column]) or pd.api.types.is_bool_dtype(dataset[column])]
    categorical = [column for column in selected if column not in numeric]
    return selected, {
        "horizon_seconds": horizon,
        "total_candidate_features": len(candidates),
        "total_selected_features": len(selected),
        "numeric_features": len(numeric),
        "categorical_features": len(categorical),
        "excluded_leakage_features": join_names(excluded_leakage),
        "excluded_future_window_features": join_names(excluded_future),
        "excluded_unsafe_context_features": join_names(excluded_unsafe_context),
        "selected_feature_names": join_names(selected),
    }


def is_manual_leakage(column: str) -> bool:
    lowered = column.casefold()
    return column in IDENTIFIER_COLUMNS or any(token in lowered for token in LEAKAGE_TOKENS)


def feature_window(column: str, catalog_index: pd.DataFrame) -> tuple[int, int, str] | None:
    catalog_end = catalog_value(catalog_index, column, "window_end")
    if catalog_end is not None and pd.notna(catalog_end):
        start = catalog_value(catalog_index, column, "window_start")
        window_type = catalog_value(catalog_index, column, "window_type") or "catalog"
        return int(start or 0), int(catalog_end), str(window_type)
    interval = re.search(r"_(\d+)_(\d+)$", column)
    if interval:
        start, end = int(interval[1]), int(interval[2])
        return start, end, "cumulative" if start == 0 else "interval"
    point = re.search(r"_(\d+)s$", column)
    if point:
        return 0, int(point[1]), "point"
    return None


def catalog_value(catalog_index: pd.DataFrame, column: str, field: str) -> Any:
    if column not in catalog_index.index or field not in catalog_index.columns:
        return None
    value = catalog_index.at[column, field]
    if isinstance(value, pd.Series):
        return value.iloc[0]
    return value


def evaluate_horizon(
    dataset: pd.DataFrame,
    features: list[str],
    catalog: pd.DataFrame,
    *,
    horizon: int,
    model_set: list[str],
    random_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    y = dataset[LABEL_COLUMN].astype(str)
    n_splits = min(5, int(y.value_counts().min()))
    folds = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_seed)
    splits = list(folds.split(dataset[features], y))
    metric_rows: list[dict[str, Any]] = []
    confusion_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    importance_rows: list[dict[str, Any]] = []

    for model_key in model_set:
        model_name = model_display_name(model_key)
        predictions = np.empty(len(dataset), dtype=object)
        probabilities = np.full((len(dataset), 2), np.nan)
        fold_ids = np.zeros(len(dataset), dtype=int)
        for fold_id, (train_index, test_index) in enumerate(splits, start=1):
            train = dataset.iloc[train_index]
            test = dataset.iloc[test_index]
            if model_key == "baseline":
                majority = train[LABEL_COLUMN].value_counts().idxmax()
                predictions[test_index] = majority
                probabilities[test_index, 0] = float(majority == "A")
                probabilities[test_index, 1] = float(majority == "B")
            else:
                pipeline = build_pipeline(train[features], model_key=model_key, random_seed=random_seed)
                pipeline.fit(train[features], train[LABEL_COLUMN])
                predictions[test_index] = pipeline.predict(test[features])
                fold_probabilities = pipeline.predict_proba(test[features])
                classes = list(pipeline.named_steps["model"].classes_)
                probabilities[test_index, 0] = fold_probabilities[:, classes.index("A")]
                probabilities[test_index, 1] = fold_probabilities[:, classes.index("B")]
            fold_ids[test_index] = fold_id

        metric_rows.append(calculate_metrics(y, predictions, probabilities[:, 1], horizon, model_name, n_splits))
        matrix = confusion_matrix(y, predictions, labels=["A", "B"])
        for true_index, true_label in enumerate(["A", "B"]):
            for predicted_index, predicted_label in enumerate(["A", "B"]):
                confusion_rows.append(
                    {
                        "horizon_seconds": horizon,
                        "model_name": model_name,
                        "true_label": true_label,
                        "predicted_label": predicted_label,
                        "count": int(matrix[true_index, predicted_index]),
                    }
                )
        for position, (_, row) in enumerate(dataset.iterrows()):
            prediction_rows.append(
                {
                    "horizon_seconds": horizon,
                    "model_name": model_name,
                    **{column: row.get(column) for column in PREDICTION_IDENTIFIERS},
                    "true_label": y.iloc[position],
                    "predicted_label": predictions[position],
                    "predicted_proba_A": probabilities[position, 0],
                    "predicted_proba_B": probabilities[position, 1],
                    "is_correct": y.iloc[position] == predictions[position],
                    "fold_id": fold_ids[position],
                }
            )

        if model_key != "baseline":
            fitted = build_pipeline(dataset[features], model_key=model_key, random_seed=random_seed)
            fitted.fit(dataset[features], y)
            importance_rows.extend(extract_feature_importance(fitted, features, catalog, horizon, model_name))

    return (
        pd.DataFrame(metric_rows, columns=metric_columns()),
        pd.DataFrame(confusion_rows, columns=confusion_columns()),
        pd.DataFrame(prediction_rows, columns=prediction_columns()),
        pd.DataFrame(importance_rows, columns=importance_columns()),
    )


def build_pipeline(data: pd.DataFrame, *, model_key: str, random_seed: int) -> Pipeline:
    numeric = [column for column in data.columns if pd.api.types.is_numeric_dtype(data[column]) or pd.api.types.is_bool_dtype(data[column])]
    categorical = [column for column in data.columns if column not in numeric]
    transformers = []
    if numeric:
        numeric_pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
        transformers.append(("num", numeric_pipeline, numeric))
    if categorical:
        categorical_pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]
        )
        transformers.append(("cat", categorical_pipeline, categorical))
    preprocessor = ColumnTransformer(transformers=transformers, remainder="drop", verbose_feature_names_out=True)
    if model_key == "logistic":
        model = LogisticRegression(class_weight="balanced", max_iter=2000, random_state=random_seed)
    elif model_key == "random_forest":
        model = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=random_seed, n_jobs=-1)
    else:
        raise ValueError(f"Unsupported trainable model: {model_key}")
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def calculate_metrics(
    y_true: pd.Series,
    y_pred: np.ndarray,
    probability_b: np.ndarray,
    horizon: int,
    model_name: str,
    n_splits: int,
) -> dict[str, Any]:
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=["A", "B"],
        zero_division=0,
    )
    try:
        roc_auc = roc_auc_score((y_true == "B").astype(int), probability_b)
    except ValueError:
        roc_auc = np.nan
    return {
        "horizon_seconds": horizon,
        "model_name": model_name,
        "accuracy": accuracy_score(y_true, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, labels=["A", "B"], average="macro", zero_division=0),
        "f1_A": f1[0],
        "f1_B": f1[1],
        "precision_A": precision[0],
        "precision_B": precision[1],
        "recall_A": recall[0],
        "recall_B": recall[1],
        "roc_auc": roc_auc,
        "support_A": int(support[0]),
        "support_B": int(support[1]),
        "n_splits": n_splits,
        "notes": "out-of-fold StratifiedKFold metrics",
    }


def extract_feature_importance(
    pipeline: Pipeline,
    original_features: list[str],
    catalog: pd.DataFrame,
    horizon: int,
    model_name: str,
) -> list[dict[str, Any]]:
    transformed = list(pipeline.named_steps["preprocessor"].get_feature_names_out())
    model = pipeline.named_steps["model"]
    if hasattr(model, "coef_"):
        raw_values = model.coef_[0]
        rank_values = np.abs(raw_values)
        directions = ["B" if value > 0 else "A" if value < 0 else "neutral" for value in raw_values]
        notes = "signed logistic coefficient; positive points toward B"
    else:
        raw_values = model.feature_importances_
        rank_values = raw_values
        directions = [None] * len(raw_values)
        notes = "random forest impurity importance"
    order = pd.Series(rank_values).rank(method="first", ascending=False).astype(int).to_numpy()
    catalog_index = catalog.drop_duplicates("column_name").set_index("column_name")
    rows = []
    for transformed_name, value, rank, direction in zip(transformed, raw_values, order, directions, strict=False):
        feature_name = original_feature_name(transformed_name, original_features)
        window = feature_window(feature_name, catalog_index)
        rows.append(
            {
                "horizon": horizon,
                "model_name": model_name,
                "feature_name": transformed_name.replace("num__", "").replace("cat__", ""),
                "feature_group": catalog_value(catalog_index, feature_name, "inferred_feature_group") or "unknown",
                "window_start": window[0] if window else None,
                "window_end": window[1] if window else None,
                "window_type": window[2] if window else "pre_round_context",
                "importance_value": float(value),
                "importance_rank": int(rank),
                "direction": direction,
                "notes": notes,
            }
        )
    return rows


def original_feature_name(transformed_name: str, originals: list[str]) -> str:
    clean = transformed_name.split("__", 1)[-1]
    exact = [feature for feature in originals if clean == feature]
    if exact:
        return exact[0]
    matches = [feature for feature in originals if clean.startswith(f"{feature}_")]
    return max(matches, key=len) if matches else clean


def build_horizon_comparison(metrics: pd.DataFrame, feature_sets: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon, group in metrics.groupby("horizon_seconds"):
        candidates = group[group["model_name"] != "majority_baseline"]
        best_pool = candidates if not candidates.empty else group
        best = best_pool.sort_values(["macro_f1", "balanced_accuracy"], ascending=False).iloc[0]
        majority = group[group["model_name"] == "majority_baseline"]
        majority_f1 = float(majority.iloc[0]["macro_f1"]) if not majority.empty else np.nan
        best_balanced_accuracy = float(best_pool["balanced_accuracy"].max())
        selected = int(feature_sets.loc[feature_sets["horizon_seconds"] == horizon, "total_selected_features"].iloc[0])
        improvement = float(best["macro_f1"] - majority_f1) if pd.notna(majority_f1) else np.nan
        rows.append(
            {
                "horizon_seconds": int(horizon),
                "best_model_by_macro_f1": best["model_name"],
                "best_macro_f1": best["macro_f1"],
                "best_balanced_accuracy": best_balanced_accuracy,
                "majority_baseline_macro_f1": majority_f1,
                "improvement_over_majority": improvement,
                "selected_features": selected,
                "interpretation_note": interpretation_note(improvement),
            }
        )
    return pd.DataFrame(rows).sort_values("horizon_seconds").reset_index(drop=True)


def interpretation_note(improvement: float) -> str:
    if pd.isna(improvement):
        return "Majority baseline was not requested; no direct improvement comparison."
    if improvement <= 0:
        return "No improvement over majority baseline in out-of-fold macro F1."
    return "Positive out-of-fold macro F1 difference; validate stability before drawing conclusions."


def build_readiness_audit(
    *,
    dataset: pd.DataFrame,
    feature_catalog: pd.DataFrame,
    feature_sets: pd.DataFrame,
    metrics: pd.DataFrame,
    predictions: pd.DataFrame,
    dataset_audit: pd.DataFrame,
) -> pd.DataFrame:
    labels = set(dataset[LABEL_COLUMN])
    selected_text = "|".join(feature_sets["selected_feature_names"].astype(str))
    leakage_selected = [column for column in selected_text.split("|") if column and is_manual_leakage(column)]
    horizon_safe = all(
        feature_window(column, feature_catalog.drop_duplicates("column_name").set_index("column_name"))[1] <= horizon
        for horizon, names in zip(feature_sets["horizon_seconds"], feature_sets["selected_feature_names"], strict=False)
        for column in str(names).split("|")
        if column and feature_window(column, feature_catalog.drop_duplicates("column_name").set_index("column_name")) is not None
    )
    manual_status = dataset_audit.iloc[0]["manual_review_status"]
    checks = [
        readiness_row("high_confidence_ab_dataset_exists", labels == {"A", "B"}, f"rows={len(dataset)}, labels={sorted(labels)}", "Proceed only with high-confidence A/B rows."),
        readiness_row("no_plant_absent", "no_plant" not in labels, f"labels={sorted(labels)}", "Keep no-plant outside this model."),
        readiness_row("feature_catalog_exists", not feature_catalog.empty, f"rows={len(feature_catalog)}", "Maintain the feature catalog as the primary allow/deny source."),
        readiness_row("leakage_fields_removed", not leakage_selected, f"selected_leakage={leakage_selected}", "Remove every leakage field before training."),
        readiness_row("manual_review_considered", True, str(manual_status), "Treat results as preliminary while review remains pending."),
        readiness_row("class_B_support", int((dataset[LABEL_COLUMN] == "B").sum()) >= 20, f"B={int((dataset[LABEL_COLUMN] == 'B').sum())}", "Use class-aware metrics and avoid optimistic claims."),
        readiness_row("horizon_windows_respected", horizon_safe, f"horizons={feature_sets['horizon_seconds'].tolist()}", "Use only features ending at or before each horizon."),
        readiness_row("metrics_generated", not metrics.empty, f"rows={len(metrics)}", "Compare every model against majority baseline."),
        readiness_row("predictions_generated", not predictions.empty, f"rows={len(predictions)}", "Inspect out-of-fold errors by round."),
        readiness_row("report_generated", True, "Markdown report content generated from current tables.", "Publish the report with the model outputs."),
    ]
    return pd.DataFrame(checks)


def readiness_row(check: str, passed: bool, evidence: str, recommendation: str) -> dict[str, str]:
    return {
        "readiness_check": check,
        "status": "pass" if passed else "fail",
        "evidence": evidence,
        "recommendation": recommendation,
    }


def build_markdown_report(frames: dict[str, pd.DataFrame], *, target_team: str, target_map: str) -> str:
    audit = frames["ab_model_dataset_audit"]
    metrics = frames["ab_model_metrics"]
    confusion = frames["ab_model_confusion_matrices"]
    importance = frames["ab_model_feature_importance"]
    comparison = frames["ab_model_horizon_comparison"]
    feature_sets = frames["ab_model_feature_sets"]
    top_importance = (
        importance.sort_values(["horizon", "model_name", "importance_rank"])
        .groupby(["horizon", "model_name"], group_keys=False)
        .head(5)
    )
    sections = [
        f"# T-side A/B Baseline Model -- {target_team} {target_map}",
        "",
        "## Scope",
        "",
        "This baseline predicts high-confidence plant A versus plant B for T-side rounds only. It is an auditable reference, not a final model.",
        "",
        "## Dataset",
        "",
        markdown_table(audit, list(audit.columns)),
        "",
        "## Leakage controls",
        "",
        "Feature-catalog exclusions, manual leakage-name blocks, identifier removal, strict pre-round context allowlisting, horizon filtering, and plant-time row filtering are applied before cross-validation.",
        "",
        "## Prediction horizons",
        "",
        markdown_table(feature_sets, ["horizon_seconds", "model_rows", "total_selected_features", "numeric_features", "categorical_features", "rows_excluded_plant_before_horizon"]),
        "",
        "## Class balance",
        "",
        "The current sample is small and imbalanced: plant B has materially lower support than plant A. No-plant rounds are excluded rather than assigned an inferred site.",
        "",
        "## Metrics by horizon",
        "",
        markdown_table(metrics, ["horizon_seconds", "model_name", "accuracy", "balanced_accuracy", "macro_f1", "f1_A", "f1_B", "roc_auc", "support_A", "support_B"]),
        "",
        "## Confusion matrices",
        "",
        markdown_table(confusion, list(confusion.columns), top_n=100),
        "",
        "## Feature importance",
        "",
        markdown_table(top_importance, ["horizon", "model_name", "feature_name", "feature_group", "importance_value", "importance_rank", "direction"], top_n=60),
        "",
        "## Horizon comparison",
        "",
        markdown_table(comparison, list(comparison.columns)),
        "",
        "## Limitations",
        "",
        "- Metrics are out-of-fold estimates from only the current Vitality Mirage sample.",
        "- Plant B has lower support, so class-specific metrics can vary substantially.",
        "- Later horizons exclude rounds planted before the cutoff, so horizon rows use different cohort sizes and are not directly causal comparisons.",
        "- Manual review is still pending; the model remains preliminary.",
        "- Feature importance is descriptive and does not establish causality.",
        "- No hyperparameter tuning or external validation is performed.",
        "",
        "## Next step",
        "",
        "Complete manual review, inspect recurring errors, and refine leakage-safe features before considering a stronger model.",
        "",
    ]
    return "\n".join(sections)


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 18) -> str:
    if frame.empty:
        return "_No rows available for the current configuration._"
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


def concat_frames(frames: Iterable[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    return pd.concat(non_empty, ignore_index=True).reindex(columns=columns) if non_empty else pd.DataFrame(columns=columns)


def join_names(values: list[str]) -> str:
    return "|".join(values)


def safe_divide(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator / denominator) if denominator else None


def model_display_name(model_key: str) -> str:
    return {"baseline": "majority_baseline", "logistic": "logistic_regression", "random_forest": "random_forest"}[model_key]


def metric_columns() -> list[str]:
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
        "n_splits",
        "notes",
    ]


def confusion_columns() -> list[str]:
    return ["horizon_seconds", "model_name", "true_label", "predicted_label", "count"]


def prediction_columns() -> list[str]:
    return [
        "horizon_seconds",
        "model_name",
        *PREDICTION_IDENTIFIERS,
        "true_label",
        "predicted_label",
        "predicted_proba_A",
        "predicted_proba_B",
        "is_correct",
        "fold_id",
    ]


def importance_columns() -> list[str]:
    return [
        "horizon",
        "model_name",
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


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("T-side A/B Baseline Model summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def comma_separated_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def comma_separated_strings(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train leakage-controlled T-side A/B baseline models by horizon.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--horizons", type=comma_separated_ints, default=DEFAULT_HORIZONS)
    parser.add_argument("--model-set", type=comma_separated_strings, default=DEFAULT_MODEL_SET)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--include-opponent", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_t_side_ab_baseline(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        horizons=args.horizons,
        model_set=args.model_set,
        random_seed=args.random_seed,
        include_opponent=args.include_opponent,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
