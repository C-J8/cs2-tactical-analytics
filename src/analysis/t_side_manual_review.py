from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "manual_review_rounds",
    "manual_review_finding_map",
    "manual_review_evidence_by_round",
    "manual_review_summary",
    "manual_review_decision_template",
    "manual_review_model_readiness",
    "manual_review_audit",
]

FINDING_INPUT_NAMES = [
    "t_side_key_findings",
    "t_side_ab_region_differences",
    "t_side_ab_utility_differences",
    "t_side_ab_timing_breakpoints",
    "t_side_no_plant_failure_findings",
    "t_side_bomb_carrier_findings",
    "t_side_opponent_tendencies",
    "t_side_progression_findings",
    "t_side_manual_review_queue",
    "t_side_findings_audit",
]

ROUND_COLUMNS = [
    "round_feature_id",
    "round_id",
    "series_id",
    "dem_file_id",
    "parse_id",
    "target_team",
    "opponent",
    "map_name",
    "round_num",
    "half",
    "target_team_side",
    "t_round_outcome",
    "target_site_model_label",
    "label_confidence",
    "winner_side",
    "winner_team",
    "target_team_win",
    "round_progression_signature",
    "round_outcome_type",
    "first_target_team_death_region",
    "first_contact_region",
    "bomb_drop_region",
    "bomb_last_known_region",
    "max_pressure_region_0_115",
    "max_pressure_region_0_55",
    "final_pressure_region_105_115",
]

EVIDENCE_COLUMNS = [
    "review_round_id",
    "round_feature_id",
    "evidence_type",
    "window_type",
    "window_start",
    "window_end",
    "region_group",
    "utility_type",
    "metric_name",
    "metric_value",
    "source_table",
]

CATEGORY_BY_TABLE = {
    "t_side_ab_region_differences": "A_vs_B_region",
    "t_side_ab_utility_differences": "A_vs_B_utility",
    "t_side_ab_timing_breakpoints": "timing",
    "t_side_no_plant_failure_findings": "no_plant",
    "t_side_bomb_carrier_findings": "bomb_carrier",
    "t_side_opponent_tendencies": "opponent",
    "t_side_progression_findings": "progression",
}

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
EVIDENCE_RANK = {"strong_candidate": 0, "medium_candidate": 1, "weak_or_sparse": 2}


def run_t_side_manual_review(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    top_n_findings: int = 20,
    max_rounds_per_finding: int = 8,
    include_weak: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"

    findings = load_findings(gold_dir / "analysis" / "t_side_tactical_findings")
    row_inputs = load_row_inputs(gold_dir, project.dem_files_manifest_path)
    rounds = prepare_rounds(row_inputs, target_team=target_team, target_map=target_map)
    selected_findings = select_findings(findings, top_n=top_n_findings, include_weak=include_weak)
    review_rounds, evidence = build_review_rounds(
        selected_findings,
        findings,
        row_inputs,
        rounds,
        max_rounds_per_finding=max_rounds_per_finding,
    )
    finding_map = build_finding_map(selected_findings, review_rounds)
    summary = build_review_summary(review_rounds, finding_map)
    decisions = build_decision_template(review_rounds)
    readiness = build_model_readiness(
        row_inputs=row_inputs,
        findings=findings,
        review_rounds=review_rounds,
        finding_map=finding_map,
    )
    audit = build_audit(
        review_rounds=review_rounds,
        finding_map=finding_map,
        evidence=evidence,
        target_team=target_team,
        target_map=target_map,
        top_n_findings=top_n_findings,
        max_rounds_per_finding=max_rounds_per_finding,
        include_weak=include_weak,
    )
    frames = {
        "manual_review_rounds": review_rounds,
        "manual_review_finding_map": finding_map,
        "manual_review_evidence_by_round": evidence,
        "manual_review_summary": summary,
        "manual_review_decision_template": decisions,
        "manual_review_model_readiness": readiness,
        "manual_review_audit": audit,
    }

    report = build_markdown_report(frames, target_team=target_team, target_map=target_map)
    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_outputs(frames, gold_dir / "analysis" / "t_side_manual_review", force=force))
        report_path = project_root / "docs" / "t_side_manual_review_pack.md"
        write_markdown_report(report, report_path, force=force)
        outputs["markdown_report"] = report_path

    run_summary = {
        "selected_findings": len(selected_findings),
        "review_rounds": len(review_rounds),
        "findings_covered": int((finding_map["selected_rounds"] > 0).sum()) if not finding_map.empty else 0,
        "evidence_rows": len(evidence),
        "output_tables": len(frames),
    }
    return frames, outputs, run_summary


def load_findings(directory: Path) -> dict[str, pd.DataFrame]:
    return {name: read_catalog(directory / f"{name}.parquet") for name in FINDING_INPUT_NAMES}


