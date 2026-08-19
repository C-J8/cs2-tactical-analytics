from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.maps.identity import resolve_map_identity
from src.maps.registry import load_yaml, normalize_id
from src.storage.scoped_gold import GOLD_DATASET_SPECS, content_hash, duplicate_key_count, schema_hash
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging
from src.validation.multi_map_gold_gate import load_gold_frames, scoped_team_map


OUTPUT_NAMES = [
    "map_dataset_reconciliation",
    "map_feature_quality_profile",
    "map_feature_missingness",
    "map_feature_domain_validation",
    "map_feature_degeneracy",
    "map_feature_by_demo_health",
    "map_demo_quality_summary",
    "map_semantic_signal_health",
    "map_region_presence_sanity",
    "map_temporal_feature_consistency",
    "map_side_feature_health",
    "map_ab_label_quality",
    "map_ab_label_crosscheck",
    "map_modeling_sample_readiness",
    "mirage_inferno_feature_sanity",
    "map_noncomparable_feature_inventory",
    "map_round_quality_flags",
    "map_quality_review_sample",
    "map_quality_scorecard",
    "map_feature_quality_read_only_audit",
    "map_feature_quality_audit",
]

CORE_READ_ONLY_DATASETS = [
    "round_features_mvp",
    "round_state_resolved",
    "round_features_t_side_all",
    "round_features_t_side_planted",
    "round_features_ct_side",
    "region_presence_by_round",
    "utility_events",
    "round_region_timeline",
    "death_context_by_round",
    "bomb_carrier_timeline",
    "round_outcome_context",
]

IDENTIFIER_COLUMNS = {
    "round_id",
    "round_feature_id",
    "parse_id",
    "dem_file_id",
    "series_id",
    "utility_event_id",
    "death_context_id",
    "target_team",
    "opponent",
    "map_name",
    "dataset_type",
    "feature_quality_status",
    "feature_notes",
}


@dataclass(frozen=True)
class GateContext:
    project_root: Path
    gold_dir: Path
    output_dir: Path
    registry_path: Path
    map_id: str
    map_name: str
    target_team: str
    quality: dict[str, Any]


