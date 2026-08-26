from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

from src.config.schemas import load_project_config
from src.maps.identity import resolve_map_identity, same_map
from src.maps.place_columns import PLACE_COLUMN_CANDIDATES, detect_place_column
from src.maps.registry import MapRegistry, load_map_registry, normalize_id
from src.utils.io import ensure_dir, read_table_pair
from src.utils.logging import configure_logging
from src.utils.notebooks import code, md, notebook_json
from src.utils.reports import markdown_table as report_markdown_table
from src.utils.reports import now_utc


OUTPUT_NAMES = [
    "map_area_discovery_summary",
    "map_place_inventory",
    "map_place_coordinates",
    "map_place_by_demo",
    "map_place_coverage",
    "map_place_name_stability",
    "map_place_vertical_profile",
    "map_place_coordinate_sample",
    "map_area_discovery_unknowns",
    "mirage_place_registry_crosswalk",
    "mirage_area_discovery_validation",
    "inferno_place_discovery",
    "map_area_discovery_audit",
]
COORD_COLUMNS = ["X", "Y", "Z"]
SIDE_COLUMNS = ["side", "player_side", "team_side"]
DEFAULT_SAMPLE_PER_PLACE = 500


def run_area_discovery(
    config_path: Path,
    *,
    map_name: str,
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    min_observations: int = 1,
    sample_per_place: int = DEFAULT_SAMPLE_PER_PLACE,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, object]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    registry_path = project_root / "configs/maps/map_registry.yaml"
    identity = resolve_map_identity(map_name, registry_path=registry_path)
    target_team = target_team or project.target_teams[0]
    output_dir = project_root / "data/gold/maps/area_discovery"

    parse_manifest = read_optional(project.parse_manifest_dir / "parse_manifest.parquet")
    parse_ids = parse_ids_for_scope(parse_manifest, target_map=identity.display_name, target_team=target_team, registry_path=registry_path)
    ticks_path = project.parsed_silver_dir / "ticks.parquet"

    context = build_scope_context(
        ticks_path,
        parse_ids=parse_ids,
        identity=identity,
        target_team=target_team,
        min_observations=min_observations,
    )
    frames = build_empty_frames(identity=identity, target_team=target_team)

    if context["critical_failures"]:
        frames["map_area_discovery_unknowns"] = pd.DataFrame(context["unknown_rows"], columns=unknown_columns())
        frames["map_area_discovery_summary"] = build_summary(identity=identity, target_team=target_team, context=context, inventory=frames["map_place_inventory"])
        frames["map_area_discovery_audit"] = build_audit(
            identity=identity,
            target_team=target_team,
            context=context,
            frames=frames,
            registry_crosswalk_available=False,
            registry_validation=frames["mirage_area_discovery_validation"],
        )
    else:
        tick_scan = prepare_tick_scan(context["scan"], context["schema_names"], context["place_column"], parse_ids=parse_ids)
        inventory = build_place_inventory(tick_scan, identity=identity, target_team=target_team, total_ticks=int(context["tick_count"]), min_observations=min_observations)
        coordinates = build_place_coordinates(tick_scan, identity=identity, target_team=target_team)
        by_demo = build_place_by_demo(tick_scan, identity=identity, target_team=target_team)
        coverage = build_place_coverage(inventory, by_demo, identity=identity, target_team=target_team, context=context)
        stability = build_place_name_stability(tick_scan, identity=identity, target_team=target_team)
        vertical = build_vertical_profile(coordinates, identity=identity, target_team=target_team)
        sample = build_coordinate_sample(tick_scan, identity=identity, target_team=target_team, sample_per_place=sample_per_place)
        unknowns = build_unknowns(tick_scan, identity=identity, target_team=target_team, context=context)
        registry, crosswalk_available = load_registry_if_available(identity.display_name, registry_path=registry_path)
        crosswalk = build_mirage_crosswalk(inventory, registry=registry, target_team=target_team) if identity.map_id == "mirage" and registry else frames["mirage_place_registry_crosswalk"]
        validation = build_mirage_validation(inventory, crosswalk, registry=registry, identity=identity, target_team=target_team) if identity.map_id == "mirage" and registry else frames["mirage_area_discovery_validation"]
        inferno = build_inferno_discovery(inventory, coordinates, coverage, identity=identity, target_team=target_team) if identity.map_id == "inferno" else frames["inferno_place_discovery"]

        frames.update(
            {
                "map_place_inventory": inventory,
                "map_place_coordinates": coordinates,
                "map_place_by_demo": by_demo,
                "map_place_coverage": coverage,
                "map_place_name_stability": stability,
                "map_place_vertical_profile": vertical,
                "map_place_coordinate_sample": sample,
                "map_area_discovery_unknowns": unknowns,
                "mirage_place_registry_crosswalk": crosswalk,
                "mirage_area_discovery_validation": validation,
                "inferno_place_discovery": inferno,
            }
        )
        frames["map_area_discovery_summary"] = build_summary(identity=identity, target_team=target_team, context=context, inventory=inventory)
        frames["map_area_discovery_audit"] = build_audit(
            identity=identity,
            target_team=target_team,
            context=context,
            frames=frames,
            registry_crosswalk_available=crosswalk_available and identity.map_id == "mirage",
            registry_validation=validation,
        )

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_outputs(frames, output_dir, identity=identity, target_team=target_team, force=force))
        persisted = load_persisted_frames(output_dir, fallback=frames)
        outputs["report"] = write_text(build_report(persisted), project_root / "docs/map_area_discovery.md", force=force)
        outputs["notebook"] = write_text(build_notebook_json(), project_root / "notebooks/20_map_area_discovery.ipynb", force=force)

    audit = frames["map_area_discovery_audit"].iloc[0]
    summary = {
        "map_id": audit["map_id"],
        "map_name": audit["map_name"],
        "target_team": audit["target_team"],
        "source_demos": int(audit["source_demos"]),
        "source_rounds": int(audit["source_rounds"]),
        "source_ticks": int(audit["source_ticks"]),
        "unique_places": int(audit["unique_places"]),
        "ready_for_region_mapping": bool(audit["ready_for_region_mapping"]),
        "status": audit["status"],
    }
    return frames, outputs, summary


