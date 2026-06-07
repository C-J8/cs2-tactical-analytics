from __future__ import annotations

import pandas as pd

from src.config.schemas import FeatureWindowsConfig
from src.features.feature_windows import FeatureWindow, interval_feature_windows

PROGRESSION_WINDOWS = interval_feature_windows(FeatureWindowsConfig())
PRESSURE_GROUPS = {"MID_CONTROL", "A_PRESSURE", "B_PRESSURE", "BOMB_SITE_A", "BOMB_SITE_B"}


def build_round_region_timeline(
    region_presence: pd.DataFrame,
    round_features: pd.DataFrame,
    utility_events: pd.DataFrame,
    death_context: pd.DataFrame,
    bomb_carrier_timeline: pd.DataFrame,
    *,
    windows: list[FeatureWindow] | None = None,
) -> pd.DataFrame:
    if region_presence.empty:
        return empty_region_timeline()
    windows = windows or PROGRESSION_WINDOWS
    timeline = region_presence.merge(
        round_features[["round_feature_id", "opponent", "target_team_side"]],
        on="round_feature_id",
        how="left",
    )
    utility_counts = aggregate_utility_to_region(utility_events, windows)
    death_counts = aggregate_deaths_to_region(death_context, windows)
    bomb_counts = aggregate_bomb_to_region(bomb_carrier_timeline)
    for frame in [utility_counts, death_counts, bomb_counts]:
        if not frame.empty:
            timeline = timeline.merge(frame, on=["round_feature_id", "window_type", "window_start", "window_end", "region_group"], how="left")
    for column in ["utility_events_to_region", "target_team_deaths_in_region", "opponent_deaths_in_region", "first_contact_in_region", "bomb_carrier_in_region"]:
        if column not in timeline.columns:
            timeline[column] = 0
        timeline[column] = timeline[column].fillna(0)
    return timeline[
        [
            "round_feature_id",
            "round_id",
            "series_id",
            "target_team",
            "opponent",
            "map_name",
            "target_team_side",
            "window_type",
            "window_start",
            "window_end",
            "region_name",
            "region_group",
            "players_count_avg",
            "players_count_max",
            "unique_players_count",
            "time_spent_total",
            "bomb_carrier_in_region",
            "utility_events_to_region",
            "target_team_deaths_in_region",
            "opponent_deaths_in_region",
            "first_contact_in_region",
        ]
    ]


