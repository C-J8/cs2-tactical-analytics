from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config.schemas import load_project_config
from src.features.bomb_context import build_bomb_carrier_timeline
from src.features.death_context import build_death_context
from src.features.position_features import build_position_outputs, load_early_ticks
from src.features.region_mapping import build_place_lookup, choose_place_column, load_region_config
from src.features.round_progression import build_round_outcome_context, build_round_region_timeline
from src.features.side_dataset_audit import build_side_dataset_audit
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


def run_side_dataset_pipeline(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    window_end: int = 30,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    silver_dir = project.parsed_silver_dir
    gold_dir = silver_dir.parent.parent / "gold"

    round_features = read_catalog(gold_dir / "round_features" / "round_features_mvp.parquet")
    round_base = read_catalog(gold_dir / "round_features" / "round_base.parquet")
    round_features = attach_round_timing(round_features, round_base)
    round_state_path = gold_dir / "round_state" / "round_state_resolved.parquet"
    if not round_state_path.exists():
        raise FileNotFoundError(
            "round_state_resolved.parquet is required before building side datasets. "
            "Run: python -m src.features.round_state --config configs/project.yaml --force"
        )
    round_features = apply_round_state(round_features, read_catalog(round_state_path))
    round_features = normalize_side_values(round_features)
    filtered = round_features[(round_features["target_team"] == target_team) & (round_features["map_name"] == target_map)].copy()
    datasets = build_side_datasets(filtered)

    region_config = load_region_config(Path("configs/maps/mirage_regions.yaml"))
    region_lookup = build_place_lookup(region_config)
    early_ticks = load_early_ticks(str(silver_dir / "ticks.parquet"), filtered, window_end=window_end)
    place_column = choose_place_column(list(early_ticks.columns), region_config)
    region_presence, _ = build_position_outputs(early_ticks, filtered, region_lookup=region_lookup, place_column=place_column)

    kills = pd.read_parquet(silver_dir / "kills.parquet") if (silver_dir / "kills.parquet").exists() else pd.DataFrame()
    bomb = pd.read_parquet(silver_dir / "bomb.parquet") if (silver_dir / "bomb.parquet").exists() else pd.DataFrame()
    utility_events_path = gold_dir / "utility_events" / "utility_events.parquet"
    utility_events = read_catalog(utility_events_path) if utility_events_path.exists() else pd.DataFrame()
    death_context = build_death_context(kills, filtered, region_lookup=region_lookup)
    bomb_timeline = build_bomb_carrier_timeline(early_ticks, filtered, bomb, region_lookup=region_lookup, place_column=place_column)
    region_timeline = build_round_region_timeline(region_presence, filtered, utility_events, death_context, bomb_timeline)
    outcome_context = build_round_outcome_context(filtered, region_timeline, death_context, bomb_timeline)
    notes = {
        "ct_side": "Uses round_state_resolved when available; a zero CT-side count now indicates side resolution should be audited."
    }
    side_audit = build_side_dataset_audit(datasets, notes=notes)

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_all_outputs(gold_dir, datasets, region_timeline, death_context, bomb_timeline, outcome_context, side_audit, force=force))
    frames = {
        **datasets,
        "round_region_timeline": region_timeline,
        "death_context_by_round": death_context,
        "bomb_carrier_timeline": bomb_timeline,
        "round_outcome_context": outcome_context,
        "side_dataset_audit": side_audit,
    }
    summary = {
        "t_side_all": len(datasets["t_side_all"]),
        "t_side_planted": len(datasets["t_side_planted"]),
        "ct_side": len(datasets["ct_side"]),
        "round_region_timeline": len(region_timeline),
        "death_context": len(death_context),
        "bomb_carrier_timeline": len(bomb_timeline),
        "round_outcome_context": len(outcome_context),
    }
    return frames, outputs, summary


def normalize_side_values(round_features: pd.DataFrame) -> pd.DataFrame:
    result = round_features.copy()
    result["target_team_side"] = result["target_team_side"].map(lambda value: str(value).upper() if pd.notna(value) else value)
    result["target_team_side"] = result["target_team_side"].replace({"TERRORIST": "T", "CT": "CT"})
    if "bomb_planted" in result.columns and "target_site_model_label" in result.columns:
        result["bomb_planted"] = result["bomb_planted"].map(bool) | result["target_site_model_label"].isin(["A", "B"])
    return result


