from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir
from src.utils.logging import configure_logging


LABEL_VALUES = ("A", "B")
ID_COLUMNS = [
    "round_feature_id",
    "round_id",
    "parse_id",
    "series_id",
    "dem_file_id",
    "target_team",
    "map_name",
    "target_team_side",
    "label_confidence",
    "target_site_model_label",
]
LEAKAGE_TOKENS = (
    "target_site",
    "bombsite",
    "bomb_planted",
    "target_team_planted",
    "opponent_planted",
    "planting_",
    "plant_tick",
    "plant_time",
    "winner",
    "round_end",
    "round_duration",
    "first_",
)
ENDPOINT_PREFIXES = ("smokes_to_", "molotovs_to_", "flashes_to_", "he_to_")
RAW_COORDINATE_RE = re.compile(r"(^|_)(x|y|z)($|_)")


def run_build_map_ab_dataset(
    *,
    config_path: Path,
    model_config_path: Path,
    target_map: str | None = None,
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    config_path = config_path.resolve()
    project_root = config_path.parent.parent
    project = load_project_config(config_path)
    model_config = load_model_config(model_config_path)
    experiment = model_config.get("experiment", {})
    prediction = model_config.get("prediction", {})
    target_map = target_map or str(experiment.get("target_map"))
    target_team = target_team or str(experiment.get("target_team"))
    target_side = str(experiment.get("target_side", "T"))
    label_column = str(experiment.get("label_column", "target_site_model_label"))
    horizon = int(prediction.get("primary_horizon_seconds", 35))
    gold_dir = (project_root / project.parsed_silver_dir).parent.parent / "gold"
    output_dir = gold_dir / "modeling" / str(experiment.get("output_subdir", "map_ab_exploratory"))

    source = read_gold_table(gold_dir / "round_features" / "round_features_t_side_planted")
    model_scope, excluded = filter_model_scope(
        source,
        target_map=target_map,
        target_team=target_team,
        target_side=target_side,
        label_column=label_column,
    )
    grouping_column = choose_grouping_column(model_scope, model_config)
    model_scope = model_scope.copy()
    model_scope["label"] = model_scope[label_column].astype(str)
    model_scope["model_group_id"] = model_scope[grouping_column].astype(str)

    feature_contract = load_feature_contract(project_root / "configs" / "features" / "feature_contract.yaml")
    quality = read_optional(gold_dir / "validation" / "map_feature_quality" / "map_feature_quality_feature_audit.parquet")
    materialization = read_optional(
        gold_dir / "validation" / "feature_materialization_repair" / "feature_materialization_repair_feature_audit.parquet"
    )
    hardened = read_optional(gold_dir / "analysis" / "tactical_finding_hardening" / "modeling_context_findings.parquet")

    leakage_audit = build_feature_leakage_audit(
        model_scope,
        model_config,
        feature_contract,
        quality,
        materialization,
        horizon=horizon,
    )
    horizon_audit = leakage_audit[
        ["feature_name", "window_type", "window_start", "window_end", "available_at_horizon", "exclusion_reason"]
    ].copy()
    horizon_audit.insert(1, "horizon", horizon)
    horizon_audit["available"] = horizon_audit["available_at_horizon"]
    horizon_audit["reason"] = horizon_audit["exclusion_reason"].fillna("available_at_horizon")

    feature_set_audit = build_feature_set_audit(model_scope, model_config, leakage_audit, hardened)
    selected_features = feature_set_audit.loc[feature_set_audit["included"], "feature_name"].astype(str).tolist()
    if not selected_features:
        raise ValueError("No leakage-safe features are available for the configured model dataset.")

    dataset_columns = [column for column in ID_COLUMNS if column in model_scope.columns]
    dataset = model_scope[dataset_columns + ["label", "model_group_id", *selected_features]].copy()
    if dataset["round_feature_id"].duplicated().any():
        duplicates = int(dataset["round_feature_id"].duplicated().sum())
        raise ValueError(f"Model dataset has duplicate round_feature_id values: {duplicates}")

    label_audit = build_label_audit(model_scope, excluded, label_column=label_column)
    group_audit = build_group_audit(model_scope, grouping_column)
    feature_set_id = str(model_config.get("feature_sets", {}).get("primary", "compact_tactical_35s"))
    fingerprint = build_experiment_fingerprint(dataset, model_config, feature_contract)
    frames = {
        "inferno_ab_model_dataset": dataset,
        "inferno_ab_label_audit": label_audit,
        "inferno_ab_group_audit": group_audit,
        "inferno_ab_feature_leakage_audit": leakage_audit,
        "inferno_ab_horizon_audit": horizon_audit,
        "inferno_ab_feature_set_audit": feature_set_audit,
        "inferno_ab_experiment_fingerprint": pd.DataFrame(
            [
                {
                    "experiment_id": experiment.get("experiment_id"),
                    "feature_set_id": feature_set_id,
                    "logical_fingerprint": fingerprint,
                    "created_at": now_utc(),
                    "status": "ok",
                }
            ]
        ),
    }
    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs = write_outputs(frames, output_dir, force=force)
    summary = {
        "rows": len(dataset),
        "a_count": int(dataset["label"].eq("A").sum()),
        "b_count": int(dataset["label"].eq("B").sum()),
        "grouping_column_used": grouping_column,
        "unique_groups": int(dataset["model_group_id"].nunique()),
        "feature_count": len(selected_features),
        "horizon_seconds": horizon,
        "output_dir": str(output_dir),
    }
    return frames, outputs, summary


def load_model_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Model config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def read_gold_table(path_without_suffix: Path) -> pd.DataFrame:
    parquet = path_without_suffix.with_suffix(".parquet")
    csv = path_without_suffix.with_suffix(".csv")
    if parquet.exists():
        return pd.read_parquet(parquet)
    if csv.exists():
        return pd.read_csv(csv)
    raise FileNotFoundError(f"Gold table not found: {parquet}")


def read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)


