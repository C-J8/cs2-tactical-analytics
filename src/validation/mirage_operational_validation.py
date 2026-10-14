from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
import yaml

from src.config.schemas import load_project_config, load_yaml
from src.features.build_role_features import run_role_feature_pipeline
from src.features.build_round_features import run_feature_pipeline
from src.features.round_state import run_round_state_pipeline
from src.features.side_datasets import run_side_dataset_pipeline
from src.ingestion.archive_extractor import ArchiveExtractor
from src.ingestion.demo_downloader import sha256_file
from src.ingestion.scan_local_archives import run_scan_pipeline
from src.parsing.parse_demos import run_parse_pipeline
from src.parsing.parse_quality import run_quality_pipeline
from src.parsing.probe_dem_metadata import run_probe_pipeline
from src.storage.migrate_silver_ticks import content_fingerprint
from src.storage.scoped_gold import GOLD_DATASET_SPECS
from src.storage.silver_tables import silver_partition_files
from src.teams.build_team_dictionary import run_team_dictionary_pipeline
from src.utils.io import ensure_dir, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.text import safe_slug


AUDIT_NAME = "mirage_operational_run_audit"
FINGERPRINT_NAME = "mirage_operational_dataset_fingerprints"
RECOVERY_NAME = "mirage_retention_recovery_audit"
COMPARISON_NAME = "mirage_idempotence_comparison"

VOLATILE_COLUMNS = {
    "completed_at",
    "created_at",
    "evaluated_at",
    "extracted_at",
    "parsed_at",
    "probed_at",
    "scanned_at",
    "started_at",
}


@dataclass(frozen=True)
class DatasetSpec:
    dataset_name: str
    paths: tuple[Path, ...]
    key_columns: tuple[str, ...] = ()
    required: bool = True