def build_scope_context(
    ticks_path: Path,
    *,
    parse_ids: set[str],
    identity,
    target_team: str,
    min_observations: int,
) -> dict[str, Any]:
    del min_observations
    unknowns: list[dict[str, object]] = []
    if not ticks_path.exists():
        unknowns.append(unknown(identity, target_team, "no_ticks", None, 0, "high", True, f"Ticks parquet not found: {ticks_path}", "Run parse_demos for the selected map/team scope."))
        return failed_context(ticks_path, unknowns)
    if not parse_ids:
        unknowns.append(unknown(identity, target_team, "no_scope_demos", None, 0, "high", True, "No parsed demos found for selected map/team scope.", "Run parse_demos and parse_quality for the selected scope."))
        return failed_context(ticks_path, unknowns)

    scan = pl.scan_parquet(ticks_path)
    schema = scan.collect_schema()
    schema_names = schema.names()
    if "source_parse_id" not in schema_names:
        unknowns.append(unknown(identity, target_team, "corrupted_source", None, 0, "high", True, "ticks.parquet is missing source_parse_id.", "Rebuild parsed silver tables."))
        return failed_context(ticks_path, unknowns, scan=scan, schema_names=schema_names)
    place_column = detect_place_column(schema_names)
    if place_column is None:
        unknowns.append(unknown(identity, target_team, "no_place_column", None, 0, "high", True, "No supported place column exists in scoped ticks.", f"Expected one of: {', '.join(PLACE_COLUMN_CANDIDATES)}."))
        return failed_context(ticks_path, unknowns, scan=scan, schema_names=schema_names)
    missing_coords = [column for column in COORD_COLUMNS if column not in schema_names]
    if missing_coords:
        unknowns.append(unknown(identity, target_team, "missing_xyz", None, 0, "high", True, f"ticks.parquet is missing coordinate columns: {', '.join(missing_coords)}.", "Re-run parser with X/Y/Z player properties enabled."))
        return failed_context(ticks_path, unknowns, scan=scan, schema_names=schema_names, place_column=place_column)

    tick_scan = prepare_tick_scan(scan, schema_names, place_column, parse_ids=parse_ids)
    metrics = tick_scan.select(
        pl.len().alias("tick_count"),
        pl.col("raw_place").is_not_null().sum().alias("place_non_null_rows"),
        (pl.col("raw_place").is_not_null() & (pl.col("raw_place").str.strip_chars() != "")).sum().alias("valid_place_rows"),
        pl.col("raw_place").filter(pl.col("raw_place").is_not_null() & (pl.col("raw_place").str.strip_chars() != "")).n_unique().alias("unique_places"),
        pl.col("source_parse_id").n_unique().alias("demo_count"),
        pl.struct(["source_parse_id", "round_num"]).n_unique().alias("round_count"),
        pl.col("player_id").filter(pl.col("player_id").is_not_null()).n_unique().alias("player_count"),
        *[pl.col(axis).is_not_null().sum().alias(f"{axis.lower()}_non_null") for axis in COORD_COLUMNS],
    ).collect()
    values = metrics.row(0, named=True)
    tick_count = int(values["tick_count"])
    valid_place_rows = int(values["valid_place_rows"])
    unique_places = int(values["unique_places"])
    if tick_count == 0:
        unknowns.append(unknown(identity, target_team, "no_ticks", None, 0, "high", True, "No scoped tick rows found for selected parse ids.", "Re-run parse_demos for this scope."))
    if valid_place_rows == 0:
        unknowns.append(unknown(identity, target_team, "all_place_null", None, tick_count, "high", True, "Place column exists, but all scoped values are null or empty.", "Inspect parser output for place-name support."))
    if any(int(values[f"{axis.lower()}_non_null"]) == 0 for axis in COORD_COLUMNS):
        unknowns.append(unknown(identity, target_team, "all_null_coordinates", None, tick_count, "high", True, "At least one coordinate axis is entirely null in scoped ticks.", "Re-run parser with X/Y/Z enabled."))

    critical = any(bool(row["blocking"]) for row in unknowns)
    return {
        "ticks_path": ticks_path,
        "scan": scan,
        "schema_names": schema_names,
        "place_column": place_column,
        "parse_ids": parse_ids,
        "tick_count": tick_count,
        "source_ticks": tick_count,
        "place_non_null_rows": int(values["place_non_null_rows"]),
        "non_null_place_ticks": int(values["place_non_null_rows"]),
        "valid_place_rows": valid_place_rows,
        "valid_named_place_ticks": valid_place_rows,
        "blank_place_ticks": max(int(values["place_non_null_rows"]) - valid_place_rows, 0),
        "invalid_place_ticks": max(tick_count - int(values["place_non_null_rows"]), 0),
        "place_non_null_share": int(values["place_non_null_rows"]) / tick_count if tick_count else 0.0,
        "unique_places": unique_places,
        "demo_count": int(values["demo_count"]),
        "round_count": int(values["round_count"]),
        "player_count": int(values["player_count"]),
        "xyz_available": all(column in schema_names for column in COORD_COLUMNS),
        "critical_failures": critical,
        "unknown_rows": unknowns,
    }


def failed_context(
    ticks_path: Path,
    unknown_rows: list[dict[str, object]],
    *,
    scan: pl.LazyFrame | None = None,
    schema_names: list[str] | None = None,
    place_column: str | None = None,
) -> dict[str, Any]:
    return {
        "ticks_path": ticks_path,
        "scan": scan,
        "schema_names": schema_names or [],
        "place_column": place_column,
        "parse_ids": set(),
        "tick_count": 0,
        "source_ticks": 0,
        "place_non_null_rows": 0,
        "non_null_place_ticks": 0,
        "valid_place_rows": 0,
        "valid_named_place_ticks": 0,
        "blank_place_ticks": 0,
        "invalid_place_ticks": 0,
        "place_non_null_share": 0.0,
        "unique_places": 0,
        "demo_count": 0,
        "round_count": 0,
        "player_count": 0,
        "xyz_available": False,
        "critical_failures": True,
        "unknown_rows": unknown_rows,
    }


def prepare_tick_scan(scan: pl.LazyFrame, schema_names: list[str], place_column: str, *, parse_ids: set[str]) -> pl.LazyFrame:
    player_source = "steamid" if "steamid" in schema_names else ("name" if "name" in schema_names else None)
    side_source = next((column for column in SIDE_COLUMNS if column in schema_names), None)
    exprs = [
        pl.col("source_parse_id").cast(pl.Utf8),
        pl.col(place_column).cast(pl.Utf8).str.strip_chars().alias("raw_place"),
        pl.col("round_num").cast(pl.Utf8).alias("round_num") if "round_num" in schema_names else pl.lit(None).cast(pl.Utf8).alias("round_num"),
        pl.col("tick").cast(pl.Int64).alias("tick") if "tick" in schema_names else pl.lit(None).cast(pl.Int64).alias("tick"),
        pl.col(player_source).cast(pl.Utf8).alias("player_id") if player_source else pl.lit(None).cast(pl.Utf8).alias("player_id"),
        pl.col("steamid").cast(pl.Utf8).alias("steamid") if "steamid" in schema_names else pl.lit(None).cast(pl.Utf8).alias("steamid"),
        pl.col(side_source).cast(pl.Utf8).str.to_uppercase().alias("side_value") if side_source else pl.lit(None).cast(pl.Utf8).alias("side_value"),
        *[pl.col(axis).cast(pl.Float64).alias(axis) for axis in COORD_COLUMNS],
    ]
    return scan.filter(pl.col("source_parse_id").cast(pl.Utf8).is_in(list(parse_ids))).select(exprs)


