from __future__ import annotations

import argparse
import math
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import polars as pl

from src.config.schemas import load_project_config
from src.features.demo_timing import run_demo_timing_pipeline
from src.features.feature_windows import FeatureWindow, configured_feature_windows
from src.features.region_mapping import add_region_columns
from src.features.utility_features import canonical_utility_type, count_inventory
from src.maps.registry import MapRegistry, load_map_registry
from src.maps.semantic import legacy_groups_for_semantic, place_lookup_from_registry
from src.utils.io import read_table_pair, write_dataframe_outputs
from src.utils.logging import configure_logging


FEATURE_ENGINE = "role-aware"
SNAPSHOT_SECONDS = (10, 15, 20, 25, 35)
ROLES = ("attack", "defense")
UTILITY_PLURALS = {
    "smoke": "smokes",
    "flash": "flashes",
    "molotov": "molotovs",
    "he": "he_grenades",
    "decoy": "decoys",
}
ID_COLUMNS = [
    "round_feature_id",
    "round_id",
    "parse_id",
    "dem_file_id",
    "series_id",
    "target_team",
    "opponent",
    "map_name",
    "round_num",
    "target_team_side",
    "target_site_model_label",
    "label_confidence",
    "tickrate",
    "timing_contract_version",
    "feature_engine",
]


