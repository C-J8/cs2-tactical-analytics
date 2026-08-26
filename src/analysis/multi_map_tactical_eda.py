from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.maps.identity import resolve_map_identity
from src.storage.scoped_gold import content_hash, map_id_series, schema_hash
from src.utils.io import ensure_dir, read_optional_table, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.reports import markdown_table as report_markdown_table
from src.utils.reports import now_utc, safe_divide as shared_safe_divide


OUTPUT_NAMES = [
    "multi_map_eda_scope_inventory",
    "multi_map_feature_eligibility",
    "t_side_map_summary",
    "plant_site_distribution",
    "direct_feature_comparison",
    "semantic_feature_comparison",
    "multi_map_temporal_profile",
    "utility_inventory_comparison",
    "utility_timing_comparison",
    "team_structure_comparison",
    "semantic_control_profile",
    "within_map_site_comparison",
    "cross_map_site_pattern_comparison",
    "plant_vs_no_plant_comparison",
    "round_outcome_summary",
    "multi_map_demo_stability",
    "opponent_sensitivity_summary",
    "multi_map_finding_candidates",
    "multi_map_ranked_findings",
    "multi_map_excluded_findings",
    "multi_map_eda_read_only_audit",
    "multi_map_tactical_eda_audit",
]

CORE_GOLD_PATHS = {
    "round_features_mvp": Path("round_features/round_features_mvp.parquet"),
    "round_state_resolved": Path("round_state/round_state_resolved.parquet"),
    "round_features_t_side_all": Path("round_features/round_features_t_side_all.parquet"),
    "round_features_t_side_planted": Path("round_features/round_features_t_side_planted.parquet"),
    "round_features_ct_side": Path("round_features/round_features_ct_side.parquet"),
    "feature_contract": Path("features/feature_contract/feature_contract.parquet"),
}

IDENTIFIER_COLUMNS = {
    "round_feature_id",
    "parse_id",
    "dem_file_id",
    "series_id",
    "round_id",
    "target_team",
    "opponent",
    "map_name",
    "round_num",
    "dataset_type",
    "canonical_map_name",
}

LABEL_AND_OUTCOME_COLUMNS = {
    "target_site_observed",
    "target_site_model_label",
    "label_source",
    "label_confidence",
    "bombsite",
    "bomb_planted",
    "winner_team",
    "winner_side",
    "target_team_planted",
    "opponent_planted",
    "target_team_side",
    "feature_quality_status",
}

ENDPOINT_PREFIXES = (
    "smokes_to_",
    "molotovs_to_",
)

UTILITY_USAGE_PREFIXES = (
    "smokes_used_",
    "flashes_used_",
    "molotovs_used_",
    "he_used_",
    "total_utility_used_",
)

UTILITY_INVENTORY_FEATURES = [
    "team_smokes_start",
    "team_flashes_start",
    "team_molotovs_start",
    "team_he_start",
    "team_decoys_start",
    "team_total_utility_start",
]

SITE_SEMANTICS = {"mid_control", "a_pressure", "b_pressure", "ct_space", "site_a", "site_b"}


@dataclass(frozen=True)
class MapRequest:
    map_id: str
    map_name: str
    requested_name: str


def run_multi_map_tactical_eda(
    config_path: Path,
    *,
    target_team: str | None = None,
    maps: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    eda_config: Path = Path("configs/analysis/multi_map_tactical_eda.yaml"),
    map_registry_path: Path = Path("configs/maps/map_registry.yaml"),
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    gold_dir = project_root / "data" / "gold"
    target_team = target_team or project.target_teams[0]
    requested_maps = maps or project.target_maps
    registry_path = resolve_project_path(project_root, map_registry_path)
    eda_config_path = resolve_project_path(project_root, eda_config)
    settings = load_eda_config(eda_config_path)
    map_requests = resolve_map_requests(requested_maps, registry_path=registry_path)
    output_dir = gold_dir / "analysis" / "multi_map_tactical_eda"

    before = capture_core_fingerprints(project_root, gold_dir)
    inputs = load_inputs(gold_dir)
    preconditions = validate_preconditions(inputs, map_requests, target_team=target_team, registry_path=registry_path, settings=settings)
    if preconditions["status"].eq("failed").any():
        failures = preconditions[preconditions["status"].eq("failed")]["notes"].tolist()
        raise RuntimeError("Stage 8.10 preconditions failed: " + " | ".join(failures))

    rounds = prepare_rounds(inputs, map_requests, target_team=target_team, registry_path=registry_path)
    cohorts = build_cohorts(rounds)
    scope_inventory = build_scope_inventory(rounds, inputs, map_requests, target_team=target_team)
    feature_eligibility = build_feature_eligibility(rounds, inputs, map_requests, target_team=target_team, settings=settings)
    comparable = feature_eligibility[feature_eligibility["eligible_for_ranked_findings"] | feature_eligibility["eligible_for_direct_comparison"] | feature_eligibility["eligible_for_semantic_comparison"]].copy()
    direct_features = comparable[comparable["eligible_for_direct_comparison"]]["feature_name"].tolist()
    semantic_features = comparable[comparable["eligible_for_semantic_comparison"]]["feature_name"].tolist()

    direct = build_feature_comparison(rounds, cohorts, direct_features, feature_eligibility, settings=settings, comparison_kind="direct")
    semantic = build_feature_comparison(rounds, cohorts, semantic_features, feature_eligibility, settings=settings, comparison_kind="semantic")
    temporal = build_temporal_profile(rounds, feature_eligibility, settings=settings)
    utility_inventory = summarize_feature_group(rounds, cohorts, [feature for feature in UTILITY_INVENTORY_FEATURES if feature in rounds.columns], "utility_inventory")
    utility_timing = build_utility_timing_comparison(rounds, cohorts, feature_eligibility, settings=settings)
    team_structure = summarize_feature_group(rounds, cohorts, structure_features(feature_eligibility), "team_structure")
    semantic_control = build_semantic_control_profile(temporal)
    within_site = build_within_map_site_comparison(rounds, comparable["feature_name"].tolist(), settings=settings)
    cross_site = build_cross_map_site_pattern(within_site)
    plant_vs_no_plant = build_plant_vs_no_plant(rounds, comparable["feature_name"].tolist(), settings=settings)
    outcome = build_round_outcome_summary(rounds)
    demo_stability = build_demo_stability(rounds, direct, settings=settings)
    findings, excluded = build_finding_candidates(direct, semantic, within_site, cross_site, plant_vs_no_plant, feature_eligibility, settings=settings)
    ranked = rank_findings(findings, settings=settings)
    opponent_sensitivity = build_opponent_sensitivity(ranked, rounds)

    frames = {
        "multi_map_eda_scope_inventory": scope_inventory,
        "multi_map_feature_eligibility": feature_eligibility,
        "t_side_map_summary": build_t_side_map_summary(rounds),
        "plant_site_distribution": build_plant_site_distribution(rounds, settings=settings),
        "direct_feature_comparison": direct,
        "semantic_feature_comparison": semantic,
        "multi_map_temporal_profile": temporal,
        "utility_inventory_comparison": utility_inventory,
        "utility_timing_comparison": utility_timing,
        "team_structure_comparison": team_structure,
        "semantic_control_profile": semantic_control,
        "within_map_site_comparison": within_site,
        "cross_map_site_pattern_comparison": cross_site,
        "plant_vs_no_plant_comparison": plant_vs_no_plant,
        "round_outcome_summary": outcome,
        "multi_map_demo_stability": demo_stability,
        "opponent_sensitivity_summary": opponent_sensitivity,
        "multi_map_finding_candidates": findings,
        "multi_map_ranked_findings": ranked,
        "multi_map_excluded_findings": excluded,
    }
    after = capture_core_fingerprints(project_root, gold_dir)
    frames["multi_map_eda_read_only_audit"] = build_read_only_audit(before, after)
    frames["multi_map_tactical_eda_audit"] = build_final_audit(
        frames,
        preconditions,
        target_team=target_team,
        map_requests=map_requests,
        settings=settings,
    )

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_outputs(frames, output_dir, force=force))
        outputs["report"] = write_markdown_report(
            build_report(frames, target_team=target_team, map_requests=map_requests),
            project_root / "docs" / "vitality_mirage_vs_inferno_eda.md",
            force=force,
        )
        outputs["notebook"] = write_notebook(project_root / "notebooks" / "25_vitality_multi_map_tactical_eda.ipynb", force=force)

    audit = frames["multi_map_tactical_eda_audit"].iloc[0]
    summary = {
        "maps_analyzed": str(audit.get("maps_analyzed")),
        "rounds_by_map": str(audit.get("rounds_by_map")),
        "t_rounds_by_map": str(audit.get("t_rounds_by_map")),
        "eligible_features": int(audit.get("direct_comparable_features", 0)) + int(audit.get("semantic_comparable_features", 0)),
        "ranked_findings": int(audit.get("ranked_findings", 0)),
        "ready_for_stage_8_11": bool(audit.get("ready_for_stage_8_11", False)),
        "status": str(audit.get("status")),
    }
    return frames, outputs, summary


def load_eda_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"EDA config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or {}
    if not isinstance(content, dict):
        raise ValueError(f"EDA config must be a mapping: {path}")
    return content