def valid_place(scan: pl.LazyFrame) -> pl.LazyFrame:
    return scan.filter(pl.col("raw_place").is_not_null() & (pl.col("raw_place").str.strip_chars() != ""))


def valid_coordinates(scan: pl.LazyFrame) -> pl.LazyFrame:
    filters = [pl.col(axis).is_not_null() & ~pl.col(axis).is_nan() for axis in COORD_COLUMNS]
    return scan.filter(filters[0] & filters[1] & filters[2])


def build_place_inventory(scan: pl.LazyFrame, *, identity, target_team: str, total_ticks: int, min_observations: int) -> pd.DataFrame:
    grouped = (
        valid_place(scan)
        .group_by("raw_place")
        .agg(
            pl.len().alias("tick_count"),
            pl.col("source_parse_id").n_unique().alias("demo_count"),
            pl.struct(["source_parse_id", "round_num"]).n_unique().alias("round_count"),
            pl.col("player_id").filter(pl.col("player_id").is_not_null()).n_unique().alias("player_count"),
            pl.col("source_parse_id").min().alias("first_demo"),
            pl.col("source_parse_id").max().alias("last_demo"),
            pl.col("side_value").is_in(["T", "TERRORIST"]).any().alias("observed_on_t_side"),
            pl.col("side_value").is_in(["CT", "COUNTERTERRORIST", "COUNTER_TERRORIST"]).any().alias("observed_on_ct_side"),
        )
        .sort("tick_count", descending=True)
        .collect()
        .to_pandas()
    )
    if grouped.empty:
        return empty_frame(inventory_columns())
    grouped.insert(0, "target_team", target_team)
    grouped.insert(0, "map_name", identity.display_name)
    grouped.insert(0, "map_id", identity.map_id)
    grouped["normalized_place_id"] = grouped["raw_place"].map(normalize_place_id)
    grouped["tick_share"] = grouped["tick_count"] / total_ticks if total_ticks else 0.0
    grouped["status"] = grouped["tick_count"].map(lambda count: "ok" if int(count) >= min_observations else "rare")
    grouped["notes"] = grouped["status"].map(lambda status: None if status == "ok" else f"Below min_observations={min_observations}; retained for review.")
    return grouped[inventory_columns()]


def build_place_coordinates(scan: pl.LazyFrame, *, identity, target_team: str) -> pd.DataFrame:
    agg_exprs = [pl.len().alias("n_observations")]
    for axis in ["x", "y", "z"]:
        column = axis.upper()
        agg_exprs.extend(
            [
                pl.col(column).min().alias(f"{axis}_min"),
                pl.col(column).quantile(0.05, interpolation="linear").alias(f"{axis}_p05"),
                pl.col(column).quantile(0.25, interpolation="linear").alias(f"{axis}_p25"),
                pl.col(column).median().alias(f"{axis}_median"),
                pl.col(column).mean().alias(f"{axis}_mean"),
                pl.col(column).quantile(0.75, interpolation="linear").alias(f"{axis}_p75"),
                pl.col(column).quantile(0.95, interpolation="linear").alias(f"{axis}_p95"),
                pl.col(column).max().alias(f"{axis}_max"),
                pl.col(column).std().alias(f"{axis}_std"),
            ]
        )
    frame = valid_coordinates(valid_place(scan)).group_by("raw_place").agg(*agg_exprs).sort("raw_place").collect().to_pandas()
    if frame.empty:
        return empty_frame(coordinate_columns())
    frame.insert(0, "target_team", target_team)
    frame.insert(0, "map_name", identity.display_name)
    frame.insert(0, "map_id", identity.map_id)
    frame["normalized_place_id"] = frame["raw_place"].map(normalize_place_id)
    return frame[coordinate_columns()]


def build_place_by_demo(scan: pl.LazyFrame, *, identity, target_team: str) -> pd.DataFrame:
    valid = valid_place(scan)
    totals = valid.group_by("source_parse_id").agg(pl.len().alias("demo_tick_count"))
    grouped = (
        valid.group_by(["source_parse_id", "raw_place"])
        .agg(
            pl.len().alias("tick_count"),
            pl.struct(["source_parse_id", "round_num"]).n_unique().alias("round_count"),
            pl.col("player_id").filter(pl.col("player_id").is_not_null()).n_unique().alias("player_count"),
        )
        .join(totals, on="source_parse_id", how="left")
        .with_columns((pl.col("tick_count") / pl.col("demo_tick_count")).alias("tick_share_within_demo"), pl.lit(True).alias("observed"))
        .sort(["source_parse_id", "tick_count"], descending=[False, True])
        .collect()
        .to_pandas()
    )
    if grouped.empty:
        return empty_frame(by_demo_columns())
    grouped.insert(0, "target_team", target_team)
    grouped.insert(0, "map_name", identity.display_name)
    grouped.insert(0, "map_id", identity.map_id)
    return grouped[by_demo_columns()]


def build_place_coverage(
    inventory: pd.DataFrame,
    by_demo: pd.DataFrame,
    *,
    identity,
    target_team: str,
    context: dict[str, Any],
) -> pd.DataFrame:
    if inventory.empty:
        return empty_frame(coverage_columns())
    rows = []
    by_place = by_demo.groupby("raw_place", dropna=False) if not by_demo.empty else None
    total_demos = int(context["demo_count"])
    total_rounds = int(context["round_count"])
    total_players = int(context["player_count"])
    for _, row in inventory.iterrows():
        raw_place = row["raw_place"]
        demos_with_place = int(by_place.get_group(raw_place)["source_parse_id"].nunique()) if by_place is not None and raw_place in by_place.groups else 0
        demo_share = demos_with_place / total_demos if total_demos else 0.0
        round_share = int(row["round_count"]) / total_rounds if total_rounds else 0.0
        status = coverage_status(demo_share)
        rows.append(
            {
                "map_id": identity.map_id,
                "map_name": identity.display_name,
                "target_team": target_team,
                "raw_place": raw_place,
                "total_demos_in_scope": total_demos,
                "demos_with_place": demos_with_place,
                "demo_coverage_share": demo_share,
                "total_rounds_in_scope": total_rounds,
                "rounds_with_place": int(row["round_count"]),
                "round_coverage_share": round_share,
                "total_players_in_scope": total_players,
                "players_with_place": int(row["player_count"]),
                "tick_count": int(row["tick_count"]),
                "coverage_status": status,
                "notes": "Thresholds: common >= 80% demo coverage; moderate >= 40%; rare otherwise.",
            }
        )
    return pd.DataFrame(rows, columns=coverage_columns()).sort_values("tick_count", ascending=False).reset_index(drop=True)


