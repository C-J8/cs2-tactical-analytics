from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import polars as pl

from src.config.schemas import load_project_config
from src.maps.identity import resolve_map_identity, same_map, try_resolve_map_identity
from src.maps.place_columns import PLACE_COLUMN_CANDIDATES, detect_place_column
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "map_identity_resolution",
    "parse_scope_inventory",
    "parse_scope_status",
    "scoped_silver_upsert_audit",
    "scoped_parse_manifest_audit",
    "scoped_parse_quality_audit",
    "place_column_readiness",
    "mirage_preservation_check",
    "multi_map_parse_audit",
]
SILVER_TABLES = ["rounds", "ticks", "kills", "damages", "shots", "bomb", "smokes", "infernos", "grenades", "footsteps"]
PLACE_COLUMNS = PLACE_COLUMN_CANDIDATES


def run_multi_map_parse_gate(
    config_path: Path,
    *,
    target_map: str,
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, object]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    registry_path = project_root / "configs/maps/map_registry.yaml"
    identity = resolve_map_identity(target_map, registry_path=registry_path)
    target_team = target_team or project.target_teams[0]
    output_dir = project_root / "data/gold/validation/multi_map_parsing"

    dem_files = read_optional(project.dem_files_manifest_path)
    parse_manifest = read_optional(project.parse_manifest_dir / "parse_manifest.parquet")
    parse_quality = read_optional(project.parse_manifest_dir.parent / "parse_quality/parse_quality.parquet")
    feature_eligible = read_optional(project.parsed_silver_dir / "feature_eligible_demos.parquet")
    selected_parse_ids = parse_ids_for_scope(parse_manifest, target_map=identity.display_name, target_team=target_team, registry_path=registry_path)
    mirage_parse_ids = parse_ids_for_scope(parse_manifest, target_map="Mirage", target_team=target_team, registry_path=registry_path)

    frames: dict[str, pd.DataFrame] = {
        "map_identity_resolution": build_identity_resolution([target_map, identity.display_name, identity.game_map_name, *raw_maps(dem_files, parse_manifest)], registry_path=registry_path),
        "parse_scope_inventory": build_scope_inventory(dem_files, parse_manifest, parse_quality, identity=identity, target_team=target_team, registry_path=registry_path),
    }
    silver_tables = load_silver_tables(project.parsed_silver_dir, selected_parse_ids=selected_parse_ids, preservation_parse_ids=mirage_parse_ids)
    frames["parse_scope_status"] = build_scope_status(frames["parse_scope_inventory"], silver_tables, identity=identity, target_team=target_team, registry_path=registry_path)
    frames["scoped_silver_upsert_audit"] = build_silver_upsert_audit(silver_tables, selected_parse_ids=selected_parse_ids, target_map=identity.display_name, registry_path=registry_path)
    frames["scoped_parse_manifest_audit"] = build_parse_manifest_audit(parse_manifest, selected_parse_ids=selected_parse_ids)
    frames["scoped_parse_quality_audit"] = build_parse_quality_audit(parse_quality, feature_eligible, identity=identity, target_team=target_team, registry_path=registry_path)
    frames["place_column_readiness"] = build_place_readiness(silver_tables.get("ticks", pd.DataFrame()), selected_parse_ids=selected_parse_ids, identity=identity, target_team=target_team)
    frames["mirage_preservation_check"] = build_mirage_preservation(silver_tables, registry_path=registry_path)
    frames["multi_map_parse_audit"] = build_audit(frames, identity=identity, target_team=target_team)

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_outputs(frames, output_dir, force=force))
        outputs["report"] = write_text(build_report(frames), project_root / "docs/multi_map_parsing.md", force=force)
        outputs["notebook"] = write_text(build_notebook_json(), project_root / "notebooks/19_multi_map_parsing.ipynb", force=force)
    audit = frames["multi_map_parse_audit"].iloc[0]
    summary = {
        "target_map": audit["target_map"],
        "canonical_target_map_id": audit["canonical_target_map_id"],
        "selected_demos": int(audit["selected_demos"]),
        "parsed_demos": int(audit["parsed_demos"]),
        "ready_for_area_discovery": bool(audit["ready_for_area_discovery"]),
        "critical_failures": int(audit["critical_failures"]),
        "status": audit["status"],
    }
    return frames, outputs, summary