def run_mirage_operational_validation(
    config_path: Path,
    *,
    run_id: str | None = None,
    source_archive_dir: Path | None = None,
    feature_contract_path: Path | None = None,
    cleanup_run_root: bool = False,
    force_evidence: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project_root = config_path.resolve().parent.parent
    project = load_project_config(config_path)
    target_map = project.target_maps[0]
    target_team = project.target_teams[0]
    run_id = run_id or datetime.now(timezone.utc).strftime("mirage_clean_room_%Y%m%dt%H%M%Sz")
    validate_run_id(run_id)

    validation_root = project_root / "data" / "validation_runs"
    run_root = validation_root / run_id
    source_archive_dir = source_archive_dir or resolve_path(project_root, project.demo_archive_dir) / target_team / target_map
    feature_contract_path = feature_contract_path or (
        project_root / "data" / "gold" / "features" / "feature_contract" / "feature_contract.parquet"
    )
    output_dir = operational_output_dir(project_root)
    evidence_paths = [output_dir / f"{name}.parquet" for name in (AUDIT_NAME, FINGERPRINT_NAME, RECOVERY_NAME, COMPARISON_NAME)]

    plan = {
        "run_id": run_id,
        "run_root": str(run_root),
        "source_archive_dir": str(source_archive_dir.resolve()),
        "feature_contract_path": str(feature_contract_path.resolve()),
        "output_dir": str(output_dir),
        "cleanup_run_root": cleanup_run_root,
    }
    if dry_run:
        audit = pd.DataFrame([{**plan, "status": "dry_run"}])
        return {AUDIT_NAME: audit}, {}, {**plan, "status": "dry_run"}

    if run_root.exists():
        raise FileExistsError(f"Clean-room run root already exists: {run_root}")
    if not source_archive_dir.exists():
        raise FileNotFoundError(f"Source archive directory does not exist: {source_archive_dir}")
    if not feature_contract_path.exists():
        raise FileNotFoundError(f"Frozen feature contract does not exist: {feature_contract_path}")
    existing_evidence = [path for path in evidence_paths if path.exists()]
    if existing_evidence and not force_evidence:
        raise FileExistsError(f"Operational evidence already exists: {existing_evidence}. Use --force-evidence after review.")

    started_at = datetime.now(timezone.utc).isoformat()
    print(f"[operational] preparing isolated root: {run_root}", flush=True)
    isolated_config = prepare_isolated_project(project_root, config_path, run_root)

    first = execute_archive_to_gold(
        isolated_config,
        source_archive_dir=source_archive_dir.resolve(),
        feature_contract_path=feature_contract_path.resolve(),
        target_map=target_map,
        target_team=target_team,
        pass_name="first",
    )
    first_fingerprints = capture_operational_fingerprints(run_root, isolated_config, pass_name="first")
    recovery = run_retention_recovery(first["dem_manifest"], run_root=run_root, run_id=run_id)

    second = execute_archive_to_gold(
        isolated_config,
        source_archive_dir=source_archive_dir.resolve(),
        feature_contract_path=feature_contract_path.resolve(),
        target_map=target_map,
        target_team=target_team,
        pass_name="second",
    )
    second_fingerprints = capture_operational_fingerprints(run_root, isolated_config, pass_name="second")
    fingerprints = pd.concat([first_fingerprints, second_fingerprints], ignore_index=True)
    comparison = compare_fingerprints(first_fingerprints, second_fingerprints)

    contract = load_yaml(project_root / "configs" / "quality" / "mirage_consolidation.yaml")
    minimum_demos = int(contract.get("thresholds", {}).get("minimum_valid_full_map_demos", 1))
    valid_demos = int(second["quality_summary"].get("valid_full_map", 0))
    if not valid_demos:
        valid_demos = int(
            second["quality"].get("quality_status", pd.Series(dtype=str)).astype(str).eq("valid_full_map").sum()
        )
    role_status = role_audit_status(second["role_frames"])
    required_present = bool(first_fingerprints["present"].all() and second_fingerprints["present"].all())
    clean_room_passed = bool(
        first["archive_count"] > 0
        and first["eligible_demos"] >= minimum_demos
        and valid_demos >= minimum_demos
        and first["rounds"] > 0
        and role_status == "passed"
        and required_present
    )
    idempotent_passed = bool(
        not comparison.empty
        and comparison["unchanged"].all()
        and comparison["duplicate_keys_after"].fillna(0).eq(0).all()
        and comparison["null_keys_after"].fillna(0).eq(0).all()
    )
    recovery_passed = bool(recovery.iloc[0]["status"] == "passed")
    overall_passed = clean_room_passed and idempotent_passed and recovery_passed

    cleanup_completed = False
    if cleanup_run_root:
        print(f"[operational] removing disposable derived root: {run_root}", flush=True)
        remove_isolated_run_root(run_root, validation_root=validation_root, run_id=run_id)
        cleanup_completed = not run_root.exists()

    completed_at = datetime.now(timezone.utc).isoformat()
    audit = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "status": "passed" if overall_passed else "failed",
                "clean_room_rebuild_passed": clean_room_passed,
                "idempotent_rerun_passed": idempotent_passed,
                "retention_recovery_passed": recovery_passed,
                "run_root": str(run_root),
                "run_root_was_empty": True,
                "run_root_retained": run_root.exists(),
                "cleanup_requested": cleanup_run_root,
                "cleanup_completed": cleanup_completed,
                "source_archive_dir": str(source_archive_dir.resolve()),
                "source_archives": int(second["archive_count"]),
                "extracted_dems": int(second["extracted_dems"]),
                "parse_eligible_demos": int(second["eligible_demos"]),
                "valid_full_map_demos": valid_demos,
                "rounds_generated": int(second["rounds"]),
                "fingerprinted_datasets": len(second_fingerprints),
                "fingerprint_mismatches": int((~comparison["unchanged"]).sum()),
                "duplicate_key_failures": int(comparison["duplicate_keys_after"].fillna(0).gt(0).sum()),
                "null_key_failures": int(comparison["null_keys_after"].fillna(0).gt(0).sum()),
                "role_feature_status": role_status,
                "started_at": started_at,
                "completed_at": completed_at,
                "notes": (
                    "Two archive-to-Gold passes ran in an isolated derived-data root; logical fingerprints exclude "
                    "execution timestamps. The retained archive recovered a deliberately removed isolated DEM."
                ),
            }
        ]
    )
    frames = {
        AUDIT_NAME: audit,
        FINGERPRINT_NAME: fingerprints,
        RECOVERY_NAME: recovery,
        COMPARISON_NAME: comparison,
    }
    outputs = write_dataframe_outputs(frames, output_dir, force=True, formats=tuple(project.output_formats))
    result = {
        "run_id": run_id,
        "status": audit.iloc[0]["status"],
        "clean_room_rebuild_passed": clean_room_passed,
        "idempotent_rerun_passed": idempotent_passed,
        "retention_recovery_passed": recovery_passed,
        "fingerprint_mismatches": int((~comparison["unchanged"]).sum()),
        "cleanup_completed": cleanup_completed,
    }
    print(f"[operational] completed: {json.dumps(result, sort_keys=True)}", flush=True)
    return frames, outputs, result


