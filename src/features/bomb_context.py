from __future__ import annotations

import pandas as pd

from src.config.schemas import FeatureWindowsConfig
from src.features.feature_windows import FeatureWindow
from src.features.feature_windows import configured_feature_windows
from src.features.region_mapping import add_region_columns
from src.features.utility_features import normalize_inventory


def build_bomb_carrier_timeline(
    early_ticks: pd.DataFrame,
    round_features: pd.DataFrame,
    bomb_events: pd.DataFrame,
    *,
    region_lookup: dict,
    place_column: str | None,
    windows: list[FeatureWindow] | None = None,
    tickrate: float = 64.0,
) -> pd.DataFrame:
    windows = windows or configured_feature_windows(FeatureWindowsConfig())
    rows = []
    ticks = early_ticks.copy()
    if not ticks.empty:
        ticks["has_c4"] = ticks["inventory"].map(has_c4)
        ticks = add_region_columns(ticks[ticks["has_c4"] == True].copy(), place_column=place_column, lookup=region_lookup, prefix="bomb_carrier_")  # noqa: E712
    for _, round_row in round_features.iterrows():
        round_ticks = ticks[ticks["round_feature_id"] == round_row["round_feature_id"]] if not ticks.empty else pd.DataFrame()
        round_bomb = bomb_events_for_round(bomb_events, round_row)
        for feature_window in windows:
            window_ticks = (
                round_ticks[(round_ticks["seconds_from_freeze_end"] >= feature_window.start) & (round_ticks["seconds_from_freeze_end"] < feature_window.end)]
                if not round_ticks.empty
                else pd.DataFrame()
            )
            carrier = window_ticks.sort_values("tick").tail(1) if "tick" in window_ticks.columns else pd.DataFrame()
            bomb_drop = first_bomb_drop(round_bomb, round_row, feature_window.start, feature_window.end, tickrate=tickrate)
            rows.append(
                {
                    "round_feature_id": round_row.get("round_feature_id"),
                    "round_id": round_row.get("round_id"),
                    "series_id": round_row.get("series_id"),
                    "target_team": round_row.get("target_team"),
                    "opponent": round_row.get("opponent"),
                    "map_name": round_row.get("map_name"),
                    "target_team_side": round_row.get("target_team_side"),
                    "window_type": feature_window.window_type,
                    "window_start": feature_window.start,
                    "window_end": feature_window.end,
                    "bomb_carrier_player": value_from(carrier, "name"),
                    "bomb_carrier_steamid": value_from(carrier, "steamid"),
                    "bomb_carrier_region_name": value_from(carrier, "bomb_carrier_region_name"),
                    "bomb_carrier_region_group": value_from(carrier, "bomb_carrier_region_group"),
                    "bomb_carrier_x": value_from(carrier, "X"),
                    "bomb_carrier_y": value_from(carrier, "Y"),
                    "bomb_carrier_z": value_from(carrier, "Z"),
                    "bomb_dropped": bomb_drop is not None,
                    "bomb_drop_tick": bomb_drop.get("tick") if bomb_drop else None,
                    "bomb_drop_seconds": bomb_drop.get("seconds_from_freeze_end") if bomb_drop else None,
                    "bomb_drop_region_name": "UNKNOWN",
                    "bomb_drop_region_group": "UNKNOWN",
                    "bomb_planted": round_row.get("bomb_planted"),
                    "bombsite": round_row.get("target_site_model_label"),
                }
            )
    return pd.DataFrame(rows)


def has_c4(inventory: object) -> bool:
    return any(item.lower() in {"c4 explosive", "c4", "bomb"} or "c4" in item.lower() for item in normalize_inventory(inventory))


def bomb_events_for_round(bomb_events: pd.DataFrame, round_row: pd.Series) -> pd.DataFrame:
    if bomb_events.empty:
        return pd.DataFrame()
    return bomb_events[
        (bomb_events["source_parse_id"].astype(str) == str(round_row.get("parse_id")))
        & (bomb_events["round_num"].astype(str) == str(round_row.get("round_num")))
    ].copy()


def first_bomb_drop(bomb_events: pd.DataFrame, round_row: pd.Series, window_start: int, window_end: int, *, tickrate: float) -> dict[str, object] | None:
    if bomb_events.empty or "event" not in bomb_events.columns:
        return None
    events = bomb_events[bomb_events["event"].astype(str).str.contains("drop", case=False, na=False)].copy()
    if events.empty:
        return None
    anchor = round_row.get("freeze_end_tick")
    if pd.isna(anchor):
        anchor = round_row.get("round_start_tick")
    events["seconds_from_freeze_end"] = (events["tick"] - anchor) / tickrate
    if "round_end_tick" in round_row.index and pd.notna(round_row.get("round_end_tick")):
        events = events[events["tick"] <= round_row.get("round_end_tick")]
    events = events[(events["seconds_from_freeze_end"] >= window_start) & (events["seconds_from_freeze_end"] < window_end)]
    if events.empty:
        return None
    return events.sort_values("tick").iloc[0].to_dict()


def value_from(df: pd.DataFrame, column: str) -> object:
    if df.empty or column not in df.columns:
        return None
    value = df.iloc[0].get(column)
    return None if pd.isna(value) else value
