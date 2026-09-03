from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from src.analysis.multi_map_tactical_eda import (
    OUTPUT_NAMES as STAGE_8_10_OUTPUT_NAMES,
    MapRequest,
    build_read_only_audit,
    capture_core_fingerprints,
    file_hash,
    parse_window,
    resolve_map_requests,
    sanitize_for_parquet,
)
from src.config.schemas import load_project_config
from src.utils.io import read_optional_table, read_table_pair, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.reports import markdown_table as report_markdown_table
from src.utils.reports import now_utc, safe_divide as shared_safe_divide


OUTPUT_NAMES = [
    "raw_finding_evidence",
    "finding_direction_consistency",
    "tactical_finding_groups",
    "finding_opponent_sensitivity",
    "finding_demo_sensitivity",
    "hardened_cross_map_site_patterns",
    "finding_exclusion_audit",
    "consolidated_tactical_findings",
    "tactical_finding_supporting_evidence",
    "tactical_finding_contradictions",
    "hardened_tactical_finding_ranking",
    "modeling_context_findings",
    "tactical_finding_hardening_read_only_audit",
    "tactical_finding_hardening_audit",
    "tactical_finding_sensitivity_revalidation",
]

REQUIRED_STAGE_8_10_INPUTS = [
    "multi_map_finding_candidates",
    "multi_map_ranked_findings",
    "multi_map_excluded_findings",
    "multi_map_temporal_profile",
    "multi_map_feature_eligibility",
    "multi_map_demo_stability",
    "multi_map_eda_scope_inventory",
    "direct_feature_comparison",
    "semantic_feature_comparison",
    "within_map_site_comparison",
    "cross_map_site_pattern_comparison",
    "plant_vs_no_plant_comparison",
    "plant_site_distribution",
    "multi_map_tactical_eda_audit",
]

EVENT_TIMING_FEATURES = {"first_smoke_time", "first_molotov_time", "first_utility_time"}
ENDPOINT_PREFIXES = ("smokes_to_", "molotovs_to_")
CONTEXT_ONLY_FEATURES = {
    "freeze_end_tick",
    "round_start_tick",
    "round_end_tick",
    "half",
    "is_early_round",
    "is_late_round",
    "is_pistol_round",
}


def run_tactical_finding_hardening(
    *,
    config_path: Path,
    target_team: str,
    map_names: list[str],
    force: bool,
    dry_run: bool = False,
    hardening_config: Path | None = None,
    map_registry: Path | None = None,
) -> tuple[dict[str, Path], dict[str, pd.DataFrame], dict[str, Any]]:
    config_path = config_path.resolve()
    project_root = config_path.parent.parent
    load_project_config(config_path)
    settings = load_hardening_settings(hardening_config or project_root / "configs" / "analysis" / "tactical_finding_hardening.yaml")
    registry_path = map_registry or project_root / "configs" / "maps" / "map_registry.yaml"
    map_requests = resolve_map_requests(map_names, registry_path=registry_path)
    if len(map_requests) < 2:
        raise ValueError("Stage 8.10.1 requires at least two --map values.")

    gold_dir = project_root / "data" / "gold"
    stage_8_10_dir = gold_dir / "analysis" / "multi_map_tactical_eda"
    output_dir = gold_dir / "analysis" / "tactical_finding_hardening"
    previous_sensitivity = capture_sensitivity_revalidation_snapshot(output_dir)

    core_before = capture_core_fingerprints(project_root, gold_dir)
    stage_before = capture_stage_output_fingerprints(stage_8_10_dir)
    inputs = load_stage_8_10_inputs(stage_8_10_dir)
    preconditions = validate_preconditions(project_root, inputs, map_requests, target_team)
    rounds = load_round_features_for_sensitivity(gold_dir, map_requests, target_team)

    raw = build_raw_finding_evidence(inputs, map_requests, settings)
    raw = apply_temporal_exposure(raw, inputs["multi_map_temporal_profile"], map_requests, settings, rounds=rounds)
    raw = apply_interpretation_metadata(raw, settings)

    site_patterns = build_hardened_cross_map_site_patterns(inputs["cross_map_site_pattern_comparison"], settings)
    raw = append_site_choice_distribution(raw, inputs["plant_site_distribution"], map_requests)

    opponent = build_finding_opponent_sensitivity(raw, rounds, settings)
    demo = build_finding_demo_sensitivity(raw, rounds, map_requests)
    raw = apply_sensitivity_flags(raw, opponent, demo)
    raw = apply_hardened_quality(raw, settings)

    direction = build_direction_consistency(raw, settings)
    groups, support = build_tactical_finding_groups(raw, direction, settings)
    contradictions = build_tactical_finding_contradictions(direction)
    consolidated = build_consolidated_tactical_findings(groups, raw, opponent, demo, contradictions, settings)
    ranking = build_hardened_ranking(consolidated, settings)
    modeling_context = build_modeling_context_findings(consolidated)
    exclusion = build_finding_exclusion_audit(inputs["multi_map_feature_eligibility"])

    core_after = capture_core_fingerprints(project_root, gold_dir)
    stage_after = capture_stage_output_fingerprints(stage_8_10_dir)
    read_only = build_combined_read_only_audit(core_before, core_after, stage_before, stage_after)

    frames = {
        "raw_finding_evidence": raw,
        "finding_direction_consistency": direction,
        "tactical_finding_groups": groups,
        "finding_opponent_sensitivity": opponent,
        "finding_demo_sensitivity": demo,
        "hardened_cross_map_site_patterns": site_patterns,
        "finding_exclusion_audit": exclusion,
        "consolidated_tactical_findings": consolidated,
        "tactical_finding_supporting_evidence": support,
        "tactical_finding_contradictions": contradictions,
        "hardened_tactical_finding_ranking": ranking,
        "modeling_context_findings": modeling_context,
        "tactical_finding_hardening_read_only_audit": read_only,
    }
    frames["tactical_finding_hardening_audit"] = build_final_audit(
        frames,
        inputs,
        preconditions,
        target_team=target_team,
        map_requests=map_requests,
        source_raw_candidates=len(inputs["multi_map_finding_candidates"]),
    )
    frames["tactical_finding_sensitivity_revalidation"] = build_sensitivity_revalidation(previous_sensitivity, frames)

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs = write_outputs(frames, output_dir, force=force)
        report_path = project_root / "docs" / "vitality_multi_map_tactical_findings.md"
        notebook_path = project_root / "notebooks" / "26_tactical_finding_hardening.ipynb"
        if force or not report_path.exists():
            report_path.write_text(build_report(frames, target_team=target_team, map_requests=map_requests), encoding="utf-8")
        if force or not notebook_path.exists():
            notebook_path.write_text(build_notebook(), encoding="utf-8")
        outputs["report"] = report_path
        outputs["notebook"] = notebook_path

    summary = {
        "status": frames["tactical_finding_hardening_audit"].iloc[0]["status"],
        "raw_candidates": int(frames["tactical_finding_hardening_audit"].iloc[0]["raw_candidates"]),
        "finding_concepts": int(frames["tactical_finding_hardening_audit"].iloc[0]["finding_concepts"]),
        "consolidated_findings": int(frames["tactical_finding_hardening_audit"].iloc[0]["consolidated_findings"]),
        "hardened_ranked_findings": int(frames["tactical_finding_hardening_audit"].iloc[0]["hardened_ranked_findings"]),
        "ready_for_stage_8_11": bool(frames["tactical_finding_hardening_audit"].iloc[0]["ready_for_stage_8_11"]),
    }
    return outputs, frames, summary


def load_hardening_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Hardening config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_stage_8_10_inputs(base_dir: Path) -> dict[str, pd.DataFrame]:
    return {name: read_named_table(base_dir, name) for name in REQUIRED_STAGE_8_10_INPUTS}


def read_named_table(base_dir: Path, name: str) -> pd.DataFrame:
    return read_table_pair(base_dir / name)


def validate_preconditions(
    project_root: Path,
    inputs: dict[str, pd.DataFrame],
    map_requests: list[MapRequest],
    target_team: str,
) -> pd.DataFrame:
    rows = []
    audit = inputs["multi_map_tactical_eda_audit"]
    rows.append(
        precondition_row(
            "stage_8_10_audit",
            not audit.empty and audit.iloc[0].get("status") == "passed" and bool(audit.iloc[0].get("ready_for_stage_8_11")),
            "Stage 8.10 audit passed and ready flag is true.",
        )
    )
    for name in REQUIRED_STAGE_8_10_INPUTS:
        rows.append(precondition_row(f"stage_8_10_input_{name}", not inputs[name].empty, f"{name} is available."))

    quality = read_optional(project_root / "data" / "gold" / "validation" / "map_feature_quality" / "map_feature_quality_audit.parquet")
    scoped_quality = quality[quality.get("target_team", pd.Series(dtype=object)).astype(str).str.casefold().eq(target_team.casefold())] if not quality.empty else pd.DataFrame()
    rows.append(
        precondition_row(
            "stage_8_9_quality_gate",
            not scoped_quality.empty and scoped_quality["status"].astype(str).eq("passed").any(),
            "Stage 8.9 quality gate passed for the target team.",
        )
    )

    repair = read_optional(project_root / "data" / "gold" / "validation" / "feature_materialization_repair" / "feature_materialization_repair_final_audit.parquet")
    rows.append(
        precondition_row(
            "stage_8_9_1_repair",
            not repair.empty and repair["status"].astype(str).eq("passed").any(),
            "Stage 8.9.1 repair gate passed.",
        )
    )

    analyzed = set(str(value).casefold() for value in audit.iloc[0].get("maps_analyzed", "").split(",")) if not audit.empty else set()
    requested = {request.map_id for request in map_requests}
    rows.append(precondition_row("requested_maps_present", requested.issubset(analyzed), "Requested maps exist in Stage 8.10 outputs."))
    return pd.DataFrame(rows)


def precondition_row(check_name: str, passed: bool, notes: str) -> dict[str, object]:
    return {"check_name": check_name, "status": "ok" if passed else "failed", "notes": notes}


def build_raw_finding_evidence(
    inputs: dict[str, pd.DataFrame],
    map_requests: list[MapRequest],
    settings: dict[str, Any],
) -> pd.DataFrame:
    candidates = inputs["multi_map_finding_candidates"].copy()
    source = build_source_lookup(inputs)
    reference = map_requests[0]
    comparison = map_requests[1]
    rows = []
    for _, row in candidates.iterrows():
        source_row = lookup_source_row(row, source)
        evidence = normalize_candidate(row, source_row, reference, comparison)
        evidence["window_type"], evidence["window_start"], evidence["window_end"] = parse_feature_window(evidence["feature_name"])
        evidence["window_label"] = window_label(evidence["window_start"], evidence["window_end"])
        evidence["finding_concept_id"] = derive_finding_concept(evidence, settings)
        evidence["window_band"] = classify_window_band(evidence.get("window_start"), evidence.get("window_end"), settings)
        evidence["comparison_type"] = str(row.get("comparison") or "unknown")
        evidence["direction_subject"], evidence["direction_reference"], evidence["direction_comparison"] = direction_fields(evidence)
        evidence["finding_text"] = explicit_finding_text(evidence)
        evidence["source_stage"] = "stage_8_10"
        rows.append(evidence)
    return pd.DataFrame(rows)


