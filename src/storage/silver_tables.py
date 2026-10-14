from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import TypeAlias

import pandas as pd
import pyarrow.parquet as pq

from src.maps.identity import try_resolve_map_identity
from src.utils.io import ensure_dir
from src.utils.text import clean_string, safe_slug


SilverScanSource: TypeAlias = str | Path | list[str]
PARTITIONED_TABLES = frozenset({"ticks"})


def silver_monolith_path(silver_dir: Path, table_name: str) -> Path:
    return silver_dir / f"{table_name}.parquet"


def silver_partition_root(silver_dir: Path, table_name: str) -> Path:
    return silver_dir / f"table={table_name}"


def silver_partition_files(silver_dir: Path, table_name: str) -> list[Path]:
    root = silver_partition_root(silver_dir, table_name)
    return (
        sorted(path for path in root.rglob("parse-*.parquet") if path.is_file() and not path.name.endswith(".tmp.parquet"))
        if root.exists()
        else []
    )


def silver_table_files(silver_dir: Path, table_name: str) -> list[Path]:
    partitions = silver_partition_files(silver_dir, table_name)
    monolith = silver_monolith_path(silver_dir, table_name)
    if partitions and monolith.exists():
        raise RuntimeError(
            f"Ambiguous Silver layout for {table_name}: both {monolith} and {silver_partition_root(silver_dir, table_name)} exist."
        )
    if partitions:
        return partitions
    return [monolith] if monolith.exists() else []


def silver_table_exists(silver_dir: Path, table_name: str) -> bool:
    return bool(silver_table_files(silver_dir, table_name))


def silver_scan_source(silver_dir: Path, table_name: str) -> SilverScanSource:
    files = silver_table_files(silver_dir, table_name)
    if not files:
        return silver_monolith_path(silver_dir, table_name)
    if len(files) == 1:
        return files[0]
    return [str(path) for path in files]


def read_silver_table(
    silver_dir: Path,
    table_name: str,
    *,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    files = silver_table_files(silver_dir, table_name)
    if not files:
        raise FileNotFoundError(f"Silver table not found: {table_name} under {silver_dir}")
    frames = [pq.ParquetFile(path).read(columns=columns).to_pandas() for path in files]
    return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)


