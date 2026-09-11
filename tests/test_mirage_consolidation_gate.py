from pathlib import Path

import pandas as pd

from src.validation.mirage_consolidation_gate import (
    ConsolidationContext,
    check_declared_evidence,
    check_downloader_orchestration,
    check_inventory_reconciliation,
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
