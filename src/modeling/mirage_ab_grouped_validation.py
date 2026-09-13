from __future__ import annotations

import argparse
import math
import warnings
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    matthews_corrcoef,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import LeaveOneGroupOut, StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.utils.io import read_table, write_dataframe_outputs


OUTPUT_DIR = Path("data/gold/modeling/mirage_ab_grouped_validation")


def run_grouped_validation(
    config_path: Path,
    *,
    project_root: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project_root = project_root or config_path.resolve().parent.parent.parent
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    dataset, features, group_column = load_candidate_dataset(project_root, config)
    primary = evaluate_scheme(dataset, features, config, scheme="stratified_group_kfold", group_column=group_column)
    sensitivity = evaluate_scheme(dataset, features, config, scheme="leave_one_group_out", group_column=group_column)
    oof = pd.concat([primary["oof"], sensitivity["oof"]], ignore_index=True)
    fold_metrics = pd.concat([primary["fold_metrics"], sensitivity["fold_metrics"]], ignore_index=True)
    metrics = pd.concat([primary["metrics"], sensitivity["metrics"]], ignore_index=True)
    isolation = pd.concat([primary["isolation"], sensitivity["isolation"]], ignore_index=True)
    coefficients = pd.concat([primary["coefficients"], sensitivity["coefficients"]], ignore_index=True)
    coefficient_stability = summarize_coefficients(coefficients)
    bootstrap = bootstrap_clustered_metrics(oof, config)
    contract = build_model_contract(config, dataset, features, group_column)
    comparison = compare_historical_metrics(project_root, config, metrics, bootstrap)
    audit = build_audit(dataset, oof, isolation, features, group_column)
    frames = {
        "grouped_validation_model_contract": contract,
        "grouped_validation_oof_predictions": oof,
        "grouped_validation_metrics": metrics,
        "grouped_validation_fold_metrics": fold_metrics,
        "group_isolation_audit": isolation,
        "grouped_validation_coefficient_stability": coefficient_stability,
        "grouped_validation_bootstrap_ci": bootstrap,
        "grouped_validation_comparison": comparison,
        "grouped_validation_audit": audit,
    }
    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs = write_dataframe_outputs(
            frames,
            project_root / OUTPUT_DIR,
            force=force,
            formats=("csv", "parquet"),
        )
    primary_metrics = metrics[metrics["validation_scheme"] == "stratified_group_kfold"].iloc[0]
    summary = {
        "candidate_id": config["candidate_id"],
        "model_rows": len(dataset),
        "groups": int(dataset["resolved_group_id"].nunique()),
        "group_column": group_column,
        "features": len(features),
        "macro_f1": float(primary_metrics["macro_f1"]),
        "balanced_accuracy": float(primary_metrics["balanced_accuracy"]),
        "recall_B": float(primary_metrics["recall_B"]),
        "group_overlap_count": int(isolation["group_overlap_count"].sum()),
        "status": str(audit.iloc[0]["status"]),
    }
    return frames, outputs, summary


def load_candidate_dataset(
    project_root: Path,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, list[str], str]:
    predictions = read_table(project_root / config["candidate_predictions"])
    feature_set = read_table(project_root / config["candidate_feature_set"])
    source = read_table(project_root / config["input_dataset"])
    candidate_id = str(config["candidate_id"])
    predictions = predictions[predictions["candidate_id"].astype(str) == candidate_id].copy()
    feature_rows = feature_set[
        (feature_set["candidate_id"].astype(str) == candidate_id)
        & feature_set["feature_name"].notna()
        & feature_set["feature_name"].astype(str).ne("__feature_set_summary__")
    ]
    features = feature_rows["feature_name"].astype(str).drop_duplicates().tolist()
    missing = sorted(set(features) - set(source.columns))
    if missing:
        raise ValueError(f"Candidate features missing from source dataset: {missing}")
    ids = predictions["round_feature_id"].astype(str)
    dataset = source[source["round_feature_id"].astype(str).isin(set(ids))].copy()
    dataset = dataset.drop_duplicates("round_feature_id").set_index("round_feature_id").loc[ids].reset_index()
    dataset["label"] = predictions["true_label"].astype(str).to_numpy()
    group_column = next(
        (
            column
            for column in config.get("group_priority", ["series_id", "parse_id"])
            if column in dataset.columns and dataset[column].notna().all() and dataset[column].astype(str).ne("").all()
        ),
        None,
    )
    if group_column is None:
        raise ValueError("No complete group column is available for grouped validation.")
    dataset["resolved_group_id"] = dataset[group_column].astype(str)
    if dataset["label"].nunique() != 2:
        raise ValueError("Grouped validation requires both A and B labels.")
    return dataset, features, group_column


def build_pipeline(config: dict[str, Any]) -> Pipeline:
    params = config["model"]
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy=str(params.get("imputer", "median")))),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    class_weight=params.get("class_weight", "balanced"),
                    max_iter=int(params.get("max_iter", 2000)),
                    random_state=int(params.get("random_state", 42)),
                ),
            ),
        ]
    )