def run_map_feature_quality_gate(
    config_path: Path,
    *,
    target_map: str,
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    quality_config: Path = Path("configs/quality/map_feature_quality.yaml"),
    map_registry_path: Path = Path("configs/maps/map_registry.yaml"),
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    gold_dir = project_root / "data" / "gold"
    target_team = target_team or project.target_teams[0]
    registry_path = resolve_project_path(project_root, map_registry_path)
    quality_path = resolve_project_path(project_root, quality_config)
    identity = resolve_map_identity(target_map, registry_path=registry_path)
    ctx = GateContext(
        project_root=project_root,
        gold_dir=gold_dir,
        output_dir=gold_dir / "validation" / "map_feature_quality",
        registry_path=registry_path,
        map_id=identity.map_id,
        map_name=identity.display_name,
        target_team=target_team,
        quality=load_quality_config(quality_path),
    )

    frames = load_gold_frames(gold_dir)
    before = capture_core_fingerprints(frames, ctx)
    preconditions = validate_preconditions(frames, ctx)
    scoped = build_scoped_frames(frames, ctx)
    contract = load_feature_contract(gold_dir)
    outputs = build_quality_outputs(scoped, contract, preconditions, before, ctx)
    after = capture_core_fingerprints(load_gold_frames(gold_dir), ctx)
    outputs["map_feature_quality_read_only_audit"] = build_read_only_audit(before, after, ctx)
    outputs["map_feature_quality_audit"] = build_final_audit(outputs, preconditions, ctx)

    paths: dict[str, Path] = {}
    if not dry_run:
        paths.update(write_quality_outputs(outputs, ctx.output_dir, map_id=ctx.map_id, target_team=ctx.target_team, force=force))
        paths["report"] = write_report(outputs, ctx, force=force)
        paths["notebook"] = write_notebook(ctx.project_root / "notebooks" / "23_inferno_feature_quality.ipynb", force=force)

    audit = outputs["map_feature_quality_audit"].iloc[0]
    summary = {
        "map_id": ctx.map_id,
        "target_team": ctx.target_team,
        "round_features": int(audit.get("round_features", 0)),
        "critical_failures": int(audit.get("critical_failures", 0)),
        "warnings": int(audit.get("warnings", 0)),
        "ready_for_multi_map_eda": bool(audit.get("ready_for_multi_map_eda", False)),
        "modeling_readiness_level": str(audit.get("modeling_readiness_level", "blocked")),
        "status": str(audit.get("status", "failed")),
    }
    return outputs, paths, summary


def build_quality_outputs(
    scoped: dict[str, pd.DataFrame],
    contract: pd.DataFrame,
    preconditions: pd.DataFrame,
    before_fingerprints: pd.DataFrame,
    ctx: GateContext,
) -> dict[str, pd.DataFrame]:
    round_features = scoped["round_features_mvp"]
    round_state = scoped["round_state_resolved"]
    outputs: dict[str, pd.DataFrame] = {}
    outputs["map_dataset_reconciliation"] = build_dataset_reconciliation(scoped, ctx)
    outputs["map_feature_quality_profile"] = build_feature_quality_profile(round_features, contract, ctx)
    outputs["map_feature_missingness"] = build_feature_missingness(outputs["map_feature_quality_profile"], round_features, round_state, contract, ctx)
    outputs["map_feature_domain_validation"] = build_domain_validation(round_features, contract, ctx)
    outputs["map_feature_degeneracy"] = build_feature_degeneracy(outputs["map_feature_quality_profile"], contract, ctx)
    outputs["map_feature_by_demo_health"] = build_feature_by_demo_health(round_features, contract, ctx)
    outputs["map_semantic_signal_health"] = build_semantic_signal_health(round_features, contract, ctx)
    outputs["map_demo_quality_summary"] = build_demo_quality_summary(scoped, outputs, ctx)
    outputs["map_region_presence_sanity"] = build_region_presence_sanity(scoped["region_presence_by_round"], ctx)
    outputs["map_temporal_feature_consistency"] = build_temporal_feature_consistency(round_features, contract, ctx)
    outputs["map_side_feature_health"] = build_side_feature_health(scoped, contract, ctx)
    outputs["map_ab_label_quality"] = build_ab_label_quality(scoped, ctx)
    outputs["map_ab_label_crosscheck"] = build_ab_label_crosscheck(scoped, ctx)
    outputs["map_modeling_sample_readiness"] = build_modeling_sample_readiness(outputs["map_ab_label_quality"], ctx)
    outputs["mirage_inferno_feature_sanity"] = build_cross_map_feature_sanity(ctx.gold_dir, contract, target_team=ctx.target_team, registry_path=ctx.registry_path)
    outputs["map_noncomparable_feature_inventory"] = build_noncomparable_feature_inventory(contract, ctx)
    outputs["map_round_quality_flags"] = build_round_quality_flags(scoped, outputs, ctx)
    outputs["map_quality_review_sample"] = build_quality_review_sample(scoped, outputs["map_round_quality_flags"], round_features, ctx)
    outputs["map_quality_scorecard"] = build_scorecard(outputs, preconditions, before_fingerprints, ctx)
    return outputs


def load_quality_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Quality config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or {}
    if not isinstance(content, dict):
        raise ValueError(f"Quality config must be a mapping: {path}")
    return content


def resolve_project_path(project_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    candidate = project_root / path
    return candidate if candidate.exists() else path


def validate_preconditions(frames: dict[str, pd.DataFrame], ctx: GateContext) -> pd.DataFrame:
    rows = []
    registry = load_yaml(ctx.registry_path)
    registry_entry = next((entry for entry in registry.get("maps", []) if normalize_id(str(entry.get("map_id") or "")) == ctx.map_id), None)
    active = bool(registry_entry and str(registry_entry.get("status") or "").casefold() == "active")
    rows.append(precondition_row("map_registry_active", active, "Map registry entry must be active."))
    stage_ready = stage_8_8_ready(ctx)
    rows.append(precondition_row("stage_8_8_ready", stage_ready, "Stage 8.8 multi-map Gold gate must be green for this scope."))
    for name in [
        "round_features_mvp",
        "round_state_resolved",
        "round_features_t_side_all",
        "round_features_t_side_planted",
        "round_features_ct_side",
    ]:
        frame = frames.get(name, pd.DataFrame())
        present = not frame.empty
        if present:
            scoped = scoped_team_map(frame, target_team=ctx.target_team, map_name=ctx.map_name, registry_path=ctx.registry_path)
            present = not scoped.empty
        rows.append(precondition_row(f"{name}_present", present, f"{name} must exist and contain selected scope rows."))
    return pd.DataFrame(rows)


def precondition_row(check_id: str, passed: bool, notes: str) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "severity": "critical", "status": "ok" if passed else "failed", "notes": notes}


def stage_8_8_ready(ctx: GateContext) -> bool:
    path = ctx.gold_dir / "validation" / "multi_map_gold" / "multi_map_gold_audit.parquet"
    if not path.exists():
        return False
    audit = read_catalog(path)
    if audit.empty:
        return False
    scoped = audit.copy()
    if "canonical_target_map_id" in scoped.columns:
        scoped = scoped[scoped["canonical_target_map_id"].astype(str).eq(ctx.map_id)]
    elif "map_id" in scoped.columns:
        scoped = scoped[scoped["map_id"].astype(str).eq(ctx.map_id)]
    if "target_team" in scoped.columns:
        scoped = scoped[scoped["target_team"].astype(str).str.casefold().eq(ctx.target_team.casefold())]
    if scoped.empty:
        return False
    row = scoped.iloc[-1]
    ready_column = f"ready_for_{ctx.map_id}_feature_quality_gate"
    if ready_column in row.index:
        return bool(row.get(ready_column))
    return str(row.get("overall_status") or row.get("status") or "").casefold() in {"passed", "ok"}


def build_scoped_frames(frames: dict[str, pd.DataFrame], ctx: GateContext) -> dict[str, pd.DataFrame]:
    scoped: dict[str, pd.DataFrame] = {}
    round_features = scoped_team_map(frames.get("round_features_mvp", pd.DataFrame()), target_team=ctx.target_team, map_name=ctx.map_name, registry_path=ctx.registry_path)
    feature_ids = set(round_features.get("round_feature_id", pd.Series(dtype=str)).dropna().astype(str))
    round_ids = set(round_features.get("round_id", pd.Series(dtype=str)).dropna().astype(str))
    parse_ids = set(round_features.get("parse_id", pd.Series(dtype=str)).dropna().astype(str))
    for name, spec in GOLD_DATASET_SPECS.items():
        frame = frames.get(name, pd.DataFrame())
        if name == "round_features_mvp":
            scoped[name] = round_features.reset_index(drop=True)
        elif not frame.empty and spec.map_column and spec.map_column in frame.columns:
            scoped[name] = scoped_team_map(frame, target_team=ctx.target_team, map_name=ctx.map_name, registry_path=ctx.registry_path)
        else:
            scoped[name] = scope_by_known_ids(frame, feature_ids=feature_ids, round_ids=round_ids, parse_ids=parse_ids)
    return scoped


def scope_by_known_ids(frame: pd.DataFrame, *, feature_ids: set[str], round_ids: set[str], parse_ids: set[str]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if "round_feature_id" in frame.columns:
        return frame[frame["round_feature_id"].astype(str).isin(feature_ids)].copy().reset_index(drop=True)
    if "round_id" in frame.columns:
        return frame[frame["round_id"].astype(str).isin(round_ids)].copy().reset_index(drop=True)
    if "parse_id" in frame.columns:
        return frame[frame["parse_id"].astype(str).isin(parse_ids)].copy().reset_index(drop=True)
    return frame.iloc[0:0].copy()


def load_feature_contract(gold_dir: Path) -> pd.DataFrame:
    parquet_path = gold_dir / "features" / "feature_contract" / "feature_contract.parquet"
    if parquet_path.exists():
        return read_catalog(parquet_path)
    config_path = Path("configs/features/feature_contract.yaml")
    if config_path.exists():
        content = load_yaml(config_path)
        return pd.DataFrame(content.get("features", []))
    return pd.DataFrame()


def build_dataset_reconciliation(scoped: dict[str, pd.DataFrame], ctx: GateContext) -> pd.DataFrame:
    round_features = scoped["round_features_mvp"]
    round_state = enrich_round_state_feature_ids(scoped["round_state_resolved"], round_features)
    feature_ids = set(round_features.get("round_feature_id", pd.Series(dtype=str)).dropna().astype(str))
    round_ids = set(round_features.get("round_id", pd.Series(dtype=str)).dropna().astype(str))
    state_t = set(round_state.loc[round_state.get("target_team_side", pd.Series(dtype=object)).eq("T"), "round_feature_id"].dropna().astype(str)) if "round_feature_id" in round_state.columns and "target_team_side" in round_state.columns else set()
    state_ct = set(round_state.loc[round_state.get("target_team_side", pd.Series(dtype=object)).eq("CT"), "round_feature_id"].dropna().astype(str)) if "round_feature_id" in round_state.columns and "target_team_side" in round_state.columns else set()
    state_planted = set(
        round_state.loc[
            round_state.get("target_team_side", pd.Series(index=round_state.index, dtype=object)).eq("T")
            & round_state.get("target_site_model_label", pd.Series(index=round_state.index, dtype=object)).isin(["A", "B"])
            & round_state.get("label_confidence", pd.Series(index=round_state.index, dtype=object)).eq("high"),
            "round_feature_id",
        ].dropna().astype(str)
    ) if "round_feature_id" in round_state.columns else set()
    expected_by_name = {
        "round_state_resolved": feature_ids,
        "round_features_t_side_all": state_t,
        "round_features_ct_side": state_ct,
        "round_features_t_side_planted": state_planted,
        "round_outcome_context": feature_ids,
    }
    rows = []
    for name in [
        "round_features_mvp",
        "round_state_resolved",
        "round_features_t_side_all",
        "round_features_t_side_planted",
        "round_features_ct_side",
        "region_presence_by_round",
        "round_region_timeline",
        "death_context_by_round",
        "bomb_carrier_timeline",
        "round_outcome_context",
        "utility_events",
    ]:
        spec = GOLD_DATASET_SPECS[name]
        frame = scoped.get(name, pd.DataFrame())
        keys = [column for column in spec.key_columns if column in frame.columns]
        missing_key_count = int(frame[keys].isna().any(axis=1).sum()) if keys and not frame.empty else (len(frame) if spec.key_columns and not keys else 0)
        duplicate_count = duplicate_key_count(frame, spec) if not frame.empty else 0
        current_ids = set(frame.get("round_feature_id", pd.Series(dtype=str)).dropna().astype(str)) if "round_feature_id" in frame.columns else set()
        current_round_ids = set(frame.get("round_id", pd.Series(dtype=str)).dropna().astype(str)) if "round_id" in frame.columns else set()
        expected = expected_by_name.get(name)
        relationship_passed = True
        relationship = "scoped rows available"
        notes = "No scoped rows found." if frame.empty else "Scoped dataset reconciled."
        if name == "round_features_mvp":
            relationship_passed = len(frame) > 0
            relationship = "base scoped round features"
        elif expected is not None:
            if name == "round_state_resolved" and not current_ids:
                relationship_passed = current_round_ids == round_ids
                relationship = "round_ids equal expected scope"
                notes = f"expected_round_ids={len(round_ids)} observed_round_ids={len(current_round_ids)} missing={len(round_ids-current_round_ids)} extra={len(current_round_ids-round_ids)}" if not relationship_passed else notes
            else:
                relationship_passed = current_ids == expected
                relationship = "round_feature_ids equal expected scope"
                if not relationship_passed:
                    notes = f"expected_ids={len(expected)} observed_ids={len(current_ids)} missing={len(expected-current_ids)} extra={len(current_ids-expected)}"
        status = "ok" if len(frame) and missing_key_count == 0 and duplicate_count == 0 and relationship_passed else "failed"
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "dataset_name": name,
                "row_count": len(frame),
                "unique_rounds": nunique(frame, "round_id"),
                "unique_parse_ids": nunique(frame, "parse_id"),
                "unique_demos": nunique(frame, "dem_file_id"),
                "duplicate_key_count": duplicate_count,
                "missing_key_count": missing_key_count,
                "expected_relationship": relationship,
                "relationship_passed": relationship_passed,
                "status": status,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def enrich_round_state_feature_ids(round_state: pd.DataFrame, round_features: pd.DataFrame) -> pd.DataFrame:
    if round_state.empty or "round_feature_id" in round_state.columns:
        return round_state.copy()
    if "round_id" not in round_state.columns or not {"round_id", "round_feature_id"}.issubset(round_features.columns):
        return round_state.copy()
    return round_state.merge(round_features[["round_id", "round_feature_id"]].drop_duplicates("round_id"), on="round_id", how="left")


def build_feature_quality_profile(round_features: pd.DataFrame, contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    contract_by_feature = contract.drop_duplicates("feature_name").set_index("feature_name") if not contract.empty and "feature_name" in contract.columns else pd.DataFrame()
    rows = []
    for column in analytical_columns(round_features, contract):
        series = round_features[column] if column in round_features.columns else pd.Series(dtype=object)
        meta = contract_by_feature.loc[column] if not contract_by_feature.empty and column in contract_by_feature.index else pd.Series(dtype=object)
        numeric = pd.to_numeric(series, errors="coerce")
        numeric_valid = numeric.dropna()
        numeric_feature = pd.api.types.is_numeric_dtype(series) or numeric_valid.size > 0 and numeric_valid.size >= max(1, int(series.notna().sum() * 0.9))
        stats = numeric_stats(numeric_valid) if numeric_feature else empty_stats()
        non_null = int(series.notna().sum())
        missing = len(series) - non_null
        unique_values = int(series.nunique(dropna=True))
        zero_rows = int((numeric_valid == 0).sum()) if numeric_feature else 0
        zero_share = zero_rows / len(series) if len(series) and numeric_feature else 0.0
        finite_share = float(np.isfinite(numeric_valid).sum() / len(series)) if len(series) and numeric_feature else None
        all_null = bool(len(series) > 0 and non_null == 0)
        all_zero = bool(numeric_feature and len(series) > 0 and zero_rows == len(series))
        constant = bool(non_null > 0 and unique_values <= 1)
        near_constant = bool(non_null > 0 and dominant_share(series) >= float(ctx.quality["degeneracy"]["near_constant_share"]))
        quality_status = profile_status(all_null, constant, near_constant, all_zero)
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "feature_name": column,
                "feature_family": meta.get("feature_family"),
                "generation_scope": meta.get("generation_scope", meta.get("map_scope")),
                "coordinate_dependency": meta.get("coordinate_dependency"),
                "cross_map_comparable": bool(meta.get("cross_map_comparable", False)) if not meta.empty else False,
                "cross_map_comparison_mode": meta.get("cross_map_comparison_mode"),
                "region_dependency": bool(meta.get("region_dependency", False)) if not meta.empty else False,
                "region_semantic": meta.get("region_semantic"),
                "dtype": str(series.dtype),
                "rows": len(series),
                "non_null_rows": non_null,
                "missing_rows": missing,
                "missing_share": missing / len(series) if len(series) else 0.0,
                "unique_values": unique_values,
                "zero_rows": zero_rows,
                "zero_share": zero_share,
                "non_zero_rows": int((numeric_valid != 0).sum()) if numeric_feature else None,
                **stats,
                "finite_share": finite_share,
                "constant": constant,
                "near_constant": near_constant,
                "all_null": all_null,
                "all_zero": all_zero,
                "quality_status": quality_status,
                "notes": profile_notes(all_null, constant, near_constant, all_zero, numeric_feature),
            }
        )
    return pd.DataFrame(rows)


def analytical_columns(round_features: pd.DataFrame, contract: pd.DataFrame) -> list[str]:
    if round_features.empty:
        return []
    contract_features = set(contract["feature_name"].dropna().astype(str)) if not contract.empty and "feature_name" in contract.columns else set()
    columns = []
    for column in round_features.columns:
        if column in IDENTIFIER_COLUMNS or column.startswith("_"):
            continue
        if contract_features and column not in contract_features:
            continue
        columns.append(column)
    return columns


def numeric_stats(values: pd.Series) -> dict[str, float | None]:
    if values.empty:
        return empty_stats()
    values = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if values.empty:
        return empty_stats()
    return {
        "min": float(values.min()),
        "p01": float(values.quantile(0.01)),
        "p05": float(values.quantile(0.05)),
        "p25": float(values.quantile(0.25)),
        "median": float(values.median()),
        "mean": float(values.mean()),
        "p75": float(values.quantile(0.75)),
        "p95": float(values.quantile(0.95)),
        "p99": float(values.quantile(0.99)),
        "max": float(values.max()),
        "std": float(values.std(ddof=0)) if len(values) > 1 else 0.0,
    }


def empty_stats() -> dict[str, None]:
    return {key: None for key in ["min", "p01", "p05", "p25", "median", "mean", "p75", "p95", "p99", "max", "std"]}


def profile_status(all_null: bool, constant: bool, near_constant: bool, all_zero: bool) -> str:
    if all_null:
        return "failed"
    if all_zero or constant or near_constant:
        return "warning"
    return "ok"


def profile_notes(all_null: bool, constant: bool, near_constant: bool, all_zero: bool, numeric_feature: bool) -> str:
    if all_null:
        return "Feature is fully missing in selected scope."
    if all_zero:
        return "Numeric feature is zero for every selected round."
    if constant:
        return "Feature has one observed value in selected scope."
    if near_constant:
        return "Feature is near constant in selected scope."
    return "Numeric distribution profiled." if numeric_feature else "Non-numeric feature profiled without numeric statistics."


def build_feature_missingness(profile: pd.DataFrame, round_features: pd.DataFrame, round_state: pd.DataFrame, contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    if profile.empty:
        return pd.DataFrame()
    rows = []
    contract_by_feature = contract.drop_duplicates("feature_name").set_index("feature_name") if not contract.empty and "feature_name" in contract.columns else pd.DataFrame()
    sides = round_features[["round_feature_id"]].merge(round_state[["round_feature_id", "target_team_side"]], on="round_feature_id", how="left") if {"round_feature_id"}.issubset(round_features.columns) and {"round_feature_id", "target_team_side"}.issubset(round_state.columns) else pd.DataFrame()
    for _, row in profile.iterrows():
        feature = str(row["feature_name"])
        series = round_features[feature] if feature in round_features.columns else pd.Series(dtype=object)
        meta = contract_by_feature.loc[feature] if not contract_by_feature.empty and feature in contract_by_feature.index else pd.Series(dtype=object)
        by_demo_max = missing_by_group(round_features, feature, "parse_id")
        by_side_max = missing_by_side(round_features, sides, feature)
        expected = expected_missingness(feature, meta)
        share = float(row["missing_share"])
        unexpected = share > 0 and not expected
        severity = "none"
        blocking = False
        status = "ok"
        if unexpected and share >= float(ctx.quality["missingness"]["critical_share"]):
            severity = "critical"
            blocking = True
            status = "failed"
        elif unexpected and share >= float(ctx.quality["missingness"]["warning_share"]):
            severity = "warning"
            status = "warning"
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "feature_name": feature,
                "total_rows": len(series),
                "missing_rows": int(row["missing_rows"]),
                "missing_share": share,
                "missing_by_demo_max_share": by_demo_max,
                "missing_by_side_max_share": by_side_max,
                "expected_missingness": expected,
                "unexpected_missingness": unexpected,
                "severity": severity,
                "blocking": blocking,
                "status": status,
                "notes": "Missingness is structurally expected for this feature." if expected else "Unexpected missingness assessed against quality config.",
            }
        )
    return pd.DataFrame(rows)