def prepare_isolated_project(project_root: Path, config_path: Path, run_root: Path) -> Path:
    if run_root.exists():
        raise FileExistsError(f"Refusing to prepare a non-empty clean-room root: {run_root}")
    ensure_dir(run_root)
    shutil.copytree(project_root / "configs", run_root / "configs")
    project_data = load_yaml(config_path)
    data_root = run_root / "data"
    rewritten = {
        "manual_seed_path": data_root / "raw" / "manual" / "matches_seed.csv",
        "hltv_cache_dir": data_root / "raw" / "hltv_pages",
        "match_discovery_manifest_dir": data_root / "bronze" / "match_discovery_manifest",
        "bronze_output_dir": data_root / "bronze" / "match_catalog_raw",
        "silver_output_dir": data_root / "silver" / "matches_catalog",
        "demo_output_dir": data_root / "raw" / "demos",
        "demo_manifest_dir": data_root / "bronze" / "demo_manifest",
        "demo_manifest_path": data_root / "bronze" / "demo_manifest" / "demo_manifest.parquet",
        "local_archive_manifest_dir": data_root / "bronze" / "local_archive_manifest",
        "dem_files_manifest_dir": data_root / "bronze" / "dem_files_manifest",
        "dem_files_manifest_path": data_root / "bronze" / "dem_files_manifest" / "dem_files_manifest.parquet",
        "parsed_bronze_dir": data_root / "bronze" / "parsed_demos",
        "parsed_silver_dir": data_root / "silver" / "parsed_demos",
        "parse_manifest_dir": data_root / "bronze" / "parse_manifest",
        "role_feature_output_dir": data_root / "gold" / "features" / "role_aware",
        "player_rosters_path": run_root / "configs" / "player_rosters.yaml",
        "team_registry_path": run_root / "configs" / "player_rosters.yaml",
        "timing_config_path": run_root / "configs" / "timing.yaml",
    }
    for key, value in rewritten.items():
        project_data[key] = str(value.resolve())
    isolated_config = run_root / "configs" / "project.yaml"
    isolated_config.write_text(yaml.safe_dump(project_data, sort_keys=False, allow_unicode=False), encoding="utf-8")
    return isolated_config


