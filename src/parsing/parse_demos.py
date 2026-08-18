from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import polars as pl

from src.config.schemas import ProjectConfig, load_project_config
from src.ingestion.demo_downloader import sha256_file
from src.maps.identity import canonical_map_id, try_resolve_map_identity
from src.parsing.parse_audit import write_parse_audit
from src.parsing.awpy_parser import AwpyParser
from src.parsing.parse_manifest import PARSE_MANIFEST_COLUMNS, empty_parse_manifest, upsert_parse_manifest, write_parse_manifest
from src.parsing.parsed_tables import bronze_output_dir, write_bronze_tables, write_silver_tables
from src.utils.io import read_catalog
from src.utils.logging import configure_logging
from src.utils.text import clean_string, safe_slug


def run_parse_pipeline(
    config_path: Path,
    *,
    manifest_path: Path | None = None,
    limit: int | None = None,
    force: bool | None = None,
    dry_run: bool = False,
    include_warnings: bool = False,
    backend: str | None = None,
    allow_unknown_map: bool = False,
    assume_map: str | None = None,
    target_maps: list[str] | None = None,
    target_team: str | None = None,
    reset_silver: bool = False,
    parser_class: type[AwpyParser] = AwpyParser,
) -> tuple[pd.DataFrame, dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    registry_path = project_root / "configs" / "maps" / "map_registry.yaml"
    parser_backend = backend or project.parser_backend
    if parser_backend != "awpy":
        raise ValueError(f"Unsupported parser backend: {parser_backend}")

    target_team_overridden = target_team is not None
    raw_target_maps = target_maps or project.target_maps
    target_map_ids = {canonical_map_id(value, registry_path=registry_path) for value in raw_target_maps}
    target_team = target_team or project.target_teams[0]
    scoped_update = target_maps is not None or target_team_overridden
    demo_manifest = load_parse_source(
        project,
        manifest_path,
        target_map_ids=target_map_ids,
        target_team=target_team,
        registry_path=registry_path,
        allow_unknown_map=allow_unknown_map,
        assume_map=assume_map,
    )
    if scoped_update and "_scope_selected" in demo_manifest.columns:
        demo_manifest = demo_manifest[demo_manifest["_scope_selected"] == True].copy()  # noqa: E712
    skipped = build_skip_rows(demo_manifest, parser_backend, project)
    eligible = select_parse_rows(demo_manifest, include_warnings=include_warnings)
    run_limit = limit if limit is not None else project.max_demos_per_run
    if run_limit is not None:
        eligible = eligible.head(run_limit)
    effective_force = project.force_parse if force is None else force
    if reset_silver and not effective_force:
        raise ValueError("--reset-silver is destructive and requires --force.")

    selected_parse_ids = {str(row["parse_id"]) for row in skipped}
    selected_parse_ids.update(build_parse_id(row.to_dict(), parser_backend) for _, row in eligible.iterrows())

    if eligible.empty and not skipped:
        parse_manifest = empty_parse_manifest()
        if scoped_update:
            existing_manifest_path = project.parse_manifest_dir / "parse_manifest.parquet"
            parse_manifest = read_demo_manifest(existing_manifest_path) if existing_manifest_path.exists() else parse_manifest
            return parse_manifest, {}, build_summary(empty_parse_manifest(), len(demo_manifest), 0)
        outputs = write_parse_manifest(parse_manifest, project.parse_manifest_dir, project.output_formats)
        return parse_manifest, outputs, build_summary(parse_manifest, len(demo_manifest), 0)

    if reset_silver and effective_force and not dry_run:
        clear_silver_tables(project.parsed_silver_dir)
    elif effective_force and selected_parse_ids and not dry_run:
        clear_selected_silver_rows(project.parsed_silver_dir, selected_parse_ids)

    rows = skipped + process_parse_rows(
        eligible,
        project,
        backend=parser_backend,
        force=effective_force,
        dry_run=dry_run,
        parser_class=parser_class,
    )
    parse_manifest = pd.DataFrame(rows, columns=PARSE_MANIFEST_COLUMNS)
    scoped_summary_manifest = parse_manifest.copy()
    if scoped_update and not reset_silver:
        outputs = upsert_parse_manifest(parse_manifest, project.parse_manifest_dir, project.output_formats, parse_ids=selected_parse_ids)
        parse_manifest = read_demo_manifest(project.parse_manifest_dir / "parse_manifest.parquet")
    else:
        outputs = write_parse_manifest(parse_manifest, project.parse_manifest_dir, project.output_formats)
    if not dry_run:
        outputs.update(write_parse_audit(project.parsed_silver_dir, project.parse_manifest_dir.parent / "parse_audit", project.output_formats))
    summary_manifest = scoped_summary_manifest if scoped_update else parse_manifest
    return parse_manifest, outputs, build_summary(summary_manifest, len(demo_manifest), len(eligible))


def read_demo_manifest(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return read_catalog(path)


def clear_silver_tables(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for path in output_dir.glob("*.parquet"):
        path.unlink()


def clear_selected_silver_rows(output_dir: Path, parse_ids: set[str]) -> None:
    if not output_dir.exists():
        return
    for path in output_dir.glob("*.parquet"):
        schema = pl.scan_parquet(path).collect_schema()
        if "source_parse_id" not in schema.names():
            continue
        temp_path = path.with_suffix(".scoped_tmp.parquet")
        (
            pl.scan_parquet(path)
            .filter(~pl.col("source_parse_id").cast(pl.Utf8).is_in(list(parse_ids)))
            .sink_parquet(temp_path)
        )
        temp_path.replace(path)


def load_parse_source(
    project: ProjectConfig,
    manifest_path: Path | None,
    *,
    target_map_ids: set[str],
    target_team: str,
    registry_path: Path,
    allow_unknown_map: bool,
    assume_map: str | None,
) -> pd.DataFrame:
    if manifest_path is not None:
        manifest = read_demo_manifest(manifest_path)
        return normalize_existing_manifest_source(manifest, target_map_ids=target_map_ids, target_team=target_team, registry_path=registry_path)
    if project.dem_files_manifest_path.exists():
        return normalize_dem_files_manifest(
            read_demo_manifest(project.dem_files_manifest_path),
            target_map_ids=target_map_ids,
            target_team=target_team,
            registry_path=registry_path,
            allow_unknown_map=allow_unknown_map,
            assume_map=assume_map,
        )
    return normalize_existing_manifest_source(read_demo_manifest(project.demo_manifest_path), target_map_ids=target_map_ids, target_team=target_team, registry_path=registry_path)


def normalize_existing_manifest_source(
    manifest: pd.DataFrame,
    *,
    target_map_ids: set[str],
    target_team: str,
    registry_path: Path,
) -> pd.DataFrame:
    if manifest.empty:
        return manifest
    rows = []
    for _, row in manifest.iterrows():
        row_dict = row.to_dict()
        map_name = clean_string(row_dict.get("map_name"))
        map_match = map_name_matches_scope(map_name, target_map_ids, registry_path=registry_path)
        team_match = team_matches_scope(row_dict.get("target_team"), target_team)
        rows.append({**row_dict, "_scope_selected": bool(map_match and team_match)})
    return pd.DataFrame(rows)


def normalize_dem_files_manifest(
    dem_files: pd.DataFrame,
    *,
    target_map_ids: set[str],
    target_team: str,
    registry_path: Path,
    allow_unknown_map: bool,
    assume_map: str | None,
) -> pd.DataFrame:
    if dem_files.empty:
        return pd.DataFrame()
    rows = []
    for _, row in dem_files.iterrows():
        row_dict = row.to_dict()
        inferred_map = clean_string(row_dict.get("inferred_map_name")) or "unknown"
        map_name = assume_map if assume_map and inferred_map == "unknown" else inferred_map
        map_match = map_name_matches_scope(map_name, target_map_ids, registry_path=registry_path)
        team_match = team_matches_scope(row_dict.get("target_team"), target_team)
        skip_reason = None
        if not is_parse_eligible(row_dict):
            skip_reason = clean_string(row_dict.get("exclusion_reason")) or "not_parse_eligible"
        elif not map_match and not (allow_unknown_map and inferred_map == "unknown") and not (assume_map and inferred_map == "unknown"):
            skip_reason = "map_unknown" if inferred_map == "unknown" else "map_not_target"
        rows.append(
            {
                **row_dict,
                "demo_record_id": row_dict.get("dem_file_id"),
                "series_id": row_dict.get("local_archive_id"),
                "hltv_match_id": None,
                "match_date": None,
                "event_name": None,
                "target_team": row_dict.get("target_team"),
                "opponent": "unknown",
                "map_name": map_name,
                "map_number": row_dict.get("inferred_map_number"),
                "status": "ok" if skip_reason is None else skip_reason,
                "_skip_reason": skip_reason,
                "_scope_selected": bool(team_match and (map_match or inferred_map == "unknown" or skip_reason != "map_not_target")),
            }
        )
    return pd.DataFrame(rows)


def map_name_matches_scope(map_name: object, target_map_ids: set[str], *, registry_path: Path) -> bool:
    identity = try_resolve_map_identity(map_name, registry_path=registry_path)
    return bool(identity and identity.map_id in target_map_ids)


def team_matches_scope(team_name: object, target_team: str) -> bool:
    team = clean_string(team_name)
    return bool(team and team.lower() == target_team.lower())


def is_parse_eligible(row: dict[str, object]) -> bool:
    if "parse_eligible" not in row:
        return True
    value = row.get("parse_eligible")
    if pd.isna(value):
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in {"false", "0", "no", "n"}


def build_skip_rows(demo_manifest: pd.DataFrame, backend: str, project: ProjectConfig) -> list[dict[str, object]]:
    if demo_manifest.empty or "_skip_reason" not in demo_manifest.columns:
        return []
    rows = []
    for _, row in demo_manifest[demo_manifest["_skip_reason"].notna()].iterrows():
        row_dict = row.to_dict()
        parse_id = build_parse_id(row_dict, backend)
        output_dir = bronze_output_dir(project.parsed_bronze_dir, row_dict)
        skip_reason = str(row_dict["_skip_reason"])
        rows.append(
            parse_manifest_row(
                row_dict,
                parse_id,
                backend,
                skip_reason,
                error_message=skip_error_message(skip_reason),
                output_bronze_dir=output_dir,
            )
        )
    return rows


def skip_error_message(skip_reason: str) -> str:
    if skip_reason in {"map_unknown", "map_not_target"}:
        return f"Skipped by map filter: {skip_reason}"
    return f"Skipped because row is not parse eligible: {skip_reason}"


def select_parse_rows(demo_manifest: pd.DataFrame, *, include_warnings: bool) -> pd.DataFrame:
    if demo_manifest.empty or "dem_path" not in demo_manifest.columns:
        return pd.DataFrame()
    statuses = ["ok", "warning"] if include_warnings else ["ok"]
    return demo_manifest[
        demo_manifest["status"].isin(statuses)
        & demo_manifest["dem_path"].map(lambda value: clean_string(value) is not None)
    ].copy()


def process_parse_rows(
    rows: pd.DataFrame,
    project: ProjectConfig,
    *,
    backend: str,
    force: bool,
    dry_run: bool,
    parser_class: type[AwpyParser],
) -> list[dict[str, object]]:
    parser = None if dry_run else parser_class(player_props=project.parse_player_props, parse_tables=project.parse_tables, parse_events=project.parse_events)
    manifest_rows: list[dict[str, object]] = []

    for _, row in rows.iterrows():
        row_dict = row.to_dict()
        dem_path = Path(str(row_dict.get("dem_path")))
        parse_id = build_parse_id(row_dict, backend)
        output_dir = bronze_output_dir(project.parsed_bronze_dir, row_dict)

        if dry_run:
            manifest_rows.append(parse_manifest_row(row_dict, parse_id, backend, "dry_run", output_bronze_dir=output_dir))
            continue

        if not dem_path.exists():
            manifest_rows.append(parse_manifest_row(row_dict, parse_id, backend, "missing_dem", error_message=f"DEM file not found: {dem_path}", output_bronze_dir=output_dir))
            continue

        if output_dir.exists() and any(output_dir.glob("*.parquet")) and not force:
            manifest_rows.append(parse_manifest_row(row_dict, parse_id, backend, "skipped_existing", output_bronze_dir=output_dir))
            continue

        try:
            assert parser is not None
            parsed = parser.parse(dem_path)
            row_counts = write_bronze_tables(parsed.tables, parsed.events, output_dir)
            write_silver_tables(parsed.tables, row_dict, parse_id, project.parsed_silver_dir)
            manifest_rows.append(
                parse_manifest_row(
                    row_dict,
                    parse_id,
                    backend,
                    "parsed",
                    parser_version=parsed.parser_version,
                    output_bronze_dir=output_dir,
                    row_counts=row_counts,
                )
            )
        except Exception as exc:
            manifest_rows.append(parse_manifest_row(row_dict, parse_id, backend, "failed", error_message=str(exc), output_bronze_dir=output_dir))

    return manifest_rows


def build_parse_id(row: dict[str, object], backend: str) -> str:
    base = row.get("demo_record_id") or row.get("series_id") or row.get("dem_file_name")
    return f"{safe_slug(base, fallback='unknown_demo')}_{safe_slug(backend)}"


def parse_manifest_row(
    row: dict[str, object],
    parse_id: str,
    backend: str,
    parse_status: str,
    *,
    parser_version: str | None = None,
    error_message: str | None = None,
    output_bronze_dir: Path | None = None,
    row_counts: dict[str, int] | None = None,
) -> dict[str, object]:
    row_counts = row_counts or {}
    dem_path = clean_string(row.get("dem_path"))
    dem_file_size = row.get("dem_file_size_bytes")
    dem_sha256 = clean_string(row.get("dem_sha256"))
    if dem_path and Path(dem_path).exists():
        dem_file_size = Path(dem_path).stat().st_size
        dem_sha256 = sha256_file(Path(dem_path))

    return {
        "parse_id": parse_id,
        "series_id": clean_string(row.get("series_id")),
        "hltv_match_id": clean_string(row.get("hltv_match_id")),
        "match_date": clean_string(row.get("match_date")),
        "event_name": clean_string(row.get("event_name")),
        "target_team": clean_string(row.get("target_team")),
        "opponent": clean_string(row.get("opponent")),
        "map_name": clean_string(row.get("map_name")),
        "map_number": clean_string(row.get("map_number")),
        "dem_path": dem_path,
        "dem_file_name": Path(dem_path).name if dem_path else clean_string(row.get("dem_file_name")),
        "dem_file_size_bytes": dem_file_size,
        "dem_sha256": dem_sha256,
        "parser_backend": backend,
        "parser_version": parser_version,
        "parse_status": parse_status,
        "parse_error_message": error_message,
        "parsed_at": datetime.now(timezone.utc).isoformat() if parse_status == "parsed" else None,
        "output_bronze_dir": str(output_bronze_dir) if output_bronze_dir else None,
        "rows_rounds": row_counts.get("rounds", 0),
        "rows_kills": row_counts.get("kills", 0),
        "rows_damages": row_counts.get("damages", 0),
        "rows_shots": row_counts.get("shots", 0),
        "rows_bomb": row_counts.get("bomb", 0),
        "rows_smokes": row_counts.get("smokes", 0),
        "rows_infernos": row_counts.get("infernos", 0),
        "rows_grenades": row_counts.get("grenades", 0),
        "rows_footsteps": row_counts.get("footsteps", 0),
        "rows_ticks": row_counts.get("ticks", 0),
        "rows_events_total": row_counts.get("events_total", 0),
    }


def build_summary(parse_manifest: pd.DataFrame, total_manifest_rows: int, total_eligible: int) -> dict[str, int]:
    if parse_manifest.empty:
        return {
            "total_manifest_rows": total_manifest_rows,
            "total_eligible": total_eligible,
            "total_parsed": 0,
            "total_dry_run": 0,
            "total_missing_dem": 0,
            "total_failed": 0,
            "total_skipped_existing": 0,
            "total_map_unknown": 0,
            "total_map_not_target": 0,
            "total_not_parse_eligible": 0,
        }
    not_parse_eligible_statuses = {"not_parse_eligible", "split_segment_merged"}
    return {
        "total_manifest_rows": total_manifest_rows,
        "total_eligible": total_eligible,
        "total_parsed": int((parse_manifest["parse_status"] == "parsed").sum()),
        "total_dry_run": int((parse_manifest["parse_status"] == "dry_run").sum()),
        "total_missing_dem": int((parse_manifest["parse_status"] == "missing_dem").sum()),
        "total_failed": int((parse_manifest["parse_status"] == "failed").sum()),
        "total_skipped_existing": int((parse_manifest["parse_status"] == "skipped_existing").sum()),
        "total_map_unknown": int((parse_manifest["parse_status"] == "map_unknown").sum()),
        "total_map_not_target": int((parse_manifest["parse_status"] == "map_not_target").sum()),
        "total_not_parse_eligible": int(parse_manifest["parse_status"].isin(not_parse_eligible_statuses).sum()),
    }


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Demo parse summary")
    print(f"- total de linhas do demo_manifest lidas: {summary['total_manifest_rows']}")
    print(f"- total elegiveis para parsing: {summary['total_eligible']}")
    print(f"- total parseadas: {summary['total_parsed']}")
    print(f"- total dry_run: {summary['total_dry_run']}")
    print(f"- total missing_dem: {summary['total_missing_dem']}")
    print(f"- total skipped_existing: {summary['total_skipped_existing']}")
    print(f"- total map_unknown: {summary['total_map_unknown']}")
    print(f"- total map_not_target: {summary['total_map_not_target']}")
    print(f"- total not_parse_eligible: {summary['total_not_parse_eligible']}")
    print(f"- total failed: {summary['total_failed']}")
    for fmt, path in outputs.items():
        label = "parse_audit" if fmt.startswith("parse_audit") else "parse_manifest"
        clean_fmt = fmt.replace("parse_audit_", "")
        print(f"- {label} {clean_fmt}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse extracted CS2 demos into bronze and silver tables.")
    parser.add_argument("--config", type=Path, required=True, help="Path to configs/project.yaml")
    parser.add_argument("--manifest", type=Path, default=None, help="Optional path to demo_manifest.parquet or .csv")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of demos processed")
    parser.add_argument("--force", action="store_true", help="Reprocess demos even when outputs already exist")
    parser.add_argument("--dry-run", action="store_true", help="Do not parse, only write parse_manifest dry-run rows")
    parser.add_argument("--include-warnings", action="store_true", help="Include warning rows from demo_manifest when dem_path exists")
    parser.add_argument("--backend", default=None, help="Parser backend. Currently only awpy is supported")
    parser.add_argument("--allow-unknown-map", action="store_true", help="Allow parsing rows from dem_files_manifest with inferred_map_name = unknown")
    parser.add_argument("--assume-map", default=None, help="Treat unknown inferred maps as this map name")
    parser.add_argument("--target-map", action="append", dest="target_maps", default=None, help="Map scope to parse. Can be passed more than once and accepts aliases such as Inferno/de_inferno.")
    parser.add_argument("--target-team", default=None, help="Team scope to parse. Defaults to the first project target team.")
    parser.add_argument("--reset-silver", action="store_true", help="Destructive full parsed-silver reset. Requires --force.")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_parse_pipeline(
        args.config,
        manifest_path=args.manifest,
        limit=args.limit,
        force=True if args.force else None,
        dry_run=args.dry_run,
        include_warnings=args.include_warnings,
        backend=args.backend,
        allow_unknown_map=args.allow_unknown_map,
        assume_map=args.assume_map,
        target_maps=args.target_maps,
        target_team=args.target_team,
        reset_silver=args.reset_silver,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
