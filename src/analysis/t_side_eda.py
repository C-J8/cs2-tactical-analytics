from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from src.config.schemas import load_project_config
from src.features.feature_windows import FeatureWindow, configured_feature_windows
from src.features.round_progression import expand_events_to_windows
from src.utils.io import read_catalog, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.reports import now_utc, safe_divide


OUTPUT_NAMES = [
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

NO_PLANT_CONTEXT_COLUMNS = [
    "first_target_team_death_region",
    "last_target_team_death_region",
    "first_contact_region",
    "bomb_drop_region",
    "bomb_last_known_region",
    "max_pressure_region_0_115",
    "max_pressure_region_0_55",
    "final_pressure_region_105_115",
    "round_failure_context",
    "round_outcome_type",
]

LEAKAGE_PATTERNS = [
    "target_site_model_label",
    "target_site_observed",
    "label_source",
    "label_confidence",
    "bombsite",
    "bomb_planted",
    "winner_",
    "round_outcome",
    "round_failure_context",
    "round_end_reason",
    "is_model_ab_candidate",
]

IDENTIFIER_COLUMNS = {
    "round_feature_id",
    "round_id",
    "parse_id",
    "dem_file_id",
    "series_id",
    "local_archive_id",
    "dataset_type",
}


def run_t_side_eda(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    inputs = load_gold_inputs(gold_dir)
    windows = configured_feature_windows(project.feature_windows)

    rounds = prepare_t_side_rounds(
        inputs["t_side_all"],
        inputs["round_state"],
        target_team=target_team,
        target_map=target_map,
    )
    validate_planted_input(inputs["t_side_planted"])

    frames = {
        "t_side_eda_overview": build_overview(rounds),
        "t_side_site_distribution": build_site_distribution(rounds),
        "t_side_opponent_summary": build_opponent_summary(rounds),
        "t_side_window_region_summary": build_window_region_summary(inputs["region_timeline"], rounds),
        "t_side_window_utility_summary": build_window_utility_summary(inputs["utility_events"], rounds, windows),
        "t_side_no_plant_summary": build_no_plant_summary(inputs["outcome_context"], rounds),
        "t_side_death_summary": build_death_summary(inputs["death_context"], rounds, windows),
        "t_side_bomb_carrier_summary": build_bomb_carrier_summary(inputs["bomb_timeline"], inputs["outcome_context"], rounds),
        "t_side_progression_signature_summary": build_progression_signature_summary(inputs["outcome_context"], rounds),
        "t_side_feature_catalog": build_feature_catalog(inputs["t_side_all"].columns, windows),
    }
    frames["t_side_eda_audit"] = build_eda_audit(
        inputs=inputs,
        rounds=rounds,
        frames=frames,
        windows=windows,
        target_team=target_team,
        target_map=target_map,
    )

    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = gold_dir / "analysis" / "t_side_tactical_eda"
        outputs = write_outputs(frames, output_dir, force=force)

    summary = {
        "total_t_side_rounds": len(rounds),
        "plant_A": int((rounds["t_round_outcome"] == "plant_A").sum()),
        "plant_B": int((rounds["t_round_outcome"] == "plant_B").sum()),
        "no_plant": int((rounds["t_round_outcome"] == "no_plant").sum()),
        "unknown": int((rounds["t_round_outcome"] == "unknown").sum()),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def load_gold_inputs(gold_dir: Path) -> dict[str, pd.DataFrame]:
    paths = {
        "t_side_all": gold_dir / "round_features" / "round_features_t_side_all.parquet",
        "t_side_planted": gold_dir / "round_features" / "round_features_t_side_planted.parquet",
        "region_timeline": gold_dir / "round_progression" / "round_region_timeline.parquet",
        "death_context": gold_dir / "round_progression" / "death_context_by_round.parquet",
        "bomb_timeline": gold_dir / "round_progression" / "bomb_carrier_timeline.parquet",
        "outcome_context": gold_dir / "round_progression" / "round_outcome_context.parquet",
        "round_state": gold_dir / "round_state" / "round_state_resolved.parquet",
    }
    inputs = {name: read_catalog(path) for name, path in paths.items()}
    utility_path = gold_dir / "utility_events" / "utility_events.parquet"
    inputs["utility_events"] = read_catalog(utility_path) if utility_path.exists() else pd.DataFrame()
    return inputs


def prepare_t_side_rounds(
    t_side_all: pd.DataFrame,
    round_state: pd.DataFrame,
    *,
    target_team: str,
    target_map: str,
) -> pd.DataFrame:
    rounds = t_side_all.copy()
    rounds = rounds[
        rounds["target_team"].astype(str).str.casefold().eq(target_team.casefold())
        & rounds["map_name"].astype(str).str.casefold().eq(target_map.casefold())
        & rounds["target_team_side"].astype(str).str.upper().eq("T")
    ].copy()

    state_columns = [
        "round_id",
        "team_t",
        "team_ct",
        "target_team_planted",
        "opponent_planted",
        "planting_team",
    ]
    available = [column for column in state_columns if column in round_state.columns]
    if "round_id" in available:
        rounds = rounds.merge(round_state[available].drop_duplicates("round_id"), on="round_id", how="left")

    if "team_ct" in rounds.columns:
        unresolved = rounds["opponent"].isna() | rounds["opponent"].astype(str).str.casefold().isin({"", "unknown", "none", "nan"})
        rounds.loc[unresolved, "opponent"] = rounds.loc[unresolved, "team_ct"]
    rounds["opponent"] = rounds["opponent"].fillna("unknown")
    rounds["t_round_outcome"] = rounds.apply(classify_t_round_outcome, axis=1)
    rounds["target_team_win"] = rounds.apply(is_target_team_win, axis=1)
    return rounds


def classify_t_round_outcome(row: pd.Series) -> str:
    label = str(row.get("target_site_model_label") or "").upper()
    confidence = str(row.get("label_confidence") or "").lower()
    if label == "A" and confidence == "high":
        return "plant_A"
    if label == "B" and confidence == "high":
        return "plant_B"
    target_planted = bool(row.get("target_team_planted")) if pd.notna(row.get("target_team_planted")) else False
    bomb_planted = bool(row.get("bomb_planted")) if pd.notna(row.get("bomb_planted")) else False
    if label not in {"A", "B"} and (not bomb_planted or not target_planted):
        return "no_plant"
    return "unknown"


def is_target_team_win(row: pd.Series) -> bool:
    winner_team = str(row.get("winner_team") or "").casefold()
    target_team = str(row.get("target_team") or "").casefold()
    if winner_team and target_team and winner_team not in {"unknown", "none", "nan"}:
        return winner_team == target_team
    return str(row.get("winner_side") or "").upper() == "T"


def validate_planted_input(t_side_planted: pd.DataFrame) -> None:
    if t_side_planted.empty:
        return
    valid = t_side_planted["target_site_model_label"].isin(["A", "B"]) & t_side_planted["label_confidence"].eq("high")
    if not bool(valid.all()):
        raise ValueError("round_features_t_side_planted contains rows without high-confidence A/B labels")


def build_overview(rounds: pd.DataFrame) -> pd.DataFrame:
    counts = rounds["t_round_outcome"].value_counts()
    total = len(rounds)
    planted = int(counts.get("plant_A", 0) + counts.get("plant_B", 0))
    overview = {
        "total_t_side_rounds": total,
        "total_plant_A": int(counts.get("plant_A", 0)),
        "total_plant_B": int(counts.get("plant_B", 0)),
        "total_no_plant": int(counts.get("no_plant", 0)),
        "total_unknown": int(counts.get("unknown", 0)),
        "plant_rate": safe_divide(planted, total),
        "A_share_when_planted": safe_divide(int(counts.get("plant_A", 0)), planted),
        "B_share_when_planted": safe_divide(int(counts.get("plant_B", 0)), planted),
        "winrate_t_side": mean_bool(rounds["target_team_win"]),
        "winrate_plant_A": outcome_winrate(rounds, "plant_A"),
        "winrate_plant_B": outcome_winrate(rounds, "plant_B"),
        "winrate_no_plant": outcome_winrate(rounds, "no_plant"),
        "opponents": int(rounds["opponent"].nunique(dropna=True)),
        "series": int(rounds["series_id"].nunique(dropna=True)),
        "demos": int(rounds["dem_file_id"].nunique(dropna=True)) if "dem_file_id" in rounds.columns else 0,
    }
    return pd.DataFrame([overview])


def build_site_distribution(rounds: pd.DataFrame) -> pd.DataFrame:
    total = len(rounds)
    planted = int(rounds["t_round_outcome"].isin(["plant_A", "plant_B"]).sum())
    rows = []
    for outcome in ["plant_A", "plant_B", "no_plant", "unknown"]:
        group = rounds[rounds["t_round_outcome"] == outcome]
        rows.append(
            {
                "t_round_outcome": outcome,
                "round_count": len(group),
                "round_share": safe_divide(len(group), total),
                "share_when_planted": safe_divide(len(group), planted) if outcome in {"plant_A", "plant_B"} else None,
                "winrate": mean_bool(group["target_team_win"]),
            }
        )
    return pd.DataFrame(rows)


def build_opponent_summary(rounds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for opponent, group in rounds.groupby("opponent", dropna=False):
        counts = group["t_round_outcome"].value_counts()
        planted = int(counts.get("plant_A", 0) + counts.get("plant_B", 0))
        rows.append(
            {
                "opponent": opponent,
                "total_t_side_rounds": len(group),
                "plant_A": int(counts.get("plant_A", 0)),
                "plant_B": int(counts.get("plant_B", 0)),
                "no_plant": int(counts.get("no_plant", 0)),
                "unknown": int(counts.get("unknown", 0)),
                "plant_rate": safe_divide(planted, len(group)),
                "A_share_when_planted": safe_divide(int(counts.get("plant_A", 0)), planted),
                "B_share_when_planted": safe_divide(int(counts.get("plant_B", 0)), planted),
                "winrate": mean_bool(group["target_team_win"]),
                "winrate_plant_A": outcome_winrate(group, "plant_A"),
                "winrate_plant_B": outcome_winrate(group, "plant_B"),
                "winrate_no_plant": outcome_winrate(group, "no_plant"),
            }
        )
    return pd.DataFrame(rows).sort_values("total_t_side_rounds", ascending=False).reset_index(drop=True)


def build_window_region_summary(timeline: pd.DataFrame, rounds: pd.DataFrame) -> pd.DataFrame:
    if timeline.empty:
        return pd.DataFrame()
    columns = [
        "round_feature_id",
        "window_type",
        "window_start",
        "window_end",
        "region_group",
        "players_count_avg",
        "players_count_max",
        "time_spent_total",
    ]
    data = timeline[[column for column in columns if column in timeline.columns]].copy()
    data = data[data["round_feature_id"].isin(rounds["round_feature_id"])].merge(
        rounds[["round_feature_id", "t_round_outcome"]], on="round_feature_id", how="inner"
    )
    per_round = (
        data.groupby(["round_feature_id", "window_type", "window_start", "window_end", "region_group", "t_round_outcome"], dropna=False)
        .agg(
            players_count_avg=("players_count_avg", "mean"),
            players_count_max=("players_count_max", "max"),
            time_spent_total=("time_spent_total", "sum"),
        )
        .reset_index()
    )
    summary = (
        per_round.groupby(["window_type", "window_start", "window_end", "region_group", "t_round_outcome"], dropna=False)
        .agg(
            round_count=("round_feature_id", "nunique"),
            avg_players_count=("players_count_avg", "mean"),
            max_players_count=("players_count_max", "max"),
            avg_time_spent=("time_spent_total", "mean"),
        )
        .reset_index()
    )
    denominators = rounds["t_round_outcome"].value_counts().to_dict()
    summary["round_share_with_region"] = summary.apply(
        lambda row: safe_divide(row["round_count"], denominators.get(row["t_round_outcome"], 0)), axis=1
    )
    return summary.sort_values(["window_type", "window_start", "t_round_outcome", "round_count"], ascending=[True, True, True, False]).reset_index(drop=True)


def build_window_utility_summary(utility_events: pd.DataFrame, rounds: pd.DataFrame, windows: list[FeatureWindow]) -> pd.DataFrame:
    if utility_events.empty:
        return empty_utility_summary()
    events = utility_events[utility_events["round_feature_id"].isin(rounds["round_feature_id"])].copy()
    events = events.merge(rounds[["round_feature_id", "t_round_outcome"]], on="round_feature_id", how="inner")
    events["region_group"] = events.apply(utility_region_group, axis=1)
    expanded = expand_events_to_windows(events, windows)
    if expanded.empty:
        return empty_utility_summary()
    denominators = rounds["t_round_outcome"].value_counts().to_dict()
    rows = []
    keys = ["window_type", "window_start", "window_end", "region_group", "t_round_outcome"]
    for key, group in expanded.groupby(keys, dropna=False):
        window_type, window_start, window_end, region_group, outcome = key
        denominator = denominators.get(outcome, 0)
        counts = group["utility_type"].value_counts()
        round_count = group["round_feature_id"].nunique()
        rows.append(
            {
                "window_type": window_type,
                "window_start": window_start,
                "window_end": window_end,
                "region_group": region_group,
                "t_round_outcome": outcome,
                "total_utilities": len(group),
                "avg_utilities_per_round": safe_divide(len(group), denominator),
                "smokes_per_round": safe_divide(int(counts.get("smoke", 0)), denominator),
                "molotovs_per_round": safe_divide(int(counts.get("molotov", 0)), denominator),
                "flashes_per_round": safe_divide(int(counts.get("flash", 0)), denominator),
                "he_per_round": safe_divide(int(counts.get("he", 0)), denominator),
                "other_utilities_per_round": safe_divide(int((~group["utility_type"].isin(["smoke", "molotov", "flash", "he"])).sum()), denominator),
                "rounds_with_utility": round_count,
                "round_share_with_utility": safe_divide(round_count, denominator),
            }
        )
    return pd.DataFrame(rows).sort_values(["window_type", "window_start", "t_round_outcome", "total_utilities"], ascending=[True, True, True, False]).reset_index(drop=True)


def build_no_plant_summary(outcome_context: pd.DataFrame, rounds: pd.DataFrame) -> pd.DataFrame:
    no_plant = rounds[rounds["t_round_outcome"] == "no_plant"]
    data = outcome_context[outcome_context["round_feature_id"].isin(no_plant["round_feature_id"])].copy()
    if data.empty:
        return pd.DataFrame(columns=[*NO_PLANT_CONTEXT_COLUMNS, "round_count", "round_share"])
    available = [column for column in NO_PLANT_CONTEXT_COLUMNS if column in data.columns]
    data[available] = data[available].fillna("UNKNOWN")
    summary = data.groupby(available, dropna=False).size().reset_index(name="round_count")
    summary["round_share"] = summary["round_count"].map(lambda value: safe_divide(value, len(no_plant)))
    return summary.sort_values("round_count", ascending=False).reset_index(drop=True)


def build_death_summary(death_context: pd.DataFrame, rounds: pd.DataFrame, windows: list[FeatureWindow]) -> pd.DataFrame:
    if death_context.empty:
        return pd.DataFrame()
    deaths = death_context[death_context["round_feature_id"].isin(rounds["round_feature_id"])].copy()
    deaths = deaths.merge(rounds[["round_feature_id", "t_round_outcome"]], on="round_feature_id", how="inner")
    records = []
    interval_windows = [window for window in windows if window.window_type == "interval"]
    for round_feature_id, group in deaths.groupby("round_feature_id"):
        group = group.sort_values(["death_order", "death_tick"])
        outcome = group.iloc[0]["t_round_outcome"]
        candidates = {
            "first_contact": group.head(1),
            "first_target_team_death": group[group["is_target_team_death"] == True].head(1),  # noqa: E712
            "first_opponent_death": group[group["is_opponent_death"] == True].head(1),  # noqa: E712
        }
        for death_type, candidate in candidates.items():
            if candidate.empty:
                continue
            event = candidate.iloc[0]
            feature_window = window_for_seconds(event.get("seconds_from_freeze_end"), interval_windows)
            records.append(
                {
                    "round_feature_id": round_feature_id,
                    "death_type": death_type,
                    "region_group": event.get("death_region_group") or "UNKNOWN",
                    "t_round_outcome": outcome,
                    "window_type": feature_window.window_type if feature_window else None,
                    "window_start": feature_window.start if feature_window else None,
                    "window_end": feature_window.end if feature_window else None,
                    "is_no_plant": outcome == "no_plant",
                }
            )
    if not records:
        return pd.DataFrame()
    records_df = pd.DataFrame(records)
    summary = (
        records_df.groupby(
            ["death_type", "region_group", "t_round_outcome", "window_type", "window_start", "window_end", "is_no_plant"],
            dropna=False,
        )["round_feature_id"]
        .nunique()
        .reset_index(name="round_count")
    )
    denominators = rounds["t_round_outcome"].value_counts().to_dict()
    summary["round_share"] = summary.apply(
        lambda row: safe_divide(row["round_count"], denominators.get(row["t_round_outcome"], 0)), axis=1
    )
    return summary.sort_values(["death_type", "t_round_outcome", "round_count"], ascending=[True, True, False]).reset_index(drop=True)


def build_bomb_carrier_summary(bomb_timeline: pd.DataFrame, outcome_context: pd.DataFrame, rounds: pd.DataFrame) -> pd.DataFrame:
    records = []
    round_outcomes = rounds.set_index("round_feature_id")["t_round_outcome"].to_dict()
    timeline = bomb_timeline[bomb_timeline["round_feature_id"].isin(rounds["round_feature_id"])].copy()
    for _, row in timeline.iterrows():
        outcome = round_outcomes.get(row["round_feature_id"], "unknown")
        region = row.get("bomb_carrier_region_group")
        if pd.notna(region):
            records.append(bomb_record(row, outcome, "carrier_region", region))
        if bool(row.get("bomb_dropped")):
            records.append(bomb_record(row, outcome, "bomb_drop_region", row.get("bomb_drop_region_group") or "UNKNOWN"))

    context = outcome_context[outcome_context["round_feature_id"].isin(rounds["round_feature_id"])].copy()
    for _, row in context.iterrows():
        outcome = round_outcomes.get(row["round_feature_id"], "unknown")
        for context_type, column in [("last_known_region", "bomb_last_known_region"), ("bomb_drop_region", "bomb_drop_region")]:
            region = row.get(column)
            if pd.notna(region):
                records.append(
                    {
                        "round_feature_id": row["round_feature_id"],
                        "context_type": context_type,
                        "window_type": None,
                        "window_start": None,
                        "window_end": None,
                        "region_group": region,
                        "t_round_outcome": outcome,
                        "is_late_round": False,
                    }
                )
    if not records:
        return pd.DataFrame()
    records_df = pd.DataFrame(records)
    summary = (
        records_df.groupby(
            ["context_type", "window_type", "window_start", "window_end", "region_group", "t_round_outcome", "is_late_round"],
            dropna=False,
        )["round_feature_id"]
        .nunique()
        .reset_index(name="round_count")
    )
    denominators = rounds["t_round_outcome"].value_counts().to_dict()
    summary["round_share"] = summary.apply(
        lambda row: safe_divide(row["round_count"], denominators.get(row["t_round_outcome"], 0)), axis=1
    )
    return summary.sort_values(["is_late_round", "window_start", "round_count"], ascending=[False, True, False]).reset_index(drop=True)


def bomb_record(row: pd.Series, outcome: str, context_type: str, region: object) -> dict[str, object]:
    window_start = row.get("window_start")
    window_end = row.get("window_end")
    return {
        "round_feature_id": row["round_feature_id"],
        "context_type": context_type,
        "window_type": row.get("window_type"),
        "window_start": window_start,
        "window_end": window_end,
        "region_group": region,
        "t_round_outcome": outcome,
        "is_late_round": bool(pd.notna(window_start) and float(window_start) >= 95),
    }


def build_progression_signature_summary(outcome_context: pd.DataFrame, rounds: pd.DataFrame) -> pd.DataFrame:
    columns = ["round_feature_id", "round_progression_signature"]
    data = outcome_context[[column for column in columns if column in outcome_context.columns]].copy()
    data = data[data["round_feature_id"].isin(rounds["round_feature_id"])].merge(
        rounds[["round_feature_id", "t_round_outcome", "target_team_win", "opponent"]], on="round_feature_id", how="inner"
    )
    if data.empty:
        return pd.DataFrame()
    summary = (
        data.groupby(["round_progression_signature", "t_round_outcome"], dropna=False)
        .agg(
            count=("round_feature_id", "nunique"),
            winrate=("target_team_win", "mean"),
            opponents=("opponent", lambda values: ", ".join(sorted(set(str(value) for value in values if pd.notna(value))))),
        )
        .reset_index()
    )
    denominators = rounds["t_round_outcome"].value_counts().to_dict()
    summary["share"] = summary.apply(
        lambda row: safe_divide(row["count"], denominators.get(row["t_round_outcome"], 0)), axis=1
    )
    return summary.sort_values(["t_round_outcome", "count"], ascending=[True, False]).reset_index(drop=True)


def build_feature_catalog(columns: pd.Index | list[str], windows: list[FeatureWindow]) -> pd.DataFrame:
    configured = {(window.start, window.end): window.window_type for window in windows}
    rows = []
    for column in columns:
        window_start, window_end = infer_window_bounds(column)
        window_type = infer_window_type(window_start, window_end, configured)
        feature_group = infer_feature_group(column)
        leakage_reason = leakage_note(column)
        usable = leakage_reason is None and column not in IDENTIFIER_COLUMNS and feature_group not in {"audit", "label", "outcome"}
        notes = leakage_reason or ("identifier/metadata column" if column in IDENTIFIER_COLUMNS else None)
        rows.append(
            {
                "column_name": column,
                "inferred_feature_group": feature_group,
                "window_start": window_start,
                "window_end": window_end,
                "window_type": window_type,
                "usable_for_future_model": bool(usable),
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def infer_feature_group(column: str) -> str:
    name = column.casefold()
    if any(token in name for token in ["target_site", "label_"]):
        return "label"
    if any(token in name for token in ["players_", "time_", "team_center", "team_spread", "pairwise", "region"]):
        return "region_position"
    if any(token in name for token in ["smoke", "molotov", "flash", "utility", "he_", "decoy"]):
        return "utility"
    if "bomb" in name:
        return "bomb"
    if "death" in name or "first_contact" in name:
        return "death"
    if any(token in name for token in ["winner", "outcome", "failure"]):
        return "outcome"
    if any(token in name for token in ["quality", "notes", "audit", "dataset_type", "candidate"]):
        return "audit"
    if any(token in name for token in ["round", "team", "opponent", "map", "series", "parse", "half", "score"]):
        return "context"
    return "unknown"


def infer_window_bounds(column: str) -> tuple[int | None, int | None]:
    match = re.search(r"_(\d+)_(\d+)$", column)
    return (int(match.group(1)), int(match.group(2))) if match else (None, None)


def infer_window_type(start: int | None, end: int | None, configured: dict[tuple[int, int], str]) -> str | None:
    if start is None or end is None:
        return None
    if (start, end) == (0, 15):
        return "both"
    if (start, end) == (0, 20):
        return "legacy"
    return configured.get((start, end), "cumulative" if start == 0 else "interval")


def leakage_note(column: str) -> str | None:
    name = column.casefold()
    if any(pattern.casefold() in name for pattern in LEAKAGE_PATTERNS):
        return "target leakage or post-round/post-plant information"
    return None


def build_eda_audit(
    *,
    inputs: dict[str, pd.DataFrame],
    rounds: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    windows: list[FeatureWindow],
    target_team: str,
    target_map: str,
) -> pd.DataFrame:
    planted = inputs["t_side_planted"]
    planted_valid = planted.empty or bool(
        (planted["target_site_model_label"].isin(["A", "B"]) & planted["label_confidence"].eq("high")).all()
    )
    max_window_end = max((window.end for window in windows), default=0)
    expected_rounds = int(
        (
            inputs["t_side_all"]["target_team"].astype(str).str.casefold().eq(target_team.casefold())
            & inputs["t_side_all"]["map_name"].astype(str).str.casefold().eq(target_map.casefold())
            & inputs["t_side_all"]["target_team_side"].astype(str).str.upper().eq("T")
        ).sum()
    )
    output_rows = {f"rows_{name}": len(frame) for name, frame in frames.items()}
    return pd.DataFrame(
        [
            {
                "audit_id": "t_side_tactical_eda",
                "target_team": target_team,
                "target_map": target_map,
                "input_t_side_rows": len(inputs["t_side_all"]),
                "eligible_t_side_rows": len(rounds),
                "expected_t_side_rows": expected_rounds,
                "ct_rows_in_analysis": int((rounds["target_team_side"].astype(str).str.upper() == "CT").sum()),
                "planted_input_rows": len(planted),
                "planted_input_all_high_confidence": planted_valid,
                "unknown_outcome_rows": int((rounds["t_round_outcome"] == "unknown").sum()),
                "interval_windows": sum(window.window_type == "interval" for window in windows),
                "cumulative_windows": sum(window.window_type == "cumulative" for window in windows),
                "max_window_end": max_window_end,
                "output_tables": len(frames) + 1,
                "status": "ok" if planted_valid and max_window_end == 115 and len(rounds) == expected_rounds else "warning",
                "created_at": now_utc(),
                **output_rows,
            }
        ]
    )


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    return write_dataframe_outputs({name: frames[name] for name in OUTPUT_NAMES}, output_dir, force=force)


def utility_region_group(row: pd.Series) -> str:
    end_region = str(row.get("end_region_group") or "")
    if end_region and end_region.upper() != "UNKNOWN":
        return end_region
    throw_region = str(row.get("throw_region_group") or "")
    return throw_region if throw_region else "UNKNOWN"


def window_for_seconds(value: object, windows: list[FeatureWindow]) -> FeatureWindow | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    for feature_window in windows:
        if feature_window.start <= seconds < feature_window.end:
            return feature_window
    return None


def outcome_winrate(rounds: pd.DataFrame, outcome: str) -> float | None:
    return mean_bool(rounds.loc[rounds["t_round_outcome"] == outcome, "target_team_win"])


def mean_bool(values: pd.Series) -> float | None:
    return float(values.astype(float).mean()) if not values.empty else None


def empty_utility_summary() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "window_type",
            "window_start",
            "window_end",
            "region_group",
            "t_round_outcome",
            "total_utilities",
            "avg_utilities_per_round",
            "smokes_per_round",
            "molotovs_per_round",
            "flashes_per_round",
            "he_per_round",
            "other_utilities_per_round",
            "rounds_with_utility",
            "round_share_with_utility",
        ]
    )


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("T-side Tactical EDA summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build auditable Vitality T-side Mirage tactical EDA tables.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_t_side_eda(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
