from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import polars as pl
import yaml

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging
from src.utils.text import clean_string


ROUND_STATE_COLUMNS = [
    "round_id",
    "round_num",
    "parse_id",
    "dem_file_id",
    "series_id",
    "target_team",
    "opponent",
    "map_name",
    "team_t",
    "team_ct",
    "target_team_side",
    "opponent_side",
    "side_resolution_method",
    "side_resolution_confidence",
    "round_start_tick",
    "freeze_end_tick",
    "round_end_tick",
    "winner_team",
    "winner_side",
    "round_end_reason",
    "bomb_planted",
    "bombsite",
    "plant_tick",
    "planting_player",
    "planting_team",
    "planting_side",
    "target_team_planted",
    "opponent_planted",
    "target_site_observed",
    "target_site_model_label",
    "label_source",
    "label_confidence",
    "state_quality_status",
    "state_quality_notes",
]

DEFAULT_TARGET_PLAYERS = {
    "vitality": {"zywoo", "flamez", "mezii", "ropz", "apex"},
}

TeamRosters = dict[str, set[str]]


def run_round_state_pipeline(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    silver_dir = project.parsed_silver_dir
    gold_dir = silver_dir.parent.parent / "gold"
    round_features = read_catalog(gold_dir / "round_features" / "round_features_mvp.parquet")
    round_base = read_catalog(gold_dir / "round_features" / "round_base.parquet")
    rounds = pd.read_parquet(silver_dir / "rounds.parquet")
    bomb = pd.read_parquet(silver_dir / "bomb.parquet") if (silver_dir / "bomb.parquet").exists() else pd.DataFrame()
    ticks_path = silver_dir / "ticks.parquet"
    team_rosters = load_player_rosters(project.player_rosters_path)

    state = build_round_state(
        round_features,
        round_base,
        rounds,
        bomb,
        ticks_path=ticks_path,
        target_team=project.target_teams[0],
        team_rosters=team_rosters,
    )
    audit = build_round_state_audit(state)
    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_round_state_outputs(state, audit, gold_dir / "round_state", force=force))
    summary = {
        "total_rounds": len(state),
        "target_team_t": int((state["target_team_side"] == "T").sum()),
        "target_team_ct": int((state["target_team_side"] == "CT").sum()),
        "target_team_unknown": int((state["target_team_side"] == "unknown").sum()),
        "high_confidence_labels": int((state["label_confidence"] == "high").sum()),
    }
    return state, audit, outputs, summary


def build_round_state(
    round_features: pd.DataFrame,
    round_base: pd.DataFrame,
    rounds: pd.DataFrame,
    bomb: pd.DataFrame,
    *,
    ticks_path: Path,
    target_team: str,
    team_rosters: TeamRosters | None = None,
) -> pd.DataFrame:
    base = round_features.merge(
        round_base[[column for column in ["round_feature_id", "round_start_tick", "freeze_end_tick", "round_end_tick"] if column in round_base.columns]],
        on="round_feature_id",
        how="left",
    )
    rounds_meta = rounds[
        [column for column in ["source_parse_id", "round_num", "winner", "reason", "bomb_plant", "bomb_site", "team_t", "team_ct", "t_team", "ct_team"] if column in rounds.columns]
    ].copy()
    base = base.merge(rounds_meta, left_on=["parse_id", "round_num"], right_on=["source_parse_id", "round_num"], how="left", suffixes=("", "_rounds"))
    team_rosters = team_rosters or default_team_rosters()
    side_evidence = resolve_sides(base, ticks_path=ticks_path, target_team=target_team, team_rosters=team_rosters)
    plant_evidence = resolve_plants(base, bomb, side_evidence, target_team=target_team, team_rosters=team_rosters)

    rows = []
    for _, row in base.iterrows():
        key = round_key(row)
        side = side_evidence.get(key, {})
        plant = plant_evidence.get(key, {})
        target_side = side.get("target_team_side", "unknown")
        opponent_side = opposite_side(target_side)
        winner_side = normalize_side(row.get("winner") or row.get("winner_side"))
        winner_team = target_team if winner_side == target_side and target_side != "unknown" else (row.get("opponent") if winner_side == opponent_side else None)
        target_site_observed = plant.get("bombsite")
        target_label = target_site_observed if target_side == "T" and plant.get("planting_team") == target_team and target_site_observed in {"A", "B"} else None
        label_confidence = "high" if target_label else None
        if target_label:
            label_source = "target_team_plant"
        elif plant.get("bomb_planted") and plant.get("planting_team") and plant.get("planting_team") != target_team:
            label_source = "opponent_plant"
        else:
            label_source = "missing"
        quality_status, quality_notes = state_quality(target_side, plant, target_label)
        rows.append(
            {
                "round_id": row.get("round_id"),
                "round_num": row.get("round_num"),
                "parse_id": row.get("parse_id"),
                "dem_file_id": row.get("dem_file_id"),
                "series_id": row.get("series_id"),
                "target_team": target_team,
                "opponent": row.get("opponent"),
                "map_name": row.get("map_name"),
                "team_t": side.get("team_t"),
                "team_ct": side.get("team_ct"),
                "target_team_side": target_side,
                "opponent_side": opponent_side,
                "side_resolution_method": side.get("side_resolution_method", "unknown"),
                "side_resolution_confidence": side.get("side_resolution_confidence", "unknown"),
                "round_start_tick": row.get("round_start_tick"),
                "freeze_end_tick": row.get("freeze_end_tick"),
                "round_end_tick": row.get("round_end_tick"),
                "winner_team": winner_team,
                "winner_side": winner_side,
                "round_end_reason": row.get("reason") or row.get("round_end_reason"),
                "bomb_planted": bool(plant.get("bomb_planted", False)),
                "bombsite": plant.get("bombsite"),
                "plant_tick": plant.get("plant_tick"),
                "planting_player": plant.get("planting_player"),
                "planting_team": plant.get("planting_team"),
                "planting_side": plant.get("planting_side"),
                "target_team_planted": plant.get("planting_team") == target_team,
                "opponent_planted": bool(plant.get("planting_team") and plant.get("planting_team") != target_team),
                "target_site_observed": target_site_observed,
                "target_site_model_label": target_label,
                "label_source": label_source,
                "label_confidence": label_confidence,
                "state_quality_status": quality_status,
                "state_quality_notes": quality_notes,
            }
        )
    return pd.DataFrame(rows, columns=ROUND_STATE_COLUMNS)