def execute_archive_to_gold(
    config_path: Path,
    *,
    source_archive_dir: Path,
    feature_contract_path: Path,
    target_map: str,
    target_team: str,
    pass_name: str,
) -> dict[str, Any]:
    print(f"[operational:{pass_name}] scan and extract", flush=True)
    local_manifest, dem_manifest, _, scan_summary = run_scan_pipeline(
        config_path,
        input_dir=source_archive_dir,
        target_team=target_team,
        assumed_map=target_map,
        extract=True,
        force=True,
    )
    print(f"[operational:{pass_name}] probe map metadata", flush=True)
    dem_manifest, _, _ = run_probe_pipeline(config_path, force=True, include_known=True)
    print(f"[operational:{pass_name}] parse Mirage demos", flush=True)
    _, _, parse_summary = run_parse_pipeline(
        config_path,
        force=True,
        target_maps=[target_map],
        target_team=target_team,
    )
    print(f"[operational:{pass_name}] quality gate", flush=True)
    quality, eligible, _, quality_summary = run_quality_pipeline(
        config_path,
        force=True,
        target_maps=[target_map],
        target_team=target_team,
    )
    print(f"[operational:{pass_name}] Gold features and resolved state", flush=True)
    run_team_dictionary_pipeline(config_path, force=True)
    round_features, _, feature_summary = run_feature_pipeline(
        config_path,
        force=True,
        target_map=target_map,
        target_team=target_team,
        feature_contract_path=feature_contract_path,
    )
    run_round_state_pipeline(config_path, force=True, target_map=target_map, target_team=target_team)
    round_features, _, feature_summary = run_feature_pipeline(
        config_path,
        force=True,
        target_map=target_map,
        target_team=target_team,
        feature_contract_path=feature_contract_path,
    )
    run_round_state_pipeline(config_path, force=True, target_map=target_map, target_team=target_team)
    run_side_dataset_pipeline(config_path, force=True, target_map=target_map, target_team=target_team)
    role_frames, _, _ = run_role_feature_pipeline(
        config_path,
        force=True,
        target_map=target_map,
        target_team=target_team,
    )
    return {
        "local_manifest": local_manifest,
        "dem_manifest": dem_manifest,
        "quality": quality,
        "role_frames": role_frames,
        "archive_count": int(scan_summary.get("total_archives", len(local_manifest))),
        "extracted_dems": len(dem_manifest),
        "eligible_demos": len(eligible),
        "rounds": len(round_features),
        "parse_summary": parse_summary,
        "quality_summary": quality_summary,
        "feature_summary": feature_summary,
    }


def capture_operational_fingerprints(run_root: Path, config_path: Path, *, pass_name: str) -> pd.DataFrame:
    print(f"[operational:{pass_name}] fingerprint core datasets", flush=True)
    specs = operational_dataset_specs(run_root, config_path)
    rows = [fingerprint_dataset(spec, pass_name=pass_name) for spec in specs]
    return pd.DataFrame(rows)


def operational_dataset_specs(run_root: Path, config_path: Path) -> list[DatasetSpec]:
    project = load_project_config(config_path)
    silver = project.parsed_silver_dir
    bronze = run_root / "data" / "bronze"
    gold = run_root / "data" / "gold"
    specs = [
        DatasetSpec("local_archive_manifest", (project.local_archive_manifest_dir / "local_archive_manifest.parquet",), ("local_archive_id",)),
        DatasetSpec("dem_files_manifest", (project.dem_files_manifest_path,), ("dem_file_id",)),
        DatasetSpec("parse_manifest", (project.parse_manifest_dir / "parse_manifest.parquet",), ("parse_id",)),
        DatasetSpec("parse_quality", (bronze / "parse_quality" / "parse_quality.parquet",), ("parse_id",)),
        DatasetSpec("feature_eligible_demos", (silver / "feature_eligible_demos.parquet",), ("parse_id",)),
    ]
    for table_name in project.parse_tables:
        if table_name == "ticks":
            paths = tuple(silver_partition_files(silver, "ticks"))
        else:
            paths = (silver / f"{table_name}.parquet",)
        specs.append(DatasetSpec(f"silver_{table_name}", paths, required=True))
    for spec in GOLD_DATASET_SPECS.values():
        specs.append(
            DatasetSpec(
                f"gold_{spec.dataset_name}",
                ((gold / spec.relative_path).with_suffix(".parquet"),),
                spec.key_columns,
                required=spec.critical,
            )
        )
    role_root = gold / "features" / "role_aware"
    for name in (
        "round_role_features",
        "round_attack_features",
        "round_defense_features",
        "round_target_team_features",
        "round_map_features",
    ):
        specs.append(DatasetSpec(f"role_{name}", (role_root / f"{name}.parquet",), ("round_feature_id",)))
    return specs


