from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from src.analysis.t_side_eda import run_t_side_eda
from src.config.schemas import load_project_config
from src.features.build_round_features import run_feature_pipeline
from src.features.round_state import run_round_state_pipeline
from src.features.side_datasets import run_side_dataset_pipeline
from src.parsing.parse_quality import run_quality_pipeline
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


BASELINE_VERSION = "mirage_mvp_map_ready_v1"
DEFAULT_BASELINE_MODE = "current_frozen_mvp"
OUTPUT_NAMES = [
    "mirage_regression_summary",
    "mirage_dataset_comparison",
    "mirage_schema_comparison",
    "mirage_row_identity_comparison",
    "mirage_feature_value_comparison",
    "mirage_region_timeline_comparison",
    "mirage_round_state_comparison",
    "mirage_side_dataset_comparison",
    "mirage_candidate_input_compatibility",
    "mirage_invariant_checks",
    "mirage_regression_failures",
    "mirage_regression_audit",
]


@dataclass(frozen=True)
class DatasetSpec:
    dataset_name: str
    relative_path: Path
    key_columns: tuple[str, ...]
    source_stage: str
    critical: bool = True


DATASET_SPECS = [
    DatasetSpec("feature_eligible_demos", Path("silver/parsed_demos/feature_eligible_demos.parquet"), ("parse_id",), "Stage 3.6"),
    DatasetSpec("parse_quality", Path("bronze/parse_quality/parse_quality.parquet"), ("parse_id",), "Stage 3.6", critical=False),
    DatasetSpec("round_features_mvp", Path("gold/round_features/round_features_mvp.parquet"), ("round_feature_id",), "Stage 4"),
    DatasetSpec(
        "region_presence_by_round",
        Path("gold/region_presence/region_presence_by_round.parquet"),
        ("round_feature_id", "window_type", "window_start", "window_end", "region_name", "region_group"),
        "Stage 4",
    ),
    DatasetSpec("utility_events", Path("gold/utility_events/utility_events.parquet"), ("utility_event_id",), "Stage 4", critical=False),
    DatasetSpec("round_region_timeline", Path("gold/round_progression/round_region_timeline.parquet"), ("round_feature_id", "window_type", "window_start", "window_end", "region_name", "region_group"), "Stage 4.3"),
    DatasetSpec("round_state_resolved", Path("gold/round_state/round_state_resolved.parquet"), ("round_id",), "Stage 4.2"),
    DatasetSpec("round_features_t_side_all", Path("gold/round_features/round_features_t_side_all.parquet"), ("round_feature_id",), "Stage 4.3"),
    DatasetSpec("round_features_t_side_planted", Path("gold/round_features/round_features_t_side_planted.parquet"), ("round_feature_id",), "Stage 4.3"),
    DatasetSpec("round_features_ct_side", Path("gold/round_features/round_features_ct_side.parquet"), ("round_feature_id",), "Stage 4.3"),
    DatasetSpec("feature_contract", Path("gold/features/feature_contract/feature_contract.parquet"), ("feature_name",), "Stage 8.0"),
    DatasetSpec("map_registry", Path("gold/maps/map_registry/map_registry.parquet"), ("map_id",), "Stage 8.1"),
    DatasetSpec("map_feature_semantic_coverage", Path("gold/maps/map_registry/map_feature_semantic_coverage.parquet"), ("feature_name",), "Stage 8.1"),
    DatasetSpec("candidate_model_selection", Path("gold/modeling/t_side_ab_candidate/candidate_model_selection.parquet"), ("candidate_id",), "Stage 6.3"),
    DatasetSpec("candidate_model_feature_set", Path("gold/modeling/t_side_ab_candidate/candidate_model_feature_set.parquet"), ("candidate_id", "feature_name"), "Stage 6.3"),
    DatasetSpec("candidate_model_metrics", Path("gold/modeling/t_side_ab_candidate/candidate_model_metrics.parquet"), ("candidate_id",), "Stage 6.3"),
]

CONFIG_SNAPSHOTS = [
    Path("configs/project.yaml"),
    Path("configs/features/feature_contract.yaml"),
    Path("configs/maps/map_registry.yaml"),
    Path("configs/maps/mirage.yaml"),
]


def run_mirage_regression_gate(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    baseline_mode: str = DEFAULT_BASELINE_MODE,
    float_atol: float = 1e-9,
    float_rtol: float = 1e-9,
    strict: bool = True,
    rerun: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    baseline_dir = gold_dir / "validation" / "mirage_regression_baseline"
    output_dir = gold_dir / "validation" / "mirage_regression_gate"
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]

    rerun_runtime = None
    if rerun and not dry_run:
        started = perf_counter()
        run_quality_pipeline(config_path, force=force)
        run_feature_pipeline(config_path, force=force, target_team=target_team, target_map=target_map)
        run_round_state_pipeline(config_path, force=force)
        run_side_dataset_pipeline(config_path, force=force, target_team=target_team, target_map=target_map)
        run_t_side_eda(config_path, force=force, target_team=target_team, target_map=target_map)
        rerun_runtime = perf_counter() - started

    current = load_current_datasets(project_root)
    if baseline_mode == "create":
        validate_stage_8_2_ready(project_root)
        if not dry_run:
            create_baseline(current, baseline_dir, project_root=project_root, force=force)
    elif baseline_mode != DEFAULT_BASELINE_MODE:
        raise ValueError(f"Unsupported baseline_mode: {baseline_mode}")

    baseline_manifest = load_baseline_manifest(baseline_dir)
    baseline = load_baseline_datasets(baseline_manifest)
    frames = compare_gate(
        baseline,
        current,
        baseline_manifest,
        target_team=target_team,
        target_map=target_map,
        project_root=project_root,
        float_atol=float_atol,
        float_rtol=float_rtol,
        strict=strict,
        rerun_requested=rerun,
        rerun_completed=rerun and not dry_run,
        rerun_runtime_seconds=rerun_runtime,
    )
    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_outputs(frames, output_dir, force=force))
        outputs["report"] = write_text(build_report(frames), project_root / "docs" / "mirage_regression_gate.md", force=force)
        outputs["notebook"] = write_text(build_notebook_json(), project_root / "notebooks" / "17_mirage_regression_gate.ipynb", force=force)
    summary_frame = frames["mirage_regression_summary"]
    summary = {
        "datasets_checked": int(summary_frame.loc[0, "datasets_checked"]) if not summary_frame.empty else 0,
        "datasets_failed": int(summary_frame.loc[0, "datasets_failed"]) if not summary_frame.empty else 0,
        "critical_checks_failed": int(summary_frame.loc[0, "critical_checks_failed"]) if not summary_frame.empty else 0,
        "ready_for_new_map_onboarding": int(bool(frames["mirage_regression_audit"].loc[0, "ready_for_new_map_onboarding"])),
    }
    return frames, outputs, summary


