from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config.schemas import load_project_config, load_yaml
from src.features.feature_audit import build_feature_audit
from src.features.feature_windows import configured_feature_windows
from src.features.map_refactor_audit import (
    build_map_refactor_audits,
    build_post_refactor_frames,
    elapsed_seconds,
    load_candidate_feature_set,
    load_compatibility_baselines,
    load_feature_contract,
    measure_start,
)
from src.features.position_features import build_position_outputs, load_early_ticks
from src.features.region_mapping import choose_place_column, load_region_mapping_from_registry
from src.features.round_context import add_score_diff_before_round, build_round_base
from src.features.utility_features import build_player_round_utility, build_utility_events
from src.maps.identity import same_map
from src.maps.semantic import legacy_feature_groups_for_registry
from src.storage.scoped_gold import GOLD_DATASET_SPECS, make_gold_scope, write_scoped_dataset
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


FINAL_COLUMNS = [
    "round_feature_id",
    "parse_id",
    "dem_file_id",
    "series_id",
    "round_id",
    "target_team",
    "opponent",
    "map_name",
    "round_num",
    "half",
    "target_team_side",
    "winner_side",
    "winner_team",
    "bomb_planted",
    "target_site_observed",
    "target_site_model_label",
    "label_source",
    "team_center_x_10s",
    "team_center_y_10s",
    "team_center_z_10s",
    "team_center_x_20s",
    "team_center_y_20s",
    "team_center_z_20s",
    "team_spread_10s",
    "team_spread_20s",
    "avg_pairwise_distance_10s",
    "avg_pairwise_distance_20s",
    "players_alive_10s",
    "players_alive_20s",
    "players_mid_0_20",
    "players_a_pressure_0_20",
    "players_b_pressure_0_20",
    "players_ct_space_0_20",
    "time_mid_control_0_20",
    "time_a_pressure_0_20",
    "time_b_pressure_0_20",
    "team_smokes_start",
    "team_flashes_start",
    "team_molotovs_start",
    "team_he_start",
    "team_decoys_start",
    "team_total_utility_start",
    "smokes_used_0_20",
    "molotovs_used_0_20",
    "flashes_used_0_20",
    "he_used_0_20",
    "total_utility_used_0_20",
    "smokes_to_mid_control_0_20",
    "smokes_to_a_pressure_0_20",
    "smokes_to_b_pressure_0_20",
    "molotovs_to_mid_control_0_20",
    "molotovs_to_a_pressure_0_20",
    "molotovs_to_b_pressure_0_20",
    "first_smoke_time",
    "first_molotov_time",
    "first_utility_time",
    "feature_quality_status",
    "feature_notes",
]