def resolve_sides(base: pd.DataFrame, *, ticks_path: Path, target_team: str, team_rosters: TeamRosters) -> dict[tuple[str, int], dict[str, object]]:
    explicit = resolve_sides_from_explicit_columns(base, target_team=target_team)
    unresolved = [key for key, value in explicit.items() if value["target_team_side"] == "unknown"]
    if not unresolved:
        return explicit
    player_evidence = resolve_sides_from_ticks(base, ticks_path=ticks_path, target_team=target_team, team_rosters=team_rosters)
    for key in unresolved:
        if key in player_evidence and player_evidence[key]["target_team_side"] != "unknown":
            explicit[key] = player_evidence[key]
    return explicit


def resolve_sides_from_explicit_columns(base: pd.DataFrame, *, target_team: str) -> dict[tuple[str, int], dict[str, object]]:
    evidence = {}
    for _, row in base.iterrows():
        team_t = clean_string(row.get("team_t")) or clean_string(row.get("t_team"))
        team_ct = clean_string(row.get("team_ct")) or clean_string(row.get("ct_team"))
        target_side = "unknown"
        method = "unknown"
        confidence = "unknown"
        if team_t and names_match(team_t, target_team):
            target_side, method, confidence = "T", "rounds_team_columns", "high"
        elif team_ct and names_match(team_ct, target_team):
            target_side, method, confidence = "CT", "rounds_team_columns", "high"
        evidence[round_key(row)] = {
            "team_t": team_t,
            "team_ct": team_ct,
            "target_team_side": target_side,
            "side_resolution_method": method,
            "side_resolution_confidence": confidence,
        }
    return evidence