def evaluate_scheme(
    dataset: pd.DataFrame,
    features: list[str],
    config: dict[str, Any],
    *,
    scheme: str,
    group_column: str,
) -> dict[str, pd.DataFrame]:
    x = dataset[features].apply(pd.to_numeric, errors="coerce")
    y = dataset["label"].astype(str)
    groups = dataset["resolved_group_id"].astype(str)
    if scheme == "stratified_group_kfold":
        cfg = config["primary_validation"]
        splitter = StratifiedGroupKFold(
            n_splits=min(int(cfg.get("n_splits", 5)), int(groups.nunique())),
            shuffle=bool(cfg.get("shuffle", True)),
            random_state=int(cfg.get("random_state", 42)),
        )
    elif scheme == "leave_one_group_out":
        splitter = LeaveOneGroupOut()
    else:
        raise ValueError(f"Unsupported validation scheme: {scheme}")

    predictions = []
    fold_rows = []
    isolation_rows = []
    coefficient_rows = []
    threshold = float(config.get("probability_threshold", 0.5))
    for fold_id, (train_index, test_index) in enumerate(splitter.split(x, y, groups), start=1):
        train_groups = set(groups.iloc[train_index])
        test_groups = set(groups.iloc[test_index])
        overlap = sorted(train_groups & test_groups)
        if y.iloc[train_index].nunique() < 2:
            raise ValueError(f"Fold {fold_id}/{scheme} has a single training class.")
        model = build_pipeline(config).fit(x.iloc[train_index], y.iloc[train_index])
        probabilities = model.predict_proba(x.iloc[test_index])
        classes = list(model.named_steps["model"].classes_)
        proba_b = probabilities[:, classes.index("B")]
        predicted = np.where(proba_b >= threshold, "B", "A")
        fold = dataset.iloc[test_index][
            ["round_feature_id", "round_id", "parse_id", "series_id", "resolved_group_id", "opponent", "round_num"]
        ].copy()
        fold["candidate_id"] = config["candidate_id"]
        fold["validation_scheme"] = scheme
        fold["fold_id"] = fold_id
        fold["true_label"] = y.iloc[test_index].to_numpy()
        fold["predicted_label"] = predicted
        fold["predicted_proba_B"] = proba_b
        fold["predicted_proba_A"] = 1.0 - proba_b
        fold["is_correct"] = fold["true_label"] == fold["predicted_label"]
        predictions.append(fold)
        fold_rows.append(
            {
                "candidate_id": config["candidate_id"],
                "validation_scheme": scheme,
                "fold_id": fold_id,
                "held_out_groups": "|".join(sorted(test_groups)),
                **metric_values(fold["true_label"], fold["predicted_label"], fold["predicted_proba_B"]),
            }
        )
        isolation_rows.append(
            {
                "candidate_id": config["candidate_id"],
                "validation_scheme": scheme,
                "fold_id": fold_id,
                "group_column": group_column,
                "train_rounds": len(train_index),
                "test_rounds": len(test_index),
                "train_groups": len(train_groups),
                "test_groups": len(test_groups),
                "group_overlap_count": len(overlap),
                "overlap_groups": "|".join(overlap),
                "status": "passed" if not overlap else "failed",
            }
        )
        coefficients = model.named_steps["model"].coef_[0]
        coefficient_rows.extend(
            {
                "candidate_id": config["candidate_id"],
                "validation_scheme": scheme,
                "fold_id": fold_id,
                "feature_name": feature,
                "standardized_coefficient": float(coefficient),
            }
            for feature, coefficient in zip(features, coefficients, strict=True)
        )
    oof = pd.concat(predictions, ignore_index=True)
    overall = pd.DataFrame(
        [
            {
                "candidate_id": config["candidate_id"],
                "validation_scheme": scheme,
                "group_column": group_column,
                "n_splits": int(oof["fold_id"].nunique()),
                **metric_values(oof["true_label"], oof["predicted_label"], oof["predicted_proba_B"]),
            }
        ]
    )
    return {
        "oof": oof,
        "fold_metrics": pd.DataFrame(fold_rows),
        "metrics": overall,
        "isolation": pd.DataFrame(isolation_rows),
        "coefficients": pd.DataFrame(coefficient_rows),
    }


