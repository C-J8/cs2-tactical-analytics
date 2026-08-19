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


def add_score_diff_before_round(
    round_base: pd.DataFrame,
    round_state: pd.DataFrame | None,
    *,
    target_team: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fill target score before each round using resolved side/team state from previous rounds only."""
    result = round_base.copy()
    if result.empty:
        return result, score_audit_row(0, 0, 0, "empty_round_base", "No round rows available.")
    if round_state is None or round_state.empty:
        result["score_diff_before_round"] = None
        return result, score_audit_row(len(result), 0, len(result), "missing_round_state", "round_state_resolved was not available.")

    state = round_state.copy()
    join_keys = ["parse_id", "round_num"]
    if not set(join_keys).issubset(result.columns) or not set(join_keys).issubset(state.columns):
        result["score_diff_before_round"] = None
        return result, score_audit_row(len(result), 0, len(result), "missing_join_keys", "Could not join round_base to round_state by parse_id and round_num.")

    state_cols = [
        column
        for column in [
            "parse_id",
            "round_num",
            "team_t",
            "team_ct",
            "target_team_side",
            "opponent_side",
            "winner_team",
            "winner_side",
        ]
        if column in state.columns
    ]
    scoring = result[join_keys + ["round_feature_id", "target_team", "opponent"]].merge(
        state[state_cols].drop_duplicates(join_keys),
        on=join_keys,
        how="left",
        suffixes=("", "_state"),
    )
    scoring["_round_order"] = pd.to_numeric(scoring["round_num"], errors="coerce")
    scores: dict[str, tuple[int, int]] = {}
    values: dict[str, int | None] = {}
    resolved_rounds = 0
    unresolved_rounds = 0
    for _, row in scoring.sort_values(["parse_id", "_round_order", "round_num"], kind="mergesort").iterrows():
        parse_id = str(row.get("parse_id"))
        target_score, opponent_score = scores.get(parse_id, (0, 0))
        round_feature_id = str(row.get("round_feature_id"))
        values[round_feature_id] = target_score - opponent_score

        winner = resolved_winner_team(row, target_team=target_team)
        if team_matches(winner, target_team):
            scores[parse_id] = (target_score + 1, opponent_score)
            resolved_rounds += 1
        elif winner and team_matches(winner, row.get("opponent")):
            scores[parse_id] = (target_score, opponent_score + 1)
            resolved_rounds += 1
        else:
            scores[parse_id] = (target_score, opponent_score)
            unresolved_rounds += 1

    result["score_diff_before_round"] = result["round_feature_id"].astype(str).map(values)
    filled = int(result["score_diff_before_round"].notna().sum())
    missing = len(result) - filled
    audit = score_audit_row(
        len(result),
        filled,
        missing,
        "round_state_previous_round_winners",
        f"resolved_winner_rows={resolved_rounds}; unresolved_winner_rows={unresolved_rounds}; score resets by parse_id.",
    )
    return result, audit


def resolved_winner_team(row: pd.Series, *, target_team: str) -> str | None:
    winner_team = row.get("winner_team")
    if winner_team and str(winner_team).strip().casefold() not in {"unknown", "none", "nan"}:
        return str(winner_team)
    winner_side = normalize_side(row.get("winner_side"))
    target_side = normalize_side(row.get("target_team_side"))
    if winner_side and target_side:
        if winner_side == target_side:
            return target_team
        opponent = row.get("opponent")
        return str(opponent) if opponent and not pd.isna(opponent) else None
    if winner_side == "T":
        return normalized_optional(row.get("team_t"))
    if winner_side == "CT":
        return normalized_optional(row.get("team_ct"))
    return None


def normalize_side(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().casefold()
    if text in {"t", "terrorist", "terrorists"}:
        return "T"
    if text in {"ct", "counter-terrorist", "counter-terrorists", "counterterrorist", "counterterrorists"}:
        return "CT"
    return None


def normalized_optional(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def team_matches(left: object, right: object) -> bool:
    if left is None or right is None or pd.isna(left) or pd.isna(right):
        return False
    return str(left).strip().casefold() == str(right).strip().casefold()


def score_audit_row(total: int, filled: int, missing: int, method: str, notes: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "total_rounds": int(total),
                "score_diff_filled": int(filled),
                "score_diff_missing": int(missing),
                "score_diff_missing_share": float(missing / total) if total else 0.0,
                "score_resolution_method": method,
                "feature_engine_version": "v2",
                "status": "ok" if total and missing == 0 else "warning",
                "notes": notes,
            }
        ]
    )


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
