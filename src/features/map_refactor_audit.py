from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from src.maps.registry import MapRegistry
from src.maps.semantic import map_feature_unknowns, resolve_feature_requirements
from src.utils.io import read_catalog


COMPATIBILITY_DATASETS = {
    "round_features_mvp": Path("round_features/round_features_mvp.parquet"),
    "region_presence_by_round": Path("region_presence/region_presence_by_round.parquet"),
    "round_region_timeline": Path("round_progression/round_region_timeline.parquet"),
    "round_features_t_side_all": Path("round_features/round_features_t_side_all.parquet"),
    "round_features_t_side_planted": Path("round_features/round_features_t_side_planted.parquet"),
}
ATOL = 1e-9
RTOL = 1e-9


def load_feature_contract(gold_dir: Path, feature_contract_path: Path | None = None) -> pd.DataFrame:
    candidates = []
    if feature_contract_path is not None:
        candidates.append(feature_contract_path)
    candidates.extend(
        [
            gold_dir / "features" / "feature_contract" / "feature_contract.parquet",
            gold_dir / "features" / "feature_contract" / "feature_contract.csv",
        ]
    )
    for path in candidates:
        if path.exists():
            return read_catalog(path)
    raise FileNotFoundError("Feature contract is required. Run Stage 8.0 before Stage 8.2.")


def load_candidate_feature_set(gold_dir: Path) -> pd.DataFrame:
    path = gold_dir / "modeling" / "t_side_ab_candidate" / "candidate_model_feature_set.parquet"
    if path.exists():
        return read_catalog(path)
    csv = path.with_suffix(".csv")
    if csv.exists():
        return read_catalog(csv)
    return pd.DataFrame(columns=["feature_name"])


def load_compatibility_baselines(gold_dir: Path) -> dict[str, pd.DataFrame]:
    baselines = {}
    for name, relative_path in COMPATIBILITY_DATASETS.items():
        path = gold_dir / relative_path
        baselines[name] = read_catalog(path) if path.exists() else pd.DataFrame()
    return baselines