def metric_values(y_true: Iterable[str], y_pred: Iterable[str], proba_b: Iterable[float]) -> dict[str, Any]:
    truth = pd.Series(y_true).astype(str).reset_index(drop=True)
    predicted = pd.Series(y_pred).astype(str).reset_index(drop=True)
    probability = pd.Series(proba_b, dtype=float).reset_index(drop=True).clip(1e-15, 1 - 1e-15)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        precision, recall, f1, support = precision_recall_fscore_support(
            truth,
            predicted,
            labels=["A", "B"],
            zero_division=0,
        )
        matrix = confusion_matrix(truth, predicted, labels=["A", "B"])
        binary = truth.eq("B").astype(int)
        accuracy = float(accuracy_score(truth, predicted))
        balanced = float(balanced_accuracy_score(truth, predicted))
        macro_f1 = float(f1_score(truth, predicted, labels=["A", "B"], average="macro", zero_division=0))
        roc_auc = safe_metric(roc_auc_score, binary, probability)
        average_precision = safe_metric(average_precision_score, binary, probability)
        matthews = float(matthews_corrcoef(truth, predicted))
    return {
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
        "macro_f1": macro_f1,
        "precision_A": float(precision[0]),
        "precision_B": float(precision[1]),
        "recall_A": float(recall[0]),
        "recall_B": float(recall[1]),
        "f1_A": float(f1[0]),
        "f1_B": float(f1[1]),
        "support_A": int(support[0]),
        "support_B": int(support[1]),
        "A_predicted_as_B": int(matrix[0, 1]),
        "B_predicted_as_A": int(matrix[1, 0]),
        "roc_auc": roc_auc,
        "average_precision": average_precision,
        "brier_score": float(brier_score_loss(binary, probability)),
        "log_loss": float(log_loss(binary, probability, labels=[0, 1])),
        "matthews_correlation": matthews,
    }


def safe_metric(function: Any, truth: pd.Series, probability: pd.Series) -> float:
    try:
        return float(function(truth, probability))
    except ValueError:
        return float("nan")


def summarize_coefficients(coefficients: pd.DataFrame) -> pd.DataFrame:
    if coefficients.empty:
        return coefficients
    return (
        coefficients.groupby(["candidate_id", "validation_scheme", "feature_name"])["standardized_coefficient"]
        .agg(
            mean_standardized_coefficient="mean",
            std_standardized_coefficient="std",
            min_standardized_coefficient="min",
            max_standardized_coefficient="max",
            fold_count="count",
        )
        .reset_index()
        .assign(
            sign_stability=lambda frame: np.where(
                frame["min_standardized_coefficient"] * frame["max_standardized_coefficient"] >= 0,
                "stable_sign",
                "sign_flip",
            )
        )
    )