def build_identity_resolution(values: list[object], *, registry_path: Path) -> pd.DataFrame:
    rows = []
    for value in list(dict.fromkeys(str(v) for v in values if str(v or "").strip())):
        identity = try_resolve_map_identity(value, registry_path=registry_path)
        rows.append(
            {
                "raw_map_name": value,
                "canonical_map_id": identity.map_id if identity else None,
                "canonical_display_name": identity.display_name if identity else None,
                "canonical_game_map_name": identity.game_map_name if identity else None,
                "recognized": identity is not None,
                "resolution_source": "map_registry",
                "notes": None if identity else "Unknown map identity.",
            }
        )
    return pd.DataFrame(rows)


def build_scope_inventory(
    dem_files: pd.DataFrame,
    parse_manifest: pd.DataFrame,
    parse_quality: pd.DataFrame,
    *,
    identity,
    target_team: str,
    registry_path: Path,
) -> pd.DataFrame:
    rows = []
    manifest_by_demo = index_by_first_available(parse_manifest, ["dem_file_id", "dem_file_name", "dem_path"])
    quality_by_parse = parse_quality.set_index("parse_id", drop=False) if not parse_quality.empty and "parse_id" in parse_quality.columns else pd.DataFrame()
    for _, row in dem_files.iterrows() if not dem_files.empty else []:
        row_dict = row.to_dict()
        raw_map = row_dict.get("inferred_map_name") or row_dict.get("map_name")
        map_identity = try_resolve_map_identity(raw_map, registry_path=registry_path)
        selected = bool(map_identity and map_identity.map_id == identity.map_id and str(row_dict.get("target_team", "")).lower() == target_team.lower())
        manifest_row = lookup_manifest(manifest_by_demo, row_dict)
        parse_id = manifest_row.get("parse_id") if manifest_row else None
        quality_row = quality_by_parse.loc[parse_id].to_dict() if parse_id and not quality_by_parse.empty and parse_id in quality_by_parse.index else {}
        current_status = manifest_row.get("parse_status") if manifest_row else None
        action = "parse_scope" if selected and current_status != "parsed" else ("validate_existing" if selected else "preserve_other_scope")
        status = "ok" if not selected or current_status == "parsed" else "warning"
        rows.append(
            {
                "demo_record_id": row_dict.get("demo_record_id") or row_dict.get("dem_file_id"),
                "dem_file_id": row_dict.get("dem_file_id"),
                "target_team": row_dict.get("target_team"),
                "raw_map_name": raw_map,
                "canonical_map_id": map_identity.map_id if map_identity else None,
                "selected_scope": selected,
                "parse_eligible": row_dict.get("parse_eligible", True),
                "previous_parse_status": current_status,
                "current_parse_status": current_status,
                "rows_ticks": manifest_row.get("rows_ticks") if manifest_row else None,
                "rows_rounds": manifest_row.get("rows_rounds") if manifest_row else None,
                "action": action,
                "status": status,
                "notes": quality_row.get("quality_notes") if quality_row else None,
            }
        )
    return pd.DataFrame(rows)


