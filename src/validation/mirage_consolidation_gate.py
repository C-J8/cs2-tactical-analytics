from __future__ import annotations

import argparse
import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.config.schemas import ProjectConfig, load_project_config
from src.ingestion.demo_downloader import sha256_file
from src.maps.registry import MapRegistry, load_map_registry, normalize_id
from src.utils.io import read_table, write_dataframe_outputs
from src.utils.logging import configure_logging
from src.utils.reports import markdown_table, now_utc


CHECK_COLUMNS = [
    "check_id",
    "category",
    "description",
    "evaluation",
    "blocking",
    "status",
    "observed",
    "expected",
    "evidence",
    "remediation",
]


@dataclass(frozen=True)
class ConsolidationContext:
    project_root: Path
    project: ProjectConfig
    contract: dict[str, Any]
    evidence: dict[str, Any]
    map_id: str
    map_name: str
    target_team: str
    registry: MapRegistry


def run_mirage_consolidation_gate(
    config_path: Path,
    *,
    contract_path: Path = Path("configs/quality/mirage_consolidation.yaml"),
    evidence_path: Path = Path("configs/quality/mirage_consolidation_evidence.yaml"),
    project_root: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project_root = project_root or config_path.resolve().parent.parent
    project = load_project_config(config_path)
    contract = load_yaml(resolve_path(project_root, contract_path))
    evidence = load_yaml(resolve_path(project_root, evidence_path))
    target_map = str(contract.get("target_map") or "Mirage")
    target_team = str(contract.get("target_team") or project.target_teams[0])
    registry_path = resolve_path(project_root, Path(contract["paths"]["map_registry"]))
    registry = load_map_registry(target_map, registry_path=registry_path)
    ctx = ConsolidationContext(
        project_root=project_root,
        project=project,
        contract=contract,
        evidence=evidence,
        map_id=registry.map_id,
        map_name=registry.display_name,
        target_team=target_team,
        registry=registry,
    )

    parse_quality = read_optional_table_pair(project_root, contract["paths"]["parse_quality"])
    demo_manifest = read_optional_table_pair(project_root, contract["paths"]["demo_manifest"])
    scoped_quality = scope_map_team(parse_quality, ctx)
    valid_quality = scoped_quality[
        scoped_quality.get("quality_status", pd.Series(dtype=str)).astype(str).eq("valid_full_map")
        & scoped_quality.get("feature_eligible", pd.Series(dtype=object)).map(as_bool)
    ].copy()

    checks = pd.DataFrame(
        [
            check_registry(ctx),
            check_assets(ctx),
            check_valid_demos(ctx, valid_quality),
            check_inventory_reconciliation(ctx, demo_manifest),
            check_archive_recoverability(ctx, demo_manifest),
            check_timing(ctx, valid_quality),
            check_semantics(ctx),
            check_role_features(ctx),
            check_declared_evidence(ctx, "manual_region_review", "map", "Manual radar/nav region review approved."),
            check_grouped_validation(ctx),
            check_model_scope(ctx),
            check_regression_gate(ctx),
            check_team_provenance(ctx),
            check_downloader_orchestration(ctx),
            check_declared_evidence(ctx, "clean_room_rebuild", "orchestration", "Clean-room archive-to-Gold rebuild passed."),
            check_declared_evidence(ctx, "idempotent_rerun", "orchestration", "Identical rerun proved idempotent."),
            check_storage_contract(ctx),
            check_partitioned_silver(ctx),
            check_declared_evidence(ctx, "retention_recovery", "storage", "Archive-to-DEM recovery test passed."),
        ],
        columns=CHECK_COLUMNS,
    )
    summary = summarize_checks(checks, ctx)
    frames = {
        "mirage_consolidation_checks": checks,
        "mirage_consolidation_summary": summary,
    }
    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = resolve_path(project_root, Path(contract["output"]["directory"]))
        outputs = write_dataframe_outputs(frames, output_dir, force=force, formats=tuple(project.output_formats))
        outputs["report"] = write_report(
            checks,
            summary,
            resolve_path(project_root, Path(contract["output"]["report"])),
            force=force,
        )
    row = summary.iloc[0]
    result = {
        "contract_id": row["contract_id"],
        "map_id": row["map_id"],
        "target_team": row["target_team"],
        "checks": int(row["checks"]),
        "blocking_open": int(row["blocking_open"]),
        "warnings": int(row["warnings"]),
        "status": row["status"],
    }
    return frames, outputs, result


def check_registry(ctx: ConsolidationContext) -> dict[str, Any]:
    registry_path = resolve_path(ctx.project_root, Path(ctx.contract["paths"]["map_registry"]))
    registry_index = load_yaml(registry_path)
    entry = next(
        (
            item
            for item in registry_index.get("maps", [])
            if normalize_id(str(item.get("map_id") or "")) == ctx.map_id
        ),
        {},
    )
    registry_status = str(entry.get("status") or "missing").casefold()
    complete = bool(ctx.registry.physical_regions and ctx.registry.semantic_groups and ctx.registry.bombsites)
    return check_row(
        "map_registry_complete",
        "map",
        "Mirage registry contains physical regions, semantic groups, and bombsites.",
        passed=registry_status == "active" and complete,
        observed={
            "registry_status": registry_status,
            "physical_regions": len(ctx.registry.physical_regions),
            "semantic_groups": len(ctx.registry.semantic_groups),
            "bombsites": len(ctx.registry.bombsites),
        },
        expected="registry_status=active and all three inventories non-empty",
        evidence=f"{registry_path}; {ctx.registry.source_path or 'configs/maps/mirage.yaml'}",
        remediation="Complete and activate the Mirage map registry.",
    )


def check_assets(ctx: ConsolidationContext) -> dict[str, Any]:
    manifest_value = ctx.registry.assets.get("manifest")
    manifest_path = resolve_path(ctx.project_root, Path(str(manifest_value))) if manifest_value else None
    manifest = read_optional_table(manifest_path)
    verified = 0
    for _, row in manifest.iterrows():
        local_value = str(row.get("local_path") or "")
        local_path = resolve_path(ctx.project_root, Path(local_value)) if local_value else None
        expected_hash = str(row.get("sha256") or "")
        if local_path and local_path.exists() and expected_hash and sha256_file(local_path) == expected_hash:
            verified += 1
    passed = bool(len(manifest)) and verified == len(manifest)
    return check_row(
        "map_assets_verified",
        "map",
        "Every pinned Mirage asset exists and matches its SHA-256 manifest.",
        passed=passed,
        observed={"manifest_rows": len(manifest), "verified_assets": verified},
        expected="verified_assets == manifest_rows > 0",
        evidence=str(manifest_path or "missing asset manifest"),
        remediation="Run the Awpy asset synchronizer and review checksum failures.",
    )


def check_valid_demos(ctx: ConsolidationContext, valid_quality: pd.DataFrame) -> dict[str, Any]:
    minimum = int(ctx.contract["thresholds"]["minimum_valid_full_map_demos"])
    return check_row(
        "valid_full_map_demo_floor",
        "provenance",
        "The Mirage MVP has enough full-map demos for operational validation.",
        passed=len(valid_quality) >= minimum,
        observed=len(valid_quality),
        expected=f">= {minimum}",
        evidence=ctx.contract["paths"]["parse_quality"],
        remediation="Acquire and validate more complete Mirage demos.",
    )


def check_inventory_reconciliation(ctx: ConsolidationContext, manifest: pd.DataFrame) -> dict[str, Any]:
    demo_root = resolve_path(ctx.project_root, ctx.project.demo_output_dir)
    physical = {normalized_path(path, ctx.project_root) for path in demo_root.rglob("*.dem")} if demo_root.exists() else set()
    cataloged = {
        normalized_path(Path(str(value)), ctx.project_root)
        for value in manifest.get("dem_path", pd.Series(dtype=str))
        if str(value).strip()
    }
    orphan = sorted(physical - cataloged)
    missing = sorted(cataloged - physical)
    return check_row(
        "physical_demo_inventory_reconciled",
        "storage",
        "Every physical DEM is cataloged and every cataloged DEM exists.",
        passed=not orphan and not missing and bool(physical),
        observed={
            "physical_dems": len(physical),
            "cataloged_dems": len(cataloged),
            "orphan_dems": len(orphan),
            "missing_dems": len(missing),
            "orphan_examples": orphan[:5],
        },
        expected="orphan_dems=0 and missing_dems=0",
        evidence=ctx.contract["paths"]["demo_manifest"],
        remediation="Reconcile split/merged DEMs in the manifest before enabling retention.",
    )


def check_archive_recoverability(ctx: ConsolidationContext, manifest: pd.DataFrame) -> dict[str, Any]:
    scoped = scope_map_team(manifest, ctx, map_columns=("inferred_map_name", "assumed_map", "map_name"))
    archive_values = scoped.get("archive_path", pd.Series(dtype=str))
    recoverable = sum(
        1
        for value in archive_values
        if str(value).strip() and resolve_path(ctx.project_root, Path(str(value))).exists()
    )
    return check_row(
        "source_archives_recoverable",
        "provenance",
        "Every cataloged Mirage DEM has a retained source archive.",
        passed=bool(len(scoped)) and recoverable == len(scoped),
        observed={"scoped_dems": len(scoped), "recoverable": recoverable},
        expected="recoverable == scoped_dems > 0",
        evidence=ctx.contract["paths"]["demo_manifest"],
        remediation="Restore or quarantine DEMs whose source archive is unavailable.",
    )


def check_timing(ctx: ConsolidationContext, valid_quality: pd.DataFrame) -> dict[str, Any]:
    timing = read_optional_table_pair(ctx.project_root, ctx.contract["paths"]["timing_audit"])
    expected_ids = set(valid_quality.get("parse_id", pd.Series(dtype=str)).dropna().astype(str))
    scoped = timing[timing.get("parse_id", pd.Series(dtype=str)).astype(str).isin(expected_ids)].copy()
    consistent = int(scoped.get("timing_evidence_status", pd.Series(dtype=str)).astype(str).eq("consistent").sum())
    passed = bool(expected_ids) and set(scoped.get("parse_id", pd.Series(dtype=str)).astype(str)) == expected_ids
    passed = passed and consistent == len(scoped)
    return check_row(
        "timing_contract_validated",
        "features",
        "Every eligible Mirage demo resolves tickrate and has consistent freeze timing.",
        passed=passed,
        observed={"eligible_parse_ids": len(expected_ids), "consistent": consistent},
        expected="all eligible parse_ids consistent",
        evidence=ctx.contract["paths"]["timing_audit"],
        remediation="Resolve missing tickrates or investigate freeze-duration inconsistencies.",
    )


def check_semantics(ctx: ConsolidationContext) -> dict[str, Any]:
    required = {normalize_id(value) for value in ctx.contract.get("required_semantics", [])}
    available = set(ctx.registry.semantic_groups)
    missing = sorted(required - available)
    return check_row(
        "required_map_semantics_resolved",
        "map",
        "All tactical semantics required by the canonical feature engine exist in the Mirage registry.",
        passed=not missing and bool(required),
        observed={"required": sorted(required), "missing": missing},
        expected="missing=[]",
        evidence=str(ctx.registry.source_path or "configs/maps/mirage.yaml"),
        remediation="Map every required semantic to verified Mirage physical regions.",
    )


def check_role_features(ctx: ConsolidationContext) -> dict[str, Any]:
    audit = read_optional_table_pair(ctx.project_root, ctx.contract["paths"]["role_feature_audit"])
    scoped = audit[audit.get("map_id", pd.Series(dtype=str)).astype(str).eq(ctx.map_id)].copy()
    row = scoped.iloc[-1] if not scoped.empty else pd.Series(dtype=object)
    maximum = float(ctx.contract["thresholds"]["maximum_unknown_place_share"])
    unknown = numeric(row.get("unknown_place_share"))
    passed = str(row.get("status") or "").casefold() == "passed" and unknown is not None and unknown <= maximum
    return check_row(
        "canonical_role_features_passed",
        "features",
        "Canonical attack/defense features cover all scoped rounds within the unknown-place limit.",
        passed=passed,
        observed={"rounds": row.get("output_rounds"), "unknown_place_share": unknown, "status": row.get("status")},
        expected=f"status=passed and unknown_place_share <= {maximum}",
        evidence=ctx.contract["paths"]["role_feature_audit"],
        remediation="Repair round coverage, map aliases, or unresolved places.",
    )


def check_grouped_validation(ctx: ConsolidationContext) -> dict[str, Any]:
    audit = read_optional_table_pair(ctx.project_root, ctx.contract["paths"]["grouped_validation_audit"])
    row = audit.iloc[-1] if not audit.empty else pd.Series(dtype=object)
    minimum = int(ctx.contract["thresholds"]["minimum_grouped_series"])
    groups = int(numeric(row.get("unique_groups")) or 0)
    passed = (
        str(row.get("status") or "").casefold() == "passed"
        and as_bool(row.get("all_folds_group_isolated"))
        and int(numeric(row.get("group_overlap_count")) or 0) == 0
        and groups >= minimum
    )
    return check_row(
        "grouped_validation_isolated",
        "modeling",
        "Model validation isolates series and has enough groups for the MVP evidence claim.",
        passed=passed,
        observed={"groups": groups, "overlap": row.get("group_overlap_count"), "status": row.get("status")},
        expected=f"status=passed, overlap=0, groups >= {minimum}",
        evidence=ctx.contract["paths"]["grouped_validation_audit"],
        remediation="Rerun grouped validation or acquire more independent series.",
    )


def check_model_scope(ctx: ConsolidationContext) -> dict[str, Any]:
    contract = read_optional_table_pair(ctx.project_root, ctx.contract["paths"]["grouped_model_contract"])
    row = contract.iloc[-1] if not contract.empty else pd.Series(dtype=object)
    intended_use = str(row.get("intended_use") or "")
    limitations = str(row.get("known_limitations") or "")
    passed = bool(intended_use and limitations and "external validation" in limitations.casefold())
    return check_row(
        "model_scope_declared",
        "modeling",
        "The model contract states intended use and the absence of external validation.",
        passed=passed,
        observed={"intended_use": intended_use, "known_limitations": limitations},
        expected="non-empty intended use and external-validation limitation",
        evidence=ctx.contract["paths"]["grouped_model_contract"],
        remediation="Complete the model contract without promoting exploratory evidence.",
    )


def check_regression_gate(ctx: ConsolidationContext) -> dict[str, Any]:
    audit = read_optional_table_pair(ctx.project_root, ctx.contract["paths"]["regression_audit"])
    row = audit.iloc[-1] if not audit.empty else pd.Series(dtype=object)
    passed = str(row.get("status") or "").casefold() == "passed" and int(numeric(row.get("critical_failures")) or 0) == 0
    return check_row(
        "mirage_regression_governed",
        "governance",
        "The Mirage regression gate passes against an intentionally governed baseline.",
        passed=passed,
        observed={
            "status": row.get("status"),
            "critical_failures": row.get("critical_failures"),
            "baseline": row.get("baseline_version"),
        },
        expected="status=passed and critical_failures=0",
        evidence=ctx.contract["paths"]["regression_audit"],
        remediation="Review the known dataset drifts and renew or repair the baseline explicitly.",
    )


def check_team_provenance(ctx: ConsolidationContext) -> dict[str, Any]:
    audit = read_optional_table_pair(ctx.project_root, ctx.contract["paths"]["team_dictionary_audit"])
    row = audit.iloc[-1] if not audit.empty else pd.Series(dtype=object)
    unverified = int(numeric(row.get("unverified_memberships")) or 0)
    return check_row(
        "team_membership_provenance_verified",
        "governance",
        "Team memberships have verified sources and effective dates.",
        passed=not audit.empty and unverified == 0,
        blocking=False,
        observed={"unverified_memberships": unverified, "date_bounded": row.get("date_bounded_memberships")},
        expected="unverified_memberships=0",
        evidence=ctx.contract["paths"]["team_dictionary_audit"],
        remediation="Verify roster sources and membership dates before broad multi-team analysis.",
    )


def check_downloader_orchestration(ctx: ConsolidationContext) -> dict[str, Any]:
    dag_path = resolve_path(ctx.project_root, Path(ctx.contract["paths"]["ingestion_dag"]))
    required = str(ctx.contract["orchestration"]["required_download_module"])
    content = dag_path.read_text(encoding="utf-8") if dag_path.exists() else ""
    passed = required in content
    return check_row(
        "downloader_in_end_to_end_orchestration",
        "orchestration",
        "The canonical ingestion workflow includes the existing downloader before archive scanning.",
        passed=passed,
        observed={"dag_exists": dag_path.exists(), "download_module_referenced": passed},
        expected=f"DAG references {required}",
        evidence=str(dag_path),
        remediation="Insert catalog-driven demo acquisition into the canonical DAG/runner.",
    )


def check_storage_contract(ctx: ConsolidationContext) -> dict[str, Any]:
    path = resolve_path(ctx.project_root, Path(ctx.contract["paths"]["storage_contract"]))
    content = load_yaml(path) if path.exists() else {}
    passed = bool(content.get("storage_version") and content.get("roots") and content.get("retention"))
    return check_row(
        "storage_and_retention_contract_defined",
        "storage",
        "Storage roots, formats, partitioning, and retention are governed by configuration.",
        passed=passed,
        observed={"path_exists": path.exists(), "sections": sorted(content)},
        expected="storage_version, roots, and retention configured",
        evidence=str(path),
        remediation="Create the storage contract before moving or deleting any data.",
    )


def check_partitioned_silver(ctx: ConsolidationContext) -> dict[str, Any]:
    monolith = resolve_path(ctx.project_root, Path(ctx.contract["paths"]["silver_ticks_monolith"]))
    pattern = str(resolve_path(ctx.project_root, Path(ctx.contract["paths"]["silver_ticks_partition_glob"])))
    partitions = [Path(path) for path in glob.glob(pattern, recursive=True)]
    passed = bool(partitions) and not monolith.exists()
    return check_row(
        "silver_ticks_partitioned",
        "storage",
        "High-volume Silver ticks are a partitioned Parquet dataset, not one rewritten monolith.",
        passed=passed,
        observed={"monolith_exists": monolith.exists(), "partition_files": len(partitions)},
        expected="monolith absent and partition_files > 0",
        evidence=pattern,
        remediation="Migrate Silver ticks to partitioned Parquet and validate row/hash parity.",
    )


def check_declared_evidence(
    ctx: ConsolidationContext,
    evidence_id: str,
    category: str,
    description: str,
) -> dict[str, Any]:
    item = ctx.evidence.get(evidence_id) or {}
    status = str(item.get("status") or "pending").casefold()
    required_fields = (
        ("reviewer", "reviewed_at", "reviewed_regions")
        if evidence_id == "manual_region_review"
        else ("run_id", "completed_at")
    )
    missing_fields = [field for field in required_fields if not item.get(field)]
    observed = {**item, "missing_required_evidence": missing_fields}
    return check_row(
        evidence_id,
        category,
        description,
        passed=status == "passed" and not missing_fields,
        pending=status == "pending",
        evaluation="manual" if evidence_id == "manual_region_review" else "recorded_run",
        observed=observed,
        expected="status=passed with run/reviewer evidence",
        evidence="configs/quality/mirage_consolidation_evidence.yaml",
        remediation=str(item.get("notes") or "Produce and record the required evidence."),
    )


def summarize_checks(checks: pd.DataFrame, ctx: ConsolidationContext) -> pd.DataFrame:
    passed = checks["status"].eq("passed")
    blocking_open = checks["blocking"] & ~passed
    warnings = ~checks["blocking"] & ~passed
    status = "consolidated" if not blocking_open.any() else "not_consolidated"
    next_blocker = checks.loc[blocking_open, "check_id"].iloc[0] if blocking_open.any() else None
    return pd.DataFrame(
        [
            {
                "contract_id": ctx.contract.get("contract_id"),
                "contract_version": ctx.contract.get("contract_version"),
                "map_id": ctx.map_id,
                "map_name": ctx.map_name,
                "target_team": ctx.target_team,
                "checks": len(checks),
                "passed": int(passed.sum()),
                "blocking_open": int(blocking_open.sum()),
                "pending": int(checks["status"].eq("pending").sum()),
                "warnings": int(warnings.sum()),
                "completion_share": float(passed.mean()) if len(checks) else 0.0,
                "next_blocker": next_blocker,
                "ready_for_new_team_same_map": status == "consolidated",
                "ready_for_new_map_same_team": status == "consolidated",
                "status": status,
                "evaluated_at": now_utc(),
            }
        ]
    )


def check_row(
    check_id: str,
    category: str,
    description: str,
    *,
    passed: bool,
    observed: Any,
    expected: str,
    evidence: str,
    remediation: str,
    blocking: bool = True,
    pending: bool = False,
    evaluation: str = "automatic",
) -> dict[str, Any]:
    status = "passed" if passed else "pending" if pending else "failed"
    return {
        "check_id": check_id,
        "category": category,
        "description": description,
        "evaluation": evaluation,
        "blocking": blocking,
        "status": status,
        "observed": serialize(observed),
        "expected": expected,
        "evidence": evidence,
        "remediation": remediation,
    }


def scope_map_team(
    frame: pd.DataFrame,
    ctx: ConsolidationContext,
    *,
    map_columns: tuple[str, ...] = ("inferred_map_name", "map_name"),
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    scoped = frame.copy()
    if "target_team" in scoped.columns:
        scoped = scoped[scoped["target_team"].astype(str).str.casefold().eq(ctx.target_team.casefold())]
    map_column = next((column for column in map_columns if column in scoped.columns), None)
    if map_column:
        scoped = scoped[
            scoped[map_column].map(lambda value: normalize_id(str(value)).removeprefix("de_") == ctx.map_id)
        ]
    return scoped.reset_index(drop=True)


def read_optional_table_pair(project_root: Path, value: str) -> pd.DataFrame:
    path = resolve_path(project_root, Path(value))
    if path.suffix:
        return read_optional_table(path)
    for suffix in (".parquet", ".csv"):
        candidate = path.with_suffix(suffix)
        if candidate.exists():
            return read_table(candidate)
    return pd.DataFrame()


def read_optional_table(path: Path | None) -> pd.DataFrame:
    return read_table(path) if path and path.exists() else pd.DataFrame()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(content, dict):
        raise ValueError(f"Expected a YAML mapping: {path}")
    return content


def resolve_path(project_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else project_root / path


def normalized_path(path: Path, project_root: Path) -> str:
    resolved = path if path.is_absolute() else project_root / path
    return str(resolved.resolve(strict=False)).replace("/", "\\").casefold()


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}


def numeric(value: Any) -> float | None:
    try:
        return None if value is None or pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


def serialize(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def write_report(checks: pd.DataFrame, summary: pd.DataFrame, path: Path, *, force: bool) -> Path:
    if path.exists() and not force:
        raise FileExistsError(f"Report already exists: {path}. Use --force to overwrite it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    current = summary.iloc[0]
    blocking = checks[checks["blocking"] & checks["status"].ne("passed")]
    lines = [
        "# Status de consolidação do Mirage",
        "",
        "O Mirage só é considerado consolidado quando todos os critérios bloqueantes do contrato passam. Desempenho do modelo não substitui proveniência, reprodutibilidade, validação do mapa ou segurança de armazenamento.",
        "",
        "## Decisão atual",
        "",
        f"- Status: `{current['status']}`",
        f"- Critérios aprovados: `{current['passed']}/{current['checks']}`",
        f"- Critérios bloqueantes em aberto: `{current['blocking_open']}`",
        f"- Evidências manuais/de execução pendentes: `{current['pending']}`",
        f"- Alertas não bloqueantes: `{current['warnings']}`",
        f"- Próximo bloqueio: `{current['next_blocker']}`",
        "",
        "## Critérios",
        "",
        markdown_table(
            checks,
            ["category", "check_id", "evaluation", "blocking", "status", "expected", "evidence"],
            top_n=None,
        ),
        "",
        "## Bloqueios em aberto",
        "",
        markdown_table(blocking, ["check_id", "observed", "remediation"], top_n=None),
        "",
        "## Regra de expansão",
        "",
        "Não adicionar uma segunda equipe-alvo nem promover outro mapa no pipeline de referência enquanto `status != consolidated`. Trabalho exploratório pode continuar, mas não pode redefinir o contrato de referência do Mirage.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate whether Mirage is consolidated as the reference map.")
    parser.add_argument("--config", type=Path, default=Path("configs/project.yaml"))
    parser.add_argument("--contract", type=Path, default=Path("configs/quality/mirage_consolidation.yaml"))
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("configs/quality/mirage_consolidation_evidence.yaml"),
    )
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Write the report without returning a non-zero exit code when blockers remain.",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_mirage_consolidation_gate(
        args.config,
        contract_path=args.contract,
        evidence_path=args.evidence,
        project_root=args.project_root.resolve(),
        force=args.force,
        dry_run=args.dry_run,
    )
    print({**summary, "outputs": {name: str(path) for name, path in outputs.items()}})
    if summary["status"] != "consolidated" and not args.report_only:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