def resolve_project_path(project_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    candidate = project_root / path
    return candidate if candidate.exists() else path


def resolve_map_requests(map_names: list[str], *, registry_path: Path) -> list[MapRequest]:
    seen: set[str] = set()
    requests: list[MapRequest] = []
    for requested in map_names:
        identity = resolve_map_identity(requested, registry_path=registry_path)
        if identity.map_id in seen:
            continue
        seen.add(identity.map_id)
        requests.append(MapRequest(map_id=identity.map_id, map_name=identity.display_name, requested_name=requested))
    if len(requests) < 2:
        raise ValueError("Stage 8.10 requires at least two distinct maps.")
    return requests


def load_inputs(gold_dir: Path) -> dict[str, pd.DataFrame]:
    paths = {
        "round_features_mvp": gold_dir / "round_features" / "round_features_mvp.parquet",
        "t_side_all": gold_dir / "round_features" / "round_features_t_side_all.parquet",
        "t_side_planted": gold_dir / "round_features" / "round_features_t_side_planted.parquet",
        "ct_side": gold_dir / "round_features" / "round_features_ct_side.parquet",
        "round_state": gold_dir / "round_state" / "round_state_resolved.parquet",
        "feature_contract": gold_dir / "features" / "feature_contract" / "feature_contract.parquet",
        "quality_audit": gold_dir / "validation" / "map_feature_quality" / "map_feature_quality_audit.parquet",
        "feature_missingness": gold_dir / "validation" / "map_feature_quality" / "map_feature_missingness.parquet",
        "cross_map_sanity": gold_dir / "validation" / "map_feature_quality" / "mirage_inferno_feature_sanity.parquet",
        "repair_audit": gold_dir / "validation" / "feature_materialization_repair" / "feature_materialization_repair_final_audit.parquet",
        "capabilities": gold_dir / "validation" / "feature_materialization_repair" / "feature_materialization_capabilities.parquet",
        "multi_map_gold_audit": gold_dir / "validation" / "multi_map_gold" / "multi_map_gold_audit.parquet",
        "mirage_regression_summary": gold_dir / "validation" / "mirage_regression_gate" / "mirage_regression_summary.parquet",
    }
    return {name: read_optional(path) for name, path in paths.items()}


def read_optional(path: Path) -> pd.DataFrame:
    return read_optional_table(path)


def validate_preconditions(
    inputs: dict[str, pd.DataFrame],
    map_requests: list[MapRequest],
    *,
    target_team: str,
    registry_path: Path,
    settings: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    required_inputs = ["t_side_all", "t_side_planted", "ct_side", "round_state", "feature_contract"]
    for name in required_inputs:
        rows.append(precondition_row(f"{name}_available", not inputs[name].empty, f"{name} must be available."))
    for request in map_requests:
        scoped_t = scope_map_team(inputs["t_side_all"], request, target_team=target_team, registry_path=registry_path)
        scoped_ct = scope_map_team(inputs["ct_side"], request, target_team=target_team, registry_path=registry_path)
        rows.append(precondition_row(f"{request.map_id}_t_side_available", not scoped_t.empty, f"T-side rows must exist for {request.map_name}."))
        rows.append(precondition_row(f"{request.map_id}_round_state_available", not scoped_t.empty and not inputs["round_state"].empty, f"Round state must exist for {request.map_name}."))
        rows.append(precondition_row(f"{request.map_id}_ct_context_available", not scoped_ct.empty, f"CT-side context should exist for {request.map_name}.", severity="warning"))
        quality = latest_quality_for_map(inputs["quality_audit"], request.map_id, target_team)
        if quality is not None:
            ready = bool(quality.get("ready_for_multi_map_eda", False)) and str(quality.get("status", "")).casefold() == "passed"
            rows.append(precondition_row(f"{request.map_id}_quality_ready", ready, f"Quality gate must be passed and ready_for_multi_map_eda for {request.map_name}."))
        else:
            rows.append(precondition_row(f"{request.map_id}_quality_ready", reference_map_ready(inputs, request), f"Reference map must have regression/current Gold evidence for {request.map_name}."))
        repair = latest_repair_for_map(inputs["repair_audit"], request.map_id, target_team)
        if repair is not None:
            rows.append(precondition_row(f"{request.map_id}_stage_8_9_1_ready", bool(repair.get("ready_for_stage_8_10", False)), f"Stage 8.9.1 must be ready for {request.map_name}."))
    contract = inputs["feature_contract"]
    contract_ok = not contract.empty and "cross_map_comparable" in contract.columns and "cross_map_comparison_mode" in contract.columns
    rows.append(precondition_row("feature_contract_v2_available", contract_ok, "Feature Contract v2 comparison metadata must be present."))
    capabilities_ok = not inputs["capabilities"].empty
    rows.append(precondition_row("materialization_capabilities_available", capabilities_ok, "Feature materialization capability audit must be present."))
    return pd.DataFrame(rows)


def precondition_row(check_id: str, passed: bool, notes: str, *, severity: str = "critical") -> dict[str, object]:
    return {
        "check_id": check_id,
        "passed": bool(passed),
        "severity": severity,
        "status": "ok" if passed else ("warning" if severity == "warning" else "failed"),
        "notes": notes,
    }


def reference_map_ready(inputs: dict[str, pd.DataFrame], request: MapRequest) -> bool:
    summary = inputs["mirage_regression_summary"]
    if not summary.empty and "overall_status" in summary.columns:
        return bool(summary["overall_status"].astype(str).str.casefold().eq("passed").any())
    multi = inputs["multi_map_gold_audit"]
    return bool(not multi.empty and str(multi.iloc[-1].get("mirage_regression_passed", "")).casefold() == "true")


def latest_quality_for_map(frame: pd.DataFrame, map_id: str, target_team: str) -> pd.Series | None:
    if frame.empty:
        return None
    result = frame.copy()
    if "map_id" in result.columns:
        result = result[result["map_id"].astype(str).eq(map_id)]
    if "target_team" in result.columns:
        result = result[result["target_team"].astype(str).str.casefold().eq(target_team.casefold())]
    if result.empty:
        return None
    return result.iloc[-1]


def latest_repair_for_map(frame: pd.DataFrame, map_id: str, target_team: str) -> pd.Series | None:
    if frame.empty or "map_id" not in frame.columns:
        return None
    result = frame[frame["map_id"].astype(str).eq(map_id)].copy()
    if "target_team" in result.columns:
        result = result[result["target_team"].astype(str).str.casefold().eq(target_team.casefold())]
    if result.empty:
        return None
    return result.iloc[-1]


def scope_map_team(frame: pd.DataFrame, request: MapRequest, *, target_team: str, registry_path: Path) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    if "target_team" in result.columns:
        result = result[result["target_team"].astype(str).str.casefold().eq(target_team.casefold())].copy()
    if "map_name" in result.columns:
        result = result[map_id_series(result["map_name"], registry_path=registry_path).eq(request.map_id)].copy()
    return result.reset_index(drop=True)


def prepare_rounds(inputs: dict[str, pd.DataFrame], map_requests: list[MapRequest], *, target_team: str, registry_path: Path) -> pd.DataFrame:
    pieces = []
    state = inputs["round_state"]
    state_cols = [
        column
        for column in [
            "round_id",
            "team_t",
            "team_ct",
            "target_team_planted",
            "opponent_planted",
            "planting_team",
            "planting_side",
            "round_end_reason",
        ]
        if column in state.columns
    ]
    for request in map_requests:
        scoped = scope_map_team(inputs["t_side_all"], request, target_team=target_team, registry_path=registry_path)
        if scoped.empty:
            continue
        scoped = scoped.copy()
        scoped["map_id"] = request.map_id
        scoped["canonical_map_name"] = request.map_name
        if state_cols and "round_id" in scoped.columns:
            scoped = scoped.merge(state[state_cols].drop_duplicates("round_id"), on="round_id", how="left", suffixes=("", "_state"))
        if "opponent" in scoped.columns and "team_ct" in scoped.columns:
            unresolved = scoped["opponent"].isna() | scoped["opponent"].astype(str).str.casefold().isin({"", "unknown", "none", "nan"})
            scoped.loc[unresolved, "opponent"] = scoped.loc[unresolved, "team_ct"]
        scoped["opponent"] = scoped.get("opponent", pd.Series(index=scoped.index, dtype=object)).fillna("unknown")
        scoped["t_round_outcome"] = scoped.apply(classify_t_round_outcome, axis=1)
        scoped["target_team_win"] = scoped.apply(is_target_team_win, axis=1)
        scoped["round_exposure_seconds"] = compute_exposure_seconds(scoped)
        pieces.append(scoped)
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True)


def classify_t_round_outcome(row: pd.Series) -> str:
    label = str(row.get("target_site_model_label") or "").upper()
    confidence = str(row.get("label_confidence") or "").casefold()
    if label == "A" and confidence == "high":
        return "plant_A"
    if label == "B" and confidence == "high":
        return "plant_B"
    target_planted = bool(row.get("target_team_planted")) if pd.notna(row.get("target_team_planted")) else False
    if not target_planted:
        return "no_plant"
    return "unknown"


def is_target_team_win(row: pd.Series) -> bool | None:
    winner_team = str(row.get("winner_team") or "").strip().casefold()
    target_team = str(row.get("target_team") or "").strip().casefold()
    if winner_team and winner_team not in {"unknown", "none", "nan"}:
        return winner_team == target_team
    winner_side = str(row.get("winner_side") or "").upper()
    return winner_side == "T" if winner_side in {"T", "CT"} else None


def compute_exposure_seconds(frame: pd.DataFrame, tickrate: float = 64.0) -> pd.Series:
    if {"round_end_tick", "freeze_end_tick"}.issubset(frame.columns):
        return (pd.to_numeric(frame["round_end_tick"], errors="coerce") - pd.to_numeric(frame["freeze_end_tick"], errors="coerce")) / tickrate
    if "round_duration_seconds" in frame.columns:
        return pd.to_numeric(frame["round_duration_seconds"], errors="coerce")
    return pd.Series(np.nan, index=frame.index)


def build_cohorts(rounds: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "t_side_all": pd.Series(True, index=rounds.index),
        "t_side_planted": rounds["t_round_outcome"].isin(["plant_A", "plant_B"]),
        "t_side_no_valid_target_plant": rounds["t_round_outcome"].eq("no_plant"),
        "t_side_a_plant": rounds["t_round_outcome"].eq("plant_A"),
        "t_side_b_plant": rounds["t_round_outcome"].eq("plant_B"),
    }


def build_scope_inventory(rounds: pd.DataFrame, inputs: dict[str, pd.DataFrame], map_requests: list[MapRequest], *, target_team: str) -> pd.DataFrame:
    rows = []
    for request in map_requests:
        group = rounds[rounds["map_id"].eq(request.map_id)]
        planted = group[group["t_round_outcome"].isin(["plant_A", "plant_B"])]
        quality = latest_quality_for_map(inputs["quality_audit"], request.map_id, target_team)
        rows.append(
            {
                "map_id": request.map_id,
                "map_name": request.map_name,
                "target_team": target_team,
                "feature_eligible_demos": int(group.get("parse_id", pd.Series(dtype=object)).nunique(dropna=True)),
                "rounds": len(group),
                "t_rounds": len(group),
                "ct_rounds": count_ct_rounds(inputs["ct_side"], request.map_name, target_team),
                "planted_t_rounds": len(planted),
                "no_plant_t_rounds": int(group["t_round_outcome"].eq("no_plant").sum()),
                "a_plants": int(group["t_round_outcome"].eq("plant_A").sum()),
                "b_plants": int(group["t_round_outcome"].eq("plant_B").sum()),
                "unique_opponents": int(group.get("opponent", pd.Series(dtype=object)).nunique(dropna=True)),
                "first_series_date": first_available(group, ["match_date", "series_date"]),
                "last_series_date": last_available(group, ["match_date", "series_date"]),
                "quality_gate_status": str(quality.get("status")) if quality is not None else "reference_or_not_applicable",
                "modeling_readiness_level": str(quality.get("modeling_readiness_level")) if quality is not None else None,
                "status": "ok" if len(group) else "failed",
            }
        )
    return pd.DataFrame(rows)


def count_ct_rounds(ct_side: pd.DataFrame, map_name: str, target_team: str) -> int:
    if ct_side.empty or "map_name" not in ct_side.columns:
        return 0
    scoped = ct_side[ct_side["map_name"].astype(str).str.casefold().eq(map_name.casefold())]
    if "target_team" in scoped.columns:
        scoped = scoped[scoped["target_team"].astype(str).str.casefold().eq(target_team.casefold())]
    return len(scoped)


def first_available(frame: pd.DataFrame, columns: list[str]) -> object | None:
    for column in columns:
        if column in frame.columns and frame[column].notna().any():
            return frame[column].dropna().astype(str).sort_values().iloc[0]
    return None


def last_available(frame: pd.DataFrame, columns: list[str]) -> object | None:
    for column in columns:
        if column in frame.columns and frame[column].notna().any():
            return frame[column].dropna().astype(str).sort_values().iloc[-1]
    return None


def build_feature_eligibility(
    rounds: pd.DataFrame,
    inputs: dict[str, pd.DataFrame],
    map_requests: list[MapRequest],
    *,
    target_team: str,
    settings: dict[str, Any],
) -> pd.DataFrame:
    contract = inputs["feature_contract"].drop_duplicates("feature_name").copy() if "feature_name" in inputs["feature_contract"].columns else pd.DataFrame()
    contract_by_feature = contract.set_index("feature_name") if not contract.empty else pd.DataFrame()
    cross_sanity = inputs["cross_map_sanity"].drop_duplicates("feature_name") if "feature_name" in inputs["cross_map_sanity"].columns else pd.DataFrame()
    structural = set(cross_sanity.loc[cross_sanity.get("structural_mismatch", pd.Series(dtype=bool)).fillna(False), "feature_name"].astype(str)) if not cross_sanity.empty else set()
    structural_semantics = (
        set(cross_sanity.loc[cross_sanity.get("structural_mismatch", pd.Series(dtype=bool)).fillna(False), "region_semantic"].dropna().astype(str))
        if not cross_sanity.empty and "region_semantic" in cross_sanity.columns
        else set()
    )
    capabilities = inputs["capabilities"]
    unsupported_endpoint = endpoint_unresolved(capabilities)
    map_ids = [request.map_id for request in map_requests]
    features = sorted(column for column in rounds.columns if is_analytical_feature(column))
    rows = []
    for feature in features:
        meta = contract_by_feature.loc[feature] if not contract_by_feature.empty and feature in contract_by_feature.index else pd.Series(dtype=object)
        mode = str(meta.get("cross_map_comparison_mode") or "unknown")
        comparable = bool(meta.get("cross_map_comparable")) if "cross_map_comparable" in meta.index and pd.notna(meta.get("cross_map_comparable")) else False
        family = str(meta.get("feature_family") or infer_feature_family(feature))
        coordinate_dependency = str(meta.get("coordinate_dependency") or "unknown")
        semantic_id = normalized_semantic(meta.get("region_semantic"))
        materialization = {map_id: materialization_status(rounds[rounds["map_id"].eq(map_id)], feature) for map_id in map_ids}
        structural_flag = feature in structural or (semantic_id in structural_semantics)
        exclusion = exclusion_reason(
            feature,
            comparable=comparable,
            mode=mode,
            coordinate_dependency=coordinate_dependency,
            materialization=materialization,
            structural_flag=structural_flag,
            unsupported_endpoint=unsupported_endpoint,
            semantic_id=semantic_id,
        )
        direct = exclusion is None and mode == "direct"
        semantic = exclusion is None and mode == "semantic"
        ranked = (direct or semantic) and not (structural_flag and settings.get("structural_review", {}).get("exclude_from_ranked_findings", True))
        rows.append(
            {
                "feature_name": feature,
                "feature_family": family,
                "generation_scope": str(meta.get("generation_scope") or "unknown"),
                "coordinate_dependency": coordinate_dependency,
                "cross_map_comparable": comparable,
                "cross_map_comparison_mode": mode,
                "materialization_status_mirage": materialization.get("mirage", materialization.get(map_ids[0])),
                "materialization_status_inferno": materialization.get("inferno", materialization.get(map_ids[-1])),
                "semantic_id": semantic_id,
                "mirage_quality_status": feature_quality_status(inputs["feature_missingness"], feature, "mirage", target_team),
                "inferno_quality_status": feature_quality_status(inputs["feature_missingness"], feature, "inferno", target_team),
                "structural_review_flag": structural_flag,
                "eligible_for_direct_comparison": direct,
                "eligible_for_semantic_comparison": semantic,
                "eligible_for_ranked_findings": ranked,
                "exclusion_reason": exclusion,
            }
        )
    return pd.DataFrame(rows)


def is_analytical_feature(column: str) -> bool:
    if column in IDENTIFIER_COLUMNS or column in LABEL_AND_OUTCOME_COLUMNS:
        return False
    if column.startswith("is_"):
        return column in {"is_pistol_round", "is_early_round", "is_late_round"}
    if column.endswith("_id") or column.endswith("_path") or column.endswith("_notes"):
        return False
    return True


def materialization_status(frame: pd.DataFrame, feature: str) -> str:
    if feature not in frame.columns:
        return "missing_on_map"
    series = frame[feature]
    if series.isna().all():
        return "all_null"
    return "materialized"


def endpoint_unresolved(capabilities: pd.DataFrame) -> bool:
    if capabilities.empty:
        return True
    endpoint = capabilities[capabilities.get("capability_id", pd.Series(dtype=object)).astype(str).eq("utility_endpoint_regions")]
    if endpoint.empty:
        return True
    return not endpoint["capability_status"].astype(str).str.contains("supported_materialized", case=False, na=False).any()


def exclusion_reason(
    feature: str,
    *,
    comparable: bool,
    mode: str,
    coordinate_dependency: str,
    materialization: dict[str, str],
    structural_flag: bool,
    unsupported_endpoint: bool,
    semantic_id: str | None,
) -> str | None:
    if feature in IDENTIFIER_COLUMNS or feature in LABEL_AND_OUTCOME_COLUMNS:
        return "not_analytical_feature"
    if any(feature.startswith(prefix) for prefix in ENDPOINT_PREFIXES) and unsupported_endpoint:
        return "unresolved_endpoint"
    if not comparable:
        return "not_cross_map_comparable"
    if mode in {"normalized", "normalization_required"} or coordinate_dependency in {"raw_coordinate", "raw_coordinates", "coordinate"}:
        return "normalized_required"
    if mode == "map_specific":
        return "map_specific"
    if any(status != "materialized" for status in materialization.values()):
        return "missing_on_map"
    if mode == "semantic" and semantic_id in {None, "", "nan"}:
        return "semantic_unhealthy"
    if structural_flag:
        return "structural_review"
    if mode not in {"direct", "semantic"}:
        return "not_cross_map_comparable"
    return None


def feature_quality_status(missingness: pd.DataFrame, feature: str, map_id: str, target_team: str) -> str | None:
    if missingness.empty or "feature_name" not in missingness.columns:
        return None
    scoped = missingness[missingness["feature_name"].astype(str).eq(feature)].copy()
    if "map_id" in scoped.columns:
        scoped = scoped[scoped["map_id"].astype(str).eq(map_id)]
    if "target_team" in scoped.columns:
        scoped = scoped[scoped["target_team"].astype(str).str.casefold().eq(target_team.casefold())]
    if scoped.empty:
        return None
    return str(scoped.iloc[-1].get("status"))


def normalized_semantic(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text and text.casefold() != "nan" else None


def infer_feature_family(feature: str) -> str:
    if feature in UTILITY_INVENTORY_FEATURES:
        return "utility_inventory"
    if feature.startswith(UTILITY_USAGE_PREFIXES) or feature.startswith("first_"):
        return "utility_usage"
    if feature.startswith(("players_", "time_")):
        return "semantic_control"
    if feature.startswith(("team_spread", "avg_pairwise", "players_alive")):
        return "position_structure"
    if feature.startswith("bomb_"):
        return "bomb_context"
    if feature.startswith("round_") or feature.startswith("score_"):
        return "round_context"
    return "unknown"


def build_t_side_map_summary(rounds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for map_id, group in rounds.groupby("map_id", sort=True):
        planted = group[group["t_round_outcome"].isin(["plant_A", "plant_B"])]
        rows.append(
            {
                "map_id": map_id,
                "map_name": group["canonical_map_name"].iloc[0],
                "rounds": len(group),
                "demos": int(group["parse_id"].nunique(dropna=True)),
                "opponents": int(group["opponent"].nunique(dropna=True)),
                "plant_rate": safe_divide(len(planted), len(group)),
                "a_plant_rate": safe_divide(int(group["t_round_outcome"].eq("plant_A").sum()), len(group)),
                "b_plant_rate": safe_divide(int(group["t_round_outcome"].eq("plant_B").sum()), len(group)),
                "no_target_plant_rate": safe_divide(int(group["t_round_outcome"].eq("no_plant").sum()), len(group)),
                "median_round_duration": numeric_median(group.get("round_duration_seconds")),
                "win_rate": mean_bool(group.get("target_team_win")),
                "median_score_diff_before_round": numeric_median(group.get("score_diff_before_round")),
                **summary_stats_prefixed(group, UTILITY_INVENTORY_FEATURES),
            }
        )
    return pd.DataFrame(rows)


def build_plant_site_distribution(rounds: pd.DataFrame, *, settings: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for map_id, group in rounds.groupby("map_id", sort=True):
        planted = group[group["t_round_outcome"].isin(["plant_A", "plant_B"])]
        planted = planted.assign(
            plant_A_indicator=planted["t_round_outcome"].eq("plant_A").astype(float),
            plant_B_indicator=planted["t_round_outcome"].eq("plant_B").astype(float),
        )
        a = int(group["t_round_outcome"].eq("plant_A").sum())
        b = int(group["t_round_outcome"].eq("plant_B").sum())
        ci = cluster_bootstrap_difference(planted, "plant_A_indicator", pd.DataFrame(), "plant_A_indicator", statistic="mean", settings=settings, one_sample=True)
        demo = (
            planted
            .groupby("parse_id")
            .agg(per_demo_a_share=("plant_A_indicator", "mean"), per_demo_b_share=("plant_B_indicator", "mean"))
            .reset_index()
        )
        rows.append(
            {
                "map_id": map_id,
                "map_name": group["canonical_map_name"].iloc[0],
                "t_rounds": len(group),
                "planted_t_rounds": len(planted),
                "a_count": a,
                "b_count": b,
                "a_share": safe_divide(a, len(planted)),
                "b_share": safe_divide(b, len(planted)),
                "per_demo_a_share_median": numeric_median(demo["per_demo_a_share"]) if not demo.empty else None,
                "per_demo_b_share_median": numeric_median(demo["per_demo_b_share"]) if not demo.empty else None,
                "bootstrap_ci_low": ci[0],
                "bootstrap_ci_high": ci[1],
                "demo_level_variability": float(demo["per_demo_a_share"].std()) if len(demo) > 1 else 0.0,
                "notes": "A/B are compared only as target plant site choice, not as equivalent site geometry.",
            }
        )
    return pd.DataFrame(rows)


def build_feature_comparison(
    rounds: pd.DataFrame,
    cohorts: dict[str, pd.Series],
    features: list[str],
    eligibility: pd.DataFrame,
    *,
    settings: dict[str, Any],
    comparison_kind: str,
) -> pd.DataFrame:
    map_ids = sorted(rounds["map_id"].dropna().unique())
    if len(map_ids) < 2:
        return pd.DataFrame()
    left_map, right_map = map_ids[0], map_ids[1]
    rows = []
    meta = eligibility.drop_duplicates("feature_name").set_index("feature_name") if not eligibility.empty else pd.DataFrame()
    for feature in features:
        if feature not in rounds.columns:
            continue
        for cohort, mask in cohorts.items():
            scoped = rounds[mask].copy()
            left = scoped[scoped["map_id"].eq(left_map)]
            right = scoped[scoped["map_id"].eq(right_map)]
            row = compare_two_groups(left, right, feature, settings=settings)
            row.update(
                {
                    "feature_name": feature,
                    "feature_family": str(meta.loc[feature].get("feature_family")) if not meta.empty and feature in meta.index else infer_feature_family(feature),
                    "cohort": cohort,
                    f"{left_map}_n": row.pop("left_n"),
                    f"{right_map}_n": row.pop("right_n"),
                    f"{left_map}_demos": row.pop("left_demos"),
                    f"{right_map}_demos": row.pop("right_demos"),
                    f"{left_map}_mean": row.pop("left_mean"),
                    f"{right_map}_mean": row.pop("right_mean"),
                    f"{left_map}_median": row.pop("left_median"),
                    f"{right_map}_median": row.pop("right_median"),
                    f"{left_map}_p25": row.pop("left_p25"),
                    f"{left_map}_p75": row.pop("left_p75"),
                    f"{right_map}_p25": row.pop("right_p25"),
                    f"{right_map}_p75": row.pop("right_p75"),
                    "comparison_kind": comparison_kind,
                }
            )
            row["status"] = comparison_status(row, settings=settings)
            row["notes"] = comparison_notes(row)
            rows.append(row)
    return pd.DataFrame(rows)


def compare_two_groups(left: pd.DataFrame, right: pd.DataFrame, feature: str, *, settings: dict[str, Any]) -> dict[str, object]:
    left_values = pd.to_numeric(left.get(feature, pd.Series(dtype=float)), errors="coerce").dropna()
    right_values = pd.to_numeric(right.get(feature, pd.Series(dtype=float)), errors="coerce").dropna()
    left_mean = safe_mean(left_values)
    right_mean = safe_mean(right_values)
    median_diff = safe_subtract(numeric_median(right_values), numeric_median(left_values))
    mean_diff = safe_subtract(right_mean, left_mean)
    return {
        "left_n": int(left_values.size),
        "right_n": int(right_values.size),
        "left_demos": int(left.loc[left_values.index, "parse_id"].nunique(dropna=True)) if not left_values.empty and "parse_id" in left.columns else 0,
        "right_demos": int(right.loc[right_values.index, "parse_id"].nunique(dropna=True)) if not right_values.empty and "parse_id" in right.columns else 0,
        "left_mean": left_mean,
        "right_mean": right_mean,
        "left_median": numeric_median(left_values),
        "right_median": numeric_median(right_values),
        "left_p25": numeric_quantile(left_values, 0.25),
        "left_p75": numeric_quantile(left_values, 0.75),
        "right_p25": numeric_quantile(right_values, 0.25),
        "right_p75": numeric_quantile(right_values, 0.75),
        "median_difference": median_diff,
        "mean_difference": mean_diff,
        "relative_difference": safe_divide(mean_diff, abs(left_mean) if left_mean not in {None, 0} else None),
        "cliffs_delta": cliffs_delta(left_values, right_values),
        "bootstrap_ci_low": cluster_bootstrap_difference(left, feature, right, feature, statistic="median_difference", settings=settings)[0],
        "bootstrap_ci_high": cluster_bootstrap_difference(left, feature, right, feature, statistic="median_difference", settings=settings)[1],
        "demo_direction_agreement": demo_direction_agreement(left, right, feature),
        "effect_strength": effect_strength(cliffs_delta(left_values, right_values)),
    }


def comparison_status(row: dict[str, object], *, settings: dict[str, Any]) -> str:
    min_rounds = int(settings.get("cohorts", {}).get("min_rounds_for_reporting", 10))
    min_demos = int(settings.get("cohorts", {}).get("min_demos_for_reporting", 3))
    n_columns = [key for key in row if key.endswith("_n")]
    demo_columns = [key for key in row if key.endswith("_demos")]
    if any(int(row.get(column, 0) or 0) < min_rounds for column in n_columns):
        return "insufficient_rounds"
    if any(int(row.get(column, 0) or 0) < min_demos for column in demo_columns):
        return "insufficient_demos"
    return "ok"


def comparison_notes(row: dict[str, object]) -> str:
    if row.get("status") == "ok":
        return "Descriptive cross-map comparison; not causal."
    return "Comparison retained for inventory but excluded from strong findings."


def build_temporal_profile(rounds: pd.DataFrame, eligibility: pd.DataFrame, *, settings: dict[str, Any]) -> pd.DataFrame:
    rows = []
    temporal = eligibility[eligibility["feature_name"].map(lambda value: parse_window(str(value)) is not None)].copy() if not eligibility.empty else pd.DataFrame()
    threshold = float(settings.get("temporal", {}).get("minimum_late_window_exposure_share", 0.70))
    for _, meta in temporal.iterrows():
        feature = str(meta["feature_name"])
        parsed = parse_window(feature)
        if parsed is None or feature not in rounds.columns:
            continue
        base, start, end = parsed
        for map_id, group in rounds.groupby("map_id", sort=True):
            values = pd.to_numeric(group[feature], errors="coerce")
            exposed = group["round_exposure_seconds"] >= end
            exposure_share = safe_divide(int(exposed.sum()), len(group))
            rows.append(
                {
                    "map_id": map_id,
                    "map_name": group["canonical_map_name"].iloc[0],
                    "feature_base": base,
                    "feature_name": feature,
                    "semantic_id": meta.get("semantic_id"),
                    "window_type": window_type_from_feature(meta, start),
                    "window_start": start,
                    "window_end": end,
                    "rounds": len(group),
                    "exposed_rounds": int(exposed.sum()),
                    "exposure_share": exposure_share,
                    "mean": safe_mean(values),
                    "median": numeric_median(values),
                    "p25": numeric_quantile(values, 0.25),
                    "p75": numeric_quantile(values, 0.75),
                    "per_demo_mean": safe_mean(group.assign(_value=values).groupby("parse_id")["_value"].mean()) if "parse_id" in group.columns else None,
                    "exposure_status": "late_window_low_exposure" if exposure_share is not None and exposure_share < threshold and start >= int(settings.get("temporal", {}).get("late_window_start_seconds", 75)) else "ok",
                }
            )
    return pd.DataFrame(rows)


def parse_window(feature: str) -> tuple[str, int, int] | None:
    match = re.match(r"(.+)_([0-9]+)_([0-9]+)$", feature)
    if not match:
        return None
    return match.group(1), int(match.group(2)), int(match.group(3))


def window_type_from_feature(meta: pd.Series, start: int) -> str:
    window_type = str(meta.get("window_type") or "")
    if window_type in {"interval", "cumulative", "point"}:
        return window_type
    return "cumulative" if start == 0 else "interval"


def build_utility_timing_comparison(rounds: pd.DataFrame, cohorts: dict[str, pd.Series], eligibility: pd.DataFrame, *, settings: dict[str, Any]) -> pd.DataFrame:
    features = eligibility[
        eligibility["eligible_for_direct_comparison"] & eligibility["feature_name"].str.startswith(UTILITY_USAGE_PREFIXES)
    ]["feature_name"].tolist() if not eligibility.empty else []
    return build_feature_comparison(rounds, cohorts, features, eligibility, settings=settings, comparison_kind="utility_timing")


def summarize_feature_group(rounds: pd.DataFrame, cohorts: dict[str, pd.Series], features: list[str], category: str) -> pd.DataFrame:
    rows = []
    for feature in features:
        if feature not in rounds.columns:
            continue
        for cohort, mask in cohorts.items():
            scoped = rounds[mask]
            for map_id, group in scoped.groupby("map_id", sort=True):
                values = pd.to_numeric(group[feature], errors="coerce")
                rows.append(
                    {
                        "category": category,
                        "feature_name": feature,
                        "cohort": cohort,
                        "map_id": map_id,
                        "map_name": group["canonical_map_name"].iloc[0],
                        "rounds": len(group),
                        "demos": int(group["parse_id"].nunique(dropna=True)) if "parse_id" in group.columns else 0,
                        "mean": safe_mean(values),
                        "median": numeric_median(values),
                        "p25": numeric_quantile(values, 0.25),
                        "p75": numeric_quantile(values, 0.75),
                        "per_demo_mean_median": numeric_median(group.assign(_value=values).groupby("parse_id")["_value"].mean()) if "parse_id" in group.columns else None,
                        "status": "ok" if len(group) else "empty",
                    }
                )
    return pd.DataFrame(rows)


def structure_features(eligibility: pd.DataFrame) -> list[str]:
    if eligibility.empty:
        return []
    mask = eligibility["feature_name"].str.startswith(("team_spread", "avg_pairwise_distance", "players_alive"))
    return eligibility[mask & eligibility["eligible_for_direct_comparison"]]["feature_name"].tolist()


def build_semantic_control_profile(temporal: pd.DataFrame) -> pd.DataFrame:
    if temporal.empty:
        return pd.DataFrame()
    return temporal[temporal["semantic_id"].isin(SITE_SEMANTICS)].copy().reset_index(drop=True)


def build_within_map_site_comparison(rounds: pd.DataFrame, features: list[str], *, settings: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for map_id, group in rounds.groupby("map_id", sort=True):
        a = group[group["t_round_outcome"].eq("plant_A")]
        b = group[group["t_round_outcome"].eq("plant_B")]
        for feature in features:
            if feature not in group.columns:
                continue
            row = compare_two_groups(a, b, feature, settings=settings)
            rows.append(
                {
                    "map_id": map_id,
                    "map_name": group["canonical_map_name"].iloc[0],
                    "feature_name": feature,
                    "a_n": row["left_n"],
                    "b_n": row["right_n"],
                    "a_median": row["left_median"],
                    "b_median": row["right_median"],
                    "difference": row["median_difference"],
                    "cliffs_delta": row["cliffs_delta"],
                    "demo_support": row["demo_direction_agreement"],
                    "effect_strength": row["effect_strength"],
                    "status": comparison_status({"a_n": row["left_n"], "b_n": row["right_n"], "a_demos": row["left_demos"], "b_demos": row["right_demos"]}, settings=settings),
                    "notes": "Within-map A/B comparison; no cross-map site geometry equivalence implied.",
                }
            )
    return pd.DataFrame(rows)


def build_cross_map_site_pattern(within_site: pd.DataFrame) -> pd.DataFrame:
    if within_site.empty:
        return pd.DataFrame()
    map_ids = sorted(within_site["map_id"].dropna().unique())
    if len(map_ids) < 2:
        return pd.DataFrame()
    left = within_site[within_site["map_id"].eq(map_ids[0])].add_prefix("left_")
    right = within_site[within_site["map_id"].eq(map_ids[1])].add_prefix("right_")
    merged = left.merge(right, left_on="left_feature_name", right_on="right_feature_name", how="inner")
    rows = []
    for _, row in merged.iterrows():
        left_effect = safe_float(row.get("left_difference"))
        right_effect = safe_float(row.get("right_difference"))
        same_direction = left_effect is not None and right_effect is not None and np.sign(left_effect) == np.sign(right_effect)
        rows.append(
            {
                "feature_name": row.get("left_feature_name"),
                f"{map_ids[0]}_a_b_effect": left_effect,
                f"{map_ids[1]}_a_b_effect": right_effect,
                "same_direction": bool(same_direction),
                f"effect_strength_{map_ids[0]}": row.get("left_effect_strength"),
                f"effect_strength_{map_ids[1]}": row.get("right_effect_strength"),
                "demo_support": min(safe_float(row.get("left_demo_support")) or 0.0, safe_float(row.get("right_demo_support")) or 0.0),
                "status": "ok" if same_direction else "opposite_or_flat_direction",
                "notes": "Compares within-map A-vs-B effect directions, not site geometry.",
            }
        )
    return pd.DataFrame(rows)


def build_plant_vs_no_plant(rounds: pd.DataFrame, features: list[str], *, settings: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for map_id, group in rounds.groupby("map_id", sort=True):
        planted = group[group["t_round_outcome"].isin(["plant_A", "plant_B"])]
        no_plant = group[group["t_round_outcome"].eq("no_plant")]
        for feature in features:
            if feature not in group.columns:
                continue
            row = compare_two_groups(planted, no_plant, feature, settings=settings)
            rows.append(
                {
                    "map_id": map_id,
                    "map_name": group["canonical_map_name"].iloc[0],
                    "feature_name": feature,
                    "planted_n": row["left_n"],
                    "no_plant_n": row["right_n"],
                    "planted_median": row["left_median"],
                    "no_plant_median": row["right_median"],
                    "difference_no_plant_minus_planted": row["median_difference"],
                    "cliffs_delta": row["cliffs_delta"],
                    "demo_support": row["demo_direction_agreement"],
                    "status": comparison_status({"planted_n": row["left_n"], "no_plant_n": row["right_n"], "planted_demos": row["left_demos"], "no_plant_demos": row["right_demos"]}, settings=settings),
                    "notes": "Descriptive association; no-plant is not treated as a homogeneous failure class.",
                }
            )
    return pd.DataFrame(rows)


def build_round_outcome_summary(rounds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for map_id, group in rounds.groupby("map_id", sort=True):
        for outcome in ["t_side_all", "plant_A", "plant_B", "no_plant"]:
            scoped = group if outcome == "t_side_all" else group[group["t_round_outcome"].eq(outcome)]
            rows.append(
                {
                    "map_id": map_id,
                    "map_name": group["canonical_map_name"].iloc[0],
                    "outcome_group": outcome,
                    "rounds": len(scoped),
                    "win_rate": mean_bool(scoped.get("target_team_win")),
                    "median_round_duration": numeric_median(scoped.get("round_duration_seconds")),
                    "notes": "Outcome context is separated from tactical feature ranking.",
                }
            )
    return pd.DataFrame(rows)


def build_demo_stability(rounds: pd.DataFrame, direct: pd.DataFrame, *, settings: dict[str, Any]) -> pd.DataFrame:
    if direct.empty:
        return pd.DataFrame()
    top_features = direct.sort_values("cliffs_delta", key=lambda values: values.abs(), ascending=False)["feature_name"].drop_duplicates().head(50)
    rows = []
    for feature in top_features:
        if feature not in rounds.columns:
            continue
        map_means = rounds.groupby("map_id")[feature].mean(numeric_only=True)
        if map_means.empty:
            continue
        for (map_id, parse_id), group in rounds.groupby(["map_id", "parse_id"], dropna=False):
            demo_metric = safe_mean(pd.to_numeric(group[feature], errors="coerce"))
            other_maps = map_means.drop(index=map_id, errors="ignore")
            other_mean = safe_mean(other_maps)
            direction = direction_label(safe_subtract(demo_metric, other_mean))
            global_direction = direction_label(safe_subtract(map_means.get(map_id), other_mean))
            rows.append(
                {
                    "map_id": map_id,
                    "feature_name": feature,
                    "cohort": "t_side_all",
                    "parse_id": parse_id,
                    "demo_metric": demo_metric,
                    "map_level_metric": map_means.get(map_id),
                    "direction_vs_other_map": direction,
                    "supports_global_direction": direction == global_direction and direction != "flat",
                    "outlier_demo": bool(abs((demo_metric or 0) - (map_means.get(map_id) or 0)) > 2 * (pd.to_numeric(rounds[rounds["map_id"].eq(map_id)][feature], errors="coerce").std() or 0)),
                    "status": "ok",
                }
            )
    return pd.DataFrame(rows)


def build_finding_candidates(
    direct: pd.DataFrame,
    semantic: pd.DataFrame,
    within_site: pd.DataFrame,
    cross_site: pd.DataFrame,
    plant_vs_no_plant: pd.DataFrame,
    eligibility: pd.DataFrame,
    *,
    settings: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates = []
    excluded = []
    candidates.extend(candidates_from_feature_comparison(direct, "direct_feature", settings=settings))
    candidates.extend(candidates_from_feature_comparison(semantic, "semantic_feature", settings=settings))
    candidates.extend(candidates_from_within_site(within_site, settings=settings))
    candidates.extend(candidates_from_cross_site(cross_site, settings=settings))
    candidates.extend(candidates_from_plant_vs_no_plant(plant_vs_no_plant, settings=settings))
    for _, row in eligibility[eligibility["exclusion_reason"].notna()].iterrows():
        excluded.append(
            {
                "feature_name": row["feature_name"],
                "candidate_claim": "Feature excluded before tactical interpretation.",
                "reason": row["exclusion_reason"],
            }
        )
    candidate_frame = pd.DataFrame(candidates)
    if not candidate_frame.empty:
        candidate_frame["finding_id"] = [f"mm_eda_{index+1:04d}" for index in range(len(candidate_frame))]
    return candidate_frame, pd.DataFrame(excluded)


def candidates_from_feature_comparison(frame: pd.DataFrame, category: str, *, settings: dict[str, Any]) -> list[dict[str, object]]:
    if frame.empty:
        return []
    rows = []
    for _, row in frame.iterrows():
        effect = abs(safe_float(row.get("cliffs_delta")) or 0.0)
        demo_agreement = safe_float(row.get("demo_direction_agreement")) or 0.0
        eligible = row.get("status") == "ok" and effect >= float(settings.get("findings", {}).get("minimum_effect_strength", 0.147))
        rows.append(
            {
                "category": category,
                "cohort": row.get("cohort"),
                "feature_name": row.get("feature_name"),
                "semantic_id": None,
                "comparison": "cross_map",
                "direction": direction_label(row.get("median_difference")),
                "effect_size": row.get("cliffs_delta"),
                "effect_strength": row.get("effect_strength"),
                "bootstrap_ci_low": row.get("bootstrap_ci_low"),
                "bootstrap_ci_high": row.get("bootstrap_ci_high"),
                "demo_direction_agreement": demo_agreement,
                "mirage_n": row.get("mirage_n"),
                "inferno_n": row.get("inferno_n"),
                "mirage_demos": row.get("mirage_demos"),
                "inferno_demos": row.get("inferno_demos"),
                "structural_review_flag": False,
                "late_window_exposure_flag": False,
                "opponent_dependency_flag": False,
                "evidence_quality": evidence_quality(effect, demo_agreement, eligible),
                "eligible_for_ranking": bool(eligible and demo_agreement >= float(settings.get("findings", {}).get("minimum_demo_direction_agreement", 0.60))),
                "exclusion_reason": None if eligible else row.get("status"),
                "finding_text_draft": finding_text(row),
            }
        )
    return rows


def candidates_from_within_site(frame: pd.DataFrame, *, settings: dict[str, Any]) -> list[dict[str, object]]:
    if frame.empty:
        return []
    rows = []
    for _, row in frame.iterrows():
        effect = abs(safe_float(row.get("cliffs_delta")) or 0.0)
        eligible = row.get("status") == "ok" and effect >= float(settings.get("findings", {}).get("minimum_effect_strength", 0.147))
        rows.append(
            {
                "category": "site_pattern",
                "cohort": "t_side_planted",
                "feature_name": row.get("feature_name"),
                "semantic_id": None,
                "comparison": f"{row.get('map_id')}_A_vs_B",
                "direction": direction_label(row.get("difference")),
                "effect_size": row.get("cliffs_delta"),
                "effect_strength": row.get("effect_strength"),
                "bootstrap_ci_low": None,
                "bootstrap_ci_high": None,
                "demo_direction_agreement": row.get("demo_support"),
                "mirage_n": None,
                "inferno_n": None,
                "mirage_demos": None,
                "inferno_demos": None,
                "structural_review_flag": False,
                "late_window_exposure_flag": False,
                "opponent_dependency_flag": False,
                "evidence_quality": evidence_quality(effect, safe_float(row.get("demo_support")) or 0.0, eligible),
                "eligible_for_ranking": bool(eligible),
                "exclusion_reason": None if eligible else row.get("status"),
                "finding_text_draft": f"{row.get('map_name')} A-vs-B planted rounds differ descriptively on {row.get('feature_name')}.",
            }
        )
    return rows


def candidates_from_cross_site(frame: pd.DataFrame, *, settings: dict[str, Any]) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return [
        {
            "category": "site_pattern",
            "cohort": "t_side_planted",
            "feature_name": row.get("feature_name"),
            "semantic_id": None,
            "comparison": "cross_map_A_B_direction",
            "direction": "same_direction" if row.get("same_direction") else "different_direction",
            "effect_size": None,
            "effect_strength": "descriptive",
            "bootstrap_ci_low": None,
            "bootstrap_ci_high": None,
            "demo_direction_agreement": row.get("demo_support"),
            "mirage_n": None,
            "inferno_n": None,
            "mirage_demos": None,
            "inferno_demos": None,
            "structural_review_flag": False,
            "late_window_exposure_flag": False,
            "opponent_dependency_flag": False,
            "evidence_quality": "moderate_descriptive" if row.get("same_direction") else "tentative",
            "eligible_for_ranking": bool(row.get("same_direction")),
            "exclusion_reason": None if row.get("same_direction") else "opposite_or_flat_direction",
            "finding_text_draft": f"A-vs-B direction for {row.get('feature_name')} is {'similar' if row.get('same_direction') else 'not similar'} across maps.",
        }
        for _, row in frame.iterrows()
    ]


def candidates_from_plant_vs_no_plant(frame: pd.DataFrame, *, settings: dict[str, Any]) -> list[dict[str, object]]:
    if frame.empty:
        return []
    rows = []
    for _, row in frame.iterrows():
        effect = abs(safe_float(row.get("cliffs_delta")) or 0.0)
        eligible = row.get("status") == "ok" and effect >= float(settings.get("findings", {}).get("minimum_effect_strength", 0.147))
        rows.append(
            {
                "category": "plant_progression",
                "cohort": "planted_vs_no_plant",
                "feature_name": row.get("feature_name"),
                "semantic_id": None,
                "comparison": f"{row.get('map_id')}_planted_vs_no_plant",
                "direction": direction_label(row.get("difference_no_plant_minus_planted")),
                "effect_size": row.get("cliffs_delta"),
                "effect_strength": effect_strength(row.get("cliffs_delta")),
                "bootstrap_ci_low": None,
                "bootstrap_ci_high": None,
                "demo_direction_agreement": row.get("demo_support"),
                "mirage_n": None,
                "inferno_n": None,
                "mirage_demos": None,
                "inferno_demos": None,
                "structural_review_flag": False,
                "late_window_exposure_flag": False,
                "opponent_dependency_flag": False,
                "evidence_quality": evidence_quality(effect, safe_float(row.get("demo_support")) or 0.0, eligible),
                "eligible_for_ranking": bool(eligible),
                "exclusion_reason": None if eligible else row.get("status"),
                "finding_text_draft": f"{row.get('map_name')} planted and no-target-plant rounds differ descriptively on {row.get('feature_name')}.",
            }
        )
    return rows


def rank_findings(findings: pd.DataFrame, *, settings: dict[str, Any]) -> pd.DataFrame:
    if findings.empty:
        return findings.copy()
    eligible = findings[findings["eligible_for_ranking"].fillna(False)].copy()
    if eligible.empty:
        return eligible
    strength_rank = {"large": 0, "moderate": 1, "small": 2, "negligible": 3, "descriptive": 2}
    quality_rank = {"high_descriptive": 0, "moderate_descriptive": 1, "tentative": 2, "insufficient": 3}
    eligible["_strength_rank"] = eligible["effect_strength"].map(strength_rank).fillna(4)
    eligible["_quality_rank"] = eligible["evidence_quality"].map(quality_rank).fillna(4)
    eligible["_demo"] = pd.to_numeric(eligible["demo_direction_agreement"], errors="coerce").fillna(0)
    eligible["_effect"] = pd.to_numeric(eligible["effect_size"], errors="coerce").abs().fillna(0)
    eligible = eligible.sort_values(["_quality_rank", "_strength_rank", "_demo", "_effect"], ascending=[True, True, False, False]).drop(columns=["_strength_rank", "_quality_rank", "_demo", "_effect"])
    eligible["rank"] = range(1, len(eligible) + 1)
    max_ranked = int(settings.get("findings", {}).get("max_ranked_findings", 25))
    return eligible.head(max_ranked).reset_index(drop=True)


def build_opponent_sensitivity(ranked: pd.DataFrame, rounds: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty:
        return pd.DataFrame(columns=["finding_id", "dominant_opponent_share", "single_opponent_dependency", "status"])
    counts = rounds.groupby("opponent").size().sort_values(ascending=False)
    dominant = safe_divide(int(counts.iloc[0]), int(counts.sum())) if not counts.empty else 0.0
    return pd.DataFrame(
        [
            {
                "finding_id": finding_id,
                "dominant_opponent_share": dominant,
                "single_opponent_dependency": bool(dominant and dominant >= 0.50),
                "status": "warning" if dominant and dominant >= 0.50 else "ok",
            }
            for finding_id in ranked["finding_id"]
        ]
    )


def capture_core_fingerprints(project_root: Path, gold_dir: Path) -> pd.DataFrame:
    rows = []
    for name, relative in CORE_GOLD_PATHS.items():
        path = gold_dir / relative
        frame = read_optional(path)
        rows.append(
            {
                "artifact_name": name,
                "path": str(path),
                "exists": path.exists(),
                "row_count": len(frame),
                "schema_hash": schema_hash(frame) if not frame.empty else "",
                "content_hash": content_hash(frame) if not frame.empty else hashlib.sha256(b"empty").hexdigest(),
            }
        )
    for relative in [Path("configs/maps/map_registry.yaml"), Path("configs/maps/mirage.yaml"), Path("configs/maps/inferno.yaml"), Path("configs/features/feature_contract.yaml")]:
        path = project_root / relative
        rows.append(
            {
                "artifact_name": str(relative),
                "path": str(path),
                "exists": path.exists(),
                "row_count": None,
                "schema_hash": "",
                "content_hash": file_hash(path),
            }
        )
    return pd.DataFrame(rows)


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_read_only_audit(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    merged = before.merge(after, on="artifact_name", suffixes=("_before", "_after"), how="outer")
    merged["content_unchanged"] = merged["content_hash_before"].eq(merged["content_hash_after"])
    merged["schema_unchanged"] = merged["schema_hash_before"].fillna("").eq(merged["schema_hash_after"].fillna(""))
    merged["status"] = merged.apply(lambda row: "ok" if row["content_unchanged"] and row["schema_unchanged"] else "failed", axis=1)
    merged["notes"] = merged["status"].map(lambda status: "Core artifact unchanged." if status == "ok" else "Core artifact changed during read-only EDA.")
    return merged


def build_final_audit(
    frames: dict[str, pd.DataFrame],
    preconditions: pd.DataFrame,
    *,
    target_team: str,
    map_requests: list[MapRequest],
    settings: dict[str, Any],
) -> pd.DataFrame:
    eligibility = frames["multi_map_feature_eligibility"]
    inventory = frames["multi_map_eda_scope_inventory"]
    read_only = frames["multi_map_eda_read_only_audit"]
    findings = frames["multi_map_finding_candidates"]
    ranked = frames["multi_map_ranked_findings"]
    excluded = frames["multi_map_excluded_findings"]
    critical_failures = int(preconditions["status"].eq("failed").sum()) + int(read_only["status"].eq("failed").sum())
    warnings = int(preconditions["status"].eq("warning").sum())
    ready = bool(critical_failures == 0 and not eligibility.empty and read_only["status"].eq("ok").all())
    return pd.DataFrame(
        [
            {
                "audit_id": "multi_map_tactical_eda_v1",
                "target_team": target_team,
                "maps_requested": ",".join(request.requested_name for request in map_requests),
                "maps_analyzed": ",".join(inventory["map_id"].astype(str)) if not inventory.empty else "",
                "demos_by_map": json.dumps(dict(zip(inventory["map_id"], inventory["feature_eligible_demos"], strict=False))) if not inventory.empty else "{}",
                "rounds_by_map": json.dumps(dict(zip(inventory["map_id"], inventory["rounds"], strict=False))) if not inventory.empty else "{}",
                "t_rounds_by_map": json.dumps(dict(zip(inventory["map_id"], inventory["t_rounds"], strict=False))) if not inventory.empty else "{}",
                "features_evaluated": len(eligibility),
                "direct_comparable_features": int(eligibility["eligible_for_direct_comparison"].sum()) if not eligibility.empty else 0,
                "semantic_comparable_features": int(eligibility["eligible_for_semantic_comparison"].sum()) if not eligibility.empty else 0,
                "excluded_normalized_features": count_exclusion(eligibility, "normalized_required"),
                "excluded_map_specific_features": count_exclusion(eligibility, "map_specific"),
                "excluded_unsupported_features": count_exclusion(eligibility, "unsupported_materialization") + count_exclusion(eligibility, "unresolved_endpoint"),
                "excluded_structural_review_features": count_exclusion(eligibility, "structural_review"),
                "plant_cohorts_valid": bool(not frames["plant_site_distribution"].empty),
                "demo_aware_bootstrap_completed": bool(settings.get("bootstrap", {}).get("enabled", True)),
                "late_window_exposure_checks": len(frames["multi_map_temporal_profile"]),
                "finding_candidates": len(findings),
                "ranked_findings": len(ranked),
                "tentative_findings": int(findings["evidence_quality"].eq("tentative").sum()) if not findings.empty else 0,
                "excluded_findings": len(excluded),
                "critical_failures": critical_failures,
                "warnings": warnings,
                "core_gold_unchanged": bool(read_only["status"].eq("ok").all()) if not read_only.empty else False,
                "modeling_readiness_level": carried_modeling_readiness(inventory),
                "ready_for_stage_8_11": ready,
                "status": "passed" if ready else "failed",
                "created_at": now_utc(),
            }
        ]
    )


def carried_modeling_readiness(inventory: pd.DataFrame) -> str | None:
    if inventory.empty or "modeling_readiness_level" not in inventory.columns:
        return None
    values = [str(value) for value in inventory["modeling_readiness_level"].dropna().unique() if str(value) not in {"", "None", "nan"}]
    return ",".join(sorted(values)) if values else None


def count_exclusion(eligibility: pd.DataFrame, reason: str) -> int:
    return int(eligibility["exclusion_reason"].astype(str).eq(reason).sum()) if not eligibility.empty else 0


def safe_mean(values: pd.Series | np.ndarray | list[object] | None) -> float | None:
    if values is None:
        return None
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype(float)
    return float(series.mean()) if not series.empty else None


def numeric_median(values: pd.Series | np.ndarray | list[object] | None) -> float | None:
    if values is None:
        return None
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype(float)
    return float(series.median()) if not series.empty else None


def numeric_quantile(values: pd.Series | np.ndarray | list[object] | None, q: float) -> float | None:
    if values is None:
        return None
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype(float)
    return float(series.quantile(q)) if not series.empty else None


def safe_divide(numerator: object, denominator: object) -> float | None:
    return shared_safe_divide(numerator, denominator)


def safe_subtract(right: object, left: object) -> float | None:
    right_float = safe_float(right)
    left_float = safe_float(left)
    if right_float is None or left_float is None:
        return None
    return right_float - left_float


def safe_float(value: object) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def mean_bool(values: pd.Series | None) -> float | None:
    if values is None:
        return None
    series = values.dropna()
    return float(series.map(bool).mean()) if not series.empty else None


def cliffs_delta(left: pd.Series | np.ndarray | list[object], right: pd.Series | np.ndarray | list[object]) -> float | None:
    left_values = pd.to_numeric(pd.Series(left), errors="coerce").dropna().to_numpy()
    right_values = pd.to_numeric(pd.Series(right), errors="coerce").dropna().to_numpy()
    if left_values.size == 0 or right_values.size == 0:
        return None
    greater = 0
    lower = 0
    for value in right_values:
        greater += int((value > left_values).sum())
        lower += int((value < left_values).sum())
    return float((greater - lower) / (left_values.size * right_values.size))


def cluster_bootstrap_difference(
    left: pd.DataFrame,
    left_feature: str,
    right: pd.DataFrame,
    right_feature: str,
    *,
    statistic: str,
    settings: dict[str, Any],
    one_sample: bool = False,
) -> tuple[float | None, float | None]:
    bootstrap = settings.get("bootstrap", {})
    if not bootstrap.get("enabled", True):
        return None, None
    resamples = int(bootstrap.get("resamples", 2000))
    seed = int(bootstrap.get("random_seed", 810))
    confidence = float(bootstrap.get("confidence_level", 0.95))
    rng = np.random.default_rng(seed)
    agg_func = "mean" if one_sample or statistic == "mean_difference" else "median"
    left_demo = demo_metric_values(left, left_feature, agg_func=agg_func)
    if one_sample:
        if left_demo.size == 0:
            return None, None
        sampled = rng.choice(left_demo, size=(resamples, left_demo.size), replace=True)
        diffs = sampled.mean(axis=1)
        alpha = 1 - confidence
        return float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))
    right_demo = demo_metric_values(right, right_feature, agg_func=agg_func)
    if left_demo.size == 0 or right_demo.size == 0:
        return None, None
    left_sampled = rng.choice(left_demo, size=(resamples, left_demo.size), replace=True)
    right_sampled = rng.choice(right_demo, size=(resamples, right_demo.size), replace=True)
    diffs = right_sampled.mean(axis=1) - left_sampled.mean(axis=1)
    alpha = 1 - confidence
    return float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))


def demo_metric_values(frame: pd.DataFrame, feature: str, *, agg_func: str) -> np.ndarray:
    if frame.empty or feature not in frame.columns:
        return np.array([])
    values = frame[["parse_id", feature]].copy() if "parse_id" in frame.columns else frame[[feature]].assign(parse_id="all")
    values[feature] = pd.to_numeric(values[feature], errors="coerce")
    values = values.dropna(subset=[feature])
    if values.empty:
        return np.array([])
    grouped = values.groupby("parse_id")[feature].mean() if agg_func == "mean" else values.groupby("parse_id")[feature].median()
    return grouped.dropna().to_numpy(dtype=float)


def legacy_round_cluster_bootstrap(
    left: pd.DataFrame,
    left_feature: str,
    right: pd.DataFrame,
    right_feature: str,
    *,
    statistic: str,
    settings: dict[str, Any],
    one_sample: bool = False,
) -> tuple[float | None, float | None]:
    bootstrap = settings.get("bootstrap", {})
    if not bootstrap.get("enabled", True):
        return None, None
    resamples = int(bootstrap.get("resamples", 2000))
    seed = int(bootstrap.get("random_seed", 810))
    confidence = float(bootstrap.get("confidence_level", 0.95))
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(resamples):
        if one_sample:
            sample = resample_by_cluster(left, rng)
            values = pd.to_numeric(sample[left_feature], errors="coerce").dropna()
            if not values.empty:
                diffs.append(float(values.mean()))
        else:
            left_sample = resample_by_cluster(left, rng)
            right_sample = resample_by_cluster(right, rng)
            left_values = pd.to_numeric(left_sample.get(left_feature, pd.Series(dtype=float)), errors="coerce").dropna()
            right_values = pd.to_numeric(right_sample.get(right_feature, pd.Series(dtype=float)), errors="coerce").dropna()
            if left_values.empty or right_values.empty:
                continue
            if statistic == "mean_difference":
                diffs.append(float(right_values.mean() - left_values.mean()))
            else:
                diffs.append(float(right_values.median() - left_values.median()))
    if not diffs:
        return None, None
    alpha = 1 - confidence
    return float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))


def resample_by_cluster(frame: pd.DataFrame, rng: np.random.Generator, cluster_column: str = "parse_id") -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if cluster_column not in frame.columns:
        return frame.sample(n=len(frame), replace=True, random_state=int(rng.integers(0, 1_000_000)))
    clusters = frame[cluster_column].dropna().unique()
    if len(clusters) == 0:
        return frame.iloc[0:0].copy()
    sampled = rng.choice(clusters, size=len(clusters), replace=True)
    return pd.concat([frame[frame[cluster_column].eq(cluster)] for cluster in sampled], ignore_index=True)


def demo_direction_agreement(left: pd.DataFrame, right: pd.DataFrame, feature: str) -> float | None:
    if left.empty or right.empty or "parse_id" not in left.columns or "parse_id" not in right.columns:
        return None
    left_values = left[["parse_id", feature]].copy()
    right_values = right[["parse_id", feature]].copy()
    left_values[feature] = pd.to_numeric(left_values[feature], errors="coerce")
    right_values[feature] = pd.to_numeric(right_values[feature], errors="coerce")
    left_demo = left_values.dropna(subset=[feature]).groupby("parse_id")[feature].mean()
    right_demo = right_values.dropna(subset=[feature]).groupby("parse_id")[feature].mean()
    left_mean = safe_mean(left_demo)
    right_mean = safe_mean(right_demo)
    if left_mean is None or right_mean is None or left_mean == right_mean:
        return 0.0
    if right_mean > left_mean:
        supports = int((right_demo > left_mean).sum()) + int((left_demo < right_mean).sum())
    else:
        supports = int((right_demo < left_mean).sum()) + int((left_demo > right_mean).sum())
    return safe_divide(supports, len(left_demo) + len(right_demo))


def effect_strength(delta: object) -> str:
    value = abs(safe_float(delta) or 0.0)
    if value >= 0.474:
        return "large"
    if value >= 0.330:
        return "moderate"
    if value >= 0.147:
        return "small"
    return "negligible"


def evidence_quality(effect: float, demo_agreement: float, eligible: bool) -> str:
    if not eligible:
        return "insufficient"
    if effect >= 0.474 and demo_agreement >= 0.75:
        return "high_descriptive"
    if effect >= 0.330 and demo_agreement >= 0.60:
        return "moderate_descriptive"
    return "tentative"


def direction_label(value: object) -> str:
    number = safe_float(value)
    if number is None or abs(number) < 1e-9:
        return "flat"
    return "higher" if number > 0 else "lower"


def finding_text(row: pd.Series | dict[str, object]) -> str:
    feature = row.get("feature_name")
    direction = direction_label(row.get("median_difference"))
    return f"{feature} is descriptively {direction} on the second map in this comparison; interpretation is non-causal."


def summary_stats_prefixed(frame: pd.DataFrame, features: list[str]) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for feature in features:
        if feature in frame.columns:
            series = pd.to_numeric(frame[feature], errors="coerce")
            values[f"{feature}_mean"] = safe_mean(series)
            values[f"{feature}_median"] = numeric_median(series)
    return values


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    sanitized = {name: sanitize_for_parquet(frames.get(name, pd.DataFrame())) for name in OUTPUT_NAMES}
    return write_dataframe_outputs(sanitized, output_dir, force=force)


def sanitize_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].map(
                lambda value: None
                if value is None or (not isinstance(value, (list, dict, tuple, set)) and pd.isna(value))
                else json.dumps(value, sort_keys=True)
                if isinstance(value, dict)
                else "|".join(map(str, value))
                if isinstance(value, (list, tuple, set))
                else value
            )
    return result


def build_report(frames: dict[str, pd.DataFrame], *, target_team: str, map_requests: list[MapRequest]) -> str:
    audit = frames["multi_map_tactical_eda_audit"].iloc[0]
    sections = [
        "# Vitality Multi-Map Tactical EDA -- Mirage vs Inferno",
        "",
        "## Purpose",
        f"Compare {target_team} T-side tactical behavior across {', '.join(request.map_name for request in map_requests)} using only technically eligible cross-map features.",
        "",
        "## Data Readiness",
        markdown_table(frames["multi_map_tactical_eda_audit"], list(frames["multi_map_tactical_eda_audit"].columns)),
        "",
        "## Scope",
        markdown_table(frames["multi_map_eda_scope_inventory"], list(frames["multi_map_eda_scope_inventory"].columns)),
        "",
        "## Feature Eligibility",
        markdown_table(frames["multi_map_feature_eligibility"], ["feature_name", "feature_family", "cross_map_comparison_mode", "eligible_for_ranked_findings", "exclusion_reason"], top_n=30),
        "",
        "## Analysis Method",
        "The analysis uses descriptive effect sizes, cluster bootstrap by demo/parse_id, demo-direction agreement, and explicit caveats. It does not use p-value-only ranking or causal language.",
        "",
        "## T-Side Overview",
        markdown_table(frames["t_side_map_summary"], list(frames["t_side_map_summary"].columns)),
        "",
        "## Plant Site Distribution",
        markdown_table(frames["plant_site_distribution"], list(frames["plant_site_distribution"].columns)),
        "",
        "## Utility Inventory",
        markdown_table(frames["utility_inventory_comparison"], ["feature_name", "cohort", "map_id", "rounds", "mean", "median"], top_n=30),
        "",
        "## Utility Timing",
        markdown_table(frames["utility_timing_comparison"], ["feature_name", "cohort", "median_difference", "cliffs_delta", "effect_strength", "status"], top_n=30),
        "",
        "## Team Structure",
        markdown_table(frames["team_structure_comparison"], ["feature_name", "cohort", "map_id", "mean", "median", "status"], top_n=30),
        "",
        "## Semantic Map Control",
        markdown_table(frames["semantic_feature_comparison"], ["feature_name", "cohort", "median_difference", "cliffs_delta", "effect_strength", "status"], top_n=30),
        "",
        "## A Pressure",
        semantic_section(frames["semantic_control_profile"], "a_pressure"),
        "",
        "## B Pressure",
        semantic_section(frames["semantic_control_profile"], "b_pressure"),
        "",
        "## A vs B Within Mirage",
        markdown_table(frames["within_map_site_comparison"][frames["within_map_site_comparison"].get("map_id", pd.Series(dtype=object)).eq("mirage")], ["feature_name", "a_n", "b_n", "difference", "cliffs_delta", "effect_strength", "status"], top_n=20),
        "",
        "## A vs B Within Inferno",
        markdown_table(frames["within_map_site_comparison"][frames["within_map_site_comparison"].get("map_id", pd.Series(dtype=object)).eq("inferno")], ["feature_name", "a_n", "b_n", "difference", "cliffs_delta", "effect_strength", "status"], top_n=20),
        "",
        "## Cross-Map Site Patterns",
        markdown_table(frames["cross_map_site_pattern_comparison"], list(frames["cross_map_site_pattern_comparison"].columns), top_n=20),
        "",
        "## Planted vs No-Plant",
        markdown_table(frames["plant_vs_no_plant_comparison"], ["map_id", "feature_name", "planted_n", "no_plant_n", "difference_no_plant_minus_planted", "status"], top_n=30),
        "",
        "## Outcome Context",
        markdown_table(frames["round_outcome_summary"], list(frames["round_outcome_summary"].columns)),
        "",
        "## Demo-Level Stability",
        markdown_table(frames["multi_map_demo_stability"], ["map_id", "feature_name", "parse_id", "demo_metric", "supports_global_direction", "outlier_demo"], top_n=30),
        "",
        "## Ranked Tactical Findings",
        markdown_table(frames["multi_map_ranked_findings"], ["rank", "finding_id", "category", "feature_name", "effect_strength", "evidence_quality", "finding_text_draft"], top_n=25),
        "",
        "## Tentative Findings",
        markdown_table(frames["multi_map_finding_candidates"][frames["multi_map_finding_candidates"].get("evidence_quality", pd.Series(dtype=object)).eq("tentative")], ["finding_id", "category", "feature_name", "evidence_quality", "finding_text_draft"], top_n=25),
        "",
        "## Excluded Features / Unsupported Comparisons",
        markdown_table(frames["multi_map_excluded_findings"], list(frames["multi_map_excluded_findings"].columns), top_n=30),
        "",
        "## Structural Caveats",
        "Mid-control structural review flags are not promoted to strong ranked findings. Utility endpoint destination features are excluded when endpoint resolution is unresolved.",
        "",
        "## Sample Limitations",
        f"Modeling readiness is carried forward as `{audit.get('modeling_readiness_level')}`; Stage 8.10 does not change modeling readiness levels.",
        "",
        "## Modeling Readiness",
        "This stage prepares descriptive EDA only. It does not train models or generate predictions.",
        "",
        "## Next Stage",
        "If `ready_for_stage_8_11` is true, the next stage can be an Inferno A/B exploratory baseline. Stage 8.10 does not start that work automatically.",
        "",
    ]
    return "\n".join(sections)


def semantic_section(profile: pd.DataFrame, semantic_id: str) -> str:
    if profile.empty:
        return "_No rows._"
    scoped = profile[profile["semantic_id"].astype(str).eq(semantic_id)]
    return markdown_table(scoped, ["map_id", "feature_name", "window_type", "window_start", "window_end", "mean", "median", "exposure_share", "exposure_status"], top_n=20)


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    return report_markdown_table(frame, columns, top_n=top_n)


def write_markdown_report(report: str, path: Path, *, force: bool) -> Path:
    if path.exists() and not force:
        return path
    ensure_dir(path.parent)
    path.write_text(report, encoding="utf-8")
    return path


def write_notebook(path: Path, *, force: bool) -> Path:
    if path.exists() and not force:
        return path
    ensure_dir(path.parent)
    notebook = {
        "cells": [
            md("# Stage 8.10 -- Vitality Multi-Map Tactical EDA"),
            code("from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\nBASE = Path('../data/gold/analysis/multi_map_tactical_eda')\ndef load(name):\n    return pd.read_parquet(BASE / f'{name}.parquet')"),
            md("## Scope"),
            code("scope = load('multi_map_eda_scope_inventory')\ndisplay(scope)\nscope.plot.bar(x='map_id', y=['t_rounds','planted_t_rounds','no_plant_t_rounds'], figsize=(8,4))\nplt.tight_layout()"),
            md("## Quality Status"),
            code("display(load('multi_map_tactical_eda_audit'))\ndisplay(load('multi_map_eda_read_only_audit'))"),
            md("## Plant Distribution"),
            code("plant = load('plant_site_distribution')\ndisplay(plant)\nplant.plot.bar(x='map_id', y=['a_share','b_share'], figsize=(7,4))\nplt.tight_layout()"),
            md("## Utility Inventory"),
            code("utility_inv = load('utility_inventory_comparison')\ndisplay(utility_inv.head(30))"),
            md("## Utility Timing"),
            code("utility = load('utility_timing_comparison')\ndisplay(utility.sort_values('cliffs_delta', key=lambda s: s.abs(), ascending=False).head(25))"),
            md("## Semantic Progression"),
            code("semantic = load('semantic_control_profile')\ndisplay(semantic.head(30))"),
            md("## Team Structure"),
            code("structure = load('team_structure_comparison')\ndisplay(structure.head(30))"),
            md("## A/B Comparisons"),
            code("within = load('within_map_site_comparison')\ndisplay(within.sort_values('cliffs_delta', key=lambda s: s.abs(), ascending=False).head(30))"),
            md("## Planted vs No-Plant"),
            code("pnp = load('plant_vs_no_plant_comparison')\ndisplay(pnp.sort_values('cliffs_delta', key=lambda s: s.abs(), ascending=False).head(30))"),
            md("## Demo Stability"),
            code("stability = load('multi_map_demo_stability')\ndisplay(stability.head(30))"),
            md("## Ranked Findings"),
            code("ranked = load('multi_map_ranked_findings')\ndisplay(ranked)"),
            md("## Caveats"),
            code("display(load('multi_map_excluded_findings').head(50))"),
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.12"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    return path


def md(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict[str, object]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def print_summary(outputs: dict[str, Path], summary: dict[str, Any]) -> None:
    print("Multi-map tactical EDA summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run read-only multi-map tactical EDA.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--map", action="append", dest="maps", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--eda-config", type=Path, default=Path("configs/analysis/multi_map_tactical_eda.yaml"))
    parser.add_argument("--map-registry", type=Path, default=Path("configs/maps/map_registry.yaml"))
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_multi_map_tactical_eda(
        args.config,
        target_team=args.target_team,
        maps=args.maps,
        force=args.force,
        dry_run=args.dry_run,
        eda_config=args.eda_config,
        map_registry_path=args.map_registry,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