def load_row_inputs(gold_dir: Path, dem_manifest_path: Path) -> dict[str, pd.DataFrame]:
    paths = {
        "t_side_all": gold_dir / "round_features" / "round_features_t_side_all.parquet",
        "t_side_planted": gold_dir / "round_features" / "round_features_t_side_planted.parquet",
        "region_timeline": gold_dir / "round_progression" / "round_region_timeline.parquet",
        "death_context": gold_dir / "round_progression" / "death_context_by_round.parquet",
        "bomb_timeline": gold_dir / "round_progression" / "bomb_carrier_timeline.parquet",
        "outcome_context": gold_dir / "round_progression" / "round_outcome_context.parquet",
        "round_state": gold_dir / "round_state" / "round_state_resolved.parquet",
        "utility_events": gold_dir / "utility_events" / "utility_events.parquet",
        "feature_catalog": gold_dir / "analysis" / "t_side_tactical_eda" / "t_side_feature_catalog.parquet",
    }
    inputs = {name: read_catalog(path) for name, path in paths.items()}
    inputs["dem_manifest"] = read_catalog(dem_manifest_path) if dem_manifest_path.exists() else pd.DataFrame()
    return inputs


def prepare_rounds(inputs: dict[str, pd.DataFrame], *, target_team: str, target_map: str) -> pd.DataFrame:
    rounds = inputs["t_side_all"].copy()
    rounds = rounds[
        rounds["target_team_side"].eq("T")
        & rounds["target_team"].astype(str).str.casefold().eq(target_team.casefold())
        & rounds["map_name"].astype(str).str.casefold().isin({target_map.casefold(), f"de_{target_map.casefold()}"})
    ].copy()

    state = inputs["round_state"]
    state_columns = [column for column in ["round_id", "team_t", "team_ct"] if column in state.columns]
    if "round_id" in state_columns:
        rounds = rounds.merge(state[state_columns].drop_duplicates("round_id"), on="round_id", how="left")
    if "team_ct" in rounds.columns:
        unresolved = rounds["opponent"].isna() | rounds["opponent"].astype(str).str.casefold().isin(
            {"", "unknown", "none", "nan"}
        )
        rounds.loc[unresolved, "opponent"] = rounds.loc[unresolved, "team_ct"]
    rounds["opponent"] = rounds["opponent"].fillna("unknown")

    context = inputs["outcome_context"].copy()
    context_columns = [
        "round_feature_id",
        "round_progression_signature",
        "round_outcome_type",
        "first_target_team_death_region",
        "first_contact_region",
        "bomb_drop_region",
        "bomb_last_known_region",
        "max_pressure_region_0_115",
        "max_pressure_region_0_55",
        "final_pressure_region_105_115",
    ]
    available = [column for column in context_columns if column in context.columns]
    rounds = rounds.merge(context[available].drop_duplicates("round_feature_id"), on="round_feature_id", how="left")
    rounds["t_round_outcome"] = rounds.apply(round_outcome, axis=1)
    resolved_winner = rounds["winner_team"].astype(str).str.casefold()
    target = rounds["target_team"].astype(str).str.casefold()
    known_winner = ~resolved_winner.isin({"", "unknown", "none", "nan"})
    rounds["target_team_win"] = (known_winner & resolved_winner.eq(target)) | (~known_winner & rounds["winner_side"].eq("T"))

    manifest = inputs["dem_manifest"]
    if not manifest.empty and "dem_file_id" in manifest.columns:
        metadata = manifest[[column for column in ["dem_file_id", "dem_path", "local_archive_id", "archive_path"] if column in manifest.columns]].copy()
        metadata = metadata.rename(columns={"archive_path": "source_archive_path"}).drop_duplicates("dem_file_id")
        existing = [column for column in metadata.columns if column == "dem_file_id" or column not in rounds.columns]
        rounds = rounds.merge(metadata[existing], on="dem_file_id", how="left")
    return rounds


def round_outcome(row: pd.Series) -> str:
    label = str(row.get("target_site_model_label") or "").upper()
    if row.get("label_confidence") == "high" and label in {"A", "B"}:
        return f"plant_{label}"
    return "no_plant"