def resolve_sides_from_ticks(base: pd.DataFrame, *, ticks_path: Path, target_team: str, team_rosters: TeamRosters) -> dict[tuple[str, int], dict[str, object]]:
    if not ticks_path.exists():
        return {}
    players = roster_players(team_rosters, target_team)
    if not players:
        return {}
    player_team_index = build_player_team_index(team_rosters)
    parse_ids = base["parse_id"].dropna().astype(str).unique().tolist()
    sample = (
        pl.scan_parquet(ticks_path)
        .select(["source_parse_id", "round_num", "side", "name", "tick"])
        .filter(pl.col("source_parse_id").is_in(parse_ids))
        .group_by(["source_parse_id", "round_num", "side", "name"])
        .len()
        .collect()
        .to_pandas()
    )
    sample["normalized_name"] = sample["name"].map(normalize_player_name)
    sample["is_target_player"] = sample["normalized_name"].map(lambda value: value in players)
    roster_rows = []
    for row in sample.to_dict("records"):
        for roster_team in player_team_index.get(row["normalized_name"], set()):
            roster_rows.append({**row, "roster_team": roster_team})
    roster_sample = pd.DataFrame(roster_rows)
    grouped = sample[sample["is_target_player"]].groupby(["source_parse_id", "round_num", "side"])["name"].nunique().reset_index(name="target_players")
    roster_grouped = (
        roster_sample
        .groupby(["source_parse_id", "round_num", "side", "roster_team"])["normalized_name"]
        .nunique()
        .reset_index(name="roster_players")
        if not roster_sample.empty
        else pd.DataFrame(columns=["source_parse_id", "round_num", "side", "roster_team", "roster_players"])
    )
    evidence = {}
    for _, row in base.iterrows():
        key = round_key(row)
        matches = grouped[(grouped["source_parse_id"] == key[0]) & (grouped["round_num"] == key[1])]
        side_counts = {normalize_side(side): int(count) for side, count in zip(matches["side"], matches["target_players"], strict=False)}
        t_count = side_counts.get("T", 0)
        ct_count = side_counts.get("CT", 0)
        if t_count > ct_count and t_count >= 2:
            target_side = "T"
        elif ct_count > t_count and ct_count >= 2:
            target_side = "CT"
        else:
            target_side = "unknown"
        confidence = "high" if max(t_count, ct_count) >= 4 and target_side != "unknown" else ("low" if target_side != "unknown" else "unknown")
        side_teams = best_roster_teams_for_round(roster_grouped, key)
        team_t = side_teams.get("T") or (target_team if target_side == "T" else None)
        team_ct = side_teams.get("CT") or (target_team if target_side == "CT" else None)
        evidence[key] = {
            "team_t": team_t,
            "team_ct": team_ct,
            "target_team_side": target_side,
            "side_resolution_method": "ticks_player_roster_config",
            "side_resolution_confidence": confidence,
        }
    return evidence


def resolve_plants(
    base: pd.DataFrame,
    bomb: pd.DataFrame,
    side_evidence: dict[tuple[str, int], dict[str, object]],
    *,
    target_team: str,
    team_rosters: TeamRosters,
) -> dict[tuple[str, int], dict[str, object]]:
    plants = {}
    bomb_plants = bomb[bomb["event"].astype(str).str.lower().eq("plant")].copy() if not bomb.empty and "event" in bomb.columns else pd.DataFrame()
    for _, row in base.iterrows():
        key = round_key(row)
        plant_rows = bomb_plants[(bomb_plants["source_parse_id"].astype(str) == key[0]) & (bomb_plants["round_num"].astype(int) == key[1])] if not bomb_plants.empty else pd.DataFrame()
        plant = plant_rows.sort_values("tick").iloc[0].to_dict() if not plant_rows.empty else {}
        bombsite = normalize_bombsite(first_present(plant.get("bombsite"), row.get("bomb_site"), row.get("target_site_observed")))
        bomb_planted = bool(bombsite and (not plant_rows.empty or pd.notna(row.get("bomb_plant"))))
        planting_player = clean_string(plant.get("name")) if bomb_planted else None
        planting_side = side_for_player_in_round(planting_player, row, side_evidence.get(key, {}), target_team=target_team, team_rosters=team_rosters) if bomb_planted else None
        side = side_evidence.get(key, {})
        preferred_team = side.get("team_t") if planting_side == "T" else side.get("team_ct") if planting_side == "CT" else None
        roster_team = identify_player_team(planting_player, team_rosters, preferred_team=clean_string(preferred_team)) if bomb_planted else None
        if roster_team:
            planting_team = roster_team
        elif planting_side == side_evidence.get(key, {}).get("target_team_side") and planting_side != "unknown":
            planting_team = target_team
        elif planting_side not in {None, "unknown"}:
            planting_team = row.get("opponent")
        else:
            planting_team = None
        plants[key] = {
            "bomb_planted": bomb_planted,
            "bombsite": bombsite,
            "plant_tick": plant.get("tick") or row.get("bomb_plant"),
            "planting_player": planting_player,
            "planting_team": planting_team,
            "planting_side": planting_side,
        }
    return plants


def side_for_player_in_round(player_name: str | None, row: pd.Series, side: dict[str, object], *, target_team: str, team_rosters: TeamRosters) -> str:
    if player_name and normalize_player_name(player_name) in roster_players(team_rosters, target_team):
        return str(side.get("target_team_side") or "unknown")
    return opposite_side(str(side.get("target_team_side") or "unknown"))


def build_round_state_audit(state: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "total_rounds": len(state),
                "target_team_side_counts": value_counts_string(state, "target_team_side"),
                "side_resolution_confidence_counts": value_counts_string(state, "side_resolution_confidence"),
                "bomb_planted_counts": value_counts_string(state, "bomb_planted"),
                "planting_team_counts": value_counts_string(state, "planting_team"),
                "target_site_model_label_counts": value_counts_string(state, "target_site_model_label"),
                "label_source_counts": value_counts_string(state, "label_source"),
                "rounds_side_unknown": int((state["target_team_side"] == "unknown").sum()),
                "rounds_label_ab_high_confidence": int((state["label_confidence"] == "high").sum()),
            }
        ]
    )