def coverage_status(demo_coverage_share: float) -> str:
    if demo_coverage_share >= 0.8:
        return "common"
    if demo_coverage_share >= 0.4:
        return "moderate"
    return "rare"


def build_place_name_stability(scan: pl.LazyFrame, *, identity, target_team: str) -> pd.DataFrame:
    centers = (
        valid_coordinates(valid_place(scan))
        .group_by(["raw_place", "source_parse_id"])
        .agg(pl.col("X").mean().alias("demo_center_x"), pl.col("Y").mean().alias("demo_center_y"), pl.col("Z").mean().alias("demo_center_z"))
    )
    frame = (
        centers.group_by("raw_place")
        .agg(
            pl.col("source_parse_id").n_unique().alias("demo_count"),
            pl.col("demo_center_x").mean().alias("coordinate_center_x"),
            pl.col("demo_center_y").mean().alias("coordinate_center_y"),
            pl.col("demo_center_z").mean().alias("coordinate_center_z"),
            pl.col("demo_center_x").std().alias("between_demo_center_std_x"),
            pl.col("demo_center_y").std().alias("between_demo_center_std_y"),
            pl.col("demo_center_z").std().alias("between_demo_center_std_z"),
        )
        .sort("raw_place")
        .collect()
        .to_pandas()
    )
    if frame.empty:
        return empty_frame(stability_columns())
    frame.insert(0, "target_team", target_team)
    frame.insert(0, "map_name", identity.display_name)
    frame.insert(0, "map_id", identity.map_id)
    frame["coordinate_consistency_status"] = frame.apply(stability_status, axis=1)
    frame["notes"] = frame["coordinate_consistency_status"].map(stability_note)
    return frame[stability_columns()]


def stability_status(row: pd.Series) -> str:
    max_std = max(float(row.get(column) or 0) for column in ["between_demo_center_std_x", "between_demo_center_std_y", "between_demo_center_std_z"])
    if max_std >= 1000:
        return "review_required"
    if max_std >= 500:
        return "moderate_variation"
    return "stable"


def stability_note(status: str) -> str | None:
    if status == "review_required":
        return "Same raw place has high between-demo center variation; review before formal region mapping."
    if status == "moderate_variation":
        return "Same raw place has moderate between-demo center variation."
    return None


def build_vertical_profile(coordinates: pd.DataFrame, *, identity, target_team: str) -> pd.DataFrame:
    if coordinates.empty:
        return empty_frame(vertical_columns())
    frame = coordinates[["map_id", "map_name", "target_team", "raw_place", "z_min", "z_median", "z_max", "z_std"]].copy()
    frame["z_range"] = frame["z_max"] - frame["z_min"]
    frame["vertical_complexity_flag"] = (frame["z_range"].fillna(0) >= 500) | (frame["z_std"].fillna(0) >= 150)
    frame["notes"] = frame["vertical_complexity_flag"].map(lambda flag: "Large Z spread; review for vertical/multi-level behavior." if flag else None)
    frame["map_id"] = identity.map_id
    frame["map_name"] = identity.display_name
    frame["target_team"] = target_team
    return frame[vertical_columns()]


def build_coordinate_sample(scan: pl.LazyFrame, *, identity, target_team: str, sample_per_place: int) -> pd.DataFrame:
    columns = ["raw_place", "source_parse_id", "round_num", "tick", "steamid", "X", "Y", "Z"]
    frame = valid_coordinates(valid_place(scan)).select(columns).group_by("raw_place", maintain_order=True).head(sample_per_place).collect(engine="streaming").to_pandas()
    if frame.empty:
        return empty_frame(sample_columns())
    frame.insert(0, "target_team", target_team)
    frame.insert(0, "map_name", identity.display_name)
    frame.insert(0, "map_id", identity.map_id)
    return frame[sample_columns()]


def build_unknowns(scan: pl.LazyFrame, *, identity, target_team: str, context: dict[str, Any]) -> pd.DataFrame:
    rows = list(context["unknown_rows"])
    stats = scan.select(
        pl.col("raw_place").is_null().sum().alias("null_place"),
        (pl.col("raw_place").is_not_null() & (pl.col("raw_place").str.strip_chars() == "")).sum().alias("empty_place"),
        ((pl.col("X").is_null() | pl.col("Y").is_null() | pl.col("Z").is_null()) | (pl.col("X").is_nan() | pl.col("Y").is_nan() | pl.col("Z").is_nan())).sum().alias("invalid_coordinates"),
        ((pl.col("X").abs() > 100000) | (pl.col("Y").abs() > 100000) | (pl.col("Z").abs() > 100000)).sum().alias("extreme_coordinate_anomaly"),
    ).collect().row(0, named=True)
    if int(stats["null_place"]):
        rows.append(unknown(identity, target_team, "null_place", None, int(stats["null_place"]), "medium", False, "Place value is null.", "Keep rows out of region mapping until parser source is understood."))
    if int(stats["empty_place"]):
        rows.append(unknown(identity, target_team, "empty_place", "", int(stats["empty_place"]), "medium", False, "Place value is empty or whitespace-only.", "Review parser output; do not invent a correction."))
    if int(stats["invalid_coordinates"]):
        rows.append(unknown(identity, target_team, "invalid_coordinates", None, int(stats["invalid_coordinates"]), "medium", False, "At least one coordinate axis is null or NaN.", "Exclude these observations from coordinate profiles."))
    if int(stats["extreme_coordinate_anomaly"]):
        rows.append(unknown(identity, target_team, "extreme_coordinate_anomaly", None, int(stats["extreme_coordinate_anomaly"]), "low", False, "At least one coordinate is outside +/-100000.", "Review as possible parser anomaly before region mapping."))
    return pd.DataFrame(rows, columns=unknown_columns())


