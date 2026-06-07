from __future__ import annotations

import math

import pandas as pd
import polars as pl

from src.config.schemas import FeatureWindowsConfig
from src.features.feature_windows import FeatureWindow, configured_feature_windows, max_window_end
from src.features.region_mapping import add_region_columns


REGION_FEATURE_GROUPS = {
    "MID_CONTROL": "mid_control",
    "A_PRESSURE": "a_pressure",
    "B_PRESSURE": "b_pressure",
    "CT_SPACE": "ct_space",
}


def load_early_ticks(ticks_path: str, round_base: pd.DataFrame, *, windows: list[FeatureWindow] | None = None, tickrate: float = 64.0) -> pd.DataFrame:
    if round_base.empty:
        return empty_early_ticks()
    windows = windows or configured_feature_windows(FeatureWindowsConfig())
    round_filter = round_base[
        [
            column
            for column in [
                "round_feature_id",
                "round_id",
                "parse_id",
                "series_id",
                "target_team",
                "map_name",
                "round_num",
                "freeze_end_tick",
                "round_start_tick",
                "round_end_tick",
            ]
            if column in round_base.columns
        ]
    ].copy()
    round_filter["anchor_tick"] = round_filter["freeze_end_tick"].fillna(round_filter["round_start_tick"])
    if "round_end_tick" not in round_filter.columns:
        round_filter["round_end_tick"] = round_filter["anchor_tick"] + (max_window_end(windows) * tickrate)
    columns = ["source_parse_id", "series_id", "target_team", "map_name", "round_num", "tick", "X", "Y", "Z", "side", "name", "steamid", "place", "health", "inventory"]
    tick_scan = pl.scan_parquet(ticks_path)
    tick_columns = [column for column in columns if column in tick_scan.collect_schema().names()]
    round_lazy = pl.from_pandas(round_filter).lazy()
    window_end = max_window_end(windows)
    ticks = (
        tick_scan.select(tick_columns)
        .join(round_lazy, left_on=["source_parse_id", "round_num"], right_on=["parse_id", "round_num"], how="inner", suffix="_round")
        .filter(pl.col("side") == "t")
        .with_columns(((pl.col("tick") - pl.col("anchor_tick")) / tickrate).alias("seconds_from_freeze_end"))
        .filter((pl.col("seconds_from_freeze_end") >= 0) & (pl.col("seconds_from_freeze_end") <= window_end))
        .filter(pl.col("tick") <= pl.col("round_end_tick"))
        .with_columns(pl.col("seconds_from_freeze_end").floor().cast(pl.Int64).alias("second_bucket"))
        .sort("tick")
        .group_by(["round_feature_id", "steamid", "second_bucket"])
        .agg(pl.all().last())
        .collect()
        .to_pandas()
    )
    if ticks.empty:
        return empty_early_ticks()
    return ticks


