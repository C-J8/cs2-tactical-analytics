from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.config.schemas import load_project_config
from src.modeling.build_map_ab_dataset import run_build_map_ab_dataset
from src.utils.io import ensure_dir, read_optional_table, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.notebooks import code, md, write_notebook as write_notebook_file
from src.utils.reports import now_utc


warnings.filterwarnings("ignore", message="'penalty' was deprecated.*", category=FutureWarning)

OUTPUT_NAMES = [
    "inferno_ab_model_dataset",
    "inferno_ab_label_audit",
    "inferno_ab_group_audit",
    "inferno_ab_feature_leakage_audit",
    "inferno_ab_horizon_audit",
    "inferno_ab_feature_set_audit",
    "inferno_ab_dummy_baselines",
    "inferno_ab_oof_predictions",
    "inferno_ab_fold_metrics",
    "inferno_ab_oof_metrics",
    "inferno_ab_metric_uncertainty",
    "inferno_ab_null_permutation",
    "inferno_ab_null_summary",
    "inferno_ab_coefficient_stability",
    "inferno_ab_model_stability",
    "inferno_ab_demo_performance",
    "inferno_ab_confidence_audit",
    "inferno_ab_error_analysis",
    "inferno_ab_feature_set_comparison",
    "inferno_ab_eda_context_audit",
    "inferno_ab_full_fit_coefficients",
    "inferno_ab_experiment_fingerprint",
    "inferno_ab_read_only_audit",
    "inferno_ab_exploratory_model_audit",
]
LABELS = ["A", "B"]