def build_source_lookup(inputs: dict[str, pd.DataFrame]) -> dict[tuple[str, str, str], pd.Series]:
    lookup: dict[tuple[str, str, str], pd.Series] = {}
    for category, name in [("direct_feature", "direct_feature_comparison"), ("semantic_feature", "semantic_feature_comparison")]:
        for _, row in inputs[name].iterrows():
            lookup[(category, str(row.get("feature_name")), str(row.get("cohort")))] = row
    for _, row in inputs["within_map_site_comparison"].iterrows():
        lookup[(f"{row.get('map_id')}_A_vs_B", str(row.get("feature_name")), "t_side_planted")] = row
    for _, row in inputs["plant_vs_no_plant_comparison"].iterrows():
        lookup[(f"{row.get('map_id')}_planted_vs_no_plant", str(row.get("feature_name")), "planted_vs_no_plant")] = row
    return lookup


def lookup_source_row(row: pd.Series, lookup: dict[tuple[str, str, str], pd.Series]) -> pd.Series:
    category = str(row.get("category"))
    comparison = str(row.get("comparison"))
    feature = str(row.get("feature_name"))
    cohort = str(row.get("cohort"))
    if category in {"direct_feature", "semantic_feature"}:
        return lookup.get((category, feature, cohort), pd.Series(dtype=object))
    return lookup.get((comparison, feature, cohort), pd.Series(dtype=object))


def normalize_candidate(row: pd.Series, source_row: pd.Series, reference: MapRequest, comparison: MapRequest) -> dict[str, object]:
    feature = str(row.get("feature_name"))
    comparison_type = str(row.get("comparison") or "unknown")
    category = str(row.get("category") or "unknown")
    base = {
        "finding_id": row.get("finding_id"),
        "category": category,
        "cohort": row.get("cohort"),
        "feature_name": feature,
        "feature_family": source_row.get("feature_family") if not source_row.empty else None,
        "semantic_id": normalized_value(row.get("semantic_id")),
        "reference_map_id": reference.map_id,
        "reference_map_name": reference.map_name,
        "comparison_map_id": comparison.map_id,
        "comparison_map_name": comparison.map_name,
        "effect_strength": row.get("effect_strength"),
        "bootstrap_ci_low": row.get("bootstrap_ci_low"),
        "bootstrap_ci_high": row.get("bootstrap_ci_high"),
        "demo_direction_agreement": safe_float(row.get("demo_direction_agreement")),
        "structural_review_flag": bool(row.get("structural_review_flag", False)),
        "late_window_exposure_flag": bool(row.get("late_window_exposure_flag", False)),
        "opponent_dependency_flag": bool(row.get("opponent_dependency_flag", False)),
        "eligible_before_hardening": bool(row.get("eligible_for_ranking", False)),
        "evidence_quality_before": row.get("evidence_quality"),
        "status": "candidate" if bool(row.get("eligible_for_ranking", False)) else "excluded_before_hardening",
        "exclusion_reason": normalized_value(row.get("exclusion_reason")),
    }
    if comparison_type == "cross_map":
        reference_value = metric_value(source_row, reference.map_id, "median")
        comparison_value = metric_value(source_row, comparison.map_id, "median")
        reference_mean = metric_value(source_row, reference.map_id, "mean")
        comparison_mean = metric_value(source_row, comparison.map_id, "mean")
        diff = safe_subtract(prefer_number(comparison_value, comparison_mean), prefer_number(reference_value, reference_mean))
        signed_effect = signed_by_difference(row.get("effect_size"), diff)
        base.update(
            {
                "reference_value": prefer_number(reference_value, reference_mean),
                "comparison_value": prefer_number(comparison_value, comparison_mean),
                "reference_n": numeric_column(source_row, reference.map_id, "n", row),
                "comparison_n": numeric_column(source_row, comparison.map_id, "n", row),
                "reference_demos": numeric_column(source_row, reference.map_id, "demos", row),
                "comparison_demos": numeric_column(source_row, comparison.map_id, "demos", row),
                "effect_size": signed_effect,
                "direction": classify_difference(diff),
            }
        )
        return base

    if comparison_type.endswith("_A_vs_B"):
        map_id = comparison_type.removesuffix("_A_vs_B")
        base.update(
            {
                "reference_map_id": map_id,
                "reference_map_name": str(source_row.get("map_name") or map_id.title()),
                "comparison_map_id": map_id,
                "comparison_map_name": str(source_row.get("map_name") or map_id.title()),
                "reference_value": safe_float(source_row.get("a_median")),
                "comparison_value": safe_float(source_row.get("b_median")),
                "reference_n": safe_float(source_row.get("a_n")),
                "comparison_n": safe_float(source_row.get("b_n")),
                "reference_demos": None,
                "comparison_demos": None,
                "effect_size": signed_by_difference(row.get("effect_size"), source_row.get("difference")),
                "direction": classify_difference(source_row.get("difference")),
            }
        )
        return base

    if comparison_type.endswith("_planted_vs_no_plant"):
        map_id = comparison_type.removesuffix("_planted_vs_no_plant")
        base.update(
            {
                "reference_map_id": map_id,
                "reference_map_name": str(source_row.get("map_name") or map_id.title()),
                "comparison_map_id": map_id,
                "comparison_map_name": str(source_row.get("map_name") or map_id.title()),
                "reference_value": safe_float(source_row.get("planted_median")),
                "comparison_value": safe_float(source_row.get("no_plant_median")),
                "reference_n": safe_float(source_row.get("planted_n")),
                "comparison_n": safe_float(source_row.get("no_plant_n")),
                "reference_demos": None,
                "comparison_demos": None,
                "effect_size": signed_by_difference(row.get("effect_size"), source_row.get("difference_no_plant_minus_planted")),
                "direction": classify_difference(source_row.get("difference_no_plant_minus_planted")),
            }
        )
        return base

    base.update(
        {
            "reference_value": None,
            "comparison_value": None,
            "reference_n": row.get(f"{reference.map_id}_n"),
            "comparison_n": row.get(f"{comparison.map_id}_n"),
            "reference_demos": row.get(f"{reference.map_id}_demos"),
            "comparison_demos": row.get(f"{comparison.map_id}_demos"),
            "effect_size": safe_float(row.get("effect_size")),
            "direction": str(row.get("direction") or "unknown"),
        }
    )
    return base


def append_site_choice_distribution(raw: pd.DataFrame, plant_distribution: pd.DataFrame, map_requests: list[MapRequest]) -> pd.DataFrame:
    if len(map_requests) < 2 or plant_distribution.empty:
        return raw
    reference = plant_distribution[plant_distribution["map_id"].astype(str).eq(map_requests[0].map_id)]
    comparison = plant_distribution[plant_distribution["map_id"].astype(str).eq(map_requests[1].map_id)]
    if reference.empty or comparison.empty:
        return raw
    ref = reference.iloc[0]
    comp = comparison.iloc[0]
    b_diff = safe_subtract(comp.get("b_share"), ref.get("b_share"))
    row = {
        "finding_id": "mm_eda_site_choice_distribution",
        "category": "site_choice",
        "cohort": "t_side_planted",
        "feature_name": "plant_site_distribution_b_share",
        "feature_family": "site_choice",
        "semantic_id": None,
        "comparison_type": "cross_map_site_choice_distribution",
        "reference_map_id": map_requests[0].map_id,
        "reference_map_name": map_requests[0].map_name,
        "comparison_map_id": map_requests[1].map_id,
        "comparison_map_name": map_requests[1].map_name,
        "effect_size": b_diff,
        "effect_strength": strength_from_abs(b_diff),
        "direction": classify_difference(b_diff),
        "reference_value": safe_float(ref.get("b_share")),
        "comparison_value": safe_float(comp.get("b_share")),
        "bootstrap_ci_low": comp.get("bootstrap_ci_low"),
        "bootstrap_ci_high": comp.get("bootstrap_ci_high"),
        "demo_direction_agreement": None,
        "reference_n": safe_float(ref.get("planted_t_rounds")),
        "comparison_n": safe_float(comp.get("planted_t_rounds")),
        "reference_demos": None,
        "comparison_demos": None,
        "window_type": None,
        "window_start": None,
        "window_end": None,
        "structural_review_flag": False,
        "late_window_exposure_flag": False,
        "opponent_dependency_flag": False,
        "eligible_before_hardening": True,
        "evidence_quality_before": "moderate_descriptive",
        "status": "candidate",
        "exclusion_reason": None,
        "finding_concept_id": "site_choice.distribution",
        "window_band": "non_temporal",
        "direction_subject": "B plant share",
        "direction_reference": map_requests[0].map_name,
        "direction_comparison": map_requests[1].map_name,
        "finding_text": site_choice_text(map_requests[0].map_name, map_requests[1].map_name, ref, comp),
        "source_stage": "stage_8_10_derived",
    }
    return pd.concat([raw, pd.DataFrame([row])], ignore_index=True)