def bootstrap_clustered_metrics(oof: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    cfg = config["bootstrap"]
    rng = np.random.default_rng(int(cfg.get("random_state", 42)))
    resamples = int(cfg.get("resamples", 2000))
    confidence = float(cfg.get("confidence_level", 0.95))
    rows = []
    for scheme, frame in oof.groupby("validation_scheme"):
        group_ids = frame["resolved_group_id"].astype(str).unique()
        truth = frame["true_label"].astype(str).eq("B").to_numpy(dtype=bool)
        predicted = frame["predicted_label"].astype(str).eq("B").to_numpy(dtype=bool)
        probability = frame["predicted_proba_B"].to_numpy(dtype=float)
        positions = frame.reset_index(drop=True).groupby("resolved_group_id").indices
        samples = []
        for _ in range(resamples):
            sampled_groups = rng.choice(group_ids, size=len(group_ids), replace=True)
            sampled_positions = np.concatenate([positions[group_id] for group_id in sampled_groups])
            samples.append(
                fast_bootstrap_metrics(
                    truth[sampled_positions],
                    predicted[sampled_positions],
                    probability[sampled_positions],
                )
            )
        sampled_metrics = pd.DataFrame(samples)
        estimates = metric_values(frame["true_label"], frame["predicted_label"], frame["predicted_proba_B"])
        alpha = (1.0 - confidence) / 2.0
        for metric in ("macro_f1", "balanced_accuracy", "recall_B", "roc_auc", "average_precision", "brier_score"):
            rows.append(
                {
                    "candidate_id": config["candidate_id"],
                    "validation_scheme": scheme,
                    "metric": metric,
                    "estimate": estimates[metric],
                    "ci_low": float(sampled_metrics[metric].quantile(alpha)),
                    "ci_high": float(sampled_metrics[metric].quantile(1.0 - alpha)),
                    "confidence_level": confidence,
                    "resamples": resamples,
                    "clustered_by": "resolved_group_id",
                }
            )
    return pd.DataFrame(rows)


def fast_bootstrap_metrics(truth: np.ndarray, predicted: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    tp = int(np.sum(truth & predicted))
    tn = int(np.sum(~truth & ~predicted))
    fp = int(np.sum(~truth & predicted))
    fn = int(np.sum(truth & ~predicted))
    recall_a = tn / (tn + fp) if tn + fp else 0.0
    recall_b = tp / (tp + fn) if tp + fn else 0.0
    precision_a = tn / (tn + fn) if tn + fn else 0.0
    precision_b = tp / (tp + fp) if tp + fp else 0.0
    f1_a = 2 * precision_a * recall_a / (precision_a + recall_a) if precision_a + recall_a else 0.0
    f1_b = 2 * precision_b * recall_b / (precision_b + recall_b) if precision_b + recall_b else 0.0
    return {
        "macro_f1": (f1_a + f1_b) / 2,
        "balanced_accuracy": (recall_a + recall_b) / 2,
        "recall_B": recall_b,
        "roc_auc": fast_roc_auc(truth, probability),
        "average_precision": fast_average_precision(truth, probability),
        "brier_score": float(np.mean((probability - truth.astype(float)) ** 2)),
    }


def fast_roc_auc(truth: np.ndarray, probability: np.ndarray) -> float:
    positives = int(truth.sum())
    negatives = len(truth) - positives
    if positives == 0 or negatives == 0:
        return math.nan
    order = np.argsort(probability, kind="stable")
    ranks = np.empty(len(probability), dtype=float)
    ranks[order] = np.arange(1, len(probability) + 1)
    sorted_probability = probability[order]
    start = 0
    while start < len(sorted_probability):
        end = start + 1
        while end < len(sorted_probability) and sorted_probability[end] == sorted_probability[start]:
            end += 1
        if end - start > 1:
            ranks[order[start:end]] = ranks[order[start:end]].mean()
        start = end
    return float((ranks[truth].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def fast_average_precision(truth: np.ndarray, probability: np.ndarray) -> float:
    positives = int(truth.sum())
    if positives == 0:
        return math.nan
    order = np.argsort(-probability, kind="stable")
    ordered_truth = truth[order]
    precision_at_rank = np.cumsum(ordered_truth) / np.arange(1, len(truth) + 1)
    return float(precision_at_rank[ordered_truth].sum() / positives)


def build_model_contract(
    config: dict[str, Any],
    dataset: pd.DataFrame,
    features: list[str],
    group_column: str,
) -> pd.DataFrame:
    params = config["model"]
    return pd.DataFrame(
        [
            {
                "validation_id": config["validation_id"],
                "candidate_id": config["candidate_id"],
                "prediction_task": "P(site B | Vitality is T and plants, information through 35s)",
                "observation_unit": "round",
                "population": "Vitality Mirage T-side planted rounds with high-confidence A/B labels",
                "model": "median imputation -> standard scaling -> balanced logistic regression",
                "model_parameters": f"class_weight={params.get('class_weight')}; max_iter={params.get('max_iter')}; random_state={params.get('random_state')}",
                "feature_count": len(features),
                "feature_names": "|".join(features),
                "row_count": len(dataset),
                "group_column": group_column,
                "group_count": int(dataset["resolved_group_id"].nunique()),
                "primary_validation": "StratifiedGroupKFold",
                "sensitivity_validation": "LeaveOneGroupOut",
                "positive_class": config.get("positive_class", "B"),
                "probability_threshold": config.get("probability_threshold", 0.5),
                "intended_use": "exploratory tactical pattern analysis; not causal or live decision automation",
                "known_limitations": "small sample|single team|single map|no external validation|conditional on eventual plant",
            }
        ]
    )


def compare_historical_metrics(
    project_root: Path,
    config: dict[str, Any],
    grouped_metrics: pd.DataFrame,
    bootstrap: pd.DataFrame,
) -> pd.DataFrame:
    historical_path = project_root / "data/gold/modeling/t_side_ab_candidate/candidate_model_metrics.parquet"
    historical = read_table(historical_path)
    historical = historical[historical["candidate_id"].astype(str) == str(config["candidate_id"])].iloc[0]
    primary = grouped_metrics[grouped_metrics["validation_scheme"] == "stratified_group_kfold"].iloc[0]
    ci = bootstrap[
        (bootstrap["validation_scheme"] == "stratified_group_kfold") & (bootstrap["metric"] == "macro_f1")
    ].iloc[0]
    return pd.DataFrame(
        [
            {
                "candidate_id": config["candidate_id"],
                "historical_validation": "StratifiedKFold_by_round",
                "historical_macro_f1": historical["macro_f1"],
                "grouped_validation": "StratifiedGroupKFold_by_series",
                "grouped_macro_f1": primary["macro_f1"],
                "delta_macro_f1": float(primary["macro_f1"] - historical["macro_f1"]),
                "grouped_macro_f1_ci_low": ci["ci_low"],
                "grouped_macro_f1_ci_high": ci["ci_high"],
                "historical_recall_B": historical["recall_B"],
                "grouped_recall_B": primary["recall_B"],
                "historical_B_predicted_as_A": historical["B_predicted_as_A"],
                "grouped_B_predicted_as_A": primary["B_predicted_as_A"],
                "interpretation": "grouped estimate replaces round-level CV for statistical claims; historical result remains reproducible",
            }
        ]
    )


def build_audit(
    dataset: pd.DataFrame,
    oof: pd.DataFrame,
    isolation: pd.DataFrame,
    features: list[str],
    group_column: str,
) -> pd.DataFrame:
    scheme_counts = oof.groupby("validation_scheme")["round_feature_id"].nunique()
    expected_schemes = {"stratified_group_kfold", "leave_one_group_out"}
    complete = expected_schemes.issubset(set(scheme_counts.index)) and all(
        int(scheme_counts.get(scheme, 0)) == len(dataset) for scheme in expected_schemes
    )
    isolated = bool((isolation["group_overlap_count"] == 0).all())
    return pd.DataFrame(
        [
            {
                "validation_unit": "series_id_or_parse_id_fallback",
                "resolved_group_column": group_column,
                "model_rows": len(dataset),
                "unique_groups": int(dataset["resolved_group_id"].nunique()),
                "selected_features": len(features),
                "both_classes_present": bool(dataset["label"].nunique() == 2),
                "all_schemes_have_complete_oof": complete,
                "all_folds_group_isolated": isolated,
                "group_overlap_count": int(isolation["group_overlap_count"].sum()),
                "status": "passed" if complete and isolated else "failed",
                "candidate_conclusion": "group-isolated internal validation complete; external validation still required",
            }
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Revalidate the frozen Mirage A/B candidate with group-isolated folds.")
    parser.add_argument("--config", type=Path, default=Path("configs/modeling/mirage_ab_grouped_validation.yaml"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    _, outputs, summary = run_grouped_validation(
        args.config,
        project_root=args.project_root.resolve(),
        force=args.force,
        dry_run=args.dry_run,
    )
    print({**summary, "outputs": {key: str(value) for key, value in outputs.items()}})


if __name__ == "__main__":
    main()