def write_partitioned_silver_table(
    silver_dir: Path,
    table_name: str,
    frame: pd.DataFrame,
    *,
    parse_ids: set[str],
    registry_path: Path,
) -> list[Path]:
    if table_name not in PARTITIONED_TABLES:
        raise ValueError(f"Table is not configured as partitioned: {table_name}")
    if "source_parse_id" not in frame.columns:
        raise ValueError(f"Cannot partition {table_name} without source_parse_id.")
    monolith = silver_monolith_path(silver_dir, table_name)
    if monolith.exists():
        raise RuntimeError(
            f"Legacy Silver monolith still exists: {monolith}. Run src.storage.migrate_silver_ticks first."
        )

    requested_parse_ids = {str(parse_id) for parse_id in parse_ids}
    observed_parse_ids = {
        value
        for item in frame["source_parse_id"]
        for value in [clean_string(item)]
        if value
    }
    if not observed_parse_ids or observed_parse_ids != requested_parse_ids:
        raise ValueError(
            f"Partition write scope mismatch for {table_name}: "
            f"requested={sorted(requested_parse_ids)}, observed={sorted(observed_parse_ids)}"
        )

    root = ensure_dir(silver_partition_root(silver_dir, table_name))
    planned: list[tuple[str, pd.DataFrame, Path]] = []
    for parse_id, scoped in frame.groupby(frame["source_parse_id"].astype(str), sort=True, dropna=False):
        if not parse_id or parse_id == "nan":
            raise ValueError(f"Cannot partition {table_name} with a blank source_parse_id.")
        teams = non_empty_values(scoped.get("target_team", pd.Series(dtype=object)))
        maps = non_empty_values(scoped.get("map_name", pd.Series(dtype=object)))
        if len(teams) != 1 or len(maps) != 1:
            raise ValueError(
                f"Partition {parse_id} must resolve to exactly one target_team/map_name; "
                f"teams={sorted(teams)}, maps={sorted(maps)}"
            )
        team_id = safe_slug(next(iter(teams))) or "unknown_team"
        identity = try_resolve_map_identity(next(iter(maps)), registry_path=registry_path)
        map_id = identity.map_id if identity else safe_slug(next(iter(maps))) or "unknown_map"
        output_path = root / f"target_team={team_id}" / f"map_id={map_id}" / partition_file_name(parse_id)
        matches = [path for path in silver_partition_files(silver_dir, table_name) if path.name == output_path.name]
        if len(matches) > 1:
            raise RuntimeError(f"Duplicate active partitions for source_parse_id={parse_id}: {matches}")
        planned.append((parse_id, scoped, output_path))

    staging_root = ensure_dir(silver_dir / ".silver_write_staging" / uuid.uuid4().hex)
    staged: list[tuple[Path, Path]] = []
    backups: list[tuple[Path, Path]] = []
    promoted: list[Path] = []
    try:
        for index, (_parse_id, scoped, output_path) in enumerate(planned):
            temporary = staging_root / "new" / f"{index:04d}.parquet"
            ensure_dir(temporary.parent)
            scoped.to_parquet(temporary, index=False, compression="zstd")
            if pq.ParquetFile(temporary).metadata.num_rows != len(scoped):
                raise RuntimeError(f"Staged partition row-count mismatch: {temporary}")
            staged.append((temporary, output_path))

        for index, (temporary, output_path) in enumerate(staged):
            matches = [path for path in silver_partition_files(silver_dir, table_name) if path.name == output_path.name]
            if len(matches) > 1:
                raise RuntimeError(f"Duplicate active partitions for destination {output_path.name}: {matches}")
            if matches:
                previous_path = matches[0]
                backup_path = staging_root / "previous" / f"{index:04d}.parquet"
                ensure_dir(backup_path.parent)
                os.replace(previous_path, backup_path)
                backups.append((previous_path, backup_path))
            ensure_dir(output_path.parent)
            os.replace(temporary, output_path)
            promoted.append(output_path)
    except Exception:
        for output_path in reversed(promoted):
            if output_path.exists():
                output_path.unlink()
        for previous_path, backup_path in reversed(backups):
            if backup_path.exists():
                ensure_dir(previous_path.parent)
                os.replace(backup_path, previous_path)
        raise
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        staging_parent = staging_root.parent
        if staging_parent.exists():
            try:
                staging_parent.rmdir()
            except OSError:
                pass
        prune_empty_directories(root)
    return [output_path for _parse_id, _scoped, output_path in planned]


def remove_partitioned_parse_ids(silver_dir: Path, table_name: str, parse_ids: set[str]) -> None:
    if not parse_ids:
        return
    root = silver_partition_root(silver_dir, table_name)
    if not root.exists():
        return
    names = {partition_file_name(str(parse_id)) for parse_id in parse_ids}
    for path in root.rglob("*.parquet"):
        if path.name in names:
            path.unlink()
    prune_empty_directories(root)


def clear_partitioned_silver_table(silver_dir: Path, table_name: str) -> None:
    root = silver_partition_root(silver_dir, table_name)
    if not root.exists():
        return
    resolved_silver = silver_dir.resolve()
    resolved_root = root.resolve()
    if resolved_root.parent != resolved_silver or resolved_root.name != f"table={table_name}":
        raise ValueError(f"Refusing to clear unexpected partition root: {resolved_root}")
    shutil.rmtree(resolved_root)


def partition_file_name(parse_id: str) -> str:
    digest = hashlib.sha256(parse_id.encode("utf-8")).hexdigest()[:24]
    return f"parse-{digest}.parquet"


def non_empty_values(values: pd.Series) -> set[str]:
    return {value for item in values for value in [clean_string(item)] if value}


def prune_empty_directories(root: Path) -> None:
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            pass