def build_post_refactor_frames(
    *,
    round_features: pd.DataFrame,
    region_presence: pd.DataFrame,
    baselines: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    return {
        "round_features_mvp": round_features,
        "region_presence_by_round": region_presence,
        "round_region_timeline": baselines.get("round_region_timeline", pd.DataFrame()),
        "round_features_t_side_all": baselines.get("round_features_t_side_all", pd.DataFrame()),
        "round_features_t_side_planted": baselines.get("round_features_t_side_planted", pd.DataFrame()),
    }


def build_map_refactor_audits(
    *,
    registry: MapRegistry,
    feature_contract: pd.DataFrame,
    candidate_feature_set: pd.DataFrame,
    baselines: dict[str, pd.DataFrame],
    post_frames: dict[str, pd.DataFrame],
    new_runtime_seconds: float,
    old_runtime_seconds: float | None = None,
) -> dict[str, pd.DataFrame]:
    usage = resolve_feature_requirements(feature_contract, registry)
    unknowns = map_feature_unknowns(usage, registry.map_id)
    compatibility = build_compatibility_table(baselines, post_frames, candidate_feature_set)
    audit = build_refactor_audit(
        registry=registry,
        feature_contract=feature_contract,
        usage=usage,
        unknowns=unknowns,
        compatibility=compatibility,
        candidate_feature_set=candidate_feature_set,
        post_frames=post_frames,
        old_runtime_seconds=old_runtime_seconds,
        new_runtime_seconds=new_runtime_seconds,
    )
    return {
        "map_feature_refactor_audit": audit,
        "map_feature_registry_usage": serialize_usage(usage),
        "map_feature_compatibility": compatibility,
        "map_feature_unknowns": unknowns,
    }


def build_compatibility_table(
    baselines: dict[str, pd.DataFrame],
    post_frames: dict[str, pd.DataFrame],
    candidate_feature_set: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    candidate_features = set(candidate_feature_names(candidate_feature_set))
    for dataset_name in COMPATIBILITY_DATASETS:
        before = baselines.get(dataset_name, pd.DataFrame())
        after = post_frames.get(dataset_name, pd.DataFrame())
        rows.append(compare_column_inventory(dataset_name, before, after))
        before_aligned, after_aligned, missing_rows, extra_rows = prepare_alignment(before, after)
        for column in sorted(set(before.columns) | set(after.columns)):
            rows.append(
                compare_column(
                    dataset_name,
                    column,
                    before,
                    after,
                    before_aligned,
                    after_aligned,
                    missing_rows,
                    extra_rows,
                    is_candidate=column in candidate_features,
                )
            )
    return pd.DataFrame(rows)


def compare_column_inventory(dataset_name: str, before: pd.DataFrame, after: pd.DataFrame) -> dict[str, object]:
    before_columns = list(before.columns)
    after_columns = list(after.columns)
    exact = before_columns == after_columns
    missing = sorted(set(before_columns) - set(after_columns))
    extra = sorted(set(after_columns) - set(before_columns))
    status = "ok" if exact else "failed"
    if before.empty and after.empty and not before_columns and not after_columns:
        status = "warning"
    return {
        "dataset_name": dataset_name,
        "column_name": "__columns__",
        "comparison_type": "column_inventory",
        "rows_before": len(before),
        "rows_after": len(after),
        "missing_rows": 0,
        "extra_rows": 0,
        "null_count_before": None,
        "null_count_after": None,
        "changed_value_count": len(missing) + len(extra) + (0 if before_columns == after_columns else int(before_columns != after_columns)),
        "max_abs_difference": None,
        "mean_abs_difference": None,
        "exact_match": exact,
        "within_tolerance": exact,
        "status": status,
        "notes": f"missing_columns={missing}; extra_columns={extra}",
        "is_candidate_feature": False,
    }


def compare_column(
    dataset_name: str,
    column: str,
    before: pd.DataFrame,
    after: pd.DataFrame,
    before_aligned: pd.DataFrame,
    after_aligned: pd.DataFrame,
    missing_rows: int,
    extra_rows: int,
    *,
    is_candidate: bool,
) -> dict[str, object]:
    if column not in before.columns or column not in after.columns:
        return missing_column_row(dataset_name, column, before, after, is_candidate=is_candidate)
    before_values = before_aligned[column]
    after_values = after_aligned[column]
    changed, max_diff, mean_diff, exact, within_tolerance = compare_values(before_values, after_values)
    status = "ok" if exact or within_tolerance else "failed"
    if missing_rows or extra_rows:
        status = "failed"
    return {
        "dataset_name": dataset_name,
        "column_name": column,
        "comparison_type": "candidate_feature" if is_candidate else "column_values",
        "rows_before": len(before),
        "rows_after": len(after),
        "missing_rows": missing_rows,
        "extra_rows": extra_rows,
        "null_count_before": int(before_values.isna().sum()),
        "null_count_after": int(after_values.isna().sum()),
        "changed_value_count": changed,
        "max_abs_difference": max_diff,
        "mean_abs_difference": mean_diff,
        "exact_match": exact and not missing_rows and not extra_rows,
        "within_tolerance": within_tolerance and not missing_rows and not extra_rows,
        "status": status,
        "notes": "Compared with atol=1e-9 and rtol=1e-9 for numeric columns.",
        "is_candidate_feature": is_candidate,
    }


def missing_column_row(dataset_name: str, column: str, before: pd.DataFrame, after: pd.DataFrame, *, is_candidate: bool) -> dict[str, object]:
    missing_before = column not in before.columns
    missing_after = column not in after.columns
    return {
        "dataset_name": dataset_name,
        "column_name": column,
        "comparison_type": "candidate_feature" if is_candidate else "column_values",
        "rows_before": len(before),
        "rows_after": len(after),
        "missing_rows": len(before) if missing_after else 0,
        "extra_rows": len(after) if missing_before else 0,
        "null_count_before": None,
        "null_count_after": None,
        "changed_value_count": max(len(before), len(after)),
        "max_abs_difference": None,
        "mean_abs_difference": None,
        "exact_match": False,
        "within_tolerance": False,
        "status": "failed",
        "notes": "Column missing in before or after snapshot.",
        "is_candidate_feature": is_candidate,
    }


def prepare_alignment(before: pd.DataFrame, after: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
    keys = key_columns(before, after)
    if keys:
        before = before.sort_values(keys, kind="mergesort")
        after = after.sort_values(keys, kind="mergesort")
    count = min(len(before), len(after))
    return (
        before.head(count).reset_index(drop=True),
        after.head(count).reset_index(drop=True),
        max(len(before) - count, 0),
        max(len(after) - count, 0),
    )


def align_frames(before: pd.DataFrame, after: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
    keys = key_columns(before, after)
    if not keys:
        count = min(len(before), len(after))
        return before.head(count).reset_index(drop=True), after.head(count).reset_index(drop=True), max(len(before) - count, 0), max(len(after) - count, 0)
    before_keyed = before.sort_values(keys).set_index(keys, drop=False)
    after_keyed = after.sort_values(keys).set_index(keys, drop=False)
    common = before_keyed.index.intersection(after_keyed.index)
    missing_rows = len(before_keyed.index.difference(after_keyed.index))
    extra_rows = len(after_keyed.index.difference(before_keyed.index))
    return before_keyed.loc[common].reset_index(drop=True), after_keyed.loc[common].reset_index(drop=True), missing_rows, extra_rows


def key_columns(before: pd.DataFrame, after: pd.DataFrame) -> list[str]:
    candidates = [
        ["round_feature_id", "window_type", "window_start", "window_end", "region_name", "region_group"],
        ["round_feature_id", "window_type", "window_start", "window_end", "region_group"],
        ["round_feature_id"],
    ]
    for keys in candidates:
        if set(keys).issubset(before.columns) and set(keys).issubset(after.columns):
            return keys
    return []


def compare_values(before: pd.Series, after: pd.Series) -> tuple[int, float | None, float | None, bool, bool]:
    if len(before) != len(after):
        return max(len(before), len(after)), None, None, False, False
    before_reset = before.reset_index(drop=True)
    after_reset = after.reset_index(drop=True)
    both_missing = before_reset.isna() & after_reset.isna()
    numeric = (
        pd.api.types.is_numeric_dtype(before_reset)
        and pd.api.types.is_numeric_dtype(after_reset)
        and not pd.api.types.is_bool_dtype(before_reset)
        and not pd.api.types.is_bool_dtype(after_reset)
    )
    if numeric:
        before_num = pd.to_numeric(before_reset, errors="coerce")
        after_num = pd.to_numeric(after_reset, errors="coerce")
        close = np.isclose(before_num, after_num, atol=ATOL, rtol=RTOL, equal_nan=True)
        diffs = (before_num - after_num).abs()
        valid_diffs = diffs[~both_missing & diffs.notna()]
        changed = int((~close).sum())
        return (
            changed,
            float(valid_diffs.max()) if not valid_diffs.empty else 0.0,
            float(valid_diffs.mean()) if not valid_diffs.empty else 0.0,
            changed == 0,
            changed == 0,
        )
    equal = (before_reset.astype("object") == after_reset.astype("object")) | both_missing
    changed = int((~equal).sum())
    return changed, None, None, changed == 0, changed == 0


def build_refactor_audit(
    *,
    registry: MapRegistry,
    feature_contract: pd.DataFrame,
    usage: pd.DataFrame,
    unknowns: pd.DataFrame,
    compatibility: pd.DataFrame,
    candidate_feature_set: pd.DataFrame,
    post_frames: dict[str, pd.DataFrame],
    old_runtime_seconds: float | None,
    new_runtime_seconds: float,
) -> pd.DataFrame:
    candidate_names = candidate_feature_names(candidate_feature_set)
    round_features = post_frames.get("round_features_mvp", pd.DataFrame())
    candidate_found = [name for name in candidate_names if name in round_features.columns]
    candidate_missing = sorted(set(candidate_names) - set(candidate_found))
    candidate_changed = int(
        compatibility[
            (compatibility["is_candidate_feature"] == True)  # noqa: E712
            & (compatibility["status"] == "failed")
        ]["changed_value_count"].sum()
    )
    unresolved = usage[(usage["region_dependency"] == True) & (usage["resolved"] == False)] if not usage.empty else pd.DataFrame()  # noqa: E712
    resolved_region_usage = usage[(usage["region_dependency"] == True) & (usage["resolved"] == True)] if not usage.empty else pd.DataFrame()  # noqa: E712
    unsupported_geometry_features = int((unknowns["unknown_type"] == "unsupported_geometry").sum()) if "unknown_type" in unknowns.columns else 0
    compatibility_passed = bool((compatibility["status"] != "failed").all()) if not compatibility.empty else False
    map_feature_engine_ready = bool(
        compatibility_passed
        and candidate_missing == []
        and candidate_changed == 0
        and unresolved.empty
        and unsupported_geometry_features == 0
        and {"A", "B"} <= set(registry.bombsites)
    )
    status = "ok" if map_feature_engine_ready else "failed"
    if not map_feature_engine_ready and not compatibility.empty and (compatibility["status"] == "warning").any() and not (compatibility["status"] == "failed").any():
        status = "warning"
    runtime_delta = None if old_runtime_seconds is None else new_runtime_seconds - old_runtime_seconds
    runtime_delta_pct = None if old_runtime_seconds in {None, 0} else runtime_delta / old_runtime_seconds
    return pd.DataFrame(
        [
            {
                "audit_id": "map_ready_feature_refactor",
                "map_id": registry.map_id,
                "registry_version": registry.registry_version,
                "feature_contract_version": contract_version(feature_contract),
                "rounds_processed": len(round_features),
                "features_generated": len(round_features.columns),
                "global_features": count_scope(feature_contract, "global"),
                "map_abstract_features": count_scope(feature_contract, "map_abstract"),
                "map_specific_features": count_scope(feature_contract, "map_specific"),
                "region_dependent_features": int(feature_contract["region_dependency"].sum()) if "region_dependency" in feature_contract.columns else 0,
                "resolved_region_features": len(resolved_region_usage),
                "unresolved_region_features": len(unresolved),
                "unsupported_geometry_features": unsupported_geometry_features,
                "candidate_features_expected": len(candidate_names),
                "candidate_features_found": len(candidate_found),
                "candidate_features_missing": len(candidate_missing),
                "candidate_feature_values_changed": candidate_changed,
                "compatibility_check_status": "passed" if compatibility_passed else "failed",
                "map_feature_engine_ready": map_feature_engine_ready,
                "old_runtime_seconds": old_runtime_seconds,
                "new_runtime_seconds": new_runtime_seconds,
                "runtime_delta_seconds": runtime_delta,
                "runtime_delta_pct": runtime_delta_pct,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def candidate_feature_names(candidate_feature_set: pd.DataFrame) -> list[str]:
    if candidate_feature_set.empty or "feature_name" not in candidate_feature_set.columns:
        return []
    names = candidate_feature_set["feature_name"].dropna().astype(str).tolist()
    return [name for name in names if name != "__feature_set_summary__"]


def count_scope(feature_contract: pd.DataFrame, scope: str) -> int:
    return int((feature_contract.get("map_scope", pd.Series(dtype="object")) == scope).sum())


def contract_version(feature_contract: pd.DataFrame) -> str:
    if "feature_contract_version" in feature_contract.columns and not feature_contract.empty:
        return str(feature_contract["feature_contract_version"].dropna().iloc[0])
    return "unknown"


def serialize_usage(usage: pd.DataFrame) -> pd.DataFrame:
    result = usage.copy()
    if "physical_regions_used" in result.columns:
        result["physical_regions_used"] = result["physical_regions_used"].map(lambda value: "|".join(value) if isinstance(value, list) else value)
    return result


def measure_start() -> float:
    return perf_counter()


def elapsed_seconds(started_at: float) -> float:
    return perf_counter() - started_at