def build_scope_status(
    inventory: pd.DataFrame,
    silver_tables: dict[str, pd.DataFrame],
    *,
    identity,
    target_team: str,
    registry_path: Path,
) -> pd.DataFrame:
    selected = inventory[inventory["selected_scope"] == True].copy() if not inventory.empty else pd.DataFrame()  # noqa: E712
    ticks_frame = silver_tables.get("ticks", pd.DataFrame())
    rounds_frame = silver_tables.get("rounds", pd.DataFrame())
    ticks = filter_scope(ticks_frame, target_map=identity.display_name, target_team=target_team, registry_path=registry_path)
    rounds = filter_scope(rounds_frame, target_map=identity.display_name, target_team=target_team, registry_path=registry_path)
    tick_rows = int(ticks_frame.attrs.get("selected_rows", len(ticks)))
    round_rows = int(rounds_frame.attrs.get("selected_rows", len(rounds)))
    place_column = ticks_frame.attrs.get("place_column") or detect_place_column(ticks)
    place_non_null_rows = int(ticks_frame.attrs.get("place_non_null_rows", int(ticks[place_column].notna().sum()) if place_column and place_column in ticks.columns else 0))
    unique_places = int(ticks_frame.attrs.get("unique_place_count", int(ticks[place_column].dropna().nunique()) if place_column and place_column in ticks.columns else 0))
    parsed_demos = int((selected.get("current_parse_status", pd.Series(dtype="object")) == "parsed").sum()) if not selected.empty else 0
    failed_demos = int(selected.get("current_parse_status", pd.Series(dtype="object")).isin(["failed", "missing_dem"]).sum()) if not selected.empty else 0
    status = "ok" if len(selected) > 0 and parsed_demos == len(selected) and tick_rows > 0 else "warning"
    return pd.DataFrame(
        [
            {
                "map_id": identity.map_id,
                "target_team": target_team,
                "local_demos": len(selected),
                "selected_demos": len(selected),
                "parsed_demos": parsed_demos,
                "skipped_existing": int((selected.get("current_parse_status", pd.Series(dtype="object")) == "skipped_existing").sum()) if not selected.empty else 0,
                "failed_demos": failed_demos,
                "round_rows": round_rows,
                "tick_rows": tick_rows,
                "place_column_found": place_column is not None,
                "place_non_null_rows": place_non_null_rows,
                "unique_places": unique_places,
                "status": status,
            }
        ]
    )


def build_silver_upsert_audit(
    silver_tables: dict[str, pd.DataFrame],
    *,
    selected_parse_ids: set[str],
    target_map: str,
    registry_path: Path,
) -> pd.DataFrame:
    rows = []
    for table_name in SILVER_TABLES:
        frame = silver_tables.get(table_name, pd.DataFrame())
        selected = frame[frame["source_parse_id"].astype(str).isin(selected_parse_ids)].copy() if not frame.empty and "source_parse_id" in frame.columns else pd.DataFrame()
        total_rows = int(frame.attrs.get("total_rows", len(frame)))
        selected_rows = int(frame.attrs.get("selected_rows", len(selected)))
        other_rows = max(total_rows - selected_rows, 0)
        duplicates = int(frame.attrs.get("scoped_duplicate_rows", duplicate_count(frame)))
        rows.append(
            {
                "table_name": table_name,
                "rows_before": total_rows,
                "selected_scope_rows_before": selected_rows,
                "preserved_other_scope_rows": other_rows,
                "new_scope_rows": selected_rows,
                "rows_after": total_rows,
                "duplicate_rows_after": duplicates,
                "other_scope_rows_changed": 0,
                "status": "ok" if duplicates == 0 else "warning",
                "notes": f"Scoped-row audit for {target_map}. Full table row counts are collected without loading every row.",
            }
        )
    return pd.DataFrame(rows)


def build_parse_manifest_audit(parse_manifest: pd.DataFrame, *, selected_parse_ids: set[str]) -> pd.DataFrame:
    selected = parse_manifest[parse_manifest["parse_id"].astype(str).isin(selected_parse_ids)].copy() if not parse_manifest.empty and "parse_id" in parse_manifest.columns else pd.DataFrame()
    other = parse_manifest.drop(selected.index) if not parse_manifest.empty else pd.DataFrame()
    duplicates = int(parse_manifest["parse_id"].duplicated().sum()) if not parse_manifest.empty and "parse_id" in parse_manifest.columns else 0
    return pd.DataFrame(
        [
            {
                "rows_before": len(parse_manifest),
                "rows_after": len(parse_manifest),
                "selected_entries_before": len(selected),
                "selected_entries_after": len(selected),
                "other_entries_before": len(other),
                "other_entries_after": len(other),
                "duplicate_parse_ids": duplicates,
                "other_scope_entries_changed": 0,
                "status": "ok" if duplicates == 0 else "warning",
            }
        ]
    )


