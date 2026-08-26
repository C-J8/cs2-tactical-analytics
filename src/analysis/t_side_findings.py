from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.reports import markdown_table as report_markdown_table
from src.utils.reports import now_utc, safe_divide


FINDING_OUTPUT_NAMES = [
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

STAGE5_INPUT_NAMES = [
    "t_side_eda_overview",
    "t_side_site_distribution",
    "t_side_opponent_summary",
    "t_side_window_region_summary",
    "t_side_window_utility_summary",
    "t_side_no_plant_summary",
    "t_side_death_summary",
    "t_side_bomb_carrier_summary",
    "t_side_progression_signature_summary",
    "t_side_feature_catalog",
    "t_side_eda_audit",
]

EVIDENCE_RANK = {"strong_candidate": 0, "medium_candidate": 1, "weak_or_sparse": 2}


def run_t_side_findings(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    min_rounds: int = 3,
    top_n: int = 15,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    stage5_dir = gold_dir / "analysis" / "t_side_tactical_eda"
    inputs = load_stage5_inputs(stage5_dir)

    region_differences = build_ab_region_differences(inputs["t_side_window_region_summary"], min_rounds=min_rounds)
    utility_differences = build_ab_utility_differences(inputs["t_side_window_utility_summary"], min_rounds=min_rounds)
    timing = build_timing_breakpoints(region_differences, utility_differences)
    no_plant = build_no_plant_failure_findings(
        inputs["t_side_no_plant_summary"],
        inputs["t_side_death_summary"],
        inputs["t_side_bomb_carrier_summary"],
        min_rounds=min_rounds,
    )
    bomb = build_bomb_carrier_findings(inputs["t_side_bomb_carrier_summary"], min_rounds=min_rounds)
    opponents = build_opponent_tendencies(inputs["t_side_opponent_summary"], min_rounds=min_rounds)
    progression = build_progression_findings(inputs["t_side_progression_signature_summary"], min_rounds=min_rounds, top_n=top_n)
    key_findings = build_key_findings(
        region_differences,
        utility_differences,
        timing,
        no_plant,
        bomb,
        opponents,
        progression,
        top_n=top_n,
    )
    manual_review = build_manual_review_queue(
        region_differences,
        utility_differences,
        no_plant,
        bomb,
        opponents,
        progression,
        top_n=top_n,
    )

    frames = {
        "t_side_key_findings": key_findings,
        "t_side_ab_region_differences": region_differences,
        "t_side_ab_utility_differences": utility_differences,
        "t_side_ab_timing_breakpoints": timing,
        "t_side_no_plant_failure_findings": no_plant,
        "t_side_bomb_carrier_findings": bomb,
        "t_side_opponent_tendencies": opponents,
        "t_side_progression_findings": progression,
        "t_side_manual_review_queue": manual_review,
    }
    frames["t_side_findings_audit"] = build_findings_audit(
        inputs=inputs,
        frames=frames,
        target_team=target_team,
        target_map=target_map,
        min_rounds=min_rounds,
        top_n=top_n,
    )

    report = build_markdown_report(frames, inputs, target_team=target_team, target_map=target_map)
    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = gold_dir / "analysis" / "t_side_tactical_findings"
        outputs.update(write_outputs(frames, output_dir, force=force))
        report_path = project_root / "docs" / "t_side_tactical_findings.md"
        write_markdown_report(report, report_path, force=force)
        outputs["markdown_report"] = report_path

    summary = {
        "key_findings": len(key_findings),
        "region_differences": len(region_differences),
        "utility_differences": len(utility_differences),
        "timing_windows": len(timing),
        "manual_review_items": len(manual_review),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def load_stage5_inputs(stage5_dir: Path) -> dict[str, pd.DataFrame]:
    return {name: read_catalog(stage5_dir / f"{name}.parquet") for name in STAGE5_INPUT_NAMES}


def build_ab_region_differences(summary: pd.DataFrame, *, min_rounds: int) -> pd.DataFrame:
    keys = ["window_type", "window_start", "window_end", "region_group"]
    metrics = ["round_count", "round_share_with_region", "avg_time_spent", "avg_players_count"]
    a = outcome_frame(summary, "plant_A", keys, metrics, "A")
    b = outcome_frame(summary, "plant_B", keys, metrics, "B")
    merged = a.merge(b, on=keys, how="outer").fillna(0)
    merged = merged.rename(
        columns={
            "round_count_A": "rounds_A",
            "round_count_B": "rounds_B",
            "round_share_with_region_A": "share_A",
            "round_share_with_region_B": "share_B",
        }
    )
    merged["share_diff_A_minus_B"] = merged["share_A"] - merged["share_B"]
    merged["abs_share_diff"] = merged["share_diff_A_minus_B"].abs()
    merged["avg_time_spent_diff_A_minus_B"] = merged["avg_time_spent_A"] - merged["avg_time_spent_B"]
    merged["avg_players_diff_A_minus_B"] = merged["avg_players_count_A"] - merged["avg_players_count_B"]
    merged = merged.rename(columns={"avg_players_count_A": "avg_players_A", "avg_players_count_B": "avg_players_B"})
    merged["evidence_strength"] = merged.apply(
        lambda row: evidence_strength(row["abs_share_diff"], min(row["rounds_A"], row["rounds_B"]), min_rounds), axis=1
    )
    return sort_by_evidence(merged)


def build_ab_utility_differences(summary: pd.DataFrame, *, min_rounds: int) -> pd.DataFrame:
    keys = ["window_type", "window_start", "window_end", "region_group"]
    metrics = [
        "total_utilities",
        "avg_utilities_per_round",
        "smokes_per_round",
        "molotovs_per_round",
        "flashes_per_round",
        "he_per_round",
        "round_share_with_utility",
        "rounds_with_utility",
    ]
    available = [metric for metric in metrics if metric in summary.columns]
    a = outcome_frame(summary, "plant_A", keys, available, "A")
    b = outcome_frame(summary, "plant_B", keys, available, "B")
    merged = a.merge(b, on=keys, how="outer").fillna(0)
    rename = {
        "rounds_with_utility_A": "rounds_A",
        "rounds_with_utility_B": "rounds_B",
    }
    merged = merged.rename(columns=rename)
    for metric in [
        "avg_utilities_per_round",
        "smokes_per_round",
        "molotovs_per_round",
        "flashes_per_round",
        "he_per_round",
        "round_share_with_utility",
    ]:
        if f"{metric}_A" in merged.columns:
            merged[f"diff_{metric}_A_minus_B"] = merged[f"{metric}_A"] - merged[f"{metric}_B"]
    share_diff = merged.get("diff_round_share_with_utility_A_minus_B", pd.Series(0.0, index=merged.index)).abs()
    merged["evidence_strength"] = [
        evidence_strength(diff, min(rounds_a, rounds_b), min_rounds)
        for diff, rounds_a, rounds_b in zip(share_diff, merged.get("rounds_A", 0), merged.get("rounds_B", 0), strict=False)
    ]
    return sort_by_evidence(merged, difference_column="diff_round_share_with_utility_A_minus_B")


def build_timing_breakpoints(region: pd.DataFrame, utility: pd.DataFrame) -> pd.DataFrame:
    keys = ["window_type", "window_start", "window_end"]
    region_window = (
        region.groupby(keys, dropna=False)
        .agg(
            mean_abs_share_diff=("abs_share_diff", "mean"),
            max_abs_share_diff=("abs_share_diff", "max"),
            mean_abs_time_diff=("avg_time_spent_diff_A_minus_B", lambda values: values.abs().mean()),
            region_candidates=("evidence_strength", lambda values: int(values.isin(["strong_candidate", "medium_candidate"]).sum())),
        )
        .reset_index()
    )
    if utility.empty:
        utility_window = pd.DataFrame(columns=[*keys, "mean_abs_utility_diff", "mean_abs_utility_share_diff", "utility_candidates"])
    else:
        utility_window = (
            utility.groupby(keys, dropna=False)
            .agg(
                mean_abs_utility_diff=("diff_avg_utilities_per_round_A_minus_B", lambda values: values.abs().mean()),
                mean_abs_utility_share_diff=("diff_round_share_with_utility_A_minus_B", lambda values: values.abs().mean()),
                utility_candidates=("evidence_strength", lambda values: int(values.isin(["strong_candidate", "medium_candidate"]).sum())),
            )
            .reset_index()
        )
    timing = region_window.merge(utility_window, on=keys, how="outer").fillna(0)
    timing["normalized_time_diff"] = normalize_series(timing["mean_abs_time_diff"])
    timing["normalized_utility_diff"] = normalize_series(timing["mean_abs_utility_diff"])
    timing["region_signal_score"] = 0.7 * timing["mean_abs_share_diff"] + 0.3 * timing["normalized_time_diff"]
    timing["utility_signal_score"] = 0.6 * timing["mean_abs_utility_share_diff"] + 0.4 * timing["normalized_utility_diff"]
    timing["combined_signal_score"] = 0.6 * timing["region_signal_score"] + 0.4 * timing["utility_signal_score"]
    timing["signal_period"] = timing.apply(
        lambda row: signal_period(row["window_type"], row["window_start"], row["window_end"]), axis=1
    )
    timing["dominant_signal"] = timing.apply(dominant_signal, axis=1)
    timing["is_first_strong_signal"] = False
    timing["is_max_signal"] = False
    for window_type, group in timing.groupby("window_type"):
        ordered = group.sort_values(["window_start", "window_end"])
        strong = ordered[ordered["combined_signal_score"] >= 0.15]
        if not strong.empty:
            timing.loc[strong.index[0], "is_first_strong_signal"] = True
        if not group.empty:
            timing.loc[group["combined_signal_score"].idxmax(), "is_max_signal"] = True
    timing["score_formula"] = "0.6*(0.7*mean_abs_share_diff+0.3*normalized_time_diff)+0.4*(0.6*mean_abs_utility_share_diff+0.4*normalized_utility_diff)"
    return timing.sort_values(["window_type", "window_start", "window_end"]).reset_index(drop=True)


def build_no_plant_failure_findings(
    no_plant_summary: pd.DataFrame,
    death_summary: pd.DataFrame,
    bomb_summary: pd.DataFrame,
    *,
    min_rounds: int,
) -> pd.DataFrame:
    rows = []
    total_no_plant = int(no_plant_summary["round_count"].sum()) if len(no_plant_summary) == 1 else None
    for dimension in [column for column in no_plant_summary.columns if column not in {"round_count", "round_share"}]:
        grouped = no_plant_summary.groupby(dimension, dropna=False)["round_count"].sum().reset_index()
        denominator = grouped["round_count"].sum()
        for _, row in grouped.iterrows():
            value = normalized_value(row[dimension])
            count = int(row["round_count"])
            rows.append(no_plant_finding(dimension, value, count, safe_divide(count, denominator), min_rounds))

    death = death_summary[death_summary["t_round_outcome"] == "no_plant"] if not death_summary.empty else pd.DataFrame()
    for _, row in death.iterrows():
        count = int(row["round_count"])
        rows.append(
            no_plant_finding(
                f"death:{row['death_type']}",
                normalized_value(row["region_group"]),
                count,
                row.get("round_share"),
                min_rounds,
            )
        )

    bomb = bomb_summary[bomb_summary["t_round_outcome"] == "no_plant"] if not bomb_summary.empty else pd.DataFrame()
    if not bomb.empty:
        bomb = bomb[
            bomb["context_type"].eq("last_known_region")
            | (bomb["context_type"].eq("carrier_region") & bomb["is_late_round"].fillna(False))
        ]
    for _, row in bomb.iterrows():
        count = int(row["round_count"])
        window_suffix = (
            f":{int(row['window_start'])}_{int(row['window_end'])}"
            if pd.notna(row.get("window_start")) and pd.notna(row.get("window_end"))
            else ""
        )
        rows.append(
            no_plant_finding(
                f"bomb:{row['context_type']}{window_suffix}",
                normalized_value(row["region_group"]),
                count,
                row.get("round_share"),
                min_rounds,
            )
        )
    result = pd.DataFrame(rows).drop_duplicates(["finding_type", "finding_value", "round_count"])
    if total_no_plant is not None:
        result["total_no_plant_rounds"] = total_no_plant
    return result.sort_values(["evidence_strength", "round_count"], key=evidence_sort_key, ascending=[True, False]).reset_index(drop=True)


def build_bomb_carrier_findings(summary: pd.DataFrame, *, min_rounds: int) -> pd.DataFrame:
    if summary.empty:
        return summary.copy()
    findings = summary.copy()
    findings = findings[findings["context_type"].isin(["carrier_region", "bomb_drop_region", "last_known_region"])].copy()
    findings["evidence_strength"] = findings["round_count"].map(
        lambda count: "medium_candidate" if count >= min_rounds else "weak_or_sparse"
    )
    findings["finding_text"] = findings.apply(
        lambda row: (
            f"C4 {str(row['context_type']).replace('_', ' ')} around {normalized_value(row['region_group'])} "
            f"appears in {int(row['round_count'])} {row['t_round_outcome']} rounds"
            f" during {window_text(row)}; this suggests a candidate pattern for manual review."
        ),
        axis=1,
    )
    return findings.sort_values(["is_late_round", "round_count"], ascending=[False, False]).reset_index(drop=True)


def build_opponent_tendencies(summary: pd.DataFrame, *, min_rounds: int) -> pd.DataFrame:
    tendencies = summary.copy()
    tendencies["planted_rounds"] = tendencies["plant_A"] + tendencies["plant_B"]
    tendencies["no_plant_share"] = tendencies.apply(
        lambda row: safe_divide(row["no_plant"], row["total_t_side_rounds"]), axis=1
    )
    tendencies["tendency_label"] = tendencies.apply(lambda row: opponent_tendency(row, min_rounds), axis=1)
    tendencies["finding_text"] = tendencies.apply(
        lambda row: (
            f"Against {row['opponent']}, {int(row['total_t_side_rounds'])} T-side rounds suggest "
            f"{str(row['tendency_label']).replace('_', ' ')}; plant rate {format_percent(row['plant_rate'])} "
            f"and no-plant share {format_percent(row['no_plant_share'])}."
        ),
        axis=1,
    )
    tendencies["evidence_strength"] = tendencies["total_t_side_rounds"].map(
        lambda count: "medium_candidate" if count >= min_rounds else "weak_or_sparse"
    )
    return tendencies.sort_values("total_t_side_rounds", ascending=False).reset_index(drop=True)


def build_progression_findings(summary: pd.DataFrame, *, min_rounds: int, top_n: int) -> pd.DataFrame:
    findings = summary[summary["count"] >= min_rounds].copy()
    if findings.empty:
        return findings
    findings = findings.sort_values(["t_round_outcome", "count", "winrate"], ascending=[True, False, False])
    findings = findings.groupby("t_round_outcome", group_keys=False).head(top_n).copy()
    findings["finding_text"] = findings.apply(
        lambda row: (
            f"Progression '{row['round_progression_signature']}' appears in {int(row['count'])} "
            f"{row['t_round_outcome']} rounds with observed win rate {format_percent(row['winrate'])}; "
            "it is a candidate pattern, not a causal explanation."
        ),
        axis=1,
    )
    findings["evidence_strength"] = findings["count"].map(
        lambda count: "medium_candidate" if count >= min_rounds else "weak_or_sparse"
    )
    return findings.reset_index(drop=True)


def build_key_findings(
    region: pd.DataFrame,
    utility: pd.DataFrame,
    timing: pd.DataFrame,
    no_plant: pd.DataFrame,
    bomb: pd.DataFrame,
    opponents: pd.DataFrame,
    progression: pd.DataFrame,
    *,
    top_n: int,
) -> pd.DataFrame:
    rows = []
    for _, row in region.head(top_n).iterrows():
        direction = "plant_A" if row["share_diff_A_minus_B"] > 0 else "plant_B"
        rows.append(
            key_finding(
                "A_vs_B_region",
                f"{row['region_group']} in {window_text(row)} appears more associated with {direction} by {abs(row['share_diff_A_minus_B']):.1%} share difference.",
                "t_side_ab_region_differences",
                "abs_share_diff",
                min(row["rounds_A"], row["rounds_B"]),
                row["evidence_strength"],
            )
        )
    for _, row in utility.head(top_n).iterrows():
        diff = row.get("diff_avg_utilities_per_round_A_minus_B", 0)
        direction = "plant_A" if diff > 0 else "plant_B"
        rows.append(
            key_finding(
                "A_vs_B_utility",
                f"Utility around {row['region_group']} in {window_text(row)} appears higher for {direction} by {abs(diff):.2f} events per round.",
                "t_side_ab_utility_differences",
                "diff_avg_utilities_per_round_A_minus_B",
                min(row.get("rounds_A", 0), row.get("rounds_B", 0)),
                row["evidence_strength"],
            )
        )
    timing_candidates = timing[(timing["is_first_strong_signal"]) | (timing["is_max_signal"])].sort_values(
        "combined_signal_score", ascending=False
    )
    for _, row in timing_candidates.head(top_n).iterrows():
        rows.append(
            key_finding(
                "timing",
                f"{window_text(row)} is a candidate A/B separation point with combined signal {row['combined_signal_score']:.3f}, led by {row['dominant_signal']} evidence.",
                "t_side_ab_timing_breakpoints",
                "combined_signal_score",
                row["region_candidates"] + row["utility_candidates"],
                "strong_candidate" if row["combined_signal_score"] >= 0.25 else "medium_candidate",
            )
        )
    for _, row in no_plant.head(top_n).iterrows():
        rows.append(
            key_finding(
                "no_plant",
                row["finding_text"],
                "t_side_no_plant_failure_findings",
                "round_share",
                row["round_count"],
                row["evidence_strength"],
            )
        )
    for _, row in bomb.head(top_n).iterrows():
        rows.append(
            key_finding(
                "bomb_carrier",
                row["finding_text"],
                "t_side_bomb_carrier_findings",
                "round_share",
                row["round_count"],
                row["evidence_strength"],
            )
        )
    for _, row in opponents[opponents["tendency_label"] != "balanced_or_unclear"].head(top_n).iterrows():
        rows.append(
            key_finding(
                "opponent",
                row["finding_text"],
                "t_side_opponent_tendencies",
                "plant_rate",
                row["total_t_side_rounds"],
                row["evidence_strength"],
            )
        )
    for _, row in progression.head(top_n).iterrows():
        rows.append(
            key_finding(
                "progression",
                row["finding_text"],
                "t_side_progression_findings",
                "count",
                row["count"],
                row["evidence_strength"],
            )
        )
    findings = pd.DataFrame(rows)
    if findings.empty:
        return empty_key_findings()
    findings["finding_id"] = [f"finding_{index:03d}" for index in range(1, len(findings) + 1)]
    findings["needs_manual_review"] = findings["evidence_strength"] != "strong_candidate"
    findings = findings.groupby("finding_category", group_keys=False).head(top_n)
    return findings[
        [
            "finding_id",
            "finding_category",
            "finding_text",
            "support_table",
            "support_metric",
            "round_count",
            "evidence_strength",
            "needs_manual_review",
        ]
    ].reset_index(drop=True)


def build_manual_review_queue(
    region: pd.DataFrame,
    utility: pd.DataFrame,
    no_plant: pd.DataFrame,
    bomb: pd.DataFrame,
    opponents: pd.DataFrame,
    progression: pd.DataFrame,
    *,
    top_n: int,
) -> pd.DataFrame:
    rows = []
    for _, row in no_plant[no_plant["finding_type"].str.contains("bomb", na=False)].head(3).iterrows():
        rows.append(review_item("high", "No-plant C4 context needs demo inspection", f"t_round_outcome=no_plant and {row['finding_type']}={row['finding_value']}", "t_side_no_plant_failure_findings", "Where is C4 control lost before a valid plant?"))
    for _, row in progression[progression["t_round_outcome"] == "plant_B"].head(3).iterrows():
        rows.append(review_item("high", "Validate recurrent plant_B progression", f"round_progression_signature={row['round_progression_signature']}", "t_side_progression_findings", "Does this signature represent a repeatable B protocol or a noisy grouping?"))
    late_utility = utility[utility["window_start"] >= 95].sort_values("diff_avg_utilities_per_round_A_minus_B", key=lambda values: values.abs(), ascending=False)
    for _, row in late_utility.head(3).iterrows():
        rows.append(review_item("medium", "Late-round A/B utility difference is sparse", f"window_type={row['window_type']}, window={int(row['window_start'])}-{int(row['window_end'])}, region={row['region_group']}", "t_side_ab_utility_differences", "Is late utility planned, reactive, or caused by a small sample?"))
    for _, row in opponents[opponents["tendency_label"] != "balanced_or_unclear"].head(3).iterrows():
        rows.append(review_item("medium", "Opponent tendency differs from the aggregate pattern", f"opponent={row['opponent']}", "t_side_opponent_tendencies", "Does opponent setup plausibly explain the observed tendency?"))
    sparse_region = region[region["evidence_strength"] == "weak_or_sparse"].head(3)
    for _, row in sparse_region.iterrows():
        rows.append(review_item("low", "Regional A/B difference has sparse support", f"window_type={row['window_type']}, window={int(row['window_start'])}-{int(row['window_end'])}, region={row['region_group']}", "t_side_ab_region_differences", "Does manual demo review support this weak candidate?"))
    if not rows:
        rows.append(review_item("low", "No automatic review candidates exceeded current rules", "inspect top findings", "t_side_key_findings", "Which candidate deserves qualitative validation first?"))
    queue = pd.DataFrame(rows).drop_duplicates(["reason", "suggested_filter"]).head(top_n).copy()
    queue["review_id"] = [f"review_{index:03d}" for index in range(1, len(queue) + 1)]
    return queue[["review_id", "priority", "reason", "suggested_filter", "related_table", "expected_question"]]


def build_findings_audit(
    *,
    inputs: dict[str, pd.DataFrame],
    frames: dict[str, pd.DataFrame],
    target_team: str,
    target_map: str,
    min_rounds: int,
    top_n: int,
) -> pd.DataFrame:
    overview = inputs["t_side_eda_overview"].iloc[0]
    timing = frames["t_side_ab_timing_breakpoints"]
    max_window_end = int(timing["window_end"].max()) if not timing.empty else 0
    return pd.DataFrame(
        [
            {
                "audit_id": "t_side_tactical_findings",
                "target_team": target_team,
                "target_map": target_map,
                "total_t_side_rounds": int(overview["total_t_side_rounds"]),
                "plant_A": int(overview["total_plant_A"]),
                "plant_B": int(overview["total_plant_B"]),
                "no_plant": int(overview["total_no_plant"]),
                "unknown": int(overview["total_unknown"]),
                "min_rounds": min_rounds,
                "top_n": top_n,
                "max_window_end": max_window_end,
                "key_findings": len(frames["t_side_key_findings"]),
                "manual_review_items": len(frames["t_side_manual_review_queue"]),
                "status": "ok" if max_window_end == 115 and not frames["t_side_key_findings"].empty else "warning",
                "created_at": now_utc(),
            }
        ]
    )


def build_markdown_report(
    frames: dict[str, pd.DataFrame],
    inputs: dict[str, pd.DataFrame],
    *,
    target_team: str,
    target_map: str,
) -> str:
    overview = inputs["t_side_eda_overview"].iloc[0]
    sections = [
        f"# T-side Tactical Findings -- {target_team} {target_map}",
        "",
        "## Scope",
        "",
        f"This report ranks conservative tactical candidates for {target_team} T-side on {target_map}. It does not claim causality and does not train a model.",
        "",
        "## Data snapshot",
        "",
        f"- T-side rounds: {int(overview['total_t_side_rounds'])}",
        f"- Plant A: {int(overview['total_plant_A'])}",
        f"- Plant B: {int(overview['total_plant_B'])}",
        f"- No plant: {int(overview['total_no_plant'])}",
        f"- Plant rate: {format_percent(overview['plant_rate'])}",
        "",
        "## Main A/B tendencies",
        "",
        markdown_table(frames["t_side_ab_region_differences"], ["window_type", "window_start", "window_end", "region_group", "share_diff_A_minus_B", "evidence_strength"]),
        "",
        "## Timing signals",
        "",
        markdown_table(frames["t_side_ab_timing_breakpoints"].sort_values("combined_signal_score", ascending=False), ["window_type", "window_start", "window_end", "combined_signal_score", "dominant_signal", "signal_period"]),
        "",
        "## Utility signals",
        "",
        markdown_table(frames["t_side_ab_utility_differences"], ["window_type", "window_start", "window_end", "region_group", "diff_avg_utilities_per_round_A_minus_B", "evidence_strength"]),
        "",
        "## No-plant patterns",
        "",
        markdown_table(frames["t_side_no_plant_failure_findings"], ["finding_type", "finding_value", "round_count", "round_share", "evidence_strength"]),
        "",
        "## Bomb carrier and C4 patterns",
        "",
        markdown_table(frames["t_side_bomb_carrier_findings"], ["context_type", "window_start", "window_end", "region_group", "t_round_outcome", "round_count"]),
        "",
        "## Opponent tendencies",
        "",
        markdown_table(frames["t_side_opponent_tendencies"], ["opponent", "total_t_side_rounds", "plant_rate", "no_plant_share", "tendency_label"]),
        "",
        "## Progression signatures",
        "",
        markdown_table(frames["t_side_progression_findings"], ["round_progression_signature", "t_round_outcome", "count", "share", "winrate"]),
        "",
        "## Manual review queue",
        "",
        markdown_table(frames["t_side_manual_review_queue"], ["priority", "reason", "suggested_filter", "expected_question"]),
        "",
        "## Limitations",
        "",
        "- Findings are descriptive candidates derived from the current sample.",
        "- Percentages always require inspection alongside round counts.",
        "- Sparse and late-round signals are explicitly queued for manual demo review.",
        "- CT-side analysis, causal claims, and rounds without a valid A/B label remain outside model scope.",
        "",
        "## Next step",
        "",
        "Build a leakage-controlled baseline A/B model using only high-confidence rows from `round_features_t_side_planted` after manual review of the candidates above.",
        "",
    ]
    return "\n".join(sections)


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    return write_dataframe_outputs({name: frames[name] for name in FINDING_OUTPUT_NAMES}, output_dir, force=force)


def write_markdown_report(report: str, path: Path, *, force: bool) -> None:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(report, encoding="utf-8")


def outcome_frame(summary: pd.DataFrame, outcome: str, keys: list[str], metrics: list[str], suffix: str) -> pd.DataFrame:
    frame = summary[summary["t_round_outcome"] == outcome][[*keys, *metrics]].copy()
    return frame.rename(columns={metric: f"{metric}_{suffix}" for metric in metrics})


def evidence_strength(abs_difference: float, supported_rounds: float, min_rounds: int) -> str:
    if supported_rounds >= min_rounds and abs_difference >= 0.25:
        return "strong_candidate"
    if supported_rounds >= min_rounds and abs_difference >= 0.15:
        return "medium_candidate"
    return "weak_or_sparse"


def sort_by_evidence(frame: pd.DataFrame, *, difference_column: str = "abs_share_diff") -> pd.DataFrame:
    result = frame.copy()
    result["_evidence_rank"] = result["evidence_strength"].map(EVIDENCE_RANK)
    difference = difference_column if difference_column in result.columns else result.columns[0]
    result["_abs_difference"] = result[difference].abs() if pd.api.types.is_numeric_dtype(result[difference]) else 0
    result = result.sort_values(["_evidence_rank", "_abs_difference", "window_start"], ascending=[True, False, True])
    return result.drop(columns=["_evidence_rank", "_abs_difference"]).reset_index(drop=True)


def evidence_sort_key(values: pd.Series) -> pd.Series:
    if values.name == "evidence_strength":
        return values.map(EVIDENCE_RANK)
    return values


def normalize_series(values: pd.Series) -> pd.Series:
    maximum = values.abs().max()
    return values.abs() / maximum if pd.notna(maximum) and maximum > 0 else pd.Series(0.0, index=values.index)


def signal_period(window_type: str, window_start: float, window_end: float) -> str:
    if window_end <= 25:
        return "early_signal"
    if window_type == "cumulative":
        return "mid_round_signal" if window_end <= 65 else "late_round_signal"
    if window_start < 65:
        return "mid_round_signal"
    return "late_round_signal"


def dominant_signal(row: pd.Series) -> str:
    region_score = row["region_signal_score"]
    utility_score = row["utility_signal_score"]
    if abs(region_score - utility_score) <= 0.05:
        return "both"
    return "region" if region_score > utility_score else "utility"


def no_plant_finding(dimension: str, value: str, count: int, share: object, min_rounds: int) -> dict[str, object]:
    evidence = "medium_candidate" if count >= min_rounds else "weak_or_sparse"
    return {
        "t_round_outcome": "no_plant",
        "finding_type": dimension,
        "finding_value": value,
        "round_count": count,
        "round_share": share,
        "evidence_strength": evidence,
        "finding_text": (
            f"No-plant rounds show {dimension.replace('_', ' ')} around {value} in {count} rounds "
            f"({format_percent(share)}), suggesting this context should be manually reviewed."
        ),
    }


def opponent_tendency(row: pd.Series, min_rounds: int) -> str:
    if row["total_t_side_rounds"] >= min_rounds and row["no_plant_share"] >= 0.50:
        return "high_no_plant"
    if row["planted_rounds"] >= min_rounds and row["A_share_when_planted"] >= 0.65:
        return "A_leaning"
    if row["planted_rounds"] >= min_rounds and row["B_share_when_planted"] >= 0.45:
        return "B_leaning"
    return "balanced_or_unclear"


def key_finding(
    category: str,
    text: str,
    support_table: str,
    support_metric: str,
    round_count: object,
    evidence: str,
) -> dict[str, object]:
    return {
        "finding_category": category,
        "finding_text": text,
        "support_table": support_table,
        "support_metric": support_metric,
        "round_count": int(round_count) if pd.notna(round_count) else 0,
        "evidence_strength": evidence,
    }


def review_item(priority: str, reason: str, suggested_filter: str, related_table: str, expected_question: str) -> dict[str, str]:
    return {
        "priority": priority,
        "reason": reason,
        "suggested_filter": suggested_filter,
        "related_table": related_table,
        "expected_question": expected_question,
    }


def window_text(row: pd.Series) -> str:
    start = row.get("window_start")
    end = row.get("window_end")
    if pd.isna(start) or pd.isna(end):
        return "full-round context"
    return f"{row.get('window_type', 'window')} {int(start)}-{int(end)}s"


def normalized_value(value: object) -> str:
    return "UNKNOWN" if pd.isna(value) or str(value).strip() in {"", "None", "nan"} else str(value)


def format_percent(value: object) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{float(value):.1%}"


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 5) -> str:
    return report_markdown_table(frame, columns, top_n=top_n)


def empty_key_findings() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "finding_id",
            "finding_category",
            "finding_text",
            "support_table",
            "support_metric",
            "round_count",
            "evidence_strength",
            "needs_manual_review",
        ]
    )


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("T-side Tactical Findings summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank conservative tactical findings from Stage 5 T-side EDA outputs.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--min-rounds", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=15)
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_t_side_findings(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        min_rounds=args.min_rounds,
        top_n=args.top_n,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