def load_current_datasets(project_root: Path) -> dict[str, pd.DataFrame]:
    frames = {}
    for spec in DATASET_SPECS:
        path = project_root / "data" / spec.relative_path
        frames[spec.dataset_name] = read_catalog(path) if path.exists() else pd.DataFrame()
    return frames


def create_baseline(current: dict[str, pd.DataFrame], baseline_dir: Path, *, project_root: Path, force: bool) -> pd.DataFrame:
    manifest_path = baseline_dir / "baseline_manifest.parquet"
    if manifest_path.exists() and not force:
        raise FileExistsError("Baseline already exists. Pass --force with --baseline-mode create to overwrite it explicitly.")
    snapshot_dir = ensure_dir(baseline_dir / "snapshots")
    rows = []
    created_at = now_utc()
    for spec in DATASET_SPECS:
        frame = current.get(spec.dataset_name, pd.DataFrame())
        snapshot_path = snapshot_dir / f"{spec.dataset_name}.parquet"
        if force or not snapshot_path.exists():
            frame.to_parquet(snapshot_path, index=False)
        rows.append(
            {
                "baseline_version": BASELINE_VERSION,
                "dataset_name": spec.dataset_name,
                "dataset_path": str(snapshot_path),
                "row_count": len(frame),
                "column_count": len(frame.columns),
                "schema_hash": schema_hash(frame),
                "content_hash": content_hash(frame, list(spec.key_columns)),
                "key_columns": "|".join(spec.key_columns),
                "comparison_policy": "strict_logical_content",
                "created_at": created_at,
                "source_stage": spec.source_stage,
                "notes": "First map-ready Mirage MVP baseline.",
            }
        )
    for path in CONFIG_SNAPSHOTS:
        absolute = project_root / path
        rows.append(
            {
                "baseline_version": BASELINE_VERSION,
                "dataset_name": f"config:{path.as_posix()}",
                "dataset_path": str(absolute),
                "row_count": 1 if absolute.exists() else 0,
                "column_count": 1,
                "schema_hash": "config_file",
                "content_hash": file_hash(absolute) if absolute.exists() else "",
                "key_columns": "path",
                "comparison_policy": "content_hash",
                "created_at": created_at,
                "source_stage": "config_snapshot",
                "notes": "Configuration file content fingerprint.",
            }
        )
    manifest = pd.DataFrame(rows)
    write_pair(manifest, baseline_dir / "baseline_manifest", force=True)
    return manifest


def validate_stage_8_2_ready(project_root: Path) -> None:
    audit_path = project_root / "data/gold/feature_audit/map_feature_refactor_audit.parquet"
    audit = read_catalog(audit_path)
    if audit.empty or not bool(audit.iloc[0].get("map_feature_engine_ready")) or str(audit.iloc[0].get("status")) != "ok":
        raise ValueError("Stage 8.2 audit must be ok with map_feature_engine_ready=true before creating a regression baseline.")


def load_baseline_manifest(baseline_dir: Path) -> pd.DataFrame:
    path = baseline_dir / "baseline_manifest.parquet"
    if not path.exists():
        raise FileNotFoundError(
            "Mirage regression baseline not found. Create it explicitly with: "
            "python -m src.validation.mirage_regression_gate --config configs/project.yaml --baseline-mode create --force"
        )
    return read_catalog(path)


def load_baseline_datasets(manifest: pd.DataFrame) -> dict[str, pd.DataFrame]:
    frames = {}
    dataset_rows = manifest[~manifest["dataset_name"].astype(str).str.startswith("config:")]
    for _, row in dataset_rows.iterrows():
        path = Path(str(row["dataset_path"]))
        frames[str(row["dataset_name"])] = read_catalog(path) if path.exists() else pd.DataFrame()
    return frames


def compare_gate(
    baseline: dict[str, pd.DataFrame],
    current: dict[str, pd.DataFrame],
    baseline_manifest: pd.DataFrame,
    *,
    target_team: str,
    target_map: str,
    project_root: Path,
    float_atol: float,
    float_rtol: float,
    strict: bool,
    rerun_requested: bool,
    rerun_completed: bool,
    rerun_runtime_seconds: float | None,
) -> dict[str, pd.DataFrame]:
    schema = build_schema_comparison(baseline, current, strict=strict)
    row_identity = build_row_identity_comparison(baseline, current)
    feature_values = build_feature_value_comparison(baseline, current, float_atol=float_atol, float_rtol=float_rtol)
    region = build_region_timeline_comparison(baseline, current)
    round_state = build_round_state_comparison(baseline, current)
    side = build_side_dataset_comparison(baseline, current)
    candidate = build_candidate_compatibility(baseline, current, float_atol=float_atol, float_rtol=float_rtol)
    dataset = build_dataset_comparison(baseline, current, schema, row_identity, feature_values)
    invariants = build_invariant_checks(baseline, current, candidate, region, round_state, side)
    failures = build_failures(schema, row_identity, feature_values, region, round_state, side, candidate, invariants)
    audit = build_audit(
        dataset,
        schema,
        row_identity,
        feature_values,
        invariants,
        candidate,
        failures,
        baseline_manifest,
        project_root=project_root,
        target_team=target_team,
        target_map=target_map,
        rerun_requested=rerun_requested,
        rerun_completed=rerun_completed,
        rerun_runtime_seconds=rerun_runtime_seconds,
    )
    summary = build_summary(dataset, invariants, candidate, audit, target_team=target_team, target_map=target_map, baseline_manifest=baseline_manifest)
    return {
        "mirage_regression_summary": summary,
        "mirage_dataset_comparison": dataset,
        "mirage_schema_comparison": schema,
        "mirage_row_identity_comparison": row_identity,
        "mirage_feature_value_comparison": feature_values,
        "mirage_region_timeline_comparison": region,
        "mirage_round_state_comparison": round_state,
        "mirage_side_dataset_comparison": side,
        "mirage_candidate_input_compatibility": candidate,
        "mirage_invariant_checks": invariants,
        "mirage_regression_failures": failures,
        "mirage_regression_audit": audit,
    }