def expected_missingness(feature: str, meta: pd.Series) -> bool:
    semantic_role = str(meta.get("semantic_role") or "")
    family = str(meta.get("feature_family") or "")
    lifecycle = str(meta.get("lifecycle_phase") or "")
    if feature.startswith("first_") or feature in {"bombsite", "target_site_model_label", "target_site_observed", "label_confidence"}:
        return True
    return semantic_role in {"bomb_progression"} or family in {"label"} or lifecycle.startswith("post")


def missing_by_group(frame: pd.DataFrame, feature: str, group_column: str) -> float:
    if frame.empty or feature not in frame.columns or group_column not in frame.columns:
        return 0.0
    shares = frame.groupby(group_column, dropna=False)[feature].apply(lambda values: float(values.isna().mean()))
    return float(shares.max()) if not shares.empty else 0.0


def missing_by_side(round_features: pd.DataFrame, sides: pd.DataFrame, feature: str) -> float:
    if sides.empty or feature not in round_features.columns or "round_feature_id" not in round_features.columns:
        return 0.0
    merged = round_features[["round_feature_id", feature]].merge(sides, on="round_feature_id", how="left")
    shares = merged.groupby("target_team_side", dropna=False)[feature].apply(lambda values: float(values.isna().mean()))
    return float(shares.max()) if not shares.empty else 0.0


def build_domain_validation(round_features: pd.DataFrame, contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    rows = []
    for feature in analytical_columns(round_features, contract):
        rule = domain_rule_for_feature(feature)
        if rule is None:
            rows.append(domain_row(ctx, feature, "unknown_domain", 0, 0.0, None, None, "none", False, "skipped"))
            continue
        series = round_features[feature]
        invalid = domain_invalid_mask(series, rule)
        numeric = pd.to_numeric(series, errors="coerce")
        invalid_rows = int(invalid.sum())
        severity = "critical" if invalid_rows else "none"
        rows.append(domain_row(ctx, feature, rule["name"], invalid_rows, invalid_rows / len(series) if len(series) else 0.0, safe_float(numeric.min()), safe_float(numeric.max()), severity, invalid_rows > 0, "failed" if invalid_rows else "ok"))
    return pd.DataFrame(rows)


def domain_rule_for_feature(feature: str) -> dict[str, object] | None:
    if feature == "round_num":
        return {"name": "positive_integer", "min": 1, "max": None}
    if feature.startswith("players_alive") or (feature.startswith("players_") and any(token in feature for token in ["control", "pressure", "space", "site", "spawn"])):
        return {"name": "player_count_0_5", "min": 0, "max": 5}
    if any(feature.startswith(prefix) for prefix in ["smokes_", "flashes_", "molotovs_", "he_", "utility_"]) or "_used_" in feature or "_to_" in feature:
        return {"name": "non_negative_count", "min": 0, "max": None}
    if feature.startswith("is_") or feature in {"bomb_planted", "target_team_planted", "opponent_planted"}:
        return {"name": "binary", "values": {0, 1, True, False}}
    return None


def domain_invalid_mask(series: pd.Series, rule: dict[str, object]) -> pd.Series:
    if rule["name"] == "binary":
        return ~series.dropna().isin(rule["values"]).reindex(series.index, fill_value=False)
    numeric = pd.to_numeric(series, errors="coerce")
    invalid = series.notna() & numeric.isna()
    minimum = rule.get("min")
    maximum = rule.get("max")
    if minimum is not None:
        invalid |= numeric < float(minimum)
    if maximum is not None:
        invalid |= numeric > float(maximum)
    return invalid.fillna(False)


def domain_row(ctx: GateContext, feature: str, rule: str, invalid_rows: int, invalid_share: float, example_min: float | None, example_max: float | None, severity: str, blocking: bool, status: str) -> dict[str, object]:
    return {
        "map_id": ctx.map_id,
        "target_team": ctx.target_team,
        "feature_name": feature,
        "domain_rule": rule,
        "invalid_rows": invalid_rows,
        "invalid_share": invalid_share,
        "example_min": example_min,
        "example_max": example_max,
        "severity": severity,
        "blocking": blocking,
        "status": status,
    }


def build_feature_degeneracy(profile: pd.DataFrame, contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    if profile.empty:
        return pd.DataFrame()
    contract_by_feature = contract.drop_duplicates("feature_name").set_index("feature_name") if not contract.empty and "feature_name" in contract.columns else pd.DataFrame()
    rows = []
    for _, row in profile.iterrows():
        feature = str(row["feature_name"])
        meta = contract_by_feature.loc[feature] if not contract_by_feature.empty and feature in contract_by_feature.index else pd.Series(dtype=object)
        all_zero = bool(row["all_zero"])
        constant = bool(row["constant"])
        near_constant = bool(row["near_constant"])
        required_semantic = bool(meta.get("feature_status") == "frozen" and meta.get("map_scope") == "map_abstract" and meta.get("region_dependency"))
        blocking = False
        severity = "warning" if all_zero or constant or near_constant or (required_semantic and all_zero) else "none"
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "feature_name": feature,
                "unique_values": int(row["unique_values"]),
                "zero_share": float(row["zero_share"] or 0.0),
                "dominant_value": None,
                "dominant_value_share": None,
                "variance": None if pd.isna(row.get("std")) else float(row.get("std") or 0.0) ** 2,
                "constant": constant,
                "near_constant": near_constant,
                "all_zero": all_zero,
                "map_scope": meta.get("map_scope"),
                "region_semantic": meta.get("region_semantic"),
                "severity": severity,
                "blocking": blocking,
                "status": "warning" if severity == "warning" else "ok",
                "notes": "Individual required semantic feature is all zero; semantic-level health decides whether this blocks." if required_semantic and all_zero else "Degeneracy assessed.",
            }
        )
    return pd.DataFrame(rows)


