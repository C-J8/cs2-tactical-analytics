from __future__ import annotations

import pandas as pd

from src.utils.text import safe_slug


def build_round_base(rounds: pd.DataFrame, feature_eligible: pd.DataFrame, bomb: pd.DataFrame | None = None) -> pd.DataFrame:
    eligible = feature_eligible[feature_eligible["feature_eligible"] == True].copy()  # noqa: E712
    if eligible.empty or rounds.empty:
        return empty_round_base()
    parse_ids = set(eligible["parse_id"].astype(str))
    base = rounds[rounds["source_parse_id"].astype(str).isin(parse_ids)].copy()
    if base.empty:
        return empty_round_base()

    eligible_meta = eligible[
        [
            "parse_id",
            "dem_file_id",
            "series_id",
            "local_archive_id",
            "target_team",
            "opponent",
            "inferred_map_name",
        ]
    ].drop_duplicates("parse_id")
    base = base.merge(eligible_meta, left_on="source_parse_id", right_on="parse_id", how="left", suffixes=("", "_eligible"))
    base["round_id"] = base["source_parse_id"].astype(str) + "_r" + base["round_num"].astype(str)
    base["round_feature_id"] = base["round_id"].map(lambda value: safe_slug(value, fallback="round"))
    base["round_start_tick"] = base.get("start")
    base["freeze_end_tick"] = base.get("freeze_end")
    base["round_end_tick"] = base.get("end")
    base["half"] = base["round_num"].map(infer_half)
    base["target_team_side"] = "t"
    base["winner_side"] = base.get("winner")
    base["winner_team"] = None
    base["bomb_planted"] = base.get("bomb_plant").notna() if "bomb_plant" in base.columns else False
    base["bombsite"] = base.get("bomb_site")
    site_labels = base.apply(lambda row: infer_target_site(row, bomb), axis=1)
    base["target_site_observed"] = site_labels.map(lambda value: value[0])
    base["target_site_model_label"] = site_labels.map(lambda value: value[1])
    base["label_source"] = site_labels.map(lambda value: value[2])
    base["score_diff_before_round"] = None
    base["is_pistol_round"] = base["round_num"].isin({1, 13})
    base["is_early_round"] = base["round_num"] <= 6
    base["is_late_round"] = base["round_num"] >= 19
    base["round_duration_ticks"] = base["round_end_tick"] - base["round_start_tick"]
    base["round_duration_seconds"] = base["round_duration_ticks"] / 64.0

    return base[round_base_columns()]


def infer_half(round_num: int) -> int:
    return 1 if int(round_num) <= 12 else 2


def infer_target_site(row: pd.Series, bomb: pd.DataFrame | None) -> tuple[str | None, str | None, str]:
    site = normalize_bombsite(row.get("bomb_site"))
    if site:
        return site, site, "rounds_bomb_site"
    if bomb is not None and not bomb.empty:
        matches = bomb[
            (bomb["source_parse_id"].astype(str) == str(row.get("source_parse_id")))
            & (bomb["round_num"].astype(str) == str(row.get("round_num")))
        ]
        for value in matches.get("bombsite", pd.Series(dtype="object")):
            site = normalize_bombsite(value)
            if site:
                return site, site, "bomb_table"
    return None, None, "missing"


def normalize_bombsite(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in {"a", "bombsite_a", "site_a", "bombsitea"}:
        return "A"
    if text in {"b", "bombsite_b", "site_b", "bombsiteb"}:
        return "B"
    return None


def round_base_columns() -> list[str]:
    return [
        "round_feature_id",
        "parse_id",
        "dem_file_id",
        "series_id",
        "local_archive_id",
        "target_team",
        "opponent",
        "map_name",
        "round_num",
        "round_id",
        "round_start_tick",
        "freeze_end_tick",
        "round_end_tick",
        "half",
        "target_team_side",
        "winner_side",
        "winner_team",
        "bomb_planted",
        "bombsite",
        "target_site_observed",
        "target_site_model_label",
        "label_source",
        "score_diff_before_round",
        "is_pistol_round",
        "is_early_round",
        "is_late_round",
        "round_duration_ticks",
        "round_duration_seconds",
    ]


def empty_round_base() -> pd.DataFrame:
    return pd.DataFrame(columns=round_base_columns())