def select_findings(findings: dict[str, pd.DataFrame], *, top_n: int, include_weak: bool) -> pd.DataFrame:
    key = findings["t_side_key_findings"].copy()
    if not include_weak:
        key = key[key["evidence_strength"] != "weak_or_sparse"]
    key["review_priority"] = key["evidence_strength"].map(
        {"strong_candidate": "high", "medium_candidate": "medium", "weak_or_sparse": "low"}
    ).fillna("medium")
    key["review_reason"] = "Validate ranked Stage 5.1 finding against concrete rounds"
    key["review_question"] = key["finding_category"].map(default_review_question)
    key["selection_source"] = "key_finding"

    queue = findings["t_side_manual_review_queue"].copy()
    if not include_weak:
        queue = queue[queue["priority"] != "low"]
    queue = queue.rename(
        columns={
            "review_id": "source_review_id",
            "priority": "review_priority",
            "reason": "review_reason",
            "related_table": "support_table",
            "expected_question": "review_question",
        }
    )
    queue["finding_id"] = "queue_" + queue["source_review_id"].astype(str)
    queue["finding_category"] = queue["support_table"].map(CATEGORY_BY_TABLE).fillna("manual_queue")
    queue["finding_text"] = queue["review_reason"] + ": " + queue["suggested_filter"]
    queue["support_metric"] = "manual_review_filter"
    queue["round_count"] = 0
    queue["evidence_strength"] = queue["review_priority"].map(
        {"high": "strong_candidate", "medium": "medium_candidate", "low": "weak_or_sparse"}
    )
    queue["needs_manual_review"] = True
    queue["selection_source"] = "manual_review_queue"

    columns = [
        "finding_id",
        "finding_category",
        "finding_text",
        "support_table",
        "support_metric",
        "round_count",
        "evidence_strength",
        "needs_manual_review",
        "review_priority",
        "review_reason",
        "review_question",
        "selection_source",
        "suggested_filter",
    ]
    combined = pd.concat([queue.reindex(columns=columns), key.reindex(columns=columns)], ignore_index=True)
    combined["_priority"] = combined["review_priority"].map(PRIORITY_RANK).fillna(9)
    combined["_evidence"] = combined["evidence_strength"].map(EVIDENCE_RANK).fillna(9)
    combined = combined.sort_values(["_priority", "_evidence", "round_count"], ascending=[True, True, False])
    combined["_category_rank"] = combined.groupby("finding_category").cumcount()
    return (
        combined.sort_values(["_category_rank", "_priority", "_evidence", "round_count"], ascending=[True, True, True, False])
        .head(top_n)
        .drop(columns=["_priority", "_evidence", "_category_rank"])
        .reset_index(drop=True)
    )


