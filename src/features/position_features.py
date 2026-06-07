from __future__ import annotations

import math

import pandas as pd
import polars as pl

from src.features.region_mapping import add_region_columns


WINDOWS = [(0, 5), (5, 10), (10, 15), (15, 20), (0, 20)]
REGION_FEATURE_GROUPS = {
    "MID_CONTROL": "mid",
    "A_PRESSURE": "a_pressure",
    "B_PRESSURE": "b_pressure",
    "CT_SPACE": "ct_space",
}


def load_early_ticks(ticks_path: str, round_base: pd.DataFrame, *, window_end: int, tickrate: float = 64.0) -> pd.DataFrame:
    if round_base.empty:
        return empty_early_ticks()
    round_filter = round_base[["round_feature_id", "round_id", "parse_id", "series_id", "target_team", "map_name", "round_num", "freeze_end_tick", "round_start_tick"]].copy()
    round_filter["anchor_tick"] = round_filter["freeze_end_tick"].fillna(round_filter["round_start_tick"])
    columns = ["source_parse_id", "series_id", "target_team", "map_name", "round_num", "tick", "X", "Y", "Z", "side", "name", "steamid", "place", "health", "inventory"]
    tick_scan = pl.scan_parquet(ticks_path)
    tick_columns = [column for column in columns if column in tick_scan.collect_schema().names()]
    round_lazy = pl.from_pandas(round_filter).lazy()
    ticks = (
        tick_scan.select(tick_columns)
        .join(round_lazy, left_on=["source_parse_id", "round_num"], right_on=["parse_id", "round_num"], how="inner", suffix="_round")
        .filter(pl.col("side") == "t")
        .with_columns(((pl.col("tick") - pl.col("anchor_tick")) / tickrate).alias("seconds_from_freeze_end"))
        .filter((pl.col("seconds_from_freeze_end") >= 0) & (pl.col("seconds_from_freeze_end") <= window_end))
        .collect()
        .to_pandas()
    )
    if ticks.empty:
        return empty_early_ticks()
    return ticks


def build_position_outputs(early_ticks: pd.DataFrame, round_base: pd.DataFrame, *, region_lookup: dict, place_column: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if early_ticks.empty:
        return empty_region_presence(), empty_position_features(round_base)
    ticks = add_region_columns(early_ticks, place_column=place_column, lookup=region_lookup)
    region_presence = build_region_presence(ticks)
    wide = build_position_wide(ticks, round_base)
    return region_presence, wide


def build_region_presence(ticks: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for window_start, window_end in WINDOWS:
        window = ticks[(ticks["seconds_from_freeze_end"] >= window_start) & (ticks["seconds_from_freeze_end"] < window_end)].copy()
        if window.empty:
            continue
        tick_counts = (
            window.groupby(["round_feature_id", "round_id", "series_id", "target_team", "map_name", "region_name", "region_group", "tick"])["steamid"]
            .nunique()
            .reset_index(name="players_count")
        )
        grouped = tick_counts.groupby(["round_feature_id", "round_id", "series_id", "target_team", "map_name", "region_name", "region_group"])
        unique_players = (
            window.groupby(["round_feature_id", "region_name", "region_group"])["steamid"]
            .nunique()
            .reset_index(name="unique_players_count")
        )
        aggregate = grouped["players_count"].agg(players_count_max="max", players_count_avg="mean", time_spent_total="sum").reset_index()
        aggregate = aggregate.merge(unique_players, on=["round_feature_id", "region_name", "region_group"], how="left")
        aggregate["window_start"] = window_start
        aggregate["window_end"] = window_end
        rows.append(aggregate)
    if not rows:
        return empty_region_presence()
    result = pd.concat(rows, ignore_index=True)
    return result[
        [
            "round_feature_id",
            "round_id",
            "series_id",
            "target_team",
            "map_name",
            "window_start",
            "window_end",
            "region_name",
            "region_group",
            "players_count_max",
            "players_count_avg",
            "time_spent_total",
            "unique_players_count",
        ]
    ]


def build_position_wide(ticks: pd.DataFrame, round_base: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for round_feature_id, group in ticks.groupby("round_feature_id"):
        row: dict[str, object] = {"round_feature_id": round_feature_id}
        for seconds in [10, 20]:
            window = group[group["seconds_from_freeze_end"] <= seconds]
            center = window[["X", "Y", "Z"]].mean(numeric_only=True)
            row[f"team_center_x_{seconds}s"] = center.get("X")
            row[f"team_center_y_{seconds}s"] = center.get("Y")
            row[f"team_center_z_{seconds}s"] = center.get("Z")
            row[f"team_spread_{seconds}s"] = average_distance_to_center(window, center)
            row[f"avg_pairwise_distance_{seconds}s"] = row[f"team_spread_{seconds}s"] * math.sqrt(2) if pd.notna(row[f"team_spread_{seconds}s"]) else None
            row[f"players_alive_{seconds}s"] = players_alive_at(window, seconds)
        window_20 = group[group["seconds_from_freeze_end"] <= 20]
        for region_group, feature_name in REGION_FEATURE_GROUPS.items():
            in_region = window_20[window_20["region_group"] == region_group]
            row[f"players_{feature_name}_0_20"] = in_region["steamid"].nunique()
            row[f"time_{feature_name}_control_0_20" if feature_name == "mid" else f"time_{feature_name}_0_20"] = len(in_region)
        rows.append(row)
    result = pd.DataFrame(rows)
    all_rounds = round_base[["round_feature_id"]].drop_duplicates()
    return all_rounds.merge(result, on="round_feature_id", how="left")


def average_distance_to_center(window: pd.DataFrame, center: pd.Series) -> float | None:
    if window.empty or center.empty:
        return None
    distances = ((window["X"] - center.get("X", 0)) ** 2 + (window["Y"] - center.get("Y", 0)) ** 2 + (window["Z"] - center.get("Z", 0)) ** 2) ** 0.5
    return float(distances.mean()) if not distances.empty else None


def players_alive_at(window: pd.DataFrame, seconds: int) -> int | None:
    if window.empty:
        return None
    latest_tick = window[window["seconds_from_freeze_end"] <= seconds]["tick"].max()
    if pd.isna(latest_tick):
        return None
    latest = window[window["tick"] == latest_tick]
    health = latest["health"] if "health" in latest.columns else pd.Series([1] * len(latest))
    return int(latest[health.fillna(0) > 0]["steamid"].nunique())


def empty_early_ticks() -> pd.DataFrame:
    return pd.DataFrame()


def empty_region_presence() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "round_feature_id",
            "round_id",
            "series_id",
            "target_team",
            "map_name",
            "window_start",
            "window_end",
            "region_name",
            "region_group",
            "players_count_max",
            "players_count_avg",
            "time_spent_total",
            "unique_players_count",
        ]
    )


def empty_position_features(round_base: pd.DataFrame) -> pd.DataFrame:
    result = round_base[["round_feature_id"]].copy() if "round_feature_id" in round_base.columns else pd.DataFrame(columns=["round_feature_id"])
    for seconds in [10, 20]:
        for column in ["team_center_x", "team_center_y", "team_center_z", "team_spread", "avg_pairwise_distance", "players_alive"]:
            result[f"{column}_{seconds}s"] = None
    for feature in ["mid", "a_pressure", "b_pressure", "ct_space"]:
        result[f"players_{feature}_0_20"] = None
    for feature in ["mid_control", "a_pressure", "b_pressure"]:
        result[f"time_{feature}_0_20"] = None
    return result
