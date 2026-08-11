from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import polars as pl

from src.config.schemas import FeatureWindowsConfig
from src.features.feature_windows import FeatureWindow, configured_feature_windows, max_window_end
from src.features.region_mapping import add_region_columns
from src.utils.text import safe_slug


UTILITY_TYPES = {
    "smoke": ["smoke"],
    "flash": ["flash"],
    "molotov": ["molotov", "incendiary"],
    "he": ["he grenade", "high explosive"],
    "decoy": ["decoy"],
}


def build_player_round_utility(early_ticks: pd.DataFrame, round_base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if early_ticks.empty:
        return empty_player_utility(), empty_utility_aggregates(round_base)
    first_ticks = early_ticks.sort_values(["round_feature_id", "steamid", "tick"]).groupby(["round_feature_id", "steamid"], as_index=False).first()
    rows = []
    for _, row in first_ticks.iterrows():
        counts = count_inventory(row.get("inventory"))
        rows.append(
            {
                "round_feature_id": row.get("round_feature_id"),
                "round_id": row.get("round_id"),
                "series_id": row.get("series_id"),
                "target_team": row.get("target_team"),
                "player_name": row.get("name"),
                "player_steamid": row.get("steamid"),
                "side": row.get("side"),
                "smokes_start": counts["smoke"],
                "flashes_start": counts["flash"],
                "molotovs_start": counts["molotov"],
                "he_start": counts["he"],
                "decoys_start": counts["decoy"],
                "total_utility_start": sum(counts.values()),
                "has_smoke": counts["smoke"] > 0,
                "has_flash": counts["flash"] > 0,
                "has_molotov": counts["molotov"] > 0,
                "has_he": counts["he"] > 0,
            }
        )
    player_utility = pd.DataFrame(rows)
    aggregates = (
        player_utility.groupby("round_feature_id")
        .agg(
            team_smokes_start=("smokes_start", "sum"),
            team_flashes_start=("flashes_start", "sum"),
            team_molotovs_start=("molotovs_start", "sum"),
            team_he_start=("he_start", "sum"),
            team_decoys_start=("decoys_start", "sum"),
            team_total_utility_start=("total_utility_start", "sum"),
        )
        .reset_index()
    )
    return player_utility, round_base[["round_feature_id"]].merge(aggregates, on="round_feature_id", how="left")


def count_inventory(inventory: object) -> dict[str, int]:
    items = normalize_inventory(inventory)
    counts = {key: 0 for key in UTILITY_TYPES}
    for item in items:
        normalized = item.lower()
        for utility_type, needles in UTILITY_TYPES.items():
            if any(needle in normalized for needle in needles):
                counts[utility_type] += 1
    return counts


def normalize_inventory(inventory: object) -> list[str]:
    if inventory is None:
        return []
    if isinstance(inventory, str):
        is_missing = pd.isna(inventory)
        if bool(is_missing):
            return []
    elif not isinstance(inventory, Iterable):
        is_missing = pd.isna(inventory)
        if bool(is_missing):
            return []
    if isinstance(inventory, str):
        stripped = inventory.strip()
        if not stripped:
            return []
        try:
            parsed = ast.literal_eval(stripped)
            if isinstance(parsed, Iterable) and not isinstance(parsed, str):
                return [str(item) for item in parsed]
        except (ValueError, SyntaxError):
            return [part.strip() for part in stripped.strip("[]").split(",") if part.strip()]
        return [stripped]
    if isinstance(inventory, Iterable):
        return [str(item) for item in inventory]
    return [str(inventory)]


def build_utility_events(
    silver_dir: Path,
    round_base: pd.DataFrame,
    *,
    windows: list[FeatureWindow] | None = None,
    window_end: int | None = None,
    region_lookup: dict,
    utility_region_groups: dict[str, str] | None = None,
    tickrate: float = 64.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    windows = windows or configured_feature_windows(FeatureWindowsConfig())
    if window_end is not None:
        windows = [FeatureWindow(0, window_end, "cumulative")]
    events = []
    diagnostics = {"grenades_granularity": detect_grenades_granularity(silver_dir / "grenades.parquet")}
    for table_name, utility_type in [("smokes", "smoke"), ("infernos", "molotov")]:
        path = silver_dir / f"{table_name}.parquet"
        if not path.exists() or round_base.empty:
            continue
        source = pd.read_parquet(path)
        table_events = events_from_table(source, round_base, utility_type=utility_type, source_table=table_name, region_lookup=region_lookup, tickrate=tickrate, windows=windows)
        events.append(table_events)
    utility_events = pd.concat(events, ignore_index=True) if events else empty_utility_events()
    aggregates = build_utility_event_aggregates(utility_events, round_base, windows, utility_region_groups=utility_region_groups)
    return utility_events, aggregates, diagnostics


def events_from_table(
    source: pd.DataFrame,
    round_base: pd.DataFrame,
    *,
    utility_type: str,
    source_table: str,
    region_lookup: dict,
    tickrate: float,
    windows: list[FeatureWindow] | None = None,
    window_end: int | None = None,
) -> pd.DataFrame:
    if source.empty:
        return empty_utility_events()
    windows = windows or configured_feature_windows(FeatureWindowsConfig())
    if window_end is not None:
        windows = [FeatureWindow(0, window_end, "cumulative")]
    merged = source.merge(
        round_base[
            [
                column
                for column in [
                    "round_feature_id",
                    "round_id",
                    "parse_id",
                    "series_id",
                    "target_team",
                    "round_num",
                    "freeze_end_tick",
                    "round_start_tick",
                    "round_end_tick",
                ]
                if column in round_base.columns
            ]
        ],
        left_on=["source_parse_id", "round_num"],
        right_on=["parse_id", "round_num"],
        how="inner",
        suffixes=("", "_round"),
    )
    if merged.empty:
        return empty_utility_events()
    merged["event_tick"] = merged.get("start_tick")
    merged["anchor_tick"] = merged["freeze_end_tick"].fillna(merged["round_start_tick"])
    if "round_end_tick" not in merged.columns:
        merged["round_end_tick"] = merged["anchor_tick"] + (max_window_end(windows) * tickrate)
    merged["seconds_from_freeze_end"] = (merged["event_tick"] - merged["anchor_tick"]) / tickrate
    merged = merged[
        (merged["seconds_from_freeze_end"] >= 0)
        & (merged["seconds_from_freeze_end"] <= max_window_end(windows))
        & (merged["event_tick"] <= merged["round_end_tick"])
        & (merged.get("thrower_side") == "t")
    ].copy()
    if merged.empty:
        return empty_utility_events()
    merged = add_region_columns(merged, place_column="thrower_place" if "thrower_place" in merged.columns else None, lookup=region_lookup, prefix="throw_")
    merged["end_region_name"] = "UNKNOWN"
    merged["end_region_group"] = "UNKNOWN"
    merged["utility_type"] = utility_type
    merged["source_table"] = source_table
    merged["source_granularity"] = "event_level"
    merged["utility_event_id"] = merged.apply(lambda row: safe_slug(f"{row['round_feature_id']}_{source_table}_{row.get('entity_id')}_{row.get('event_tick')}", fallback="utility_event"), axis=1)
    if "series_id_round" not in merged.columns:
        merged["series_id_round"] = merged.get("series_id")
    if "target_team_round" not in merged.columns:
        merged["target_team_round"] = merged.get("target_team")
    return merged[
        [
            "utility_event_id",
            "round_feature_id",
            "round_id",
            "series_id_round",
            "target_team_round",
            "thrower_name",
            "thrower_steamid",
            "utility_type",
            "event_tick",
            "seconds_from_freeze_end",
            "thrower_X",
            "thrower_Y",
            "thrower_Z",
            "throw_region_name",
            "throw_region_group",
            "X",
            "Y",
            "Z",
            "end_region_name",
            "end_region_group",
            "source_table",
            "source_granularity",
        ]
    ].rename(
        columns={
            "series_id_round": "series_id",
            "target_team_round": "target_team",
            "thrower_name": "player_name",
            "thrower_steamid": "player_steamid",
            "thrower_X": "throw_x",
            "thrower_Y": "throw_y",
            "thrower_Z": "throw_z",
            "X": "end_x",
            "Y": "end_y",
            "Z": "end_z",
        }
    )


def detect_grenades_granularity(path: Path) -> str:
    if not path.exists():
        return "missing"
    sample = pl.scan_parquet(path).select(["entity_id", "tick"]).limit(100_000).collect().to_pandas()
    if sample.empty or "entity_id" not in sample.columns:
        return "unknown"
    ticks_per_entity = sample.groupby("entity_id")["tick"].nunique()
    return "trajectory_level" if ticks_per_entity.mean() > 1 else "event_level"


def build_utility_event_aggregates(
    utility_events: pd.DataFrame,
    round_base: pd.DataFrame,
    windows: list[FeatureWindow],
    *,
    utility_region_groups: dict[str, str] | None = None,
) -> pd.DataFrame:
    utility_region_groups = utility_region_groups or {"MID_CONTROL": "mid_control", "A_PRESSURE": "a_pressure", "B_PRESSURE": "b_pressure"}
    result = round_base[["round_feature_id"]].copy()
    defaults = utility_aggregate_defaults(windows, utility_region_groups=utility_region_groups)
    defaults.update(
        {
            "smokes_used_0_20": 0,
            "molotovs_used_0_20": 0,
            "flashes_used_0_20": None,
            "he_used_0_20": None,
            "total_utility_used_0_20": 0,
            "smokes_to_mid_control_0_20": 0,
            "smokes_to_a_pressure_0_20": 0,
            "smokes_to_b_pressure_0_20": 0,
            "molotovs_to_mid_control_0_20": 0,
            "molotovs_to_a_pressure_0_20": 0,
            "molotovs_to_b_pressure_0_20": 0,
        }
    )
    defaults.update(
        {
            "first_smoke_time": None,
            "first_molotov_time": None,
            "first_utility_time": None,
        }
    )
    if utility_events.empty:
        defaults_frame = pd.DataFrame([defaults] * len(result), index=result.index)
        return pd.concat([result, defaults_frame], axis=1)
    grouped = []
    for round_feature_id, events in utility_events.groupby("round_feature_id"):
        row = {"round_feature_id": round_feature_id, **defaults}
        for feature_window in windows:
            window_events = events[(events["seconds_from_freeze_end"] >= feature_window.start) & (events["seconds_from_freeze_end"] < feature_window.end)]
            add_utility_counts(row, window_events, feature_window.suffix, utility_region_groups=utility_region_groups)
        legacy_events = events[(events["seconds_from_freeze_end"] >= 0) & (events["seconds_from_freeze_end"] < 20)]
        add_utility_counts(row, legacy_events, "0_20", utility_region_groups=utility_region_groups)
        smokes = events[events["utility_type"] == "smoke"]
        molotovs = events[events["utility_type"] == "molotov"]
        row["first_smoke_time"] = smokes["seconds_from_freeze_end"].min() if not smokes.empty else None
        row["first_molotov_time"] = molotovs["seconds_from_freeze_end"].min() if not molotovs.empty else None
        row["first_utility_time"] = events["seconds_from_freeze_end"].min()
        grouped.append(row)
    merged = result.merge(pd.DataFrame(grouped), on="round_feature_id", how="left")
    for column, value in defaults.items():
        if column not in merged.columns:
            merged[column] = value
        elif value is not None:
            merged[column] = merged[column].fillna(value)
    return merged


def utility_aggregate_defaults(windows: list[FeatureWindow], *, utility_region_groups: dict[str, str] | None = None) -> dict[str, object]:
    utility_region_groups = utility_region_groups or {"MID_CONTROL": "mid_control", "A_PRESSURE": "a_pressure", "B_PRESSURE": "b_pressure"}
    defaults: dict[str, object] = {}
    for feature_window in windows:
        suffix = feature_window.suffix
        defaults[f"smokes_used_{suffix}"] = 0
        defaults[f"molotovs_used_{suffix}"] = 0
        defaults[f"flashes_used_{suffix}"] = None
        defaults[f"he_used_{suffix}"] = None
        defaults[f"total_utility_used_{suffix}"] = 0
        for region_suffix in utility_region_groups.values():
            defaults[f"smokes_to_{region_suffix}_{suffix}"] = 0
            defaults[f"molotovs_to_{region_suffix}_{suffix}"] = 0
    return defaults


def add_utility_counts(
    row: dict[str, object],
    events: pd.DataFrame,
    suffix: str,
    *,
    utility_region_groups: dict[str, str] | None = None,
) -> None:
    utility_region_groups = utility_region_groups or {"MID_CONTROL": "mid_control", "A_PRESSURE": "a_pressure", "B_PRESSURE": "b_pressure"}
    smokes = events[events["utility_type"] == "smoke"]
    molotovs = events[events["utility_type"] == "molotov"]
    row[f"smokes_used_{suffix}"] = len(smokes)
    row[f"molotovs_used_{suffix}"] = len(molotovs)
    row[f"total_utility_used_{suffix}"] = len(events)
    for group, region_suffix in utility_region_groups.items():
        row[f"smokes_to_{region_suffix}_{suffix}"] = int((smokes["end_region_group"] == group).sum())
        row[f"molotovs_to_{region_suffix}_{suffix}"] = int((molotovs["end_region_group"] == group).sum())


def empty_player_utility() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "round_feature_id",
            "round_id",
            "series_id",
            "target_team",
            "player_name",
            "player_steamid",
            "side",
            "smokes_start",
            "flashes_start",
            "molotovs_start",
            "he_start",
            "decoys_start",
            "total_utility_start",
            "has_smoke",
            "has_flash",
            "has_molotov",
            "has_he",
        ]
    )


def empty_utility_aggregates(round_base: pd.DataFrame) -> pd.DataFrame:
    result = round_base[["round_feature_id"]].copy() if "round_feature_id" in round_base.columns else pd.DataFrame(columns=["round_feature_id"])
    for column in ["team_smokes_start", "team_flashes_start", "team_molotovs_start", "team_he_start", "team_decoys_start", "team_total_utility_start"]:
        result[column] = None
    return result


def empty_utility_events() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "utility_event_id",
            "round_feature_id",
            "round_id",
            "series_id",
            "target_team",
            "player_name",
            "player_steamid",
            "utility_type",
            "event_tick",
            "seconds_from_freeze_end",
            "throw_x",
            "throw_y",
            "throw_z",
            "throw_region_name",
            "throw_region_group",
            "end_x",
            "end_y",
            "end_z",
            "end_region_name",
            "end_region_group",
            "source_table",
            "source_granularity",
        ]
    )