def build_mirage_crosswalk(inventory: pd.DataFrame, *, registry: MapRegistry, target_team: str) -> pd.DataFrame:
    if inventory.empty:
        return empty_frame(crosswalk_columns())
    lookup = registry_match_lookup(registry)
    rows = []
    for _, row in inventory.iterrows():
        normalized = str(row["normalized_place_id"])
        matches = lookup.get(normalized, [])
        region_ids = sorted({match["region_id"] for match in matches})
        ambiguous = len(region_ids) > 1
        matched = len(region_ids) == 1
        match_sources = sorted({match["match_source"] for match in matches}, key=match_source_rank)
        region = registry.physical_regions.get(region_ids[0]) if matched else None
        semantic_tags = "|".join(region.semantic_tags) if region else "|".join(sorted({tag for region_id in region_ids for tag in registry.physical_regions[region_id].semantic_tags}))
        rows.append(
            {
                "map_id": registry.map_id,
                "map_name": registry.display_name,
                "target_team": target_team,
                "raw_place": row["raw_place"],
                "normalized_place_id": normalized,
                "tick_count": int(row["tick_count"]),
                "matched_region_id": region.region_id if region else None,
                "matched_region_display_name": region.display_name if region else None,
                "match_source": match_sources[0] if match_sources else "none",
                "match_count": len(matches),
                "matched": matched,
                "ambiguous": ambiguous,
                "candidate_regions": "|".join(region_ids) if region_ids else None,
                "semantic_tags": semantic_tags or None,
                "status": "matched" if matched else ("review_required" if ambiguous else "unresolved"),
                "notes": None if matched else ("Multiple deterministic registry matches." if ambiguous else "No deterministic registry match."),
            }
        )
    return pd.DataFrame(rows, columns=crosswalk_columns()).sort_values("tick_count", ascending=False).reset_index(drop=True)


def registry_match_lookup(registry: MapRegistry) -> dict[str, list[dict[str, str]]]:
    lookup: dict[str, list[dict[str, str]]] = {}
    for region in registry.physical_regions.values():
        candidates = [
            ("region_id", region.region_id),
            ("display_name", region.display_name),
            *[("alias", value) for value in region.aliases],
            *[("alias", value) for value in registry.aliases.get(region.region_id, [])],
            *[("geometry_area_name", value) for value in region.geometry.get("area_names", [])],
            *[("geometry_area_name", value) for value in region.geometry.get("source_place_aliases", [])],
        ]
        for source, value in candidates:
            key = normalize_place_id(value)
            if not key:
                continue
            lookup.setdefault(key, []).append({"region_id": region.region_id, "match_source": source})
    return lookup


def match_source_rank(source: str) -> int:
    return {"region_id": 0, "display_name": 1, "alias": 2, "geometry_area_name": 3, "none": 99}.get(source, 50)


def build_mirage_validation(inventory: pd.DataFrame, crosswalk: pd.DataFrame, *, registry: MapRegistry, identity, target_team: str) -> pd.DataFrame:
    del identity
    observed_places = len(inventory)
    matched = crosswalk[crosswalk["matched"] == True] if not crosswalk.empty else pd.DataFrame()  # noqa: E712
    unmatched = crosswalk[crosswalk["matched"] != True] if not crosswalk.empty else pd.DataFrame()  # noqa: E712
    ambiguous = crosswalk[crosswalk["ambiguous"] == True] if not crosswalk.empty else pd.DataFrame()  # noqa: E712
    total_ticks = int(inventory["tick_count"].sum()) if not inventory.empty else 0
    matched_ticks = int(matched["tick_count"].sum()) if not matched.empty else 0
    observed_regions = set()
    if not matched.empty:
        observed_regions.update(matched["matched_region_id"].dropna().astype(str))
    registry_regions = set(registry.physical_regions)
    matched_share = matched_ticks / total_ticks if total_ticks else 0.0
    critical = 1 if observed_places and matched_share < 0.5 else 0
    return pd.DataFrame(
        [
            {
                "map_id": registry.map_id,
                "map_name": registry.display_name,
                "target_team": target_team,
                "observed_places": observed_places,
                "matched_places": len(matched),
                "unmatched_places": len(unmatched),
                "ambiguous_places": len(ambiguous),
                "matched_tick_share": matched_share,
                "unmatched_tick_share": 1 - matched_share if total_ticks else 0.0,
                "registry_regions": len(registry_regions),
                "registry_regions_observed": len(observed_regions),
                "registry_regions_not_observed": len(registry_regions - observed_regions),
                "critical_mismatch_count": critical,
                "status": "ok" if critical == 0 else "warning",
            }
        ]
    )


def build_inferno_discovery(inventory: pd.DataFrame, coordinates: pd.DataFrame, coverage: pd.DataFrame, *, identity, target_team: str) -> pd.DataFrame:
    del target_team
    if inventory.empty:
        return empty_frame(inferno_columns())
    frame = inventory.merge(coverage[["raw_place", "demo_coverage_share", "round_coverage_share", "coverage_status"]], on="raw_place", how="left")
    frame = frame.merge(coordinates[["raw_place", "x_median", "y_median", "z_median", "x_p05", "x_p95", "y_p05", "y_p95", "z_p05", "z_p95"]], on="raw_place", how="left")
    frame["map_id"] = identity.map_id
    frame["map_name"] = identity.display_name
    return frame[inferno_columns()].sort_values("tick_count", ascending=False).reset_index(drop=True)


def build_summary(*, identity, target_team: str, context: dict[str, Any], inventory: pd.DataFrame) -> pd.DataFrame:
    if inventory.empty:
        all_demo = multiple_demo = one_demo = 0
    else:
        demos = inventory["demo_count"].astype(int)
        total = int(context["demo_count"])
        all_demo = int((demos == total).sum()) if total else 0
        multiple_demo = int((demos > 1).sum())
        one_demo = int((demos == 1).sum())
    ready = bool(
        int(context["tick_count"]) > 0
        and context["place_column"]
        and int(context["place_non_null_rows"]) > 0
        and bool(context["xyz_available"])
        and int(context["unique_places"]) > 0
        and int(context["demo_count"]) > 0
        and not bool(context["critical_failures"])
    )
    return pd.DataFrame(
        [
            {
                "map_id": identity.map_id,
                "map_name": identity.display_name,
                "target_team": target_team,
                "demo_count": int(context["demo_count"]),
                "round_count": int(context["round_count"]),
                "tick_count": int(context["tick_count"]),
                "source_ticks": int(context["source_ticks"]),
                "place_column": context["place_column"],
                "place_non_null_rows": int(context["place_non_null_rows"]),
                "non_null_place_ticks": int(context["non_null_place_ticks"]),
                "valid_named_place_ticks": int(context["valid_named_place_ticks"]),
                "blank_place_ticks": int(context["blank_place_ticks"]),
                "invalid_place_ticks": int(context["invalid_place_ticks"]),
                "place_non_null_share": float(context["place_non_null_share"]),
                "unique_raw_places": int(context["unique_places"]),
                "places_seen_all_demos": all_demo,
                "places_seen_multiple_demos": multiple_demo,
                "places_seen_one_demo": one_demo,
                "xyz_available": bool(context["xyz_available"]),
                "discovery_status": "ok" if ready else "failed",
                "ready_for_region_mapping": ready,
                "created_at": now_utc(),
            }
        ]
    )