def run_feature_pipeline(
    config_path: Path,
    *,
    limit_demos: int | None = None,
    force: bool = False,
    dry_run: bool = False,
    window_end: int | None = None,
    target_map: str | None = None,
    target_team: str | None = None,
    map_registry_path: Path = Path("configs/maps/map_registry.yaml"),
    feature_contract_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Path], dict[str, int]]:
    started_at = measure_start()
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    target_map = target_map or project.target_maps[0]
    target_team = target_team or project.target_teams[0]
    silver_dir = project.parsed_silver_dir if project.parsed_silver_dir.is_absolute() else project_root / project.parsed_silver_dir
    gold_dir = project_root / "data" / "gold"
    warnings: list[str] = []
    feature_windows = configured_feature_windows(project.feature_windows)
    if window_end is not None:
        warnings.append("--window-end is deprecated; using feature_windows from configs/project.yaml.")

    effective_registry_path = map_registry_path if map_registry_path.is_absolute() else project_root / map_registry_path
    if not effective_registry_path.exists() and not map_registry_path.is_absolute() and map_registry_path.exists():
        effective_registry_path = map_registry_path
    registry, region_lookup, region_config = load_region_mapping_from_registry(target_map, registry_path=effective_registry_path)
    feature_contract = load_feature_contract(gold_dir, feature_contract_path)
    candidate_feature_set = load_candidate_feature_set(gold_dir)
    baselines = load_compatibility_baselines(gold_dir)
    region_feature_groups = legacy_feature_groups_for_registry(registry, ["mid_control", "a_pressure", "b_pressure", "ct_space"])
    utility_region_groups = legacy_feature_groups_for_registry(registry, ["mid_control", "a_pressure", "b_pressure"])

    feature_eligible = read_catalog(silver_dir / "feature_eligible_demos.parquet")
    feature_eligible = feature_eligible[
        (feature_eligible["feature_eligible"] == True)  # noqa: E712
        & (feature_eligible["inferred_map_name"].map(lambda value: same_map(value, target_map, registry_path=effective_registry_path)))
        & (feature_eligible["target_team"] == target_team)
    ].copy()
    if limit_demos is not None:
        feature_eligible = feature_eligible.head(limit_demos)

    rounds = pd.read_parquet(silver_dir / "rounds.parquet")
    bomb = pd.read_parquet(silver_dir / "bomb.parquet") if (silver_dir / "bomb.parquet").exists() else pd.DataFrame()
    round_base = build_round_base(rounds, feature_eligible, bomb)
    if not round_base.empty and "map_name" in round_base.columns:
        round_base["map_name"] = registry.display_name
    round_state_path = gold_dir / "round_state" / "round_state_resolved.parquet"
    existing_round_state = read_catalog(round_state_path) if round_state_path.exists() else pd.DataFrame()
    round_base, score_audit = add_score_diff_before_round(round_base, existing_round_state, target_team=target_team)

    early_ticks = load_early_ticks(str(silver_dir / "ticks.parquet"), round_base, windows=feature_windows)
    place_column = choose_place_column(list(early_ticks.columns), region_config)
    if place_column is None:
        warnings.append("No place-name column found in ticks; region mapping fell back to UNKNOWN.")

    region_presence, position_wide = build_position_outputs(
        early_ticks,
        round_base,
        region_lookup=region_lookup,
        place_column=place_column,
        region_feature_groups=region_feature_groups,
        windows=feature_windows,
    )
    if not region_presence.empty and "map_name" in region_presence.columns:
        region_presence["map_name"] = registry.display_name
    player_utility, utility_start_wide = build_player_round_utility(early_ticks, round_base)
    target_player_names = load_target_player_names(
        project.player_rosters_path if project.player_rosters_path.is_absolute() else project_root / project.player_rosters_path,
        target_team,
    )
    utility_events, utility_events_wide, diagnostics = build_utility_events(
        silver_dir,
        round_base,
        windows=feature_windows,
        region_lookup=region_lookup,
        utility_region_groups=utility_region_groups,
        target_player_names=target_player_names,
    )
    diagnostics["feature_windows_interval"] = ",".join(f"{window.start}-{window.end}" for window in feature_windows if window.window_type == "interval")
    diagnostics["feature_windows_cumulative"] = ",".join(f"{window.start}-{window.end}" for window in feature_windows if window.window_type == "cumulative")
    diagnostics["map_registry_version"] = registry.registry_version
    diagnostics["map_registry_id"] = registry.map_id
    diagnostics["score_diff_status"] = str(score_audit.iloc[0].get("status")) if not score_audit.empty else "warning"
    diagnostics["score_diff_method"] = str(score_audit.iloc[0].get("score_resolution_method")) if not score_audit.empty else "unknown"
    round_features = assemble_round_features(round_base, position_wide, utility_start_wide, utility_events_wide)
    new_runtime_seconds = elapsed_seconds(started_at)
    post_frames = build_post_refactor_frames(round_features=round_features, region_presence=region_presence, baselines=baselines)
    map_refactor_audits = build_map_refactor_audits(
        registry=registry,
        feature_contract=feature_contract,
        candidate_feature_set=candidate_feature_set,
        baselines=baselines,
        post_frames=post_frames,
        new_runtime_seconds=new_runtime_seconds,
    )
    feature_audit = build_feature_audit(
        feature_eligible=feature_eligible,
        round_features=round_features,
        utility_events=utility_events,
        region_presence=region_presence,
        diagnostics=diagnostics,
        warnings=warnings,
    )

    outputs: dict[str, Path] = {}
    if not dry_run:
        scope = make_gold_scope(
            map_id=registry.map_id,
            map_name=registry.display_name,
            target_team=target_team,
            parse_ids=set(feature_eligible["parse_id"].dropna().astype(str)),
            round_feature_ids=set(round_features["round_feature_id"].dropna().astype(str)),
            round_ids=set(round_features["round_id"].dropna().astype(str)),
        )
        outputs.update(
            write_outputs(
                round_features,
                round_base,
                player_utility,
                utility_events,
                region_presence,
                feature_audit,
                map_refactor_audits,
                score_audit,
                gold_dir=gold_dir,
                scope=scope,
                registry_path=effective_registry_path,
                write_reference_audits=registry.map_id == "mirage",
                force=force,
            )
        )
    summary = {
        "demos_used": len(feature_eligible),
        "rounds_generated": len(round_features),
        "utility_events": len(utility_events),
        "region_presence_rows": len(region_presence),
        "map_refactor_unknowns": len(map_refactor_audits["map_feature_unknowns"]),
        "warnings": len(warnings),
    }
    return round_features, outputs, summary