def apply_temporal_exposure(
    raw: pd.DataFrame,
    temporal: pd.DataFrame,
    map_requests: list[MapRequest],
    settings: dict[str, Any],
    rounds: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if raw.empty:
        return raw
    result = raw.copy()
    threshold = float(settings.get("temporal", {}).get("minimum_exposure_share", 0.70))
    late_start = int(settings.get("temporal", {}).get("late_window_start_seconds", 75))
    lookup = {
        (str(row.get("feature_name")), str(row.get("map_id"))): safe_float(row.get("exposure_share"))
        for _, row in temporal.iterrows()
    }
    refs = []
    comps = []
    low_refs = []
    low_comps = []
    flags = []
    statuses = []
    available = []
    all_effects = []
    fully_effects = []
    all_directions = []
    fully_directions = []
    same_directions = []
    fully_ref_rows = []
    fully_comp_rows = []
    fully_ref_shares = []
    fully_comp_shares = []
    for _, row in result.iterrows():
        end = safe_float(row.get("window_end"))
        is_late = end is not None and end >= late_start
        ref_share = lookup.get((str(row.get("feature_name")), map_requests[0].map_id))
        comp_share = lookup.get((str(row.get("feature_name")), map_requests[1].map_id))
        low_ref = bool(is_late and (ref_share is None or ref_share < threshold))
        low_comp = bool(is_late and (comp_share is None or comp_share < threshold))
        flag = bool(is_late and (low_ref or low_comp))
        refs.append(ref_share)
        comps.append(comp_share)
        low_refs.append(low_ref)
        low_comps.append(low_comp)
        flags.append(flag)
        sensitivity = temporal_exposure_sensitivity(row, rounds, map_requests, threshold) if rounds is not None else {}
        status = str(sensitivity.get("exposure_sensitivity_status") or "")
        if not is_late and not status:
            status = "not_applicable"
        elif flag:
            status = "insufficient_exposure"
        elif ref_share is None or comp_share is None:
            status = "insufficient_exposure"
        elif not status:
            status = "stable"
        statuses.append(status)
        available.append(bool(sensitivity.get("fully_exposed_analysis_available", False)))
        all_effects.append(sensitivity.get("all_round_effect", row.get("effect_size")))
        fully_effects.append(sensitivity.get("fully_exposed_effect"))
        all_directions.append(sensitivity.get("all_round_direction"))
        fully_directions.append(sensitivity.get("fully_exposed_direction"))
        same_directions.append(sensitivity.get("same_direction_after_exposure_filter"))
        fully_ref_rows.append(sensitivity.get("fully_exposed_rows_reference"))
        fully_comp_rows.append(sensitivity.get("fully_exposed_rows_comparison"))
        fully_ref_shares.append(sensitivity.get("fully_exposed_share_reference"))
        fully_comp_shares.append(sensitivity.get("fully_exposed_share_comparison"))
    result["reference_exposure_share"] = refs
    result["comparison_exposure_share"] = comps
    result["minimum_exposure_share"] = threshold
    result["low_exposure_reference"] = low_refs
    result["low_exposure_comparison"] = low_comps
    result["late_window_exposure_flag"] = flags
    result["fully_exposed_analysis_available"] = available
    result["all_round_effect"] = all_effects
    result["fully_exposed_effect"] = fully_effects
    result["all_round_direction"] = all_directions
    result["fully_exposed_direction"] = fully_directions
    result["same_direction_after_exposure_filter"] = same_directions
    result["fully_exposed_rows_reference"] = fully_ref_rows
    result["fully_exposed_rows_comparison"] = fully_comp_rows
    result["fully_exposed_share_reference"] = fully_ref_shares
    result["fully_exposed_share_comparison"] = fully_comp_shares
    result["exposure_sensitivity_status"] = statuses
    return result


def temporal_exposure_sensitivity(
    finding: pd.Series,
    rounds: pd.DataFrame | None,
    map_requests: list[MapRequest],
    minimum_exposure_share: float,
) -> dict[str, object]:
    feature = str(finding.get("feature_name"))
    end = safe_float(finding.get("window_end"))
    if rounds is None or rounds.empty or end is None or feature not in rounds.columns:
        return exposure_result(
            available=False,
            all_effect=safe_float(finding.get("effect_size")),
            all_direction=classify_direction(finding.get("direction")),
            status="not_applicable",
        )
    full = evaluate_finding_effect(rounds, finding, map_requests)
    if str(full["status"]) == "unsupported_comparison_type":
        return exposure_result(
            available=False,
            all_effect=None,
            all_direction="flat",
            status="not_applicable",
        )
    scoped = full["rows"]
    if scoped.empty:
        return exposure_result(
            available=False,
            all_effect=safe_float(finding.get("effect_size")),
            all_direction=classify_direction(finding.get("direction")),
            status="insufficient_exposure",
            reference_rows=0,
            comparison_rows=0,
            reference_share=0.0,
            comparison_share=0.0,
        )
    duration_col = "round_exposure_seconds" if "round_exposure_seconds" in scoped.columns else "round_duration_seconds"
    if duration_col not in scoped.columns:
        return exposure_result(
            available=False,
            all_effect=full["effect"],
            all_direction=full["direction"],
            status="not_applicable",
        )
    durations = pd.to_numeric(scoped[duration_col], errors="coerce")
    fully = scoped[durations >= float(end)].copy()
    all_effect = safe_float(full["effect"])
    full_direction = str(full["direction"])
    if fully.empty:
        return exposure_result(
            available=False,
            all_effect=all_effect,
            all_direction=full_direction,
            status="insufficient_exposure",
            reference_rows=0,
            comparison_rows=0,
            reference_share=0.0,
            comparison_share=0.0,
        )
    fully_effect = evaluate_finding_effect(fully, finding, map_requests)
    ref_rows = int(fully_effect["reference_rows"])
    comp_rows = int(fully_effect["comparison_rows"])
    ref_share = safe_divide(ref_rows, full["reference_rows"])
    comp_share = safe_divide(comp_rows, full["comparison_rows"])
    enough_rows = ref_rows >= 3 and comp_rows >= 3
    enough_share = (ref_share is not None and ref_share >= minimum_exposure_share) and (comp_share is not None and comp_share >= minimum_exposure_share)
    if not enough_rows or not enough_share:
        return exposure_result(
            available=bool(enough_rows),
            all_effect=all_effect,
            all_direction=full_direction,
            fully_effect=fully_effect["effect"] if enough_rows else None,
            fully_direction=fully_effect["direction"] if enough_rows else None,
            status="insufficient_exposure",
            reference_rows=ref_rows,
            comparison_rows=comp_rows,
            reference_share=ref_share,
            comparison_share=comp_share,
        )
    fully_direction = str(fully_effect["direction"])
    same = bool(full_direction != "flat" and fully_direction == full_direction)
    if not same:
        status = "reversed"
    elif abs(safe_float(fully_effect["effect"]) or 0.0) < abs(all_effect or 0.0) * 0.5:
        status = "weakened"
    else:
        status = "stable"
    return exposure_result(
        available=True,
        all_effect=all_effect,
        all_direction=full_direction,
        fully_effect=fully_effect["effect"],
        fully_direction=fully_direction,
        same=same,
        status=status,
        reference_rows=ref_rows,
        comparison_rows=comp_rows,
        reference_share=ref_share,
        comparison_share=comp_share,
    )


def exposure_result(
    *,
    available: bool,
    all_effect: object,
    all_direction: object,
    status: str,
    fully_effect: object = None,
    fully_direction: object = None,
    same: bool | None = None,
    reference_rows: object = None,
    comparison_rows: object = None,
    reference_share: object = None,
    comparison_share: object = None,
) -> dict[str, object]:
    return {
        "fully_exposed_analysis_available": available,
        "all_round_effect": all_effect,
        "fully_exposed_effect": fully_effect,
        "all_round_direction": all_direction,
        "fully_exposed_direction": fully_direction,
        "same_direction_after_exposure_filter": same,
        "fully_exposed_rows_reference": reference_rows,
        "fully_exposed_rows_comparison": comparison_rows,
        "fully_exposed_share_reference": reference_share,
        "fully_exposed_share_comparison": comparison_share,
        "exposure_sensitivity_status": status,
    }


def apply_interpretation_metadata(raw: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    result = raw.copy()
    result["interpretation_class"] = result.apply(classify_interpretation, axis=1)
    result["finding_concept_id"] = result.apply(lambda row: row.get("finding_concept_id") or derive_finding_concept(row, settings), axis=1)
    result["finding_text"] = result.apply(explicit_finding_text, axis=1)
    return result


def apply_sensitivity_flags(raw: pd.DataFrame, opponent: pd.DataFrame, demo: pd.DataFrame) -> pd.DataFrame:
    result = raw.copy()
    opponent_flags = opponent.groupby("finding_id")["single_opponent_dependency"].max().to_dict() if not opponent.empty else {}
    demo_flags = demo.set_index("finding_id")["demo_fragile"].to_dict() if not demo.empty else {}
    result["opponent_dependency_flag"] = result["finding_id"].map(opponent_flags).fillna(False).astype(bool)
    result["demo_fragile_flag"] = result["finding_id"].map(demo_flags).fillna(False).astype(bool)
    return result


def apply_hardened_quality(raw: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    result = raw.copy()
    high_agree = float(settings.get("evidence", {}).get("high_min_demo_agreement", 0.75))
    moderate_agree = float(settings.get("evidence", {}).get("moderate_min_demo_agreement", 0.60))
    min_effect = float(settings.get("evidence", {}).get("minimum_effect_strength", 0.147))
    qualities = []
    eligible = []
    reasons = []
    for _, row in result.iterrows():
        blockers = blocker_reasons(row)
        effect = abs(safe_float(row.get("effect_size")) or 0.0)
        agreement = safe_float(row.get("demo_direction_agreement"))
        agreement_value = 1.0 if agreement is None and str(row.get("category")) == "site_choice" else (agreement or 0.0)
        if blockers:
            qualities.append("tentative" if row.get("eligible_before_hardening") else "insufficient")
            eligible.append(False)
            reasons.append("|".join(blockers))
        elif not row.get("eligible_before_hardening") or effect < min_effect:
            qualities.append("insufficient")
            eligible.append(False)
            reasons.append(str(row.get("exclusion_reason") or "insufficient_effect"))
        elif agreement_value >= high_agree and effect >= 0.474:
            qualities.append("high_descriptive")
            eligible.append(True)
            reasons.append(None)
        elif agreement_value >= moderate_agree:
            qualities.append("moderate_descriptive")
            eligible.append(True)
            reasons.append(None)
        else:
            qualities.append("tentative")
            eligible.append(False)
            reasons.append("low_demo_agreement")
    result["evidence_quality_hardened"] = qualities
    result["eligible_after_hardening"] = eligible
    result["hardening_exclusion_reason"] = reasons
    return result


def blocker_reasons(row: pd.Series) -> list[str]:
    blockers = []
    if bool(row.get("late_window_exposure_flag")):
        blockers.append("late_window_low_exposure")
    if bool(row.get("structural_review_flag")):
        blockers.append("structural_review")
    if bool(row.get("opponent_dependency_flag")):
        blockers.append("opponent_sensitive")
    if bool(row.get("demo_fragile_flag")):
        blockers.append("demo_fragile")
    if str(row.get("feature_name")) in CONTEXT_ONLY_FEATURES:
        blockers.append("context_only")
    if str(row.get("interpretation_class")) == "outcome_adjacent":
        blockers.append("outcome_adjacent")
    if str(row.get("exclusion_reason")) in {"unresolved_endpoint", "normalized_required", "map_specific"}:
        blockers.append(str(row.get("exclusion_reason")))
    if classify_direction(row.get("direction")) == "flat":
        blockers.append("flat_effect")
    return blockers


def build_direction_consistency(raw: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    rows = []
    group_cols = ["finding_concept_id", "comparison_type"]
    for keys, group in raw.groupby(group_cols, dropna=False):
        concept, comparison_type = keys
        directions = group["direction"].map(classify_direction)
        counts = directions.value_counts()
        nonflat = int(len(group) - counts.get("flat", 0))
        dominant = "flat" if nonflat == 0 else str(directions[directions.ne("flat")].mode().iloc[0])
        dominant_count = int(counts.get(dominant, 0))
        dominant_share = safe_divide(dominant_count, nonflat or len(group))
        rows.append(
            {
                "finding_concept_id": concept,
                "comparison_type": comparison_type,
                "candidate_count": len(group),
                "higher_count": int(counts.get("higher", 0)),
                "lower_count": int(counts.get("lower", 0)),
                "flat_count": int(counts.get("flat", 0)),
                "dominant_direction": dominant,
                "dominant_direction_share": dominant_share,
                "direction_consistent": bool(nonflat > 0 and (dominant_share or 0.0) >= 0.80),
                "conflicting_features": join_unique(group.loc[directions.ne(dominant) & directions.ne("flat"), "feature_name"]),
                "conflicting_windows": join_unique(group.loc[directions.ne(dominant) & directions.ne("flat"), "window_label"]),
                "status": "ok" if nonflat > 0 and (dominant_share or 0.0) >= 0.80 else "conflicting_or_flat",
            }
        )
    return pd.DataFrame(rows)


def build_tactical_finding_groups(
    raw: pd.DataFrame,
    direction: pd.DataFrame,
    settings: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    support_rows = []
    direction_lookup = direction.set_index(["finding_concept_id", "comparison_type"]) if not direction.empty else pd.DataFrame()
    for keys, group in raw.groupby(["finding_concept_id", "comparison_type"], dropna=False):
        concept, comparison_type = keys
        consistency = direction_lookup.loc[keys] if not direction_lookup.empty and keys in direction_lookup.index else pd.Series(dtype=object)
        selected = select_representative(group, settings)
        rep_id = selected.get("finding_id")
        directions = group["direction"].map(classify_direction)
        low_exposure = int(group["late_window_exposure_flag"].fillna(False).sum())
        structural = int(group["structural_review_flag"].fillna(False).sum())
        opponent = int(group["opponent_dependency_flag"].fillna(False).sum())
        rows.append(
            {
                "finding_concept_id": concept,
                "category": selected.get("category"),
                "semantic_id": selected.get("semantic_id"),
                "comparison_type": comparison_type,
                "raw_candidate_count": len(group),
                "feature_names": join_unique(group["feature_name"]),
                "windows": join_unique(group["window_label"]),
                "directions_observed": join_unique(directions),
                "direction_consistent": bool(consistency.get("direction_consistent", False)),
                "cohorts_supporting": join_unique(group.loc[directions.eq(selected.get("direction")), "cohort"]),
                "cohorts_conflicting": join_unique(group.loc[directions.ne(selected.get("direction")) & directions.ne("flat"), "cohort"]),
                "max_effect_size": max_abs(group["effect_size"]),
                "median_effect_size": median_abs(group["effect_size"]),
                "max_demo_agreement": safe_float(pd.to_numeric(group["demo_direction_agreement"], errors="coerce").max()),
                "median_demo_agreement": safe_float(pd.to_numeric(group["demo_direction_agreement"], errors="coerce").median()),
                "best_ci_low": selected.get("bootstrap_ci_low"),
                "best_ci_high": selected.get("bootstrap_ci_high"),
                "low_exposure_candidates": low_exposure,
                "structural_candidates": structural,
                "opponent_sensitive_candidates": opponent,
                "representative_finding_id": rep_id,
                "representative_feature": selected.get("feature_name"),
                "representative_window": selected.get("window_label"),
                "status": group_status(group, consistency),
            }
        )
        for _, candidate in group.iterrows():
            support_rows.append(
                {
                    "finding_concept_id": concept,
                    "representative": bool(candidate.get("finding_id") == rep_id),
                    "raw_finding_id": candidate.get("finding_id"),
                    "feature_name": candidate.get("feature_name"),
                    "cohort": candidate.get("cohort"),
                    "window": candidate.get("window_label"),
                    "direction": candidate.get("direction"),
                    "effect_size": candidate.get("effect_size"),
                    "demo_agreement": candidate.get("demo_direction_agreement"),
                    "exposure_status": candidate.get("exposure_sensitivity_status"),
                    "opponent_status": "warning" if bool(candidate.get("opponent_dependency_flag")) else "ok",
                    "support_role": support_role(candidate, selected),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(support_rows)


def build_consolidated_tactical_findings(
    groups: pd.DataFrame,
    raw: pd.DataFrame,
    opponent: pd.DataFrame,
    demo: pd.DataFrame,
    contradictions: pd.DataFrame,
    settings: dict[str, Any],
) -> pd.DataFrame:
    rows = []
    raw_by_id = raw.set_index("finding_id") if not raw.empty else pd.DataFrame()
    contradiction_ids = set(contradictions.loc[contradictions["requires_manual_review"], "finding_concept_id"]) if not contradictions.empty else set()
    for _, group in groups.iterrows():
        rep_id = group.get("representative_finding_id")
        rep = raw_by_id.loc[rep_id] if not raw_by_id.empty and rep_id in raw_by_id.index else pd.Series(dtype=object)
        blockers = blocker_reasons(rep) if not rep.empty else ["missing_representative"]
        if group.get("finding_concept_id") in contradiction_ids:
            blockers.append("direction_contradiction")
        quality = str(rep.get("evidence_quality_hardened") or "insufficient")
        if blockers and quality == "high_descriptive":
            quality = "tentative"
        rows.append(
            {
                "finding_concept_id": group.get("finding_concept_id"),
                "category": group.get("category"),
                "comparison_type": group.get("comparison_type"),
                "representative_finding_id": rep_id,
                "representative_feature": group.get("representative_feature"),
                "representative_window": group.get("representative_window"),
                "representative_text": rep.get("finding_text"),
                "effect_size": rep.get("effect_size"),
                "effect_strength": rep.get("effect_strength"),
                "demo_direction_agreement": rep.get("demo_direction_agreement"),
                "evidence_quality": quality,
                "raw_candidate_count": group.get("raw_candidate_count"),
                "cohorts_supporting": group.get("cohorts_supporting"),
                "cohorts_conflicting": group.get("cohorts_conflicting"),
                "direction_consistent": group.get("direction_consistent"),
                "low_exposure_candidates": group.get("low_exposure_candidates"),
                "opponent_sensitive_candidates": group.get("opponent_sensitive_candidates"),
                "demo_fragile": bool(rep.get("demo_fragile_flag", False)),
                "interpretation_class": rep.get("interpretation_class"),
                "hardening_exclusion_reason": "|".join(dict.fromkeys(blockers)) if blockers else None,
                "eligible_for_hardened_ranking": bool(rep.get("eligible_after_hardening", False) and not blockers),
                "ranking_score": concept_score(rep, group, settings),
                "status": "ok" if bool(rep.get("eligible_after_hardening", False) and not blockers) else "downgraded",
            }
        )
    return pd.DataFrame(rows)


def build_hardened_ranking(consolidated: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    if consolidated.empty:
        return pd.DataFrame()
    max_total = int(settings.get("ranking", {}).get("max_consolidated_findings", 15))
    max_category = int(settings.get("ranking", {}).get("max_findings_per_category", 4))
    eligible = consolidated[consolidated["eligible_for_hardened_ranking"]].copy()
    eligible = eligible.sort_values(["ranking_score", "raw_candidate_count"], ascending=[False, False])
    selected = []
    category_counts: dict[str, int] = {}
    selected_concepts: set[str] = set()
    for _, row in eligible.iterrows():
        category = str(row.get("category"))
        concept = str(row.get("finding_concept_id"))
        if concept in selected_concepts:
            continue
        if category_counts.get(category, 0) >= max_category:
            continue
        selected.append(row)
        selected_concepts.add(concept)
        category_counts[category] = category_counts.get(category, 0) + 1
        if len(selected) >= max_total:
            break
    if not selected:
        return pd.DataFrame(columns=list(consolidated.columns) + ["rank"])
    ranked = pd.DataFrame(selected).reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def build_hardened_cross_map_site_patterns(cross_site: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    epsilon = float(settings.get("site_pattern", {}).get("zero_effect_epsilon", 1e-9))
    min_support = float(settings.get("evidence", {}).get("moderate_min_demo_agreement", 0.60))
    rows = []
    for _, row in cross_site.iterrows():
        mirage_direction = signed_direction(row.get("mirage_a_b_effect"), epsilon)
        inferno_direction = signed_direction(row.get("inferno_a_b_effect"), epsilon)
        same = mirage_direction != "flat" and inferno_direction != "flat" and mirage_direction == inferno_direction
        support = safe_float(row.get("demo_support")) or 0.0
        rows.append(
            {
                "feature_name": row.get("feature_name"),
                "finding_concept_id": derive_site_pattern_concept(str(row.get("feature_name"))),
                "mirage_effect": row.get("mirage_a_b_effect"),
                "mirage_effect_strength": row.get("effect_strength_mirage"),
                "mirage_direction": mirage_direction,
                "inferno_effect": row.get("inferno_a_b_effect"),
                "inferno_effect_strength": row.get("effect_strength_inferno"),
                "inferno_direction": inferno_direction,
                "same_nonflat_direction": same,
                "mirage_demo_support": row.get("demo_support"),
                "inferno_demo_support": row.get("demo_support"),
                "minimum_demo_support": min_support,
                "eligible_as_shared_pattern": bool(same and support >= min_support),
                "status": "ok" if same and support >= min_support else "flat_on_one_or_more_maps" if "flat" in {mirage_direction, inferno_direction} else "opposite_or_weak_direction",
                "notes": "Compares within-map A-vs-B direction only; no cross-map site geometry equivalence.",
            }
        )
    return pd.DataFrame(rows)


def build_finding_opponent_sensitivity(raw: pd.DataFrame, rounds: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    threshold = float(settings.get("opponent_sensitivity", {}).get("dominant_share_warning", 0.50))
    min_opponents = int(settings.get("opponent_sensitivity", {}).get("minimum_opponents", 2))
    rows = []
    cohort_cache: dict[tuple[str, str], pd.DataFrame] = {}
    for _, finding in raw.iterrows():
        for map_id in unique_maps_for_finding(finding):
            cache_key = (map_id, str(finding.get("cohort")))
            if cache_key not in cohort_cache:
                cohort_cache[cache_key] = rows_for_finding(rounds, finding, map_id)
            scoped = cohort_cache[cache_key]
            valid = scoped[scoped[str(finding.get("feature_name"))].notna()] if str(finding.get("feature_name")) in scoped.columns else scoped
            counts = valid["opponent"].fillna("unknown").astype(str).value_counts() if "opponent" in valid.columns else pd.Series(dtype=int)
            dominant_opponent = counts.index[0] if not counts.empty else None
            dominant_share = safe_divide(int(counts.iloc[0]), len(valid)) if not counts.empty else None
            opponents = int(counts.size)
            insufficient_metadata = bool(opponents == 0 or (opponents == 1 and dominant_opponent == "unknown"))
            single = bool(
                not insufficient_metadata
                and dominant_share is not None
                and (dominant_share >= threshold or opponents < min_opponents)
            )
            rows.append(
                {
                    "finding_id": finding.get("finding_id"),
                    "finding_concept_id": finding.get("finding_concept_id"),
                    "map_id": map_id,
                    "cohort": finding.get("cohort"),
                    "feature_name": finding.get("feature_name"),
                    "valid_rows": len(valid),
                    "opponents": opponents,
                    "demos": int(valid["parse_id"].nunique(dropna=True)) if "parse_id" in valid.columns else 0,
                    "dominant_opponent": dominant_opponent,
                    "dominant_opponent_share": dominant_share,
                    "single_opponent_dependency": single,
                    "status": "insufficient_metadata" if insufficient_metadata else "warning" if single else "ok",
                }
            )
    return pd.DataFrame(rows)


def build_finding_demo_sensitivity(raw: pd.DataFrame, rounds: pd.DataFrame, map_requests: list[MapRequest]) -> pd.DataFrame:
    rows = []
    cache: dict[tuple[str, str, str], dict[str, object]] = {}
    for _, finding in raw.iterrows():
        if str(finding.get("category")) == "site_choice":
            rows.append(
                {
                    "finding_id": finding.get("finding_id"),
                    "finding_concept_id": finding.get("finding_concept_id"),
                    "feature_name": finding.get("feature_name"),
                    "cohort": finding.get("cohort"),
                    "demos_evaluated": 0,
                    "leave_one_demo_out_checks": 0,
                    "stable_direction_after_demo_removal": True,
                    "direction_flips": 0,
                    "flat_after_removal": 0,
                    "demo_fragile": False,
                    "comparison_type": finding.get("comparison_type"),
                    "effect_method": "aggregate_context",
                    "sensitivity_method": "not_applicable",
                    "status": "aggregate_context",
                }
            )
            continue
        feature = str(finding.get("feature_name"))
        if rounds.empty or feature not in rounds.columns or not bool(finding.get("eligible_before_hardening", False)):
            reference_demos = safe_float(finding.get("reference_demos"))
            comparison_demos = safe_float(finding.get("comparison_demos"))
            demos = int(max([value for value in [reference_demos, comparison_demos] if value is not None], default=0))
            rows.append(
                {
                    "finding_id": finding.get("finding_id"),
                    "finding_concept_id": finding.get("finding_concept_id"),
                    "feature_name": finding.get("feature_name"),
                    "cohort": finding.get("cohort"),
                    "demos_evaluated": demos,
                    "leave_one_demo_out_checks": 0,
                    "stable_direction_after_demo_removal": False,
                    "direction_flips": 0,
                    "flat_after_removal": 0,
                    "demo_fragile": False,
                    "comparison_type": finding.get("comparison_type"),
                    "effect_method": "not_available",
                    "sensitivity_method": "not_available",
                    "status": "not_evaluated",
                }
            )
            continue
        key = (feature, str(finding.get("cohort")), str(finding.get("comparison_type")))
        sensitivity = cache.get(key)
        if sensitivity is None:
            sensitivity = demo_sensitivity_for_feature(finding, rounds, map_requests)
            cache[key] = sensitivity
        rows.append(
            {
                "finding_id": finding.get("finding_id"),
                "finding_concept_id": finding.get("finding_concept_id"),
                "feature_name": finding.get("feature_name"),
                "cohort": finding.get("cohort"),
                "demos_evaluated": sensitivity["demos_evaluated"],
                "leave_one_demo_out_checks": sensitivity["leave_one_demo_out_checks"],
                "stable_direction_after_demo_removal": sensitivity["stable_direction_after_demo_removal"],
                "direction_flips": sensitivity["direction_flips"],
                "flat_after_removal": sensitivity["flat_after_removal"],
                "demo_fragile": sensitivity["demo_fragile"],
                "comparison_type": sensitivity["comparison_type"],
                "effect_method": sensitivity["effect_method"],
                "sensitivity_method": sensitivity["sensitivity_method"],
                "status": sensitivity["status"],
            }
        )
    return pd.DataFrame(rows)


def demo_sensitivity_for_feature(finding: pd.Series, rounds: pd.DataFrame, map_requests: list[MapRequest]) -> dict[str, object]:
    full = evaluate_finding_effect(rounds, finding, map_requests)
    if str(full["status"]) == "unsupported_comparison_type":
        return {
            "demos_evaluated": 0,
            "leave_one_demo_out_checks": 0,
            "stable_direction_after_demo_removal": False,
            "direction_flips": 0,
            "flat_after_removal": 0,
            "demo_fragile": False,
            "comparison_type": str(finding.get("comparison_type") or "unknown"),
            "effect_method": full["effect_method"],
            "sensitivity_method": "not_available",
            "status": "unsupported_comparison_type",
        }
    full_direction = str(full["direction"])
    scoped = full["rows"]
    removals = []
    for parse_id in scoped["parse_id"].dropna().unique() if "parse_id" in scoped.columns else []:
        subset = scoped[~scoped["parse_id"].eq(parse_id)]
        effect = evaluate_finding_effect(subset, finding, map_requests)
        removals.append(str(effect["direction"]))
    nonflat_removals = [value for value in removals if value != "flat"]
    stable = bool(nonflat_removals and all(value == full_direction for value in nonflat_removals))
    fragile = bool(nonflat_removals and any(value != full_direction for value in nonflat_removals))
    return {
        "demos_evaluated": int(scoped["parse_id"].nunique(dropna=True)) if "parse_id" in scoped.columns else 0,
        "leave_one_demo_out_checks": len(removals),
        "stable_direction_after_demo_removal": stable,
        "direction_flips": int(sum(value != full_direction and value != "flat" for value in removals)),
        "flat_after_removal": int(sum(value == "flat" for value in removals)),
        "demo_fragile": fragile or len(removals) < 2,
        "comparison_type": str(finding.get("comparison_type") or "unknown"),
        "effect_method": full["effect_method"],
        "sensitivity_method": "leave_one_demo_out",
        "status": "warning" if fragile or len(removals) < 2 else "ok",
    }


def build_finding_exclusion_audit(eligibility: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in eligibility.iterrows():
        original = normalized_value(row.get("exclusion_reason"))
        hardened = taxonomy_reason(row)
        secondary = secondary_taxonomy_reasons(row)
        if original or hardened:
            rows.append(
                {
                    "feature_name": row.get("feature_name"),
                    "original_exclusion_reason": original,
                    "hardened_exclusion_reason": hardened,
                    "secondary_exclusion_reasons": "|".join(secondary),
                    "taxonomy_changed": bool(original != hardened),
                    "status": "changed" if original != hardened else "ok",
                }
            )
    return pd.DataFrame(rows)


def build_tactical_finding_contradictions(direction: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in direction.iterrows():
        conflicting = int(row.get("higher_count", 0)) > 0 and int(row.get("lower_count", 0)) > 0
        share = safe_float(row.get("dominant_direction_share")) or 0.0
        severity = "high" if conflicting and share < 0.70 else "medium" if conflicting else "none"
        rows.append(
            {
                "finding_concept_id": row.get("finding_concept_id"),
                "comparison_type": row.get("comparison_type"),
                "conflicting_candidate_count": int(row.get("higher_count", 0)) + int(row.get("lower_count", 0)) if conflicting else 0,
                "conflicting_features": row.get("conflicting_features"),
                "conflicting_cohorts": None,
                "conflicting_windows": row.get("conflicting_windows"),
                "severity": severity,
                "requires_manual_review": bool(severity in {"high", "medium"}),
                "notes": "Opposite strong directions exist across windows/cohorts." if conflicting else "No opposite non-flat direction detected.",
            }
        )
    return pd.DataFrame(rows)


def build_modeling_context_findings(consolidated: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in consolidated.iterrows():
        interpretation = str(row.get("interpretation_class"))
        safe = bool(row.get("eligible_for_hardened_ranking")) and interpretation != "outcome_adjacent"
        relevant = str(row.get("category")) in {"direct_feature", "semantic_feature", "site_choice"}
        rows.append(
            {
                "finding_concept_id": row.get("finding_concept_id"),
                "representative_feature": row.get("representative_feature"),
                "relevant_to_ab_modeling": relevant,
                "reason": "Descriptive tactical context only; Stage 8.11 must apply its own leakage and horizon rules.",
                "safe_as_modeling_context": bool(safe and relevant),
                "leakage_risk": "horizon_risk" if interpretation in {"outcome_adjacent", "tactical_progression"} else "review_required",
                "sample_risk": "exploratory_only",
                "notes": "Not automatic feature selection.",
            }
        )
    return pd.DataFrame(rows)


def build_final_audit(
    frames: dict[str, pd.DataFrame],
    inputs: dict[str, pd.DataFrame],
    preconditions: pd.DataFrame,
    *,
    target_team: str,
    map_requests: list[MapRequest],
    source_raw_candidates: int,
) -> pd.DataFrame:
    raw = frames["raw_finding_evidence"]
    groups = frames["tactical_finding_groups"]
    consolidated = frames["consolidated_tactical_findings"]
    ranking = frames["hardened_tactical_finding_ranking"]
    read_only = frames["tactical_finding_hardening_read_only_audit"]
    contradictions = frames["tactical_finding_contradictions"]
    site_patterns = frames["hardened_cross_map_site_patterns"]
    critical = int(preconditions["status"].eq("failed").sum()) + int(read_only["status"].eq("failed").sum())
    hardened_ok = not ranking.empty and critical == 0
    raw_ranked = inputs["multi_map_ranked_findings"]
    redundant = max(source_raw_candidates - len(groups), 0)
    ready = bool(
        hardened_ok
        and read_only["status"].eq("ok").all()
        and not raw[raw["hardening_exclusion_reason"].fillna("").str.contains("unresolved_endpoint|normalized_required|structural_review") & raw["eligible_after_hardening"]].any().any()
    )
    return pd.DataFrame(
        [
            {
                "audit_id": "tactical_finding_hardening_v1",
                "target_team": target_team,
                "maps": ",".join(request.map_name for request in map_requests),
                "stage_8_10_passed": bool(inputs["multi_map_tactical_eda_audit"].iloc[0].get("status") == "passed"),
                "raw_candidates": source_raw_candidates,
                "raw_ranked_findings": len(raw_ranked),
                "finding_concepts": int(groups["finding_concept_id"].nunique(dropna=True)) if not groups.empty else 0,
                "consolidated_findings": len(consolidated),
                "hardened_ranked_findings": len(ranking),
                "high_descriptive_findings": int(consolidated["evidence_quality"].eq("high_descriptive").sum()) if not consolidated.empty else 0,
                "moderate_descriptive_findings": int(consolidated["evidence_quality"].eq("moderate_descriptive").sum()) if not consolidated.empty else 0,
                "tentative_findings": int(consolidated["evidence_quality"].eq("tentative").sum()) if not consolidated.empty else 0,
                "redundant_candidates_collapsed": redundant,
                "late_window_candidates_checked": int(raw["window_end"].fillna(0).ge(75).sum()) if not raw.empty else 0,
                "late_window_candidates_downgraded": int(raw["late_window_exposure_flag"].fillna(False).sum()) if not raw.empty else 0,
                "opponent_sensitive_findings": int(consolidated["hardening_exclusion_reason"].fillna("").str.contains("opponent_sensitive").sum()) if not consolidated.empty else 0,
                "demo_fragile_findings": int(consolidated["demo_fragile"].fillna(False).sum()) if not consolidated.empty else 0,
                "direction_conflicts": int(contradictions["requires_manual_review"].fillna(False).sum()) if not contradictions.empty else 0,
                "cross_map_flat_pattern_rejections": int(site_patterns["status"].eq("flat_on_one_or_more_maps").sum()) if not site_patterns.empty else 0,
                "exclusion_taxonomy_changes": int(frames["finding_exclusion_audit"]["taxonomy_changed"].fillna(False).sum()) if not frames["finding_exclusion_audit"].empty else 0,
                "core_gold_unchanged": bool(read_only[read_only["artifact_group"].eq("core_gold")]["status"].eq("ok").all()),
                "stage_8_10_outputs_unchanged": bool(read_only[read_only["artifact_group"].eq("stage_8_10")]["status"].eq("ok").all()),
                "critical_failures": critical,
                "warnings": int(preconditions["status"].eq("warning").sum()),
                "ready_for_stage_8_11": ready,
                "status": "passed" if ready else "failed",
                "created_at": now_utc(),
            }
        ]
    )


def capture_sensitivity_revalidation_snapshot(output_dir: Path) -> dict[str, object]:
    audit = read_optional(output_dir / "tactical_finding_hardening_audit.parquet")
    demo = read_optional(output_dir / "finding_demo_sensitivity.parquet")
    raw = read_optional(output_dir / "raw_finding_evidence.parquet")
    ranking = read_optional(output_dir / "hardened_tactical_finding_ranking.parquet")
    consolidated = read_optional(output_dir / "consolidated_tactical_findings.parquet")
    return sensitivity_metrics_from_frames(
        {
            "tactical_finding_hardening_audit": audit,
            "finding_demo_sensitivity": demo,
            "raw_finding_evidence": raw,
            "hardened_tactical_finding_ranking": ranking,
            "consolidated_tactical_findings": consolidated,
        }
    )


def build_sensitivity_revalidation(before: dict[str, object], frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    after = sensitivity_metrics_from_frames(frames)
    rows = []
    for metric, after_value in after.items():
        before_value = before.get(metric)
        before_num = safe_float(before_value)
        after_num = safe_float(after_value)
        difference = after_num - before_num if before_num is not None and after_num is not None else None
        rows.append(
            {
                "metric": metric,
                "before": before_value,
                "after": after_value,
                "difference": difference,
                "reason": "comparison_dispatch_revalidation" if before_value is not None and before_value != after_value else "unchanged_or_no_previous",
            }
        )
    return pd.DataFrame(rows)


def sensitivity_metrics_from_frames(frames: dict[str, pd.DataFrame]) -> dict[str, object]:
    audit = frames.get("tactical_finding_hardening_audit", pd.DataFrame())
    demo = frames.get("finding_demo_sensitivity", pd.DataFrame())
    raw = frames.get("raw_finding_evidence", pd.DataFrame())
    ranking = frames.get("hardened_tactical_finding_ranking", pd.DataFrame())
    consolidated = frames.get("consolidated_tactical_findings", pd.DataFrame())
    return {
        "demo_fragile_findings": first_or_count(audit, "demo_fragile_findings", demo, "demo_fragile"),
        "stable_lodo_findings": int(demo["stable_direction_after_demo_removal"].fillna(False).sum()) if "stable_direction_after_demo_removal" in demo.columns else None,
        "fully_exposed_available": int(raw["fully_exposed_analysis_available"].fillna(False).sum()) if "fully_exposed_analysis_available" in raw.columns else None,
        "exposure_reversals": int(raw["exposure_sensitivity_status"].astype(str).eq("reversed").sum()) if "exposure_sensitivity_status" in raw.columns else None,
        "hardened_ranked_findings": len(ranking) if not ranking.empty else first_or_none(audit, "hardened_ranked_findings"),
        "high_descriptive": int(consolidated["evidence_quality"].astype(str).eq("high_descriptive").sum()) if "evidence_quality" in consolidated.columns else None,
        "moderate_descriptive": int(consolidated["evidence_quality"].astype(str).eq("moderate_descriptive").sum()) if "evidence_quality" in consolidated.columns else None,
        "tentative": int(consolidated["evidence_quality"].astype(str).eq("tentative").sum()) if "evidence_quality" in consolidated.columns else None,
    }


def first_or_count(audit: pd.DataFrame, audit_column: str, frame: pd.DataFrame, count_column: str) -> object:
    value = first_or_none(audit, audit_column)
    if value is not None:
        return value
    if count_column in frame.columns:
        return int(frame[count_column].fillna(False).sum())
    return None


def first_or_none(frame: pd.DataFrame, column: str) -> object:
    if frame.empty or column not in frame.columns:
        return None
    return frame.iloc[0].get(column)


def capture_stage_output_fingerprints(stage_dir: Path) -> pd.DataFrame:
    rows = []
    for name in STAGE_8_10_OUTPUT_NAMES:
        for suffix in ["csv", "parquet"]:
            path = stage_dir / f"{name}.{suffix}"
            rows.append(
                {
                    "artifact_name": f"stage_8_10/{name}.{suffix}",
                    "path": str(path),
                    "exists": path.exists(),
                    "row_count": None,
                    "schema_hash": "",
                    "content_hash": file_hash(path),
                }
            )
    return pd.DataFrame(rows)


def build_combined_read_only_audit(
    core_before: pd.DataFrame,
    core_after: pd.DataFrame,
    stage_before: pd.DataFrame,
    stage_after: pd.DataFrame,
) -> pd.DataFrame:
    core = build_read_only_audit(core_before, core_after)
    core["artifact_group"] = "core_gold"
    stage = build_read_only_audit(stage_before, stage_after)
    stage["artifact_group"] = "stage_8_10"
    return pd.concat([core, stage], ignore_index=True)


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    sanitized = {name: sanitize_for_parquet(frames.get(name, pd.DataFrame())) for name in OUTPUT_NAMES}
    return write_dataframe_outputs(sanitized, output_dir, force=force)


def load_round_features_for_sensitivity(gold_dir: Path, map_requests: list[MapRequest], target_team: str) -> pd.DataFrame:
    path = gold_dir / "round_features" / "round_features_t_side_all.parquet"
    frame = read_optional(path)
    if frame.empty:
        return frame
    aliases = {request.map_name.casefold(): request.map_id for request in map_requests}
    aliases.update({request.map_id.casefold(): request.map_id for request in map_requests})
    result = frame.copy()
    result["map_id"] = result.get("map_id", result.get("canonical_map_name", result.get("map_name", ""))).astype(str).str.casefold().map(aliases)
    if "target_team" in result.columns:
        result = result[result["target_team"].astype(str).str.casefold().eq(target_team.casefold())]
    return result[result["map_id"].isin([request.map_id for request in map_requests])].copy()


def rows_for_finding(rounds: pd.DataFrame, finding: pd.Series, map_id: str) -> pd.DataFrame:
    if rounds.empty or "map_id" not in rounds.columns:
        return rounds.iloc[0:0].copy()
    scoped = rounds[rounds["map_id"].eq(map_id)].copy()
    return apply_cohort_filter(scoped, str(finding.get("cohort")))


def rows_for_cross_map_finding(rounds: pd.DataFrame, finding: pd.Series, map_requests: list[MapRequest]) -> pd.DataFrame:
    if rounds.empty:
        return rounds.iloc[0:0].copy()
    scoped = rounds[rounds["map_id"].isin([request.map_id for request in map_requests])].copy()
    return apply_cohort_filter(scoped, str(finding.get("cohort")))


def apply_cohort_filter(frame: pd.DataFrame, cohort: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    label = frame.get("target_site_model_label", pd.Series(index=frame.index, dtype=object)).astype(str)
    confidence = frame.get("label_confidence", pd.Series(index=frame.index, dtype=object)).astype(str)
    planted = label.isin(["A", "B"]) & confidence.eq("high")
    if cohort == "t_side_planted":
        return frame[planted].copy()
    if cohort == "t_side_no_valid_target_plant":
        return frame[~planted].copy()
    if cohort == "t_side_a_plant":
        return frame[planted & label.eq("A")].copy()
    if cohort == "t_side_b_plant":
        return frame[planted & label.eq("B")].copy()
    return frame.copy()


def cross_map_median_difference(frame: pd.DataFrame, finding: pd.Series, map_requests: list[MapRequest]) -> float | None:
    feature = str(finding.get("feature_name"))
    if frame.empty or feature not in frame.columns:
        return None
    reference = pd.to_numeric(frame[frame["map_id"].eq(map_requests[0].map_id)][feature], errors="coerce").dropna()
    comparison = pd.to_numeric(frame[frame["map_id"].eq(map_requests[1].map_id)][feature], errors="coerce").dropna()
    if reference.empty or comparison.empty:
        return None
    return float(comparison.median() - reference.median())


def evaluate_finding_effect(frame: pd.DataFrame, finding: pd.Series, map_requests: list[MapRequest]) -> dict[str, object]:
    comparison_type = str(finding.get("comparison_type") or finding.get("comparison") or "unknown")
    feature = str(finding.get("feature_name"))
    if frame.empty or feature not in frame.columns:
        return effect_result(frame.iloc[0:0].copy(), None, "not_available", comparison_type, 0, 0)
    if comparison_type == "cross_map":
        scoped = rows_for_cross_map_finding(frame, finding, map_requests)
        reference_map = map_requests[0].map_id
        comparison_map = map_requests[1].map_id
        reference = numeric_values(scoped[scoped["map_id"].eq(reference_map)], feature)
        comparison = numeric_values(scoped[scoped["map_id"].eq(comparison_map)], feature)
        effect = median_difference(comparison, reference)
        return effect_result(scoped, effect, "cross_map_median_difference", comparison_type, len(reference), len(comparison))
    if comparison_type.endswith("_A_vs_B"):
        map_id = comparison_type.removesuffix("_A_vs_B")
        scoped = rows_for_finding(frame, finding, map_id)
        labels = scoped.get("target_site_model_label", pd.Series(index=scoped.index, dtype=object)).astype(str)
        confidence = scoped.get("label_confidence", pd.Series(index=scoped.index, dtype=object)).astype(str).str.casefold()
        planted = confidence.eq("high") & labels.isin(["A", "B"])
        reference = numeric_values(scoped[planted & labels.eq("A")], feature)
        comparison = numeric_values(scoped[planted & labels.eq("B")], feature)
        effect = median_difference(comparison, reference)
        return effect_result(scoped[planted].copy(), effect, "within_map_b_minus_a_median", comparison_type, len(reference), len(comparison))
    if comparison_type.endswith("_planted_vs_no_plant"):
        map_id = comparison_type.removesuffix("_planted_vs_no_plant")
        if frame.empty or "map_id" not in frame.columns:
            scoped = frame.iloc[0:0].copy()
        else:
            scoped = frame[frame["map_id"].eq(map_id)].copy()
        labels = scoped.get("target_site_model_label", pd.Series(index=scoped.index, dtype=object)).astype(str)
        confidence = scoped.get("label_confidence", pd.Series(index=scoped.index, dtype=object)).astype(str).str.casefold()
        planted_mask = confidence.eq("high") & labels.isin(["A", "B"])
        reference = numeric_values(scoped[planted_mask], feature)
        comparison = numeric_values(scoped[~planted_mask], feature)
        effect = median_difference(comparison, reference)
        return effect_result(scoped, effect, "within_map_no_plant_minus_planted_median", comparison_type, len(reference), len(comparison))
    if comparison_type == "cross_map_site_choice_distribution":
        return effect_result(frame.iloc[0:0].copy(), None, "not_applicable", comparison_type, 0, 0, status="not_applicable")
    return effect_result(frame.iloc[0:0].copy(), None, "unsupported_comparison_type", comparison_type, 0, 0, status="unsupported_comparison_type")


def numeric_values(frame: pd.DataFrame, feature: str) -> pd.Series:
    if frame.empty or feature not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[feature], errors="coerce").dropna()


def median_difference(comparison: pd.Series, reference: pd.Series) -> float | None:
    if reference.empty or comparison.empty:
        return None
    return float(comparison.median() - reference.median())


def effect_result(
    rows: pd.DataFrame,
    effect: float | None,
    method: str,
    comparison_type: str,
    reference_rows: int,
    comparison_rows: int,
    *,
    status: str | None = None,
) -> dict[str, object]:
    final_status = status or ("ok" if effect is not None else "insufficient_rows")
    return {
        "rows": rows,
        "effect": effect,
        "direction": classify_difference(effect),
        "effect_method": method,
        "comparison_type": comparison_type,
        "reference_rows": reference_rows,
        "comparison_rows": comparison_rows,
        "status": final_status,
    }


def select_representative(group: pd.DataFrame, settings: dict[str, Any]) -> pd.Series:
    ranked = group.copy()
    ranked["_has_blocker"] = ranked.apply(lambda row: bool(blocker_reasons(row)), axis=1)
    ranked["_agreement"] = pd.to_numeric(ranked["demo_direction_agreement"], errors="coerce").fillna(1.0)
    ranked["_effect"] = pd.to_numeric(ranked["effect_size"], errors="coerce").abs().fillna(0.0)
    ranked["_window_end"] = pd.to_numeric(ranked["window_end"], errors="coerce").fillna(9999)
    ranked["_quality"] = ranked["evidence_quality_hardened"].map({"high_descriptive": 3, "moderate_descriptive": 2, "tentative": 1}).fillna(0)
    ranked = ranked.sort_values(
        ["_has_blocker", "_quality", "_agreement", "_effect", "_window_end", "feature_name"],
        ascending=[True, False, False, False, True, True],
    )
    return ranked.iloc[0]


def group_status(group: pd.DataFrame, consistency: pd.Series) -> str:
    if group["eligible_after_hardening"].fillna(False).any() and bool(consistency.get("direction_consistent", False)):
        return "ok"
    if group["late_window_exposure_flag"].fillna(False).any():
        return "downgraded_exposure"
    if group["structural_review_flag"].fillna(False).any():
        return "structural_review"
    return "tentative"


def support_role(candidate: pd.Series, selected: pd.Series) -> str:
    if candidate.get("finding_id") == selected.get("finding_id"):
        return "representative"
    if not bool(candidate.get("eligible_after_hardening", False)):
        return "excluded"
    if classify_direction(candidate.get("direction")) != classify_direction(selected.get("direction")):
        return "conflicting"
    return "supporting"


def concept_score(rep: pd.Series, group: pd.Series, settings: dict[str, Any]) -> float:
    if rep.empty:
        return 0.0
    quality = {"high_descriptive": 3.0, "moderate_descriptive": 2.0, "tentative": 1.0}.get(str(rep.get("evidence_quality_hardened")), 0.0)
    effect = abs(safe_float(rep.get("effect_size")) or 0.0)
    agreement = safe_float(rep.get("demo_direction_agreement")) or 0.60
    consistency = 1.0 if bool(group.get("direction_consistent")) else 0.0
    support = min(float(group.get("raw_candidate_count") or 0) / 10.0, 1.0)
    blocker_penalty = 1.0 if blocker_reasons(rep) else 0.0
    return round(quality * 3 + effect * 2 + agreement + consistency + support - blocker_penalty * 4, 4)


def derive_finding_concept(row: pd.Series | dict[str, object], settings: dict[str, Any]) -> str:
    feature = str(row.get("feature_name") or "")
    category = str(row.get("category") or "")
    semantic = normalized_value(row.get("semantic_id")) or infer_semantic_from_feature(feature)
    band = classify_window_band(row.get("window_start"), row.get("window_end"), settings)
    if feature == "plant_site_distribution_b_share":
        return "site_choice.distribution"
    if feature in EVENT_TIMING_FEATURES:
        return f"utility.{utility_name(feature)}.first_timing"
    if feature.startswith(("smokes_used_", "flashes_used_", "molotovs_used_", "he_used_", "total_utility_used_")):
        return f"utility.{utility_name(feature)}.{band}_usage"
    if feature.startswith("team_") and feature.endswith("_start"):
        return f"utility.inventory.{utility_name(feature)}"
    if feature.startswith("team_spread"):
        return f"structure.team_spread.{band}"
    if feature.startswith("avg_pairwise_distance"):
        return f"structure.pairwise_distance.{band}"
    if feature.startswith("players_alive"):
        return f"plant_progression.players_alive.{band}"
    if feature.startswith("players_") and semantic:
        return f"semantic.{semantic}.player_presence.{band}"
    if feature.startswith("time_") and semantic:
        return f"semantic.{semantic}.time_presence.{band}"
    if category == "site_pattern":
        return derive_site_pattern_concept(feature)
    return f"{category}.{semantic or feature_base(feature)}.{band}"


def derive_site_pattern_concept(feature: str) -> str:
    semantic = infer_semantic_from_feature(feature)
    if semantic:
        return f"site_pattern.{semantic}"
    return f"site_pattern.{feature_base(feature)}"


def classify_window_band(start: object, end: object, settings: dict[str, Any]) -> str:
    end_value = safe_float(end)
    if end_value is None:
        return "non_temporal"
    early_end = float(settings.get("time_bands", {}).get("early_end", 35))
    mid_end = float(settings.get("time_bands", {}).get("mid_end", 75))
    if end_value <= early_end:
        return "early"
    if end_value <= mid_end:
        return "mid"
    return "late"


def parse_feature_window(feature: object) -> tuple[str | None, int | None, int | None]:
    parsed = parse_window(str(feature))
    if parsed is None:
        point = re.match(r".+_([0-9]+)s$", str(feature))
        if point:
            horizon = int(point.group(1))
            return "point", horizon, horizon
        return None, None, None
    _, start, end = parsed
    return "cumulative" if start == 0 else "interval", start, end


def window_label(start: object, end: object) -> str:
    start_number = safe_float(start)
    end_number = safe_float(end)
    if start_number is None or end_number is None:
        return "non_temporal"
    return f"{int(start_number)}_{int(end_number)}"


def direction_fields(row: pd.Series | dict[str, object]) -> tuple[str, str, str]:
    comparison_type = str(row.get("comparison_type") or "")
    if comparison_type == "cross_map":
        return str(row.get("feature_name")), str(row.get("reference_map_name")), str(row.get("comparison_map_name"))
    if comparison_type.endswith("_A_vs_B"):
        return str(row.get("feature_name")), "A-plant rounds", "B-plant rounds"
    if comparison_type.endswith("_planted_vs_no_plant"):
        return str(row.get("feature_name")), "planted rounds", "no-target-plant rounds"
    if comparison_type == "cross_map_site_choice_distribution":
        return "B plant share", str(row.get("reference_map_name")), str(row.get("comparison_map_name"))
    return str(row.get("feature_name")), str(row.get("reference_map_name")), str(row.get("comparison_map_name"))


def explicit_finding_text(row: pd.Series | dict[str, object]) -> str:
    direction = classify_direction(row.get("direction"))
    feature = str(row.get("feature_name"))
    ref = str(row.get("direction_reference") or row.get("reference_map_name"))
    comp = str(row.get("direction_comparison") or row.get("comparison_map_name"))
    if direction == "flat":
        return f"{feature} is descriptively flat between {ref} and {comp}; interpretation is non-causal."
    if feature in EVENT_TIMING_FEATURES:
        temporal = "later" if direction == "higher" else "earlier"
        return f"{human_feature(feature)} occurs {temporal} on {comp} than {ref}; interpretation is non-causal."
    if str(row.get("comparison_type")).endswith("_A_vs_B"):
        direction_word = "higher" if direction == "higher" else "lower"
        return f"{human_feature(feature)} is {direction_word} in {comp} than {ref}; interpretation is non-causal."
    if str(row.get("comparison_type")).endswith("_planted_vs_no_plant"):
        direction_word = "higher" if direction == "higher" else "lower"
        return f"{human_feature(feature)} is {direction_word} in {comp} than {ref}; no-plant is descriptive, not a failure label."
    direction_word = "higher" if direction == "higher" else "lower"
    return f"{human_feature(feature)} is {direction_word} on {comp} than {ref}; interpretation is non-causal."


def site_choice_text(reference_name: str, comparison_name: str, ref: pd.Series, comp: pd.Series) -> str:
    ref_b = safe_float(ref.get("b_share")) or 0.0
    comp_b = safe_float(comp.get("b_share")) or 0.0
    if abs(comp_b - ref_b) < 1e-9:
        return f"Observed B plant share is similar on {comparison_name} and {reference_name}; no geometry equivalence is implied."
    balance = "more balanced" if abs(comp_b - 0.5) < abs(ref_b - 0.5) else "less balanced"
    return f"Observed planted T rounds are {balance} between A and B on {comparison_name} than {reference_name}; this is plant-site choice only."


def classify_interpretation(row: pd.Series) -> str:
    feature = str(row.get("feature_name"))
    end = safe_float(row.get("window_end"))
    category = str(row.get("category"))
    if feature.startswith("round_duration"):
        return "outcome_adjacent"
    if feature.startswith("players_alive") and end is not None and end >= 75:
        return "outcome_adjacent"
    if feature.startswith("players_alive") or category == "plant_progression":
        return "tactical_progression"
    if feature.startswith(("team_", "first_", "smokes_used", "flashes_used", "molotovs_used", "he_used", "total_utility_used")):
        return "tactical_input"
    if feature.startswith(("players_", "time_", "team_spread", "avg_pairwise")):
        return "tactical_progression"
    if category in {"site_choice", "site_pattern"}:
        return "context"
    return "unknown"


def taxonomy_reason(row: pd.Series) -> str | None:
    feature = str(row.get("feature_name") or "")
    coordinate = str(row.get("coordinate_dependency") or "")
    mode = str(row.get("cross_map_comparison_mode") or "")
    if any(feature.startswith(prefix) for prefix in ENDPOINT_PREFIXES):
        return "unresolved_endpoint"
    if coordinate in {"raw_coordinate", "raw_coordinates", "coordinate"} or mode in {"normalized", "normalized_required", "normalization_required"}:
        return "normalized_required"
    if mode == "map_specific":
        return "map_specific"
    if bool(row.get("structural_review_flag", False)):
        return "structural_review"
    return normalized_value(row.get("exclusion_reason"))


def secondary_taxonomy_reasons(row: pd.Series) -> list[str]:
    reasons = []
    feature = str(row.get("feature_name") or "")
    if any(feature.startswith(prefix) for prefix in ENDPOINT_PREFIXES):
        reasons.append("unresolved_endpoint")
    coordinate = str(row.get("coordinate_dependency") or "")
    if coordinate in {"raw_coordinate", "raw_coordinates", "coordinate"}:
        reasons.append("normalized_required")
    if bool(row.get("structural_review_flag", False)):
        reasons.append("structural_review")
    original = normalized_value(row.get("exclusion_reason"))
    if original:
        reasons.append(original)
    return list(dict.fromkeys(reasons))


def unique_maps_for_finding(finding: pd.Series) -> list[str]:
    ref = normalized_value(finding.get("reference_map_id"))
    comp = normalized_value(finding.get("comparison_map_id"))
    return list(dict.fromkeys([value for value in [ref, comp] if value]))


def metric_value(row: pd.Series, map_id: str, metric: str) -> float | None:
    if row.empty:
        return None
    return safe_float(row.get(f"{map_id}_{metric}"))


def numeric_column(source_row: pd.Series, map_id: str, name: str, fallback: pd.Series) -> float | None:
    return safe_float(source_row.get(f"{map_id}_{name}")) if not source_row.empty else safe_float(fallback.get(f"{map_id}_{name}"))


def signed_by_difference(effect: object, difference: object) -> float | None:
    value = abs(safe_float(effect) or 0.0)
    diff = safe_float(difference)
    if diff is None:
        return safe_float(effect)
    if abs(diff) < 1e-9:
        return 0.0
    return value if diff > 0 else -value


def classify_difference(value: object) -> str:
    number = safe_float(value)
    if number is None or abs(number) < 1e-9:
        return "flat"
    return "higher" if number > 0 else "lower"


def classify_direction(value: object) -> str:
    text = str(value).strip().casefold()
    if text in {"higher", "positive", "later"}:
        return "higher"
    if text in {"lower", "negative", "earlier"}:
        return "lower"
    return "flat"


def signed_direction(value: object, epsilon: float) -> str:
    number = safe_float(value)
    if number is None or abs(number) <= epsilon:
        return "flat"
    return "positive" if number > 0 else "negative"


def strength_from_abs(value: object) -> str:
    number = abs(safe_float(value) or 0.0)
    if number >= 0.30:
        return "large"
    if number >= 0.20:
        return "moderate"
    if number >= 0.10:
        return "small"
    return "negligible"


def prefer_number(primary: object, fallback: object) -> float | None:
    primary_number = safe_float(primary)
    return primary_number if primary_number is not None else safe_float(fallback)


def safe_float(value: object) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_subtract(left: object, right: object) -> float | None:
    left_number = safe_float(left)
    right_number = safe_float(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def safe_divide(numerator: object, denominator: object) -> float | None:
    return shared_safe_divide(numerator, denominator)


def normalized_value(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return None if not text or text.casefold() == "nan" else text


def max_abs(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").abs().dropna()
    return float(numeric.max()) if not numeric.empty else None


def median_abs(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").abs().dropna()
    return float(numeric.median()) if not numeric.empty else None


def join_unique(values: pd.Series) -> str:
    clean = [str(value) for value in values if normalized_value(value)]
    return "|".join(dict.fromkeys(clean))


def feature_base(feature: str) -> str:
    parsed = parse_window(feature)
    if parsed is not None:
        return parsed[0]
    return re.sub(r"_[0-9]+s$", "", feature)


def utility_name(feature: str) -> str:
    if "smoke" in feature:
        return "smoke"
    if "flash" in feature:
        return "flash"
    if "molotov" in feature:
        return "molotov"
    if feature.startswith("he_") or "_he_" in feature or "team_he" in feature:
        return "he"
    if "total_utility" in feature or "utility" in feature:
        return "total"
    return feature_base(feature)


def infer_semantic_from_feature(feature: str) -> str | None:
    for semantic in ["mid_control", "a_pressure", "b_pressure", "ct_space"]:
        if semantic in feature:
            return semantic
    return None


def human_feature(feature: str) -> str:
    if feature == "first_smoke_time":
        return "First smoke usage"
    if feature == "first_molotov_time":
        return "First molotov usage"
    if feature == "first_utility_time":
        return "First observed utility usage"
    return feature.replace("_", " ")


def read_optional(path: Path) -> pd.DataFrame:
    return read_optional_table(path) if path.suffix in {".parquet", ".csv"} else pd.DataFrame()


def build_report(frames: dict[str, pd.DataFrame], *, target_team: str, map_requests: list[MapRequest]) -> str:
    audit = frames["tactical_finding_hardening_audit"]
    ranked = frames["hardened_tactical_finding_ranking"]
    consolidated = frames["consolidated_tactical_findings"]
    sections = [
        f"# {target_team} Mirage vs Inferno -- Hardened Tactical Findings",
        "",
        "## Purpose",
        "Consolidate Stage 8.10 raw statistical rows into auditable tactical evidence units without modifying core Gold outputs.",
        "",
        "## Input EDA",
        markdown_table(audit, list(audit.columns)),
        "",
        "## Why Consolidation Was Needed",
        "A feature window is not a tactical finding. This stage collapses redundant windows/cohorts, hardens direction text, applies temporal exposure checks, and evaluates opponent/demo sensitivity.",
        "",
        "## Evidence Method",
        "Evidence is descriptive, map-order explicit, demo-aware, and non-causal. The requested map order is "
        f"{map_requests[0].map_name} as reference and {map_requests[1].map_name} as comparison.",
        "",
        "## Map Comparison Direction",
        "Final text names maps explicitly and never uses first-map or second-map wording.",
        "",
        "## Temporal Exposure Rules",
        "Late windows are downgraded when either map has exposure below the configured threshold.",
        "",
        "## Finding Consolidation",
        markdown_table(frames["tactical_finding_groups"], ["finding_concept_id", "raw_candidate_count", "representative_feature", "directions_observed", "status"], top_n=30),
        "",
        "## Top Hardened Findings",
        markdown_table(ranked, ["rank", "finding_concept_id", "category", "representative_feature", "evidence_quality", "representative_text"], top_n=15),
        "",
        "## Utility Findings",
        markdown_table(consolidated[consolidated["category"].astype(str).str.contains("direct|utility", case=False, na=False)], ["finding_concept_id", "representative_feature", "evidence_quality", "representative_text"], top_n=15),
        "",
        "## Team Structure Findings",
        markdown_table(consolidated[consolidated["finding_concept_id"].astype(str).str.startswith("structure.")], ["finding_concept_id", "representative_feature", "evidence_quality", "representative_text"], top_n=15),
        "",
        "## Semantic Control Findings",
        markdown_table(consolidated[consolidated["finding_concept_id"].astype(str).str.startswith("semantic.")], ["finding_concept_id", "representative_feature", "evidence_quality", "representative_text"], top_n=15),
        "",
        "## Plant-Site Findings",
        markdown_table(consolidated[consolidated["category"].astype(str).str.contains("site", case=False, na=False)], ["finding_concept_id", "representative_feature", "evidence_quality", "representative_text"], top_n=15),
        "",
        "## A/B Pattern Findings",
        markdown_table(frames["hardened_cross_map_site_patterns"], ["feature_name", "mirage_direction", "inferno_direction", "same_nonflat_direction", "status"], top_n=20),
        "",
        "## Plant vs No-Plant Findings",
        markdown_table(consolidated[consolidated["category"].astype(str).eq("plant_progression")], ["finding_concept_id", "representative_feature", "evidence_quality", "representative_text"], top_n=15),
        "",
        "## Findings Downgraded by Exposure",
        markdown_table(frames["raw_finding_evidence"][frames["raw_finding_evidence"]["late_window_exposure_flag"].fillna(False)], ["finding_id", "finding_concept_id", "feature_name", "reference_exposure_share", "comparison_exposure_share", "exposure_sensitivity_status"], top_n=20),
        "",
        "## Findings Sensitive to One Demo",
        markdown_table(frames["finding_demo_sensitivity"][frames["finding_demo_sensitivity"]["demo_fragile"].fillna(False)], ["finding_id", "finding_concept_id", "demos_evaluated", "direction_flips", "status"], top_n=20),
        "",
        "## Findings Sensitive to Opponent",
        markdown_table(frames["finding_opponent_sensitivity"][frames["finding_opponent_sensitivity"]["single_opponent_dependency"].fillna(False)], ["finding_id", "finding_concept_id", "map_id", "dominant_opponent", "dominant_opponent_share", "status"], top_n=20),
        "",
        "## Contradictory Evidence",
        markdown_table(frames["tactical_finding_contradictions"], ["finding_concept_id", "conflicting_candidate_count", "severity", "requires_manual_review"], top_n=20),
        "",
        "## Excluded Comparisons",
        markdown_table(frames["finding_exclusion_audit"], ["feature_name", "hardened_exclusion_reason", "secondary_exclusion_reasons", "taxonomy_changed"], top_n=30),
        "",
        "## Modeling Context",
        markdown_table(frames["modeling_context_findings"], ["finding_concept_id", "representative_feature", "safe_as_modeling_context", "leakage_risk", "notes"], top_n=20),
        "",
        "## Sample Limitations",
        "The Inferno sample remains small and exploratory. Hardened findings are context for Stage 8.11, not automatic feature selection.",
        "",
        "## Readiness",
        f"`ready_for_stage_8_11 = {bool(audit.iloc[0].get('ready_for_stage_8_11'))}`.",
        "",
        "## Next Stage",
        "Stage 8.11 can run an Inferno A/B exploratory baseline if readiness remains true. This report does not start model training.",
        "",
    ]
    return "\n".join(sections)


def markdown_table(frame: pd.DataFrame, columns: list[str], top_n: int | None = None) -> str:
    return report_markdown_table(frame, columns, top_n=top_n)


def build_notebook() -> str:
    cells = [
        md("# Stage 8.10.1 -- Tactical Finding Hardening"),
        code("from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\nbase = Path('../data/gold/analysis/tactical_finding_hardening')"),
        code("audit = pd.read_parquet(base / 'tactical_finding_hardening_audit.parquet')\ndisplay(audit)"),
        code("raw = pd.read_parquet(base / 'raw_finding_evidence.parquet')\ngroups = pd.read_parquet(base / 'tactical_finding_groups.parquet')\nranked = pd.read_parquet(base / 'hardened_tactical_finding_ranking.parquet')\nprint({'raw': len(raw), 'concepts': groups['finding_concept_id'].nunique(), 'ranked': len(ranked)})"),
        code("groups['raw_candidate_count'].sort_values(ascending=False).head(20).plot(kind='bar', title='Candidates collapsed per concept')\nplt.tight_layout()"),
        code("ranked[['rank','finding_concept_id','representative_feature','evidence_quality','ranking_score']]"),
        code("ranked.plot.barh(x='finding_concept_id', y='ranking_score', title='Top consolidated findings')\nplt.gca().invert_yaxis()\nplt.tight_layout()"),
        code("exposure = raw[raw['late_window_exposure_flag']]\ndisplay(exposure[['finding_id','finding_concept_id','feature_name','reference_exposure_share','comparison_exposure_share']].head(20))"),
        code("demo = pd.read_parquet(base / 'finding_demo_sensitivity.parquet')\ndisplay(demo[demo['demo_fragile']].head(20))"),
        code("opponent = pd.read_parquet(base / 'finding_opponent_sensitivity.parquet')\ndisplay(opponent[opponent['single_opponent_dependency']].head(20))"),
        code("site = pd.read_parquet(base / 'hardened_cross_map_site_patterns.parquet')\ndisplay(site[['feature_name','mirage_direction','inferno_direction','same_nonflat_direction','status']].head(20))"),
        code("contradictions = pd.read_parquet(base / 'tactical_finding_contradictions.parquet')\ndisplay(contradictions[contradictions['requires_manual_review']].head(20))"),
        code("modeling = pd.read_parquet(base / 'modeling_context_findings.parquet')\ndisplay(modeling.head(20))"),
    ]
    return json.dumps(
        {
            "cells": cells,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 5,
        },
        indent=2,
    )


def md(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": [source]}


def code(source: str) -> dict[str, object]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [source]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate and harden Stage 8.10 tactical findings.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-team", required=True)
    parser.add_argument("--map", action="append", dest="maps", required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--hardening-config", type=Path)
    parser.add_argument("--map-registry", type=Path)
    args = parser.parse_args()
    configure_logging()
    outputs, _, summary = run_tactical_finding_hardening(
        config_path=args.config,
        target_team=args.target_team,
        map_names=args.maps,
        force=args.force,
        dry_run=args.dry_run,
        hardening_config=args.hardening_config,
        map_registry=args.map_registry,
    )
    print("Tactical finding hardening summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