def build_audit(
    *,
    identity,
    target_team: str,
    context: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    registry_crosswalk_available: bool,
    registry_validation: pd.DataFrame,
) -> pd.DataFrame:
    unknowns = frames["map_area_discovery_unknowns"]
    critical_unknowns = unknowns[unknowns["blocking"] == True] if not unknowns.empty else pd.DataFrame()  # noqa: E712
    crosswalk = frames["mirage_place_registry_crosswalk"]
    matched_places = int((crosswalk["matched"] == True).sum()) if not crosswalk.empty and "matched" in crosswalk.columns else 0  # noqa: E712
    unmatched_places = int((crosswalk["matched"] != True).sum()) if not crosswalk.empty and "matched" in crosswalk.columns else 0  # noqa: E712
    matched_share = float(registry_validation.iloc[0]["matched_tick_share"]) if not registry_validation.empty and "matched_tick_share" in registry_validation.columns else 0.0
    summary = frames["map_area_discovery_summary"].iloc[0] if not frames["map_area_discovery_summary"].empty else {}
    ready = bool(summary.get("ready_for_region_mapping", False))
    status = "failed" if len(critical_unknowns) else ("ok" if ready else "warning")
    return pd.DataFrame(
        [
            {
                "audit_id": f"map_area_discovery_{identity.map_id}_{normalize_id(target_team)}",
                "map_id": identity.map_id,
                "map_name": identity.display_name,
                "target_team": target_team,
                "source_demos": int(context["demo_count"]),
                "source_rounds": int(context["round_count"]),
                "source_ticks": int(context["tick_count"]),
                "place_column": context["place_column"],
                "place_non_null_rows": int(context["place_non_null_rows"]),
                "non_null_place_ticks": int(context["non_null_place_ticks"]),
                "valid_named_place_ticks": int(context["valid_named_place_ticks"]),
                "blank_place_ticks": int(context["blank_place_ticks"]),
                "invalid_place_ticks": int(context["invalid_place_ticks"]),
                "place_non_null_share": float(context["place_non_null_share"]),
                "unique_places": int(context["unique_places"]),
                "coordinate_profiles_generated": len(frames["map_place_coordinates"]),
                "coverage_profiles_generated": len(frames["map_place_coverage"]),
                "stability_profiles_generated": len(frames["map_place_name_stability"]),
                "unknown_count": len(unknowns),
                "critical_unknown_count": len(critical_unknowns),
                "registry_crosswalk_available": registry_crosswalk_available,
                "registry_matched_places": matched_places,
                "registry_unmatched_places": unmatched_places,
                "registry_matched_tick_share": matched_share,
                "ready_for_region_mapping": ready,
                "status": status,
                "created_at": now_utc(),
            }
        ]
    )


def parse_ids_for_scope(parse_manifest: pd.DataFrame, *, target_map: str, target_team: str, registry_path: Path) -> set[str]:
    if parse_manifest.empty or "parse_id" not in parse_manifest.columns:
        return set()
    scoped = parse_manifest.copy()
    if "target_team" in scoped.columns:
        scoped = scoped[scoped["target_team"].astype(str).str.lower() == target_team.lower()]
    if "map_name" in scoped.columns:
        scoped = scoped[scoped["map_name"].map(lambda value: same_map(value, target_map, registry_path=registry_path))]
    if "parse_status" in scoped.columns:
        scoped = scoped[scoped["parse_status"].astype(str).isin(["parsed", "skipped_existing"])]
    return set(scoped["parse_id"].dropna().astype(str))


def load_registry_if_available(map_name: str, *, registry_path: Path) -> tuple[MapRegistry | None, bool]:
    try:
        return load_map_registry(map_name, registry_path=registry_path), True
    except Exception:
        return None, False


def normalize_place_id(value: object) -> str:
    return normalize_id(str(value or ""))