def assemble_round_features(round_base: pd.DataFrame, position_wide: pd.DataFrame, utility_start_wide: pd.DataFrame, utility_events_wide: pd.DataFrame) -> pd.DataFrame:
    result = round_base.copy()
    for frame in [position_wide, utility_start_wide, utility_events_wide]:
        result = result.merge(frame, on="round_feature_id", how="left")
    result["feature_quality_status"] = result["target_site_model_label"].map(lambda value: "ok" if value in {"A", "B"} else "missing_label")
    result["feature_notes"] = result["target_site_model_label"].map(lambda value: None if value in {"A", "B"} else "No observed plant label; target-site inference not implemented.")
    for column in FINAL_COLUMNS:
        if column not in result.columns:
            result[column] = None
    ordered = [column for column in FINAL_COLUMNS if column in result.columns]
    extras = [column for column in result.columns if column not in ordered]
    return result[ordered + extras]


def load_target_player_names(path: Path, target_team: str) -> set[str]:
    if not path.exists():
        return set()
    content = load_yaml(path)
    for team in content.get("teams", []):
        if str(team.get("team_name") or "").strip().casefold() != target_team.strip().casefold():
            continue
        names: set[str] = set()
        for player in team.get("players", []):
            add_normalized(names, player.get("player_name"))
            for alias in player.get("aliases", []) or []:
                add_normalized(names, alias)
        return names
    return set()


def add_normalized(names: set[str], value: object) -> None:
    text = str(value or "").strip().casefold()
    if text:
        names.add(text)


def write_outputs(
    round_features: pd.DataFrame,
    round_base: pd.DataFrame,
    player_utility: pd.DataFrame,
    utility_events: pd.DataFrame,
    region_presence: pd.DataFrame,
    feature_audit: pd.DataFrame,
    map_refactor_audits: dict[str, pd.DataFrame],
    score_audit: pd.DataFrame,
    *,
    gold_dir: Path,
    scope,
    registry_path: Path,
    write_reference_audits: bool,
    force: bool,
) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    for dataset_name, frame in [
        ("round_features_mvp", round_features),
        ("round_base", round_base),
        ("player_round_utility", player_utility),
        ("utility_events", utility_events),
        ("region_presence_by_round", region_presence),
    ]:
        dataset_outputs, _ = write_scoped_dataset(
            frame,
            gold_dir,
            scope,
            GOLD_DATASET_SPECS[dataset_name],
            registry_path=registry_path,
            force=force,
        )
        outputs.update(dataset_outputs)
    audit_dir = ensure_dir(gold_dir / "feature_audit")
    audit_name = "feature_audit" if write_reference_audits else f"feature_audit_{scope.map_id}"
    outputs.update(write_frame(feature_audit, audit_dir / audit_name, csv=True, parquet=True, force=force))
    score_audit_name = "score_before_round_audit" if write_reference_audits else f"score_before_round_audit_{scope.map_id}"
    outputs.update(write_frame(score_audit, audit_dir / score_audit_name, csv=True, parquet=True, force=force))
    if write_reference_audits:
        for name, frame in map_refactor_audits.items():
            outputs.update(write_frame(frame, audit_dir / name, csv=True, parquet=True, force=force))
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
    print("Round feature MVP summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MVP round-level features for eligible CS2 demos.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--limit-demos", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--window-end", type=int, default=None, help="Deprecated; feature windows are read from configs/project.yaml.")
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--map-registry", type=Path, default=Path("configs/maps/map_registry.yaml"))
    parser.add_argument("--feature-contract", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_feature_pipeline(
        args.config,
        limit_demos=args.limit_demos,
        force=args.force,
        dry_run=args.dry_run,
        window_end=args.window_end,
        target_map=args.target_map,
        target_team=args.target_team,
        map_registry_path=args.map_registry,
        feature_contract_path=args.feature_contract,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