def build_position_outputs(
    early_ticks: pd.DataFrame,
    round_base: pd.DataFrame,
    *,
    region_lookup: dict,
    place_column: str | None,
    windows: list[FeatureWindow] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    windows = windows or configured_feature_windows(FeatureWindowsConfig())
    if early_ticks.empty:
        return empty_region_presence(), empty_position_features(round_base, windows)
    ticks = add_region_columns(early_ticks, place_column=place_column, lookup=region_lookup)
    region_presence = build_region_presence(ticks, windows)
    wide = build_position_wide(ticks, round_base, windows)
    return region_presence, wide


def build_region_presence(ticks: pd.DataFrame, windows: list[FeatureWindow] | None = None) -> pd.DataFrame:
    windows = windows or configured_feature_windows(FeatureWindowsConfig())
    required_columns = [
        "round_feature_id",
        "round_id",
        "series_id",
        "target_team",
        "map_name",
        "region_name",
        "region_group",
        "tick",
        "steamid",
        "seconds_from_freeze_end",
    ]
    ticks = ticks[[column for column in required_columns if column in ticks.columns]]
    rows = []
    for feature_window in windows:
        window = ticks[(ticks["seconds_from_freeze_end"] >= feature_window.start) & (ticks["seconds_from_freeze_end"] < feature_window.end)]
        if window.empty:
            continue
        window = window[
            [
                "round_feature_id",
                "round_id",
                "series_id",
                "target_team",
                "map_name",
                "region_name",
                "region_group",
                "tick",
                "steamid",
            ]
        ]
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
        aggregate["window_type"] = feature_window.window_type
        aggregate["window_start"] = feature_window.start
        aggregate["window_end"] = feature_window.end
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
            "window_type",
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


def build_position_wide(ticks: pd.DataFrame, round_base: pd.DataFrame, windows: list[FeatureWindow] | None = None) -> pd.DataFrame:
    windows = windows or configured_feature_windows(FeatureWindowsConfig())
    rows = []
    for round_feature_id, group in ticks.groupby("round_feature_id"):
        row: dict[str, object] = {"round_feature_id": round_feature_id}
        for seconds in [10, 15, 20, 25, 115]:
            window = group[group["seconds_from_freeze_end"] <= seconds]
            center = window[["X", "Y", "Z"]].mean(numeric_only=True)
            row[f"team_center_x_{seconds}s"] = center.get("X")
            row[f"team_center_y_{seconds}s"] = center.get("Y")
            row[f"team_center_z_{seconds}s"] = center.get("Z")
            row[f"team_spread_{seconds}s"] = average_distance_to_center(window, center)
            row[f"avg_pairwise_distance_{seconds}s"] = row[f"team_spread_{seconds}s"] * math.sqrt(2) if pd.notna(row[f"team_spread_{seconds}s"]) else None
            row[f"players_alive_{seconds}s"] = players_alive_at(window, seconds)
        for feature_window in windows:
            window = group[(group["seconds_from_freeze_end"] >= feature_window.start) & (group["seconds_from_freeze_end"] < feature_window.end)]
            for region_group, feature_name in REGION_FEATURE_GROUPS.items():
                in_region = window[window["region_group"] == region_group]
                row[f"players_{feature_name}_{feature_window.suffix}"] = in_region["steamid"].nunique()
                row[f"time_{feature_name}_{feature_window.suffix}"] = len(in_region)
        legacy_window = group[(group["seconds_from_freeze_end"] >= 0) & (group["seconds_from_freeze_end"] < 20)]
        for region_group, feature_name in REGION_FEATURE_GROUPS.items():
            in_region = legacy_window[legacy_window["region_group"] == region_group]
            legacy_name = "mid" if feature_name == "mid_control" else feature_name
            row[f"players_{legacy_name}_0_20"] = in_region["steamid"].nunique()
            row[f"time_{feature_name}_0_20"] = len(in_region)
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
            "window_type",
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


def empty_position_features(round_base: pd.DataFrame, windows: list[FeatureWindow] | None = None) -> pd.DataFrame:
    windows = windows or configured_feature_windows(FeatureWindowsConfig())
    result = round_base[["round_feature_id"]].copy() if "round_feature_id" in round_base.columns else pd.DataFrame(columns=["round_feature_id"])
    for seconds in [10, 15, 20, 25, 115]:
        for column in ["team_center_x", "team_center_y", "team_center_z", "team_spread", "avg_pairwise_distance", "players_alive"]:
            result[f"{column}_{seconds}s"] = None
    for feature_window in windows:
        for feature in REGION_FEATURE_GROUPS.values():
            result[f"players_{feature}_{feature_window.suffix}"] = 0
            result[f"time_{feature}_{feature_window.suffix}"] = 0
    for feature in ["mid", "a_pressure", "b_pressure", "ct_space"]:
        result[f"players_{feature}_0_20"] = 0
    for feature in ["mid_control", "a_pressure", "b_pressure", "ct_space"]:
        result[f"time_{feature}_0_20"] = 0
    return result