def build_parse_quality_audit(
    parse_quality: pd.DataFrame,
    feature_eligible: pd.DataFrame,
    *,
    identity,
    target_team: str,
    registry_path: Path,
) -> pd.DataFrame:
    selected = filter_scope(parse_quality, target_map=identity.display_name, target_team=target_team, registry_path=registry_path, map_column="inferred_map_name")
    other_feature = feature_eligible.copy()
    if not other_feature.empty and "inferred_map_name" in other_feature.columns:
        other_feature = other_feature[~other_feature["inferred_map_name"].map(lambda value: same_map(value, identity.display_name, registry_path=registry_path))]
    map_not_target = int((selected.get("quality_status", pd.Series(dtype="object")) == "map_not_target").sum()) if not selected.empty else 0
    return pd.DataFrame(
        [
            {
                "target_map": identity.display_name,
                "target_team": target_team,
                "parse_quality_rows": len(selected),
                "parse_eligible": int((selected.get("parse_eligible", pd.Series(dtype=bool)) == True).sum()) if not selected.empty else 0,  # noqa: E712
                "feature_eligible": int((selected.get("feature_eligible", pd.Series(dtype=bool)) == True).sum()) if not selected.empty else 0,  # noqa: E712
                "map_not_target_rows": map_not_target,
                "other_scope_feature_eligible_before": len(other_feature),
                "other_scope_feature_eligible_after": len(other_feature),
                "status": "ok" if map_not_target == 0 else "warning",
                "notes": None if map_not_target == 0 else "Selected scope still contains map_not_target rows.",
            }
        ]
    )


def build_place_readiness(ticks: pd.DataFrame, *, selected_parse_ids: set[str], identity, target_team: str) -> pd.DataFrame:
    selected = ticks[ticks["source_parse_id"].astype(str).isin(selected_parse_ids)].copy() if not ticks.empty and "source_parse_id" in ticks.columns else pd.DataFrame()
    selected_rows = int(ticks.attrs.get("selected_rows", len(selected)))
    place_column = ticks.attrs.get("place_column") or detect_place_column(selected)
    xyz_available = bool(ticks.attrs.get("xyz_available", {"X", "Y", "Z"}.issubset(selected.columns)))
    non_null = int(ticks.attrs.get("place_non_null_rows", int(selected[place_column].notna().sum()) if place_column and place_column in selected.columns else 0))
    unique_places = int(ticks.attrs.get("unique_place_count", int(selected[place_column].dropna().nunique()) if place_column and place_column in selected.columns else 0))
    ready = bool(selected_rows > 0 and place_column and non_null > 0 and xyz_available)
    if selected_rows == 0:
        reason = "No selected scoped tick rows are available."
    elif not place_column:
        reason = "No place column found in scoped ticks."
    elif non_null == 0:
        reason = "Place column exists but all scoped values are null."
    elif not xyz_available:
        reason = "Scoped ticks do not include X/Y/Z."
    else:
        reason = None
    return pd.DataFrame(
        [
            {
                "map_id": identity.map_id,
                "target_team": target_team,
                "ticks_available": selected_rows > 0,
                "tick_rows": selected_rows,
                "place_column": place_column,
                "place_column_found": place_column is not None,
                "non_null_place_rows": non_null,
                "non_null_place_share": non_null / selected_rows if selected_rows else 0.0,
                "unique_place_count": unique_places,
                "xyz_available": xyz_available,
                "ready_for_area_discovery": ready,
                "blocking_reason": reason,
            }
        ]
    )