def filter_model_scope(
    source: pd.DataFrame,
    *,
    target_map: str,
    target_team: str,
    target_side: str,
    label_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = source.copy()
    checks = pd.DataFrame(index=frame.index)
    checks["map_ok"] = frame.get("map_name", "").astype(str).str.casefold().eq(target_map.casefold())
    checks["team_ok"] = frame.get("target_team", "").astype(str).str.casefold().eq(target_team.casefold())
    checks["side_ok"] = frame.get("target_team_side", "").astype(str).str.upper().eq(target_side.upper())
    checks["label_ok"] = frame.get(label_column, "").astype(str).isin(LABEL_VALUES)
    checks["confidence_ok"] = frame.get("label_confidence", "").astype(str).str.casefold().eq("high")
    if "target_team_planted" in frame.columns:
        checks["target_plant_ok"] = frame["target_team_planted"].astype(str).str.casefold().isin(["true", "1", "yes"])
    else:
        checks["target_plant_ok"] = checks["label_ok"] & checks["confidence_ok"]
    keep = checks.all(axis=1)
    excluded = checks.assign(round_feature_id=frame.get("round_feature_id", pd.Series(index=frame.index, dtype=object)))
    excluded["excluded"] = ~keep
    return frame[keep].copy(), excluded


def choose_grouping_column(dataset: pd.DataFrame, model_config: dict[str, Any]) -> str:
    validation = model_config.get("validation", {})
    preferred = str(validation.get("preferred_group_column", "series_id"))
    fallback = str(validation.get("fallback_group_column", "parse_id"))
    if preferred in dataset.columns:
        values = dataset[preferred].astype(str).str.strip()
        if values.ne("").all() and values.nunique() >= int(validation.get("minimum_valid_groups", 3)):
            return preferred
    if fallback not in dataset.columns:
        raise ValueError(f"Neither {preferred} nor {fallback} is available for model grouping.")
    values = dataset[fallback].astype(str).str.strip()
    if values.nunique() < int(validation.get("minimum_valid_groups", 3)):
        raise ValueError("Fewer than 3 valid model groups are available.")
    return fallback


def load_feature_contract(path: Path) -> dict[str, dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(item.get("feature_name")): item for item in config.get("features", [])}


def build_feature_leakage_audit(
    dataset: pd.DataFrame,
    model_config: dict[str, Any],
    feature_contract: dict[str, dict[str, Any]],
    quality: pd.DataFrame,
    materialization: pd.DataFrame,
    *,
    horizon: int,
) -> pd.DataFrame:
    rows = []
    candidates = configured_candidate_features(model_config)
    for feature_name, family, selection_source in candidates:
        contract = feature_contract.get(feature_name, {})
        present = feature_name in dataset.columns
        window_type, window_start, window_end = feature_window(feature_name, contract)
        materialization_status = materialization_status_for(feature_name, materialization, present)
        quality_status = quality_status_for(feature_name, quality)
        flags = leakage_flags(feature_name, contract, window_end=window_end, horizon=horizon)
        eligible = bool(present and materialization_status != "missing" and quality_status != "failed" and not flags["blocked"])
        rows.append(
            {
                "feature_name": feature_name,
                "feature_family": family or contract.get("feature_family"),
                "window_type": window_type,
                "window_start": window_start,
                "window_end": window_end,
                "available_at_horizon": flags["available_at_horizon"],
                "full_round_dependency": flags["full_round_dependency"],
                "plant_dependency": flags["plant_dependency"],
                "outcome_dependency": flags["outcome_dependency"],
                "label_dependency": flags["label_dependency"],
                "endpoint_dependency": flags["endpoint_dependency"],
                "raw_coordinate_dependency": flags["raw_coordinate_dependency"],
                "materialization_status": materialization_status,
                "quality_status": quality_status,
                "selection_source": selection_source,
                "eligible": eligible,
                "exclusion_reason": None if eligible else flags["reason"] or "missing_or_low_quality",
            }
        )
    return pd.DataFrame(rows)


def configured_candidate_features(model_config: dict[str, Any]) -> list[tuple[str, str | None, str]]:
    feature_sets = model_config.get("feature_sets", {})
    primary = str(feature_sets.get("primary", "compact_tactical_35s"))
    rows: list[tuple[str, str | None, str]] = []
    for item in feature_sets.get(primary, {}).get("features", []):
        rows.append((str(item.get("feature_name")), item.get("family"), primary))
    for ablation_id, features in feature_sets.get("ablations", {}).items():
        for feature in features:
            rows.append((str(feature), None, str(ablation_id)))
    seen = set()
    unique = []
    for row in rows:
        if row[0] not in seen:
            unique.append(row)
            seen.add(row[0])
    return unique


def feature_window(feature_name: str, contract: dict[str, Any]) -> tuple[str, float | None, float | None]:
    if contract:
        return (
            str(contract.get("window_type") or "static"),
            to_float(contract.get("window_start")),
            to_float(contract.get("window_end")),
        )
    match = re.search(r"_(\d+)_(\d+)$", feature_name)
    if match:
        start, end = float(match.group(1)), float(match.group(2))
        return ("cumulative" if start == 0 else "interval", start, end)
    match = re.search(r"_(\d+)s$", feature_name)
    if match:
        end = float(match.group(1))
        return ("point", 0.0, end)
    return ("static", None, None)


def leakage_flags(feature_name: str, contract: dict[str, Any], *, window_end: float | None, horizon: int) -> dict[str, Any]:
    lower = feature_name.casefold()
    label_dependency = any(token in lower for token in ("target_site", "bombsite", "label"))
    plant_dependency = any(token in lower for token in ("plant", "bomb"))
    outcome_dependency = "winner" in lower or "round_end_reason" in lower
    full_round_dependency = lower.startswith("first_") or "round_duration" in lower
    endpoint_dependency = lower.startswith(ENDPOINT_PREFIXES)
    raw_coordinate_dependency = bool(RAW_COORDINATE_RE.search(lower)) and str(contract.get("coordinate_dependency")) not in {"none", ""}
    after_horizon = window_end is not None and float(window_end) > horizon
    blocked = bool(
        label_dependency
        or plant_dependency
        or outcome_dependency
        or full_round_dependency
        or endpoint_dependency
        or raw_coordinate_dependency
        or after_horizon
        or any(token in lower for token in LEAKAGE_TOKENS)
    )
    reason = None
    if after_horizon:
        reason = "after_horizon"
    elif label_dependency:
        reason = "label_dependency"
    elif plant_dependency:
        reason = "plant_dependency"
    elif outcome_dependency:
        reason = "outcome_dependency"
    elif full_round_dependency:
        reason = "full_round_dependency"
    elif endpoint_dependency:
        reason = "unresolved_endpoint"
    elif raw_coordinate_dependency:
        reason = "raw_coordinate_requires_normalization"
    return {
        "available_at_horizon": not after_horizon,
        "full_round_dependency": full_round_dependency,
        "plant_dependency": plant_dependency,
        "outcome_dependency": outcome_dependency,
        "label_dependency": label_dependency,
        "endpoint_dependency": endpoint_dependency,
        "raw_coordinate_dependency": raw_coordinate_dependency,
        "blocked": blocked,
        "reason": reason,
    }


def materialization_status_for(feature_name: str, materialization: pd.DataFrame, present: bool) -> str:
    if not present:
        return "missing"
    if materialization.empty or "feature_name" not in materialization.columns:
        return "supported"
    row = materialization[materialization["feature_name"].astype(str).eq(feature_name)]
    if row.empty:
        return "supported"
    status = str(row.iloc[0].get("status") or row.iloc[0].get("repair_status") or "supported")
    return "supported" if status in {"ok", "passed", "supported", "repaired"} else status


def quality_status_for(feature_name: str, quality: pd.DataFrame) -> str:
    if quality.empty or "feature_name" not in quality.columns:
        return "unknown"
    row = quality[quality["feature_name"].astype(str).eq(feature_name)]
    if row.empty:
        return "unknown"
    return str(row.iloc[0].get("status") or row.iloc[0].get("quality_status") or "unknown")


def build_feature_set_audit(
    dataset: pd.DataFrame,
    model_config: dict[str, Any],
    leakage_audit: pd.DataFrame,
    hardened: pd.DataFrame,
) -> pd.DataFrame:
    feature_sets = model_config.get("feature_sets", {})
    primary = str(feature_sets.get("primary", "compact_tactical_35s"))
    hardened_features = set(hardened.get("representative_feature", pd.Series(dtype=object)).dropna().astype(str))
    rows = []
    lookup = leakage_audit.set_index("feature_name") if not leakage_audit.empty else pd.DataFrame()
    for item in feature_sets.get(primary, {}).get("features", []):
        feature = str(item.get("feature_name"))
        audit = lookup.loc[feature] if not lookup.empty and feature in lookup.index else pd.Series(dtype=object)
        present = feature in dataset.columns
        missing_share = float(dataset[feature].isna().mean()) if present else None
        unique_values = int(dataset[feature].nunique(dropna=True)) if present else 0
        quality_passed = str(audit.get("quality_status")) not in {"failed", "blocked"}
        materialization_supported = str(audit.get("materialization_status")) != "missing"
        included = bool(audit.get("eligible", False) and unique_values > 1)
        reason = audit.get("exclusion_reason")
        reason = None if reason is None or pd.isna(reason) else reason
        rows.append(
            {
                "feature_set_id": primary,
                "feature_name": feature,
                "family": item.get("family") or audit.get("feature_family"),
                "source": "predeclared_compact_feature_family",
                "horizon_safe": bool(audit.get("available_at_horizon", False)),
                "quality_passed": quality_passed,
                "materialization_supported": materialization_supported,
                "missing_share": missing_share,
                "unique_values": unique_values,
                "included": included,
                "exclusion_reason": None if included else reason or "constant_or_missing",
                "eda_hardened_context_overlap": feature in hardened_features,
            }
        )
    return pd.DataFrame(rows)


def build_label_audit(scope: pd.DataFrame, excluded: pd.DataFrame, *, label_column: str) -> pd.DataFrame:
    labels = scope[label_column].astype(str)
    grouped = scope.groupby("parse_id")[label_column] if "parse_id" in scope.columns else labels.groupby(labels.index)
    series_grouped = scope.groupby("series_id")[label_column] if "series_id" in scope.columns else labels.groupby(labels.index)
    return pd.DataFrame(
        [
            {
                "rows": len(scope),
                "a_count": int(labels.eq("A").sum()),
                "b_count": int(labels.eq("B").sum()),
                "a_share": safe_divide(int(labels.eq("A").sum()), len(scope)),
                "b_share": safe_divide(int(labels.eq("B").sum()), len(scope)),
                "unique_demos": int(scope.get("parse_id", pd.Series(dtype=object)).nunique(dropna=True)),
                "unique_series": int(scope.get("series_id", pd.Series(dtype=object)).nunique(dropna=True)),
                "demos_with_a": int(grouped.apply(lambda values: values.astype(str).eq("A").any()).sum()),
                "demos_with_b": int(grouped.apply(lambda values: values.astype(str).eq("B").any()).sum()),
                "series_with_a": int(series_grouped.apply(lambda values: values.astype(str).eq("A").any()).sum()),
                "series_with_b": int(series_grouped.apply(lambda values: values.astype(str).eq("B").any()).sum()),
                "invalid_labels": int((~labels.isin(LABEL_VALUES)).sum()),
                "missing_labels": int(scope[label_column].isna().sum()),
                "duplicate_round_feature_ids": int(scope.get("round_feature_id", pd.Series(dtype=object)).duplicated().sum()),
                "low_confidence_excluded": int((excluded["label_ok"] & ~excluded["confidence_ok"]).sum()),
                "no_plant_excluded": int((~excluded["label_ok"]).sum()),
                "status": "ok" if len(scope) > 0 and not scope.get("round_feature_id", pd.Series(dtype=object)).duplicated().any() else "failed",
            }
        ]
    )


def build_group_audit(scope: pd.DataFrame, grouping_column: str) -> pd.DataFrame:
    rows = []
    for group_id, group in scope.groupby(grouping_column, dropna=False):
        labels = group["label"].astype(str)
        rows.append(
            {
                "grouping_column_used": grouping_column,
                "model_group_id": str(group_id),
                "rounds": len(group),
                "a_count": int(labels.eq("A").sum()),
                "b_count": int(labels.eq("B").sum()),
                "has_a": bool(labels.eq("A").any()),
                "has_b": bool(labels.eq("B").any()),
                "heldout_one_class": bool(labels.nunique() == 1),
                "status": "ok",
            }
        )
    result = pd.DataFrame(rows)
    result["unique_groups"] = len(result)
    return result


def build_experiment_fingerprint(dataset: pd.DataFrame, model_config: dict[str, Any], feature_contract: dict[str, dict[str, Any]]) -> str:
    stable = dataset.sort_values("round_feature_id").reset_index(drop=True)
    payload = {
        "dataset": json.loads(stable.to_json(orient="records", date_format="iso")),
        "model_config": model_config,
        "feature_contract_hash": hashlib.sha256(json.dumps(feature_contract, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs = {}
    for name, frame in frames.items():
        for suffix in ("csv", "parquet"):
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                frame.to_csv(path, index=False) if suffix == "csv" else frame.to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def to_float(value: object) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_divide(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator / denominator) if denominator else None


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def print_summary(summary: dict[str, Any], outputs: dict[str, Path]) -> None:
    print("Map A/B modeling dataset summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for key, value in outputs.items():
        print(f"- {key}: {value}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a leakage-audited map-aware A/B modeling dataset.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model-config", type=Path, required=True)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_build_map_ab_dataset(
        config_path=args.config,
        model_config_path=args.model_config,
        target_map=args.target_map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
    )
    print_summary(summary, outputs)


if __name__ == "__main__":
    main()