def build_schema_comparison(baseline: dict[str, pd.DataFrame], current: dict[str, pd.DataFrame], *, strict: bool) -> pd.DataFrame:
    rows = []
    for spec in DATASET_SPECS:
        before = baseline.get(spec.dataset_name, pd.DataFrame())
        after = current.get(spec.dataset_name, pd.DataFrame())
        columns = list(dict.fromkeys([*before.columns, *after.columns]))
        for column in columns:
            exists_before = column in before.columns
            exists_after = column in after.columns
            order_before = list(before.columns).index(column) if exists_before else None
            order_after = list(after.columns).index(column) if exists_after else None
            dtype_before = str(before[column].dtype) if exists_before else None
            dtype_after = str(after[column].dtype) if exists_after else None
            ok = exists_before and exists_after and dtype_before == dtype_after and (not strict or order_before == order_after)
            status = "ok" if ok else "failed"
            rows.append(
                {
                    "dataset_name": spec.dataset_name,
                    "column_name": column,
                    "baseline_dtype": dtype_before,
                    "current_dtype": dtype_after,
                    "exists_baseline": exists_before,
                    "exists_current": exists_after,
                    "column_order_baseline": order_before,
                    "column_order_current": order_after,
                    "status": status,
                    "notes": "Schema exact match." if ok else "Column presence, dtype, or order differs.",
                }
            )
    return pd.DataFrame(rows)


