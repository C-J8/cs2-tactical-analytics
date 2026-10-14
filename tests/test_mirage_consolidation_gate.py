import hashlib
from pathlib import Path

import pandas as pd

from src.validation.mirage_consolidation_gate import (
    ConsolidationContext,
    check_declared_evidence,
    check_downloader_orchestration,
    check_inventory_reconciliation,
    check_operational_evidence,
    check_partitioned_silver,
    check_storage_contract,
    summarize_checks,
)


class ProjectStub:
    demo_output_dir = Path("data/raw/demos")


class RegistryStub:
    map_id = "mirage"
    display_name = "Mirage"


def context(
    tmp_path: Path,
    *,
    evidence: dict | None = None,
    contract: dict | None = None,
) -> ConsolidationContext:
    return ConsolidationContext(
        project_root=tmp_path,
        project=ProjectStub(),  # type: ignore[arg-type]
        contract=contract
        or {"contract_id": "mirage_consolidation", "contract_version": "v1", "paths": {"demo_manifest": "manifest"}},
        evidence=evidence or {},
        map_id="mirage",
        map_name="Mirage",
        target_team="Vitality",
        registry=RegistryStub(),  # type: ignore[arg-type]
    )


def test_inventory_reconciliation_detects_orphan_demo(tmp_path: Path) -> None:
    demo_root = tmp_path / "data" / "raw" / "demos"
    demo_root.mkdir(parents=True)
    cataloged = demo_root / "cataloged.dem"
    orphan = demo_root / "orphan.dem"
    cataloged.write_bytes(b"cataloged")
    orphan.write_bytes(b"orphan")
    manifest = pd.DataFrame([{"dem_path": str(cataloged)}])

    row = check_inventory_reconciliation(context(tmp_path), manifest)

    assert row["status"] == "failed"
    assert '"orphan_dems": 1' in row["observed"]


def test_pending_manual_evidence_is_blocking() -> None:
    ctx = context(Path("."), evidence={"manual_region_review": {"status": "pending"}})

    row = check_declared_evidence(ctx, "manual_region_review", "map", "review")

    assert row["status"] == "pending"
    assert row["blocking"]


def test_manual_evidence_cannot_pass_without_review_details() -> None:
    ctx = context(
        Path("."),
        evidence={
            "manual_region_review": {
                "status": "passed",
                "reviewer": None,
                "reviewed_at": None,
                "reviewed_regions": [],
            }
        },
    )

    row = check_declared_evidence(ctx, "manual_region_review", "map", "review")

    assert row["status"] == "failed"
    assert '"reviewed_regions"' in row["observed"]


def test_operational_evidence_requires_matching_passed_audit(tmp_path: Path) -> None:
    audit_base = tmp_path / "audit" / "mirage_operational_run_audit"
    audit_base.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "run_id": "run_001",
                "status": "passed",
                "clean_room_rebuild_passed": True,
                "completed_at": "2026-09-13T10:00:00+00:00",
            }
        ]
    ).to_parquet(audit_base.with_suffix(".parquet"), index=False)
    ctx = context(
        tmp_path,
        evidence={
            "clean_room_rebuild": {
                "status": "passed",
                "run_id": "run_001",
                "completed_at": "2026-09-13T10:00:00+00:00",
            }
        },
        contract={
            "contract_id": "mirage_consolidation",
            "contract_version": "v1",
            "paths": {"operational_audit": "audit/mirage_operational_run_audit"},
        },
    )

    row = check_operational_evidence(
        ctx,
        "clean_room_rebuild",
        "clean_room_rebuild_passed",
        "orchestration",
        "clean room",
    )

    assert row["status"] == "passed"


def test_operational_evidence_rejects_yaml_only_claim(tmp_path: Path) -> None:
    ctx = context(
        tmp_path,
        evidence={
            "clean_room_rebuild": {
                "status": "passed",
                "run_id": "run_001",
                "completed_at": "2026-09-13T10:00:00+00:00",
            }
        },
        contract={
            "contract_id": "mirage_consolidation",
            "contract_version": "v1",
            "paths": {"operational_audit": "audit/mirage_operational_run_audit"},
        },
    )

    row = check_operational_evidence(
        ctx,
        "clean_room_rebuild",
        "clean_room_rebuild_passed",
        "orchestration",
        "clean room",
    )

    assert row["status"] == "failed"


def test_downloader_orchestration_requires_archive_only_stage_order(tmp_path: Path) -> None:
    dag_path = tmp_path / "dag.py"
    downloader_path = tmp_path / "download.py"
    dag_path.write_text(
        'module = "src.ingestion.download_demos"\nargs = ["--require-ready"]\n'
        "build_catalog >> download_archives >> scan_archives\n",
        encoding="utf-8",
    )
    downloader_path.write_text('field = "archive_ready_for_scan"\n', encoding="utf-8")
    ctx = context(
        tmp_path,
        contract={
            "contract_id": "mirage_consolidation",
            "contract_version": "v1",
            "paths": {"ingestion_dag": "dag.py", "downloader_module": "download.py"},
            "orchestration": {"required_download_module": "src.ingestion.download_demos"},
        },
    )

    row = check_downloader_orchestration(ctx)

    assert row["status"] == "passed"


