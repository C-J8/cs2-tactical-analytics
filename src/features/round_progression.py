from __future__ import annotations

import pandas as pd


PROGRESSION_WINDOWS = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30)]
PRESSURE_GROUPS = {"MID_CONTROL", "A_PRESSURE", "B_PRESSURE", "BOMB_SITE_A", "BOMB_SITE_B"}


def build_round_region_timeline(
    region_presence: pd.DataFrame,
    round_features: pd.DataFrame,
    utility_events: pd.DataFrame,
    death_context: pd.DataFrame,
    bomb_carrier_timeline: pd.DataFrame,
) -> pd.DataFrame:
    if region_presence.empty:
        return empty_region_timeline()
    timeline = region_presence.merge(
        round_features[["round_feature_id", "opponent", "target_team_side"]],
        on="round_feature_id",
        how="left",
    )
    utility_counts = aggregate_utility_to_region(utility_events)
    death_counts = aggregate_deaths_to_region(death_context)
    bomb_counts = aggregate_bomb_to_region(bomb_carrier_timeline)
    for frame in [utility_counts, death_counts, bomb_counts]:
        if not frame.empty:
            timeline = timeline.merge(frame, on=["round_feature_id", "window_start", "window_end", "region_group"], how="left")
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


def build_round_outcome_context(round_features: pd.DataFrame, timeline: pd.DataFrame, death_context: pd.DataFrame, bomb_carrier_timeline: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in round_features.iterrows():
        round_feature_id = row["round_feature_id"]
        round_timeline = timeline[timeline["round_feature_id"] == round_feature_id] if "round_feature_id" in timeline.columns else pd.DataFrame()
        deaths = death_context[death_context["round_feature_id"] == round_feature_id] if not death_context.empty else pd.DataFrame()
        bomb = bomb_carrier_timeline[bomb_carrier_timeline["round_feature_id"] == round_feature_id] if not bomb_carrier_timeline.empty else pd.DataFrame()
        planted_site = row.get("target_site_model_label")
        signature = build_progression_signature(round_timeline, planted_site)
        first_target_death = first_region(deaths[deaths["is_target_team_death"] == True], "death_region_group") if not deaths.empty else None  # noqa: E712
        last_target_death = last_region(deaths[deaths["is_target_team_death"] == True], "death_region_group") if not deaths.empty else None  # noqa: E712
        first_contact = first_region(deaths, "death_region_group") if not deaths.empty else None
        bomb_last = last_region(bomb, "bomb_carrier_region_group") if not bomb.empty else None
        bomb_drop = first_region(bomb[bomb["bomb_dropped"] == True], "bomb_drop_region_group") if not bomb.empty else None  # noqa: E712
        rows.append(
            {
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
                "max_pressure_region_0_20": dominant_region(round_timeline, 0, 20),
                "max_pressure_region_0_30": dominant_region(round_timeline, 0, 30),
                "final_pressure_region_20_30": dominant_region(round_timeline, 20, 30),
                "bomb_last_known_region": bomb_last,
                "bomb_drop_region": bomb_drop,
                "round_progression_signature": signature,
                "round_failure_context": build_failure_context(row, first_target_death, bomb_drop),
                "round_outcome_type": classify_outcome(row, bomb_drop),
            }
        )
    return pd.DataFrame(rows)


def build_progression_signature(round_timeline: pd.DataFrame, planted_site: object = None) -> str:
    parts = []
    for window_start, window_end in PROGRESSION_WINDOWS:
        region = dominant_region(round_timeline, window_start, window_end)
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


def dominant_region(round_timeline: pd.DataFrame, window_start: int, window_end: int) -> str | None:
    if round_timeline.empty or not {"window_start", "window_end", "region_group", "time_spent_total"}.issubset(round_timeline.columns):
        return None
    window = round_timeline[(round_timeline["window_start"] >= window_start) & (round_timeline["window_end"] <= window_end)]
    if window.empty:
        return None
    pressure = window[window["region_group"].isin(PRESSURE_GROUPS)]
    source = pressure if not pressure.empty else window
    grouped = source.groupby("region_group")["time_spent_total"].sum().sort_values(ascending=False)
    return str(grouped.index[0]) if not grouped.empty else None


def aggregate_utility_to_region(utility_events: pd.DataFrame) -> pd.DataFrame:
    if utility_events.empty:
        return pd.DataFrame()
    events = utility_events.copy()
    events["window_start"], events["window_end"] = zip(*events["seconds_from_freeze_end"].map(window_for_seconds))
    return (
        events.groupby(["round_feature_id", "window_start", "window_end", "end_region_group"])
        .size()
        .reset_index(name="utility_events_to_region")
        .rename(columns={"end_region_group": "region_group"})
    )


def aggregate_deaths_to_region(death_context: pd.DataFrame) -> pd.DataFrame:
    if death_context.empty:
        return pd.DataFrame()
    deaths = death_context.copy()
    deaths["window_start"], deaths["window_end"] = zip(*deaths["seconds_from_freeze_end"].map(window_for_seconds))
    grouped = deaths.groupby(["round_feature_id", "window_start", "window_end", "death_region_group"])
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
        bomb_timeline.groupby(["round_feature_id", "window_start", "window_end", "bomb_carrier_region_group"])
        .size()
        .reset_index(name="bomb_carrier_in_region")
        .rename(columns={"bomb_carrier_region_group": "region_group"})
    )


def window_for_seconds(value: object) -> tuple[int, int]:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0, 5
    for window_start, window_end in PROGRESSION_WINDOWS:
        if window_start <= seconds < window_end:
            return window_start, window_end
    return PROGRESSION_WINDOWS[-1]


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