def build_feature_by_demo_health(round_features: pd.DataFrame, contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    if round_features.empty or "parse_id" not in round_features.columns:
        return pd.DataFrame()
    rows = []
    for parse_id, group in round_features.groupby("parse_id", dropna=False):
        for feature in analytical_columns(group, contract):
            series = group[feature]
            numeric = pd.to_numeric(series, errors="coerce")
            zero_share = float((numeric == 0).sum() / len(series)) if len(series) and numeric.notna().any() else 0.0
            unique = int(series.nunique(dropna=True))
            degenerate = bool(unique <= 1 and len(series) > 1)
            rows.append(
                {
                    "map_id": ctx.map_id,
                    "target_team": ctx.target_team,
                    "parse_id": parse_id,
                    "feature_name": feature,
                    "rounds": len(group),
                    "non_null_share": float(series.notna().mean()) if len(series) else 0.0,
                    "zero_share": zero_share,
                    "unique_values": unique,
                    "median": safe_float(numeric.median()) if numeric.notna().any() else None,
                    "mean": safe_float(numeric.mean()) if numeric.notna().any() else None,
                    "std": safe_float(numeric.std(ddof=0)) if numeric.notna().any() else None,
                    "degenerate_within_demo": degenerate,
                    "status": "warning" if degenerate else "ok",
                    "notes": "Feature is degenerate within this demo." if degenerate else "Demo feature distribution assessed.",
                }
            )
    return pd.DataFrame(rows)


def build_demo_quality_summary(scoped: dict[str, pd.DataFrame], outputs: dict[str, pd.DataFrame], ctx: GateContext) -> pd.DataFrame:
    round_features = scoped["round_features_mvp"]
    round_state = scoped["round_state_resolved"]
    if round_features.empty or "parse_id" not in round_features.columns:
        return pd.DataFrame()
    missing = outputs["map_feature_missingness"]
    by_demo = outputs["map_feature_by_demo_health"]
    semantics = outputs["map_semantic_signal_health"]
    rows = []
    for parse_id, group in round_features.groupby("parse_id", dropna=False):
        state = round_state[round_state["parse_id"].astype(str).eq(str(parse_id))] if "parse_id" in round_state.columns else pd.DataFrame()
        planted = state[state.get("target_site_model_label", pd.Series(index=state.index, dtype=object)).isin(["A", "B"])] if not state.empty else pd.DataFrame()
        demo_health = by_demo[by_demo["parse_id"].astype(str).eq(str(parse_id))] if not by_demo.empty else pd.DataFrame()
        warnings = int((missing["status"] == "warning").sum()) if not missing.empty else 0
        degenerate = int(demo_health["degenerate_within_demo"].fillna(False).sum()) if not demo_health.empty else 0
        semantic_failures = int((semantics["status"] == "failed").sum()) if not semantics.empty else 0
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "parse_id": parse_id,
                "rounds": len(group),
                "t_rounds": int((state.get("target_team_side", pd.Series(dtype=object)) == "T").sum()) if not state.empty else 0,
                "ct_rounds": int((state.get("target_team_side", pd.Series(dtype=object)) == "CT").sum()) if not state.empty else 0,
                "feature_missingness_warning_count": warnings,
                "degenerate_feature_count": degenerate,
                "semantic_failure_count": semantic_failures,
                "plant_labels": len(planted),
                "a_labels": int((planted.get("target_site_model_label", pd.Series(dtype=object)) == "A").sum()) if not planted.empty else 0,
                "b_labels": int((planted.get("target_site_model_label", pd.Series(dtype=object)) == "B").sum()) if not planted.empty else 0,
                "status": "failed" if semantic_failures else ("warning" if degenerate else "ok"),
            }
        )
    return pd.DataFrame(rows)


def build_semantic_signal_health(round_features: pd.DataFrame, contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    if contract.empty:
        return pd.DataFrame()
    required = contract[
        contract.get("feature_status", pd.Series(index=contract.index, dtype=object)).eq("frozen")
        & contract.get("map_scope", pd.Series(index=contract.index, dtype=object)).eq("map_abstract")
        & contract.get("region_dependency", pd.Series(index=contract.index, dtype=bool)).fillna(False)
    ].copy()
    semantics = sorted(set(required.get("region_semantic", pd.Series(dtype=object)).dropna().astype(str)))
    rows = []
    mapping = load_region_mapping(ctx)
    for semantic_id in semantics:
        required_features = required[required["region_semantic"].astype(str).eq(semantic_id)]["feature_name"].dropna().astype(str).tolist()
        materialized = [feature for feature in required_features if feature in round_features.columns]
        numeric = round_features[materialized].apply(pd.to_numeric, errors="coerce") if materialized else pd.DataFrame(index=round_features.index)
        per_round = numeric.fillna(0).abs().sum(axis=1) if not numeric.empty else pd.Series(0, index=round_features.index)
        rounds_with_signal = int((per_round > 0).sum())
        demos_with_signal = int(round_features.loc[per_round > 0, "parse_id"].nunique()) if "parse_id" in round_features.columns and len(per_round) else 0
        total_demos = int(round_features["parse_id"].nunique()) if "parse_id" in round_features.columns and not round_features.empty else 0
        mapping_row = mapping[mapping.get("semantic_id", pd.Series(dtype=object)).astype(str).eq(semantic_id)] if not mapping.empty and "semantic_id" in mapping.columns else pd.DataFrame()
        resolved = not mapping_row.empty and str(mapping_row.iloc[-1].get("status") or "ok").casefold() != "failed"
        round_share = rounds_with_signal / len(round_features) if len(round_features) else 0.0
        demo_share = demos_with_signal / total_demos if total_demos else 0.0
        blocking = bool(required_features and materialized and resolved and round_share < float(ctx.quality["semantic_health"]["minimum_nonzero_round_share"]))
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "semantic_id": semantic_id,
                "required_feature_count": len(required_features),
                "materialized_feature_count": len(materialized),
                "physical_regions": mapping_row.iloc[-1].get("physical_regions") if not mapping_row.empty else None,
                "source_places": mapping_row.iloc[-1].get("source_places") if not mapping_row.empty else None,
                "rounds": len(round_features),
                "features_non_null": int(sum(round_features[feature].notna().any() for feature in materialized)) if materialized else 0,
                "features_non_zero": int(sum((numeric[feature].fillna(0) != 0).any() for feature in numeric.columns)) if not numeric.empty else 0,
                "rounds_with_any_signal": rounds_with_signal,
                "round_signal_share": round_share,
                "demos_with_any_signal": demos_with_signal,
                "demo_signal_share": demo_share,
                "mean_signal": safe_float(per_round.mean()) if len(per_round) else None,
                "median_signal": safe_float(per_round.median()) if len(per_round) else None,
                "all_zero_feature_count": int(sum((numeric[feature].fillna(0) == 0).all() for feature in numeric.columns)) if not numeric.empty else 0,
                "near_constant_feature_count": int(sum(dominant_share(round_features[feature]) >= float(ctx.quality["degeneracy"]["near_constant_share"]) for feature in materialized)) if materialized else 0,
                "status": "failed" if blocking else ("ok" if materialized else "warning"),
                "blocking": blocking,
                "notes": "Required resolved semantic has no meaningful signal." if blocking else "Semantic signal assessed from Feature Contract.",
            }
        )
    return pd.DataFrame(rows)


def load_region_mapping(ctx: GateContext) -> pd.DataFrame:
    path = ctx.gold_dir / "maps" / ctx.map_id / "region_mapping" / f"{ctx.map_id}_semantic_mapping.parquet"
    return read_catalog(path) if path.exists() else pd.DataFrame()


def build_region_presence_sanity(region_presence: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    if region_presence.empty:
        return pd.DataFrame(columns=["map_id", "target_team", "region_id", "region_group", "status"])
    rows = []
    group_cols = [column for column in ["region_name", "region_group"] if column in region_presence.columns]
    for keys, group in region_presence.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        key_values = dict(zip(group_cols, keys, strict=False))
        numeric_cols = [column for column in group.columns if column.startswith("players_") or column in {"presence_count", "rounds_present"}]
        signal = group[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) if numeric_cols else pd.Series(0, index=group.index)
        observed = bool((signal > 0).any())
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "region_id": key_values.get("region_name"),
                "region_group": key_values.get("region_group"),
                "rounds_observed": nunique(group, "round_id") or nunique(group, "round_feature_id"),
                "demos_observed": nunique(group, "parse_id"),
                "rows": len(group),
                "presence_count": int((signal > 0).sum()),
                "presence_share": float((signal > 0).mean()) if len(signal) else 0.0,
                "semantic_tags": key_values.get("region_group"),
                "expected_active": True,
                "observed": observed,
                "status": "ok" if observed else "warning",
                "notes": "Region has observed signal." if observed else "Mapped region appears absent in region presence table.",
            }
        )
    return pd.DataFrame(rows)


def build_temporal_feature_consistency(round_features: pd.DataFrame, contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    if contract.empty or round_features.empty:
        return pd.DataFrame()
    temporal = contract[
        contract.get("temporal", pd.Series(index=contract.index, dtype=bool)).fillna(False)
        & contract.get("window_type", pd.Series(index=contract.index, dtype=object)).isin(["cumulative", "both"])
        & contract.get("feature_name", pd.Series(index=contract.index, dtype=object)).isin(round_features.columns)
    ].copy()
    if temporal.empty:
        return pd.DataFrame()
    temporal["feature_group"] = temporal.apply(feature_group_key, axis=1)
    rows = []
    for (group_key, semantic_id), meta_group in temporal.groupby(["feature_group", "region_semantic"], dropna=False):
        ordered = meta_group.sort_values(["window_end", "window_start"])
        columns = ordered["feature_name"].dropna().astype(str).tolist()
        if len(columns) < 2:
            continue
        numeric = round_features[columns].apply(pd.to_numeric, errors="coerce")
        violations = (numeric.diff(axis=1).iloc[:, 1:] < 0).any(axis=1)
        violation_count = int(violations.sum())
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "feature_group": group_key,
                "semantic_id": semantic_id,
                "windows_checked": len(columns),
                "rows_checked": len(round_features),
                "monotonicity_violations": violation_count,
                "violation_share": violation_count / len(round_features) if len(round_features) else 0.0,
                "status": "failed" if violation_count else "ok",
                "blocking": bool(violation_count),
                "notes": "Cumulative feature decreased across windows." if violation_count else "Cumulative windows are monotonic.",
            }
        )
    return pd.DataFrame(rows)


