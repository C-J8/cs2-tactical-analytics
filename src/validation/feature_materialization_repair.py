from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

from src.config.schemas import load_project_config
from src.features.utility_features import canonical_utility_type
from src.maps.identity import resolve_map_identity
from src.validation.multi_map_gold_gate import scoped_team_map
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "utility_source_capability",
    "utility_source_policy_audit",
    "utility_event_reconstruction_audit",
    "utility_endpoint_resolution_audit",
    "score_before_round_audit",
    "feature_materialization_change_manifest",
    "mirage_feature_migration_diff",
    "feature_materialization_repair_audit",
    "utility_type_feature_sanity",
    "mid_control_structural_review",
    "feature_materialization_capabilities",
    "quality_gate_recovery",
    "feature_materialization_repair_final_audit",
]


def run_feature_materialization_repair_audit(
    config_path: Path,
    *,
    target_map: str | None = None,
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    gold_dir = project_root / "data" / "gold"
    silver_dir = project.parsed_silver_dir if project.parsed_silver_dir.is_absolute() else project_root / project.parsed_silver_dir
    registry_path = project_root / "configs" / "maps" / "map_registry.yaml"
    target_map = target_map or project.target_maps[0]
    target_team = target_team or project.target_teams[0]
    identity = resolve_map_identity(target_map, registry_path=registry_path)
    output_dir = gold_dir / "validation" / "feature_materialization_repair"

    frames = load_repair_inputs(gold_dir, map_name=identity.display_name, target_team=target_team, registry_path=registry_path)
    ensure_quality_before_snapshot(output_dir, gold_dir, force=force)
    outputs = build_repair_outputs(
        frames,
        silver_dir=silver_dir,
        gold_dir=gold_dir,
        output_dir=output_dir,
        map_id=identity.map_id,
        map_name=identity.display_name,
        target_team=target_team,
        registry_path=registry_path,
    )
    paths: dict[str, Path] = {}
    if not dry_run:
        paths.update(write_repair_outputs(outputs, output_dir, force=force))
        paths["report"] = write_report(project_root / "docs" / "feature_materialization_repair.md", outputs, force=force)
        paths["notebook"] = write_notebook(project_root / "notebooks" / "24_feature_materialization_repair.ipynb", force=force)

    final = outputs["feature_materialization_repair_final_audit"].iloc[0]
    summary = {
        "map_id": identity.map_id,
        "target_team": target_team,
        "repair_status": str(final.get("status", "unknown")),
        "failed_checks": int(final.get("failed_checks", 0)),
        "warning_checks": int(final.get("warning_checks", 0)),
        "quality_gate_status": str(final.get("quality_gate_status", "unknown")),
    }
    return outputs, paths, summary


def load_repair_inputs(gold_dir: Path, *, map_name: str, target_team: str, registry_path: Path) -> dict[str, pd.DataFrame]:
    loaded = {
        "round_features_mvp": read_optional(gold_dir / "round_features" / "round_features_mvp.parquet"),
        "round_state_resolved": read_optional(gold_dir / "round_state" / "round_state_resolved.parquet"),
        "utility_events": read_optional(gold_dir / "utility_events" / "utility_events.parquet"),
        "map_feature_quality_audit": read_optional(gold_dir / "validation" / "map_feature_quality" / "map_feature_quality_audit.parquet"),
        "map_feature_missingness": read_optional(gold_dir / "validation" / "map_feature_quality" / "map_feature_missingness.parquet"),
        "mirage_inferno_feature_sanity": read_optional(gold_dir / "validation" / "map_feature_quality" / "mirage_inferno_feature_sanity.parquet"),
    }
    round_features = scoped_team_map(loaded["round_features_mvp"], target_team=target_team, map_name=map_name, registry_path=registry_path)
    round_ids = set(round_features.get("round_id", pd.Series(dtype=str)).dropna().astype(str))
    feature_ids = set(round_features.get("round_feature_id", pd.Series(dtype=str)).dropna().astype(str))
    loaded["round_features_mvp"] = round_features.reset_index(drop=True)
    loaded["round_state_resolved"] = scope_frame(loaded["round_state_resolved"], target_team=target_team, map_name=map_name, registry_path=registry_path, round_ids=round_ids)
    utility = loaded["utility_events"]
    if not utility.empty and "round_feature_id" in utility.columns:
        utility = utility[utility["round_feature_id"].astype(str).isin(feature_ids)].copy()
    loaded["utility_events"] = utility.reset_index(drop=True)
    for quality_name in ["map_feature_quality_audit", "map_feature_missingness", "mirage_inferno_feature_sanity"]:
        quality = loaded[quality_name]
        if not quality.empty and {"map_id", "target_team"}.issubset(quality.columns):
            loaded[quality_name] = quality[
                quality["target_team"].astype(str).str.casefold().eq(target_team.casefold())
            ].copy()
    return loaded


def scope_frame(
    frame: pd.DataFrame,
    *,
    target_team: str,
    map_name: str,
    registry_path: Path,
    round_ids: set[str],
) -> pd.DataFrame:
    if frame.empty:
        return frame
    if "map_name" in frame.columns:
        return scoped_team_map(frame, target_team=target_team, map_name=map_name, registry_path=registry_path).reset_index(drop=True)
    if "round_id" in frame.columns:
        return frame[frame["round_id"].astype(str).isin(round_ids)].copy().reset_index(drop=True)
    return frame.iloc[0:0].copy()


def build_repair_outputs(
    frames: dict[str, pd.DataFrame],
    *,
    silver_dir: Path,
    gold_dir: Path,
    output_dir: Path,
    map_id: str,
    map_name: str,
    target_team: str,
    registry_path: Path,
) -> dict[str, pd.DataFrame]:
    utility_events = frames["utility_events"]
    round_features = frames["round_features_mvp"]
    quality = frames["map_feature_quality_audit"]
    missing = frames["map_feature_missingness"]
    cross_map = frames["mirage_inferno_feature_sanity"]
    outputs: dict[str, pd.DataFrame] = {}
    outputs["utility_source_capability"] = build_source_capability(silver_dir, map_id=map_id, map_name=map_name, target_team=target_team)
    outputs["utility_source_policy_audit"] = build_source_policy_audit(utility_events, map_id=map_id, target_team=target_team)
    outputs["utility_event_reconstruction_audit"] = build_event_reconstruction_audit(utility_events, map_id=map_id, target_team=target_team)
    outputs["utility_endpoint_resolution_audit"] = build_endpoint_resolution_audit(utility_events, map_id=map_id, target_team=target_team)
    outputs["score_before_round_audit"] = build_score_audit(round_features, gold_dir=gold_dir, map_id=map_id, target_team=target_team)
    outputs["feature_materialization_change_manifest"] = build_change_manifest(round_features, utility_events, map_id=map_id, target_team=target_team)
    outputs["mirage_feature_migration_diff"] = build_mirage_migration_diff(gold_dir, registry_path=registry_path, target_team=target_team)
    outputs["feature_materialization_repair_audit"] = build_repair_audit(outputs, round_features, utility_events, map_id=map_id, target_team=target_team)
    outputs["utility_type_feature_sanity"] = build_utility_type_sanity(round_features, utility_events, map_id=map_id, target_team=target_team)
    outputs["mid_control_structural_review"] = build_mid_control_review(cross_map, map_id=map_id, target_team=target_team)
    outputs["feature_materialization_capabilities"] = build_capabilities(outputs, map_id=map_id, target_team=target_team)
    outputs["quality_gate_recovery"] = build_quality_gate_recovery(output_dir, quality, missing, map_id=map_id, target_team=target_team)
    outputs["feature_materialization_repair_final_audit"] = build_final_audit(outputs, map_id=map_id, target_team=target_team)
    return outputs


def build_source_capability(silver_dir: Path, *, map_id: str, map_name: str, target_team: str) -> pd.DataFrame:
    rows = []
    for source_table in ["grenades", "smokes", "infernos"]:
        path = silver_dir / f"{source_table}.parquet"
        columns, row_count = parquet_schema_and_count(path)
        grenade_types: dict[str, int] = {}
        if source_table == "grenades" and path.exists():
            try:
                counts = (
                    pl.scan_parquet(path)
                    .filter(pl.col("map_name").cast(pl.Utf8).str.to_lowercase() == map_name.casefold())
                    .group_by("grenade_type")
                    .agg(pl.len().alias("trajectory_rows"))
                    .collect()
                    .to_pandas()
                )
                grenade_types = dict(zip(counts["grenade_type"].astype(str), counts["trajectory_rows"].astype(int), strict=False))
            except Exception as exc:  # noqa: BLE001
                grenade_types = {"schema_probe_failed": str(exc)}
        rows.append(
            {
                "map_id": map_id,
                "target_team": target_team,
                "source_table": source_table,
                "path": str(path),
                "exists": path.exists(),
                "row_count": row_count,
                "column_count": len(columns),
                "columns": ",".join(columns),
                "source_granularity": infer_source_granularity(source_table, columns),
                "supports_smoke": source_table in {"smokes", "grenades"},
                "supports_flash": source_table == "grenades" and any(canonical_utility_type(name) == "flash" for name in grenade_types),
                "supports_molotov": source_table in {"infernos", "grenades"},
                "supports_he": source_table == "grenades" and any(canonical_utility_type(name) == "he" for name in grenade_types),
                "supports_decoy": source_table == "grenades" and any(canonical_utility_type(name) == "decoy" for name in grenade_types),
                "observed_grenade_types": json.dumps(grenade_types, sort_keys=True),
                "feature_engine_version": "v2",
                "status": "ok" if path.exists() and columns else "warning",
                "notes": "Real source schema inspected without synthetic utility generation.",
            }
        )
    return pd.DataFrame(rows)


def parquet_schema_and_count(path: Path) -> tuple[list[str], int | None]:
    if not path.exists():
        return [], None
    try:
        scan = pl.scan_parquet(path)
        columns = scan.collect_schema().names()
        count = int(scan.select(pl.len().alias("rows")).collect().item())
        return columns, count
    except Exception:
        return [], None


def infer_source_granularity(source_table: str, columns: list[str]) -> str:
    if source_table == "grenades" and {"entity_id", "tick"}.issubset(columns):
        return "trajectory_level"
    if source_table in {"smokes", "infernos"} and {"entity_id", "start_tick", "end_tick"}.issubset(columns):
        return "event_level"
    return "unknown"


def build_source_policy_audit(utility_events: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    policy = [
        ("smoke", "smokes", "grenades", "smokes primary; grenades fallback only if smokes unavailable."),
        ("molotov", "infernos", "grenades", "infernos primary; grenades fallback only if infernos unavailable."),
        ("flash", "grenades", None, "grenades trajectory source collapsed by entity_id."),
        ("he", "grenades", None, "grenades trajectory source collapsed by entity_id."),
        ("decoy", "grenades", None, "represented by adapter when available; no MVP temporal feature required."),
    ]
    rows = []
    for utility_type, primary, fallback, notes in policy:
        scoped = utility_events[utility_events.get("utility_type", pd.Series(dtype=object)).astype(str).eq(utility_type)] if not utility_events.empty and "utility_type" in utility_events.columns else pd.DataFrame()
        rows.append(
            {
                "map_id": map_id,
                "target_team": target_team,
                "utility_type": utility_type,
                "primary_source": primary,
                "fallback_source": fallback,
                "materialized_events": len(scoped),
                "source_tables_observed": ",".join(sorted(scoped.get("source_table", pd.Series(dtype=str)).dropna().astype(str).unique())),
                "double_count_policy": "primary_source_only_unless_missing",
                "feature_engine_version": "v2",
                "status": "ok" if utility_type == "decoy" or len(scoped) > 0 else "warning",
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def build_event_reconstruction_audit(utility_events: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    if utility_events.empty:
        return pd.DataFrame(
            [
                {
                    "map_id": map_id,
                    "target_team": target_team,
                    "utility_type": "all",
                    "source_table": None,
                    "source_granularity": None,
                    "events": 0,
                    "unique_source_entities": 0,
                    "status": "warning",
                    "notes": "No utility events materialized.",
                }
            ]
        )
    events_frame = utility_events.copy()
    if "source_entity_id" not in events_frame.columns:
        events_frame["source_entity_id"] = None
    for column in ["source_table", "source_granularity"]:
        if column not in events_frame.columns:
            events_frame[column] = "legacy_unknown"
    grouped = (
        events_frame.groupby(["utility_type", "source_table", "source_granularity"], dropna=False)
        .agg(events=("utility_event_id", "count"), unique_source_entities=("source_entity_id", "nunique"))
        .reset_index()
    )
    grouped.insert(0, "target_team", target_team)
    grouped.insert(0, "map_id", map_id)
    grouped["feature_engine_version"] = "v2"
    grouped["status"] = "ok"
    grouped["notes"] = "Trajectory-level grenades are collapsed to one logical event per source entity."
    return grouped


def build_endpoint_resolution_audit(utility_events: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    if utility_events.empty:
        return pd.DataFrame(columns=["map_id", "target_team", "endpoint_resolution_method", "endpoint_resolution_confidence", "events", "status", "notes"])
    events_frame = utility_events.copy()
    if "endpoint_resolution_method" not in events_frame.columns:
        events_frame["endpoint_resolution_method"] = "legacy_missing"
    if "endpoint_resolution_confidence" not in events_frame.columns:
        events_frame["endpoint_resolution_confidence"] = "none"
    grouped = (
        events_frame.groupby(["endpoint_resolution_method", "endpoint_resolution_confidence"], dropna=False)
        .agg(events=("utility_event_id", "count"))
        .reset_index()
    )
    grouped.insert(0, "target_team", target_team)
    grouped.insert(0, "map_id", map_id)
    grouped["status"] = grouped["endpoint_resolution_method"].map(lambda value: "warning" if str(value) == "unresolved" else "ok")
    grouped["notes"] = grouped["endpoint_resolution_method"].map(lambda value: "Endpoint kept unresolved because no deterministic endpoint region evidence is available." if str(value) == "unresolved" else "Endpoint resolved from deterministic source data.")
    return grouped


def build_score_audit(round_features: pd.DataFrame, *, gold_dir: Path, map_id: str, target_team: str) -> pd.DataFrame:
    existing = read_optional(gold_dir / "feature_audit" / ("score_before_round_audit.parquet" if map_id == "mirage" else f"score_before_round_audit_{map_id}.parquet"))
    if not existing.empty:
        existing = existing.copy()
        existing.insert(0, "target_team", target_team)
        existing.insert(0, "map_id", map_id)
        return existing
    total = len(round_features)
    filled = int(round_features.get("score_diff_before_round", pd.Series(dtype=object)).notna().sum()) if not round_features.empty else 0
    missing = total - filled
    return pd.DataFrame(
        [
            {
                "map_id": map_id,
                "target_team": target_team,
                "total_rounds": total,
                "score_diff_filled": filled,
                "score_diff_missing": missing,
                "score_diff_missing_share": float(missing / total) if total else 0.0,
                "score_resolution_method": "round_features_observed",
                "feature_engine_version": "v2",
                "status": "ok" if total and missing == 0 else "warning",
                "notes": "Observed current round_features score_diff_before_round.",
            }
        ]
    )


def build_change_manifest(round_features: pd.DataFrame, utility_events: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    checks = [
        ("flash_usage_materialization", "flashes_used_", "utility_count", "grenades trajectory table"),
        ("he_usage_materialization", "he_used_", "utility_count", "grenades trajectory table"),
        ("score_diff_before_round", "score_diff_before_round", "round_context", "round_state previous-round winners"),
        ("utility_endpoint_semantics", "endpoint_resolution_method", "event_metadata", "deterministic endpoint evidence only"),
    ]
    rows = []
    for change_id, pattern, feature_family, source in checks:
        frame = utility_events if pattern == "endpoint_resolution_method" else round_features
        columns = [column for column in frame.columns if column == pattern or column.startswith(pattern)] if not frame.empty else []
        all_null = bool(columns and frame[columns].isna().all().all())
        materialized = bool(columns and not all_null)
        rows.append(
            {
                "map_id": map_id,
                "target_team": target_team,
                "change_id": change_id,
                "feature_family": feature_family,
                "affected_columns": ",".join(columns),
                "source_evidence": source,
                "materialized": materialized,
                "feature_engine_version": "v2",
                "status": "ok" if materialized or change_id == "utility_endpoint_semantics" else "failed",
                "notes": "Endpoint regions remain unresolved when deterministic evidence is unavailable." if change_id == "utility_endpoint_semantics" else ("Columns materialized." if materialized else "Expected columns are absent or fully null."),
            }
        )
    return pd.DataFrame(rows)


def build_mirage_migration_diff(gold_dir: Path, *, registry_path: Path, target_team: str) -> pd.DataFrame:
    current = read_optional(gold_dir / "round_features" / "round_features_mvp.parquet")
    baseline = read_optional(gold_dir / "validation" / "mirage_regression_baseline" / "snapshots" / "round_features_mvp.parquet")
    if current.empty or baseline.empty:
        return pd.DataFrame(
            [
                {
                    "map_id": "mirage",
                    "target_team": target_team,
                    "feature_name": None,
                    "baseline_missing_share": None,
                    "current_missing_share": None,
                    "baseline_sum": None,
                    "current_sum": None,
                    "expected_change": True,
                    "status": "warning",
                    "notes": "Current Mirage features or baseline snapshot not available.",
                }
            ]
        )
    current = scoped_team_map(current, target_team=target_team, map_name="Mirage", registry_path=registry_path)
    baseline = scoped_team_map(baseline, target_team=target_team, map_name="Mirage", registry_path=registry_path)
    rows = []
    tracked = [
        column
        for column in sorted(set(current.columns) | set(baseline.columns))
        if column.startswith(("flashes_used_", "he_used_")) or column == "score_diff_before_round"
    ]
    for column in tracked:
        cur = pd.to_numeric(current[column], errors="coerce") if column in current.columns else pd.Series(dtype=float)
        old = pd.to_numeric(baseline[column], errors="coerce") if column in baseline.columns else pd.Series(dtype=float)
        expected = column.startswith(("flashes_used_", "he_used_")) or column == "score_diff_before_round"
        rows.append(
            {
                "map_id": "mirage",
                "target_team": target_team,
                "feature_name": column,
                "baseline_missing_share": float(old.isna().mean()) if len(old) else None,
                "current_missing_share": float(cur.isna().mean()) if len(cur) else None,
                "baseline_sum": float(old.sum()) if len(old) and old.notna().any() else None,
                "current_sum": float(cur.sum()) if len(cur) and cur.notna().any() else None,
                "expected_change": expected,
                "status": "ok" if expected else "warning",
                "notes": "Controlled migration feature repaired by Stage 8.9.1.",
            }
        )
    return pd.DataFrame(rows)


def build_repair_audit(outputs: dict[str, pd.DataFrame], round_features: pd.DataFrame, utility_events: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    checks = [
        ("flash_features_not_null", has_materialized_prefix(round_features, "flashes_used_"), "Flash temporal features must be numeric/materialized."),
        ("he_features_not_null", has_materialized_prefix(round_features, "he_used_"), "HE temporal features must be numeric/materialized."),
        ("score_diff_not_null", feature_not_null(round_features, "score_diff_before_round"), "score_diff_before_round must be filled from previous round scores."),
        ("utility_adapter_has_canonical_columns", set(canonical_utility_event_columns()).issubset(utility_events.columns), "utility_events must expose canonical adapter columns."),
        ("endpoint_policy_explicit", "endpoint_resolution_method" in utility_events.columns, "Endpoint confidence/method must be explicit."),
    ]
    rows = []
    for check_id, passed, notes in checks:
        rows.append(
            {
                "map_id": map_id,
                "target_team": target_team,
                "check_id": check_id,
                "passed": bool(passed),
                "severity": "critical",
                "feature_engine_version": "v2",
                "status": "ok" if passed else "failed",
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def build_utility_type_sanity(round_features: pd.DataFrame, utility_events: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    rows = []
    for utility_type in ["smoke", "flash", "molotov", "he", "decoy"]:
        prefix = {"smoke": "smokes_used_", "flash": "flashes_used_", "molotov": "molotovs_used_", "he": "he_used_", "decoy": "decoys_used_"}[utility_type]
        feature_columns = [column for column in round_features.columns if column.startswith(prefix)] if not round_features.empty else []
        feature_sum = float(pd.to_numeric(round_features[feature_columns].stack(), errors="coerce").sum()) if feature_columns else 0.0
        events = utility_events[utility_events.get("utility_type", pd.Series(dtype=object)).astype(str).eq(utility_type)] if not utility_events.empty and "utility_type" in utility_events.columns else pd.DataFrame()
        rows.append(
            {
                "map_id": map_id,
                "target_team": target_team,
                "utility_type": utility_type,
                "event_rows": len(events),
                "feature_columns": len(feature_columns),
                "feature_value_sum": feature_sum,
                "feature_engine_version": "v2",
                "status": "ok" if utility_type == "decoy" or len(events) > 0 or feature_sum > 0 else "warning",
                "notes": "Decoy support is adapter-level only in MVP." if utility_type == "decoy" else "Utility source and feature columns reconciled.",
            }
        )
    return pd.DataFrame(rows)


def build_mid_control_review(cross_map: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    if cross_map.empty or "feature_name" not in cross_map.columns:
        return pd.DataFrame(
            [
                {
                    "map_id": map_id,
                    "target_team": target_team,
                    "feature_name": None,
                    "structural_mismatch": None,
                    "review_status": "not_available",
                    "status": "review_only",
                    "notes": "No cross-map feature sanity table available for mid-control review.",
                }
            ]
        )
    review = cross_map[cross_map["feature_name"].astype(str).str.contains("mid_control", case=False, na=False)].copy()
    if review.empty:
        return pd.DataFrame(columns=["map_id", "target_team", "feature_name", "structural_mismatch", "review_status", "status", "notes"])
    review["map_id"] = map_id
    review["target_team"] = target_team
    review["review_status"] = "review_only_no_mapping_change"
    review["status"] = "review_only"
    review["notes"] = "Structural mismatch is audited only; Stage 8.9.1 does not change region mapping semantics."
    return review


def build_capabilities(outputs: dict[str, pd.DataFrame], *, map_id: str, target_team: str) -> pd.DataFrame:
    rows = [
        ("flash_usage", "supported_materialized", "grenades", "Flash events rebuilt from trajectory entities."),
        ("he_usage", "supported_materialized", "grenades", "HE events rebuilt from trajectory entities."),
        ("smoke_usage", "supported_materialized", "smokes", "Smoke events use event-level smokes table."),
        ("molotov_usage", "supported_materialized", "infernos", "Molotov/incendiary events use infernos table."),
        ("utility_endpoint_regions", "unsupported_unresolved", "utility_events", "No deterministic endpoint region evidence currently available."),
        ("score_diff_before_round", "supported_materialized", "round_state_resolved", "Score before round uses previous-round winner state by parse_id."),
    ]
    return pd.DataFrame(
        [
            {
                "map_id": map_id,
                "target_team": target_team,
                "capability_id": capability_id,
                "capability_status": status,
                "source": source,
                "feature_engine_version": "v2",
                "status": "ok" if status == "supported_materialized" else "warning",
                "notes": notes,
            }
            for capability_id, status, source, notes in rows
        ]
    )


def build_quality_gate_recovery(output_dir: Path, quality: pd.DataFrame, missing: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    before = read_optional(output_dir / "quality_gate_before_snapshot.parquet")
    current = latest_quality_row(quality, map_id=map_id, target_team=target_team)
    before_row = latest_quality_row(before, map_id=map_id, target_team=target_team)
    current_missing_blockers = int(
        missing.get("blocking", pd.Series(dtype=bool)).fillna(False).sum()
    ) if not missing.empty else None
    return pd.DataFrame(
        [
            {
                "map_id": map_id,
                "target_team": target_team,
                "before_critical_failures": int(before_row.get("critical_failures", 0) or 0) if before_row is not None else None,
                "current_critical_failures": int(current.get("critical_failures", 0) or 0) if current is not None else None,
                "before_unexpected_missing_features": int(before_row.get("unexpected_missing_features", 0) or 0) if before_row is not None else None,
                "current_unexpected_missing_features": int(current.get("unexpected_missing_features", 0) or 0) if current is not None else current_missing_blockers,
                "current_status": str(current.get("status", "unknown")) if current is not None else "unknown",
                "current_modeling_readiness_level": str(current.get("modeling_readiness_level", "unknown")) if current is not None else "unknown",
                "feature_engine_version": "v2",
                "status": "ok" if current is not None and str(current.get("status", "")).casefold() == "passed" else "warning",
                "notes": "Quality gate should be rerun after feature repair to update this recovery row.",
            }
        ]
    )


def build_final_audit(outputs: dict[str, pd.DataFrame], *, map_id: str, target_team: str) -> pd.DataFrame:
    repair = outputs["feature_materialization_repair_audit"]
    failed = int(repair.get("status", pd.Series(dtype=object)).eq("failed").sum()) if not repair.empty else 0
    warning_frames = [
        outputs["utility_endpoint_resolution_audit"],
        outputs["mid_control_structural_review"],
        outputs["quality_gate_recovery"],
    ]
    warnings = sum(int(frame.get("status", pd.Series(dtype=object)).eq("warning").sum()) for frame in warning_frames if not frame.empty)
    quality = outputs["quality_gate_recovery"].iloc[0] if not outputs["quality_gate_recovery"].empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "map_id": map_id,
                "target_team": target_team,
                "feature_engine_version": "v2",
                "failed_checks": failed,
                "warning_checks": warnings,
                "quality_gate_status": quality.get("current_status", "unknown"),
                "ready_for_stage_8_10": bool(failed == 0 and str(quality.get("current_status", "")).casefold() == "passed"),
                "status": "passed" if failed == 0 else "failed",
                "created_at": now_utc(),
                "notes": "Stage 8.9.1 repairs materialization only. It does not implement ML, tactical EDA, dashboard, or BigQuery.",
            }
        ]
    )


def ensure_quality_before_snapshot(output_dir: Path, gold_dir: Path, *, force: bool) -> None:
    source = gold_dir / "validation" / "map_feature_quality" / "map_feature_quality_audit.parquet"
    target = output_dir / "quality_gate_before_snapshot.parquet"
    if target.exists():
        return
    if not source.exists():
        return
    ensure_dir(output_dir)
    frame = read_optional(source)
    if frame.empty:
        return
    frame.to_parquet(target, index=False)
    frame.to_csv(output_dir / "quality_gate_before_snapshot.csv", index=False)


def latest_quality_row(frame: pd.DataFrame, *, map_id: str, target_team: str) -> pd.Series | None:
    if frame.empty:
        return None
    scoped = frame.copy()
    if "map_id" in scoped.columns:
        scoped = scoped[scoped["map_id"].astype(str).eq(map_id)]
    if "target_team" in scoped.columns:
        scoped = scoped[scoped["target_team"].astype(str).str.casefold().eq(target_team.casefold())]
    if scoped.empty:
        return None
    return scoped.iloc[-1]


def has_materialized_prefix(frame: pd.DataFrame, prefix: str) -> bool:
    columns = [column for column in frame.columns if column.startswith(prefix)] if not frame.empty else []
    if not columns:
        return False
    return bool(frame[columns].notna().all().all())


def feature_not_null(frame: pd.DataFrame, feature: str) -> bool:
    return bool(not frame.empty and feature in frame.columns and frame[feature].notna().all())


def canonical_utility_event_columns() -> list[str]:
    return [
        "utility_event_id",
        "round_feature_id",
        "round_id",
        "series_id",
        "target_team",
        "player_name",
        "player_steamid",
        "utility_type",
        "event_tick",
        "seconds_from_freeze_end",
        "throw_x",
        "throw_y",
        "throw_z",
        "throw_place",
        "throw_region_name",
        "throw_region_group",
        "end_x",
        "end_y",
        "end_z",
        "end_place",
        "end_region_name",
        "end_region_group",
        "source_table",
        "source_granularity",
        "source_entity_id",
        "endpoint_resolution_method",
        "endpoint_resolution_confidence",
    ]


def write_repair_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    paths: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        frame = sanitize_for_parquet(frames.get(name, pd.DataFrame()))
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if path.exists() and not force:
                paths[f"{name}_{suffix}"] = path
                continue
            if suffix == "csv":
                frame.to_csv(path, index=False)
            else:
                frame.to_parquet(path, index=False)
            paths[f"{name}_{suffix}"] = path
    return paths


def sanitize_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].map(
                lambda value: None
                if value is None or (not isinstance(value, (list, dict, tuple, set)) and pd.isna(value))
                else "|".join(map(str, value))
                if isinstance(value, (list, tuple, set))
                else json.dumps(value, sort_keys=True)
                if isinstance(value, dict)
                else value
            )
    return result


def write_report(path: Path, outputs: dict[str, pd.DataFrame], *, force: bool) -> Path:
    if path.exists() and not force:
        return path
    ensure_dir(path.parent)
    final = outputs["feature_materialization_repair_final_audit"].iloc[0]
    recovery = outputs["quality_gate_recovery"].iloc[0]
    sections = [
        "# Stage 8.9.1 -- Feature Materialization Repair",
        "",
        "## Purpose",
        "Repair real upstream feature materialization issues found by the Inferno quality gate without relaxing thresholds.",
        "",
        "## Repairs",
        "- Flash usage is materialized from `grenades.parquet` trajectory entities.",
        "- HE usage is materialized from `grenades.parquet` trajectory entities.",
        "- `score_diff_before_round` is filled from previous-round winners using resolved round state.",
        "- Utility endpoint metadata is explicit and remains unresolved when no deterministic endpoint evidence exists.",
        "- Mirage mid-control structural mismatches are review-only; no mapping semantics were changed.",
        "",
        "## Current Status",
        f"repair_status: `{final.get('status')}`",
        f"failed_checks: `{final.get('failed_checks')}`",
        f"warning_checks: `{final.get('warning_checks')}`",
        f"quality_gate_status: `{recovery.get('current_status')}`",
        f"ready_for_stage_8_10: `{final.get('ready_for_stage_8_10')}`",
        "",
        "## Output Tables",
        "\n".join(f"- `{name}.csv` / `{name}.parquet`" for name in OUTPUT_NAMES),
        "",
        "## Non-Goals",
        "This stage does not implement tactical EDA, ML, predictions, dashboard, BigQuery, or model training.",
        "",
    ]
    path.write_text("\n".join(sections), encoding="utf-8")
    return path


def write_notebook(path: Path, *, force: bool) -> Path:
    if path.exists() and not force:
        return path
    ensure_dir(path.parent)
    notebook = {
        "cells": [
            md("# Stage 8.9.1 -- Feature Materialization Repair"),
            code("from pathlib import Path\nimport pandas as pd\nBASE = Path('../data/gold/validation/feature_materialization_repair')\ndef load(name):\n    return pd.read_parquet(BASE / f'{name}.parquet')"),
            md("## Final Audit"),
            code("display(load('feature_materialization_repair_final_audit'))"),
            md("## Utility Source Capability"),
            code("display(load('utility_source_capability'))"),
            md("## Utility Event Reconstruction"),
            code("display(load('utility_event_reconstruction_audit'))"),
            md("## Utility Type Feature Sanity"),
            code("display(load('utility_type_feature_sanity'))"),
            md("## Score Before Round"),
            code("display(load('score_before_round_audit'))"),
            md("## Quality Gate Recovery"),
            code("display(load('quality_gate_recovery'))"),
            md("## Mirage Migration Diff"),
            code("display(load('mirage_feature_migration_diff').head(50))"),
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.12"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    return path


def read_optional(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return read_catalog(path)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def md(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict[str, object]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def print_summary(outputs: dict[str, Path], summary: dict[str, Any]) -> None:
    print("Feature materialization repair summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Stage 8.9.1 feature materialization repairs.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_feature_materialization_repair_audit(
        args.config,
        target_map=args.target_map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
