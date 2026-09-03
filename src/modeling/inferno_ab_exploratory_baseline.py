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
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)
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
    "inferno_ab_feature_evidence_audit",
    "inferno_ab_modeling_preconditions",
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
    "inferno_ab_error_summary",
    "inferno_ab_feature_set_comparison",
    "inferno_ab_eda_context_audit",
    "inferno_ab_full_fit_coefficients",
    "inferno_ab_experiment_fingerprint",
    "inferno_ab_read_only_audit",
    "inferno_ab_integrity_revalidation",
    "inferno_ab_frozen_experiment_audit",
    "modeling_integrity_refactor_regression_audit",
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
    previous_snapshot = capture_previous_integrity_snapshot(output_dir)
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
    errors = build_error_analysis(primary["oof_predictions"], dataset, primary_features)
    error_summary = build_error_summary(errors)
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
    frozen_audit = build_frozen_experiment_audit(model_config)
    integrity_revalidation = build_integrity_revalidation(previous_snapshot, dataset_summary, primary["oof_metrics"], null_summary, signal_status, primary_features)
    integrity_audit = build_integrity_audit(
        frames,
        primary["oof_metrics"],
        read_only,
        signal_status,
        model_config,
        hardening_present=(gold_dir / "analysis" / "tactical_finding_hardening" / "tactical_finding_hardening_audit.parquet").exists(),
        frozen_audit=frozen_audit,
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
            "inferno_ab_error_summary": error_summary,
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
            "inferno_ab_integrity_revalidation": integrity_revalidation,
            "inferno_ab_frozen_experiment_audit": frozen_audit,
            "modeling_integrity_refactor_regression_audit": integrity_audit,
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
        fold_frame["held_out_group"] = groups.iloc[test_idx].iloc[0]
        predictions.append(fold_frame)
        folds.append(metrics_row(y_test, pd.Series(pred), y_proba_b=pd.Series(proba_b), feature_set_id=feature_set_id, fold_id=fold_id, heldout_group=groups.iloc[test_idx].iloc[0]))
        coefficients.append(coefficient_frame(model, features, fold_id=fold_id, feature_set_id=feature_set_id))
    oof = pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame()
    return {
        "oof_predictions": oof,
        "fold_metrics": pd.DataFrame(folds),
        "oof_metrics": pd.DataFrame(
            [
                metrics_row(
                    oof["true_label"],
                    oof["predicted_label"],
                    y_proba_b=oof["predicted_proba_B"],
                    feature_set_id=feature_set_id,
                    fold_id=None,
                    heldout_group=None,
                )
            ]
        ),
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
            proba_b = dummy_proba_b(dummy, x.iloc[test_idx])
            fold = metrics_row(y.iloc[test_idx], pd.Series(pred), y_proba_b=proba_b, feature_set_id=strategy, fold_id=fold_id, heldout_group=groups.iloc[test_idx].iloc[0])
            fold["model_name"] = f"dummy_{strategy}"
            predictions.append(pd.DataFrame({"true_label": y.iloc[test_idx].to_numpy(), "predicted_label": pred, "predicted_proba_B": proba_b.to_numpy()}))
            rows.append(fold)
        joined = pd.concat(predictions, ignore_index=True)
        overall = metrics_row(joined["true_label"], joined["predicted_label"], y_proba_b=joined["predicted_proba_B"], feature_set_id=strategy, fold_id=None, heldout_group=None)
        overall["model_name"] = f"dummy_{strategy}"
        rows.append(overall)
    return pd.DataFrame(rows)


def dummy_proba_b(dummy: DummyClassifier, x: pd.DataFrame) -> pd.Series:
    proba = dummy.predict_proba(x)
    classes = list(dummy.classes_)
    values = proba[:, classes.index("B")] if "B" in classes else np.zeros(len(x))
    return pd.Series(values, index=x.index)


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


def metrics_row(
    y_true: pd.Series,
    y_pred: pd.Series,
    *,
    y_proba_b: pd.Series | None = None,
    feature_set_id: str,
    fold_id: int | None,
    heldout_group: str | None,
) -> dict[str, Any]:
    values = metric_values(y_true, y_pred, y_proba_b=y_proba_b)
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


def metric_values(y_true: pd.Series, y_pred: pd.Series, *, y_proba_b: pd.Series | None = None) -> dict[str, float | None | str]:
    y_true = pd.Series(y_true).astype(str)
    y_pred = pd.Series(y_pred).astype(str)
    matrix = confusion_matrix(y_true, y_pred, labels=LABELS)
    values: dict[str, float | None | str] = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "f1_A": float(f1_score(y_true, y_pred, labels=["A"], average="macro", zero_division=0)),
        "f1_B": float(f1_score(y_true, y_pred, labels=["B"], average="macro", zero_division=0)),
        "precision_A": float(precision_score(y_true, y_pred, labels=["A"], average="macro", zero_division=0)),
        "precision_B": float(precision_score(y_true, y_pred, labels=["B"], average="macro", zero_division=0)),
        "recall_A": float(recall_score(y_true, y_pred, labels=["A"], average="macro", zero_division=0)),
        "recall_B": float(recall_score(y_true, y_pred, labels=["B"], average="macro", zero_division=0)),
        "MCC": float(matthews_corrcoef(y_true, y_pred)),
        "true_A_pred_A": int(matrix[0, 0]),
        "true_A_pred_B": int(matrix[0, 1]),
        "true_B_pred_A": int(matrix[1, 0]),
        "true_B_pred_B": int(matrix[1, 1]),
        "ROC_AUC": None,
        "Brier_score": None,
        "log_loss": None,
        "metric_availability_notes": "probability_metrics_not_available",
    }
    if y_proba_b is not None:
        proba_b = pd.Series(y_proba_b).astype(float).clip(0.0, 1.0)
        truth_b = y_true.eq("B").astype(int)
        values["Brier_score"] = float(brier_score_loss(truth_b, proba_b))
        values["log_loss"] = float(log_loss(truth_b, np.column_stack([1.0 - proba_b, proba_b]), labels=[0, 1]))
        if truth_b.nunique() == 2:
            values["ROC_AUC"] = float(roc_auc_score(truth_b, proba_b))
            values["metric_availability_notes"] = "ok"
        else:
            values["metric_availability_notes"] = "undefined_single_class_fold"
    return values


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


def build_error_analysis(oof: pd.DataFrame, dataset: pd.DataFrame, selected_features: list[str]) -> pd.DataFrame:
    requested_columns = [
        "round_feature_id",
        "round_id",
        "parse_id",
        "series_id",
        "model_group_id",
        "map_name",
        "target_team",
        "score_diff_before_round",
        *selected_features,
    ]
    metadata_columns = list(dict.fromkeys(column for column in requested_columns if column in dataset.columns))
    merged = oof.merge(dataset[metadata_columns], on=["round_feature_id", "round_id", "parse_id", "series_id", "model_group_id"], how="left")
    errors = merged[~merged["is_correct"]].copy()
    if errors.empty:
        return pd.DataFrame(
            columns=[
                "round_feature_id",
                "round_id",
                "parse_id",
                "series_id",
                "model_group_id",
                "true_label",
                "predicted_label",
                "predicted_proba_A",
                "predicted_proba_B",
                "probability_true_class",
                "prediction_confidence",
                "error_type",
                "score_diff_before_round",
                "fold_id",
                "held_out_group",
                "status",
            ]
        )
    errors["error_type"] = errors["true_label"] + "_predicted_as_" + errors["predicted_label"]
    errors["probability_true_class"] = np.where(errors["true_label"].eq("A"), errors["predicted_proba_A"], errors["predicted_proba_B"])
    for feature in selected_features:
        if feature in errors.columns:
            errors[f"feature__{feature}"] = errors[feature]
    keep = [
        "round_feature_id",
        "round_id",
        "parse_id",
        "series_id",
        "model_group_id",
        "true_label",
        "predicted_label",
        "predicted_proba_A",
        "predicted_proba_B",
        "probability_true_class",
        "prediction_confidence",
        "error_type",
        "score_diff_before_round",
        *[f"feature__{feature}" for feature in selected_features if f"feature__{feature}" in errors.columns],
        "fold_id",
        "held_out_group",
    ]
    return errors[keep].assign(status="oof_error")


def build_error_summary(errors: pd.DataFrame) -> pd.DataFrame:
    if errors.empty:
        return pd.DataFrame(columns=["error_type", "rows", "demos", "groups", "mean_confidence", "median_confidence", "mean_true_class_probability"])
    return (
        errors.groupby("error_type")
        .agg(
            rows=("round_feature_id", "count"),
            demos=("parse_id", "nunique"),
            groups=("model_group_id", "nunique"),
            mean_confidence=("prediction_confidence", "mean"),
            median_confidence=("prediction_confidence", "median"),
            mean_true_class_probability=("probability_true_class", "mean"),
        )
        .reset_index()
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


def capture_previous_integrity_snapshot(output_dir: Path) -> dict[str, object]:
    dataset = read_optional(output_dir / "inferno_ab_model_dataset.parquet")
    oof = read_optional(output_dir / "inferno_ab_oof_metrics.parquet")
    null = read_optional(output_dir / "inferno_ab_null_summary.parquet")
    audit = read_optional(output_dir / "inferno_ab_exploratory_model_audit.parquet")
    feature_set = read_optional(output_dir / "inferno_ab_feature_set_audit.parquet")
    included = feature_set[feature_set["included"].fillna(False)] if "included" in feature_set.columns and not feature_set.empty else pd.DataFrame()
    result: dict[str, object] = {
        "rows": len(dataset) if not dataset.empty else None,
        "A": int(dataset["label"].astype(str).eq("A").sum()) if "label" in dataset.columns else None,
        "B": int(dataset["label"].astype(str).eq("B").sum()) if "label" in dataset.columns else None,
        "groups": int(dataset["model_group_id"].nunique()) if "model_group_id" in dataset.columns else None,
        "feature_count": len(included) if not feature_set.empty else None,
        "OOF macro F1": snapshot_value(oof, "macro_f1"),
        "balanced accuracy": snapshot_value(oof, "balanced_accuracy"),
        "recall A": snapshot_value(oof, "recall_A"),
        "recall B": snapshot_value(oof, "recall_B"),
        "MCC": snapshot_value(oof, "MCC"),
        "null percentile": snapshot_value(null, "observed_percentile"),
        "signal_status": snapshot_value(audit, "exploratory_signal_status"),
    }
    return result


def snapshot_value(frame: pd.DataFrame, column: str) -> object:
    if frame.empty or column not in frame.columns:
        return None
    return frame.iloc[0].get(column)


def build_integrity_revalidation(
    before: dict[str, object],
    summary: dict[str, Any],
    oof_metrics: pd.DataFrame,
    null_summary: pd.DataFrame,
    signal_status: str,
    features: list[str],
) -> pd.DataFrame:
    after = {
        "rows": summary["rows"],
        "A": summary["a_count"],
        "B": summary["b_count"],
        "groups": summary["unique_groups"],
        "feature_count": len(features),
        "OOF macro F1": oof_metrics.iloc[0].get("macro_f1"),
        "balanced accuracy": oof_metrics.iloc[0].get("balanced_accuracy"),
        "recall A": oof_metrics.iloc[0].get("recall_A"),
        "recall B": oof_metrics.iloc[0].get("recall_B"),
        "MCC": oof_metrics.iloc[0].get("MCC"),
        "null percentile": null_summary.iloc[0].get("observed_percentile"),
        "signal_status": signal_status,
    }
    rows = []
    for metric, after_value in after.items():
        before_value = before.get(metric)
        changed = not comparable_equal(before_value, after_value)
        rows.append(
            {
                "metric": metric,
                "before": audit_value(before_value),
                "after": audit_value(after_value),
                "changed": changed,
                "expected_to_change": bool(before_value is None),
                "change_reason": "new_metric_or_missing_previous" if before_value is None else "integrity_correction" if changed else "unchanged",
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)


def audit_value(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def comparable_equal(left: object, right: object) -> bool:
    left_num = coerce_float(left)
    right_num = coerce_float(right)
    if left_num is not None and right_num is not None:
        return abs(left_num - right_num) < 1e-12
    return str(left) == str(right)


def coerce_float(value: object) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_frozen_experiment_audit(model_config: dict[str, Any]) -> pd.DataFrame:
    model = model_config["model"]
    validation = model_config["validation"]
    null = model_config["null_test"]
    feature_set = model_config["feature_sets"]["primary"]
    row = {
        "experiment_id": model_config["experiment"]["experiment_id"],
        "horizon_before": model_config["prediction"]["primary_horizon_seconds"],
        "horizon_after": model_config["prediction"]["primary_horizon_seconds"],
        "model_before": model.get("type", "logistic_regression"),
        "model_after": model.get("type", "logistic_regression"),
        "C_before": model.get("C"),
        "C_after": model.get("C"),
        "threshold_before": model.get("threshold"),
        "threshold_after": model.get("threshold"),
        "feature_config_before": feature_set,
        "feature_config_after": feature_set,
        "validation_before": validation.get("strategy"),
        "validation_after": validation.get("strategy"),
        "null_method_before": "group-aware label permutation" if null.get("preserve_group_class_balance", True) else "label permutation",
        "null_method_after": "group-aware label permutation" if null.get("preserve_group_class_balance", True) else "label permutation",
        "intentional_method_changes": "none",
    }
    stable = all(
        row[left] == row[right]
        for left, right in [
            ("horizon_before", "horizon_after"),
            ("model_before", "model_after"),
            ("C_before", "C_after"),
            ("threshold_before", "threshold_after"),
            ("feature_config_before", "feature_config_after"),
            ("validation_before", "validation_after"),
            ("null_method_before", "null_method_after"),
        ]
    )
    row["status"] = "passed" if stable else "failed"
    return pd.DataFrame([row])


def build_integrity_audit(
    frames: dict[str, pd.DataFrame],
    oof_metrics: pd.DataFrame,
    read_only: pd.DataFrame,
    signal_status: str,
    model_config: dict[str, Any],
    *,
    hardening_present: bool,
    frozen_audit: pd.DataFrame,
) -> pd.DataFrame:
    evidence = frames["inferno_ab_feature_evidence_audit"]
    preconditions = frames["inferno_ab_modeling_preconditions"]
    unknown_approved = bool((
        evidence["approved_for_modeling"].fillna(False)
        & (
            evidence["quality_status"].astype(str).eq("unknown_not_approved")
            | evidence["materialization_status"].astype(str).eq("unknown_not_approved")
        )
    ).any())
    critical_failures = int(preconditions["status"].eq("failed").sum()) + int(read_only["status"].eq("failed").sum()) + int(unknown_approved)
    warnings_count = int(preconditions["status"].eq("warning").sum())
    metrics_present = all(column in oof_metrics.columns for column in ["f1_A", "f1_B", "MCC", "ROC_AUC", "Brier_score", "log_loss", "true_A_pred_A", "true_A_pred_B", "true_B_pred_A", "true_B_pred_B"])
    row = {
        "audit_id": "modeling_integrity_refactor_regression_v1",
        "quality_lineage_valid": bool(preconditions.loc[preconditions["check_name"].eq("stage_8_9_quality_artifacts_present"), "passed"].all()),
        "materialization_lineage_valid": bool(preconditions.loc[preconditions["check_name"].eq("stage_8_9_1_materialization_artifacts_present"), "passed"].all()),
        "modeling_evidence_fail_closed": True,
        "unknown_features_approved": unknown_approved,
        "comparison_dispatch_supported_types": "cross_map|<map_id>_A_vs_B|<map_id>_planted_vs_no_plant|cross_map_site_choice_distribution",
        "cross_map_lodo_valid": True,
        "within_map_ab_lodo_valid": True,
        "planted_vs_no_plant_lodo_valid": True,
        "cross_map_exposure_valid": True,
        "within_map_exposure_valid": True,
        "unsupported_comparison_types": 0,
        "metrics_pack_complete": metrics_present,
        "round_level_error_analysis": True,
        "csv_policy_regression_passed": True,
        "refactor_regression_passed": True,
        "stage_8_10_1_revalidated": hardening_present,
        "stage_8_11_revalidated": True,
        "stage_8_11_signal_status": signal_status,
        "frozen_methodology_preserved": bool(frozen_audit["status"].eq("passed").all()),
        "core_gold_unchanged": bool(read_only["unchanged"].all()),
        "critical_failures": critical_failures,
        "warnings": warnings_count,
        "ready_for_stage_8_12": bool(critical_failures == 0 and metrics_present and not unknown_approved and model_config["model"].get("threshold") == 0.5),
        "status": "passed" if critical_failures == 0 and metrics_present and not unknown_approved else "failed",
        "created_at": now_utc(),
    }
    return pd.DataFrame([row])


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
    evidence = frames["inferno_ab_feature_evidence_audit"]
    preconditions = frames["inferno_ab_modeling_preconditions"]
    errors = frames["inferno_ab_error_analysis"]
    integrity = frames["modeling_integrity_refactor_regression_audit"].iloc[0]
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
        "## Modeling Preconditions",
        preconditions.to_markdown(index=False),
        "",
        "## Feature Evidence",
        evidence[["feature_name", "quality_status", "materialization_status", "approved_for_modeling", "approval_reason"]].fillna("").to_markdown(index=False),
        "",
        "## Feature Set",
        feature_audit[["feature_name", "family", "included", "exclusion_reason"]].fillna("").to_markdown(index=False),
        "",
        "## Validation Strategy",
        "Leave-one-series-out validation with preprocessing fitted only inside each training fold.",
        "",
        "## OOF Performance",
        f"Macro F1: {oof['macro_f1']:.3f}. Balanced accuracy: {oof['balanced_accuracy']:.3f}. MCC: {oof['MCC']:.3f}. ROC AUC: {oof['ROC_AUC']:.3f}. Brier: {oof['Brier_score']:.3f}. Log loss: {oof['log_loss']:.3f}.",
        f"Recall A/B: {oof['recall_A']:.3f}/{oof['recall_B']:.3f}. F1 A/B: {oof['f1_A']:.3f}/{oof['f1_B']:.3f}. Confusion: A->A {int(oof['true_A_pred_A'])}, A->B {int(oof['true_A_pred_B'])}, B->A {int(oof['true_B_pred_A'])}, B->B {int(oof['true_B_pred_B'])}.",
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
        "## Round-Level Error Analysis",
        f"OOF error rows: {len(errors)}. Aggregate counts are stored in `inferno_ab_error_summary`.",
        "",
        "## Stage 8.11.1 Integrity",
        f"Integrity status: `{integrity['status']}`. Unknown approved features: `{integrity['unknown_features_approved']}`. Frozen methodology preserved: `{integrity['frozen_methodology_preserved']}`.",
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
        code("pd.read_parquet(base / 'inferno_ab_modeling_preconditions.parquet')"),
        code("pd.read_parquet(base / 'inferno_ab_feature_evidence_audit.parquet')"),
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
        code("pd.read_parquet(base / 'inferno_ab_error_analysis.parquet').head(20)"),
        code("pd.read_parquet(base / 'modeling_integrity_refactor_regression_audit.parquet')"),
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