def build_round_outcome_context(
    round_features: pd.DataFrame,
    timeline: pd.DataFrame,
    death_context: pd.DataFrame,
    bomb_carrier_timeline: pd.DataFrame,
    *,
    windows: list[FeatureWindow] | None = None,
) -> pd.DataFrame:
    windows = windows or PROGRESSION_WINDOWS
    rows = []
    for _, row in round_features.iterrows():
        round_feature_id = row["round_feature_id"]
        round_timeline = timeline[timeline["round_feature_id"] == round_feature_id] if "round_feature_id" in timeline.columns else pd.DataFrame()
        deaths = death_context[death_context["round_feature_id"] == round_feature_id] if not death_context.empty else pd.DataFrame()
        bomb = bomb_carrier_timeline[bomb_carrier_timeline["round_feature_id"] == round_feature_id] if not bomb_carrier_timeline.empty else pd.DataFrame()
        planted_site = row.get("target_site_model_label")
        interval_windows = [window for window in windows if window.window_type == "interval"]
        signature = build_progression_signature(round_timeline, planted_site, windows=interval_windows)
        first_target_death = first_region(deaths[deaths["is_target_team_death"] == True], "death_region_group") if not deaths.empty else None  # noqa: E712
        last_target_death = last_region(deaths[deaths["is_target_team_death"] == True], "death_region_group") if not deaths.empty else None  # noqa: E712
        first_contact = first_region(deaths, "death_region_group") if not deaths.empty else None
        bomb_last = last_region(bomb, "bomb_carrier_region_group") if not bomb.empty else None
        bomb_drop = first_region(bomb[bomb["bomb_dropped"] == True], "bomb_drop_region_group") if not bomb.empty else None  # noqa: E712
        context_row = {
            "round_feature_id": round_feature_id,
            "round_id": row.get("round_id"),
            "series_id": row.get("series_id"),
            "target_team": row.get("target_team"),
            "opponent": row.get("opponent"),
            "map_name": row.get("map_name"),
            "target_team_side": row.get("target_team_side"),
            "bomb_planted": row.get("bomb_planted"),
            "target_site_model_label": planted_site,
            "winner_team": row.get("winner_team"),
            "winner_side": row.get("winner_side"),
            "round_end_reason": row.get("round_end_reason") or row.get("reason"),
            "last_target_team_death_region": last_target_death,
            "first_target_team_death_region": first_target_death,
            "first_contact_region": first_contact,
            "max_pressure_region_0_115": dominant_region(round_timeline, 0, 115, window_type="cumulative"),
            "max_pressure_region_0_55": dominant_region(round_timeline, 0, 55, window_type="cumulative"),
            "final_pressure_region_105_115": dominant_region(round_timeline, 105, 115, window_type="interval"),
            "max_pressure_region_0_20": dominant_region(round_timeline, 0, 20),
            "max_pressure_region_0_30": dominant_region(round_timeline, 0, 30),
            "final_pressure_region_20_30": dominant_region(round_timeline, 20, 30),
            "bomb_last_known_region": bomb_last,
            "bomb_drop_region": bomb_drop,
            "round_progression_signature": signature,
            "round_failure_context": build_failure_context(row, first_target_death, bomb_drop),
            "round_outcome_type": classify_outcome(row, bomb_drop),
        }
        context_row.update(bomb_carrier_region_columns(bomb, windows))
        rows.append(context_row)
    return pd.DataFrame(rows)


def build_progression_signature(round_timeline: pd.DataFrame, planted_site: object = None, *, windows: list[FeatureWindow] | None = None) -> str:
    parts = []
    for feature_window in windows or PROGRESSION_WINDOWS:
        region = dominant_region(round_timeline, feature_window.start, feature_window.end, window_type=feature_window.window_type)
        if region:
            parts.append(region)
    if planted_site in {"A", "B"}:
        parts.append(f"PLANT_{planted_site}")
    elif not parts:
        parts.append("UNKNOWN")
    return ">".join(parts)


def classify_outcome(row: pd.Series, bomb_drop_region: str | None) -> str:
    label = row.get("target_site_model_label")
    if label == "A":
        return "plant_A"
    if label == "B":
        return "plant_B"
    winner_side = str(row.get("winner_side") or "").lower()
    target_side = str(row.get("target_team_side") or "").lower()
    if bomb_drop_region:
        return "bomb_lost_before_plant"
    if winner_side == target_side:
        return "no_plant_target_team_win"
    if winner_side:
        return "no_plant_target_team_loss"
    return "unknown"


def build_failure_context(row: pd.Series, first_target_death: str | None, bomb_drop_region: str | None) -> str | None:
    if row.get("target_site_model_label") in {"A", "B"}:
        return None
    if bomb_drop_region:
        return f"bomb_lost_{bomb_drop_region}"
    if first_target_death:
        return f"first_target_death_{first_target_death}"
    return "no_plant_context_unknown"


def bomb_carrier_region_columns(bomb: pd.DataFrame, windows: list[FeatureWindow]) -> dict[str, object]:
    columns = {}
    for feature_window in windows:
        if feature_window.window_type != "interval":
            continue
        window = bomb[
            (bomb["window_type"] == feature_window.window_type)
            & (bomb["window_start"] == feature_window.start)
            & (bomb["window_end"] == feature_window.end)
        ] if not bomb.empty and "window_type" in bomb.columns else pd.DataFrame()
        columns[f"bomb_carrier_region_{feature_window.suffix}"] = last_region(window, "bomb_carrier_region_group") if not window.empty else None
    return columns


