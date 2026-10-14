from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
import yaml

from src.config.schemas import load_project_config
from src.ingestion.demo_downloader import sha256_file
from src.maps.identity import try_resolve_map_identity
from src.storage.silver_tables import partition_file_name, silver_partition_files, silver_partition_root
from src.utils.io import ensure_dir, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.text import clean_string, safe_slug


AUDIT_COLUMNS = [
    "run_id",
    "status",
    "source_path",
    "partition_root",
    "rollback_path",
    "source_rows",
    "partition_rows",
    "source_parse_ids",
    "partition_files",
    "schema_match",
    "per_parse_count_match",
    "content_fingerprint_match",
    "source_fingerprint",
    "partition_fingerprint",
    "source_sha256",
    "rollback_sha256",
    "rollback_hash_match",
    "started_at",
    "completed_at",
    "notes",
]


def run_ticks_migration(
    config_path: Path,
    *,
    run_id: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    silver_dir = resolve(project_root, project.parsed_silver_dir)
    source_path = silver_dir / "ticks.parquet"
    target_root = silver_partition_root(silver_dir, "ticks")
    storage = load_storage_contract(project_root / "configs/storage.yaml")
    rollback_root = resolve(project_root, Path(storage["roots"]["migration_rollback"]))
    output_dir = resolve(project_root, Path(storage["audit"]["silver_ticks_migration"]))
    run_id = run_id or datetime.now(timezone.utc).strftime("ticks_%Y%m%dt%H%M%Sz")
    validate_run_id(run_id)
    started_at = datetime.now(timezone.utc).isoformat()

    existing_partitions = silver_partition_files(silver_dir, "ticks")
    if not source_path.exists():
        if not existing_partitions:
            raise FileNotFoundError(f"Neither legacy nor partitioned Silver ticks exist under {silver_dir}")
        audit = verify_existing_partition_state(output_dir, existing_partitions)
        frames = {
            "silver_ticks_migration_audit": audit,
            "silver_ticks_partition_manifest": partition_manifest(existing_partitions),
        }
        return frames, {}, summary_from_audit(audit)

    if target_root.exists() and not force:
        raise FileExistsError(f"Partition root already exists: {target_root}. Use --force only after reviewing it.")

    rollback_dir = rollback_root / run_id
    rollback_path = rollback_dir / "ticks.parquet"
    previous_partition_rollback = rollback_dir / "previous_table_ticks"
    if rollback_dir.exists():
        raise FileExistsError(f"Rollback run directory already exists; choose a new run_id: {rollback_dir}")
    evidence_paths = [
        output_dir / f"{name}.{suffix}"
        for name in ("silver_ticks_migration_audit", "silver_ticks_partition_manifest")
        for suffix in project.output_formats
    ]
    existing_evidence = [path for path in evidence_paths if path.exists()]
    if existing_evidence:
        raise FileExistsError(
            "Governed migration evidence already exists and will not be overwritten: "
            f"{existing_evidence}. Verify the current partition state instead."
        )

    source_scan = pl.scan_parquet(source_path)
    scopes = source_scopes(source_scan)
    source_rows = int(scopes["row_count"].sum())
    source_schema = schema_signature(source_scan)
    registry_path = project_root / "configs/maps/map_registry.yaml"
    plan = build_partition_plan(scopes, target_root, registry_path=registry_path)
    if dry_run:
        audit = pd.DataFrame(
            [
                audit_row(
                    run_id=run_id,
                    status="dry_run",
                    source_path=source_path,
                    partition_root=target_root,
                    rollback_path=None,
                    source_rows=source_rows,
                    partition_rows=0,
                    source_parse_ids=len(scopes),
                    partition_files=len(plan),
                    schema_match=None,
                    per_parse_count_match=None,
                    content_fingerprint_match=None,
                    source_fingerprint=None,
                    partition_fingerprint=None,
                    source_sha256=None,
                    rollback_sha256=None,
                    rollback_hash_match=None,
                    started_at=started_at,
                    notes="Migration plan validated; no files written.",
                )
            ],
            columns=AUDIT_COLUMNS,
        )
        return {"silver_ticks_migration_audit": audit, "silver_ticks_partition_plan": plan}, {}, summary_from_audit(audit)

    staging_root = silver_dir / f"table=ticks.__staging__.{run_id}"
    if staging_root.exists():
        raise FileExistsError(f"Migration staging directory already exists: {staging_root}")
    ensure_dir(staging_root)
    previous_moved = False
    target_promoted = False
    source_moved = False
    try:
        staging_files = write_partitions(source_scan, scopes, staging_root, project_root=project_root)
        partition_scan = pl.scan_parquet([str(path) for path in staging_files])
        partition_scopes = source_scopes(partition_scan)
        partition_rows = int(partition_scopes["row_count"].sum())
        schema_match = source_schema == schema_signature(partition_scan)
        count_match = scope_counts(scopes) == scope_counts(partition_scopes)
        source_fingerprint = content_fingerprint(source_scan)
        partition_fingerprint = content_fingerprint(partition_scan)
        fingerprint_match = source_fingerprint == partition_fingerprint
        if not (source_rows == partition_rows and schema_match and count_match and fingerprint_match):
            raise RuntimeError(
                "Silver ticks migration parity failed: "
                f"rows={source_rows == partition_rows}, schema={schema_match}, "
                f"per_parse={count_match}, fingerprint={fingerprint_match}"
            )

        source_sha256 = sha256_file(source_path)
        if target_root.exists():
            ensure_dir(rollback_dir)
            os.replace(target_root, previous_partition_rollback)
            previous_moved = True
        os.replace(staging_root, target_root)
        target_promoted = True
        final_files = silver_partition_files(silver_dir, "ticks")

        ensure_dir(rollback_dir)
        os.replace(source_path, rollback_path)
        source_moved = True
        rollback_sha256 = sha256_file(rollback_path)
        rollback_hash_match = source_sha256 == rollback_sha256
        if not rollback_hash_match:
            raise RuntimeError("Rollback copy hash does not match the legacy Silver source hash.")

        manifest = partition_manifest(final_files, scopes=scopes)
        audit = pd.DataFrame(
            [
                audit_row(
                    run_id=run_id,
                    status="passed",
                    source_path=source_path,
                    partition_root=target_root,
                    rollback_path=rollback_path,
                    source_rows=source_rows,
                    partition_rows=partition_rows,
                    source_parse_ids=len(scopes),
                    partition_files=len(final_files),
                    schema_match=schema_match,
                    per_parse_count_match=count_match,
                    content_fingerprint_match=fingerprint_match,
                    source_fingerprint=source_fingerprint,
                    partition_fingerprint=partition_fingerprint,
                    source_sha256=source_sha256,
                    rollback_sha256=rollback_sha256,
                    rollback_hash_match=rollback_hash_match,
                    started_at=started_at,
                    notes=(
                        "Row count, schema, per-parse counts, and a commutative row-content fingerprint match. "
                        "The legacy monolith was moved to rollback storage."
                    ),
                )
            ],
            columns=AUDIT_COLUMNS,
        )
        frames = {"silver_ticks_migration_audit": audit, "silver_ticks_partition_manifest": manifest}
        outputs = write_dataframe_outputs(frames, output_dir, force=True, formats=tuple(project.output_formats))
        return frames, outputs, summary_from_audit(audit)
    except Exception:
        if source_moved and rollback_path.exists() and not source_path.exists():
            os.replace(rollback_path, source_path)
        if target_promoted and target_root.exists():
            os.replace(target_root, staging_root)
        if previous_moved and previous_partition_rollback.exists():
            os.replace(previous_partition_rollback, target_root)
        if staging_root.exists():
            shutil.rmtree(staging_root)
        if rollback_dir.exists():
            try:
                rollback_dir.rmdir()
            except OSError:
                pass
        for path in evidence_paths:
            if path.exists():
                path.unlink()
        raise


def source_scopes(scan: pl.LazyFrame) -> pd.DataFrame:
    required = {"source_parse_id", "target_team", "map_name"}
    missing = sorted(required - set(scan.collect_schema().names()))
    if missing:
        raise ValueError(f"Silver ticks cannot be partitioned; missing columns: {missing}")
    frame = (
        scan.group_by(["source_parse_id", "target_team", "map_name"])
        .agg(pl.len().alias("row_count"))
        .sort(["source_parse_id", "target_team", "map_name"])
        .collect(engine="streaming")
        .to_pandas()
    )
    duplicates = frame.groupby("source_parse_id", dropna=False).size()
    if bool((duplicates > 1).any()):
        invalid = duplicates[duplicates > 1].index.astype(str).tolist()
        raise ValueError(f"Parse ids span multiple team/map scopes: {invalid[:5]}")
    if frame["source_parse_id"].isna().any():
        raise ValueError("Silver ticks contain null source_parse_id values.")
    return frame


def build_partition_plan(scopes: pd.DataFrame, target_root: Path, *, registry_path: Path) -> pd.DataFrame:
    rows = []
    for row in scopes.to_dict("records"):
        parse_id = str(row["source_parse_id"])
        team_id = safe_slug(clean_string(row["target_team"]) or "unknown_team")
        identity = try_resolve_map_identity(row["map_name"], registry_path=registry_path)
        map_id = identity.map_id if identity else safe_slug(clean_string(row["map_name"]) or "unknown_map")
        rows.append(
            {
                **row,
                "planned_relative_path": str(
                    Path(f"target_team={team_id}") / f"map_id={map_id}" / partition_file_name(parse_id)
                ),
                "partition_root": str(target_root),
            }
        )
    return pd.DataFrame(rows)


def write_partitions(
    source_scan: pl.LazyFrame,
    scopes: pd.DataFrame,
    staging_root: Path,
    *,
    project_root: Path,
) -> list[Path]:
    registry_path = project_root / "configs/maps/map_registry.yaml"
    outputs = []
    for row in scopes.to_dict("records"):
        parse_id = str(row["source_parse_id"])
        team_id = safe_slug(clean_string(row["target_team"]) or "unknown_team")
        identity = try_resolve_map_identity(row["map_name"], registry_path=registry_path)
        map_id = identity.map_id if identity else safe_slug(clean_string(row["map_name"]) or "unknown_map")
        output_dir = ensure_dir(staging_root / f"target_team={team_id}" / f"map_id={map_id}")
        output_path = output_dir / partition_file_name(parse_id)
        temporary = output_path.with_suffix(".tmp.parquet")
        source_scan.filter(pl.col("source_parse_id").cast(pl.Utf8) == parse_id).sink_parquet(
            temporary,
            compression="zstd",
            statistics=True,
            mkdir=True,
        )
        os.replace(temporary, output_path)
        outputs.append(output_path)
    return outputs


def schema_signature(scan: pl.LazyFrame) -> list[tuple[str, str]]:
    return [(name, str(dtype)) for name, dtype in scan.collect_schema().items()]


def scope_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {str(row["source_parse_id"]): int(row["row_count"]) for row in frame.to_dict("records")}


def content_fingerprint(scan: pl.LazyFrame) -> str:
    row_hash = pl.struct(pl.all()).hash(seed=17, seed_1=29, seed_2=43, seed_3=71)
    values = scan.select(
        pl.len().alias("rows"),
        row_hash.sum().alias("hash_sum"),
        row_hash.min().alias("hash_min"),
        row_hash.max().alias("hash_max"),
    ).collect(engine="streaming").row(0, named=True)
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


def partition_manifest(files: list[Path], *, scopes: pd.DataFrame | None = None) -> pd.DataFrame:
    scope_by_file: dict[str, dict[str, object]] = {}
    if scopes is not None:
        for row in scopes.to_dict("records"):
            scope_by_file[partition_file_name(str(row["source_parse_id"]))] = row
    rows = []
    for path in sorted(files):
        metadata = pl.scan_parquet(path)
        scope = scope_by_file.get(path.name, {})
        rows.append(
            {
                "partition_path": str(path),
                "partition_file": path.name,
                "source_parse_id": scope.get("source_parse_id"),
                "target_team": scope.get("target_team"),
                "map_name": scope.get("map_name"),
                "row_count": int(scope.get("row_count") or metadata.select(pl.len()).collect().item()),
                "file_size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return pd.DataFrame(rows)


def verify_existing_partition_state(output_dir: Path, files: list[Path]) -> pd.DataFrame:
    audit_path = output_dir / "silver_ticks_migration_audit.parquet"
    if audit_path.exists():
        persisted = pd.read_parquet(audit_path)
    else:
        csv_path = output_dir / "silver_ticks_migration_audit.csv"
        if not csv_path.exists():
            raise RuntimeError(
                "Partitioned Silver ticks exist without a persisted migration audit; "
                "refusing to create parity evidence from the dataset itself."
            )
        persisted = pd.read_csv(csv_path)
    passed = persisted[persisted["status"].astype(str).str.casefold().eq("passed")]
    if passed.empty:
        raise RuntimeError("No persisted passed migration audit is available for the active partitions.")

    row = passed.iloc[-1].to_dict()
    rollback_value = clean_string(row.get("rollback_path"))
    if not rollback_value:
        raise RuntimeError("Persisted migration audit does not identify a rollback source.")
    rollback_path = Path(rollback_value)
    if not rollback_path.exists():
        raise RuntimeError(f"Persisted migration rollback source is missing: {rollback_path}")

    source_scan = pl.scan_parquet(rollback_path)
    partition_scan = pl.scan_parquet([str(path) for path in files])
    source_scope = source_scopes(source_scan)
    partition_scope = source_scopes(partition_scan)
    source_rows = int(source_scope["row_count"].sum())
    partition_rows = int(partition_scope["row_count"].sum())
    source_fingerprint = content_fingerprint(source_scan)
    partition_fingerprint = content_fingerprint(partition_scan)
    rollback_sha256 = sha256_file(rollback_path)
    checks = {
        "row_count": source_rows == partition_rows == int(row.get("source_rows") or -1),
        "schema": schema_signature(source_scan) == schema_signature(partition_scan),
        "per_parse_count": scope_counts(source_scope) == scope_counts(partition_scope),
        "content_fingerprint": source_fingerprint == partition_fingerprint,
        "recorded_source_fingerprint": source_fingerprint == clean_string(row.get("source_fingerprint")),
        "recorded_partition_fingerprint": partition_fingerprint == clean_string(row.get("partition_fingerprint")),
        "rollback_hash": rollback_sha256 == clean_string(row.get("source_sha256")),
        "partition_files": len(files) == int(row.get("partition_files") or -1),
    }
    failures = [name for name, value in checks.items() if not value]
    if failures:
        raise RuntimeError(f"Active Silver partitions no longer match the governed migration evidence: {failures}")

    row.update(
        {
            "rollback_sha256": rollback_sha256,
            "rollback_hash_match": True,
            "notes": f"{row.get('notes', '')} Existing partition state revalidated against the retained rollback source.",
        }
    )
    return pd.DataFrame([row], columns=AUDIT_COLUMNS)


def audit_row(**values: object) -> dict[str, object]:
    normalized = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in values.items()
    }
    return {**normalized, "completed_at": datetime.now(timezone.utc).isoformat()}


def summary_from_audit(audit: pd.DataFrame) -> dict[str, Any]:
    row = audit.iloc[-1]
    return {
        "run_id": row["run_id"],
        "status": row["status"],
        "source_rows": int(row["source_rows"]),
        "partition_rows": int(row["partition_rows"]),
        "partition_files": int(row["partition_files"]),
    }


def load_storage_contract(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Storage contract not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or {}
    if not isinstance(content, dict):
        raise ValueError(f"Storage contract must be a mapping: {path}")
    return content


def resolve(project_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else project_root / path


def validate_run_id(run_id: str) -> None:
    if not run_id or safe_slug(run_id) != run_id:
        raise ValueError("run_id must already be a lowercase filesystem-safe slug.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy Silver ticks into verified per-parse Parquet partitions.")
    parser.add_argument("--config", type=Path, default=Path("configs/project.yaml"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_ticks_migration(
        args.config,
        run_id=args.run_id,
        force=args.force,
        dry_run=args.dry_run,
    )
    print("Silver ticks migration summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for key, path in outputs.items():
        print(f"- {key}: {path}")


if __name__ == "__main__":
    main()