def unknown(identity, target_team: str, unknown_type: str, raw_place: object, count: int, severity: str, blocking: bool, reason: str, action: str) -> dict[str, object]:
    return {
        "map_id": identity.map_id,
        "map_name": identity.display_name,
        "target_team": target_team,
        "unknown_type": unknown_type,
        "raw_place": raw_place,
        "observation_count": count,
        "severity": severity,
        "blocking": blocking,
        "reason": reason,
        "recommended_action": action,
    }


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, identity, target_team: str, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        new_frame = sanitize_for_parquet(frames[name])
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if path.exists() and not force:
                outputs[f"{name}_{suffix}"] = path
                continue
            final = upsert_scope(path, new_frame, map_id=identity.map_id, target_team=target_team)
            final.to_csv(path, index=False) if suffix == "csv" else final.to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def upsert_scope(path: Path, new_frame: pd.DataFrame, *, map_id: str, target_team: str) -> pd.DataFrame:
    existing = read_optional(path) if path.exists() else pd.DataFrame(columns=new_frame.columns)
    if existing.empty:
        return new_frame.reset_index(drop=True)
    if "map_id" not in existing.columns or "target_team" not in existing.columns:
        return new_frame.reset_index(drop=True)
    other = existing[~((existing["map_id"].astype(str) == map_id) & (existing["target_team"].astype(str).str.lower() == target_team.lower()))].copy()
    if other.empty:
        return new_frame.reset_index(drop=True)
    if new_frame.empty:
        return other.reset_index(drop=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        combined = pd.concat([other, new_frame], ignore_index=True)
    return combined.reindex(columns=list(dict.fromkeys([*existing.columns, *new_frame.columns])))


def load_persisted_frames(output_dir: Path, *, fallback: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    frames = {}
    for name in OUTPUT_NAMES:
        path = output_dir / f"{name}.parquet"
        frames[name] = read_optional(path) if path.exists() else fallback[name]
    return frames


def read_optional(path: Path) -> pd.DataFrame:
    base_path = path.with_suffix("")
    try:
        return read_table_pair(base_path)
    except FileNotFoundError:
        return pd.DataFrame()


def sanitize_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].map(lambda value: "|".join(value) if isinstance(value, list) else value)
    return result


def build_report(frames: dict[str, pd.DataFrame]) -> str:
    summary = frames["map_area_discovery_summary"]
    audit = frames["map_area_discovery_audit"]
    coverage = frames["map_place_coverage"]
    coordinates = frames["map_place_coordinates"]
    stability = frames["map_place_name_stability"]
    vertical = frames["map_place_vertical_profile"]
    unknowns = frames["map_area_discovery_unknowns"]
    crosswalk = frames["mirage_place_registry_crosswalk"]
    validation = frames["mirage_area_discovery_validation"]
    inferno = frames["inferno_place_discovery"]
    return "\n".join(
        [
            "# Generic Map Area Discovery",
            "",
            "## Purpose",
            "Stage 8.6 discovers real parser-reported map places and coordinate evidence for already parsed maps.",
            "",
            "## Input Data",
            "`data/silver/parsed_demos/ticks.parquet` is scanned by scoped `source_parse_id`; the stage avoids loading full tick tables into pandas.",
            "",
            "## Canonical Map Scope",
            "Map scope is resolved through `src.maps.identity`, so aliases such as `Inferno`, `inferno`, and `de_inferno` point to the same canonical map id.",
            "",
            "## Place Column",
            f"Supported place columns, in order: `{', '.join(PLACE_COLUMN_CANDIDATES)}`.",
            "",
            "## Discovery Method",
            "The stage aggregates raw place names, coordinate percentiles, demo/round/player coverage, name stability, vertical spread, and deterministic coordinate samples. It does not infer tactical semantic groups.",
            "",
            "## Mirage Results",
            markdown_table(summary[summary["map_id"].eq("mirage")], list(summary.columns)),
            "",
            "## Mirage Registry Crosswalk",
            markdown_table(crosswalk, list(crosswalk.columns), top_n=40),
            "",
            "## Inferno Results",
            markdown_table(summary[summary["map_id"].eq("inferno")], list(summary.columns)),
            "",
            "## Coordinate Profiles",
            markdown_table(coordinates, ["map_id", "raw_place", "n_observations", "x_p05", "x_median", "x_p95", "y_p05", "y_median", "y_p95", "z_p05", "z_median", "z_p95"], top_n=40),
            "",
            "## Demo Coverage",
            markdown_table(coverage, ["map_id", "raw_place", "demos_with_place", "demo_coverage_share", "rounds_with_place", "round_coverage_share", "coverage_status"], top_n=50),
            "",
            "## Place Stability",
            markdown_table(stability, list(stability.columns), top_n=50),
            "",
            "## Vertical Profiles",
            markdown_table(vertical, list(vertical.columns), top_n=50),
            "",
            "## Unknowns",
            markdown_table(unknowns, list(unknowns.columns), top_n=50),
            "",
            "## Limitations",
            "No callouts, bounding boxes, semantic groups, or Inferno registry entries are invented here. Mirage registry differences are reported, not corrected.",
            "",
            "## Readiness",
            markdown_table(audit, list(audit.columns)),
            "",
            "## Next Stage",
            "Stage 8.7 should use these raw-place outputs to review and formalize Inferno physical regions and tactical semantic groups.",
            "",
            "## Inferno Place Discovery",
            markdown_table(inferno, ["raw_place", "tick_count", "demo_count", "round_count", "demo_coverage_share", "coverage_status", "x_median", "y_median", "z_median"], top_n=50),
            "",
            "## Mirage Discovery Validation",
            markdown_table(validation, list(validation.columns)),
            "",
        ]
    )


def build_notebook_json() -> str:
    cells = [
        md("# Stage 8.6 -- Generic Map Area Discovery"),
        code(
            "from pathlib import Path\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n\n"
            "BASE = Path('../data/gold/maps/area_discovery')\n"
            "MAP_ID = 'inferno'\n\n"
            "def load(name):\n"
            "    return pd.read_parquet(BASE / f'{name}.parquet')\n\n"
            "summary = load('map_area_discovery_summary')\n"
            "inventory = load('map_place_inventory')\n"
            "coverage = load('map_place_coverage')\n"
            "coordinates = load('map_place_coordinates')\n"
            "sample = load('map_place_coordinate_sample')\n"
            "stability = load('map_place_name_stability')\n"
            "vertical = load('map_place_vertical_profile')\n"
            "unknowns = load('map_area_discovery_unknowns')\n"
            "crosswalk = load('mirage_place_registry_crosswalk')\n"
            "audit = load('map_area_discovery_audit')\n\n"
            "def scoped(df):\n"
            "    return df[df['map_id'].eq(MAP_ID)].copy() if 'map_id' in df.columns else df.iloc[0:0].copy()"
        ),
        md("## Discovery Summary"),
        code("display(scoped(summary))"),
        md("## Place Frequency"),
        code(
            "freq = scoped(inventory).sort_values('tick_count', ascending=False)\n"
            "display(freq)\n"
            "ax = freq.head(25).plot.bar(x='raw_place', y='tick_count', figsize=(12, 4), legend=False)\n"
            "ax.set_ylabel('ticks')\n"
            "plt.xticks(rotation=60, ha='right')\n"
            "plt.tight_layout()"
        ),
        md("## Demo Coverage"),
        code(
            "cov = scoped(coverage).sort_values('demo_coverage_share', ascending=False)\n"
            "display(cov)\n"
            "ax = cov.plot.bar(x='raw_place', y='demo_coverage_share', figsize=(12, 4), legend=False)\n"
            "ax.set_ylim(0, 1.05)\n"
            "plt.xticks(rotation=60, ha='right')\n"
            "plt.tight_layout()"
        ),
        md("## Round Coverage"),
        code("display(cov[['raw_place', 'rounds_with_place', 'round_coverage_share', 'coverage_status']])"),
        md("## Coordinate Profile"),
        code("display(scoped(coordinates))"),
        md("## X/Y Coordinate Scatter"),
        code(
            "pts = scoped(sample)\n"
            "fig, ax = plt.subplots(figsize=(7, 7))\n"
            "for place, group in pts.groupby('raw_place'):\n"
            "    ax.scatter(group['X'], group['Y'], s=4, alpha=0.25)\n"
            "centers = scoped(coordinates)\n"
            "for _, row in centers.iterrows():\n"
            "    ax.text(row['x_median'], row['y_median'], row['raw_place'], fontsize=8)\n"
            "ax.set_xlabel('X')\n"
            "ax.set_ylabel('Y')\n"
            "ax.set_aspect('equal', adjustable='box')\n"
            "plt.tight_layout()"
        ),
        md("## Median X/Y by Place"),
        code(
            "centers = scoped(coordinates)\n"
            "fig, ax = plt.subplots(figsize=(7, 7))\n"
            "ax.scatter(centers['x_median'], centers['y_median'])\n"
            "for _, row in centers.iterrows():\n"
            "    ax.text(row['x_median'], row['y_median'], row['raw_place'], fontsize=8)\n"
            "ax.set_xlabel('median X')\n"
            "ax.set_ylabel('median Y')\n"
            "ax.set_aspect('equal', adjustable='box')"
        ),
        md("## Z Profile"),
        code(
            "z = scoped(vertical).sort_values('z_range', ascending=False)\n"
            "display(z)\n"
            "ax = z.plot.bar(x='raw_place', y='z_range', figsize=(12, 4), legend=False)\n"
            "ax.set_ylabel('Z range')\n"
            "plt.xticks(rotation=60, ha='right')\n"
            "plt.tight_layout()"
        ),
        md("## Place Stability"),
        code("display(scoped(stability))"),
        md("## Unknowns"),
        code("display(scoped(unknowns))"),
        md("## Mirage Registry Crosswalk"),
        code("display(scoped(crosswalk) if MAP_ID == 'mirage' else 'Crosswalk is only available for Mirage in this stage.')"),
        md("## Final Readiness"),
        code("display(scoped(audit))"),
    ]
    return notebook_json(cells) + "\n"


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    return report_markdown_table(frame, columns, top_n=top_n)


def build_empty_frames(*, identity, target_team: str) -> dict[str, pd.DataFrame]:
    del identity, target_team
    return {
        "map_area_discovery_summary": empty_frame(summary_columns()),
        "map_place_inventory": empty_frame(inventory_columns()),
        "map_place_coordinates": empty_frame(coordinate_columns()),
        "map_place_by_demo": empty_frame(by_demo_columns()),
        "map_place_coverage": empty_frame(coverage_columns()),
        "map_place_name_stability": empty_frame(stability_columns()),
        "map_place_vertical_profile": empty_frame(vertical_columns()),
        "map_place_coordinate_sample": empty_frame(sample_columns()),
        "map_area_discovery_unknowns": empty_frame(unknown_columns()),
        "mirage_place_registry_crosswalk": empty_frame(crosswalk_columns()),
        "mirage_area_discovery_validation": empty_frame(validation_columns()),
        "inferno_place_discovery": empty_frame(inferno_columns()),
        "map_area_discovery_audit": empty_frame(audit_columns()),
    }


def empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def summary_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "demo_count", "round_count", "tick_count", "source_ticks", "place_column", "place_non_null_rows", "non_null_place_ticks", "valid_named_place_ticks", "blank_place_ticks", "invalid_place_ticks", "place_non_null_share", "unique_raw_places", "places_seen_all_demos", "places_seen_multiple_demos", "places_seen_one_demo", "xyz_available", "discovery_status", "ready_for_region_mapping", "created_at"]