def dominant_region(round_timeline: pd.DataFrame, window_start: int, window_end: int, *, window_type: str | None = None) -> str | None:
    if round_timeline.empty or not {"window_start", "window_end", "region_group", "time_spent_total"}.issubset(round_timeline.columns):
        return None
    window = round_timeline[(round_timeline["window_start"] >= window_start) & (round_timeline["window_end"] <= window_end)]
    if window_type and "window_type" in window.columns:
        window = window[window["window_type"] == window_type]
    if window.empty:
        return None
    pressure = window[window["region_group"].isin(PRESSURE_GROUPS)]
    source = pressure if not pressure.empty else window
    grouped = source.groupby("region_group")["time_spent_total"].sum().sort_values(ascending=False)
    return str(grouped.index[0]) if not grouped.empty else None


def aggregate_utility_to_region(utility_events: pd.DataFrame, windows: list[FeatureWindow]) -> pd.DataFrame:
    if utility_events.empty:
        return pd.DataFrame()
    events = expand_events_to_windows(utility_events, windows)
    if events.empty:
        return pd.DataFrame()
    return (
        events.groupby(["round_feature_id", "window_type", "window_start", "window_end", "end_region_group"])
        .size()
        .reset_index(name="utility_events_to_region")
        .rename(columns={"end_region_group": "region_group"})
    )


def aggregate_deaths_to_region(death_context: pd.DataFrame, windows: list[FeatureWindow]) -> pd.DataFrame:
    if death_context.empty:
        return pd.DataFrame()
    deaths = expand_events_to_windows(death_context, windows)
    if deaths.empty:
        return pd.DataFrame()
    grouped = deaths.groupby(["round_feature_id", "window_type", "window_start", "window_end", "death_region_group"])
    result = grouped.agg(
        target_team_deaths_in_region=("is_target_team_death", "sum"),
        opponent_deaths_in_region=("is_opponent_death", "sum"),
        first_contact_in_region=("is_first_death", "sum"),
    ).reset_index()
    return result.rename(columns={"death_region_group": "region_group"})


def aggregate_bomb_to_region(bomb_timeline: pd.DataFrame) -> pd.DataFrame:
    if bomb_timeline.empty:
        return pd.DataFrame()
    return (
        bomb_timeline.groupby(["round_feature_id", "window_type", "window_start", "window_end", "bomb_carrier_region_group"])
        .size()
        .reset_index(name="bomb_carrier_in_region")
        .rename(columns={"bomb_carrier_region_group": "region_group"})
    )


def expand_events_to_windows(events: pd.DataFrame, windows: list[FeatureWindow]) -> pd.DataFrame:
    rows = []
    for _, event in events.iterrows():
        try:
            seconds = float(event.get("seconds_from_freeze_end"))
        except (TypeError, ValueError):
            continue
        for feature_window in windows:
            if feature_window.start <= seconds < feature_window.end:
                rows.append({**event.to_dict(), "window_type": feature_window.window_type, "window_start": feature_window.start, "window_end": feature_window.end})
    return pd.DataFrame(rows)


def first_region(df: pd.DataFrame, column: str) -> str | None:
    if df.empty or column not in df.columns:
        return None
    value = df.sort_values(df.columns.intersection(["death_order", "window_start"]).tolist()).iloc[0].get(column)
    return None if pd.isna(value) else str(value)


def last_region(df: pd.DataFrame, column: str) -> str | None:
    if df.empty or column not in df.columns:
        return None
    value = df.sort_values(df.columns.intersection(["death_order", "window_start"]).tolist()).iloc[-1].get(column)
    return None if pd.isna(value) else str(value)


def empty_region_timeline() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "round_feature_id",
            "round_id",
            "series_id",
            "target_team",
            "opponent",
            "map_name",
            "target_team_side",
            "window_type",
            "window_start",
            "window_end",
            "region_name",
            "region_group",
            "players_count_avg",
            "players_count_max",
            "unique_players_count",
            "time_spent_total",
            "bomb_carrier_in_region",
            "utility_events_to_region",
            "target_team_deaths_in_region",
            "opponent_deaths_in_region",
            "first_contact_in_region",
        ]
    )