def build_row_identity_comparison(baseline: dict[str, pd.DataFrame], current: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for spec in DATASET_SPECS:
        before = baseline.get(spec.dataset_name, pd.DataFrame())
        after = current.get(spec.dataset_name, pd.DataFrame())
        keys = available_keys(spec, before, after)
        before_keys = key_frame(before, keys)
        after_keys = key_frame(after, keys)
        missing = len(before_keys.merge(after_keys, how="left", indicator=True).query("_merge == 'left_only'")) if not before_keys.empty else 0
        extra = len(after_keys.merge(before_keys, how="left", indicator=True).query("_merge == 'left_only'")) if not after_keys.empty else 0
        duplicate_before = int(before_keys.duplicated().sum()) if not before_keys.empty else 0
        duplicate_after = int(after_keys.duplicated().sum()) if not after_keys.empty else 0
        exact = missing == 0 and extra == 0 and duplicate_before == 0 and duplicate_after == 0 and len(before) == len(after)
        rows.append(
            {
                "dataset_name": spec.dataset_name,
                "key_columns": "|".join(keys),
                "baseline_keys": len(before_keys),
                "current_keys": len(after_keys),
                "missing_keys": missing,
                "extra_keys": extra,
                "duplicate_keys_baseline": duplicate_before,
                "duplicate_keys_current": duplicate_after,
                "exact_key_match": exact,
                "status": "ok" if exact else "failed",
            }
        )
    return pd.DataFrame(rows)


def build_feature_value_comparison(
    baseline: dict[str, pd.DataFrame],
    current: dict[str, pd.DataFrame],
    *,
    float_atol: float,
    float_rtol: float,
) -> pd.DataFrame:
    before = baseline.get("round_features_mvp", pd.DataFrame())
    after = current.get("round_features_mvp", pd.DataFrame())
    candidates = candidate_feature_names(current.get("candidate_model_feature_set", pd.DataFrame()))
    rows = []
    before_aligned, after_aligned = align_on_keys(before, after, ["round_feature_id"])
    for column in sorted(set(before.columns) | set(after.columns)):
        if column not in before.columns or column not in after.columns:
            rows.append(value_row(column, None, None, True, len(before_aligned), failed=True, candidate=column in candidates, notes="Column missing."))
            continue
        comparison = compare_series(before_aligned[column], after_aligned[column], float_atol=float_atol, float_rtol=float_rtol)
        rows.append(
            value_row(
                column,
                before_aligned[column],
                after_aligned[column],
                comparison["exact_match"],
                len(before_aligned),
                failed=not comparison["within_tolerance"],
                candidate=column in candidates,
                notes="Compared round_features_mvp.",
                comparison=comparison,
            )
        )
    return pd.DataFrame(rows)


def build_region_timeline_comparison(baseline: dict[str, pd.DataFrame], current: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name in ["region_presence_by_round", "round_region_timeline"]:
        before = baseline.get(name, pd.DataFrame())
        after = current.get(name, pd.DataFrame())
        keys = ["round_feature_id", "window_type", "window_start", "window_end", "region_name", "region_group"]
        before_aligned, after_aligned = align_on_keys(before, after, keys)
        region_changes = changed_count(before_aligned.get("region_name"), after_aligned.get("region_name"))
        semantic_changes = changed_count(before_aligned.get("region_group"), after_aligned.get("region_group"))
        identity = row_identity_for_name(name, baseline, current)
        exact = region_changes == 0 and semantic_changes == 0 and identity["status"] == "ok" and len(before) == len(after)
        rows.append(
            {
                "dataset_name": name,
                "rounds_compared": nunique(before_aligned, "round_feature_id"),
                "players_compared": nunique(before_aligned, "steamid"),
                "time_rows_baseline": len(before),
                "time_rows_current": len(after),
                "region_assignment_changes": region_changes,
                "semantic_assignment_changes": semantic_changes,
                "missing_region_rows": int(identity["missing_keys"]),
                "extra_region_rows": int(identity["extra_keys"]),
                "exact_match": exact,
                "status": "ok" if exact else "failed",
                "notes": "Spatial outputs unchanged." if exact else "Spatial row identity or region assignment changed.",
            }
        )
    return pd.DataFrame(rows)


def build_round_state_comparison(baseline: dict[str, pd.DataFrame], current: dict[str, pd.DataFrame]) -> pd.DataFrame:
    before = baseline.get("round_state_resolved", pd.DataFrame())
    after = current.get("round_state_resolved", pd.DataFrame())
    before_aligned, after_aligned = align_on_keys(before, after, ["round_id"])
    side_changes = changed_count(before_aligned.get("target_team_side"), after_aligned.get("target_team_side"))
    label_changes = changed_count(before_aligned.get("target_site_model_label"), after_aligned.get("target_site_model_label"))
    bombsite_changes = changed_count(before_aligned.get("bombsite"), after_aligned.get("bombsite"))
    confidence_changes = changed_count(before_aligned.get("label_confidence"), after_aligned.get("label_confidence"))
    no_plant_changes = changed_count(before_aligned.get("bomb_planted"), after_aligned.get("bomb_planted"))
    exact = all(value == 0 for value in [side_changes, label_changes, bombsite_changes, confidence_changes, no_plant_changes]) and len(before) == len(after)
    return pd.DataFrame(
        [
            {
                "rounds_compared": len(before_aligned),
                "side_changes": side_changes,
                "plant_label_changes": label_changes,
                "target_team_side_changes": side_changes,
                "bombsite_changes": bombsite_changes,
                "confidence_changes": confidence_changes,
                "no_plant_changes": no_plant_changes,
                "exact_match": exact,
                "status": "ok" if exact else "failed",
            }
        ]
    )


def build_side_dataset_comparison(baseline: dict[str, pd.DataFrame], current: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name in ["round_features_t_side_all", "round_features_t_side_planted", "round_features_ct_side"]:
        before = baseline.get(name, pd.DataFrame())
        after = current.get(name, pd.DataFrame())
        before_ids = set(before.get("round_id", pd.Series(dtype="object")).astype(str))
        after_ids = set(after.get("round_id", pd.Series(dtype="object")).astype(str))
        feature_columns_match = list(before.columns) == list(after.columns)
        label_distribution_match = label_counts(before).equals(label_counts(after))
        ok = len(before) == len(after) and before_ids == after_ids and feature_columns_match and label_distribution_match
        rows.append(
            {
                "dataset_name": name.removeprefix("round_features_"),
                "rows_baseline": len(before),
                "rows_current": len(after),
                "row_delta": len(after) - len(before),
                "round_ids_match": before_ids == after_ids,
                "feature_columns_match": feature_columns_match,
                "label_distribution_match": label_distribution_match,
                "status": "ok" if ok else "failed",
                "notes": "Side dataset unchanged." if ok else "Side dataset rows, IDs, columns, or labels changed.",
            }
        )
    return pd.DataFrame(rows)


def build_candidate_compatibility(
    baseline: dict[str, pd.DataFrame],
    current: dict[str, pd.DataFrame],
    *,
    float_atol: float,
    float_rtol: float,
) -> pd.DataFrame:
    feature_set = current.get("candidate_model_feature_set", pd.DataFrame())
    selection = current.get("candidate_model_selection", pd.DataFrame())
    before = baseline.get("round_features_t_side_planted", pd.DataFrame())
    after = current.get("round_features_t_side_planted", pd.DataFrame())
    names = candidate_feature_names(feature_set)
    found = [name for name in names if name in after.columns]
    missing = sorted(set(names) - set(found))
    extra = sorted(set(after.columns) - set(before.columns))
    before_aligned, after_aligned = align_on_keys(before, after, ["round_feature_id"])
    feature_values_match = True
    for name in found:
        comparison = compare_series(before_aligned[name], after_aligned[name], float_atol=float_atol, float_rtol=float_rtol)
        feature_values_match = feature_values_match and bool(comparison["within_tolerance"])
    labels_equal = compare_series(before_aligned.get("target_site_model_label", pd.Series(dtype="object")), after_aligned.get("target_site_model_label", pd.Series(dtype="object")), float_atol=float_atol, float_rtol=float_rtol)["exact_match"]
    row_identity_match = len(before) == len(after) and set(before.get("round_feature_id", [])) == set(after.get("round_feature_id", []))
    compatible = len(missing) == 0 and len(before) == len(after) and row_identity_match and feature_values_match and labels_equal
    selected = selection.iloc[0] if not selection.empty else {}
    return pd.DataFrame(
        [
            {
                "candidate_id": selected.get("candidate_id", "unknown"),
                "candidate_horizon": selected.get("candidate_horizon_seconds", feature_set.get("horizon_seconds", pd.Series([None])).iloc[0] if not feature_set.empty else None),
                "candidate_feature_set": selected.get("candidate_feature_set", "unknown"),
                "candidate_model": selected.get("candidate_model_name", "unknown"),
                "expected_feature_count": len(names),
                "found_feature_count": len(found),
                "missing_features": "|".join(missing),
                "extra_features": "|".join(extra),
                "candidate_rows_baseline": len(before),
                "candidate_rows_current": len(after),
                "row_identity_match": row_identity_match,
                "feature_values_match": feature_values_match,
                "label_match": labels_equal,
                "compatible": compatible,
                "status": "ok" if compatible else "failed",
                "notes": "Candidate input unchanged." if compatible else "Candidate input rows, labels, or feature values changed.",
            }
        ]
    )


def build_dataset_comparison(
    baseline: dict[str, pd.DataFrame],
    current: dict[str, pd.DataFrame],
    schema: pd.DataFrame,
    row_identity: pd.DataFrame,
    feature_values: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    value_status = "ok" if (feature_values["status"] == "ok").all() else "failed"
    for spec in DATASET_SPECS:
        before = baseline.get(spec.dataset_name, pd.DataFrame())
        after = current.get(spec.dataset_name, pd.DataFrame())
        schema_match = not (schema[(schema["dataset_name"] == spec.dataset_name) & (schema["status"] == "failed")].shape[0])
        identity_row = row_identity[row_identity["dataset_name"] == spec.dataset_name]
        row_match = bool(identity_row.iloc[0]["exact_key_match"]) if not identity_row.empty else False
        value_match = value_status == "ok" if spec.dataset_name == "round_features_mvp" else content_hash(before, list(spec.key_columns)) == content_hash(after, list(spec.key_columns))
        ok = schema_match and row_match and value_match
        rows.append(
            {
                "dataset_name": spec.dataset_name,
                "baseline_path": spec.relative_path.as_posix(),
                "current_path": spec.relative_path.as_posix(),
                "rows_baseline": len(before),
                "rows_current": len(after),
                "row_delta": len(after) - len(before),
                "columns_baseline": len(before.columns),
                "columns_current": len(after.columns),
                "column_delta": len(after.columns) - len(before.columns),
                "schema_match": schema_match,
                "row_identity_match": row_match,
                "value_match": value_match,
                "status": "ok" if ok else "failed",
                "notes": "Dataset unchanged." if ok else "Dataset schema, row identity, or content changed.",
            }
        )
    return pd.DataFrame(rows)


def build_invariant_checks(
    baseline: dict[str, pd.DataFrame],
    current: dict[str, pd.DataFrame],
    candidate: pd.DataFrame,
    region: pd.DataFrame,
    round_state: pd.DataFrame,
    side: pd.DataFrame,
) -> pd.DataFrame:
    checks = []
    add_count_check(checks, "eligible_demo_count_unchanged", "parse", "Feature eligible demo count unchanged.", len(baseline["feature_eligible_demos"]), len(current["feature_eligible_demos"]))
    add_count_check(checks, "feature_round_count_unchanged", "features", "Round feature row count unchanged.", len(baseline["round_features_mvp"]), len(current["round_features_mvp"]))
    add_count_check(checks, "t_side_round_count_unchanged", "side", "T-side round count unchanged.", len(baseline["round_features_t_side_all"]), len(current["round_features_t_side_all"]))
    add_count_check(checks, "t_side_planted_count_unchanged", "side", "T-side planted count unchanged.", len(baseline["round_features_t_side_planted"]), len(current["round_features_t_side_planted"]))
    add_count_check(checks, "plant_A_count_unchanged", "labels", "Plant A count unchanged.", label_count(baseline["round_features_t_side_planted"], "A"), label_count(current["round_features_t_side_planted"], "A"))
    add_count_check(checks, "plant_B_count_unchanged", "labels", "Plant B count unchanged.", label_count(baseline["round_features_t_side_planted"], "B"), label_count(current["round_features_t_side_planted"], "B"))
    add_count_check(checks, "no_plant_count_unchanged", "labels", "No-plant count unchanged.", no_plant_count(baseline["round_features_t_side_all"]), no_plant_count(current["round_features_t_side_all"]))
    add_count_check(checks, "feature_column_count_unchanged", "schema", "Feature column count unchanged.", len(baseline["round_features_mvp"].columns), len(current["round_features_mvp"].columns))
    add_count_check(checks, "candidate_feature_count_unchanged", "candidate", "Candidate feature count unchanged.", int(candidate.iloc[0]["expected_feature_count"]), int(candidate.iloc[0]["found_feature_count"]))
    add_count_check(checks, "candidate_rows_unchanged", "candidate", "Candidate rows unchanged.", int(candidate.iloc[0]["candidate_rows_baseline"]), int(candidate.iloc[0]["candidate_rows_current"]))
    add_bool_check(checks, "candidate_labels_unchanged", "candidate", "Candidate labels unchanged.", bool(candidate.iloc[0]["label_match"]))
    add_bool_check(checks, "region_timeline_unchanged", "spatial", "Region timeline unchanged.", bool((region["status"] == "ok").all()))
    add_bool_check(checks, "round_state_unchanged", "round_state", "Round state unchanged.", bool(round_state.iloc[0]["exact_match"]))
    add_bool_check(checks, "side_datasets_unchanged", "side", "Side datasets unchanged.", bool((side["status"] == "ok").all()))
    return pd.DataFrame(checks)


def build_failures(*frames: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for frame in frames:
        if frame.empty or "status" not in frame.columns:
            continue
        failed = frame[frame["status"].isin(["failed", "breaking_change"])]
        for index, row in failed.head(500).iterrows():
            rows.append(
                {
                    "failure_id": f"failure_{len(rows) + 1}",
                    "dataset_name": row.get("dataset_name", row.get("category", "gate")),
                    "failure_type": row.get("comparison_type", row.get("check_id", "regression_difference")),
                    "column_name": row.get("column_name", row.get("feature_name")),
                    "row_key": row.get("key_columns", row.get("check_id")),
                    "baseline_value": row.get("expected_value", row.get("rows_baseline", row.get("baseline_dtype"))),
                    "current_value": row.get("observed_value", row.get("rows_current", row.get("current_dtype"))),
                    "difference": row.get("changed_value_count", row.get("row_delta")),
                    "critical": bool(row.get("critical", True)),
                    "recommended_action": "Inspect the upstream stage that produced this artifact before onboarding a new map.",
                }
            )
    return pd.DataFrame(rows, columns=["failure_id", "dataset_name", "failure_type", "column_name", "row_key", "baseline_value", "current_value", "difference", "critical", "recommended_action"])


def build_audit(
    dataset: pd.DataFrame,
    schema: pd.DataFrame,
    row_identity: pd.DataFrame,
    feature_values: pd.DataFrame,
    invariants: pd.DataFrame,
    candidate: pd.DataFrame,
    failures: pd.DataFrame,
    baseline_manifest: pd.DataFrame,
    *,
    project_root: Path,
    target_team: str,
    target_map: str,
    rerun_requested: bool,
    rerun_completed: bool,
    rerun_runtime_seconds: float | None,
) -> pd.DataFrame:
    stage82 = stage_8_2_ready(project_root)
    critical_failures = int((failures["critical"] == True).sum()) if not failures.empty else 0  # noqa: E712
    warnings = int((dataset["status"] == "warning").sum()) if "status" in dataset.columns else 0
    ready = bool(critical_failures == 0 and stage82 and candidate.iloc[0]["compatible"])
    return pd.DataFrame(
        [
            {
                "audit_id": "mirage_regression_gate",
                "baseline_version": baseline_manifest["baseline_version"].iloc[0],
                "target_team": target_team,
                "target_map": target_map,
                "datasets_expected": len(DATASET_SPECS),
                "datasets_found": int((dataset["rows_current"] >= 0).sum()),
                "datasets_missing": int((dataset["rows_current"] == 0).sum()),
                "schema_checks": len(schema),
                "row_checks": len(row_identity),
                "value_checks": len(feature_values),
                "invariant_checks": len(invariants),
                "candidate_checks": 1,
                "critical_failures": critical_failures,
                "warnings": warnings,
                "noncritical_differences": 0,
                "rerun_requested": rerun_requested,
                "rerun_completed": rerun_completed,
                "rerun_runtime_seconds": rerun_runtime_seconds,
                "report_written": True,
                "baseline_loaded": True,
                "stage_8_2_ready": stage82,
                "ready_for_new_map_onboarding": ready,
                "status": "passed" if ready else "failed",
                "created_at": now_utc(),
            }
        ]
    )


def build_summary(
    dataset: pd.DataFrame,
    invariants: pd.DataFrame,
    candidate: pd.DataFrame,
    audit: pd.DataFrame,
    *,
    target_team: str,
    target_map: str,
    baseline_manifest: pd.DataFrame,
) -> pd.DataFrame:
    failed = int((dataset["status"] == "failed").sum())
    warning = int((dataset["status"] == "warning").sum())
    passed = int((dataset["status"] == "ok").sum())
    critical_failed = int((invariants["passed"] == False).sum())  # noqa: E712
    ready = bool(audit.iloc[0]["ready_for_new_map_onboarding"])
    return pd.DataFrame(
        [
            {
                "gate_id": "mirage_regression_gate",
                "baseline_version": baseline_manifest["baseline_version"].iloc[0],
                "target_team": target_team,
                "target_map": target_map,
                "datasets_checked": len(dataset),
                "datasets_passed": passed,
                "datasets_warning": warning,
                "datasets_failed": failed,
                "critical_checks": len(invariants),
                "critical_checks_passed": int((invariants["passed"] == True).sum()),  # noqa: E712
                "critical_checks_failed": critical_failed,
                "candidate_compatible": bool(candidate.iloc[0]["compatible"]),
                "feature_engine_compatible": failed == 0,
                "round_state_compatible": bool(invariants[invariants["check_id"] == "round_state_unchanged"]["passed"].iloc[0]),
                "side_datasets_compatible": bool(invariants[invariants["check_id"] == "side_datasets_unchanged"]["passed"].iloc[0]),
                "overall_status": "passed" if ready else "failed",
                "created_at": now_utc(),
            }
        ]
    )


def stage_8_2_ready(project_root: Path) -> bool:
    path = project_root / "data/gold/feature_audit/map_feature_refactor_audit.parquet"
    if not path.exists():
        return False
    audit = read_catalog(path)
    return bool(not audit.empty and audit.iloc[0].get("status") == "ok" and audit.iloc[0].get("map_feature_engine_ready") == True)  # noqa: E712


def available_keys(spec: DatasetSpec, before: pd.DataFrame, after: pd.DataFrame) -> list[str]:
    keys = [key for key in spec.key_columns if key in before.columns and key in after.columns]
    return keys or [column for column in ["round_feature_id", "round_id", "parse_id", "candidate_id", "feature_name"] if column in before.columns and column in after.columns]


def key_frame(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if frame.empty or not keys:
        return pd.DataFrame(columns=keys)
    return frame[keys].astype("string").fillna("<NA>").drop_duplicates()


def row_identity_for_name(name: str, baseline: dict[str, pd.DataFrame], current: dict[str, pd.DataFrame]) -> pd.Series:
    row_identity = build_row_identity_comparison(baseline, current)
    return row_identity[row_identity["dataset_name"] == name].iloc[0]


def align_on_keys(before: pd.DataFrame, after: pd.DataFrame, keys: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = [key for key in keys if key in before.columns and key in after.columns]
    if not keys:
        count = min(len(before), len(after))
        return before.head(count).reset_index(drop=True), after.head(count).reset_index(drop=True)
    before_sorted = before.sort_values(keys, kind="mergesort")
    after_sorted = after.sort_values(keys, kind="mergesort")
    before_keyed = before_sorted.set_index(keys, drop=False)
    after_keyed = after_sorted.set_index(keys, drop=False)
    common = before_keyed.index.intersection(after_keyed.index)
    return before_keyed.loc[common].reset_index(drop=True), after_keyed.loc[common].reset_index(drop=True)


def compare_series(before: pd.Series, after: pd.Series, *, float_atol: float, float_rtol: float) -> dict[str, object]:
    before = before.reset_index(drop=True)
    after = after.reset_index(drop=True)
    if len(before) != len(after):
        return {"changed_value_count": max(len(before), len(after)), "changed_value_share": 1.0, "max_abs_difference": None, "mean_abs_difference": None, "p99_abs_difference": None, "exact_match": False, "within_tolerance": False}
    both_missing = before.isna() & after.isna()
    numeric = pd.api.types.is_numeric_dtype(before) and pd.api.types.is_numeric_dtype(after) and not pd.api.types.is_bool_dtype(before) and not pd.api.types.is_bool_dtype(after)
    if numeric:
        before_num = pd.to_numeric(before, errors="coerce")
        after_num = pd.to_numeric(after, errors="coerce")
        close = np.isclose(before_num, after_num, atol=float_atol, rtol=float_rtol, equal_nan=True)
        diffs = (before_num - after_num).abs()
        valid = diffs[~both_missing & diffs.notna()]
        changed = int((~close).sum())
        return {
            "changed_value_count": changed,
            "changed_value_share": changed / len(before) if len(before) else 0,
            "max_abs_difference": float(valid.max()) if not valid.empty else 0.0,
            "mean_abs_difference": float(valid.mean()) if not valid.empty else 0.0,
            "p99_abs_difference": float(valid.quantile(0.99)) if not valid.empty else 0.0,
            "exact_match": changed == 0,
            "within_tolerance": changed == 0,
        }
    equal = (before.astype("object") == after.astype("object")) | both_missing
    changed = int((~equal).sum())
    return {"changed_value_count": changed, "changed_value_share": changed / len(before) if len(before) else 0, "max_abs_difference": None, "mean_abs_difference": None, "p99_abs_difference": None, "exact_match": changed == 0, "within_tolerance": changed == 0}


def value_row(
    feature_name: str,
    before: pd.Series | None,
    after: pd.Series | None,
    exact_match: bool,
    rows_compared: int,
    *,
    failed: bool,
    candidate: bool,
    notes: str,
    comparison: dict[str, object] | None = None,
) -> dict[str, object]:
    comparison = comparison or {}
    return {
        "feature_name": feature_name,
        "feature_family": None,
        "map_scope": None,
        "candidate_feature": candidate,
        "rows_compared": rows_compared,
        "nulls_baseline": int(before.isna().sum()) if before is not None else None,
        "nulls_current": int(after.isna().sum()) if after is not None else None,
        "changed_value_count": comparison.get("changed_value_count", rows_compared if failed else 0),
        "changed_value_share": comparison.get("changed_value_share", 1.0 if failed else 0.0),
        "max_abs_difference": comparison.get("max_abs_difference"),
        "mean_abs_difference": comparison.get("mean_abs_difference"),
        "p99_abs_difference": comparison.get("p99_abs_difference"),
        "exact_match": exact_match,
        "within_tolerance": comparison.get("within_tolerance", exact_match),
        "status": "failed" if failed else "ok",
        "notes": notes,
    }


def changed_count(before: pd.Series | None, after: pd.Series | None) -> int:
    if before is None or after is None:
        return 0
    comparison = compare_series(before, after, float_atol=0, float_rtol=0)
    return int(comparison["changed_value_count"])


def nunique(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].nunique()) if column in frame.columns else 0


def label_counts(frame: pd.DataFrame) -> pd.Series:
    if "target_site_model_label" not in frame.columns:
        return pd.Series(dtype=int)
    return frame["target_site_model_label"].value_counts(dropna=False).sort_index()


def label_count(frame: pd.DataFrame, label: str) -> int:
    return int((frame.get("target_site_model_label", pd.Series(dtype="object")) == label).sum())


def no_plant_count(frame: pd.DataFrame) -> int:
    labels = frame.get("target_site_model_label", pd.Series(dtype="object"))
    return int((~labels.isin(["A", "B"])).sum())


def candidate_feature_names(feature_set: pd.DataFrame) -> list[str]:
    if feature_set.empty or "feature_name" not in feature_set.columns:
        return []
    return [name for name in feature_set["feature_name"].dropna().astype(str).tolist() if name != "__feature_set_summary__"]


def add_count_check(rows: list[dict[str, object]], check_id: str, category: str, description: str, expected: int, observed: int) -> None:
    passed = expected == observed
    rows.append({"check_id": check_id, "category": category, "description": description, "expected_value": expected, "observed_value": observed, "critical": True, "passed": passed, "severity": "critical" if not passed else "none", "status": "ok" if passed else "failed", "notes": None})


def add_bool_check(rows: list[dict[str, object]], check_id: str, category: str, description: str, passed: bool) -> None:
    rows.append({"check_id": check_id, "category": category, "description": description, "expected_value": True, "observed_value": passed, "critical": True, "passed": passed, "severity": "critical" if not passed else "none", "status": "ok" if passed else "failed", "notes": None})


def schema_hash(frame: pd.DataFrame) -> str:
    payload = [{"column": column, "dtype": str(frame[column].dtype)} for column in frame.columns]
    return sha256_text(json.dumps(payload, sort_keys=True))


def content_hash(frame: pd.DataFrame, keys: list[str]) -> str:
    if frame.empty:
        return sha256_text("empty")
    canonical = frame.copy()
    sort_keys = [key for key in keys if key in canonical.columns]
    if sort_keys:
        canonical = canonical.sort_values(sort_keys, kind="mergesort")
    canonical = canonical.reset_index(drop=True)
    text = canonical.map(cell_text).to_json(orient="split", date_format="iso", default_handler=str)
    return sha256_text(text)


def cell_text(value: object) -> str:
    if value is None:
        return "<NA>"
    try:
        if pd.isna(value):
            return "<NA>"
    except (TypeError, ValueError):
        pass
    return str(value)


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    outputs = {}
    for name in OUTPUT_NAMES:
        outputs.update(write_pair(frames[name], output_dir / name, force=force))
    return outputs


def write_pair(frame: pd.DataFrame, base_path: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(base_path.parent)
    frame = sanitize_for_parquet(frame)
    outputs = {}
    csv_path = base_path.with_suffix(".csv")
    parquet_path = base_path.with_suffix(".parquet")
    if force or not csv_path.exists():
        frame.to_csv(csv_path, index=False)
    if force or not parquet_path.exists():
        frame.to_parquet(parquet_path, index=False)
    outputs[csv_path.name] = csv_path
    outputs[parquet_path.name] = parquet_path
    return outputs


def sanitize_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            non_null = result[column].dropna()
            types = {type(value) for value in non_null.head(1000)}
            if len(types) > 1:
                result[column] = result[column].map(lambda value: None if value is None or pd.isna(value) else str(value))
    return result


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def build_report(frames: dict[str, pd.DataFrame]) -> str:
    audit = frames["mirage_regression_audit"].iloc[0]
    summary = frames["mirage_regression_summary"].iloc[0]
    return "\n".join(
        [
            "# Mirage Regression / Backward Compatibility Gate",
            "",
            "## Purpose",
            "Validate that the map-ready Mirage pipeline preserves the existing MVP behavior before onboarding a new map.",
            "",
            "## Baseline",
            f"Baseline version: `{summary['baseline_version']}`.",
            "",
            "## Configuration versions",
            "Configuration files are fingerprinted in the baseline manifest.",
            "",
            "## Datasets validated",
            markdown_table(frames["mirage_dataset_comparison"], ["dataset_name", "rows_baseline", "rows_current", "schema_match", "row_identity_match", "value_match", "status"]),
            "",
            "## Feature schema compatibility",
            markdown_table(frames["mirage_schema_comparison"][frames["mirage_schema_comparison"]["status"] != "ok"], ["dataset_name", "column_name", "baseline_dtype", "current_dtype", "status"]),
            "",
            "## Feature value compatibility",
            markdown_table(frames["mirage_feature_value_comparison"][frames["mirage_feature_value_comparison"]["status"] != "ok"], ["feature_name", "candidate_feature", "changed_value_count", "status"]),
            "",
            "## Spatial / region compatibility",
            markdown_table(frames["mirage_region_timeline_comparison"], list(frames["mirage_region_timeline_comparison"].columns)),
            "",
            "## Round state compatibility",
            markdown_table(frames["mirage_round_state_comparison"], list(frames["mirage_round_state_comparison"].columns)),
            "",
            "## Side dataset compatibility",
            markdown_table(frames["mirage_side_dataset_comparison"], list(frames["mirage_side_dataset_comparison"].columns)),
            "",
            "## Candidate input compatibility",
            markdown_table(frames["mirage_candidate_input_compatibility"], list(frames["mirage_candidate_input_compatibility"].columns)),
            "",
            "## Invariant checks",
            markdown_table(frames["mirage_invariant_checks"], ["check_id", "expected_value", "observed_value", "passed", "severity"]),
            "",
            "## Failures / warnings",
            markdown_table(frames["mirage_regression_failures"], list(frames["mirage_regression_failures"].columns)),
            "",
            "## Regression decision",
            f"overall_status: `{summary['overall_status']}`",
            "",
            "## New-map readiness",
            f"ready_for_new_map_onboarding: `{str(audit['ready_for_new_map_onboarding']).lower()}`",
            "",
            "## Next stage",
            "Next: Stage 8.4 -- First New Map Onboarding.",
            "",
        ]
    )


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 30) -> str:
    if frame.empty:
        return "_No rows._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def build_notebook_json() -> str:
    cells = [
        md("# Stage 8.3 -- Mirage Regression Gate"),
        code("from pathlib import Path\nimport pandas as pd\nBASE = Path('../data/gold/validation/mirage_regression_gate')\ndef load(name):\n    return pd.read_parquet(BASE / f'{name}.parquet')\nsummary = load('mirage_regression_summary')\ndatasets = load('mirage_dataset_comparison')\nschema = load('mirage_schema_comparison')\nfeatures = load('mirage_feature_value_comparison')\nregion = load('mirage_region_timeline_comparison')\nround_state = load('mirage_round_state_comparison')\nside = load('mirage_side_dataset_comparison')\ncandidate = load('mirage_candidate_input_compatibility')\ninvariants = load('mirage_invariant_checks')\nfailures = load('mirage_regression_failures')\naudit = load('mirage_regression_audit')"),
        md("## Regression Summary"),
        code("display(summary)"),
        md("## Dataset Comparison"),
        code("display(datasets)"),
        md("## Schema Differences"),
        code("display(schema[schema['status'] != 'ok'])"),
        md("## Feature Value Differences"),
        code("display(features[features['status'] != 'ok'])"),
        md("## Candidate Features"),
        code("display(candidate)"),
        md("## Region Timeline Comparison"),
        code("display(region)"),
        md("## Round State Comparison"),
        code("display(round_state)"),
        md("## Side Datasets"),
        code("display(side)"),
        md("## Invariants"),
        code("display(invariants)"),
        md("## Failures"),
        code("display(failures)"),
        md("## Audit"),
        code("display(audit)"),
        md("Next: onboard the first new map only if ready_for_new_map_onboarding is true."),
    ]
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.11"}}, "nbformat": 4, "nbformat_minor": 5}
    return json.dumps(notebook, indent=1) + "\n"


def md(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict[str, object]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Mirage regression gate summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Mirage regression/backward compatibility gate.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--baseline-mode", default=DEFAULT_BASELINE_MODE, choices=[DEFAULT_BASELINE_MODE, "create"])
    parser.add_argument("--float-atol", type=float, default=1e-9)
    parser.add_argument("--float-rtol", type=float, default=1e-9)
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--rerun", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_mirage_regression_gate(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        baseline_mode=args.baseline_mode,
        float_atol=args.float_atol,
        float_rtol=args.float_rtol,
        strict=args.strict,
        rerun=args.rerun,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