def test_summary_requires_every_blocking_check_to_pass(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    checks = pd.DataFrame(
        [
            {"check_id": "passed", "blocking": True, "status": "passed"},
            {"check_id": "pending", "blocking": True, "status": "pending"},
            {"check_id": "warning", "blocking": False, "status": "failed"},
        ]
    )

    summary = summarize_checks(checks, ctx).iloc[0]

    assert summary["status"] == "not_consolidated"
    assert summary["blocking_open"] == 1
    assert summary["warnings"] == 1
    assert summary["next_blocker"] == "pending"


def test_storage_contract_requires_recovery_and_partition_safety(tmp_path: Path) -> None:
    storage = tmp_path / "storage.yaml"
    storage.write_text(
        """
storage_version: v1
roots:
  raw: raw
  bronze: bronze
  silver: silver
  gold: gold
  source_archives: archives
  extracted_demos: demos
  quarantine: quarantine
partitioning:
  silver_ticks:
    logical_partition_key: source_parse_id
    atomic_promotion: true
retention:
  source_archives: {policy: retain}
  extracted_demos: {policy: cache}
  bronze: {policy: retain}
  silver_gold: {policy: rebuildable}
  quarantine: {policy: review}
safety:
  never_delete_last_recovery_source: true
""",
        encoding="utf-8",
    )
    ctx = context(
        tmp_path,
        contract={
            "contract_id": "mirage_consolidation",
            "contract_version": "v1",
            "paths": {"storage_contract": "storage.yaml"},
        },
    )

    row = check_storage_contract(ctx)

    assert row["status"] == "passed"


def test_partition_gate_rejects_self_certified_existing_dataset(tmp_path: Path) -> None:
    partition = tmp_path / "data/silver/parsed_demos/table=ticks/target_team=vitality/map_id=mirage/parse-a.parquet"
    partition.parent.mkdir(parents=True)
    partition.write_bytes(b"partition")
    audit_base = tmp_path / "data/gold/validation/silver_ticks_migration/silver_ticks_migration_audit"
    audit_base.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "status": "already_partitioned",
                "source_rows": 1,
                "partition_rows": 1,
                "schema_match": True,
                "per_parse_count_match": True,
                "content_fingerprint_match": True,
            }
        ]
    ).to_parquet(audit_base.with_suffix(".parquet"), index=False)
    ctx = context(
        tmp_path,
        contract={
            "contract_id": "mirage_consolidation",
            "contract_version": "v1",
            "paths": {
                "silver_ticks_monolith": "data/silver/parsed_demos/ticks.parquet",
                "silver_ticks_partition_glob": "data/silver/parsed_demos/table=ticks/**/*.parquet",
                "silver_ticks_migration_audit": str(audit_base.relative_to(tmp_path)),
            },
        },
    )

    row = check_partitioned_silver(ctx)

    assert row["status"] == "failed"


def test_partition_gate_requires_and_validates_rollback_hash(tmp_path: Path) -> None:
    partition = tmp_path / "data/silver/parsed_demos/table=ticks/target_team=vitality/map_id=mirage/parse-a.parquet"
    partition.parent.mkdir(parents=True)
    partition.write_bytes(b"partition")
    rollback = tmp_path / "data/raw/quarantine/storage_migrations/run/ticks.parquet"
    rollback.parent.mkdir(parents=True)
    rollback.write_bytes(b"rollback")
    rollback_hash = hashlib.sha256(b"rollback").hexdigest()
    audit_base = tmp_path / "data/gold/validation/silver_ticks_migration/silver_ticks_migration_audit"
    audit_base.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "status": "passed",
                "source_rows": 1,
                "partition_rows": 1,
                "schema_match": True,
                "per_parse_count_match": True,
                "content_fingerprint_match": True,
                "rollback_path": str(rollback),
                "source_sha256": rollback_hash,
                "rollback_sha256": rollback_hash,
                "rollback_hash_match": True,
            }
        ]
    ).to_parquet(audit_base.with_suffix(".parquet"), index=False)
    ctx = context(
        tmp_path,
        contract={
            "contract_id": "mirage_consolidation",
            "contract_version": "v1",
            "paths": {
                "silver_ticks_monolith": "data/silver/parsed_demos/ticks.parquet",
                "silver_ticks_partition_glob": "data/silver/parsed_demos/table=ticks/**/*.parquet",
                "silver_ticks_migration_audit": str(audit_base.relative_to(tmp_path)),
            },
        },
    )

    row = check_partitioned_silver(ctx)

    assert row["status"] == "passed"