def attach_round_timing(round_features: pd.DataFrame, round_base: pd.DataFrame) -> pd.DataFrame:
    timing_columns = [
        "round_feature_id",
        "round_start_tick",
        "freeze_end_tick",
        "round_end_tick",
        "round_duration_ticks",
        "round_duration_seconds",
    ]
    missing = [column for column in timing_columns if column != "round_feature_id" and column not in round_features.columns]
    if not missing or round_base.empty:
        return round_features
    return round_features.merge(round_base[[column for column in timing_columns if column in round_base.columns]], on="round_feature_id", how="left")


def apply_round_state(round_features: pd.DataFrame, round_state: pd.DataFrame) -> pd.DataFrame:
    state_columns = [
        "round_id",
        "target_team_side",
        "winner_team",
        "winner_side",
        "bomb_planted",
        "bombsite",
        "target_site_model_label",
        "label_source",
        "label_confidence",
    ]
    available = [column for column in state_columns if column in round_state.columns]
    merged = round_features.drop(columns=[column for column in available if column in round_features.columns and column != "round_id"]).merge(
        round_state[available],
        on="round_id",
        how="left",
    )
    return merged


def build_side_datasets(round_features: pd.DataFrame) -> dict[str, pd.DataFrame]:
    t_all = round_features[round_features["target_team_side"] == "T"].copy()
    t_planted = t_all[
        (t_all["bomb_planted"].map(bool))
        & (t_all["target_site_model_label"].isin(["A", "B"]))
        & (t_all.get("label_confidence", pd.Series(index=t_all.index, dtype="object")) == "high")
    ].copy()
    ct_side = round_features[round_features["target_team_side"] == "CT"].copy()
    return {
        "t_side_all": decorate_dataset(t_all, "t_side_all"),
        "t_side_planted": decorate_dataset(t_planted, "t_side_planted"),
        "ct_side": decorate_dataset(ct_side, "ct_side"),
    }


def decorate_dataset(df: pd.DataFrame, dataset_type: str) -> pd.DataFrame:
    result = df.copy()
    result["dataset_type"] = dataset_type
    result["is_model_ab_candidate"] = dataset_type == "t_side_planted"
    result["is_progression_candidate"] = dataset_type == "t_side_all"
    result["is_defense_analysis_candidate"] = dataset_type == "ct_side"
    return result


def write_all_outputs(
    gold_dir: Path,
    datasets: dict[str, pd.DataFrame],
    region_timeline: pd.DataFrame,
    death_context: pd.DataFrame,
    bomb_timeline: pd.DataFrame,
    outcome_context: pd.DataFrame,
    side_audit: pd.DataFrame,
    *,
    force: bool,
) -> dict[str, Path]:
    outputs = {}
    round_dir = ensure_dir(gold_dir / "round_features")
    progression_dir = ensure_dir(gold_dir / "round_progression")
    audit_dir = ensure_dir(gold_dir / "feature_audit")
    for dataset_type, df in datasets.items():
        outputs.update(write_frame(df, round_dir / f"round_features_{dataset_type}", csv=True, parquet=True, force=force))
    outputs.update(write_frame(region_timeline, progression_dir / "round_region_timeline", csv=True, parquet=True, force=force))
    outputs.update(write_frame(death_context, progression_dir / "death_context_by_round", csv=True, parquet=True, force=force))
    outputs.update(write_frame(bomb_timeline, progression_dir / "bomb_carrier_timeline", csv=True, parquet=True, force=force))
    outputs.update(write_frame(outcome_context, progression_dir / "round_outcome_context", csv=True, parquet=True, force=force))
    outputs.update(write_frame(side_audit, audit_dir / "side_dataset_audit", csv=True, parquet=True, force=force))
    return outputs


def write_frame(df: pd.DataFrame, base_path: Path, *, csv: bool, parquet: bool, force: bool) -> dict[str, Path]:
    outputs = {}
    if csv:
        path = base_path.with_suffix(".csv")
        if force or not path.exists():
            df.to_csv(path, index=False)
        outputs[path.name] = path
    if parquet:
        path = base_path.with_suffix(".parquet")
        if force or not path.exists():
            df.to_parquet(path, index=False)
        outputs[path.name] = path
    return outputs


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Side datasets and round progression summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build side-specific datasets and round progression tables.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--window-end", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_side_dataset_pipeline(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        window_end=args.window_end,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
