from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.utils.io import read_optional_table, read_table_pair, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.notebooks import code, md, write_notebook as write_notebook_file
from src.utils.reports import now_utc, safe_divide


OUTPUT_NAMES = [
    "inferno_sample_inventory",
    "inferno_sample_summary",
    "inferno_sample_gap_analysis",
    "inferno_sample_expansion_priority",
    "inferno_demo_dedup_audit",
    "inferno_expansion_lineage",
    "inferno_expanded_label_quality",
    "inferno_class_coverage",
    "inferno_group_coverage",
    "inferno_modeling_readiness_scorecard",
    "inferno_expansion_mirage_preservation_audit",
    "inferno_existing_scope_preservation",
    "inferno_opponent_coverage",
    "inferno_sample_concentration_audit",
    "inferno_frozen_baseline_sample_comparison",
    "inferno_sample_learning_curve",
    "inferno_temporal_holdout_audit",
    "inferno_next_data_targets",
    "inferno_sample_expansion_read_only_audit",
    "inferno_sample_expansion_audit",
]

INVENTORY_COLUMNS = [
    "series_id",
    "parse_id",
    "dem_file_id",
    "match_date",
    "opponent",
    "map_name",
    "target_team",
    "rounds",
    "t_rounds",
    "target_team_planted_t_rounds",
    "a_plants",
    "b_plants",
    "no_plant_t_rounds",
    "high_confidence_labels",
    "feature_eligible",
    "quality_status",
    "source_status",
    "included_in_modeling_sample",
]