def run_inferno_ab_exploratory_baseline(
    *,
    config_path: Path,
    model_config_path: Path,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    config_path = config_path.resolve()
    project_root = config_path.parent.parent
    project = load_project_config(config_path)
    gold_dir = (project_root / project.parsed_silver_dir).parent.parent / "gold"
    model_config = load_model_config(model_config_path)
    experiment = model_config["experiment"]
    output_dir = gold_dir / "modeling" / str(experiment.get("output_subdir", "inferno_ab_exploratory"))
    upstream_before = capture_upstream_fingerprints(project_root, gold_dir)

    frames, _, dataset_summary = run_build_map_ab_dataset(
        config_path=config_path,
        model_config_path=model_config_path,
        target_map=str(experiment["target_map"]),
        target_team=str(experiment["target_team"]),
        force=force,
        dry_run=True,
    )
    dataset = frames["inferno_ab_model_dataset"]
    feature_set_audit = frames["inferno_ab_feature_set_audit"]
    primary_features = feature_set_audit.loc[feature_set_audit["included"], "feature_name"].astype(str).tolist()
    validation_audit = validate_logo_feasibility(dataset)
    if not bool(validation_audit["experiment_allowed"].all()):
        raise ValueError("Inferno A/B exploratory experiment is blocked by group validation feasibility.")

    primary = evaluate_feature_set(dataset, primary_features, model_config, "compact_tactical_35s")
    dummies = evaluate_dummy_baselines(dataset, primary_features, model_config)
    null_perm = run_null_permutation(dataset, primary_features, model_config)
    null_summary = build_null_summary(primary["oof_metrics"], null_perm)
    uncertainty = bootstrap_metric_uncertainty(primary["oof_predictions"], model_config)
    full_fit = fit_pipeline(dataset[primary_features], dataset["label"], model_config)
    full_coefficients = full_fit_coefficients(full_fit, primary_features)
    write_model_artifact(full_fit, primary_features, dataset, model_config, output_dir, force=force, dry_run=dry_run)

    ablations = evaluate_ablations(dataset, feature_set_audit, model_config, null_summary)
    eda_context = build_eda_context_audit(feature_set_audit, gold_dir)
    confidence = build_confidence_audit(primary["oof_predictions"])
    errors = build_error_analysis(primary["oof_predictions"], dataset)
    demo_performance = build_demo_performance(primary["oof_predictions"], dataset)
    stability = build_model_stability(primary["fold_metrics"], primary["coefficient_stability"], uncertainty)
    fingerprint = build_experiment_fingerprint(dataset, primary["oof_predictions"], primary_features, model_config)
    upstream_after = capture_upstream_fingerprints(project_root, gold_dir)
    read_only = build_read_only_audit(upstream_before, upstream_after)
    signal_status = classify_signal(primary["oof_metrics"], dummies, null_summary, primary["fold_metrics"], uncertainty)
    exploratory_audit = build_model_audit(
        dataset_summary,
        primary_features,
        primary["oof_metrics"],
        null_summary,
        uncertainty,
        read_only,
        signal_status,
        model_config,
    )

    frames.update(
        {
            "inferno_ab_dummy_baselines": dummies,
            "inferno_ab_oof_predictions": primary["oof_predictions"],
            "inferno_ab_fold_metrics": primary["fold_metrics"],
            "inferno_ab_oof_metrics": primary["oof_metrics"],
            "inferno_ab_metric_uncertainty": uncertainty,
            "inferno_ab_null_permutation": null_perm,
            "inferno_ab_null_summary": null_summary,
            "inferno_ab_coefficient_stability": primary["coefficient_stability"],
            "inferno_ab_model_stability": stability,
            "inferno_ab_demo_performance": demo_performance,
            "inferno_ab_confidence_audit": confidence,
            "inferno_ab_error_analysis": errors,
            "inferno_ab_feature_set_comparison": ablations,
            "inferno_ab_eda_context_audit": eda_context,
            "inferno_ab_full_fit_coefficients": full_coefficients,
            "inferno_ab_experiment_fingerprint": pd.DataFrame(
                [
                    {
                        "experiment_id": experiment["experiment_id"],
                        "model_id": experiment["model_id"],
                        "logical_fingerprint": fingerprint,
                        "created_at": now_utc(),
                        "status": "ok",
                    }
                ]
            ),
            "inferno_ab_read_only_audit": read_only,
            "inferno_ab_exploratory_model_audit": exploratory_audit,
        }
    )
    ordered = {name: frames.get(name, pd.DataFrame()) for name in OUTPUT_NAMES}
    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs = write_dataframe_outputs(ordered, output_dir, force=force)
        write_report(project_root / "docs" / "inferno_ab_exploratory_baseline.md", ordered, model_config, force=force)
        write_notebook(project_root / "notebooks" / "27_inferno_ab_exploratory_baseline.ipynb", force=force)
    summary = {
        "rows": len(dataset),
        "a_count": int(dataset["label"].eq("A").sum()),
        "b_count": int(dataset["label"].eq("B").sum()),
        "groups": int(dataset["model_group_id"].nunique()),
        "feature_count": len(primary_features),
        "macro_f1": float(primary["oof_metrics"].iloc[0]["macro_f1"]),
        "balanced_accuracy": float(primary["oof_metrics"].iloc[0]["balanced_accuracy"]),
        "signal_status": signal_status,
        "ready_for_stage_8_12": bool(exploratory_audit.iloc[0]["ready_for_stage_8_12"]),
    }
    return ordered, outputs, summary


def load_model_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def fit_pipeline(x: pd.DataFrame, y: pd.Series, model_config: dict[str, Any]) -> Pipeline:
    params = model_config["model"]
    pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    penalty=str(params.get("penalty", "l2")),
                    C=float(params.get("C", 0.1)),
                    solver=str(params.get("solver", "liblinear")),
                    max_iter=int(params.get("max_iter", 5000)),
                    class_weight=params.get("class_weight"),
                    random_state=int(params.get("random_state", 811)),
                ),
            ),
        ]
    )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="'penalty' was deprecated.*", category=FutureWarning)
        return pipeline.fit(x, y)


def evaluate_feature_set(dataset: pd.DataFrame, features: list[str], model_config: dict[str, Any], feature_set_id: str) -> dict[str, pd.DataFrame]:
    x = dataset[features].copy()
    y = dataset["label"].astype(str)
    groups = dataset["model_group_id"].astype(str)
    logo = LeaveOneGroupOut()
    predictions = []
    folds = []
    coefficients = []
    threshold = float(model_config["model"].get("threshold", 0.5))
    for fold_id, (train_idx, test_idx) in enumerate(logo.split(x, y, groups), start=1):
        y_train = y.iloc[train_idx]
        y_test = y.iloc[test_idx]
        if y_train.nunique() < 2:
            continue
        model = fit_pipeline(x.iloc[train_idx], y_train, model_config)
        proba = model.predict_proba(x.iloc[test_idx])
        classes = list(model.named_steps["model"].classes_)
        proba_a = proba[:, classes.index("A")] if "A" in classes else np.zeros(len(test_idx))
        proba_b = proba[:, classes.index("B")] if "B" in classes else np.zeros(len(test_idx))
        pred = np.where(proba_b >= threshold, "B", "A")
        fold_frame = dataset.iloc[test_idx][["round_feature_id", "round_id", "parse_id", "series_id", "model_group_id"]].copy()
        fold_frame["feature_set_id"] = feature_set_id
        fold_frame["fold_id"] = fold_id
        fold_frame["true_label"] = y_test.to_numpy()
        fold_frame["predicted_label"] = pred
        fold_frame["predicted_proba_A"] = proba_a
        fold_frame["predicted_proba_B"] = proba_b
        fold_frame["prediction_confidence"] = np.maximum(proba_a, proba_b)
        fold_frame["is_correct"] = fold_frame["true_label"].eq(fold_frame["predicted_label"])
        predictions.append(fold_frame)
        folds.append(metrics_row(y_test, pd.Series(pred), feature_set_id=feature_set_id, fold_id=fold_id, heldout_group=groups.iloc[test_idx].iloc[0]))
        coefficients.append(coefficient_frame(model, features, fold_id=fold_id, feature_set_id=feature_set_id))
    oof = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
    return {
        "oof_predictions": oof,
        "fold_metrics": pd.DataFrame(folds),
        "oof_metrics": pd.DataFrame([metrics_row(oof["true_label"], oof["predicted_label"], feature_set_id=feature_set_id, fold_id=None, heldout_group=None)]),
        "coefficient_stability": coefficient_stability(pd.concat(coefficients, ignore_index=True) if coefficients else pd.DataFrame(), features, feature_set_id),
    }