def fingerprint_dataset(spec: DatasetSpec, *, pass_name: str) -> dict[str, Any]:
    paths = tuple(path for path in spec.paths if path.exists())
    if not paths:
        return {
            "pass_name": pass_name,
            "dataset_name": spec.dataset_name,
            "present": False,
            "required": spec.required,
            "file_count": 0,
            "row_count": 0,
            "schema_hash": None,
            "content_fingerprint": None,
            "key_columns": "|".join(spec.key_columns),
            "duplicate_keys": None,
            "null_keys": None,
            "paths": "",
        }
    scan = pl.scan_parquet([str(path) for path in paths])
    schema = scan.collect_schema()
    logical_columns = [name for name in schema.names() if not is_volatile_column(name)]
    logical_scan = scan.select(logical_columns)
    schema_payload = [(name, str(schema[name])) for name in logical_columns]
    rows = int(logical_scan.select(pl.len()).collect(engine="streaming").item())
    keys = [key for key in spec.key_columns if key in logical_columns]
    duplicate_keys: int | None = None
    null_keys: int | None = None
    if keys:
        duplicate_keys = int(
            logical_scan.group_by(keys)
            .agg(pl.len().alias("_rows"))
            .filter(pl.col("_rows") > 1)
            .select(pl.len())
            .collect(engine="streaming")
            .item()
        )
        null_expression = pl.any_horizontal([pl.col(key).is_null() for key in keys])
        null_keys = int(logical_scan.filter(null_expression).select(pl.len()).collect(engine="streaming").item())
    return {
        "pass_name": pass_name,
        "dataset_name": spec.dataset_name,
        "present": True,
        "required": spec.required,
        "file_count": len(paths),
        "row_count": rows,
        "schema_hash": hashlib.sha256(json.dumps(schema_payload).encode("utf-8")).hexdigest(),
        "content_fingerprint": content_fingerprint(logical_scan),
        "key_columns": "|".join(spec.key_columns),
        "duplicate_keys": duplicate_keys,
        "null_keys": null_keys,
        "paths": "|".join(str(path) for path in paths),
    }


def compare_fingerprints(first: pd.DataFrame, second: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "dataset_name",
        "present",
        "file_count",
        "row_count",
        "schema_hash",
        "content_fingerprint",
        "duplicate_keys",
        "null_keys",
    ]
    merged = first[columns].merge(second[columns], on="dataset_name", suffixes=("_before", "_after"), how="outer")
    merged["present_unchanged"] = merged["present_before"].eq(merged["present_after"]) & merged["present_after"].fillna(False)
    merged["file_count_unchanged"] = merged["file_count_before"].eq(merged["file_count_after"])
    merged["row_count_unchanged"] = merged["row_count_before"].eq(merged["row_count_after"])
    merged["schema_unchanged"] = merged["schema_hash_before"].eq(merged["schema_hash_after"])
    merged["content_unchanged"] = merged["content_fingerprint_before"].eq(merged["content_fingerprint_after"])
    merged["unchanged"] = merged[
        ["present_unchanged", "file_count_unchanged", "row_count_unchanged", "schema_unchanged", "content_unchanged"]
    ].all(axis=1)
    return merged.sort_values("dataset_name").reset_index(drop=True)