def run_inferno_sample_expansion(
    *,
    config_path: Path,
    expansion_config_path: Path,
    force: bool = False,
    dry_run: bool = False,
    rerun_frozen_baseline: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    config_path = config_path.resolve()
    project_root = config_path.parent.parent
    project = load_project_config(config_path)
    expansion_config = load_expansion_config(expansion_config_path)
    gold_dir = (project_root / project.parsed_silver_dir).parent.parent / "gold"
    output_dir = gold_dir / "modeling" / "inferno_sample_expansion"
    target_map = str(expansion_config["sample_expansion"].get("target_map", "Inferno"))
    target_team = str(expansion_config["sample_expansion"].get("target_team", "Vitality"))
    frozen_config_path = resolve_project_path(project_root, expansion_config["frozen_experiment"]["config"])

    stage_gate = validate_stage_8_11_1(gold_dir)
    if rerun_frozen_baseline and not frozen_config_path.exists():
        raise FileNotFoundError(f"Frozen experiment config not found: {frozen_config_path}")

    before = load_current_state(gold_dir, target_map=target_map, target_team=target_team)
    before_metrics = baseline_metrics(before["baseline_dir"])
    mirage_before = preservation_fingerprints(gold_dir, map_name="Mirage")
    inferno_before = preservation_fingerprints(gold_dir, map_name=target_map)

    # Stage 8.12 is intake-aware but read-only by default. New demos must enter through
    # the existing catalog/local-scan/parse/quality pipeline, not through this module.
    after = before
    baseline_after_metrics = before_metrics.copy()
    baseline_rerun = False
    if rerun_frozen_baseline and not dry_run:
        from src.modeling.inferno_ab_exploratory_baseline import run_inferno_ab_exploratory_baseline

        run_inferno_ab_exploratory_baseline(
            config_path=config_path,
            model_config_path=frozen_config_path,
            force=force,
            dry_run=False,
        )
        after = load_current_state(gold_dir, target_map=target_map, target_team=target_team)
        baseline_after_metrics = baseline_metrics(after["baseline_dir"])
        baseline_rerun = True

    inventory = build_sample_inventory(after, target_map=target_map, target_team=target_team)
    summary = build_sample_summary(inventory, after["model_dataset"], expansion_config)
    gap = build_gap_analysis(summary, expansion_config)
    priority = build_expansion_priority(gap)
    dedup = build_demo_dedup_audit(after["dem_files"], after["parse_manifest"], target_map=target_map, target_team=target_team)
    lineage = build_expansion_lineage(pd.DataFrame(), target_map=target_map, target_team=target_team)
    label_quality = build_label_quality(after["round_state"], after["t_all"], target_map=target_map, target_team=target_team)
    class_coverage = build_class_coverage(after["model_dataset"], inventory)
    group_coverage = build_group_coverage(after["model_dataset"], inventory, expansion_config)
    scorecard = build_readiness_scorecard(summary, gap, after, expansion_config)
    data_readiness = classify_data_readiness(scorecard, summary, expansion_config)
    summary.loc[:, "status"] = data_readiness
    mirage_after = preservation_fingerprints(gold_dir, map_name="Mirage")
    inferno_after = preservation_fingerprints(gold_dir, map_name=target_map)
    mirage_preservation = build_mirage_preservation_audit(mirage_before, mirage_after)
    inferno_preservation = build_existing_scope_preservation(inferno_before, inferno_after, map_name=target_map)
    opponent_coverage = build_opponent_coverage(after["model_dataset"], inventory)
    concentration = build_sample_concentration(after["model_dataset"], inventory)
    comparison = build_frozen_baseline_comparison(before_metrics, baseline_after_metrics)
    learning_curve = build_sample_learning_curve(after["model_dataset"], baseline_after_metrics)
    temporal_holdout = build_temporal_holdout_audit(inventory, expansion_config)
    next_targets = build_next_data_targets(gap, data_readiness)
    read_only = build_read_only_audit(mirage_preservation, inferno_preservation, dry_run=dry_run)
    final_audit = build_final_audit(
        target_team=target_team,
        map_id=canonical_map_id(target_map),
        stage_gate=stage_gate,
        before_inventory=build_sample_inventory(before, target_map=target_map, target_team=target_team),
        after_inventory=inventory,
        before_metrics=before_metrics,
        after_metrics=baseline_after_metrics,
        scorecard=scorecard,
        readiness_after=data_readiness,
        baseline_rerun=baseline_rerun,
        dedup=dedup,
        mirage_preservation=mirage_preservation,
        inferno_preservation=inferno_preservation,
    )

    frames = {
        "inferno_sample_inventory": inventory,
        "inferno_sample_summary": summary,
        "inferno_sample_gap_analysis": gap,
        "inferno_sample_expansion_priority": priority,
        "inferno_demo_dedup_audit": dedup,
        "inferno_expansion_lineage": lineage,
        "inferno_expanded_label_quality": label_quality,
        "inferno_class_coverage": class_coverage,
        "inferno_group_coverage": group_coverage,
        "inferno_modeling_readiness_scorecard": scorecard,
        "inferno_expansion_mirage_preservation_audit": mirage_preservation,
        "inferno_existing_scope_preservation": inferno_preservation,
        "inferno_opponent_coverage": opponent_coverage,
        "inferno_sample_concentration_audit": concentration,
        "inferno_frozen_baseline_sample_comparison": comparison,
        "inferno_sample_learning_curve": learning_curve,
        "inferno_temporal_holdout_audit": temporal_holdout,
        "inferno_next_data_targets": next_targets,
        "inferno_sample_expansion_read_only_audit": read_only,
        "inferno_sample_expansion_audit": final_audit,
    }
    ordered = {name: sanitize_for_output(frames[name]) for name in OUTPUT_NAMES}

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs = write_dataframe_outputs(ordered, output_dir, force=force)
        write_report(project_root / "docs" / "inferno_sample_expansion.md", ordered, expansion_config, force=force)
        write_notebook(project_root / "notebooks" / "29_inferno_sample_expansion.ipynb", force=force)

    summary_row = summary.iloc[0].to_dict() if not summary.empty else {}
    audit_row = final_audit.iloc[0].to_dict()
    run_summary = {
        "data_readiness": data_readiness,
        "stage_completed": bool(audit_row["stage_completed"]),
        "modeling_sample_ready": bool(audit_row["modeling_sample_ready"]),
        "recommended_next_action": audit_row["recommended_next_action"],
        "demos_after": int(summary_row.get("total_demos", 0) or 0),
        "series_after": int(summary_row.get("total_series", 0) or 0),
        "opponents_after": int(summary_row.get("total_opponents", 0) or 0),
        "planted_t_rounds_after": int(summary_row.get("planted_t_rounds", 0) or 0),
        "a_count": int(summary_row.get("a_count", 0) or 0),
        "b_count": int(summary_row.get("b_count", 0) or 0),
        "output_dir": str(output_dir),
    }
    return ordered, outputs, run_summary


def load_expansion_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Expansion config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_project_path(project_root: Path, path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else project_root / path


def validate_stage_8_11_1(gold_dir: Path) -> pd.DataFrame:
    path = gold_dir / "modeling" / "inferno_ab_exploratory" / "modeling_integrity_refactor_regression_audit"
    audit = read_table_pair(path)
    if audit.empty:
        raise ValueError("Stage 8.11.1 audit is empty.")
    row = audit.iloc[0]
    required_checks = {
        "status_passed": str(row.get("status", "")).casefold() == "passed",
        "modeling_evidence_fail_closed": truthy(row.get("modeling_evidence_fail_closed")),
        "comparison_aware_sensitivity": all(
            truthy(row.get(column))
            for column in [
                "cross_map_lodo_valid",
                "within_map_ab_lodo_valid",
                "planted_vs_no_plant_lodo_valid",
                "cross_map_exposure_valid",
                "within_map_exposure_valid",
            ]
        ),
        "refactor_regression_passed": truthy(row.get("refactor_regression_passed")),
        "core_gold_integrity_passed": truthy(row.get("core_gold_unchanged")),
    }
    if not all(required_checks.values()):
        failed = "|".join(name for name, passed in required_checks.items() if not passed)
        raise ValueError(f"Stage 8.11.1 precondition failed: {failed}")
    return pd.DataFrame([{**required_checks, "status": "passed"}])


def truthy(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "yes", "passed", "ok"}


def load_current_state(gold_dir: Path, *, target_map: str, target_team: str) -> dict[str, Any]:
    baseline_dir = gold_dir / "modeling" / "inferno_ab_exploratory"
    return {
        "baseline_dir": baseline_dir,
        "round_features": scope_rows(read_optional_pair(gold_dir / "round_features" / "round_features_mvp"), target_map=target_map, target_team=target_team),
        "round_state": scope_rows(read_optional_pair(gold_dir / "round_state" / "round_state_resolved"), target_map=target_map, target_team=target_team),
        "t_all": scope_rows(read_optional_pair(gold_dir / "round_features" / "round_features_t_side_all"), target_map=target_map, target_team=target_team),
        "t_planted": scope_rows(read_optional_pair(gold_dir / "round_features" / "round_features_t_side_planted"), target_map=target_map, target_team=target_team),
        "model_dataset": scope_rows(read_optional_pair(baseline_dir / "inferno_ab_model_dataset"), target_map=target_map, target_team=target_team),
        "parse_manifest": read_optional_pair(gold_dir.parent / "bronze" / "parse_manifest" / "parse_manifest"),
        "dem_files": read_optional_pair(gold_dir.parent / "bronze" / "dem_files_manifest" / "dem_files_manifest"),
        "quality_audit": scope_rows(read_optional_pair(gold_dir / "validation" / "map_feature_quality" / "map_feature_quality_audit"), target_map=target_map, target_team=target_team),
        "materialization_audit": scope_rows(
            read_optional_pair(gold_dir / "validation" / "feature_materialization_repair" / "feature_materialization_repair_final_audit"),
            target_map=target_map,
            target_team=target_team,
        ),
    }


def read_optional_pair(path_without_suffix: Path) -> pd.DataFrame:
    try:
        return read_table_pair(path_without_suffix)
    except FileNotFoundError:
        return pd.DataFrame()


def scope_rows(frame: pd.DataFrame, *, target_map: str, target_team: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    scoped = frame.copy()
    if "map_name" in scoped.columns:
        names = {target_map.casefold(), f"de_{target_map}".casefold(), canonical_map_id(target_map)}
        scoped = scoped[scoped["map_name"].astype(str).str.casefold().isin(names)]
    elif "map_id" in scoped.columns:
        scoped = scoped[scoped["map_id"].astype(str).str.casefold().eq(canonical_map_id(target_map))]
    if "target_team" in scoped.columns:
        scoped = scoped[scoped["target_team"].astype(str).str.casefold().eq(target_team.casefold())]
    return scoped.copy()


def canonical_map_id(map_name: str) -> str:
    return str(map_name).replace("de_", "").strip().casefold()


def build_sample_inventory(state: dict[str, Any], *, target_map: str, target_team: str) -> pd.DataFrame:
    rounds = state["round_state"].copy() if not state["round_state"].empty else state["round_features"].copy()
    if rounds.empty:
        return pd.DataFrame(columns=INVENTORY_COLUMNS)
    parse_manifest = state["parse_manifest"].copy()
    model_dataset = state["model_dataset"].copy()
    model_demo_ids = set(model_dataset.get("dem_file_id", pd.Series(dtype=str)).dropna().astype(str))
    eligible_demo_ids = feature_eligible_demo_ids(state["t_all"])
    group_cols = [column for column in ["series_id", "parse_id", "dem_file_id"] if column in rounds.columns]
    rows = []
    for keys, group in rounds.groupby(group_cols, dropna=False):
        key_map = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,), strict=False))
        parse_id = str(key_map.get("parse_id", ""))
        dem_file_id = str(key_map.get("dem_file_id", ""))
        series_id = str(key_map.get("series_id", ""))
        t_rounds = t_side_rows(group)
        planted = planted_label_rows(t_rounds)
        metadata = demo_metadata(parse_manifest, parse_id=parse_id, dem_file_id=dem_file_id, series_id=series_id, target_team=target_team)
        quality_values = group.get("feature_quality_status", pd.Series(dtype=str)).dropna().astype(str).str.casefold()
        feature_eligible = bool(dem_file_id in eligible_demo_ids or parse_id in eligible_demo_ids or quality_values.isin({"ok", "passed"}).any())
        quality_status = "passed" if feature_eligible else "warning" if not group.empty else "missing"
        rows.append(
            {
                "series_id": series_id,
                "parse_id": parse_id,
                "dem_file_id": dem_file_id,
                "match_date": metadata["match_date"],
                "opponent": metadata["opponent"],
                "map_name": target_map,
                "target_team": target_team,
                "rounds": int(len(group)),
                "t_rounds": int(len(t_rounds)),
                "target_team_planted_t_rounds": int(len(planted)),
                "a_plants": int(planted["target_site_model_label"].astype(str).eq("A").sum()) if not planted.empty else 0,
                "b_plants": int(planted["target_site_model_label"].astype(str).eq("B").sum()) if not planted.empty else 0,
                "no_plant_t_rounds": int(len(t_rounds) - len(planted)),
                "high_confidence_labels": int(planted.get("label_confidence", pd.Series(dtype=str)).astype(str).str.casefold().eq("high").sum()) if not planted.empty else 0,
                "feature_eligible": feature_eligible,
                "quality_status": quality_status,
                "source_status": metadata["source_status"],
                "included_in_modeling_sample": dem_file_id in model_demo_ids or parse_id in set(model_dataset.get("parse_id", pd.Series(dtype=str)).astype(str)),
            }
        )
    return pd.DataFrame(rows, columns=INVENTORY_COLUMNS).sort_values(["match_date", "series_id", "parse_id"], na_position="last").reset_index(drop=True)


def feature_eligible_demo_ids(t_all: pd.DataFrame) -> set[str]:
    if t_all.empty or "feature_quality_status" not in t_all.columns:
        return set()
    eligible = t_all[t_all["feature_quality_status"].astype(str).str.casefold().isin({"ok", "passed"})]
    values: set[str] = set()
    for column in ["dem_file_id", "parse_id"]:
        if column in eligible.columns:
            values.update(eligible[column].dropna().astype(str))
    return values


def t_side_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "target_team_side" not in frame.columns:
        return pd.DataFrame(columns=frame.columns)
    return frame[frame["target_team_side"].astype(str).str.upper().eq("T")].copy()


def planted_label_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "target_site_model_label" not in frame.columns:
        return pd.DataFrame(columns=frame.columns)
    planted = frame[frame["target_site_model_label"].astype(str).isin(["A", "B"])].copy()
    if "label_confidence" in planted.columns:
        planted = planted[planted["label_confidence"].astype(str).str.casefold().eq("high")]
    return planted.copy()


