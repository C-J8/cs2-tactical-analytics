from __future__ import annotations

import pandas as pd

from src.features.region_mapping import add_region_columns
from src.utils.text import safe_slug


def build_death_context(kills: pd.DataFrame, round_features: pd.DataFrame, *, region_lookup: dict, tickrate: float = 64.0) -> pd.DataFrame:
    if kills.empty or round_features.empty:
        return empty_death_context()
    context = kills.merge(
        round_features[["round_feature_id", "round_id", "parse_id", "series_id", "target_team", "opponent", "map_name", "target_team_side", "round_num", "freeze_end_tick", "round_start_tick"]],
        left_on=["source_parse_id", "round_num"],
        right_on=["parse_id", "round_num"],
        how="inner",
        suffixes=("", "_round"),
    )
    if context.empty:
        return empty_death_context()
    context["anchor_tick"] = context["freeze_end_tick"].fillna(context["round_start_tick"])
    context["death_tick"] = context["tick"]
    context["seconds_from_freeze_end"] = (context["death_tick"] - context["anchor_tick"]) / tickrate
    if "round_end_tick" in round_features.columns:
        end_ticks = round_features[["round_feature_id", "round_end_tick"]].drop_duplicates()
        context = context.merge(end_ticks, on="round_feature_id", how="left")
        context = context[(context["round_end_tick"].isna()) | (context["death_tick"] <= context["round_end_tick"])].copy()
    context = add_region_columns(context, place_column="victim_place" if "victim_place" in context.columns else None, lookup=region_lookup, prefix="death_")
    context["death_order"] = context.groupby("round_feature_id")["death_tick"].rank(method="first").astype(int)
    context["is_first_death"] = context["death_order"] == 1
    target_side = context["target_team_side"].astype(str).str.lower()
    victim_side = context.get("victim_side", pd.Series(index=context.index, dtype="object")).astype(str).str.lower()
    context["is_target_team_death"] = victim_side == target_side
    context["is_opponent_death"] = victim_side != target_side
    context["victim_team"] = context.apply(lambda row: row["target_team"] if row["is_target_team_death"] else row["opponent"], axis=1)
    context["killer_team"] = context.apply(lambda row: row["target_team"] if str(row.get("attacker_side")).lower() == str(row.get("target_team_side")).lower() else row["opponent"], axis=1)
    context["is_bomb_carrier_death"] = False
    context["death_context_id"] = context.apply(lambda row: safe_slug(f"{row['round_feature_id']}_death_{row['death_order']}", fallback="death_context"), axis=1)
    return context[
        [
            "death_context_id",
            "round_feature_id",
            "round_id",
            "series_id",
            "target_team",
            "opponent",
            "map_name",
            "target_team_side",
            "death_order",
            "death_tick",
            "seconds_from_freeze_end",
            "attacker_name",
            "victim_name",
            "killer_team",
            "victim_team",
            "weapon",
            "is_target_team_death",
            "is_opponent_death",
            "is_first_death",
            "is_bomb_carrier_death",
            "victim_X",
            "victim_Y",
            "victim_Z",
            "death_region_name",
            "death_region_group",
        ]
    ].rename(columns={"attacker_name": "killer_name", "victim_X": "death_x", "victim_Y": "death_y", "victim_Z": "death_z"})


def empty_death_context() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "death_context_id",
            "round_feature_id",
            "round_id",
            "series_id",
            "target_team",
            "opponent",
            "map_name",
            "target_team_side",
            "death_order",
            "death_tick",
            "seconds_from_freeze_end",
            "killer_name",
            "victim_name",
            "killer_team",
            "victim_team",
            "weapon",
            "is_target_team_death",
            "is_opponent_death",
            "is_first_death",
            "is_bomb_carrier_death",
            "death_x",
            "death_y",
            "death_z",
            "death_region_name",
            "death_region_group",
        ]
    )