def load_player_rosters(path: Path) -> TeamRosters:
    if not path.exists():
        return default_team_rosters()
    with path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}
    rosters: TeamRosters = {}
    for team in content.get("teams", []):
        team_name = clean_string(team.get("team_name"))
        if not team_name:
            continue
        players: set[str] = set()
        for player in team.get("players", []):
            if isinstance(player, str):
                players.add(normalize_player_name(player))
                continue
            player_name = player.get("player_name") or player.get("name")
            players.add(normalize_player_name(player_name))
            for alias in player.get("aliases", []):
                players.add(normalize_player_name(alias))
        rosters[team_name] = {player for player in players if player}
    return rosters or default_team_rosters()


def default_team_rosters() -> TeamRosters:
    return {"Vitality": DEFAULT_TARGET_PLAYERS["vitality"]}


def roster_players(team_rosters: TeamRosters, team_name: str) -> set[str]:
    for roster_team, players in team_rosters.items():
        if names_match(roster_team, team_name):
            return players
    return DEFAULT_TARGET_PLAYERS.get(team_name.lower(), set())


def build_player_team_index(team_rosters: TeamRosters) -> dict[str, set[str]]:
    player_team_index: dict[str, set[str]] = {}
    for team_name, players in team_rosters.items():
        for player_name in players:
            player_team_index.setdefault(player_name, set()).add(team_name)
    return player_team_index


def identify_player_team(player_name: str | None, team_rosters: TeamRosters, *, preferred_team: str | None = None) -> str | None:
    if not player_name:
        return None
    candidates = build_player_team_index(team_rosters).get(normalize_player_name(player_name), set())
    if preferred_team:
        for candidate in candidates:
            if names_match(candidate, preferred_team):
                return candidate
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def best_roster_teams_for_round(roster_grouped: pd.DataFrame, key: tuple[str, int]) -> dict[str, str]:
    if roster_grouped.empty:
        return {}
    matches = roster_grouped[(roster_grouped["source_parse_id"] == key[0]) & (roster_grouped["round_num"] == key[1])]
    side_teams = {}
    for side in ["T", "CT"]:
        side_matches = matches[matches["side"].map(normalize_side) == side].sort_values("roster_players", ascending=False)
        if not side_matches.empty and int(side_matches.iloc[0]["roster_players"]) >= 2:
            side_teams[side] = str(side_matches.iloc[0]["roster_team"])
    return side_teams


def write_round_state_outputs(state: pd.DataFrame, audit: pd.DataFrame, output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs = {}
    for name, df in [("round_state_resolved", state), ("round_state_audit", audit)]:
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                df.to_csv(path, index=False) if suffix == "csv" else df.to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def normalize_side(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"t", "terrorist", "terrorists"}:
        return "T"
    if text in {"ct", "counterterrorist", "counter-terrorist", "counterterrorists"}:
        return "CT"
    return "unknown"


def opposite_side(side: str) -> str:
    return {"T": "CT", "CT": "T"}.get(side, "unknown")


def normalize_bombsite(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"a", "bombsitea", "bombsite_a", "site_a"}:
        return "A"
    if text in {"b", "bombsiteb", "bombsite_b", "site_b"}:
        return "B"
    return None


def normalize_player_name(value: object) -> str:
    return str(value or "").strip().lower().replace("ø", "o")


def first_present(*values: object) -> object | None:
    for value in values:
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        if str(value).strip():
            return value
    return None


def names_match(left: str, right: str) -> bool:
    return left.strip().lower() == right.strip().lower()


def round_key(row: pd.Series) -> tuple[str, int]:
    return str(row.get("parse_id") or row.get("source_parse_id")), int(row.get("round_num"))


def state_quality(target_side: str, plant: dict[str, object], target_label: str | None) -> tuple[str, str | None]:
    if target_side == "unknown":
        return "side_unknown", "Could not resolve target team side for this round."
    if plant.get("bomb_planted") and not target_label:
        return "plant_not_target_team", "Bomb was planted, but not by target team on T side."
    if target_label:
        return "label_high_confidence", None
    return "no_target_label", "No target-team A/B plant label for this round."


def value_counts_string(df: pd.DataFrame, column: str) -> str:
    if column not in df.columns:
        return ""
    counts = df[column].value_counts(dropna=False)
    return "; ".join(f"{index}={value}" for index, value in counts.items())


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Round state resolution summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve round state, sides, plant ownership, and conservative A/B labels.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, _, outputs, summary = run_round_state_pipeline(args.config, force=args.force, dry_run=args.dry_run)
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