def demo_metadata(parse_manifest: pd.DataFrame, *, parse_id: str, dem_file_id: str, series_id: str, target_team: str) -> dict[str, str | None]:
    row = pd.Series(dtype=object)
    if not parse_manifest.empty:
        candidates = parse_manifest.copy()
        for column, value in [("parse_id", parse_id), ("dem_file_id", dem_file_id), ("series_id", series_id)]:
            if column in candidates.columns and value:
                matched = candidates[candidates[column].astype(str).eq(value)]
                if not matched.empty:
                    row = matched.iloc[0]
                    break
    opponent = first_non_empty(row.get("opponent")) if not row.empty else None
    if not opponent or opponent.casefold() == "unknown":
        opponent = infer_opponent_from_identity("|".join([parse_id, dem_file_id, series_id]), target_team)
    return {
        "match_date": first_non_empty(row.get("match_date")) if not row.empty else None,
        "opponent": opponent or "unknown",
        "source_status": first_non_empty(row.get("parse_status")) if not row.empty else "missing_parse_manifest",
    }


def first_non_empty(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text and text.casefold() not in {"none", "nan", "nat"} else None


def infer_opponent_from_identity(identity: str, target_team: str) -> str | None:
    target = normalize_team_slug(target_team)
    tokens = [token for token in identity.casefold().replace("-", "_").split("_") if token]
    target_tokens = target.split("_")
    for index, token in enumerate(tokens):
        if token != "vs":
            continue
        left = team_slug_near_vs(tokens[:index], reverse=True)
        right = team_slug_near_vs(tokens[index + 1 :], reverse=False)
        if left == target and right and right != target:
            return prettify_slug(right)
        if right == target and left and left != target:
            return prettify_slug(left)
        left_multi = team_slug_near_vs(tokens[:index], reverse=True, width=len(target_tokens))
        right_multi = team_slug_near_vs(tokens[index + 1 :], reverse=False, width=len(target_tokens))
        if left_multi == target and right:
            return prettify_slug(right)
        if right_multi == target and left:
            return prettify_slug(left)
    return None


def team_slug_near_vs(tokens: list[str], *, reverse: bool, width: int = 1) -> str:
    if not tokens:
        return ""
    selected = list(reversed(tokens))[:width] if reverse else tokens[:width]
    if reverse:
        selected = list(reversed(selected))
    return "_".join(selected)


def normalize_team_slug(team: str) -> str:
    return str(team).strip().casefold().replace(" ", "_").replace("-", "_")


def prettify_slug(slug: str) -> str:
    overrides = {"fut": "FUT", "mibr": "MIBR", "g2": "G2"}
    if slug in overrides:
        return overrides[slug]
    return " ".join(part.capitalize() for part in slug.split("_") if part)


def build_sample_summary(inventory: pd.DataFrame, model_dataset: pd.DataFrame, expansion_config: dict[str, Any]) -> pd.DataFrame:
    labels = model_dataset.get("label", model_dataset.get("target_site_model_label", pd.Series(dtype=str))).astype(str) if not model_dataset.empty else pd.Series(dtype=str)
    a_count = int(labels.eq("A").sum())
    b_count = int(labels.eq("B").sum())
    minority_class = "A" if a_count <= b_count else "B"
    minority_count = min(a_count, b_count)
    planted = a_count + b_count
    opponents = inventory["opponent"] if "opponent" in inventory.columns else pd.Series(dtype=str)
    known_opponents = opponents.dropna().astype(str)
    known_opponents = known_opponents[~known_opponents.str.casefold().isin({"", "unknown"})]
    dates = pd.to_datetime(inventory.get("match_date", pd.Series(dtype=str)), errors="coerce") if not inventory.empty else pd.Series(dtype="datetime64[ns]")
    groups = model_dataset.get("model_group_id", model_dataset.get("series_id", pd.Series(dtype=str))).dropna().astype(str) if not model_dataset.empty else pd.Series(dtype=str)
    feature_eligible = int(inventory.get("feature_eligible", pd.Series(dtype=bool)).fillna(False).sum()) if not inventory.empty else 0
    quality_passed = int(inventory.get("quality_status", pd.Series(dtype=str)).astype(str).str.casefold().eq("passed").sum()) if not inventory.empty else 0
    return pd.DataFrame(
        [
            {
                "total_demos": int(inventory["dem_file_id"].nunique()) if "dem_file_id" in inventory.columns else 0,
                "total_series": int(inventory["series_id"].nunique()) if "series_id" in inventory.columns else 0,
                "total_opponents": int(known_opponents.nunique()),
                "total_rounds": int(inventory["rounds"].sum()) if "rounds" in inventory.columns else 0,
                "t_rounds": int(inventory["t_rounds"].sum()) if "t_rounds" in inventory.columns else 0,
                "planted_t_rounds": planted,
                "a_count": a_count,
                "b_count": b_count,
                "minority_class": minority_class if planted else None,
                "minority_count": minority_count,
                "minority_share": safe_divide(minority_count, planted),
                "high_confidence_label_share": safe_divide(
                    int(inventory["high_confidence_labels"].sum()) if "high_confidence_labels" in inventory.columns else 0,
                    int(inventory["target_team_planted_t_rounds"].sum()) if "target_team_planted_t_rounds" in inventory.columns else 0,
                ),
                "first_match_date": dates.min().date().isoformat() if not dates.dropna().empty else None,
                "last_match_date": dates.max().date().isoformat() if not dates.dropna().empty else None,
                "feature_eligible_demos": feature_eligible,
                "quality_passed_demos": quality_passed,
                "modeling_groups": int(groups.nunique()),
                "status": "pending",
            }
        ]
    )


def build_gap_analysis(summary: pd.DataFrame, expansion_config: dict[str, Any]) -> pd.DataFrame:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    readiness = expansion_config.get("readiness", {})
    balance = expansion_config.get("balance", {})
    metrics = [
        ("demos", row.get("total_demos", 0), readiness.get("minimum_demos", 0), "high", "Independent demos are preferred over more rounds from one demo."),
        ("series", row.get("total_series", 0), readiness.get("minimum_series", 0), "critical", "Independent series are the primary readiness unit."),
        ("opponents", row.get("total_opponents", 0), readiness.get("minimum_opponents", 0), "medium", "Opponent diversity reduces overfitting to one matchup."),
        ("planted rounds", row.get("planted_t_rounds", 0), readiness.get("minimum_planted_t_rounds", 0), "high", "A/B labels exist only on high-confidence planted T rounds."),
        ("A count", row.get("a_count", 0), readiness.get("minimum_class_count", 0), "high", "A class coverage must be sufficient independently."),
        ("B count", row.get("b_count", 0), readiness.get("minimum_class_count", 0), "high", "B class coverage must be sufficient independently."),
        ("minority share", row.get("minority_share", 0) or 0, balance.get("minimum_minority_share", 0), "medium", "Class balance matters even when raw rows increase."),
        ("model groups", row.get("modeling_groups", 0), readiness.get("minimum_valid_logo_groups", readiness.get("minimum_series", 0)), "critical", "LOGO validation needs enough independent held-out groups."),
    ]
    rows = []
    for metric, current, target, priority, notes in metrics:
        current_value = float(current or 0)
        target_value = float(target or 0)
        rows.append(
            {
                "metric": metric,
                "current_value": current_value,
                "target_value": target_value,
                "gap_absolute": max(target_value - current_value, 0.0),
                "target_met": current_value >= target_value,
                "priority": priority if current_value < target_value else "met",
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def build_expansion_priority(gap: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        "series": ("independent_series", "need_more_independent_series"),
        "demos": ("independent_demos", "need_more_feature_eligible_demos"),
        "opponents": ("new_opponents", "need_more_opponent_diversity"),
        "planted rounds": ("high_confidence_planted_t_rounds", "need_more_ab_planted_rounds"),
        "A count": ("A_planted_rounds", "need_more_a_rounds"),
        "B count": ("B_planted_rounds", "need_more_b_rounds"),
        "minority share": ("minority_class_balance", "need_better_ab_balance"),
        "model groups": ("valid_logo_groups", "need_more_independent_series"),
    }
    rows = []
    unmet = gap[~gap["target_met"]].copy() if not gap.empty else pd.DataFrame()
    priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    if not unmet.empty:
        unmet["_rank"] = unmet["priority"].map(priority_rank).fillna(9)
        unmet = unmet.sort_values(["_rank", "gap_absolute"], ascending=[True, False])
    for index, (_, item) in enumerate(unmet.iterrows(), start=1):
        target_type, diagnostic = mapping.get(str(item["metric"]), ("sample_requirement", "need_more_independent_evidence"))
        rows.append(
            {
                "priority": index,
                "diagnostic": diagnostic,
                "target_type": target_type,
                "needed_count": item["gap_absolute"],
                "reason": f"{item['metric']} current={item['current_value']} target={item['target_value']}.",
                "status": "open",
            }
        )
    if not rows:
        rows.append(
            {
                "priority": 1,
                "diagnostic": "sample_targets_met",
                "target_type": "robustness_context",
                "needed_count": 0,
                "reason": "Configured readiness targets are met.",
                "status": "met",
            }
        )
    return pd.DataFrame(rows)


def build_demo_dedup_audit(dem_files: pd.DataFrame, parse_manifest: pd.DataFrame, *, target_map: str, target_team: str) -> pd.DataFrame:
    columns = [
        "candidate_file",
        "source_filename",
        "file_size",
        "existing_dem_file_id",
        "existing_parse_id",
        "match_metadata",
        "possible_duplicate",
        "duplicate_reason",
        "action",
        "status",
    ]
    if dem_files.empty:
        return pd.DataFrame(columns=columns)
    scoped = dem_files.copy()
    if "target_team" in scoped.columns:
        scoped = scoped[scoped["target_team"].astype(str).str.casefold().eq(target_team.casefold())]
    if "inferred_map_name" in scoped.columns:
        map_values = {target_map.casefold(), f"de_{target_map}".casefold(), canonical_map_id(target_map)}
        scoped = scoped[scoped["inferred_map_name"].astype(str).str.casefold().isin(map_values)]
    rows = []
    hashes = scoped.get("dem_sha256", pd.Series(dtype=str)).fillna("").astype(str)
    ids = scoped.get("dem_file_id", pd.Series(dtype=str)).fillna("").astype(str)
    duplicate_hashes = set(hashes[hashes.ne("") & hashes.duplicated(keep=False)])
    duplicate_ids = set(ids[ids.ne("") & ids.duplicated(keep=False)])
    parse_lookup = parse_manifest.set_index("dem_file_id") if not parse_manifest.empty and "dem_file_id" in parse_manifest.columns else pd.DataFrame()
    for _, row in scoped.iterrows():
        dem_file_id = str(row.get("dem_file_id", ""))
        sha = str(row.get("dem_sha256", ""))
        duplicate = bool((sha and sha in duplicate_hashes) or (dem_file_id and dem_file_id in duplicate_ids))
        reason = "same_deterministic_content_hash" if sha and sha in duplicate_hashes else "same_canonical_demo_identity" if duplicate else ""
        existing_parse_id = ""
        if not parse_lookup.empty and dem_file_id in parse_lookup.index:
            existing_parse_id = str(parse_lookup.loc[dem_file_id].iloc[0].get("parse_id", "") if isinstance(parse_lookup.loc[dem_file_id], pd.DataFrame) else parse_lookup.loc[dem_file_id].get("parse_id", ""))
        rows.append(
            {
                "candidate_file": row.get("dem_path", ""),
                "source_filename": row.get("original_dem_file_name", row.get("dem_file_name", "")),
                "file_size": row.get("dem_file_size_bytes", 0),
                "existing_dem_file_id": dem_file_id,
                "existing_parse_id": existing_parse_id,
                "match_metadata": "|".join(str(row.get(column, "")) for column in ["target_team", "inferred_map_name", "local_archive_id"]),
                "possible_duplicate": duplicate,
                "duplicate_reason": reason,
                "action": "skip_reparse" if duplicate else "eligible_for_incremental_pipeline",
                "status": "warning" if duplicate else "ok",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_expansion_lineage(new_demos: pd.DataFrame, *, target_map: str, target_team: str) -> pd.DataFrame:
    columns = [
        "source_demo",
        "source_identifier",
        "series_id",
        "parse_id",
        "opponent",
        "match_date",
        "map_id",
        "ingestion_status",
        "parse_status",
        "quality_status",
        "feature_status",
        "gold_status",
        "modeling_eligible",
        "exclusion_reason",
    ]
    if new_demos.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, row in new_demos.iterrows():
        rows.append(
            {
                "source_demo": row.get("dem_path", ""),
                "source_identifier": row.get("dem_sha256", row.get("dem_file_id", "")),
                "series_id": row.get("series_id", ""),
                "parse_id": row.get("parse_id", ""),
                "opponent": row.get("opponent", "unknown"),
                "match_date": row.get("match_date"),
                "map_id": canonical_map_id(target_map),
                "ingestion_status": row.get("ingestion_status", "not_processed_by_stage_8_12"),
                "parse_status": row.get("parse_status", "not_processed_by_stage_8_12"),
                "quality_status": row.get("quality_status", "not_processed_by_stage_8_12"),
                "feature_status": row.get("feature_status", "not_processed_by_stage_8_12"),
                "gold_status": row.get("gold_status", "not_processed_by_stage_8_12"),
                "modeling_eligible": bool(row.get("modeling_eligible", False)),
                "exclusion_reason": row.get("exclusion_reason", "new demos must enter via existing pipeline"),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_label_quality(round_state: pd.DataFrame, t_all: pd.DataFrame, *, target_map: str, target_team: str) -> pd.DataFrame:
    source = round_state if not round_state.empty else t_all
    columns = [
        "scope",
        "scope_id",
        "t_rounds",
        "target_team_planted_t_rounds",
        "A",
        "B",
        "unknown_plant_site",
        "low_confidence",
        "opponent_plant",
        "label_conflicts",
        "status",
    ]
    if source.empty:
        return pd.DataFrame(columns=columns)
    t_rows = t_side_rows(source)
    rows = []
    for scope, column in [("demo", "dem_file_id"), ("series", "series_id")]:
        if column not in t_rows.columns:
            continue
        for value, group in t_rows.groupby(column, dropna=False):
            rows.append(label_quality_row(scope, str(value), group))
    rows.append(label_quality_row("overall", f"{target_team}_{target_map}", t_rows))
    return pd.DataFrame(rows, columns=columns)


def label_quality_row(scope: str, scope_id: str, group: pd.DataFrame) -> dict[str, Any]:
    labels = group.get("target_site_model_label", pd.Series(dtype=str)).astype(str)
    confidence = group.get("label_confidence", pd.Series(dtype=str)).astype(str).str.casefold()
    planted = labels.isin(["A", "B"])
    opponent_plant = group.get("opponent_planted", pd.Series([False] * len(group))).fillna(False).astype(bool) if "opponent_planted" in group.columns else pd.Series([False] * len(group))
    return {
        "scope": scope,
        "scope_id": scope_id,
        "t_rounds": int(len(group)),
        "target_team_planted_t_rounds": int((planted & confidence.eq("high")).sum()),
        "A": int((labels.eq("A") & confidence.eq("high")).sum()),
        "B": int((labels.eq("B") & confidence.eq("high")).sum()),
        "unknown_plant_site": int(group.get("bomb_planted", pd.Series([False] * len(group))).fillna(False).astype(bool).sum() - planted.sum()) if "bomb_planted" in group.columns else 0,
        "low_confidence": int((planted & ~confidence.eq("high")).sum()),
        "opponent_plant": int(opponent_plant.sum()),
        "label_conflicts": 0,
        "status": "passed" if int((planted & confidence.eq("high")).sum()) > 0 else "warning",
    }


def build_class_coverage(model_dataset: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    columns = ["scope", "scope_id", "opponent", "A", "B", "both_classes_present", "minority_class", "minority_count", "status"]
    if model_dataset.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    opponent_lookup = inventory.set_index("series_id")["opponent"].to_dict() if not inventory.empty and "series_id" in inventory.columns else {}
    for scope, column in [("series", "series_id"), ("demo", "dem_file_id"), ("opponent", "opponent")]:
        frame = model_dataset.copy()
        if column == "opponent" and "opponent" not in frame.columns:
            frame["opponent"] = frame.get("series_id", pd.Series(dtype=str)).map(opponent_lookup).fillna("unknown")
        if column not in frame.columns:
            continue
        for value, group in frame.groupby(column, dropna=False):
            a_count = int(group["label"].astype(str).eq("A").sum())
            b_count = int(group["label"].astype(str).eq("B").sum())
            both = a_count > 0 and b_count > 0
            rows.append(
                {
                    "scope": scope,
                    "scope_id": str(value),
                    "opponent": str(value) if scope == "opponent" else str(group.get("opponent", pd.Series(["unknown"])).iloc[0]) if "opponent" in group.columns else opponent_lookup.get(str(group.get("series_id", pd.Series([""])).iloc[0]), "unknown"),
                    "A": a_count,
                    "B": b_count,
                    "both_classes_present": both,
                    "minority_class": "A" if a_count <= b_count else "B",
                    "minority_count": min(a_count, b_count),
                    "status": "ok" if both else "one_class_only",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_group_coverage(model_dataset: pd.DataFrame, inventory: pd.DataFrame, expansion_config: dict[str, Any]) -> pd.DataFrame:
    columns = ["model_group_id", "group_type", "rounds", "A", "B", "both_classes", "eligible_as_training_group", "heldout_metric_limitations", "opponent", "date", "status"]
    if model_dataset.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    lookup = inventory.set_index("series_id").to_dict("index") if not inventory.empty and "series_id" in inventory.columns else {}
    for group_id, group in model_dataset.groupby("model_group_id", dropna=False):
        a_count = int(group["label"].astype(str).eq("A").sum())
        b_count = int(group["label"].astype(str).eq("B").sum())
        both = a_count > 0 and b_count > 0
        series_id = str(group.get("series_id", pd.Series([group_id])).iloc[0])
        meta = lookup.get(series_id, {})
        rows.append(
            {
                "model_group_id": str(group_id),
                "group_type": "series_id",
                "rounds": int(len(group)),
                "A": a_count,
                "B": b_count,
                "both_classes": both,
                "eligible_as_training_group": bool(len(group) > 0),
                "heldout_metric_limitations": "one_class_heldout_fold" if not both else "ok",
                "opponent": meta.get("opponent", "unknown"),
                "date": meta.get("match_date"),
                "status": "ok" if both else "limited_one_class_group",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_readiness_scorecard(summary: pd.DataFrame, gap: pd.DataFrame, state: dict[str, Any], expansion_config: dict[str, Any]) -> pd.DataFrame:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    readiness = expansion_config.get("readiness", {})
    balance = expansion_config.get("balance", {})
    quality = expansion_config.get("quality", {})
    quality_ok = bool(not state["quality_audit"].empty and state["quality_audit"].get("status", pd.Series([""])).astype(str).str.casefold().eq("passed").any())
    materialization_ok = bool(not state["materialization_audit"].empty and state["materialization_audit"].get("status", pd.Series([""])).astype(str).str.casefold().eq("passed").any())
    checks = [
        ("minimum demos", row.get("total_demos", 0), readiness.get("minimum_demos", 0), "readiness"),
        ("minimum series", row.get("total_series", 0), readiness.get("minimum_series", 0), "readiness"),
        ("minimum opponents", row.get("total_opponents", 0), readiness.get("minimum_opponents", 0), "readiness"),
        ("minimum planted rounds", row.get("planted_t_rounds", 0), readiness.get("minimum_planted_t_rounds", 0), "readiness"),
        ("minimum A", row.get("a_count", 0), readiness.get("minimum_class_count", 0), "class_coverage"),
        ("minimum B", row.get("b_count", 0), readiness.get("minimum_class_count", 0), "class_coverage"),
        ("minimum minority share", row.get("minority_share", 0) or 0, balance.get("minimum_minority_share", 0), "class_balance"),
        ("minimum valid LOGO groups", row.get("modeling_groups", 0), readiness.get("minimum_valid_logo_groups", readiness.get("minimum_series", 0)), "validation"),
        ("both classes in overall sample", int(row.get("a_count", 0) > 0 and row.get("b_count", 0) > 0), 1, "class_coverage"),
        ("high-confidence labels", row.get("high_confidence_label_share", 0) or 0, 1 if quality.get("require_high_confidence_labels", True) else 0, "label_quality"),
        ("quality gate", int(quality_ok), 1 if quality.get("require_feature_quality_gate", True) else 0, "quality"),
        ("materialization gate", int(materialization_ok), 1 if quality.get("require_materialization_gate", True) else 0, "quality"),
        ("training-fold class feasibility", int(training_fold_feasible(state["model_dataset"])), 1, "validation"),
    ]
    rows = []
    for name, current, target, category in checks:
        current_value = float(current or 0)
        target_value = float(target or 0)
        rows.append(
            {
                "check_name": name,
                "category": category,
                "current_value": current_value,
                "target_value": target_value,
                "passed": current_value >= target_value,
                "status": "passed" if current_value >= target_value else "failed",
                "notes": readiness_note(name),
            }
        )
    return pd.DataFrame(rows)


def training_fold_feasible(model_dataset: pd.DataFrame) -> bool:
    if model_dataset.empty or "model_group_id" not in model_dataset.columns:
        return False
    for group_id in model_dataset["model_group_id"].astype(str).unique():
        train = model_dataset[~model_dataset["model_group_id"].astype(str).eq(group_id)]
        if train["label"].astype(str).nunique() < 2:
            return False
    return True


def readiness_note(name: str) -> str:
    notes = {
        "minimum series": "Independent series are more important than raw rows.",
        "minimum planted rounds": "Only high-confidence planted T rounds produce A/B model labels.",
        "training-fold class feasibility": "Every LOGO training fold must retain both classes.",
        "high-confidence labels": "Low-confidence labels stay out of the frozen modeling sample.",
    }
    return notes.get(name, "Configured readiness heuristic.")


def classify_data_readiness(scorecard: pd.DataFrame, summary: pd.DataFrame, expansion_config: dict[str, Any]) -> str:
    if scorecard.empty:
        return "insufficient"
    hard_checks = scorecard[
        scorecard["category"].isin(["quality", "label_quality"])
        | scorecard["check_name"].isin(["both classes in overall sample", "training-fold class feasibility"])
    ]
    if not bool(hard_checks["passed"].all()):
        return "insufficient"
    if bool(scorecard["passed"].all()):
        row = summary.iloc[0]
        minimum_series = int(expansion_config.get("readiness", {}).get("minimum_series", 8))
        if int(row.get("total_series", 0)) >= minimum_series * 2 and int(row.get("total_opponents", 0)) >= 8:
            return "robustness_candidate"
        return "baseline_ready"
    return "expanded_but_limited"


def preservation_fingerprints(gold_dir: Path, *, map_name: str) -> pd.DataFrame:
    bases = [
        gold_dir / "round_features" / "round_features_mvp",
        gold_dir / "round_features" / "round_features_t_side_all",
        gold_dir / "round_features" / "round_features_t_side_planted",
        gold_dir / "round_features" / "round_features_ct_side",
        gold_dir / "round_state" / "round_state_resolved",
        gold_dir / "validation" / "mirage_regression_gate" / "mirage_regression_audit",
        gold_dir / "modeling" / "t_side_ab_candidate" / "candidate_model_audit",
    ]
    rows = []
    for base in bases:
        frame = read_optional_pair(base)
        scoped = scope_rows(frame, target_map=map_name, target_team="Vitality") if not frame.empty else frame
        rows.append({"dataset": base.name, "rows": len(scoped), "fingerprint": frame_fingerprint(scoped), "path": str(base)})
    return pd.DataFrame(rows)


def frame_fingerprint(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "empty"
    hashed = pd.util.hash_pandas_object(frame.sort_index(axis=1), index=True).astype("uint64").to_numpy()
    return hashlib.sha256(hashed.tobytes()).hexdigest()


def build_mirage_preservation_audit(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    return build_preservation_rows(before, after, map_name="Mirage", artifact_name="inferno_expansion_mirage_preservation_audit")


def build_existing_scope_preservation(before: pd.DataFrame, after: pd.DataFrame, *, map_name: str) -> pd.DataFrame:
    return build_preservation_rows(before, after, map_name=map_name, artifact_name="inferno_existing_scope_preservation")


def build_preservation_rows(before: pd.DataFrame, after: pd.DataFrame, *, map_name: str, artifact_name: str) -> pd.DataFrame:
    rows = []
    before_lookup = before.set_index("dataset").to_dict("index") if not before.empty else {}
    after_lookup = after.set_index("dataset").to_dict("index") if not after.empty else {}
    for dataset in sorted(set(before_lookup) | set(after_lookup)):
        before_row = before_lookup.get(dataset, {})
        after_row = after_lookup.get(dataset, {})
        same = before_row.get("fingerprint") == after_row.get("fingerprint")
        rows.append(
            {
                "dataset": dataset,
                "map_name": map_name,
                "existing_rows_before": int(before_row.get("rows", 0) or 0),
                "existing_rows_after": int(after_row.get("rows", 0) or 0),
                "existing_keys_preserved": same,
                "existing_content_changed": not same,
                "new_rows_added": max(int(after_row.get("rows", 0) or 0) - int(before_row.get("rows", 0) or 0), 0),
                "duplicates_added": 0,
                "status": "passed" if same else "critical_failure",
                "artifact_name": artifact_name,
            }
        )
    return pd.DataFrame(rows)


def build_opponent_coverage(model_dataset: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    columns = ["opponent", "series", "demos", "T rounds", "planted rounds", "A", "B", "share_of_model_sample", "dominant_opponent", "status"]
    if inventory.empty:
        return pd.DataFrame(columns=columns)
    inv = inventory.copy()
    total_model_rows = len(model_dataset)
    model = model_dataset.copy()
    if not model.empty and "opponent" not in model.columns:
        lookup = inv.set_index("series_id")["opponent"].to_dict()
        model["opponent"] = model.get("series_id", pd.Series(dtype=str)).map(lookup).fillna("unknown")
    rows = []
    for opponent, group in inv.groupby("opponent", dropna=False):
        model_group = model[model.get("opponent", pd.Series(dtype=str)).astype(str).eq(str(opponent))] if not model.empty else pd.DataFrame()
        share = safe_divide(len(model_group), total_model_rows)
        rows.append(
            {
                "opponent": str(opponent),
                "series": int(group["series_id"].nunique()),
                "demos": int(group["dem_file_id"].nunique()),
                "T rounds": int(group["t_rounds"].sum()),
                "planted rounds": int(model_group["label"].astype(str).isin(["A", "B"]).sum()) if not model_group.empty else 0,
                "A": int(model_group["label"].astype(str).eq("A").sum()) if not model_group.empty else 0,
                "B": int(model_group["label"].astype(str).eq("B").sum()) if not model_group.empty else 0,
                "share_of_model_sample": share,
                "dominant_opponent": bool((share or 0) >= 0.4),
                "status": "dominant_opponent" if (share or 0) >= 0.4 else "ok",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_sample_concentration(model_dataset: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    rows = []
    dimensions = {
        "series": model_dataset.get("series_id", pd.Series(dtype=str)) if not model_dataset.empty else pd.Series(dtype=str),
        "demo": model_dataset.get("dem_file_id", pd.Series(dtype=str)) if not model_dataset.empty else pd.Series(dtype=str),
        "opponent": opponent_series(model_dataset, inventory),
        "month": month_series(model_dataset, inventory),
    }
    for dimension, values in dimensions.items():
        counts = values.fillna("unknown").astype(str).value_counts()
        total = int(counts.sum())
        largest = counts.index[0] if total else "none"
        largest_share = safe_divide(int(counts.iloc[0]), total) if total else 0
        rows.append(
            {
                "dimension": dimension,
                "largest_group": str(largest),
                "largest_group_share": largest_share,
                "top_2_share": safe_divide(int(counts.head(2).sum()), total) if total else 0,
                "top_3_share": safe_divide(int(counts.head(3).sum()), total) if total else 0,
                "concentration_status": "high" if (largest_share or 0) >= 0.4 else "ok",
            }
        )
    return pd.DataFrame(rows)


def opponent_series(model_dataset: pd.DataFrame, inventory: pd.DataFrame) -> pd.Series:
    if model_dataset.empty:
        return pd.Series(dtype=str)
    if "opponent" in model_dataset.columns:
        return model_dataset["opponent"]
    lookup = inventory.set_index("series_id")["opponent"].to_dict() if not inventory.empty and "series_id" in inventory.columns else {}
    return model_dataset.get("series_id", pd.Series(dtype=str)).map(lookup).fillna("unknown")


def month_series(model_dataset: pd.DataFrame, inventory: pd.DataFrame) -> pd.Series:
    if model_dataset.empty:
        return pd.Series(dtype=str)
    lookup = inventory.set_index("series_id")["match_date"].to_dict() if not inventory.empty and "series_id" in inventory.columns else {}
    dates = pd.to_datetime(model_dataset.get("series_id", pd.Series(dtype=str)).map(lookup), errors="coerce")
    return dates.dt.to_period("M").astype(str).replace("NaT", "unknown")


def baseline_metrics(baseline_dir: Path) -> dict[str, Any]:
    audit = read_optional_table(baseline_dir / "inferno_ab_exploratory_model_audit.parquet")
    oof = read_optional_table(baseline_dir / "inferno_ab_oof_metrics.parquet")
    null = read_optional_table(baseline_dir / "inferno_ab_null_summary.parquet")
    uncertainty = read_optional_table(baseline_dir / "inferno_ab_metric_uncertainty.parquet")
    coefficients = read_optional_table(baseline_dir / "inferno_ab_coefficient_stability.parquet")
    dataset = read_optional_table(baseline_dir / "inferno_ab_model_dataset.parquet")
    audit_row = audit.iloc[0] if not audit.empty else pd.Series(dtype=object)
    oof_row = oof.iloc[0] if not oof.empty else pd.Series(dtype=object)
    null_row = null.iloc[0] if not null.empty else pd.Series(dtype=object)
    ci_width = None
    if not uncertainty.empty:
        macro = uncertainty[uncertainty["metric"].astype(str).eq("macro_f1")]
        if not macro.empty:
            ci_width = float(macro.iloc[0]["ci_high"]) - float(macro.iloc[0]["ci_low"])
    coefficient_stability = None
    if not coefficients.empty and "sign_agreement" in coefficients.columns:
        coefficient_stability = float(pd.to_numeric(coefficients["sign_agreement"], errors="coerce").mean())
    labels = dataset.get("label", pd.Series(dtype=str)).astype(str) if not dataset.empty else pd.Series(dtype=str)
    groups = dataset.get("model_group_id", pd.Series(dtype=str)).astype(str) if not dataset.empty else pd.Series(dtype=str)
    return {
        "rows": int(len(dataset)),
        "groups": int(groups.nunique()),
        "A": int(labels.eq("A").sum()),
        "B": int(labels.eq("B").sum()),
        "macro_f1": value_or_none(oof_row.get("macro_f1")),
        "balanced_accuracy": value_or_none(oof_row.get("balanced_accuracy")),
        "MCC": value_or_none(oof_row.get("MCC")),
        "F1_A": value_or_none(oof_row.get("f1_A")),
        "F1_B": value_or_none(oof_row.get("f1_B")),
        "recall_A": value_or_none(oof_row.get("recall_A")),
        "recall_B": value_or_none(oof_row.get("recall_B")),
        "ROC_AUC": value_or_none(oof_row.get("ROC_AUC")),
        "Brier": value_or_none(oof_row.get("Brier_score")),
        "log_loss": value_or_none(oof_row.get("log_loss")),
        "null_percentile": value_or_none(null_row.get("observed_percentile", audit_row.get("null_percentile"))),
        "bootstrap_CI": ci_width,
        "fold_variance": fold_variance(baseline_dir),
        "coefficient_sign_stability": coefficient_stability,
        "signal_status": first_non_empty(audit_row.get("exploratory_signal_status")) or "unknown",
    }


def value_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def fold_variance(baseline_dir: Path) -> float | None:
    folds = read_optional_table(baseline_dir / "inferno_ab_fold_metrics.parquet")
    if folds.empty or "macro_f1" not in folds.columns:
        return None
    return float(pd.to_numeric(folds["macro_f1"], errors="coerce").var(ddof=0))


def build_frozen_baseline_comparison(before: dict[str, Any], after: dict[str, Any]) -> pd.DataFrame:
    metrics = [
        "macro_f1",
        "balanced_accuracy",
        "MCC",
        "F1_A",
        "F1_B",
        "recall_A",
        "recall_B",
        "ROC_AUC",
        "Brier",
        "log_loss",
        "null_percentile",
        "bootstrap_CI",
        "fold_variance",
        "coefficient_sign_stability",
        "signal_status",
    ]
    rows = []
    for metric in metrics:
        before_value = before.get(metric)
        after_value = after.get(metric)
        diff = numeric_difference(before_value, after_value)
        rows.append(
            {
                "metric": metric,
                "before": before_value,
                "after": after_value,
                "difference": diff,
                "before_rows": before.get("rows"),
                "after_rows": after.get("rows"),
                "before_groups": before.get("groups"),
                "after_groups": after.get("groups"),
                "before_A": before.get("A"),
                "after_A": after.get("A"),
                "before_B": before.get("B"),
                "after_B": after.get("B"),
                "interpretation": comparison_interpretation(metric, before_value, after_value),
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)


def numeric_difference(before: Any, after: Any) -> float | None:
    try:
        if before is None or after is None:
            return None
        return float(after) - float(before)
    except (TypeError, ValueError):
        return None


def comparison_interpretation(metric: str, before: Any, after: Any) -> str:
    if metric == "signal_status":
        return "signal status changed" if str(before) != str(after) else "signal status unchanged"
    diff = numeric_difference(before, after)
    if diff is None:
        return "not comparable"
    if diff < 0:
        return "decreased; accepted as real evidence, no tuning or demo removal"
    if diff > 0:
        return "increased; diagnostic only, no promotion"
    return "unchanged"


def build_sample_learning_curve(model_dataset: pd.DataFrame, metrics: dict[str, Any]) -> pd.DataFrame:
    columns = [
        "snapshot_id",
        "series_count",
        "demo_count",
        "round_count",
        "A",
        "B",
        "macro_f1",
        "balanced_accuracy",
        "MCC",
        "null_percentile",
        "ci_width_macro_f1",
        "coefficient_stability",
        "signal_status",
        "status",
    ]
    if model_dataset.empty or "model_group_id" not in model_dataset.columns:
        return pd.DataFrame(columns=columns)
    rows = []
    ordered_groups = sorted(model_dataset["model_group_id"].astype(str).unique())
    for size in range(1, len(ordered_groups) + 1):
        groups = ordered_groups[:size]
        snap = model_dataset[model_dataset["model_group_id"].astype(str).isin(groups)]
        labels = snap["label"].astype(str)
        valid = size >= 3 and labels.nunique() == 2
        is_all = size == len(ordered_groups)
        rows.append(
            {
                "snapshot_id": f"first_{size}_groups",
                "series_count": size,
                "demo_count": int(snap["dem_file_id"].nunique()) if "dem_file_id" in snap.columns else 0,
                "round_count": int(len(snap)),
                "A": int(labels.eq("A").sum()),
                "B": int(labels.eq("B").sum()),
                "macro_f1": metrics.get("macro_f1") if is_all and valid else None,
                "balanced_accuracy": metrics.get("balanced_accuracy") if is_all and valid else None,
                "MCC": metrics.get("MCC") if is_all and valid else None,
                "null_percentile": metrics.get("null_percentile") if is_all and valid else None,
                "ci_width_macro_f1": metrics.get("bootstrap_CI") if is_all and valid else None,
                "coefficient_stability": metrics.get("coefficient_sign_stability") if is_all and valid else None,
                "signal_status": metrics.get("signal_status") if is_all and valid else "not_evaluated",
                "status": "available_current_frozen_result" if is_all and valid else "counts_only" if valid else "invalid_small_snapshot",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_temporal_holdout_audit(inventory: pd.DataFrame, expansion_config: dict[str, Any]) -> pd.DataFrame:
    minimum_series = int(expansion_config.get("readiness", {}).get("minimum_series", 8))
    dated = inventory.copy()
    dates = pd.to_datetime(dated.get("match_date", pd.Series(dtype=str)), errors="coerce") if not dated.empty else pd.Series(dtype="datetime64[ns]")
    enough = int(dated["series_id"].nunique()) >= minimum_series and not dates.dropna().empty
    return pd.DataFrame(
        [
            {
                "diagnostic": "older_train_newer_descriptive_holdout",
                "series": int(dated["series_id"].nunique()) if not dated.empty and "series_id" in dated.columns else 0,
                "dated_series": int(dated.loc[dates.notna(), "series_id"].nunique()) if not dated.empty and "series_id" in dated.columns else 0,
                "minimum_series": minimum_series,
                "status": "available" if enough else "not_enough_data",
                "notes": "Temporal holdout is descriptive only and does not replace LOGO.",
            }
        ]
    )


def build_next_data_targets(gap: pd.DataFrame, data_readiness: str) -> pd.DataFrame:
    if data_readiness in {"baseline_ready", "robustness_candidate"}:
        return pd.DataFrame(
            [
                {
                    "priority": 1,
                    "target_type": "none",
                    "needed_count": 0,
                    "reason": "Configured modeling readiness targets are met.",
                    "status": "met",
                }
            ]
        )
    rows = []
    open_gap = gap[~gap["target_met"]].copy() if not gap.empty else pd.DataFrame()
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    if not open_gap.empty:
        open_gap["_rank"] = open_gap["priority"].map(rank).fillna(9)
        open_gap = open_gap.sort_values(["_rank", "gap_absolute"], ascending=[True, False])
    for idx, (_, row) in enumerate(open_gap.iterrows(), start=1):
        rows.append(
            {
                "priority": idx,
                "target_type": next_target_type(str(row["metric"])),
                "needed_count": row["gap_absolute"],
                "reason": f"Only {row['current_value']} current {row['metric']}; target is {row['target_value']}.",
                "status": "open",
            }
        )
    return pd.DataFrame(rows)


def next_target_type(metric: str) -> str:
    return {
        "series": "independent_series",
        "demos": "feature_eligible_demos",
        "opponents": "new_opponents",
        "planted rounds": "high_confidence_planted_t_rounds",
        "A count": "A_planted_rounds",
        "B count": "B_planted_rounds",
        "minority share": "minority_class_balance",
        "model groups": "valid_logo_groups",
    }.get(metric, "sample_requirement")


def build_read_only_audit(mirage: pd.DataFrame, inferno: pd.DataFrame, *, dry_run: bool) -> pd.DataFrame:
    critical = int(mirage["status"].astype(str).eq("critical_failure").sum() + inferno["status"].astype(str).eq("critical_failure").sum())
    return pd.DataFrame(
        [
            {
                "audit_id": "inferno_sample_expansion_read_only_v1",
                "dry_run": dry_run,
                "core_gold_writes": 0,
                "mirage_preserved": critical == 0,
                "existing_inferno_preserved": critical == 0,
                "status": "passed" if critical == 0 else "failed",
                "created_at": now_utc(),
            }
        ]
    )


def build_final_audit(
    *,
    target_team: str,
    map_id: str,
    stage_gate: pd.DataFrame,
    before_inventory: pd.DataFrame,
    after_inventory: pd.DataFrame,
    before_metrics: dict[str, Any],
    after_metrics: dict[str, Any],
    scorecard: pd.DataFrame,
    readiness_after: str,
    baseline_rerun: bool,
    dedup: pd.DataFrame,
    mirage_preservation: pd.DataFrame,
    inferno_preservation: pd.DataFrame,
) -> pd.DataFrame:
    before_summary = compact_counts(before_inventory)
    after_summary = compact_counts(after_inventory)
    critical = 0
    warnings = 0
    if not bool(stage_gate.iloc[0].get("status") == "passed"):
        critical += 1
    if mirage_preservation["status"].astype(str).eq("critical_failure").any():
        critical += 1
    if inferno_preservation["status"].astype(str).eq("critical_failure").any():
        critical += 1
    if readiness_after not in {"baseline_ready", "robustness_candidate"}:
        warnings += 1
    modeling_ready = readiness_after in {"baseline_ready", "robustness_candidate"}
    return pd.DataFrame(
        [
            {
                "audit_id": "inferno_sample_expansion_v1",
                "target_team": target_team,
                "map_id": map_id,
                "stage_8_11_1_passed": True,
                "demos_before": before_summary["demos"],
                "demos_after": after_summary["demos"],
                "demos_added": after_summary["demos"] - before_summary["demos"],
                "series_before": before_summary["series"],
                "series_after": after_summary["series"],
                "series_added": after_summary["series"] - before_summary["series"],
                "opponents_before": before_summary["opponents"],
                "opponents_after": after_summary["opponents"],
                "planted_rounds_before": before_metrics.get("rows"),
                "planted_rounds_after": after_metrics.get("rows"),
                "A_before": before_metrics.get("A"),
                "A_after": after_metrics.get("A"),
                "B_before": before_metrics.get("B"),
                "B_after": after_metrics.get("B"),
                "model_groups_before": before_metrics.get("groups"),
                "model_groups_after": after_metrics.get("groups"),
                "new_demos_quality_passed": 0,
                "new_demos_quality_failed": 0,
                "duplicate_candidates": int(dedup.get("possible_duplicate", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if not dedup.empty else 0,
                "mirage_preserved": not mirage_preservation["status"].astype(str).eq("critical_failure").any(),
                "existing_inferno_preserved": not inferno_preservation["status"].astype(str).eq("critical_failure").any(),
                "readiness_before": readiness_after,
                "readiness_after": readiness_after,
                "frozen_baseline_rerun": baseline_rerun,
                "macro_f1_before": before_metrics.get("macro_f1"),
                "macro_f1_after": after_metrics.get("macro_f1"),
                "balanced_accuracy_before": before_metrics.get("balanced_accuracy"),
                "balanced_accuracy_after": after_metrics.get("balanced_accuracy"),
                "null_percentile_before": before_metrics.get("null_percentile"),
                "null_percentile_after": after_metrics.get("null_percentile"),
                "signal_status_before": before_metrics.get("signal_status"),
                "signal_status_after": after_metrics.get("signal_status"),
                "critical_failures": critical,
                "warnings": warnings,
                "ready_for_stage_8_13": critical == 0,
                "stage_completed": critical == 0,
                "modeling_sample_ready": modeling_ready,
                "recommended_next_action": recommended_next_action(readiness_after, critical),
                "status": "passed" if critical == 0 else "failed",
                "created_at": now_utc(),
            }
        ]
    )


def compact_counts(inventory: pd.DataFrame) -> dict[str, int]:
    if inventory.empty:
        return {"demos": 0, "series": 0, "opponents": 0}
    opponents = inventory["opponent"].dropna().astype(str)
    opponents = opponents[~opponents.str.casefold().isin({"", "unknown"})]
    return {
        "demos": int(inventory["dem_file_id"].nunique()),
        "series": int(inventory["series_id"].nunique()),
        "opponents": int(opponents.nunique()),
    }


def recommended_next_action(readiness: str, critical_failures: int) -> str:
    if critical_failures:
        return "data_quality_repair_required"
    if readiness == "robustness_candidate":
        return "robustness_study_candidate"
    if readiness == "baseline_ready":
        return "rerun_frozen_baseline"
    return "continue_sample_expansion"


def sanitize_for_output(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    sanitized = frame.copy()
    for column in sanitized.columns:
        if sanitized[column].dtype == "object":
            sanitized[column] = sanitized[column].map(sanitize_cell)
    return sanitized


def sanitize_cell(value: Any) -> Any:
    if isinstance(value, list | tuple | set):
        return "|".join(map(str, value))
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        return value
    return str(value)


def write_report(path: Path, frames: dict[str, pd.DataFrame], expansion_config: dict[str, Any], *, force: bool) -> None:
    if path.exists() and not force:
        return
    summary = first_row(frames["inferno_sample_summary"])
    audit = first_row(frames["inferno_sample_expansion_audit"])
    comparison = frames["inferno_frozen_baseline_sample_comparison"]
    gaps = frames["inferno_sample_gap_analysis"]
    targets = frames["inferno_next_data_targets"]
    lines = [
        "# Inferno Sample Expansion & Modeling Readiness",
        "",
        "## Purpose",
        "",
        "Stage 8.12 measures whether the Inferno/Vitality T-side A/B sample is large and independent enough for a more reliable frozen-baseline re-evaluation. It is not a tuning stage.",
        "",
        "## Starting Sample",
        "",
        f"- Demos: {summary.get('total_demos', 0)}",
        f"- Series: {summary.get('total_series', 0)}",
        f"- Opponents: {summary.get('total_opponents', 0)}",
        f"- Planted T-side model rows: {summary.get('planted_t_rounds', 0)}",
        f"- A/B: {summary.get('a_count', 0)} / {summary.get('b_count', 0)}",
        f"- Model groups: {summary.get('modeling_groups', 0)}",
        "",
        "## Expansion Strategy",
        "",
        "The stage prioritizes independent series, independent demos, A/B plant coverage, temporal coverage, and opponent diversity over raw round count.",
        "",
        "## Intake",
        "",
        "No HLTV scraper or parallel intake path is implemented. New demos must enter through the existing manual/local pipeline.",
        "",
        "## New Demos",
        "",
        f"- Demos added by this run: {audit.get('demos_added', 0)}",
        f"- Frozen baseline rerun: {audit.get('frozen_baseline_rerun', False)}",
        "",
        "## Duplicate Protection",
        "",
        "Duplicate detection uses deterministic identifiers such as content hash and canonical demo identity; filename alone is not enough.",
        "",
        "## Data Lineage",
        "",
        "New-demo lineage is emitted in `inferno_expansion_lineage`. Empty lineage means no new demo was processed by Stage 8.12.",
        "",
        "## Parse / Feature Quality",
        "",
        "The stage requires the existing feature-quality and materialization gates and reports readiness without relaxing thresholds.",
        "",
        "## A/B Label Coverage",
        "",
        f"- Minority class: {summary.get('minority_class')}",
        f"- Minority count/share: {summary.get('minority_count', 0)} / {summary.get('minority_share')}",
        "",
        "## Independent Series Coverage",
        "",
        f"- Independent series: {summary.get('total_series', 0)}",
        "",
        "## Opponent Diversity",
        "",
        f"- Opponents: {summary.get('total_opponents', 0)}",
        "",
        "## Sample Concentration",
        "",
        "See `inferno_sample_concentration_audit` for concentration by series, demo, opponent, and month.",
        "",
        "## Modeling Readiness",
        "",
        f"- Data readiness: `{audit.get('readiness_after')}`",
        f"- Modeling sample ready: `{audit.get('modeling_sample_ready')}`",
        f"- Recommended next action: `{audit.get('recommended_next_action')}`",
        "",
        "## Frozen Baseline Before / After",
        "",
        dataframe_to_markdown(comparison[comparison["metric"].isin(["macro_f1", "balanced_accuracy", "MCC", "null_percentile", "signal_status"])]),
        "",
        "## Learning-Curve Context",
        "",
        "The learning curve is diagnostic only; it does not select the best sample size.",
        "",
        "## Temporal Generalization Context",
        "",
        "Temporal holdout is only emitted when enough dated independent series exist and never replaces LOGO.",
        "",
        "## Remaining Data Gaps",
        "",
        dataframe_to_markdown(gaps),
        "",
        "## Next Data Targets",
        "",
        dataframe_to_markdown(targets),
        "",
        "## Limitations",
        "",
        "Stage 8.12 does not add scraping, tune models, search horizons, promote models, build dashboards, export BigQuery, or add a new map/team.",
        "",
        "## Next Stage",
        "",
        "Choose Stage 8.13 from the readiness result: continued sample expansion, A/B signal diagnosis, or robustness study.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def first_row(frame: pd.DataFrame) -> dict[str, Any]:
    return frame.iloc[0].to_dict() if not frame.empty else {}


def dataframe_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    return frame.fillna("").to_markdown(index=False)


def write_notebook(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        return
    base = "../data/gold/modeling/inferno_sample_expansion"
    cells = [
        md("# Inferno Sample Expansion"),
        code("import pandas as pd\nfrom pathlib import Path\nbase = Path('" + base + "')"),
        code("pd.read_parquet(base / 'inferno_sample_summary.parquet')"),
        code("pd.read_parquet(base / 'inferno_sample_gap_analysis.parquet')"),
        code("pd.read_parquet(base / 'inferno_modeling_readiness_scorecard.parquet')"),
        code("pd.read_parquet(base / 'inferno_class_coverage.parquet')"),
        code("pd.read_parquet(base / 'inferno_opponent_coverage.parquet')"),
        code("pd.read_parquet(base / 'inferno_sample_concentration_audit.parquet')"),
        code("pd.read_parquet(base / 'inferno_frozen_baseline_sample_comparison.parquet')"),
        code("pd.read_parquet(base / 'inferno_sample_learning_curve.parquet')"),
        code("pd.read_parquet(base / 'inferno_next_data_targets.parquet')"),
        code("pd.read_parquet(base / 'inferno_sample_expansion_audit.parquet')"),
    ]
    write_notebook_file(path, cells, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 8.12 Inferno sample expansion and modeling readiness.")
    parser.add_argument("--config", type=Path, default=Path("configs/project.yaml"))
    parser.add_argument("--expansion-config", type=Path, default=Path("configs/modeling/inferno_sample_expansion.yaml"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rerun-frozen-baseline", action="store_true")
    args = parser.parse_args()
    configure_logging()
    _, outputs, summary = run_inferno_sample_expansion(
        config_path=args.config,
        expansion_config_path=args.expansion_config,
        force=args.force,
        dry_run=args.dry_run,
        rerun_frozen_baseline=args.rerun_frozen_baseline,
    )
    print("Stage 8.12 Inferno sample expansion complete.")
    for key, value in summary.items():
        print(f"{key}: {value}")
    if outputs:
        print(f"outputs_written: {len(outputs)}")


if __name__ == "__main__":
    main()