def feature_group_key(row: pd.Series) -> str:
    name = str(row.get("feature_name") or "")
    start = int(float(row.get("window_start") or 0))
    end = int(float(row.get("window_end") or 0))
    for token in [f"_{start}_{end}", f"_{end}s"]:
        if name.endswith(token):
            return name[: -len(token)]
    return name


def build_side_feature_health(scoped: dict[str, pd.DataFrame], contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    t_frame = scoped["round_features_t_side_all"]
    ct_frame = scoped["round_features_ct_side"]
    columns = sorted(set(analytical_columns(t_frame, contract)) & set(analytical_columns(ct_frame, contract)))
    rows = []
    for feature in columns:
        t_series = t_frame[feature]
        ct_series = ct_frame[feature]
        t_num = pd.to_numeric(t_series, errors="coerce")
        ct_num = pd.to_numeric(ct_series, errors="coerce")
        t_zero = zero_share(t_series)
        ct_zero = zero_share(ct_series)
        flag = abs(t_zero - ct_zero) >= float(ctx.quality["distribution_sanity"]["large_zero_share_difference"])
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "feature_name": feature,
                "t_rows": len(t_series),
                "ct_rows": len(ct_series),
                "t_missing_share": float(t_series.isna().mean()) if len(t_series) else 0.0,
                "ct_missing_share": float(ct_series.isna().mean()) if len(ct_series) else 0.0,
                "t_zero_share": t_zero,
                "ct_zero_share": ct_zero,
                "t_median": safe_float(t_num.median()) if t_num.notna().any() else None,
                "ct_median": safe_float(ct_num.median()) if ct_num.notna().any() else None,
                "side_asymmetry_flag": flag,
                "status": "warning" if flag else "ok",
                "notes": "Large T/CT zero-share asymmetry; tactical interpretation deferred." if flag else "T/CT distribution assessed.",
            }
        )
    return pd.DataFrame(rows)


def build_ab_label_quality(scoped: dict[str, pd.DataFrame], ctx: GateContext) -> pd.DataFrame:
    state = scoped["round_state_resolved"]
    t_all = scoped["round_features_t_side_all"]
    planted = scoped["round_features_t_side_planted"]
    labels = planted.get("target_site_model_label", pd.Series(dtype=object))
    a_count = int((labels == "A").sum())
    b_count = int((labels == "B").sum())
    invalid_site = int((~labels.dropna().isin(["A", "B"])).sum())
    duplicate_rounds = int(planted.duplicated("round_id").sum()) if "round_id" in planted.columns else 0
    minority = min(a_count, b_count) if a_count or b_count else 0
    status = "failed" if invalid_site or duplicate_rounds or minority == 0 else "ok"
    return pd.DataFrame(
        [
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "t_rounds": len(t_all),
                "plant_rounds": int(state.get("bomb_planted", pd.Series(dtype=bool)).fillna(False).map(bool).sum()) if not state.empty else 0,
                "target_team_plant_rounds": int(state.get("target_team_planted", pd.Series(dtype=bool)).fillna(False).map(bool).sum()) if not state.empty else 0,
                "high_confidence_plant_labels": len(planted),
                "a_labels": a_count,
                "b_labels": b_count,
                "a_share": a_count / len(planted) if len(planted) else 0.0,
                "b_share": b_count / len(planted) if len(planted) else 0.0,
                "minority_class": "A" if a_count <= b_count else "B",
                "minority_class_count": minority,
                "minority_class_share": minority / len(planted) if len(planted) else 0.0,
                "missing_site": int(labels.isna().sum()),
                "invalid_site": invalid_site,
                "duplicate_rounds": duplicate_rounds,
                "demos_with_a": nunique(planted[labels == "A"], "parse_id") if len(planted) else 0,
                "demos_with_b": nunique(planted[labels == "B"], "parse_id") if len(planted) else 0,
                "label_status": status,
                "notes": "A/B labels are high-confidence T-side plants only." if status == "ok" else "Label quality blocker detected.",
            }
        ]
    )


def build_ab_label_crosscheck(scoped: dict[str, pd.DataFrame], ctx: GateContext) -> pd.DataFrame:
    state = scoped["round_state_resolved"]
    planted = state[state.get("target_site_model_label", pd.Series(index=state.index, dtype=object)).isin(["A", "B"])].copy() if not state.empty else pd.DataFrame()
    rows = []
    for _, row in planted.iterrows():
        label = row.get("target_site_model_label")
        bomb_site = normalize_bombsite(row.get("bombsite"))
        consistent = bool(bomb_site in {None, "", label} or pd.isna(bomb_site))
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "round_id": row.get("round_id"),
                "parse_id": row.get("parse_id"),
                "round_num": row.get("round_num"),
                "round_state_label": label,
                "bomb_event_site": bomb_site,
                "consistent": consistent,
                "label_confidence": row.get("label_confidence"),
                "status": "ok" if consistent else "failed",
            }
        )
    return pd.DataFrame(rows)


def normalize_bombsite(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in {"A", "B"}:
        return text
    if text in {"BOMBSITEA", "SITEA"}:
        return "A"
    if text in {"BOMBSITEB", "SITEB"}:
        return "B"
    return text or None


def build_modeling_sample_readiness(label_quality: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    row = label_quality.iloc[0] if not label_quality.empty else pd.Series(dtype=object)
    planted = int(row.get("high_confidence_plant_labels", 0) or 0)
    a_count = int(row.get("a_labels", 0) or 0)
    b_count = int(row.get("b_labels", 0) or 0)
    minority = min(a_count, b_count) if a_count or b_count else 0
    cfg = ctx.quality["modeling_sample"]
    exploratory = planted >= int(cfg["exploratory_min_total"]) and minority >= int(cfg["exploratory_min_class"])
    baseline = planted >= int(cfg["baseline_min_total"]) and minority >= int(cfg["baseline_min_class"])
    robust = planted >= int(cfg["robust_min_total"]) and minority >= int(cfg["robust_min_class"])
    status = "robust_candidate" if robust else ("baseline_candidate" if baseline else ("exploratory_only" if exploratory else "insufficient"))
    return pd.DataFrame(
        [
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "t_rounds": int(row.get("t_rounds", 0) or 0),
                "planted_t_rounds": planted,
                "a_count": a_count,
                "b_count": b_count,
                "minority_class_count": minority,
                "unique_demos": None,
                "demos_with_both_classes": min(int(row.get("demos_with_a", 0) or 0), int(row.get("demos_with_b", 0) or 0)),
                "sample_status": status,
                "ready_for_exploratory_modeling": exploratory,
                "ready_for_baseline_modeling": baseline,
                "ready_for_robust_modeling": robust,
                "blocking_reason": None if exploratory else "Insufficient high-confidence two-class planted T-side sample.",
                "limitations": "Small sample; use only controlled exploratory analysis." if exploratory and not baseline else None,
                "notes": "Readiness derives from quality config thresholds.",
            }
        ]
    )


def build_cross_map_feature_sanity(gold_dir: Path, contract: pd.DataFrame, *, target_team: str, registry_path: Path) -> pd.DataFrame:
    path = gold_dir / "round_features" / "round_features_mvp.parquet"
    if not path.exists() or contract.empty:
        return pd.DataFrame()
    frame = read_catalog(path)
    mirage = scoped_team_map(frame, target_team=target_team, map_name="Mirage", registry_path=registry_path)
    inferno = scoped_team_map(frame, target_team=target_team, map_name="Inferno", registry_path=registry_path)
    comparable = contract[
        contract.get("cross_map_comparable", pd.Series(index=contract.index, dtype=bool)).fillna(False)
        & contract.get("cross_map_comparison_mode", pd.Series(index=contract.index, dtype=object)).isin(["direct", "semantic"])
    ]
    rows = []
    for _, meta in comparable.iterrows():
        feature = str(meta.get("feature_name") or "")
        if feature not in mirage.columns or feature not in inferno.columns or feature in IDENTIFIER_COLUMNS:
            continue
        m = pd.to_numeric(mirage[feature], errors="coerce").dropna().astype(float)
        i = pd.to_numeric(inferno[feature], errors="coerce").dropna().astype(float)
        if not m.notna().any() or not i.notna().any():
            continue
        m_p25, m_p75 = float(m.quantile(0.25)), float(m.quantile(0.75))
        i_p25, i_p75 = float(i.quantile(0.25)), float(i.quantile(0.75))
        pooled_iqr = max(((m_p75 - m_p25) + (i_p75 - i_p25)) / 2, 1e-9)
        shift = abs(float(m.median()) - float(i.median())) / pooled_iqr
        structural = bool(m.nunique(dropna=True) > 5 and i.nunique(dropna=True) <= 1)
        rows.append(
            {
                "feature_name": feature,
                "comparison_mode": meta.get("cross_map_comparison_mode"),
                "coordinate_dependency": meta.get("coordinate_dependency"),
                "region_semantic": meta.get("region_semantic"),
                "mirage_rows": len(mirage),
                "inferno_rows": len(inferno),
                "mirage_missing_share": float(mirage[feature].isna().mean()) if len(mirage) else 0.0,
                "inferno_missing_share": float(inferno[feature].isna().mean()) if len(inferno) else 0.0,
                "mirage_zero_share": zero_share(mirage[feature]),
                "inferno_zero_share": zero_share(inferno[feature]),
                "mirage_unique_values": int(mirage[feature].nunique(dropna=True)),
                "inferno_unique_values": int(inferno[feature].nunique(dropna=True)),
                "mirage_median": safe_float(m.median()),
                "inferno_median": safe_float(i.median()),
                "mirage_p25": m_p25,
                "mirage_p75": m_p75,
                "inferno_p25": i_p25,
                "inferno_p75": i_p75,
                "mirage_std": safe_float(m.std(ddof=0)),
                "inferno_std": safe_float(i.std(ddof=0)),
                "median_difference": safe_float(float(i.median()) - float(m.median())),
                "pooled_iqr": pooled_iqr,
                "robust_location_shift": shift,
                "range_overlap_share": range_overlap_share(m, i),
                "zero_share_difference": abs(zero_share(mirage[feature]) - zero_share(inferno[feature])),
                "distribution_shift_flag": shift >= 3.0,
                "structural_mismatch": structural,
                "status": "warning" if structural or shift >= 3.0 else "ok",
                "notes": "Potential structural comparable-feature mismatch; tactical interpretation deferred." if structural else "Cross-map comparable distribution profiled.",
            }
        )
    return pd.DataFrame(rows)


def build_noncomparable_feature_inventory(contract: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    if contract.empty:
        return pd.DataFrame()
    noncomp = contract[
        ~contract.get("cross_map_comparable", pd.Series(index=contract.index, dtype=bool)).fillna(False)
        | contract.get("cross_map_comparison_mode", pd.Series(index=contract.index, dtype=object)).isin(["normalized_required", "map_specific_only"])
    ]
    rows = []
    for _, row in noncomp.iterrows():
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "feature_name": row.get("feature_name"),
                "reason": row.get("cross_map_notes") or "Feature is not eligible for direct cross-map comparison.",
                "comparison_mode": row.get("cross_map_comparison_mode"),
            }
        )
    return pd.DataFrame(rows)