def run_role_feature_pipeline(
    config_path: Path,
    *,
    target_map: str,
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    map_registry_path: Path = Path("configs/maps/map_registry.yaml"),
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    target_team = target_team or project.target_teams[0]
    registry_path = map_registry_path if map_registry_path.is_absolute() else project_root / map_registry_path
    registry = load_map_registry(target_map, registry_path=registry_path)
    silver_dir = project.parsed_silver_dir if project.parsed_silver_dir.is_absolute() else project_root / project.parsed_silver_dir
    timing_path = silver_dir / "demo_timing"
    if not timing_path.with_suffix(".parquet").exists() and not timing_path.with_suffix(".csv").exists():
        run_demo_timing_pipeline(config_path, force=force, dry_run=False)

    state = read_table_pair(project_root / "data/gold/round_state/round_state_resolved")
    legacy = read_table_pair(project_root / "data/gold/round_features/round_features_mvp")
    timing = read_table_pair(timing_path)
    metadata = build_round_metadata(
        state,
        legacy,
        timing,
        target_map=registry.display_name,
        target_team=target_team,
    )
    role_ticks = load_role_ticks(silver_dir / "ticks.parquet", metadata, registry)
    windows = unique_windows(configured_feature_windows(project.feature_windows))
    role_features = build_role_feature_frame(metadata, role_ticks, registry, windows)
    utility_events = load_role_utility_events(silver_dir, metadata, role_ticks)
    role_features = add_role_utility_usage(role_features, utility_events, windows)
    canonical = add_target_team_projection(role_features)
    dictionary = build_feature_dictionary(canonical)
    aliases = build_feature_aliases(windows)
    audit = build_role_feature_audit(metadata, role_ticks, canonical, registry)
    frames = build_output_views(canonical, dictionary, aliases, audit)

    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = (
            project.role_feature_output_dir
            if project.role_feature_output_dir.is_absolute()
            else project_root / project.role_feature_output_dir
        )
        outputs = write_dataframe_outputs(
            frames,
            output_dir,
            force=force,
            formats=tuple(project.output_formats),
        )
    summary = {
        "map_id": registry.map_id,
        "target_team": target_team,
        "rounds": len(canonical),
        "feature_columns": len(dictionary),
        "attack_tick_rows": int((role_ticks["role"] == "attack").sum()) if not role_ticks.empty else 0,
        "defense_tick_rows": int((role_ticks["role"] == "defense").sum()) if not role_ticks.empty else 0,
        "unknown_place_share": float((role_ticks["region_name"] == "UNKNOWN").mean()) if not role_ticks.empty else math.nan,
        "feature_engine": FEATURE_ENGINE,
    }
    return frames, outputs, summary


def build_round_metadata(
    state: pd.DataFrame,
    legacy: pd.DataFrame,
    timing: pd.DataFrame,
    *,
    target_map: str,
    target_team: str,
) -> pd.DataFrame:
    scoped = state[
        state["map_name"].astype(str).str.casefold().eq(target_map.casefold())
        & state["target_team"].astype(str).str.casefold().eq(target_team.casefold())
    ].copy()
    legacy_columns = [
        "round_feature_id",
        "round_id",
        "round_start_tick",
        "freeze_end_tick",
        "round_end_tick",
    ]
    legacy_ticks = legacy[legacy_columns].drop_duplicates("round_id")
    for column in ("round_start_tick", "freeze_end_tick", "round_end_tick"):
        if column in scoped.columns:
            scoped = scoped.drop(columns=column)
    scoped = scoped.merge(legacy_ticks, on="round_id", how="left")
    timing_columns = [
        "parse_id",
        "tickrate",
        "timing_contract_version",
        "tickrate_resolution_method",
    ]
    scoped = scoped.merge(timing[timing_columns].drop_duplicates("parse_id"), on="parse_id", how="left")
    scoped["anchor_tick"] = pd.to_numeric(scoped["freeze_end_tick"], errors="coerce").fillna(
        pd.to_numeric(scoped["round_start_tick"], errors="coerce")
    )
    for column in ("round_num", "round_start_tick", "freeze_end_tick", "round_end_tick", "anchor_tick"):
        scoped[column] = pd.to_numeric(scoped[column], errors="coerce")
    if scoped["tickrate"].isna().any():
        raise ValueError("Every scoped round must resolve to a per-demo tickrate.")
    if scoped["anchor_tick"].isna().any():
        raise ValueError("Every scoped round must have freeze_end_tick or round_start_tick.")
    return scoped.sort_values(["parse_id", "round_num"], kind="stable").reset_index(drop=True)


def load_role_ticks(ticks_path: Path, metadata: pd.DataFrame, registry: MapRegistry) -> pd.DataFrame:
    if metadata.empty:
        return pd.DataFrame()
    join_columns = [
        "round_feature_id",
        "round_id",
        "parse_id",
        "round_num",
        "anchor_tick",
        "round_end_tick",
        "tickrate",
    ]
    join_frame = pl.from_pandas(metadata[join_columns])
    scan = pl.scan_parquet(ticks_path)
    available = set(scan.collect_schema().names())
    tick_columns = [
        column
        for column in (
            "source_parse_id",
            "round_num",
            "tick",
            "X",
            "Y",
            "Z",
            "side",
            "name",
            "steamid",
            "place",
            "health",
            "inventory",
        )
        if column in available
    ]
    max_seconds = int(max(SNAPSHOT_SECONDS[-1], 115))
    sampled = (
        scan.select(tick_columns)
        .filter(pl.col("source_parse_id").cast(pl.Utf8).is_in(metadata["parse_id"].astype(str).tolist()))
        .join(
            join_frame.lazy(),
            left_on=["source_parse_id", "round_num"],
            right_on=["parse_id", "round_num"],
            how="inner",
        )
        .filter(pl.col("side").cast(pl.Utf8).str.to_lowercase().is_in(["t", "ct"]))
        .with_columns(((pl.col("tick") - pl.col("anchor_tick")) / pl.col("tickrate")).alias("seconds_from_freeze_end"))
        .filter((pl.col("seconds_from_freeze_end") >= 0) & (pl.col("seconds_from_freeze_end") <= max_seconds))
        .filter(pl.col("round_end_tick").is_null() | (pl.col("tick") <= pl.col("round_end_tick")))
        .with_columns(pl.col("seconds_from_freeze_end").floor().cast(pl.Int32).alias("second_bucket"))
        .sort(["round_feature_id", "side", "steamid", "second_bucket", "tick"])
        .group_by(["round_feature_id", "side", "steamid", "second_bucket"], maintain_order=True)
        .agg(pl.all().last())
        .collect(engine="streaming")
        .to_pandas()
    )
    if sampled.empty:
        return sampled
    sampled["side"] = sampled["side"].astype(str).str.casefold()
    sampled["role"] = sampled["side"].map({"t": "attack", "ct": "defense"})
    return add_region_columns(
        sampled,
        place_column="place" if "place" in sampled.columns else None,
        lookup=place_lookup_from_registry(registry),
    )


def build_role_feature_frame(
    metadata: pd.DataFrame,
    role_ticks: pd.DataFrame,
    registry: MapRegistry,
    windows: list[FeatureWindow],
) -> pd.DataFrame:
    base_columns = [column for column in ID_COLUMNS if column in metadata.columns and column != "feature_engine"]
    result = metadata[base_columns].copy()
    result["feature_engine"] = FEATURE_ENGINE
    feature_rows: list[dict[str, Any]] = []
    groups = {key: value for key, value in role_ticks.groupby("round_feature_id")} if not role_ticks.empty else {}
    semantics = sorted(registry.semantic_groups)
    for round_feature_id in result["round_feature_id"]:
        row: dict[str, Any] = {"round_feature_id": round_feature_id}
        round_ticks = groups.get(round_feature_id, pd.DataFrame())
        for role in ROLES:
            role_frame = round_ticks[round_ticks.get("role", pd.Series(dtype=str)).eq(role)].copy()
            add_snapshot_features(row, role_frame, role)
            add_inventory_features(row, role_frame, role)
            add_semantic_features(row, role_frame, role, registry, semantics, windows)
        feature_rows.append(row)
    return result.merge(pd.DataFrame(feature_rows), on="round_feature_id", how="left")


def add_snapshot_features(row: dict[str, Any], frame: pd.DataFrame, role: str) -> None:
    for seconds in SNAPSHOT_SECONDS:
        cumulative = frame[frame.get("seconds_from_freeze_end", pd.Series(dtype=float)) <= seconds]
        latest = latest_player_rows(cumulative)
        alive = latest[pd.to_numeric(latest.get("health"), errors="coerce").fillna(100) > 0] if not latest.empty else latest
        coordinates = alive[["X", "Y", "Z"]].apply(pd.to_numeric, errors="coerce").dropna() if not alive.empty else pd.DataFrame()
        xy = coordinates[["X", "Y"]].to_numpy(dtype=float) if not coordinates.empty else np.empty((0, 2))
        row[f"{role}_players_alive_{seconds}s_snapshot"] = int(len(alive))
        for axis in ("X", "Y", "Z"):
            key = f"{role}_center_{axis.lower()}_{seconds}s_snapshot"
            row[key] = float(coordinates[axis].mean()) if not coordinates.empty else np.nan
        row[f"{role}_median_pairwise_distance_2d_{seconds}s_snapshot"] = median_pairwise_distance(xy)
        row[f"{role}_median_distance_to_centroid_2d_{seconds}s_snapshot"] = median_distance_to_centroid(xy)
        row[f"{role}_convex_hull_area_2d_{seconds}s_snapshot"] = convex_hull_area(xy)

        accumulated_coordinates = (
            cumulative[["X", "Y", "Z"]].apply(pd.to_numeric, errors="coerce").dropna()
            if not cumulative.empty
            else pd.DataFrame()
        )
        if accumulated_coordinates.empty:
            for axis in ("X", "Y", "Z"):
                row[f"{role}_center_{axis.lower()}_{seconds}s_accumulated"] = np.nan
            row[f"{role}_mean_distance_to_accumulated_center_3d_{seconds}s"] = np.nan
            row[f"{role}_pairwise_distance_proxy_sqrt2_{seconds}s"] = np.nan
        else:
            center = accumulated_coordinates.mean()
            for axis in ("X", "Y", "Z"):
                row[f"{role}_center_{axis.lower()}_{seconds}s_accumulated"] = float(center[axis])
            distances = np.sqrt(((accumulated_coordinates - center) ** 2).sum(axis=1))
            legacy_spread = float(distances.mean())
            row[f"{role}_mean_distance_to_accumulated_center_3d_{seconds}s"] = legacy_spread
            row[f"{role}_pairwise_distance_proxy_sqrt2_{seconds}s"] = legacy_spread * math.sqrt(2)


def add_inventory_features(row: dict[str, Any], frame: pd.DataFrame, role: str) -> None:
    first = frame.sort_values("tick").groupby("steamid", as_index=False).head(1) if not frame.empty else frame
    totals = {key: 0 for key in ("smoke", "flash", "molotov", "he", "decoy")}
    for inventory in first.get("inventory", pd.Series(dtype=object)):
        counts = count_inventory(inventory)
        for key in totals:
            totals[key] += counts[key]
    for key, value in totals.items():
        row[f"{role}_{UTILITY_PLURALS[key]}_start"] = value
    row[f"{role}_total_utility_start"] = sum(totals.values())


def add_semantic_features(
    row: dict[str, Any],
    frame: pd.DataFrame,
    role: str,
    registry: MapRegistry,
    semantics: list[str],
    windows: list[FeatureWindow],
) -> None:
    for window in windows:
        window_frame = frame[
            (frame.get("seconds_from_freeze_end", pd.Series(dtype=float)) >= window.start)
            & (frame.get("seconds_from_freeze_end", pd.Series(dtype=float)) < window.end)
        ]
        for semantic in semantics:
            region_groups = legacy_groups_for_semantic(registry, semantic)
            selected = window_frame[window_frame.get("region_group", pd.Series(dtype=str)).isin(region_groups)]
            row[f"{role}_unique_players_{semantic}_{window.suffix}"] = int(selected.get("steamid", pd.Series()).nunique())
            row[f"{role}_player_seconds_{semantic}_{window.suffix}"] = int(len(selected))


def load_role_utility_events(
    silver_dir: Path,
    metadata: pd.DataFrame,
    role_ticks: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    parse_ids = set(metadata["parse_id"].astype(str))
    for table_name, utility_type in (("smokes", "smoke"), ("infernos", "molotov")):
        path = silver_dir / f"{table_name}.parquet"
        if not path.exists():
            continue
        source = pd.read_parquet(
            path,
            columns=["source_parse_id", "round_num", "entity_id", "start_tick", "thrower_steamid", "thrower_side"],
        )
        source = source[source["source_parse_id"].astype(str).isin(parse_ids)].drop_duplicates(
            ["source_parse_id", "round_num", "entity_id"]
        )
        source = source.rename(columns={"start_tick": "event_tick", "thrower_steamid": "steamid", "thrower_side": "side"})
        source["utility_type"] = utility_type
        source = source.merge(
            metadata[["round_feature_id", "parse_id", "round_num"]],
            left_on=["source_parse_id", "round_num"],
            right_on=["parse_id", "round_num"],
            how="inner",
        )
        rows.append(source)

    grenades_path = silver_dir / "grenades.parquet"
    if grenades_path.exists():
        grenade = (
            pl.scan_parquet(grenades_path)
            .filter(pl.col("source_parse_id").cast(pl.Utf8).is_in(sorted(parse_ids)))
            .group_by(["source_parse_id", "round_num", "entity_id"])
            .agg(
                pl.col("tick").min().alias("event_tick"),
                pl.col("thrower_steamid").first().alias("steamid"),
                pl.col("grenade_type").first().alias("grenade_type"),
            )
            .collect(engine="streaming")
            .to_pandas()
        )
        grenade["utility_type"] = grenade["grenade_type"].map(canonical_utility_type)
        grenade = grenade[grenade["utility_type"].isin(["flash", "he", "decoy"])].copy()
        player_sides = role_ticks[["round_feature_id", "steamid", "side"]].drop_duplicates(
            ["round_feature_id", "steamid"]
        )
        round_keys = metadata[["round_feature_id", "parse_id", "round_num"]]
        grenade = grenade.merge(
            round_keys,
            left_on=["source_parse_id", "round_num"],
            right_on=["parse_id", "round_num"],
            how="inner",
        ).merge(player_sides, on=["round_feature_id", "steamid"], how="left")
        rows.append(grenade)
    if not rows:
        return pd.DataFrame()
    events = pd.concat(rows, ignore_index=True, sort=False)
    timing = metadata[["round_feature_id", "anchor_tick", "round_end_tick", "tickrate"]].drop_duplicates(
        "round_feature_id"
    )
    events = events.merge(timing, on="round_feature_id", how="left")
    events["seconds_from_freeze_end"] = (
        pd.to_numeric(events["event_tick"], errors="coerce") - events["anchor_tick"]
    ) / events["tickrate"]
    events["side"] = events["side"].astype(str).str.casefold()
    events["role"] = events["side"].map({"t": "attack", "ct": "defense"})
    return events[
        events["role"].notna()
        & (events["seconds_from_freeze_end"] >= 0)
        & (events["seconds_from_freeze_end"] <= 115)
        & (pd.to_numeric(events["event_tick"], errors="coerce") <= events["round_end_tick"])
    ].copy()


def add_role_utility_usage(
    feature_frame: pd.DataFrame,
    events: pd.DataFrame,
    windows: list[FeatureWindow],
) -> pd.DataFrame:
    result = feature_frame.copy()
    event_groups = {key: value for key, value in events.groupby("round_feature_id")} if not events.empty else {}
    rows = []
    for round_feature_id in result["round_feature_id"]:
        row: dict[str, Any] = {"round_feature_id": round_feature_id}
        round_events = event_groups.get(round_feature_id, pd.DataFrame())
        for role in ROLES:
            role_events = round_events[round_events.get("role", pd.Series(dtype=str)).eq(role)]
            for window in windows:
                selected = role_events[
                    (role_events.get("seconds_from_freeze_end", pd.Series(dtype=float)) >= window.start)
                    & (role_events.get("seconds_from_freeze_end", pd.Series(dtype=float)) < window.end)
                ]
                for utility_type in ("smoke", "molotov", "flash", "he", "decoy"):
                    row[f"{role}_{UTILITY_PLURALS[utility_type]}_used_{window.suffix}"] = int(
                        (selected.get("utility_type", pd.Series(dtype=str)) == utility_type).sum()
                    )
                row[f"{role}_total_utility_used_{window.suffix}"] = int(len(selected))
        rows.append(row)
    return result.merge(pd.DataFrame(rows), on="round_feature_id", how="left")


def add_target_team_projection(frame: pd.DataFrame) -> pd.DataFrame:
    suffixes = sorted(
        {column.removeprefix("attack_") for column in frame.columns if column.startswith("attack_")}
        & {column.removeprefix("defense_") for column in frame.columns if column.startswith("defense_")}
    )
    target_is_attack = frame["target_team_side"].astype(str).str.casefold().isin(["t", "attack"])
    projected: dict[str, np.ndarray] = {}
    for suffix in suffixes:
        projected[f"target_team_{suffix}"] = np.where(
            target_is_attack,
            frame[f"attack_{suffix}"],
            frame[f"defense_{suffix}"],
        )
        projected[f"opponent_{suffix}"] = np.where(
            target_is_attack,
            frame[f"defense_{suffix}"],
            frame[f"attack_{suffix}"],
        )
    return pd.concat([frame.reset_index(drop=True), pd.DataFrame(projected)], axis=1)


def build_feature_dictionary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in frame.columns:
        if column in ID_COLUMNS:
            continue
        entity = next((prefix for prefix in ("attack", "defense", "target_team", "opponent") if column.startswith(f"{prefix}_")), "round")
        family = infer_family(column)
        map_scope = infer_map_scope(column)
        rows.append(
            {
                "feature_name": column,
                "feature_engine": FEATURE_ENGINE,
                "entity_scope": entity,
                "feature_family": family,
                "map_scope": map_scope,
                "requires_map_registry": map_scope in {"map_abstract", "map_specific"},
                "temporal_semantics": infer_temporal_semantics(column),
                "unit": infer_unit(column),
                "status": "deprecated_proxy" if "proxy_sqrt2" in column else "active",
                "recommended_dispersion_metric": "median_pairwise_distance_2d" if family == "dispersion" else None,
            }
        )
    return pd.DataFrame(rows)


def build_feature_aliases(windows: list[FeatureWindow]) -> pd.DataFrame:
    rows = []
    for seconds in (10, 15, 20, 25, 115):
        for axis in ("x", "y", "z"):
            rows.append(alias(f"team_center_{axis}_{seconds}s", f"attack_center_{axis}_{seconds}s_accumulated", "exact_legacy_semantics"))
        rows.append(alias(f"team_spread_{seconds}s", f"attack_mean_distance_to_accumulated_center_3d_{seconds}s", "exact_legacy_semantics"))
        rows.append(alias(f"avg_pairwise_distance_{seconds}s", f"attack_pairwise_distance_proxy_sqrt2_{seconds}s", "exact_legacy_proxy"))
        rows.append(alias(f"players_alive_{seconds}s", f"attack_players_alive_{seconds}s_snapshot", "snapshot_equivalent"))
    for old, new in (
        ("team_smokes_start", "attack_smokes_start"),
        ("team_flashes_start", "attack_flashes_start"),
        ("team_molotovs_start", "attack_molotovs_start"),
        ("team_he_start", "attack_he_grenades_start"),
        ("team_decoys_start", "attack_decoys_start"),
        ("team_total_utility_start", "attack_total_utility_start"),
    ):
        rows.append(alias(old, new, "exact_role_rename"))
    for window in windows:
        for semantic in ("mid_control", "a_pressure", "b_pressure", "ct_space"):
            rows.append(
                alias(
                    f"players_{semantic}_{window.suffix}",
                    f"attack_unique_players_{semantic}_{window.suffix}",
                    "semantic_replacement",
                )
            )
            rows.append(
                alias(
                    f"time_{semantic}_{window.suffix}",
                    f"attack_player_seconds_{semantic}_{window.suffix}",
                    "unit_corrected_seconds",
                )
            )
    return pd.DataFrame(rows).drop_duplicates("legacy_feature_name").reset_index(drop=True)


def alias(old: str, new: str, compatibility: str) -> dict[str, str]:
    return {
        "legacy_feature_name": old,
        "canonical_feature_name": new,
        "compatibility": compatibility,
        "migration_status": "legacy_preserved_canonical_available",
    }


def build_role_feature_audit(
    metadata: pd.DataFrame,
    role_ticks: pd.DataFrame,
    canonical: pd.DataFrame,
    registry: MapRegistry,
) -> pd.DataFrame:
    attack_rounds = int(role_ticks.loc[role_ticks.get("role", pd.Series(dtype=str)).eq("attack"), "round_feature_id"].nunique()) if not role_ticks.empty else 0
    defense_rounds = int(role_ticks.loc[role_ticks.get("role", pd.Series(dtype=str)).eq("defense"), "round_feature_id"].nunique()) if not role_ticks.empty else 0
    return pd.DataFrame(
        [
            {
                "map_id": registry.map_id,
                "map_name": registry.display_name,
                "region_schema_version": registry.region_schema_version,
                "feature_engine": FEATURE_ENGINE,
                "expected_rounds": len(metadata),
                "output_rounds": len(canonical),
                "attack_rounds_with_ticks": attack_rounds,
                "defense_rounds_with_ticks": defense_rounds,
                "unknown_place_share": float((role_ticks["region_name"] == "UNKNOWN").mean()) if not role_ticks.empty else math.nan,
                "all_tickrates_resolved": bool(metadata["tickrate"].notna().all()),
                "unique_tickrates": "|".join(str(value) for value in sorted(metadata["tickrate"].unique())),
                "status": "passed"
                if len(metadata) == len(canonical) and attack_rounds == len(metadata) and defense_rounds == len(metadata)
                else "warning",
            }
        ]
    )


def build_output_views(
    canonical: pd.DataFrame,
    dictionary: pd.DataFrame,
    aliases: pd.DataFrame,
    audit: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    ids = [column for column in ID_COLUMNS if column in canonical.columns]
    label_columns = [column for column in ("target_site_model_label", "label_confidence") if column in ids]
    base_ids = [column for column in ids if column not in label_columns]
    map_features = set(dictionary.loc[dictionary["map_scope"] != "global", "feature_name"])
    return {
        "round_role_features": canonical,
        "round_attack_features": canonical[base_ids + [column for column in canonical if column.startswith("attack_")] + label_columns],
        "round_defense_features": canonical[base_ids + [column for column in canonical if column.startswith("defense_")] + label_columns],
        "round_target_team_features": canonical[
            base_ids
            + [column for column in canonical if column.startswith("target_team_") and column not in ids]
            + label_columns
        ],
        "round_map_features": canonical[base_ids + [column for column in canonical if column in map_features] + label_columns],
        "feature_dictionary": dictionary,
        "feature_aliases": aliases,
        "role_feature_audit": audit,
    }


def latest_player_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.sort_values("tick").groupby("steamid", as_index=False).tail(1)


def median_pairwise_distance(points: np.ndarray) -> float:
    if len(points) < 2:
        return math.nan
    distances = [float(np.linalg.norm(points[left] - points[right])) for left, right in combinations(range(len(points)), 2)]
    return float(np.median(distances))


def median_distance_to_centroid(points: np.ndarray) -> float:
    if len(points) == 0:
        return math.nan
    centroid = points.mean(axis=0)
    return float(np.median(np.linalg.norm(points - centroid, axis=1)))


def convex_hull_area(points: np.ndarray) -> float:
    unique = sorted(set(map(tuple, points.tolist())))
    if len(unique) < 3:
        return 0.0 if unique else math.nan

    def cross(origin: tuple[float, float], left: tuple[float, float], right: tuple[float, float]) -> float:
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    return abs(
        sum(
            hull[index][0] * hull[(index + 1) % len(hull)][1]
            - hull[(index + 1) % len(hull)][0] * hull[index][1]
            for index in range(len(hull))
        )
    ) / 2.0


def unique_windows(windows: list[FeatureWindow]) -> list[FeatureWindow]:
    seen: set[tuple[int, int]] = set()
    result = []
    for window in windows:
        key = (window.start, window.end)
        if key not in seen:
            seen.add(key)
            result.append(window)
    return result


def infer_family(name: str) -> str:
    if any(token in name for token in ("pairwise", "distance_to_centroid", "convex_hull", "distance_to_accumulated")):
        return "dispersion"
    if "center_" in name:
        return "position_center"
    if "players_alive" in name:
        return "survival"
    if "utility" in name or any(
        token in name for token in ("smokes", "flashes", "molotovs", "he_grenades", "decoys")
    ):
        return "utility"
    if "unique_players" in name or "player_seconds" in name:
        return "semantic_area_control"
    return "round_context"


def infer_map_scope(name: str) -> str:
    if any(f"_center_{axis}_" in name for axis in ("x", "y", "z")):
        return "map_specific"
    if "unique_players" in name or "player_seconds" in name:
        return "map_abstract"
    return "global"


def infer_temporal_semantics(name: str) -> str:
    if "snapshot" in name:
        return "last_observation_at_or_before_second"
    if "accumulated" in name or "proxy_sqrt2" in name:
        return "all_sampled_observations_from_freeze_end"
    if "_start" in name:
        return "first_observation_after_freeze_end"
    if "_used_" in name or "unique_players" in name or "player_seconds" in name:
        return "half_open_window_seconds"
    return "round_level"


def infer_unit(name: str) -> str:
    if "center_" in name or "distance" in name:
        return "source_coordinate_units"
    if "convex_hull_area" in name:
        return "source_coordinate_units_squared"
    if "player_seconds" in name:
        return "player_seconds"
    if any(
        token in name
        for token in ("players", "utility", "smokes", "flashes", "molotovs", "he_grenades", "decoys")
    ):
        return "count"
    return "dimensionless"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build generic attack/defense and target/opponent feature views.")
    parser.add_argument("--config", type=Path, default=Path("configs/project.yaml"))
    parser.add_argument("--target-map", required=True)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--map-registry", type=Path, default=Path("configs/maps/map_registry.yaml"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    configure_logging()
    _, outputs, summary = run_role_feature_pipeline(
        args.config,
        target_map=args.target_map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
        map_registry_path=args.map_registry,
    )
    print({**summary, "outputs": {key: str(value) for key, value in outputs.items()}})


if __name__ == "__main__":
    main()