def inventory_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "raw_place", "normalized_place_id", "tick_count", "tick_share", "demo_count", "round_count", "player_count", "first_demo", "last_demo", "observed_on_t_side", "observed_on_ct_side", "status", "notes"]


def coordinate_columns() -> list[str]:
    axis_columns = []
    for axis in ["x", "y", "z"]:
        axis_columns.extend([f"{axis}_min", f"{axis}_p05", f"{axis}_p25", f"{axis}_median", f"{axis}_mean", f"{axis}_p75", f"{axis}_p95", f"{axis}_max", f"{axis}_std"])
    return ["map_id", "map_name", "target_team", "raw_place", "normalized_place_id", "n_observations", *axis_columns]


def by_demo_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "source_parse_id", "raw_place", "tick_count", "tick_share_within_demo", "round_count", "player_count", "observed"]


def coverage_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "raw_place", "total_demos_in_scope", "demos_with_place", "demo_coverage_share", "total_rounds_in_scope", "rounds_with_place", "round_coverage_share", "total_players_in_scope", "players_with_place", "tick_count", "coverage_status", "notes"]


def stability_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "raw_place", "demo_count", "coordinate_center_x", "coordinate_center_y", "coordinate_center_z", "between_demo_center_std_x", "between_demo_center_std_y", "between_demo_center_std_z", "coordinate_consistency_status", "notes"]


def vertical_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "raw_place", "z_min", "z_median", "z_max", "z_range", "z_std", "vertical_complexity_flag", "notes"]


def sample_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "raw_place", "source_parse_id", "round_num", "tick", "steamid", "X", "Y", "Z"]


def unknown_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "unknown_type", "raw_place", "observation_count", "severity", "blocking", "reason", "recommended_action"]


def crosswalk_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "raw_place", "normalized_place_id", "tick_count", "matched_region_id", "matched_region_display_name", "match_source", "match_count", "matched", "ambiguous", "candidate_regions", "semantic_tags", "status", "notes"]


def validation_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "observed_places", "matched_places", "unmatched_places", "ambiguous_places", "matched_tick_share", "unmatched_tick_share", "registry_regions", "registry_regions_observed", "registry_regions_not_observed", "critical_mismatch_count", "status"]


def inferno_columns() -> list[str]:
    return ["map_id", "map_name", "target_team", "raw_place", "normalized_place_id", "tick_count", "demo_count", "round_count", "player_count", "demo_coverage_share", "round_coverage_share", "coverage_status", "x_median", "y_median", "z_median", "x_p05", "x_p95", "y_p05", "y_p95", "z_p05", "z_p95"]


def audit_columns() -> list[str]:
    return ["audit_id", "map_id", "map_name", "target_team", "source_demos", "source_rounds", "source_ticks", "place_column", "place_non_null_rows", "non_null_place_ticks", "valid_named_place_ticks", "blank_place_ticks", "invalid_place_ticks", "place_non_null_share", "unique_places", "coordinate_profiles_generated", "coverage_profiles_generated", "stability_profiles_generated", "unknown_count", "critical_unknown_count", "registry_crosswalk_available", "registry_matched_places", "registry_unmatched_places", "registry_matched_tick_share", "ready_for_region_mapping", "status", "created_at"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover parser-reported map places and coordinate evidence for a scoped map/team.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-observations", type=int, default=1)
    return parser.parse_args()


def print_summary(outputs: dict[str, Path], summary: dict[str, object]) -> None:
    print("Map area discovery summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_area_discovery(
        args.config,
        map_name=args.map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
        min_observations=args.min_observations,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