def build_round_quality_flags(scoped: dict[str, pd.DataFrame], outputs: dict[str, pd.DataFrame], ctx: GateContext) -> pd.DataFrame:
    round_features = scoped["round_features_mvp"]
    round_state = scoped["round_state_resolved"]
    rows = []
    domain = outputs["map_feature_domain_validation"]
    for _, check in domain[domain.get("status", pd.Series(dtype=object)).eq("failed")].iterrows() if not domain.empty else []:
        feature = str(check["feature_name"])
        if feature not in round_features.columns:
            continue
        rule = domain_rule_for_feature(feature)
        if rule is None:
            continue
        invalid = domain_invalid_mask(round_features[feature], rule)
        for _, row in round_features.loc[invalid].head(50).iterrows():
            rows.append(round_flag(ctx, row, "invalid_domain", feature, None, "critical", True, f"{feature} violates domain rule {check['domain_rule']}"))
    temporal = outputs["map_temporal_feature_consistency"]
    for _, check in temporal[temporal.get("status", pd.Series(dtype=object)).eq("failed")].iterrows() if not temporal.empty else []:
        rows.append(round_flag(ctx, {}, "temporal_inconsistency", str(check.get("feature_group")), str(check.get("semantic_id")), "critical", True, "Cumulative temporal consistency failed."))
    labels = outputs["map_ab_label_crosscheck"]
    for _, conflict in labels[labels.get("status", pd.Series(dtype=object)).eq("failed")].iterrows() if not labels.empty else []:
        match = round_state[round_state.get("round_id", pd.Series(dtype=object)).astype(str).eq(str(conflict.get("round_id")))]
        row = match.iloc[0] if not match.empty else conflict
        rows.append(round_flag(ctx, row, "label_conflict", "target_site_model_label", None, "critical", True, "Round-state label conflicts with bombsite evidence."))
    semantics = outputs["map_semantic_signal_health"]
    for _, semantic in semantics[semantics.get("status", pd.Series(dtype=object)).eq("failed")].iterrows() if not semantics.empty else []:
        rows.append(round_flag(ctx, {}, "semantic_signal_failure", None, str(semantic.get("semantic_id")), "critical", True, "Required semantic signal is absent."))
    return pd.DataFrame(rows)


def round_flag(ctx: GateContext, row: Any, category: str, feature: str | None, semantic: str | None, severity: str, blocking: bool, reason: str) -> dict[str, object]:
    getter = row.get if hasattr(row, "get") else lambda _key, default=None: default
    return {
        "map_id": ctx.map_id,
        "target_team": ctx.target_team,
        "round_id": getter("round_id"),
        "round_feature_id": getter("round_feature_id"),
        "parse_id": getter("parse_id"),
        "round_num": getter("round_num"),
        "target_team_side": getter("target_team_side"),
        "issue_category": category,
        "feature_name": feature,
        "semantic_id": semantic,
        "severity": severity,
        "blocking": blocking,
        "reason": reason,
    }