def evaluate_dummy_baselines(dataset: pd.DataFrame, features: list[str], model_config: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for strategy in ["most_frequent", "stratified"]:
        predictions = []
        x = dataset[features]
        y = dataset["label"].astype(str)
        groups = dataset["model_group_id"].astype(str)
        for fold_id, (train_idx, test_idx) in enumerate(LeaveOneGroupOut().split(x, y, groups), start=1):
            dummy = DummyClassifier(strategy=strategy, random_state=int(model_config["model"].get("random_state", 811)))
            dummy.fit(x.iloc[train_idx], y.iloc[train_idx])
            pred = dummy.predict(x.iloc[test_idx])
            fold = metrics_row(y.iloc[test_idx], pd.Series(pred), feature_set_id=strategy, fold_id=fold_id, heldout_group=groups.iloc[test_idx].iloc[0])
            fold["model_name"] = f"dummy_{strategy}"
            predictions.append(pd.DataFrame({"true_label": y.iloc[test_idx].to_numpy(), "predicted_label": pred}))
            rows.append(fold)
        joined = pd.concat(predictions, ignore_index=True)
        overall = metrics_row(joined["true_label"], joined["predicted_label"], feature_set_id=strategy, fold_id=None, heldout_group=None)
        overall["model_name"] = f"dummy_{strategy}"
        rows.append(overall)
    return pd.DataFrame(rows)


def run_null_permutation(dataset: pd.DataFrame, features: list[str], model_config: dict[str, Any]) -> pd.DataFrame:
    cfg = model_config["null_test"]
    rng = np.random.default_rng(int(cfg.get("random_state", 811)))
    rows = []
    for iteration in range(1, int(cfg.get("permutations", 1000)) + 1):
        shuffled = dataset.copy()
        labels = shuffled["label"].to_numpy(copy=True)
        if bool(cfg.get("preserve_group_class_balance", True)):
            for group in shuffled["model_group_id"].astype(str).unique():
                idx = np.where(shuffled["model_group_id"].astype(str).to_numpy() == group)[0]
                labels[idx] = rng.permutation(labels[idx])
        else:
            labels = rng.permutation(labels)
        shuffled["label"] = labels
        evaluated = evaluate_feature_set(shuffled, features, model_config, "null_permutation")
        rows.append(
            {
                "permutation_id": iteration,
                "macro_f1": evaluated["oof_metrics"].iloc[0]["macro_f1"],
                "balanced_accuracy": evaluated["oof_metrics"].iloc[0]["balanced_accuracy"],
            }
        )
    return pd.DataFrame(rows)


def build_null_summary(oof_metrics: pd.DataFrame, null_perm: pd.DataFrame) -> pd.DataFrame:
    observed = float(oof_metrics.iloc[0]["macro_f1"])
    values = pd.to_numeric(null_perm["macro_f1"], errors="coerce")
    return pd.DataFrame(
        [
            {
                "observed_macro_f1": observed,
                "null_mean_macro_f1": float(values.mean()),
                "null_p05_macro_f1": float(values.quantile(0.05)),
                "null_p50_macro_f1": float(values.quantile(0.50)),
                "null_p95_macro_f1": float(values.quantile(0.95)),
                "observed_percentile": float((values <= observed).mean()),
                "p_value_greater_equal": float((values >= observed).mean()),
                "permutations": len(null_perm),
                "status": "ok",
            }
        ]
    )


def bootstrap_metric_uncertainty(oof: pd.DataFrame, model_config: dict[str, Any]) -> pd.DataFrame:
    cfg = model_config["bootstrap"]
    rng = np.random.default_rng(int(cfg.get("random_state", 811)))
    groups = oof["model_group_id"].astype(str).unique()
    metrics = []
    for _ in range(int(cfg.get("resamples", 2000))):
        sampled = rng.choice(groups, size=len(groups), replace=True)
        frame = pd.concat([oof[oof["model_group_id"].astype(str).eq(group)] for group in sampled], ignore_index=True)
        metrics.append(metric_values(frame["true_label"], frame["predicted_label"]))
    metric_frame = pd.DataFrame(metrics)
    alpha = (1.0 - float(cfg.get("confidence_level", 0.95))) / 2.0
    rows = []
    for metric in ["macro_f1", "balanced_accuracy", "recall_A", "recall_B"]:
        rows.append(
            {
                "metric": metric,
                "estimate": float(metric_values(oof["true_label"], oof["predicted_label"])[metric]),
                "ci_low": float(metric_frame[metric].quantile(alpha)),
                "ci_high": float(metric_frame[metric].quantile(1 - alpha)),
                "resamples": len(metric_frame),
                "clustered_by": "model_group_id",
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)


def metrics_row(y_true: pd.Series, y_pred: pd.Series, *, feature_set_id: str, fold_id: int | None, heldout_group: str | None) -> dict[str, Any]:
    values = metric_values(y_true, y_pred)
    values.update(
        {
            "feature_set_id": feature_set_id,
            "model_name": "logistic_regression",
            "fold_id": fold_id,
            "heldout_group": heldout_group,
            "support_A": int(pd.Series(y_true).astype(str).eq("A").sum()),
            "support_B": int(pd.Series(y_true).astype(str).eq("B").sum()),
            "status": "ok",
        }
    )
    return values


def metric_values(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    y_true = pd.Series(y_true).astype(str)
    y_pred = pd.Series(y_pred).astype(str)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "precision_A": float(precision_score(y_true, y_pred, labels=["A"], average="macro", zero_division=0)),
        "precision_B": float(precision_score(y_true, y_pred, labels=["B"], average="macro", zero_division=0)),
        "recall_A": float(recall_score(y_true, y_pred, labels=["A"], average="macro", zero_division=0)),
        "recall_B": float(recall_score(y_true, y_pred, labels=["B"], average="macro", zero_division=0)),
    }


def coefficient_frame(model: Pipeline, features: list[str], *, fold_id: int, feature_set_id: str) -> pd.DataFrame:
    coefs = model.named_steps["model"].coef_[0]
    return pd.DataFrame(
        {
            "feature_set_id": feature_set_id,
            "fold_id": fold_id,
            "feature_name": features,
            "coefficient": coefs,
            "coefficient_sign": np.sign(coefs),
        }
    )


def coefficient_stability(coefficients: pd.DataFrame, features: list[str], feature_set_id: str) -> pd.DataFrame:
    rows = []
    for feature in features:
        values = coefficients[coefficients["feature_name"].eq(feature)]["coefficient"]
        signs = np.sign(values)
        nonzero = signs[signs.ne(0)]
        dominant = int(nonzero.mode().iloc[0]) if not nonzero.empty else 0
        agreement = float((nonzero.eq(dominant).mean())) if not nonzero.empty else 0.0
        rows.append(
            {
                "feature_set_id": feature_set_id,
                "feature_name": feature,
                "folds": int(values.count()),
                "mean_coefficient": float(values.mean()),
                "std_coefficient": float(values.std(ddof=0)),
                "dominant_sign": dominant,
                "sign_agreement": agreement,
                "sign_flips": int((nonzero.ne(dominant)).sum()) if not nonzero.empty else 0,
                "status": "stable" if agreement >= 0.8 else "unstable",
            }
        )
    return pd.DataFrame(rows)


def full_fit_coefficients(model: Pipeline, features: list[str]) -> pd.DataFrame:
    coefs = model.named_steps["model"].coef_[0]
    rows = []
    for feature, coef in zip(features, coefs, strict=True):
        rows.append(
            {
                "feature_name": feature,
                "coefficient": float(coef),
                "abs_coefficient": float(abs(coef)),
                "direction_toward_class": "B" if coef > 0 else "A" if coef < 0 else "neutral",
            }
        )
    return pd.DataFrame(rows).sort_values("abs_coefficient", ascending=False)


def evaluate_ablations(dataset: pd.DataFrame, feature_set_audit: pd.DataFrame, model_config: dict[str, Any], null_summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    primary = str(model_config["feature_sets"].get("primary", "compact_tactical_35s"))
    sets = {primary: feature_set_audit.loc[feature_set_audit["included"], "feature_name"].astype(str).tolist()}
    sets.update(model_config["feature_sets"].get("ablations", {}))
    for feature_set_id, features in sets.items():
        features = [feature for feature in features if feature in dataset.columns and feature in set(feature_set_audit.loc[feature_set_audit["included"], "feature_name"])]
        if not features:
            continue
        evaluated = evaluate_feature_set(dataset, features, model_config, str(feature_set_id))
        metric = evaluated["oof_metrics"].iloc[0]
        rows.append(
            {
                "feature_set_id": feature_set_id,
                "feature_count": len(features),
                "macro_f1": metric["macro_f1"],
                "balanced_accuracy": metric["balanced_accuracy"],
                "recall_A": metric["recall_A"],
                "recall_B": metric["recall_B"],
                "null_percentile": null_summary.iloc[0]["observed_percentile"] if feature_set_id == primary else None,
                "fold_variability": float(evaluated["fold_metrics"]["macro_f1"].std(ddof=0)),
                "notes": "Primary predeclared model." if feature_set_id == primary else "Predeclared ablation for interpretation only.",
            }
        )
    return pd.DataFrame(rows)


def validate_logo_feasibility(dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    groups = dataset["model_group_id"].astype(str)
    y = dataset["label"].astype(str)
    valid = int(groups.nunique()) >= 3
    for fold_id, (train_idx, test_idx) in enumerate(LeaveOneGroupOut().split(dataset, y, groups), start=1):
        train_labels = y.iloc[train_idx]
        test_labels = y.iloc[test_idx]
        fold_ok = train_labels.nunique() == 2
        rows.append(
            {
                "fold_id": fold_id,
                "heldout_group": groups.iloc[test_idx].iloc[0],
                "training_has_both_classes": bool(fold_ok),
                "heldout_one_class": bool(test_labels.nunique() == 1),
                "experiment_allowed": bool(valid and fold_ok),
                "status": "ok" if valid and fold_ok else "failed",
            }
        )
    return pd.DataFrame(rows)


def build_eda_context_audit(feature_set_audit: pd.DataFrame, gold_dir: Path) -> pd.DataFrame:
    context = read_optional(gold_dir / "analysis" / "tactical_finding_hardening" / "modeling_context_findings.parquet")
    features = set(context.get("representative_feature", pd.Series(dtype=object)).dropna().astype(str))
    ranks = read_optional(gold_dir / "analysis" / "tactical_finding_hardening" / "hardened_tactical_finding_ranking.parquet")
    rank_lookup = ranks.set_index("representative_feature")["rank"].to_dict() if "representative_feature" in ranks.columns and "rank" in ranks.columns else {}
    rows = []
    for _, row in feature_set_audit.iterrows():
        feature = str(row["feature_name"])
        rows.append(
            {
                "feature_name": feature,
                "appears_in_hardened_findings": feature in features,
                "finding_concept_id": None,
                "finding_rank": rank_lookup.get(feature),
                "included_in_model": bool(row["included"]),
                "model_inclusion_reason": "predeclared_contract_horizon_quality" if row["included"] else row["exclusion_reason"],
                "selection_was_label_driven": False,
            }
        )
    return pd.DataFrame(rows)


def build_confidence_audit(oof: pd.DataFrame) -> pd.DataFrame:
    bins = pd.cut(oof["prediction_confidence"], bins=[0.0, 0.55, 0.65, 0.75, 0.85, 1.0], include_lowest=True)
    rows = []
    for bucket, group in oof.groupby(bins, observed=True):
        rows.append(
            {
                "confidence_bin": str(bucket),
                "rows": len(group),
                "accuracy": float(group["is_correct"].mean()),
                "mean_confidence": float(group["prediction_confidence"].mean()),
                "errors": int((~group["is_correct"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def build_error_analysis(oof: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    merged = oof.merge(dataset[["round_feature_id", "map_name", "target_team"]], on="round_feature_id", how="left")
    errors = merged[~merged["is_correct"]].copy()
    if errors.empty:
        return pd.DataFrame(columns=["error_type", "rows", "mean_confidence", "demos", "notes"])
    errors["error_type"] = errors["true_label"] + "_predicted_as_" + errors["predicted_label"]
    return (
        errors.groupby("error_type")
        .agg(rows=("round_feature_id", "count"), mean_confidence=("prediction_confidence", "mean"), demos=("parse_id", "nunique"))
        .reset_index()
        .assign(notes="Exploratory OOF errors; not tactical proof.")
    )


def build_demo_performance(oof: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group_id, group in oof.groupby("model_group_id"):
        metrics = metric_values(group["true_label"], group["predicted_label"])
        rows.append(
            {
                "model_group_id": group_id,
                "parse_id": group["parse_id"].iloc[0],
                "series_id": group["series_id"].iloc[0],
                "rounds": len(group),
                "a_count": int(group["true_label"].eq("A").sum()),
                "b_count": int(group["true_label"].eq("B").sum()),
                **metrics,
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)


def build_model_stability(fold_metrics: pd.DataFrame, coefficients: pd.DataFrame, uncertainty: pd.DataFrame) -> pd.DataFrame:
    macro = pd.to_numeric(fold_metrics["macro_f1"], errors="coerce")
    return pd.DataFrame(
        [
            {
                "folds": len(fold_metrics),
                "fold_macro_f1_min": float(macro.min()),
                "fold_macro_f1_max": float(macro.max()),
                "fold_macro_f1_std": float(macro.std(ddof=0)),
                "unstable_coefficients": int(coefficients["status"].eq("unstable").sum()),
                "macro_f1_ci_low": float(uncertainty[uncertainty["metric"].eq("macro_f1")]["ci_low"].iloc[0]),
                "macro_f1_ci_high": float(uncertainty[uncertainty["metric"].eq("macro_f1")]["ci_high"].iloc[0]),
                "status": "exploratory_only",
            }
        ]
    )


def classify_signal(
    oof_metrics: pd.DataFrame,
    dummies: pd.DataFrame,
    null_summary: pd.DataFrame,
    fold_metrics: pd.DataFrame,
    uncertainty: pd.DataFrame,
) -> str:
    macro = float(oof_metrics.iloc[0]["macro_f1"])
    dummy_best = float(dummies[dummies["fold_id"].isna()]["macro_f1"].max())
    percentile = float(null_summary.iloc[0]["observed_percentile"])
    fold_std = float(fold_metrics["macro_f1"].std(ddof=0))
    ci_low = float(uncertainty[uncertainty["metric"].eq("macro_f1")]["ci_low"].iloc[0])
    if macro <= dummy_best or percentile < 0.75:
        return "no_signal"
    if fold_std > 0.25 or ci_low < dummy_best:
        return "unstable_signal"
    if percentile < 0.90:
        return "weak_signal"
    return "exploratory_signal"


def build_model_audit(
    summary: dict[str, Any],
    features: list[str],
    oof_metrics: pd.DataFrame,
    null_summary: pd.DataFrame,
    uncertainty: pd.DataFrame,
    read_only: pd.DataFrame,
    signal_status: str,
    model_config: dict[str, Any],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "experiment_id": model_config["experiment"]["experiment_id"],
                "model_id": model_config["experiment"]["model_id"],
                "model_status": "exploratory_only",
                "target_map": model_config["experiment"]["target_map"],
                "target_team": model_config["experiment"]["target_team"],
                "target_side": model_config["experiment"]["target_side"],
                "horizon_seconds": model_config["prediction"]["primary_horizon_seconds"],
                "training_rows": summary["rows"],
                "a_count": summary["a_count"],
                "b_count": summary["b_count"],
                "groups": summary["unique_groups"],
                "feature_count": len(features),
                "features": "|".join(features),
                "macro_f1": float(oof_metrics.iloc[0]["macro_f1"]),
                "balanced_accuracy": float(oof_metrics.iloc[0]["balanced_accuracy"]),
                "null_percentile": float(null_summary.iloc[0]["observed_percentile"]),
                "macro_f1_ci_low": float(uncertainty[uncertainty["metric"].eq("macro_f1")]["ci_low"].iloc[0]),
                "macro_f1_ci_high": float(uncertainty[uncertainty["metric"].eq("macro_f1")]["ci_high"].iloc[0]),
                "exploratory_signal_status": signal_status,
                "upstream_unchanged": bool(read_only["unchanged"].all()),
                "ready_for_stage_8_12": bool(read_only["unchanged"].all()),
                "created_at": now_utc(),
                "limitations": "Small Inferno sample; group-aware exploratory model only; no promotion.",
            }
        ]
    )


def capture_upstream_fingerprints(project_root: Path, gold_dir: Path) -> pd.DataFrame:
    paths = [
        gold_dir / "round_features" / "round_features_t_side_planted.parquet",
        gold_dir / "round_features" / "round_features_t_side_all.parquet",
        gold_dir / "analysis" / "multi_map_tactical_eda" / "multi_map_tactical_eda_audit.parquet",
        gold_dir / "analysis" / "tactical_finding_hardening" / "tactical_finding_hardening_audit.parquet",
        project_root / "configs" / "features" / "feature_contract.yaml",
        project_root / "configs" / "maps" / "map_registry.yaml",
        project_root / "configs" / "maps" / "inferno.yaml",
        project_root / "configs" / "maps" / "mirage.yaml",
    ]
    rows = []
    for path in paths:
        rows.append({"artifact_path": str(path.relative_to(project_root)), "exists": path.exists(), "content_hash": file_hash(path) if path.exists() else None})
    return pd.DataFrame(rows)


def build_read_only_audit(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    merged = before.merge(after, on="artifact_path", suffixes=("_before", "_after"))
    merged["unchanged"] = merged["exists_before"].eq(merged["exists_after"]) & merged["content_hash_before"].eq(merged["content_hash_after"])
    merged["status"] = np.where(merged["unchanged"], "ok", "failed")
    return merged


def build_experiment_fingerprint(dataset: pd.DataFrame, oof: pd.DataFrame, features: list[str], model_config: dict[str, Any]) -> str:
    payload = {
        "dataset": json.loads(dataset.sort_values("round_feature_id").to_json(orient="records")),
        "oof": json.loads(oof.sort_values("round_feature_id").to_json(orient="records")),
        "features": features,
        "config": model_config,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def write_model_artifact(model: Pipeline, features: list[str], dataset: pd.DataFrame, model_config: dict[str, Any], output_dir: Path, *, force: bool, dry_run: bool) -> None:
    if dry_run:
        return
    ensure_dir(output_dir)
    model_path = output_dir / "inferno_ab_full_fit_model.pkl"
    metadata_path = output_dir / "inferno_ab_full_fit_model_metadata.json"
    if force or not model_path.exists():
        with model_path.open("wb") as handle:
            pickle.dump(model, handle)
    metadata = {
        "model_id": model_config["experiment"]["model_id"],
        "model_status": "exploratory_only",
        "map": model_config["experiment"]["target_map"],
        "team": model_config["experiment"]["target_team"],
        "side": model_config["experiment"]["target_side"],
        "label": model_config["experiment"]["label_column"],
        "horizon": model_config["prediction"]["primary_horizon_seconds"],
        "feature_set": model_config["feature_sets"]["primary"],
        "features": features,
        "training_rows": len(dataset),
        "class_balance": dataset["label"].value_counts().to_dict(),
        "grouping_strategy": "leave_one_group_out",
        "model_params": model_config["model"],
        "created_at": now_utc(),
        "limitations": "Exploratory only; not promoted or production.",
    }
    if force or not metadata_path.exists():
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def write_report(path: Path, frames: dict[str, pd.DataFrame], model_config: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        return
    ensure_dir(path.parent)
    audit = frames["inferno_ab_exploratory_model_audit"].iloc[0]
    label = frames["inferno_ab_label_audit"].iloc[0]
    group = frames["inferno_ab_group_audit"]
    oof = frames["inferno_ab_oof_metrics"].iloc[0]
    null = frames["inferno_ab_null_summary"].iloc[0]
    uncertainty = frames["inferno_ab_metric_uncertainty"]
    feature_audit = frames["inferno_ab_feature_set_audit"]
    sections = [
        "# Inferno A/B Exploratory Baseline",
        "",
        "## Purpose",
        "Estimate whether early-round Inferno features contain reproducible exploratory signal for Vitality T-side eventual A/B plant site.",
        "",
        "## Why This Is Exploratory",
        "The sample is small and validation is leave-one-series-out. The model is not promoted and is not a production artifact.",
        "",
        "## Dataset",
        f"Rows: {int(label['rows'])}. A/B: {int(label['a_count'])}/{int(label['b_count'])}. Groups: {int(group['model_group_id'].nunique())}.",
        "",
        "## Prediction Horizon",
        f"Primary horizon: {model_config['prediction']['primary_horizon_seconds']} seconds after freeze end, chosen from the historical Mirage 35s candidate context before Inferno modeling.",
        "",
        "## Leakage Rules",
        "Plant, outcome, label, raw coordinate, endpoint, and post-horizon features are excluded.",
        "",
        "## Feature Set",
        feature_audit[["feature_name", "family", "included", "exclusion_reason"]].fillna("").to_markdown(index=False),
        "",
        "## Validation Strategy",
        "Leave-one-series-out validation with preprocessing fitted only inside each training fold.",
        "",
        "## OOF Performance",
        f"Macro F1: {oof['macro_f1']:.3f}. Balanced accuracy: {oof['balanced_accuracy']:.3f}. Recall A/B: {oof['recall_A']:.3f}/{oof['recall_B']:.3f}.",
        "",
        "## Null Permutation Test",
        f"Observed macro F1 percentile: {null['observed_percentile']:.3f}; null median: {null['null_p50_macro_f1']:.3f}.",
        "",
        "## Metric Uncertainty",
        uncertainty.to_markdown(index=False),
        "",
        "## Exploratory Signal Assessment",
        f"Signal status: `{audit['exploratory_signal_status']}`. Model status: `{audit['model_status']}`.",
        "",
        "## Readiness",
        f"`ready_for_stage_8_12 = {bool(audit['ready_for_stage_8_12'])}`.",
    ]
    path.write_text("\n".join(sections), encoding="utf-8")


def write_notebook(path: Path, *, force: bool) -> None:
    cells = [
        md("# Stage 8.11 -- Inferno A/B Exploratory Baseline"),
        code("import pandas as pd\nfrom pathlib import Path\nbase = Path('../data/gold/modeling/inferno_ab_exploratory')"),
        code("dataset = pd.read_parquet(base / 'inferno_ab_model_dataset.parquet')\ndataset.shape"),
        code("dataset['label'].value_counts()"),
        code("pd.read_parquet(base / 'inferno_ab_group_audit.parquet')"),
        code("pd.read_parquet(base / 'inferno_ab_feature_set_audit.parquet')"),
        code("pd.read_parquet(base / 'inferno_ab_oof_metrics.parquet')"),
        code("pd.read_parquet(base / 'inferno_ab_fold_metrics.parquet')"),
        code(
            "import matplotlib.pyplot as plt\n"
            "oof = pd.read_parquet(base / 'inferno_ab_oof_predictions.parquet')\n"
            "cm = pd.crosstab(oof['true_label'], oof['predicted_label'])\n"
            "fig, ax = plt.subplots(figsize=(4, 4))\n"
            "ax.imshow(cm.reindex(index=['A','B'], columns=['A','B'], fill_value=0), cmap='Blues')\n"
            "ax.set_xticks([0,1], ['A','B'])\n"
            "ax.set_yticks([0,1], ['A','B'])\n"
            "ax.set_xlabel('Predicted')\n"
            "ax.set_ylabel('True')\n"
            "ax.set_title('OOF confusion matrix')\n"
            "for i in range(2):\n"
            "    for j in range(2):\n"
            "        ax.text(j, i, int(cm.reindex(index=['A','B'], columns=['A','B'], fill_value=0).iloc[i, j]), ha='center', va='center')\n"
            "plt.tight_layout()"
        ),
        code(
            "null = pd.read_parquet(base / 'inferno_ab_null_permutation.parquet')\n"
            "obs = pd.read_parquet(base / 'inferno_ab_oof_metrics.parquet').iloc[0]['macro_f1']\n"
            "fig, ax = plt.subplots(figsize=(7, 4))\n"
            "ax.hist(null['macro_f1'], bins=25, alpha=0.8)\n"
            "ax.axvline(obs, color='crimson', linewidth=2)\n"
            "ax.set_title('Exploratory null comparison')\n"
            "ax.set_xlabel('Permutation macro F1')\n"
            "plt.tight_layout()"
        ),
        code("pd.read_parquet(base / 'inferno_ab_coefficient_stability.parquet')"),
        code("pd.read_parquet(base / 'inferno_ab_exploratory_model_audit.parquet')"),
    ]
    write_notebook_file(path, cells, force=force)


def read_optional(path: Path) -> pd.DataFrame:
    return read_optional_table(path)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def print_summary(summary: dict[str, Any], outputs: dict[str, Path]) -> None:
    print("Inferno A/B exploratory baseline summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for key, value in outputs.items():
        print(f"- {key}: {value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Stage 8.11 Inferno A/B exploratory baseline.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_inferno_ab_exploratory_baseline(
        config_path=args.config,
        model_config_path=args.model_config,
        force=args.force,
        dry_run=args.dry_run,
    )
    print_summary(summary, outputs)


if __name__ == "__main__":
    main()