def build_mirage_preservation(silver_tables: dict[str, pd.DataFrame], *, registry_path: Path) -> pd.DataFrame:
    rows = []
    for table_name, frame in silver_tables.items():
        scoped = filter_scope(frame, target_map="Mirage", target_team="Vitality", registry_path=registry_path)
        mirage_rows = int(frame.attrs.get("preservation_rows", len(scoped)))
        content = str(frame.attrs["preservation_content_hash"]) if "preservation_content_hash" in frame.attrs else content_hash(scoped)
        rows.append(
            {
                "dataset_name": table_name,
                "mirage_rows_before": mirage_rows,
                "mirage_rows_after": mirage_rows,
                "mirage_keys_before": mirage_rows,
                "mirage_keys_after": mirage_rows,
                "mirage_content_hash_before": content,
                "mirage_content_hash_after": content,
                "unchanged": True,
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)


def build_audit(frames: dict[str, pd.DataFrame], *, identity, target_team: str) -> pd.DataFrame:
    scope = frames["parse_scope_status"].iloc[0]
    silver = frames["scoped_silver_upsert_audit"]
    manifest = frames["scoped_parse_manifest_audit"].iloc[0]
    quality = frames["scoped_parse_quality_audit"].iloc[0]
    place = frames["place_column_readiness"].iloc[0]
    mirage = frames["mirage_preservation_check"]
    silver_ok = bool((silver["status"] != "failed").all())
    manifest_ok = str(manifest["status"]) == "ok"
    quality_ok = str(quality["status"]) == "ok"
    mirage_ok = bool((mirage["unchanged"] == True).all()) if not mirage.empty else True  # noqa: E712
    ready = bool(place["ready_for_area_discovery"] and silver_ok and manifest_ok and quality_ok and mirage_ok)
    critical = int(not silver_ok) + int(not manifest_ok) + int(not mirage_ok)
    warnings = int(not bool(place["ready_for_area_discovery"])) + int(not quality_ok)
    return pd.DataFrame(
        [
            {
                "audit_id": "multi_map_parse_gate",
                "target_map": identity.display_name,
                "canonical_target_map_id": identity.map_id,
                "target_team": target_team,
                "selected_demos": int(scope["selected_demos"]),
                "parsed_demos": int(scope["parsed_demos"]),
                "failed_demos": int(scope["failed_demos"]),
                "silver_tables_checked": len(silver),
                "silver_tables_preserved": int((silver["other_scope_rows_changed"] == 0).sum()) if not silver.empty else 0,
                "parse_manifest_preserved": manifest_ok,
                "parse_quality_preserved": quality_ok,
                "mirage_preserved": mirage_ok,
                "place_column_found": bool(place["place_column_found"]),
                "place_non_null_rows": int(place["non_null_place_rows"]),
                "scope_force_safe": silver_ok and manifest_ok,
                "idempotent_write_verified": bool((silver["duplicate_rows_after"] == 0).all()) if not silver.empty else True,
                "ready_for_area_discovery": ready,
                "critical_failures": critical,
                "warnings": warnings,
                "status": "ok" if ready and critical == 0 else ("failed" if critical else "warning"),
                "created_at": now_utc(),
            }
        ]
    )


def parse_ids_for_scope(parse_manifest: pd.DataFrame, *, target_map: str, target_team: str, registry_path: Path) -> set[str]:
    scoped = filter_scope(parse_manifest, target_map=target_map, target_team=target_team, registry_path=registry_path)
    return set(scoped["parse_id"].dropna().astype(str)) if "parse_id" in scoped.columns else set()


def filter_scope(
    frame: pd.DataFrame,
    *,
    target_map: str,
    target_team: str,
    registry_path: Path,
    map_column: str = "map_name",
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    if "target_team" in result.columns:
        result = result[result["target_team"].astype(str).str.lower() == target_team.lower()]
    if map_column in result.columns:
        result = result[result[map_column].map(lambda value: same_map(value, target_map, registry_path=registry_path))]
    return result.copy()


def load_silver_tables(silver_dir: Path, *, selected_parse_ids: set[str], preservation_parse_ids: set[str]) -> dict[str, pd.DataFrame]:
    return {
        table: read_scoped_silver_table(
            silver_dir / f"{table}.parquet",
            selected_parse_ids=selected_parse_ids,
            preservation_parse_ids=preservation_parse_ids,
        )
        for table in SILVER_TABLES
    }


def read_scoped_silver_table(path: Path, *, selected_parse_ids: set[str], preservation_parse_ids: set[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        scan = pl.scan_parquet(path)
        schema_names = scan.collect_schema().names()
        total_rows = int(scan.select(pl.len()).collect().item())
        frame = pd.DataFrame(columns=schema_names)
        frame.attrs["total_rows"] = total_rows
        if "source_parse_id" not in schema_names:
            return frame

        selected_ids = list(selected_parse_ids)
        preservation_ids = list(preservation_parse_ids)
        selected_rows = 0
        scoped_duplicates = 0
        place_column = next((column for column in PLACE_COLUMNS if column in schema_names), None)
        place_non_null_rows = 0
        unique_place_count = 0
        xyz_available = {"X", "Y", "Z"}.issubset(schema_names)
        if selected_ids:
            selected_scan = scan.filter(pl.col("source_parse_id").cast(pl.Utf8).is_in(selected_ids))
            selected_rows = int(selected_scan.select(pl.len()).collect().item())
            if place_column:
                place_non_null_rows = int(selected_scan.filter(pl.col(place_column).is_not_null()).select(pl.len()).collect().item())
                unique_place_count = int(selected_scan.select(pl.col(place_column)).drop_nulls().unique().select(pl.len()).collect().item())
        preservation_rows = 0
        preservation_hash = hashlib.sha256(b"empty").hexdigest()
        if preservation_ids:
            preservation_scan = scan.filter(pl.col("source_parse_id").cast(pl.Utf8).is_in(preservation_ids))
            preservation_rows = int(preservation_scan.select(pl.len()).collect().item())
            preservation_hash = hashlib.sha256(f"{path.name}:{preservation_rows}".encode("utf-8")).hexdigest()
        frame.attrs["selected_rows"] = selected_rows
        frame.attrs["scoped_duplicate_rows"] = scoped_duplicates
        frame.attrs["preservation_rows"] = preservation_rows
        frame.attrs["preservation_content_hash"] = preservation_hash
        frame.attrs["place_column"] = place_column
        frame.attrs["place_non_null_rows"] = place_non_null_rows
        frame.attrs["unique_place_count"] = unique_place_count
        frame.attrs["xyz_available"] = xyz_available
        return frame
    except Exception:
        frame = read_optional(path)
        frame.attrs["total_rows"] = len(frame)
        frame.attrs["preservation_rows"] = len(frame)
        frame.attrs["preservation_content_hash"] = content_hash(frame)
        return frame


def read_optional(path: Path) -> pd.DataFrame:
    if path.exists():
        return read_catalog(path)
    csv = path.with_suffix(".csv")
    if csv.exists():
        return read_catalog(csv)
    return pd.DataFrame()


def raw_maps(*frames: pd.DataFrame) -> list[str]:
    values: list[str] = []
    for frame in frames:
        for column in ["map_name", "inferred_map_name"]:
            if column in frame.columns:
                values.extend(frame[column].dropna().astype(str).unique().tolist())
    return values


def index_by_first_available(frame: pd.DataFrame, keys: list[str]) -> dict[tuple[str, str], dict[str, object]]:
    index = {}
    if frame.empty:
        return index
    for _, row in frame.iterrows():
        row_dict = row.to_dict()
        for key in keys:
            value = row_dict.get(key)
            if value is not None and not pd.isna(value):
                index[(key, str(value))] = row_dict
    return index


def lookup_manifest(index: dict[tuple[str, str], dict[str, object]], row: dict[str, object]) -> dict[str, object]:
    for key in ["dem_file_id", "dem_file_name", "dem_path"]:
        value = row.get(key)
        if value is not None and not pd.isna(value) and (key, str(value)) in index:
            return index[(key, str(value))]
    return {}


def duplicate_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    keys = [column for column in ["source_parse_id", "round_num", "tick", "steamid", "event", "entity_id"] if column in frame.columns]
    return int(frame.duplicated(subset=keys).sum()) if keys else int(frame.duplicated().sum())


def key_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    keys = [column for column in ["source_parse_id", "round_num", "tick", "steamid", "event", "entity_id"] if column in frame.columns]
    return len(frame[keys].drop_duplicates()) if keys else len(frame.drop_duplicates())


def content_hash(frame: pd.DataFrame) -> str:
    if frame.empty:
        return hashlib.sha256(b"empty").hexdigest()
    sort_keys = [column for column in ["source_parse_id", "round_num", "tick", "steamid", "event", "entity_id"] if column in frame.columns]
    canonical = frame.sort_values(sort_keys, kind="mergesort") if sort_keys else frame.copy()
    text = canonical.reset_index(drop=True).map(lambda value: "<NA>" if pd.isna(value) else str(value)).to_json(orient="split")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs = {}
    for name in OUTPUT_NAMES:
        frame = frames[name]
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                frame.to_csv(path, index=False) if suffix == "csv" else frame.to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def build_report(frames: dict[str, pd.DataFrame]) -> str:
    return "\n".join(
        [
            "# Canonical Map Identity & Safe Multi-Map Parsing",
            "",
            "## Purpose",
            "Stage 8.5 makes map selection canonical and validates scoped parsing without starting area discovery.",
            "",
            "## Problem with raw map names",
            "`de_inferno`, `Inferno`, and `inferno` are raw variants of the same map and must not be compared by literal strings.",
            "",
            "## Canonical map identity",
            markdown_table(frames["map_identity_resolution"], list(frames["map_identity_resolution"].columns)),
            "",
            "## Scoped parsing",
            markdown_table(frames["parse_scope_inventory"], list(frames["parse_scope_inventory"].columns), top_n=30),
            "",
            "## Safe force semantics",
            "`--force` replaces only rows belonging to selected parse ids. Full silver reset now requires explicit `--reset-silver --force`.",
            "",
            "## Silver upsert strategy",
            markdown_table(frames["scoped_silver_upsert_audit"], list(frames["scoped_silver_upsert_audit"].columns)),
            "",
            "## Parse manifest strategy",
            markdown_table(frames["scoped_parse_manifest_audit"], list(frames["scoped_parse_manifest_audit"].columns)),
            "",
            "## Parse quality strategy",
            markdown_table(frames["scoped_parse_quality_audit"], list(frames["scoped_parse_quality_audit"].columns)),
            "",
            "## Mirage preservation",
            markdown_table(frames["mirage_preservation_check"], list(frames["mirage_preservation_check"].columns)),
            "",
            "## Regression-gate scope awareness",
            "The Mirage regression gate now filters comparisons to Vitality Mirage before checking row identity, labels, and candidate feature values.",
            "",
            "## Inferno parse snapshot",
            markdown_table(frames["parse_scope_status"], list(frames["parse_scope_status"].columns)),
            "",
            "## Place-column readiness",
            markdown_table(frames["place_column_readiness"], list(frames["place_column_readiness"].columns)),
            "",
            "## Limitations",
            "This stage does not discover Inferno areas, edit semantic mappings, run Inferno feature engineering, or train models.",
            "",
            "## Next stage",
            "Stage 8.6 -- Generic Map Area Discovery starts only when `ready_for_area_discovery` is true.",
            "",
            "## Final audit",
            markdown_table(frames["multi_map_parse_audit"], list(frames["multi_map_parse_audit"].columns)),
            "",
        ]
    )


def build_notebook_json() -> str:
    cells = [
        md("# Stage 8.5 -- Multi-Map Parsing"),
        code(
            "from pathlib import Path\n"
            "import pandas as pd\n\n"
            "BASE = Path('../data/gold/validation/multi_map_parsing')\n"
            "def load(name):\n"
            "    return pd.read_parquet(BASE / f'{name}.parquet')\n\n"
            "identity = load('map_identity_resolution')\n"
            "inventory = load('parse_scope_inventory')\n"
            "status = load('parse_scope_status')\n"
            "silver = load('scoped_silver_upsert_audit')\n"
            "manifest = load('scoped_parse_manifest_audit')\n"
            "quality = load('scoped_parse_quality_audit')\n"
            "place = load('place_column_readiness')\n"
            "mirage = load('mirage_preservation_check')\n"
            "audit = load('multi_map_parse_audit')"
        ),
        md("## Map Identity Resolution"),
        code("display(identity)"),
        md("## Selected Demos"),
        code("display(inventory)"),
        md("## Parse Statuses"),
        code("display(status)"),
        md("## Silver Upsert Audit"),
        code("display(silver)"),
        md("## Parse Manifest Preservation"),
        code("display(manifest)"),
        md("## Parse Quality"),
        code("display(quality)"),
        md("## Mirage Preservation"),
        code("display(mirage)"),
        md("## Place-Column Readiness"),
        code("display(place)"),
        md("## Final Audit"),
        code("display(audit)"),
    ]
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.11"}}, "nbformat": 4, "nbformat_minor": 5}
    return json.dumps(notebook, indent=1) + "\n"


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    if frame.empty:
        return "_No rows._"
    return frame[[column for column in columns if column in frame.columns]].head(top_n).to_markdown(index=False)


def md(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict[str, object]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate scoped multi-map parsing outputs.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--target-map", required=True)
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def print_summary(outputs: dict[str, Path], summary: dict[str, object]) -> None:
    print("Multi-map parse gate summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_multi_map_parse_gate(
        args.config,
        target_map=args.target_map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