def run_retention_recovery(dem_manifest: pd.DataFrame, *, run_root: Path, run_id: str) -> pd.DataFrame:
    candidates = dem_manifest.copy()
    if "is_merged_demo" in candidates.columns:
        candidates = candidates[~candidates["is_merged_demo"].map(as_bool)]
    candidates = candidates[candidates.get("parse_eligible", pd.Series(False, index=candidates.index)).map(as_bool)]
    candidates = candidates[
        candidates.get("dem_path", pd.Series(dtype=str)).map(lambda value: Path(str(value)).exists())
        & candidates.get("archive_path", pd.Series(dtype=str)).map(lambda value: Path(str(value)).exists())
    ]
    if candidates.empty:
        raise RuntimeError("No isolated, archive-backed eligible DEM is available for the retention recovery test.")
    row = candidates.sort_values([column for column in ("local_archive_id", "dem_file_id") if column in candidates.columns]).iloc[0]
    demo_path = Path(str(row["dem_path"])).resolve()
    archive_path = Path(str(row["archive_path"])).resolve()
    ensure_within(demo_path, run_root)
    expected_hash = str(row.get("dem_sha256") or sha256_file(demo_path))
    before_hash = sha256_file(demo_path)
    before_size = demo_path.stat().st_size
    archive_hash = sha256_file(archive_path)
    demo_path.unlink()
    missing_after_delete = not demo_path.exists()
    result = ArchiveExtractor().extract(
        archive_path,
        demo_path.parent,
        str(row["local_archive_id"]),
        force=False,
    )
    recovered = demo_path.exists()
    after_hash = sha256_file(demo_path) if recovered else None
    after_size = demo_path.stat().st_size if recovered else None
    passed = bool(
        missing_after_delete
        and recovered
        and before_hash == expected_hash == after_hash
        and before_size == after_size
        and result.status in {"extracted", "skipped_existing", "not_needed"}
    )
    return pd.DataFrame(
        [
            {
                "run_id": run_id,
                "status": "passed" if passed else "failed",
                "archive_path": str(archive_path),
                "archive_sha256": archive_hash,
                "dem_path": str(demo_path),
                "dem_file_id": row.get("dem_file_id"),
                "expected_dem_sha256": expected_hash,
                "before_dem_sha256": before_hash,
                "recovered_dem_sha256": after_hash,
                "before_size_bytes": before_size,
                "recovered_size_bytes": after_size,
                "missing_after_delete": missing_after_delete,
                "extract_status": result.status,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "notes": "Only the disposable clean-room DEM was removed; the retained source archive was never modified.",
            }
        ]
    )


def role_audit_status(frames: dict[str, pd.DataFrame]) -> str:
    audit = frames.get("role_feature_audit", pd.DataFrame())
    return str(audit.iloc[-1].get("status") or "missing").casefold() if not audit.empty else "missing"


def is_volatile_column(column: str) -> bool:
    name = column.casefold()
    return name in VOLATILE_COLUMNS or name.endswith("_at")


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def validate_run_id(run_id: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,79}", run_id) or safe_slug(run_id) != run_id:
        raise ValueError("run_id must be a lowercase safe slug between 3 and 80 characters.")


def ensure_within(path: Path, root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise ValueError(f"Path is outside the isolated run root: {resolved_path}")


def remove_isolated_run_root(run_root: Path, *, validation_root: Path, run_id: str) -> None:
    resolved_root = run_root.resolve()
    resolved_parent = validation_root.resolve()
    if resolved_root.parent != resolved_parent or resolved_root.name != run_id:
        raise ValueError(f"Refusing to remove unexpected validation root: {resolved_root}")
    if run_root.exists():
        shutil.rmtree(run_root)


def operational_output_dir(project_root: Path) -> Path:
    storage = load_yaml(project_root / "configs" / "storage.yaml")
    return resolve_path(project_root, Path(storage["audit"]["operational_runs"]))


def resolve_path(project_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else project_root / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated Mirage rebuild, idempotence, and recovery validation.")
    parser.add_argument("--config", type=Path, default=Path("configs/project.yaml"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--source-archive-dir", type=Path, default=None)
    parser.add_argument("--feature-contract", type=Path, default=None)
    parser.add_argument("--cleanup-run-root", action="store_true")
    parser.add_argument("--force-evidence", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, result = run_mirage_operational_validation(
        args.config,
        run_id=args.run_id,
        source_archive_dir=args.source_archive_dir,
        feature_contract_path=args.feature_contract,
        cleanup_run_root=args.cleanup_run_root,
        force_evidence=args.force_evidence,
        dry_run=args.dry_run,
    )
    print({**result, "outputs": {key: str(value) for key, value in outputs.items()}})


if __name__ == "__main__":
    main()