def build_review_rounds(
    selected_findings: pd.DataFrame,
    findings: dict[str, pd.DataFrame],
    inputs: dict[str, pd.DataFrame],
    rounds: pd.DataFrame,
    *,
    max_rounds_per_finding: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    review_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for _, finding in selected_findings.iterrows():
        descriptor = finding_descriptor(finding, findings)
        candidates = candidate_rounds(descriptor, inputs, rounds)
        candidates = candidates.sort_values(["selection_score", "round_num"], ascending=[False, True]).head(max_rounds_per_finding)
        for position, (_, candidate) in enumerate(candidates.iterrows(), start=1):
            review_round_id = f"{finding['finding_id']}_round_{position:02d}"
            row = {column: candidate.get(column) for column in ROUND_COLUMNS if column in candidate.index}
            row.update(
                {
                    "review_round_id": review_round_id,
                    "finding_id": finding["finding_id"],
                    "finding_category": finding["finding_category"],
                    "review_priority": finding["review_priority"],
                    "review_reason": finding["review_reason"],
                    "review_question": finding["review_question"],
                    "suggested_focus": suggested_focus(descriptor),
                    "evidence_strength": finding["evidence_strength"],
                    "needs_manual_review": True,
                }
            )
            for optional in ["dem_path", "local_archive_id", "source_archive_path"]:
                if optional in candidate.index:
                    row[optional] = candidate.get(optional)
            review_rows.append(row)
            evidence_rows.append(
                {
                    "review_round_id": review_round_id,
                    "round_feature_id": candidate["round_feature_id"],
                    "evidence_type": candidate.get("evidence_type", descriptor["category"]),
                    "window_type": candidate.get("window_type"),
                    "window_start": candidate.get("window_start"),
                    "window_end": candidate.get("window_end"),
                    "region_group": candidate.get("region_group"),
                    "utility_type": candidate.get("utility_type"),
                    "metric_name": candidate.get("metric_name", "selection_score"),
                    "metric_value": candidate.get("metric_value", candidate["selection_score"]),
                    "source_table": candidate.get("source_table", finding["support_table"]),
                }
            )

    review_columns = [
        "review_round_id",
        "finding_id",
        "finding_category",
        "review_priority",
        "review_reason",
        *ROUND_COLUMNS,
        "review_question",
        "suggested_focus",
        "evidence_strength",
        "needs_manual_review",
    ]
    optional = [column for column in ["dem_path", "local_archive_id", "source_archive_path"] if column in rounds.columns]
    review = pd.DataFrame(review_rows).reindex(columns=[*review_columns, *optional])
    evidence = pd.DataFrame(evidence_rows).reindex(columns=EVIDENCE_COLUMNS)
    return review, evidence


def finding_descriptor(finding: pd.Series, findings: dict[str, pd.DataFrame]) -> dict[str, Any]:
    category = finding["finding_category"]
    descriptor: dict[str, Any] = {"category": category, "source_table": finding["support_table"]}
    if finding.get("selection_source") == "manual_review_queue":
        return descriptor_from_filter(descriptor, str(finding.get("suggested_filter") or ""))

    text = str(finding["finding_text"])
    if category == "A_vs_B_region":
        match = re.search(r"^(.+) in (interval|cumulative) (\d+)-(\d+)s .* (plant_[AB])", text)
        if match:
            descriptor.update(region=match[1], window_type=match[2], window_start=int(match[3]), window_end=int(match[4]), outcome=match[5])
    elif category == "A_vs_B_utility":
        match = re.search(r"^Utility around (.+) in (interval|cumulative) (\d+)-(\d+)s .* (plant_[AB])", text)
        if match:
            descriptor.update(region=match[1], window_type=match[2], window_start=int(match[3]), window_end=int(match[4]), outcome=match[5])
    elif category == "timing":
        match = re.search(r"^(interval|cumulative) (\d+)-(\d+)s", text)
        if match:
            descriptor.update(window_type=match[1], window_start=int(match[2]), window_end=int(match[3]))
    else:
        source = findings.get(finding["support_table"], pd.DataFrame())
        if "finding_text" in source.columns:
            matches = source[source["finding_text"] == text]
            if not matches.empty:
                descriptor.update(matches.iloc[0].to_dict())
    return descriptor


def descriptor_from_filter(descriptor: dict[str, Any], filter_text: str) -> dict[str, Any]:
    descriptor = descriptor.copy()
    window = re.search(r"window=(\d+)-(\d+)", filter_text)
    for name, pattern in [
        ("window_type", r"window_type=([^,]+)"),
        ("region", r"region=([^,]+)"),
        ("opponent", r"opponent=(.+)$"),
        ("outcome", r"t_round_outcome=(plant_[AB]|no_plant)"),
        ("round_progression_signature", r"round_progression_signature=(.+)$"),
    ]:
        match = re.search(pattern, filter_text)
        if match:
            descriptor[name] = match[1].strip()
    if window:
        descriptor.update(window_start=int(window[1]), window_end=int(window[2]))
    context = re.search(r"(?:and )?([a-z_]+)=([^,]+)$", filter_text)
    if context and context[1] not in {"t_round_outcome", "opponent", "round_progression_signature"}:
        descriptor.update(context_field=context[1], context_value=context[2].strip())
    bomb = re.search(r"bomb:(carrier_region|bomb_drop_region|last_known_region):(\d+)_(\d+)=(.+)$", filter_text)
    if bomb:
        descriptor.update(context_type=bomb[1], window_start=int(bomb[2]), window_end=int(bomb[3]), region=bomb[4])
    return descriptor


def candidate_rounds(descriptor: dict[str, Any], inputs: dict[str, pd.DataFrame], rounds: pd.DataFrame) -> pd.DataFrame:
    category = descriptor["category"]
    eligible = rounds.copy()
    outcome = descriptor.get("outcome") or descriptor.get("t_round_outcome")
    if outcome in {"plant_A", "plant_B"}:
        eligible = eligible[(eligible["t_round_outcome"] == outcome) & (eligible["label_confidence"] == "high")]
    elif outcome == "no_plant" or category == "no_plant":
        eligible = eligible[eligible["t_round_outcome"] == "no_plant"]

    if category == "A_vs_B_region":
        return region_candidates(descriptor, inputs["region_timeline"], eligible)
    if category == "A_vs_B_utility":
        return utility_candidates(descriptor, inputs["utility_events"], eligible)
    if category == "timing":
        return timing_candidates(descriptor, inputs, eligible)
    if category == "bomb_carrier":
        return bomb_candidates(descriptor, inputs, eligible)
    if category == "progression":
        signature = descriptor.get("round_progression_signature")
        if signature is not None:
            eligible = eligible[eligible["round_progression_signature"] == signature]
        return contextual_candidates(eligible, "progression_signature", "round_progression_signature", "round_outcome_context")
    if category == "opponent":
        opponent = descriptor.get("opponent")
        if opponent is not None:
            eligible = eligible[eligible["opponent"].astype(str).str.casefold() == str(opponent).casefold()]
        tendency = descriptor.get("tendency_label")
        if tendency == "A_leaning":
            eligible = eligible[eligible["t_round_outcome"] == "plant_A"]
        elif tendency == "B_leaning":
            eligible = eligible[eligible["t_round_outcome"] == "plant_B"]
        elif tendency == "high_no_plant":
            eligible = eligible[eligible["t_round_outcome"] == "no_plant"]
        return contextual_candidates(eligible, "opponent_tendency", "opponent_round", "round_features_t_side_all")
    return no_plant_candidates(descriptor, inputs, eligible)


def region_candidates(descriptor: dict[str, Any], timeline: pd.DataFrame, rounds: pd.DataFrame) -> pd.DataFrame:
    data = timeline[timeline["round_feature_id"].isin(rounds["round_feature_id"])].copy()
    for column, value in [
        ("window_type", descriptor.get("window_type")),
        ("window_start", descriptor.get("window_start")),
        ("window_end", descriptor.get("window_end")),
        ("region_group", descriptor.get("region")),
    ]:
        if value is not None:
            data = data[data[column] == value]
    if data.empty:
        return empty_candidates(rounds)
    data["selection_score"] = data["time_spent_total"].fillna(0) + 5 * data["players_count_max"].fillna(0) + data["players_count_avg"].fillna(0)
    data["evidence_type"] = "region_presence"
    data["metric_name"] = "time_spent_total"
    data["metric_value"] = data["time_spent_total"]
    data["source_table"] = "round_region_timeline"
    return merge_candidates(rounds, data)


def utility_candidates(descriptor: dict[str, Any], events: pd.DataFrame, rounds: pd.DataFrame) -> pd.DataFrame:
    data = events[events["round_feature_id"].isin(rounds["round_feature_id"])].copy()
    start, end = descriptor.get("window_start"), descriptor.get("window_end")
    if start is not None and end is not None:
        data = data[(data["seconds_from_freeze_end"] >= start) & (data["seconds_from_freeze_end"] < end)]
    data["region_group"] = data.apply(utility_region_group, axis=1)
    if descriptor.get("region") is not None:
        data = data[data["region_group"] == descriptor["region"]]
    if data.empty:
        return empty_candidates(rounds)
    grouped = (
        data.groupby("round_feature_id", dropna=False)
        .agg(selection_score=("utility_event_id", "count"), utility_type=("utility_type", join_unique), region_group=("region_group", "first"))
        .reset_index()
    )
    grouped["evidence_type"] = "utility_event"
    grouped["metric_name"] = "utility_event_count"
    grouped["metric_value"] = grouped["selection_score"]
    grouped["window_type"] = descriptor.get("window_type")
    grouped["window_start"] = start
    grouped["window_end"] = end
    grouped["source_table"] = "utility_events"
    return merge_candidates(rounds, grouped)


def timing_candidates(descriptor: dict[str, Any], inputs: dict[str, pd.DataFrame], rounds: pd.DataFrame) -> pd.DataFrame:
    region = region_candidates(descriptor, inputs["region_timeline"], rounds)
    utility = utility_candidates(descriptor, inputs["utility_events"], rounds)
    scores = []
    for frame, weight in [(region, 1.0), (utility, 5.0)]:
        if not frame.empty:
            scores.append(frame[["round_feature_id", "selection_score"]].assign(selection_score=lambda value: value["selection_score"] * weight))
    if not scores:
        return empty_candidates(rounds)
    grouped = pd.concat(scores).groupby("round_feature_id", as_index=False)["selection_score"].sum()
    grouped["evidence_type"] = "timing_signal"
    grouped["metric_name"] = "combined_round_signal"
    grouped["metric_value"] = grouped["selection_score"]
    grouped["window_type"] = descriptor.get("window_type")
    grouped["window_start"] = descriptor.get("window_start")
    grouped["window_end"] = descriptor.get("window_end")
    grouped["source_table"] = "round_region_timeline+utility_events"
    return merge_candidates(rounds, grouped)


def no_plant_candidates(descriptor: dict[str, Any], inputs: dict[str, pd.DataFrame], rounds: pd.DataFrame) -> pd.DataFrame:
    field = descriptor.get("context_field") or descriptor.get("finding_type")
    value = descriptor.get("context_value") or descriptor.get("finding_value")
    if field and str(field).startswith("death:"):
        death_type = str(field).split(":", 1)[1]
        deaths = inputs["death_context"]
        if death_type == "first_target_team_death":
            deaths = deaths[(deaths["is_target_team_death"] == True)].sort_values(["round_feature_id", "death_order"]).drop_duplicates("round_feature_id")  # noqa: E712
        if value is not None:
            deaths = deaths[deaths["death_region_group"] == value]
        data = deaths[["round_feature_id", "death_region_group"]].copy()
        data["region_group"] = data["death_region_group"]
        return scored_context(rounds, data, "death_context", "death_order", "death_context_by_round")
    if field and str(field).startswith("bomb:"):
        parts = str(field).split(":")
        descriptor = {**descriptor, "context_type": parts[1]}
        if len(parts) == 3 and "_" in parts[2]:
            start, end = parts[2].split("_", 1)
            descriptor.update(window_start=int(start), window_end=int(end), region=value)
        return bomb_candidates(descriptor, inputs, rounds)
    if field in rounds.columns and value is not None:
        rounds = rounds[rounds[field].fillna("UNKNOWN").astype(str) == str(value)]
    return contextual_candidates(rounds, "no_plant_context", str(field or "no_plant"), "round_outcome_context")


def bomb_candidates(descriptor: dict[str, Any], inputs: dict[str, pd.DataFrame], rounds: pd.DataFrame) -> pd.DataFrame:
    context_type = descriptor.get("context_type")
    region = descriptor.get("region") or descriptor.get("region_group")
    start, end = descriptor.get("window_start"), descriptor.get("window_end")
    if context_type in {"carrier_region", "bomb_drop_region"}:
        data = inputs["bomb_timeline"]
        data = data[data["round_feature_id"].isin(rounds["round_feature_id"])].copy()
        if start is not None:
            data = data[(data["window_start"] == start) & (data["window_end"] == end)]
        region_column = "bomb_carrier_region_group" if context_type == "carrier_region" else "bomb_drop_region_group"
        if region is not None:
            data = data[data[region_column].fillna("UNKNOWN") == region]
        if data.empty:
            return empty_candidates(rounds)
        data = data.drop_duplicates("round_feature_id")[["round_feature_id", region_column, "window_type", "window_start", "window_end"]]
        data["region_group"] = data[region_column]
        return scored_context(rounds, data, "bomb_carrier", context_type, "bomb_carrier_timeline")
    field = "bomb_last_known_region" if context_type == "last_known_region" else "bomb_drop_region"
    if region is not None and field in rounds.columns:
        rounds = rounds[rounds[field].fillna("UNKNOWN") == region]
    return contextual_candidates(rounds, "bomb_carrier", field, "round_outcome_context")


def contextual_candidates(rounds: pd.DataFrame, evidence_type: str, metric_name: str, source_table: str) -> pd.DataFrame:
    result = rounds.copy()
    result["selection_score"] = context_score(result)
    result["evidence_type"] = evidence_type
    result["metric_name"] = metric_name
    result["metric_value"] = result["selection_score"]
    result["source_table"] = source_table
    return result


def scored_context(rounds: pd.DataFrame, data: pd.DataFrame, evidence_type: str, metric_name: str, source_table: str) -> pd.DataFrame:
    data = data.copy()
    data["selection_score"] = 1.0
    data["evidence_type"] = evidence_type
    data["metric_name"] = metric_name
    data["metric_value"] = 1.0
    data["source_table"] = source_table
    return merge_candidates(rounds, data)


def merge_candidates(rounds: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    evidence_columns = [column for column in evidence.columns if column == "round_feature_id" or column not in rounds.columns]
    return rounds.merge(evidence[evidence_columns], on="round_feature_id", how="inner")


def empty_candidates(rounds: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(columns=[*rounds.columns, "selection_score"])


def context_score(frame: pd.DataFrame) -> pd.Series:
    score = pd.Series(1.0, index=frame.index)
    if "bomb_drop_region" in frame.columns:
        score += frame["bomb_drop_region"].notna().astype(float) * 2
    if "final_pressure_region_105_115" in frame.columns:
        score += frame["final_pressure_region_105_115"].notna().astype(float)
    return score


def utility_region_group(row: pd.Series) -> str:
    end = str(row.get("end_region_group") or "")
    if end and end.upper() != "UNKNOWN":
        return end
    throw = str(row.get("throw_region_group") or "")
    return throw or "UNKNOWN"


def join_unique(values: pd.Series) -> str:
    return ",".join(sorted({str(value) for value in values if pd.notna(value)}))


def default_review_question(category: str) -> str:
    questions = {
        "A_vs_B_region": "Does the regional pattern visibly distinguish the selected A/B outcome?",
        "A_vs_B_utility": "Is the utility pattern planned and repeatable for the selected site?",
        "timing": "Does this window contain a meaningful tactical decision point?",
        "no_plant": "What prevents a valid plant in this round?",
        "bomb_carrier": "Does C4 routing support the candidate pattern?",
        "progression": "Is this progression repeatable or only a coarse grouping?",
        "opponent": "Does the opponent setup plausibly explain the observed tendency?",
    }
    return questions.get(category, "Does the round support the candidate finding?")


def suggested_focus(descriptor: dict[str, Any]) -> str:
    parts = [descriptor["category"]]
    if descriptor.get("region"):
        parts.append(str(descriptor["region"]))
    if descriptor.get("window_start") is not None:
        parts.append(f"{descriptor['window_start']}-{descriptor['window_end']}s")
    if descriptor.get("outcome"):
        parts.append(str(descriptor["outcome"]))
    return " / ".join(parts)


def build_finding_map(findings: pd.DataFrame, review_rounds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, finding in findings.iterrows():
        selected = review_rounds[review_rounds["finding_id"] == finding["finding_id"]]
        counts = selected["t_round_outcome"].value_counts()
        rows.append(
            {
                "finding_id": finding["finding_id"],
                "finding_category": finding["finding_category"],
                "finding_text": finding["finding_text"],
                "support_table": finding["support_table"],
                "support_metric": finding["support_metric"],
                "evidence_strength": finding["evidence_strength"],
                "selected_rounds": len(selected),
                "plant_A_examples": int(counts.get("plant_A", 0)),
                "plant_B_examples": int(counts.get("plant_B", 0)),
                "no_plant_examples": int(counts.get("no_plant", 0)),
                "review_status": "pending_manual_review",
            }
        )
    return pd.DataFrame(rows)


def build_review_summary(review: pd.DataFrame, finding_map: pd.DataFrame) -> pd.DataFrame:
    outcomes = review["t_round_outcome"].value_counts() if not review.empty else pd.Series(dtype=int)
    priorities = review["review_priority"].value_counts() if not review.empty else pd.Series(dtype=int)
    return pd.DataFrame(
        [
            {
                "total_review_rounds": len(review),
                "total_findings_covered": int((finding_map["selected_rounds"] > 0).sum()),
                "findings_without_round_examples": int((finding_map["selected_rounds"] == 0).sum()),
                "plant_A_rounds": int(outcomes.get("plant_A", 0)),
                "plant_B_rounds": int(outcomes.get("plant_B", 0)),
                "no_plant_rounds": int(outcomes.get("no_plant", 0)),
                "high_priority_items": int(priorities.get("high", 0)),
                "medium_priority_items": int(priorities.get("medium", 0)),
                "low_priority_items": int(priorities.get("low", 0)),
                "opponents_covered": review["opponent"].nunique() if not review.empty else 0,
                "series_covered": review["series_id"].nunique() if not review.empty else 0,
                "late_round_examples": int(review["suggested_focus"].str.contains(r"(?:95-105|105-115)s", na=False).sum()) if not review.empty else 0,
                "status": "ok" if not review.empty else "warning",
            }
        ]
    )


def build_decision_template(review: pd.DataFrame) -> pd.DataFrame:
    columns = ["review_round_id", "finding_id", "round_feature_id"]
    template = review[columns].copy() if not review.empty else pd.DataFrame(columns=columns)
    template["review_decision"] = "pending"
    template["confidence"] = ""
    template["manual_notes"] = ""
    template["is_good_example_for_report"] = ""
    template["is_good_example_for_model_motivation"] = ""
    template["should_exclude_from_model_reason"] = ""
    template["reviewed_at"] = ""
    return template


def build_model_readiness(
    *,
    row_inputs: dict[str, pd.DataFrame],
    findings: dict[str, pd.DataFrame],
    review_rounds: pd.DataFrame,
    finding_map: pd.DataFrame,
) -> pd.DataFrame:
    planted = row_inputs["t_side_planted"]
    catalog = row_inputs["feature_catalog"]
    audit = findings["t_side_findings_audit"]
    ab_findings = finding_map[finding_map["finding_category"].isin(["A_vs_B_region", "A_vs_B_utility", "timing"])]
    labels = planted.get("target_site_model_label", pd.Series(dtype=str)).value_counts()
    leakage_marked = (
        not catalog.empty
        and "notes" in catalog.columns
        and catalog["notes"].fillna("").str.contains("leakage", case=False).any()
    )
    checks = [
        readiness_row("high_confidence_ab_dataset", not planted.empty and set(labels.index) >= {"A", "B"}, f"A={labels.get('A', 0)}, B={labels.get('B', 0)}", "Keep only high-confidence A/B rows."),
        readiness_row("feature_catalog_exists", not catalog.empty, f"rows={len(catalog)}", "Use the catalog to define predictors."),
        readiness_row("leakage_fields_marked", leakage_marked, "Catalog notes identify post-round/target leakage fields.", "Exclude all leakage-marked fields."),
        readiness_row("stage_5_1_audit_ok", not audit.empty and audit.iloc[0].get("status") == "ok", f"status={audit.iloc[0].get('status') if not audit.empty else 'missing'}", "Resolve Stage 5.1 warnings before modeling."),
        readiness_row("manual_review_pack_generated", not review_rounds.empty, f"rounds={len(review_rounds)}", "Complete the decision template."),
        readiness_row("enough_plant_A_examples", labels.get("A", 0) >= 20, f"plant_A={labels.get('A', 0)}", "Retain class-aware validation."),
        readiness_row("enough_plant_B_examples", labels.get("B", 0) >= 20, f"plant_B={labels.get('B', 0)}", "Use conservative validation because B is smaller."),
        readiness_row("enough_ab_findings", len(ab_findings) >= 3, f"findings={len(ab_findings)}", "Use findings only as motivation, not feature proof."),
        readiness_row("no_plant_separated", "no_plant" not in set(labels.index), f"labels={sorted(map(str, labels.index))}", "Do not infer A/B for no-plant rounds."),
        readiness_row("prediction_horizon_required", False, "Windows reach 115s; a pre-plant horizon is not selected yet.", "Choose and document a leakage-safe prediction horizon."),
    ]
    frame = pd.DataFrame(checks)
    if (frame["status"] == "fail").sum() == 0:
        overall = "ready_for_baseline_after_manual_review"
    elif (frame["status"] == "fail").sum() == 1 and frame.loc[frame["status"] == "fail", "readiness_check"].iloc[0] == "prediction_horizon_required":
        overall = "ready_for_baseline_after_manual_review"
    elif (frame["status"] == "pass").sum() >= 7:
        overall = "needs_more_manual_review"
    else:
        overall = "not_ready"
    overall_row = pd.DataFrame(
        [
            {
                "readiness_check": "overall_readiness",
                "status": "pass" if overall == "ready_for_baseline_after_manual_review" else "fail",
                "evidence": f"{int((frame['status'] == 'pass').sum())} of {len(frame)} checks passed.",
                "recommendation": overall,
            }
        ]
    )
    return pd.concat([frame, overall_row], ignore_index=True)


def readiness_row(check: str, passed: bool, evidence: str, recommendation: str) -> dict[str, str]:
    return {"readiness_check": check, "status": "pass" if passed else "fail", "evidence": evidence, "recommendation": recommendation}


def build_audit(
    *,
    review_rounds: pd.DataFrame,
    finding_map: pd.DataFrame,
    evidence: pd.DataFrame,
    target_team: str,
    target_map: str,
    top_n_findings: int,
    max_rounds_per_finding: int,
    include_weak: bool,
) -> pd.DataFrame:
    valid_outcomes = review_rounds.empty or review_rounds["t_round_outcome"].isin(["plant_A", "plant_B", "no_plant"]).all()
    t_only = review_rounds.empty or review_rounds["target_team_side"].eq("T").all()
    status = "ok" if not review_rounds.empty and valid_outcomes and t_only else "warning"
    return pd.DataFrame(
        [
            {
                "audit_id": "t_side_manual_review_pack",
                "target_team": target_team,
                "target_map": target_map,
                "top_n_findings": top_n_findings,
                "max_rounds_per_finding": max_rounds_per_finding,
                "include_weak": include_weak,
                "review_rounds": len(review_rounds),
                "findings_selected": len(finding_map),
                "findings_covered": int((finding_map["selected_rounds"] > 0).sum()) if not finding_map.empty else 0,
                "evidence_rows": len(evidence),
                "t_side_only": t_only,
                "valid_outcomes_only": valid_outcomes,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def build_markdown_report(frames: dict[str, pd.DataFrame], *, target_team: str, target_map: str) -> str:
    review = frames["manual_review_rounds"]
    summary = frames["manual_review_summary"]
    finding_map = frames["manual_review_finding_map"]
    readiness = frames["manual_review_model_readiness"]
    top_columns = ["review_round_id", "finding_category", "review_priority", "opponent", "round_num", "t_round_outcome", "suggested_focus"]
    sections = [
        f"# T-side Manual Review Pack -- {target_team} {target_map}",
        "",
        "## Scope",
        "",
        "This pack links conservative Stage 5.1 findings to concrete T-side rounds and row-level evidence.",
        "",
        "## Why this stage exists",
        "",
        "Manual review separates repeatable tactical candidates from sparse patterns before any A/B model is trained.",
        "",
        "## Review summary",
        "",
        markdown_table(summary, list(summary.columns)),
        "",
        "## Top findings selected",
        "",
        markdown_table(finding_map, ["finding_id", "finding_category", "evidence_strength", "selected_rounds", "review_status"], top_n=10),
        "",
        "## Rounds to review first",
        "",
        markdown_table(review, top_columns, top_n=10),
        "",
        "## A/B examples",
        "",
        markdown_table(review[review["t_round_outcome"].isin(["plant_A", "plant_B"])], top_columns, top_n=10),
        "",
        "## No-plant examples",
        "",
        markdown_table(review[review["t_round_outcome"] == "no_plant"], top_columns, top_n=10),
        "",
        "## C4/bomb carrier examples",
        "",
        markdown_table(review[review["finding_category"] == "bomb_carrier"], top_columns, top_n=10),
        "",
        "## Late-round examples",
        "",
        markdown_table(review[review["suggested_focus"].str.contains(r"(?:95-105|105-115)s", na=False)], top_columns, top_n=10),
        "",
        "## Manual decision template",
        "",
        "Fill `manual_review_decision_template.csv` after inspecting each selected demo round.",
        "",
        "## Model readiness",
        "",
        markdown_table(readiness, list(readiness.columns), top_n=20),
        "",
        "## Limitations",
        "",
        "- Findings remain descriptive candidates, not causal claims.",
        "- Repeated rounds can support more than one finding.",
        "- No-plant rounds never receive an inferred A/B label.",
        "- A leakage-safe prediction horizon must be chosen before modeling.",
        "",
        "## Next step",
        "",
        "Complete manual decisions, then design a leakage-controlled A/B baseline using only high-confidence planted T-side rounds.",
        "",
    ]
    return "\n".join(sections)


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 10) -> str:
    if frame.empty:
        return "_No rows available for the current filters._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                frames[name].to_csv(path, index=False) if suffix == "csv" else frames[name].to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def write_markdown_report(report: str, path: Path, *, force: bool) -> None:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(report, encoding="utf-8")


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("T-side Manual Review Pack summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an auditable manual-review queue from Stage 5.1 findings.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--top-n-findings", type=int, default=20)
    parser.add_argument("--max-rounds-per-finding", type=int, default=8)
    parser.add_argument("--include-weak", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_t_side_manual_review(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        top_n_findings=args.top_n_findings,
        max_rounds_per_finding=args.max_rounds_per_finding,
        include_weak=args.include_weak,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