def build_quality_review_sample(scoped: dict[str, pd.DataFrame], flags: pd.DataFrame, round_features: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    state = scoped["round_state_resolved"]
    max_rows = int(ctx.quality.get("review_sample", {}).get("max_rows", 40))
    selected_ids: list[str] = []
    rows = []
    for _, flag in flags.head(max_rows // 2).iterrows() if not flags.empty else []:
        rid = str(flag.get("round_id") or flag.get("round_feature_id") or "")
        if rid:
            selected_ids.append(rid)
            rows.append(review_row(ctx, flag, "flagged_round", 1, round_features))
    scenarios = [
        ("A", "a_plant"),
        ("B", "b_plant"),
        (None, "representative_normal"),
    ]
    for label, reason in scenarios:
        subset = state
        if label:
            subset = subset[subset.get("target_site_model_label", pd.Series(index=subset.index, dtype=object)).eq(label)]
        for _, row in subset.sort_values(["parse_id", "round_num"], kind="mergesort").head(5).iterrows():
            key = str(row.get("round_id") or row.get("round_feature_id"))
            if key not in selected_ids and len(rows) < max_rows:
                selected_ids.append(key)
                rows.append(review_row(ctx, row, reason, 2, round_features))
    return pd.DataFrame(rows)


def review_row(ctx: GateContext, row: pd.Series, reason: str, priority: int, round_features: pd.DataFrame) -> dict[str, object]:
    feature_row = pd.Series(dtype=object)
    if "round_feature_id" in row.index and "round_feature_id" in round_features.columns:
        match = round_features[round_features["round_feature_id"].astype(str).eq(str(row.get("round_feature_id")))]
        if not match.empty:
            feature_row = match.iloc[0]
    selected = {feature: feature_row.get(feature) for feature in ["smokes_used_0_15", "molotovs_used_0_15", "players_mid_control_0_15", "players_a_pressure_0_15", "players_b_pressure_0_15"] if feature in feature_row.index}
    return {
        "map_id": ctx.map_id,
        "target_team": ctx.target_team,
        "round_id": row.get("round_id"),
        "parse_id": row.get("parse_id"),
        "round_num": row.get("round_num"),
        "target_team_side": row.get("target_team_side"),
        "target_site_model_label": row.get("target_site_model_label"),
        "review_reason": reason,
        "priority": priority,
        **selected,
    }


def build_scorecard(outputs: dict[str, pd.DataFrame], preconditions: pd.DataFrame, before_fingerprints: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    categories = {
        "dataset_integrity": outputs["map_dataset_reconciliation"],
        "feature_missingness": outputs["map_feature_missingness"],
        "feature_domains": outputs["map_feature_domain_validation"],
        "feature_degeneracy": outputs["map_feature_degeneracy"],
        "semantic_health": outputs["map_semantic_signal_health"],
        "temporal_consistency": outputs["map_temporal_feature_consistency"],
        "round_state": preconditions,
        "label_quality": outputs["map_ab_label_crosscheck"],
        "cross_map_sanity": outputs["mirage_inferno_feature_sanity"],
        "sample_size": outputs["map_modeling_sample_readiness"],
    }
    rows = []
    for category, frame in categories.items():
        status_series = frame.get("status", pd.Series(dtype=object)) if not frame.empty else pd.Series(dtype=object)
        failed = int(status_series.eq("failed").sum())
        warnings = int(status_series.eq("warning").sum())
        passed = int(status_series.eq("ok").sum())
        blocking = int(frame.get("blocking", pd.Series(dtype=bool)).fillna(False).sum()) if not frame.empty and "blocking" in frame.columns else failed
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "category": category,
                "checks": len(frame),
                "passed": passed,
                "warnings": warnings,
                "failed": failed,
                "blocking_failures": blocking,
                "status": "failed" if blocking else ("warning" if warnings or failed else "ok"),
                "notes": "Category assessed by Stage 8.9 quality gate.",
            }
        )
    return pd.DataFrame(rows)


def capture_core_fingerprints(frames: dict[str, pd.DataFrame], ctx: GateContext) -> pd.DataFrame:
    scoped = build_scoped_frames(frames, ctx) if "round_features_mvp" in frames else {}
    rows = []
    for name in CORE_READ_ONLY_DATASETS:
        frame = scoped.get(name, pd.DataFrame())
        spec = GOLD_DATASET_SPECS[name]
        keys = [column for column in spec.key_columns if column in frame.columns]
        rows.append(
            {
                "map_id": ctx.map_id,
                "target_team": ctx.target_team,
                "dataset_name": name,
                "row_count": len(frame),
                "schema_hash": schema_hash(frame) if not frame.empty else "",
                "content_hash": content_hash(frame, keys),
                "captured_at": now_utc(),
            }
        )
    return pd.DataFrame(rows)


def build_read_only_audit(before: pd.DataFrame, after: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    merged = before.merge(after, on=["map_id", "target_team", "dataset_name"], how="outer", suffixes=("_before", "_after"))
    merged["row_count_unchanged"] = merged["row_count_before"].eq(merged["row_count_after"])
    merged["schema_hash_unchanged"] = merged["schema_hash_before"].eq(merged["schema_hash_after"])
    merged["content_hash_unchanged"] = merged["content_hash_before"].eq(merged["content_hash_after"])
    merged["unchanged"] = merged["row_count_unchanged"] & merged["schema_hash_unchanged"] & merged["content_hash_unchanged"]
    merged["status"] = np.where(merged["unchanged"], "ok", "failed")
    merged["blocking"] = ~merged["unchanged"]
    merged["notes"] = np.where(merged["unchanged"], "Core Gold input unchanged.", "Core Gold input changed during read-only gate.")
    return merged


def build_final_audit(outputs: dict[str, pd.DataFrame], preconditions: pd.DataFrame, ctx: GateContext) -> pd.DataFrame:
    scorecard = outputs["map_quality_scorecard"]
    reconciliation = outputs["map_dataset_reconciliation"]
    profile = outputs["map_feature_quality_profile"]
    missing = outputs["map_feature_missingness"]
    domains = outputs["map_feature_domain_validation"]
    semantics = outputs["map_semantic_signal_health"]
    temporal = outputs["map_temporal_feature_consistency"]
    labels = outputs["map_ab_label_quality"].iloc[0] if not outputs["map_ab_label_quality"].empty else pd.Series(dtype=object)
    sample = outputs["map_modeling_sample_readiness"].iloc[0] if not outputs["map_modeling_sample_readiness"].empty else pd.Series(dtype=object)
    state = outputs["map_dataset_reconciliation"]
    round_state_rows = int(state.loc[state["dataset_name"].eq("round_state_resolved"), "row_count"].iloc[0]) if not state.empty and state["dataset_name"].eq("round_state_resolved").any() else 0
    side_counts = read_round_side_counts(ctx)
    blocking = int(scorecard["blocking_failures"].sum()) if not scorecard.empty else 1
    nonblocking_failed = max(int(scorecard["failed"].sum()) - int(scorecard["blocking_failures"].sum()), 0) if not scorecard.empty else 0
    warnings = int(scorecard["warnings"].sum()) + nonblocking_failed if not scorecard.empty else 0
    mirage_passed = mirage_regression_passed(ctx)
    ready_eda = bool(
        preconditions["passed"].all()
        and mirage_passed
        and int((reconciliation["status"] == "failed").sum()) == 0
        and int(missing.get("blocking", pd.Series(dtype=bool)).fillna(False).sum()) == 0
        and int(domains.get("blocking", pd.Series(dtype=bool)).fillna(False).sum()) == 0
        and int(semantics.get("blocking", pd.Series(dtype=bool)).fillna(False).sum()) == 0
        and int(outputs["map_ab_label_crosscheck"].get("status", pd.Series(dtype=object)).eq("failed").sum()) == 0
        and int(outputs["map_feature_quality_read_only_audit"].get("status", pd.Series(dtype=object)).eq("failed").sum()) == 0
    )
    readiness = str(sample.get("sample_status") or "insufficient")
    modeling_level = {"insufficient": "blocked", "exploratory_only": "exploratory_only", "baseline_candidate": "baseline_ready", "robust_candidate": "robust_ready"}.get(readiness, "blocked")
    return pd.DataFrame(
        [
            {
                "audit_id": f"map_feature_quality_{ctx.map_id}_{normalize_id(ctx.target_team)}",
                "map_id": ctx.map_id,
                "map_name": ctx.map_name,
                "target_team": ctx.target_team,
                "stage_8_8_ready": bool(preconditions.loc[preconditions["check_id"].eq("stage_8_8_ready"), "passed"].iloc[0]) if not preconditions.empty else False,
                "round_features": int(reconciliation.loc[reconciliation["dataset_name"].eq("round_features_mvp"), "row_count"].iloc[0]) if not reconciliation.empty else 0,
                "round_state_rows": round_state_rows,
                "t_rounds": side_counts["T"],
                "ct_rounds": side_counts["CT"],
                "unknown_side_rounds": side_counts["unknown"],
                "planted_t_rounds": int(labels.get("high_confidence_plant_labels", 0) or 0),
                "a_labels": int(labels.get("a_labels", 0) or 0),
                "b_labels": int(labels.get("b_labels", 0) or 0),
                "minority_class_count": int(labels.get("minority_class_count", 0) or 0),
                "features_evaluated": len(profile),
                "features_all_null": int(profile.get("all_null", pd.Series(dtype=bool)).fillna(False).sum()) if not profile.empty else 0,
                "features_constant": int(profile.get("constant", pd.Series(dtype=bool)).fillna(False).sum()) if not profile.empty else 0,
                "features_near_constant": int(profile.get("near_constant", pd.Series(dtype=bool)).fillna(False).sum()) if not profile.empty else 0,
                "features_all_zero": int(profile.get("all_zero", pd.Series(dtype=bool)).fillna(False).sum()) if not profile.empty else 0,
                "unexpected_missing_features": int(missing.get("unexpected_missingness", pd.Series(dtype=bool)).fillna(False).sum()) if not missing.empty else 0,
                "invalid_domain_features": int(domains.get("status", pd.Series(dtype=object)).eq("failed").sum()) if not domains.empty else 0,
                "required_semantics": int((semantics.get("required_feature_count", pd.Series(dtype=int)).fillna(0) > 0).sum()) if not semantics.empty else 0,
                "healthy_semantics": int((semantics.get("status", pd.Series(dtype=object)).eq("ok")).sum()) if not semantics.empty else 0,
                "failed_semantics": int((semantics.get("status", pd.Series(dtype=object)).eq("failed")).sum()) if not semantics.empty else 0,
                "temporal_checks": len(temporal),
                "temporal_failures": int(temporal.get("status", pd.Series(dtype=object)).eq("failed").sum()) if not temporal.empty else 0,
                "dataset_reconciliation_failures": int(reconciliation.get("status", pd.Series(dtype=object)).eq("failed").sum()) if not reconciliation.empty else 0,
                "label_conflicts": int(outputs["map_ab_label_crosscheck"].get("status", pd.Series(dtype=object)).eq("failed").sum()) if not outputs["map_ab_label_crosscheck"].empty else 0,
                "comparable_features_checked": len(outputs["mirage_inferno_feature_sanity"]),
                "cross_map_structural_mismatches": int(outputs["mirage_inferno_feature_sanity"].get("structural_mismatch", pd.Series(dtype=bool)).fillna(False).sum()) if not outputs["mirage_inferno_feature_sanity"].empty else 0,
                "modeling_sample_status": readiness,
                "critical_failures": blocking + (0 if mirage_passed else 1),
                "warnings": warnings,
                "ready_for_multi_map_eda": ready_eda,
                "ready_for_inferno_modeling_experiment": bool(ready_eda and modeling_level != "blocked"),
                "modeling_readiness_level": modeling_level,
                "mirage_regression_passed": mirage_passed,
                "status": "passed" if ready_eda else "failed",
                "created_at": now_utc(),
            }
        ]
    )


def read_round_side_counts(ctx: GateContext) -> dict[str, int]:
    path = ctx.gold_dir / "round_state" / "round_state_resolved.parquet"
    if not path.exists():
        return {"T": 0, "CT": 0, "unknown": 0}
    state = scoped_team_map(read_catalog(path), target_team=ctx.target_team, map_name=ctx.map_name, registry_path=ctx.registry_path)
    return {
        "T": int((state.get("target_team_side", pd.Series(dtype=object)) == "T").sum()),
        "CT": int((state.get("target_team_side", pd.Series(dtype=object)) == "CT").sum()),
        "unknown": int((state.get("target_team_side", pd.Series(dtype=object)) == "unknown").sum()),
    }


def mirage_regression_passed(ctx: GateContext) -> bool:
    path = ctx.gold_dir / "validation" / "mirage_regression_gate" / "mirage_regression_summary.parquet"
    if not path.exists():
        return False
    summary = read_catalog(path)
    return bool(not summary.empty and str(summary.iloc[0].get("overall_status") or "").casefold() == "passed")


def write_quality_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, map_id: str, target_team: str, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    paths = {}
    for name in OUTPUT_NAMES:
        frame = sanitize_for_parquet(frames.get(name, pd.DataFrame()))
        if frame.empty and not {"map_id", "target_team"}.issubset(frame.columns):
            frame = pd.DataFrame(columns=["map_id", "target_team"])
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            existing = read_existing_output(path)
            if path.exists() and not force and not existing.empty and same_quality_scope_exists(existing, map_id, target_team):
                paths[f"{name}_{suffix}"] = path
                continue
            combined = upsert_quality_scope(existing, frame, map_id=map_id, target_team=target_team)
            combined = sanitize_for_parquet(combined)
            if suffix == "csv":
                combined.to_csv(path, index=False)
            else:
                combined.to_parquet(path, index=False)
            paths[f"{name}_{suffix}"] = path
    return paths


def read_existing_output(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return read_catalog(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def upsert_quality_scope(existing: pd.DataFrame, incoming: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    if existing.empty:
        return incoming.copy().reset_index(drop=True)
    if incoming.empty:
        return existing.copy().reset_index(drop=True)
    columns = list(dict.fromkeys([*existing.columns, *incoming.columns]))
    existing = existing.reindex(columns=columns)
    incoming = incoming.reindex(columns=columns)
    if {"map_id", "target_team"}.issubset(existing.columns):
        mask = existing["map_id"].astype(str).eq(map_id) & existing["target_team"].astype(str).str.casefold().eq(target_team.casefold())
        existing = existing.loc[~mask].copy()
    combined = pd.concat([existing, incoming], ignore_index=True)
    sort_cols = [column for column in ["map_id", "target_team", "dataset_name", "feature_name", "parse_id", "round_id"] if column in combined.columns]
    return combined.sort_values(sort_cols, kind="mergesort").reset_index(drop=True) if sort_cols else combined.reset_index(drop=True)


def same_quality_scope_exists(frame: pd.DataFrame, map_id: str, target_team: str) -> bool:
    return {"map_id", "target_team"}.issubset(frame.columns) and bool((frame["map_id"].astype(str).eq(map_id) & frame["target_team"].astype(str).str.casefold().eq(target_team.casefold())).any())


def write_report(frames: dict[str, pd.DataFrame], ctx: GateContext, *, force: bool) -> Path:
    path = ctx.project_root / "docs" / "inferno_feature_quality.md"
    if path.exists() and not force:
        return path
    ensure_dir(path.parent)
    path.write_text(build_report(frames, ctx), encoding="utf-8")
    return path


def build_report(frames: dict[str, pd.DataFrame], ctx: GateContext) -> str:
    audit = frames["map_feature_quality_audit"].iloc[0]
    sections = [
        "# Inferno Feature Quality & Tactical Readiness Gate",
        "",
        "## Purpose",
        "Validate whether the scoped Inferno Gold features are technically reliable for analysis and whether the A/B sample is ready for modeling experiments.",
        "",
        "## Stage 8.8 Input",
        f"Map/team scope: `{ctx.map_name}` / `{ctx.target_team}`.",
        "",
        "## Dataset Reconciliation",
        markdown_table(frames["map_dataset_reconciliation"], ["dataset_name", "row_count", "duplicate_key_count", "missing_key_count", "relationship_passed", "status", "notes"]),
        "",
        "## Feature Missingness",
        markdown_table(top_status(frames["map_feature_missingness"]), ["feature_name", "missing_share", "expected_missingness", "severity", "status", "notes"]),
        "",
        "## Feature Domains",
        markdown_table(top_status(frames["map_feature_domain_validation"]), ["feature_name", "domain_rule", "invalid_rows", "severity", "status"]),
        "",
        "## Degenerate Features",
        markdown_table(top_status(frames["map_feature_degeneracy"]), ["feature_name", "zero_share", "constant", "near_constant", "all_zero", "severity", "status", "notes"]),
        "",
        "## Per-Demo Health",
        markdown_table(frames["map_demo_quality_summary"], list(frames["map_demo_quality_summary"].columns)),
        "",
        "## Semantic Signal Health",
        markdown_table(frames["map_semantic_signal_health"], ["semantic_id", "required_feature_count", "materialized_feature_count", "round_signal_share", "demo_signal_share", "status", "notes"]),
        "",
        "## Region Presence",
        markdown_table(top_status(frames["map_region_presence_sanity"]), ["region_id", "region_group", "presence_share", "status", "notes"]),
        "",
        "## Temporal Consistency",
        markdown_table(top_status(frames["map_temporal_feature_consistency"]), ["feature_group", "semantic_id", "windows_checked", "monotonicity_violations", "status", "notes"]),
        "",
        "## Side Health",
        markdown_table(top_status(frames["map_side_feature_health"]), ["feature_name", "t_zero_share", "ct_zero_share", "side_asymmetry_flag", "status", "notes"]),
        "",
        "## A/B Label Quality",
        markdown_table(frames["map_ab_label_quality"], list(frames["map_ab_label_quality"].columns)),
        "",
        "## Sample Size",
        markdown_table(frames["map_modeling_sample_readiness"], list(frames["map_modeling_sample_readiness"].columns)),
        "",
        "## Mirage vs Inferno Comparable Features",
        markdown_table(top_status(frames["mirage_inferno_feature_sanity"]), ["feature_name", "comparison_mode", "mirage_zero_share", "inferno_zero_share", "robust_location_shift", "structural_mismatch", "status", "notes"]),
        "",
        "## Non-Comparable Features",
        markdown_table(frames["map_noncomparable_feature_inventory"], ["feature_name", "reason", "comparison_mode"]),
        "",
        "## Round-Level Flags",
        markdown_table(frames["map_round_quality_flags"], list(frames["map_round_quality_flags"].columns)),
        "",
        "## Quality Scorecard",
        markdown_table(frames["map_quality_scorecard"], list(frames["map_quality_scorecard"].columns)),
        "",
        "## Modeling Limitations",
        str(frames["map_modeling_sample_readiness"].iloc[0].get("limitations") if not frames["map_modeling_sample_readiness"].empty else "No sample readiness row."),
        "",
        "## Readiness",
        f"ready_for_multi_map_eda: `{bool(audit['ready_for_multi_map_eda'])}`",
        f"ready_for_inferno_modeling_experiment: `{bool(audit['ready_for_inferno_modeling_experiment'])}`",
        f"modeling_readiness_level: `{audit['modeling_readiness_level']}`",
        f"status: `{audit['status']}`",
        "",
        "## Next Stage",
        "If multi-map EDA is ready, the next stage is Stage 8.10 -- Vitality Multi-Map Tactical EDA: Mirage vs Inferno. This report does not make tactical conclusions.",
        "",
    ]
    return "\n".join(sections)


def write_notebook(path: Path, *, force: bool) -> Path:
    if path.exists() and not force:
        return path
    ensure_dir(path.parent)
    notebook = {
        "cells": [
            md("# Stage 8.9 -- Inferno Feature Quality"),
            code("from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\nBASE = Path('../data/gold/validation/map_feature_quality')\ndef load(name):\n    return pd.read_parquet(BASE / f'{name}.parquet')"),
            md("## Final Scorecard"),
            code("scorecard = load('map_quality_scorecard')\ndisplay(scorecard)\nscorecard.plot.bar(x='category', y=['passed', 'warnings', 'failed'], stacked=True, figsize=(10, 4))\nplt.tight_layout()"),
            md("## Feature Missingness Distribution"),
            code("missing = load('map_feature_missingness')\ndisplay(missing.sort_values('missing_share', ascending=False).head(20))\nmissing.sort_values('missing_share', ascending=False).head(20).plot.bar(x='feature_name', y='missing_share', figsize=(12, 4))\nplt.tight_layout()"),
            md("## Zero Share Distribution"),
            code("profile = load('map_feature_quality_profile')\ndisplay(profile.sort_values('zero_share', ascending=False).head(20))\nprofile.sort_values('zero_share', ascending=False).head(20).plot.bar(x='feature_name', y='zero_share', figsize=(12, 4))\nplt.tight_layout()"),
            md("## Constant / Near-Constant Features"),
            code("display(profile[(profile['constant']) | (profile['near_constant']) | (profile['all_zero'])].head(50))"),
            md("## Semantic Signal Health"),
            code("semantic = load('map_semantic_signal_health')\ndisplay(semantic)\nsemantic.plot.bar(x='semantic_id', y='round_signal_share', figsize=(8, 4))\nplt.tight_layout()"),
            md("## Feature Health by Demo"),
            code("demo = load('map_demo_quality_summary')\ndisplay(demo)\ndemo.plot.bar(x='parse_id', y=['degenerate_feature_count', 'semantic_failure_count'], figsize=(10, 4))\nplt.tight_layout()"),
            md("## T vs CT Summary"),
            code("side = load('map_side_feature_health')\ndisplay(side.sort_values('t_zero_share', ascending=False).head(20))"),
            md("## A/B Class Balance"),
            code("labels = load('map_ab_label_quality')\ndisplay(labels)\nlabels[['a_labels', 'b_labels']].iloc[0].plot.bar(figsize=(4, 3))\nplt.tight_layout()"),
            md("## Mirage vs Inferno Comparable Features"),
            code("cross = load('mirage_inferno_feature_sanity')\ndisplay(cross.sort_values('robust_location_shift', ascending=False).head(20))\ncross.sort_values('robust_location_shift', ascending=False).head(15).plot.bar(x='feature_name', y='robust_location_shift', figsize=(12, 4))\nplt.tight_layout()"),
            md("## Flagged Rounds"),
            code("flags = load('map_round_quality_flags')\ndisplay(flags.head(50))"),
            md("## Modeling Sample Readiness"),
            code("sample = load('map_modeling_sample_readiness')\ndisplay(sample)"),
            md("## Final Gate"),
            code("audit = load('map_feature_quality_audit')\ndisplay(audit)"),
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.11"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    return path


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 30) -> str:
    if frame.empty:
        return "_No rows._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def top_status(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "status" not in frame.columns:
        return frame
    status_order = {"failed": 0, "warning": 1, "skipped": 2, "ok": 3}
    result = frame.copy()
    result["_status_order"] = result["status"].map(status_order).fillna(4)
    sort_cols = ["_status_order"]
    if "missing_share" in result.columns:
        sort_cols.append("missing_share")
    elif "zero_share" in result.columns:
        sort_cols.append("zero_share")
    return result.sort_values(sort_cols, ascending=[True] + [False] * (len(sort_cols) - 1)).drop(columns="_status_order")


def sanitize_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].map(lambda value: None if value is None or (not isinstance(value, (list, dict, tuple)) and pd.isna(value)) else ("|".join(map(str, value)) if isinstance(value, (list, tuple, set)) else json.dumps(value, sort_keys=True) if isinstance(value, dict) else value))
    return result


def zero_share(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce")
    return float((numeric == 0).sum() / len(series)) if len(series) and numeric.notna().any() else 0.0


def dominant_share(series: pd.Series) -> float:
    values = series.dropna()
    if values.empty:
        return 0.0
    counts = values.value_counts(dropna=True)
    return float(counts.iloc[0] / len(values)) if not counts.empty else 0.0


def safe_float(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def range_overlap_share(left: pd.Series, right: pd.Series) -> float:
    left = pd.to_numeric(left, errors="coerce").dropna()
    right = pd.to_numeric(right, errors="coerce").dropna()
    if left.empty or right.empty:
        return 0.0
    overlap = max(0.0, min(float(left.max()), float(right.max())) - max(float(left.min()), float(right.min())))
    union = max(float(left.max()), float(right.max())) - min(float(left.min()), float(right.min()))
    return overlap / union if union else 1.0


def nunique(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].nunique(dropna=True)) if column in frame.columns and not frame.empty else 0


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def md(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict[str, object]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def print_summary(outputs: dict[str, Path], summary: dict[str, Any]) -> None:
    print("Map feature quality gate summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a read-only map feature quality and tactical readiness gate.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-map", required=True)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quality-config", type=Path, default=Path("configs/quality/map_feature_quality.yaml"))
    parser.add_argument("--map-registry", type=Path, default=Path("configs/maps/map_registry.yaml"))
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_map_feature_quality_gate(
        args.config,
        target_map=args.target_map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
        quality_config=args.quality_config,
        map_registry_path=args.map_registry,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
