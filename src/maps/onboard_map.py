from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.config.schemas import load_project_config
from src.features.build_round_features import run_feature_pipeline
from src.features.map_refactor_audit import load_candidate_feature_set, load_feature_contract
from src.maps.identity import same_map
from src.maps.registry import MapRegistry, load_map_registry, normalize_id, validate_map_registry
from src.maps.semantic import resolve_feature_requirements
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "inferno_onboarding_summary",
    "inferno_data_availability",
    "inferno_region_inventory",
    "inferno_semantic_coverage",
    "inferno_feature_coverage",
    "inferno_candidate_feature_portability",
    "inferno_dataset_snapshot",
    "inferno_feature_quality",
    "inferno_unknowns",
    "inferno_onboarding_audit",
]

DEFAULT_MAP = "Inferno"
DEFAULT_TARGET_TEAM = "Vitality"
MIRAGE_GATE_PATH = Path("data/gold/validation/mirage_regression_gate/mirage_regression_audit.parquet")


def run_onboarding(
    config_path: Path,
    *,
    map_name: str = DEFAULT_MAP,
    target_team: str = DEFAULT_TARGET_TEAM,
    force: bool = False,
    dry_run: bool = False,
    run_pipeline: bool = False,
    registry_only: bool = False,
    registry_path: Path = Path("configs/maps/map_registry.yaml"),
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, object]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    output_dir = project_root / "data" / "gold" / "maps" / "inferno" / "onboarding"

    gate = load_mirage_gate(project_root)
    if not mirage_gate_passed(gate):
        raise ValueError("Mirage regression gate has not passed. New-map onboarding is blocked.")

    registry = load_map_registry(map_name, registry_path=project_root / registry_path)
    validate_map_registry(registry)
    if registry.map_id != "inferno":
        raise ValueError(f"Stage 8.4 only onboards Inferno. Received map_id={registry.map_id}.")

    feature_contract = load_feature_contract(gold_dir)
    candidate_set = load_candidate_feature_set(gold_dir)
    data_availability = build_data_availability(project_root, target_team=target_team, registry=registry)
    region_inventory = build_region_inventory(registry, project_root=project_root)
    semantic_coverage = build_semantic_coverage(feature_contract, registry)
    feature_coverage = build_feature_coverage(feature_contract, registry)
    candidate_portability = build_candidate_portability(candidate_set, feature_coverage)
    unknowns = build_unknowns(registry, data_availability, semantic_coverage, feature_coverage, candidate_portability)

    dataset_snapshot, feature_quality, pipeline_status, pipeline_completed = build_pipeline_outputs(
        config_path,
        project_root=project_root,
        registry=registry,
        target_team=target_team,
        data_availability=data_availability,
        run_pipeline=run_pipeline and not registry_only,
        dry_run=dry_run,
    )
    if registry_only:
        pipeline_status = "not_requested_registry_only"
        pipeline_completed = False

    audit = build_audit(
        gate=gate,
        registry=registry,
        feature_contract=feature_contract,
        semantic_coverage=semantic_coverage,
        feature_coverage=feature_coverage,
        candidate_portability=candidate_portability,
        data_availability=data_availability,
        feature_quality=feature_quality,
        unknowns=unknowns,
        pipeline_run_requested=run_pipeline and not registry_only,
        pipeline_run_completed=pipeline_completed,
    )
    summary = build_summary(
        registry=registry,
        target_team=target_team,
        feature_contract=feature_contract,
        data_availability=data_availability,
        semantic_coverage=semantic_coverage,
        audit=audit,
        pipeline_status=pipeline_status,
    )
    frames = {
        "inferno_onboarding_summary": summary,
        "inferno_data_availability": data_availability,
        "inferno_region_inventory": region_inventory,
        "inferno_semantic_coverage": semantic_coverage,
        "inferno_feature_coverage": feature_coverage,
        "inferno_candidate_feature_portability": candidate_portability,
        "inferno_dataset_snapshot": dataset_snapshot,
        "inferno_feature_quality": feature_quality,
        "inferno_unknowns": unknowns,
        "inferno_onboarding_audit": audit,
    }

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_outputs(frames, output_dir, force=force))
        outputs["report"] = write_text(build_report(frames), project_root / "docs" / "inferno_onboarding_report.md", force=force)
        outputs["notebook"] = write_text(build_notebook_json(), project_root / "notebooks" / "18_inferno_onboarding.ipynb", force=force)

    return frames, outputs, {
        "data_status": str(summary.loc[0, "data_status"]),
        "registry_status": str(summary.loc[0, "registry_status"]),
        "semantic_coverage_status": str(summary.loc[0, "semantic_coverage_status"]),
        "pipeline_execution_status": str(summary.loc[0, "pipeline_execution_status"]),
        "ready_for_inferno_feature_run": bool(summary.loc[0, "ready_for_inferno_feature_run"]),
        "ready_for_inferno_eda": bool(summary.loc[0, "ready_for_inferno_eda"]),
        "ready_for_inferno_modeling_evaluation": bool(summary.loc[0, "ready_for_inferno_modeling_evaluation"]),
        "unknowns": len(unknowns),
    }


def load_mirage_gate(project_root: Path) -> pd.DataFrame:
    path = project_root / MIRAGE_GATE_PATH
    if not path.exists():
        raise FileNotFoundError(f"Mirage regression gate audit not found: {path}")
    return read_catalog(path)


def mirage_gate_passed(gate: pd.DataFrame) -> bool:
    return bool(not gate.empty and gate.iloc[0].get("ready_for_new_map_onboarding") == True)  # noqa: E712


def build_data_availability(project_root: Path, *, target_team: str, registry: MapRegistry) -> pd.DataFrame:
    catalog = read_optional(project_root / "data/silver/matches_catalog/matches_catalog.parquet")
    dem_files = read_optional(project_root / "data/bronze/dem_files_manifest/dem_files_manifest.parquet")
    parse_quality = read_optional(project_root / "data/bronze/parse_quality/parse_quality.parquet")
    parse_manifest = read_optional(project_root / "data/bronze/parse_manifest/parse_manifest.parquet")
    feature_eligible = read_optional(project_root / "data/silver/parsed_demos/feature_eligible_demos.parquet")

    catalog_map = filter_team_map(catalog, target_team=target_team, registry=registry, map_column="map_name")
    dem_map = filter_team_map(dem_files, target_team=target_team, registry=registry, map_column="inferred_map_name")
    quality_map = filter_team_map(parse_quality, target_team=target_team, registry=registry, map_column="inferred_map_name")
    parse_map = filter_team_map(parse_manifest, target_team=target_team, registry=registry, map_column="map_name")
    eligible_map = filter_team_map(feature_eligible, target_team=target_team, registry=registry, map_column="inferred_map_name")
    archive_count = unique_count(dem_map, "local_archive_id") or unique_count(dem_map, "archive_path")

    if len(dem_map) == 0:
        data_status = "missing_demos"
        blocking_reason = "No local Inferno demos were found in dem_files_manifest."
        recommended_action = "Add Vitality Inferno demos through the local/manual archive flow."
    elif int((quality_map.get("feature_eligible", pd.Series(dtype=bool)) == True).sum()) == 0:  # noqa: E712
        data_status = "local_demos_not_feature_eligible"
        blocking_reason = "Inferno demos exist locally, but current parse quality marks them outside target maps or not feature eligible."
        recommended_action = "Re-run parsing/quality with Inferno explicitly targeted after confirming the Inferno registry area names."
    else:
        data_status = "available"
        blocking_reason = None
        recommended_action = "Run onboarding with --run-pipeline after confirming the registry."

    dates = date_bounds(pd.concat([parse_map, catalog_map], ignore_index=True) if not catalog_map.empty or not parse_map.empty else pd.DataFrame())
    return pd.DataFrame(
        [
            {
                "target_team": target_team,
                "map_id": registry.map_id,
                "catalog_matches": len(catalog_map),
                "local_archives": archive_count,
                "dem_files": len(dem_map),
                "parse_eligible_demos": int((quality_map.get("parse_eligible", pd.Series(dtype=bool)) == True).sum()),  # noqa: E712
                "feature_eligible_demos": len(eligible_map[eligible_map.get("feature_eligible", pd.Series(dtype=bool)) == True]) if not eligible_map.empty and "feature_eligible" in eligible_map.columns else len(eligible_map),  # noqa: E712
                "parsed_demos": int((parse_map.get("parse_status", pd.Series(dtype="object")).astype(str) == "parsed").sum()) if not parse_map.empty else 0,
                "date_min": dates[0],
                "date_max": dates[1],
                "data_status": data_status,
                "blocking_reason": blocking_reason,
                "recommended_action": recommended_action,
            }
        ]
    )


def build_region_inventory(registry: MapRegistry, *, project_root: Path) -> pd.DataFrame:
    ticks = read_tick_area_inventory(project_root, registry)
    rows = []
    for region in registry.physical_regions.values():
        area_names = [str(value) for value in region.geometry.get("area_names", [])]
        observed_rows = int(ticks[ticks["place_name"].isin(area_names)]["observed_player_rows"].sum()) if not ticks.empty and area_names else 0
        rows.append(
            {
                "map_id": registry.map_id,
                "region_id": region.region_id,
                "display_name": region.display_name,
                "geometry_type": region.geometry.get("type"),
                "geometry_source": region.geometry.get("source"),
                "observed_in_demo_data": observed_rows > 0,
                "observed_player_rows": observed_rows,
                "site_affinity": "|".join(region.site_affinity),
                "semantic_tags": "|".join(region.semantic_tags),
                "status": region.status,
                "notes": region.notes,
            }
        )
    return pd.DataFrame(rows)


def build_semantic_coverage(feature_contract: pd.DataFrame, registry: MapRegistry) -> pd.DataFrame:
    required = required_semantics(feature_contract)
    rows = []
    for semantic_id, required_count in required.items():
        group = registry.get_semantic_group(semantic_id)
        regions = registry.regions_for_semantic(semantic_id)
        active_regions = [region for region in regions if region.status == "active"]
        unresolved_regions = [region for region in regions if region.status != "active"]
        if not regions:
            status = "missing"
            resolved = False
            confidence = "none"
            notes = "Required semantic is absent from Inferno registry."
        elif unresolved_regions and not active_regions:
            status = "partial"
            resolved = False
            confidence = "low"
            notes = "Semantic exists structurally, but member regions are unresolved pending parser/nav area inventory."
        elif unresolved_regions:
            status = "partial"
            resolved = False
            confidence = "low"
            notes = "Semantic has at least one unresolved member region."
        else:
            status = "resolved"
            resolved = bool(group)
            confidence = "high"
            notes = None
        rows.append(
            {
                "semantic_id": semantic_id,
                "required_by_feature_count": required_count,
                "physical_region_count": len(regions),
                "physical_regions": "|".join(region.region_id for region in regions),
                "resolved": resolved,
                "coverage_status": status,
                "confidence": confidence,
                "blocking_feature_count": 0 if resolved else required_count,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def build_feature_coverage(feature_contract: pd.DataFrame, registry: MapRegistry) -> pd.DataFrame:
    usage = resolve_feature_requirements(feature_contract, registry)
    rows = []
    for _, row in feature_contract.iterrows():
        feature_name = str(row.get("feature_name"))
        region_dependency = bool(row.get("region_dependency"))
        map_scope = str(row.get("map_scope") or "unknown")
        semantic = normalize_optional(row.get("region_semantic"))
        resolved_regions = usage[usage["feature_name"] == feature_name]["physical_regions_used"].iloc[0] if not usage.empty and feature_name in set(usage["feature_name"]) else []
        regions = [registry.get_region(region_id) for region_id in (resolved_regions if isinstance(resolved_regions, list) else [])]
        regions = [region for region in regions if region is not None]
        has_unresolved_region = any(region.status != "active" for region in regions)

        if not region_dependency:
            inferno_supported = True
            support_type = "global"
            blocking_reason = None
            recommended_action = "No map-specific registry action needed."
        elif map_scope == "map_specific":
            inferno_supported = False
            support_type = "not_applicable"
            blocking_reason = "Mirage/reference-map-specific feature is not automatically adapted to Inferno."
            recommended_action = "Create an explicit future map-specific equivalent decision if this concept matters on Inferno."
        elif regions and not has_unresolved_region:
            inferno_supported = True
            support_type = "semantic_mapping"
            blocking_reason = None
            recommended_action = "Available through Inferno semantic mapping."
        elif regions and has_unresolved_region:
            inferno_supported = False
            support_type = "unresolved"
            blocking_reason = "Inferno semantic exists only as unresolved named-area placeholder."
            recommended_action = "Populate Inferno parser/nav area names in configs/maps/inferno.yaml."
        else:
            inferno_supported = False
            support_type = "blocked"
            blocking_reason = "Missing Inferno semantic mapping."
            recommended_action = "Add semantic group and physical region mapping to the Inferno registry."

        rows.append(
            {
                "feature_name": feature_name,
                "feature_family": row.get("feature_family"),
                "semantic_role": row.get("semantic_role"),
                "feature_status": row.get("feature_status"),
                "map_scope": map_scope,
                "region_dependency": region_dependency,
                "region_semantic": semantic,
                "inferno_supported": inferno_supported,
                "support_type": support_type,
                "physical_regions_used": "|".join(region.region_id for region in regions),
                "modeling_allowed": bool(row.get("modeling_allowed")) if "modeling_allowed" in row else False,
                "dashboard_allowed": bool(row.get("dashboard_allowed")) if "dashboard_allowed" in row else False,
                "blocking_reason": blocking_reason,
                "recommended_action": recommended_action,
            }
        )
    return pd.DataFrame(rows)


def build_candidate_portability(candidate_set: pd.DataFrame, feature_coverage: pd.DataFrame) -> pd.DataFrame:
    if candidate_set.empty or "feature_name" not in candidate_set.columns:
        return pd.DataFrame(
            columns=[
                "candidate_id",
                "feature_name",
                "mirage_importance_rank",
                "mirage_importance_value",
                "map_scope",
                "region_dependency",
                "region_semantic",
                "available_on_inferno",
                "portability_type",
                "physical_regions_used",
                "status",
                "notes",
            ]
        )
    coverage = feature_coverage.set_index("feature_name") if not feature_coverage.empty else pd.DataFrame()
    rows = []
    for rank, row in enumerate(candidate_set[candidate_set["feature_name"].astype(str) != "__feature_set_summary__"].to_dict("records"), start=1):
        feature_name = str(row.get("feature_name"))
        if feature_name in coverage.index:
            cov = coverage.loc[feature_name]
            map_scope = str(cov.get("map_scope"))
            region_dependency = bool(cov.get("region_dependency"))
            available = bool(cov.get("inferno_supported"))
            support_type = str(cov.get("support_type"))
            if map_scope == "global":
                portability_type = "direct_global"
            elif available and support_type == "semantic_mapping":
                portability_type = "semantic_equivalent"
            elif map_scope == "map_specific":
                portability_type = "map_specific_missing"
            else:
                portability_type = "unresolved"
            physical = cov.get("physical_regions_used")
            semantic = cov.get("region_semantic")
            status = "available" if available else "unresolved"
            notes = "Metadata only; no Mirage prediction is reused on Inferno."
        else:
            map_scope = None
            region_dependency = None
            available = False
            portability_type = "unresolved"
            physical = None
            semantic = None
            status = "unresolved"
            notes = "Candidate feature is absent from the current feature contract coverage table."
        rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "feature_name": feature_name,
                "mirage_importance_rank": rank,
                "mirage_importance_value": row.get("importance_value"),
                "map_scope": map_scope,
                "region_dependency": region_dependency,
                "region_semantic": semantic,
                "available_on_inferno": available,
                "portability_type": portability_type,
                "physical_regions_used": physical,
                "status": status,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def build_pipeline_outputs(
    config_path: Path,
    *,
    project_root: Path,
    registry: MapRegistry,
    target_team: str,
    data_availability: pd.DataFrame,
    run_pipeline: bool,
    dry_run: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, str, bool]:
    data = data_availability.iloc[0]
    if not run_pipeline:
        return build_dataset_snapshot(project_root, registry=registry, target_team=target_team, pipeline_frame=None), empty_feature_quality(), "not_requested", False
    if int(data["feature_eligible_demos"]) == 0:
        return build_dataset_snapshot(project_root, registry=registry, target_team=target_team, pipeline_frame=None), empty_feature_quality(), "blocked_by_data", False
    try:
        round_features, _, _ = run_feature_pipeline(
            config_path,
            force=False,
            dry_run=True if dry_run else True,
            target_team=target_team,
            target_map=registry.display_name,
            map_registry_path=Path("configs/maps/map_registry.yaml"),
        )
    except Exception as exc:  # noqa: BLE001
        snapshot = build_dataset_snapshot(project_root, registry=registry, target_team=target_team, pipeline_frame=None)
        quality = pd.DataFrame(
            [
                {
                    "feature_name": "__pipeline_error__",
                    "feature_family": "pipeline",
                    "map_scope": "global",
                    "row_count": 0,
                    "non_null_count": 0,
                    "null_share": None,
                    "unique_values": None,
                    "zero_share": None,
                    "min": None,
                    "max": None,
                    "mean": None,
                    "std": None,
                    "constant_feature": False,
                    "all_null_feature": False,
                    "suspicious_feature": True,
                    "quality_status": "failed",
                    "notes": str(exc),
                }
            ]
        )
        return snapshot, quality, "failed", False
    return build_dataset_snapshot(project_root, registry=registry, target_team=target_team, pipeline_frame=round_features), build_feature_quality(round_features), "dry_run_completed" if dry_run else "isolated_dry_run_completed", True


def build_dataset_snapshot(project_root: Path, *, registry: MapRegistry, target_team: str, pipeline_frame: pd.DataFrame | None) -> pd.DataFrame:
    t_side_all = filter_team_map(read_optional(project_root / "data/gold/round_features/round_features_t_side_all.parquet"), target_team=target_team, registry=registry, map_column="map_name")
    t_side_planted = filter_team_map(read_optional(project_root / "data/gold/round_features/round_features_t_side_planted.parquet"), target_team=target_team, registry=registry, map_column="map_name")
    ct_side = filter_team_map(read_optional(project_root / "data/gold/round_features/round_features_ct_side.parquet"), target_team=target_team, registry=registry, map_column="map_name")
    region_presence = filter_team_map(read_optional(project_root / "data/gold/region_presence/region_presence_by_round.parquet"), target_team=target_team, registry=registry, map_column="map_name")
    utility_events = filter_team_map(read_optional(project_root / "data/gold/utility_events/utility_events.parquet"), target_team=target_team, registry=registry, map_column="map_name")
    feature_eligible = filter_team_map(read_optional(project_root / "data/silver/parsed_demos/feature_eligible_demos.parquet"), target_team=target_team, registry=registry, map_column="inferred_map_name")
    source = pipeline_frame if pipeline_frame is not None else t_side_all
    labels = t_side_planted.get("target_site_model_label", pd.Series(dtype="object"))
    return pd.DataFrame(
        [
            {
                "feature_eligible_demos": len(feature_eligible),
                "total_rounds": len(source) if pipeline_frame is not None else None,
                "t_side_rounds": len(t_side_all) if not t_side_all.empty else None,
                "ct_side_rounds": len(ct_side) if not ct_side.empty else None,
                "t_side_planted_rounds": len(t_side_planted) if not t_side_planted.empty else None,
                "plant_A": int((labels == "A").sum()) if not t_side_planted.empty else None,
                "plant_B": int((labels == "B").sum()) if not t_side_planted.empty else None,
                "no_plant": int((source.get("target_site_model_label", pd.Series(dtype="object")).isna()).sum()) if pipeline_frame is not None and "target_site_model_label" in source else None,
                "feature_count": len(source.columns) if pipeline_frame is not None else None,
                "region_presence_rows": len(region_presence) if not region_presence.empty else None,
                "utility_event_rows": len(utility_events) if not utility_events.empty else None,
            }
        ]
    )


def build_feature_quality(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return empty_feature_quality()
    rows = []
    for column in frame.columns:
        series = frame[column]
        numeric = pd.api.types.is_numeric_dtype(series)
        non_null = int(series.notna().sum())
        unique_values = int(series.nunique(dropna=True))
        zero_share = float((series == 0).sum() / len(series)) if numeric and len(series) else None
        all_null = non_null == 0
        constant = unique_values <= 1 and not all_null
        suspicious = all_null or (constant and column not in {"map_name", "target_team", "dataset_type"})
        rows.append(
            {
                "feature_name": column,
                "feature_family": None,
                "map_scope": None,
                "row_count": len(series),
                "non_null_count": non_null,
                "null_share": float(series.isna().sum() / len(series)) if len(series) else None,
                "unique_values": unique_values,
                "zero_share": zero_share,
                "min": float(series.min()) if numeric and non_null else None,
                "max": float(series.max()) if numeric and non_null else None,
                "mean": float(series.mean()) if numeric and non_null else None,
                "std": float(series.std()) if numeric and non_null else None,
                "constant_feature": constant,
                "all_null_feature": all_null,
                "suspicious_feature": suspicious,
                "quality_status": "warning" if suspicious else "ok",
                "notes": "Conservative quality probe; constant/all-null features need review." if suspicious else None,
            }
        )
    return pd.DataFrame(rows)


def empty_feature_quality() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "feature_name",
            "feature_family",
            "map_scope",
            "row_count",
            "non_null_count",
            "null_share",
            "unique_values",
            "zero_share",
            "min",
            "max",
            "mean",
            "std",
            "constant_feature",
            "all_null_feature",
            "suspicious_feature",
            "quality_status",
            "notes",
        ]
    )


def build_unknowns(
    registry: MapRegistry,
    data_availability: pd.DataFrame,
    semantic_coverage: pd.DataFrame,
    feature_coverage: pd.DataFrame,
    candidate_portability: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    data = data_availability.iloc[0]
    if str(data["data_status"]) != "available":
        rows.append(unknown("missing_data", None, None, None, str(data["blocking_reason"]), "high", True, str(data["recommended_action"])))
    for _, row in semantic_coverage.iterrows():
        if not bool(row["resolved"]):
            rows.append(unknown("missing_semantic", None, str(row["semantic_id"]), None, str(row["notes"]), "high", True, "Populate Inferno semantic mappings from parser/nav area inventory."))
    unsupported = feature_coverage[feature_coverage["inferno_supported"] == False] if not feature_coverage.empty else pd.DataFrame()  # noqa: E712
    for _, row in unsupported.head(200).iterrows():
        category = "map_specific_feature" if row.get("support_type") == "not_applicable" else "missing_region"
        rows.append(unknown(category, str(row["feature_name"]), str(row.get("region_semantic")), None, str(row.get("blocking_reason")), "medium", row.get("support_type") != "not_applicable", str(row.get("recommended_action"))))
    for region in registry.physical_regions.values():
        if region.status != "active":
            rows.append(unknown("missing_region", None, None, region.region_id, "Region is registered as unresolved pending real parser/nav area names.", "high", True, "Update configs/maps/inferno.yaml with confirmed named areas."))
    if not candidate_portability.empty and (candidate_portability["status"] != "available").any():
        count = int((candidate_portability["status"] != "available").sum())
        rows.append(unknown("feature_quality", None, None, None, f"{count} Mirage candidate features are not portable to Inferno yet.", "medium", False, "Use this as metadata only; do not reuse Mirage predictions."))
    return pd.DataFrame(rows, columns=["unknown_id", "category", "feature_name", "semantic_id", "region_id", "reason", "severity", "blocking", "recommended_action"])


def build_audit(
    *,
    gate: pd.DataFrame,
    registry: MapRegistry,
    feature_contract: pd.DataFrame,
    semantic_coverage: pd.DataFrame,
    feature_coverage: pd.DataFrame,
    candidate_portability: pd.DataFrame,
    data_availability: pd.DataFrame,
    feature_quality: pd.DataFrame,
    unknowns: pd.DataFrame,
    pipeline_run_requested: bool,
    pipeline_run_completed: bool,
) -> pd.DataFrame:
    required = semantic_coverage
    resolved_semantics = int(required["resolved"].sum()) if not required.empty else 0
    unresolved_semantics = int((~required["resolved"]).sum()) if not required.empty else 0
    frozen = feature_contract[feature_contract.get("feature_status", pd.Series(dtype="object")).eq("frozen")] if "feature_status" in feature_contract.columns else feature_contract
    supported_frozen = int((feature_coverage[feature_coverage["feature_status"].eq("frozen")]["inferno_supported"] == True).sum()) if "feature_status" in feature_coverage.columns else int((feature_coverage["inferno_supported"] == True).sum())  # noqa: E712
    unsupported_frozen = len(frozen) - supported_frozen
    critical_failures = int(unknowns[unknowns["blocking"] == True].shape[0]) if not unknowns.empty else 0  # noqa: E712
    quality_warnings = int((feature_quality.get("quality_status", pd.Series(dtype="object")) == "warning").sum()) if not feature_quality.empty else 0
    data = data_availability.iloc[0]
    registry_valid = all(region.status == "active" for region in registry.physical_regions.values())
    bomb_a = bool(registry.regions_for_site("A")) and all(region.status == "active" for region in registry.regions_for_site("A"))
    bomb_b = bool(registry.regions_for_site("B")) and all(region.status == "active" for region in registry.regions_for_site("B"))
    ready_feature = bool(mirage_gate_passed(gate) and registry_valid and bomb_a and bomb_b and unresolved_semantics == 0)
    ready_eda = bool(ready_feature and str(data["data_status"]) == "available" and pipeline_run_completed and quality_warnings == 0)
    labels_ok = False
    ready_model = bool(ready_eda and labels_ok)
    status = "ok" if ready_eda else ("blocked" if critical_failures else "warning")
    return pd.DataFrame(
        [
            {
                "audit_id": "inferno_onboarding",
                "map_id": registry.map_id,
                "target_team": str(data["target_team"]),
                "mirage_gate_passed": mirage_gate_passed(gate),
                "registry_valid": registry_valid,
                "bombsite_A_resolved": bomb_a,
                "bombsite_B_resolved": bomb_b,
                "required_semantics": len(required),
                "resolved_semantics": resolved_semantics,
                "unresolved_semantics": unresolved_semantics,
                "frozen_features": len(frozen),
                "supported_frozen_features": supported_frozen,
                "unsupported_frozen_features": unsupported_frozen,
                "candidate_features": len(candidate_portability),
                "portable_candidate_features": int((candidate_portability["available_on_inferno"] == True).sum()) if not candidate_portability.empty else 0,  # noqa: E712
                "unresolved_candidate_features": int((candidate_portability["available_on_inferno"] == False).sum()) if not candidate_portability.empty else 0,  # noqa: E712
                "demos_available": int(data["dem_files"]) > 0,
                "pipeline_run_requested": pipeline_run_requested,
                "pipeline_run_completed": pipeline_run_completed,
                "feature_quality_checks": len(feature_quality),
                "feature_quality_warnings": quality_warnings,
                "critical_feature_failures": critical_failures,
                "ready_for_inferno_feature_run": ready_feature,
                "ready_for_inferno_eda": ready_eda,
                "ready_for_inferno_modeling_evaluation": ready_model,
                "status": status,
                "created_at": now_utc(),
            }
        ]
    )


def build_summary(
    *,
    registry: MapRegistry,
    target_team: str,
    feature_contract: pd.DataFrame,
    data_availability: pd.DataFrame,
    semantic_coverage: pd.DataFrame,
    audit: pd.DataFrame,
    pipeline_status: str,
) -> pd.DataFrame:
    audit_row = audit.iloc[0]
    data_row = data_availability.iloc[0]
    semantic_status = "ok" if int(audit_row["unresolved_semantics"]) == 0 else "blocked"
    registry_status = "ok" if bool(audit_row["registry_valid"]) else "blocked"
    return pd.DataFrame(
        [
            {
                "onboarding_id": "vitality_inferno_t_side_stage_8_4",
                "map_id": registry.map_id,
                "map_name": registry.display_name,
                "target_team": target_team,
                "registry_version": registry.registry_version,
                "region_schema_version": registry.region_schema_version,
                "feature_contract_version": contract_version(feature_contract),
                "data_status": data_row["data_status"],
                "registry_status": registry_status,
                "semantic_coverage_status": semantic_status,
                "feature_engine_status": "config_ready_but_regions_unresolved" if registry_status != "ok" else "ready",
                "pipeline_execution_status": pipeline_status,
                "ready_for_inferno_feature_run": bool(audit_row["ready_for_inferno_feature_run"]),
                "ready_for_inferno_eda": bool(audit_row["ready_for_inferno_eda"]),
                "ready_for_inferno_modeling_evaluation": bool(audit_row["ready_for_inferno_modeling_evaluation"]),
                "created_at": now_utc(),
            }
        ]
    )


def read_optional(path: Path) -> pd.DataFrame:
    if path.exists():
        return read_catalog(path)
    csv = path.with_suffix(".csv")
    if csv.exists():
        return read_catalog(csv)
    return pd.DataFrame()


def filter_team_map(df: pd.DataFrame, *, target_team: str, registry: MapRegistry, map_column: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    result = df.copy()
    if "target_team" in result.columns:
        result = result[result["target_team"].astype(str).str.lower() == target_team.lower()]
    if map_column in result.columns:
        result = result[result[map_column].map(lambda value: same_map(value, registry.display_name))]
    return result.copy()


def unique_count(df: pd.DataFrame, column: str) -> int:
    return int(df[column].nunique()) if column in df.columns and not df.empty else 0


def date_bounds(df: pd.DataFrame) -> tuple[str | None, str | None]:
    if df.empty or "match_date" not in df.columns:
        return None, None
    dates = pd.to_datetime(df["match_date"], errors="coerce").dropna()
    if dates.empty:
        return None, None
    return dates.min().date().isoformat(), dates.max().date().isoformat()


def read_tick_area_inventory(project_root: Path, registry: MapRegistry) -> pd.DataFrame:
    del registry
    path = project_root / "data/silver/parsed_demos/ticks.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["place_name", "observed_player_rows"])
    return pd.DataFrame(columns=["place_name", "observed_player_rows"])


def required_semantics(feature_contract: pd.DataFrame) -> dict[str, int]:
    if feature_contract.empty:
        return {}
    data = feature_contract.copy()
    if "feature_status" in data.columns:
        data = data[data["feature_status"].astype(str) == "frozen"]
    data = data[(data.get("map_scope", pd.Series(dtype="object")) == "map_abstract") & (data.get("region_dependency", pd.Series(dtype=bool)) == True)]  # noqa: E712
    if "region_semantic" not in data.columns:
        return {}
    counts = data["region_semantic"].dropna().map(lambda value: normalize_id(str(value))).value_counts()
    return {str(key): int(value) for key, value in counts.items()}


def normalize_optional(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = normalize_id(str(value))
    return text or None


def unknown(
    category: str,
    feature_name: str | None,
    semantic_id: str | None,
    region_id: str | None,
    reason: str,
    severity: str,
    blocking: bool,
    recommended_action: str,
) -> dict[str, object]:
    seed = "|".join(str(value or "") for value in [category, feature_name, semantic_id, region_id, reason])
    return {
        "unknown_id": f"unknown_{abs(hash(seed)) % 10_000_000}",
        "category": category,
        "feature_name": feature_name,
        "semantic_id": semantic_id,
        "region_id": region_id,
        "reason": reason,
        "severity": severity,
        "blocking": blocking,
        "recommended_action": recommended_action,
    }


def contract_version(feature_contract: pd.DataFrame) -> str:
    if "feature_contract_version" in feature_contract.columns and not feature_contract.empty:
        values = feature_contract["feature_contract_version"].dropna()
        if not values.empty:
            return str(values.iloc[0])
    return "unknown"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        frame = sanitize_for_parquet(frames[name])
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                frame.to_csv(path, index=False) if suffix == "csv" else frame.to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def sanitize_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].map(lambda value: "|".join(value) if isinstance(value, list) else value)
    return result


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def build_report(frames: dict[str, pd.DataFrame]) -> str:
    summary = frames["inferno_onboarding_summary"]
    availability = frames["inferno_data_availability"]
    regions = frames["inferno_region_inventory"]
    semantics = frames["inferno_semantic_coverage"]
    features = frames["inferno_feature_coverage"]
    candidate = frames["inferno_candidate_feature_portability"]
    snapshot = frames["inferno_dataset_snapshot"]
    quality = frames["inferno_feature_quality"]
    unknowns = frames["inferno_unknowns"]
    audit = frames["inferno_onboarding_audit"]
    return "\n".join(
        [
            "# Vitality Inferno -- First New Map Onboarding",
            "",
            "## Purpose",
            "Stage 8.4 tests whether the map-ready architecture can add Inferno through registry, configuration, and validation instead of ad hoc feature-engine changes.",
            "",
            "## Why Inferno was selected",
            "Inferno is the first non-Mirage map used to test portability of Vitality T-side tactical feature definitions.",
            "",
            "## Stage 8.3 precondition",
            f"Mirage gate passed: `{str(audit.loc[0, 'mirage_gate_passed']).lower()}`.",
            "",
            "## Data availability",
            markdown_table(availability, list(availability.columns)),
            "",
            "## Inferno registry",
            "Inferno is registered in `configs/maps/map_registry.yaml` with `status: onboarding`. The current `configs/maps/inferno.yaml` intentionally marks physical regions as unresolved because no verified Inferno parser/nav area inventory is available locally yet.",
            "",
            "## Physical regions",
            markdown_table(regions, list(regions.columns), top_n=40),
            "",
            "## Semantic groups",
            markdown_table(semantics, list(semantics.columns), top_n=40),
            "",
            "## Feature contract coverage",
            markdown_table(features, ["feature_name", "map_scope", "region_dependency", "region_semantic", "inferno_supported", "support_type", "blocking_reason"], top_n=40),
            "",
            "## Map-abstract feature portability",
            "Map-abstract portability means the same semantic feature definition can be produced after Inferno has verified region mappings. It does not mean the Mirage model transfers to Inferno.",
            "",
            "## Mirage-specific features",
            markdown_table(features[features["support_type"].eq("not_applicable")], ["feature_name", "region_semantic", "support_type", "recommended_action"], top_n=40),
            "",
            "## Candidate-feature portability",
            markdown_table(candidate, ["candidate_id", "feature_name", "map_scope", "available_on_inferno", "portability_type", "status"], top_n=40),
            "",
            "## Pipeline execution",
            markdown_table(summary, ["pipeline_execution_status", "ready_for_inferno_feature_run", "ready_for_inferno_eda", "ready_for_inferno_modeling_evaluation"]),
            "",
            "## Dataset snapshot",
            markdown_table(snapshot, list(snapshot.columns)),
            "",
            "## Feature quality",
            markdown_table(quality, ["feature_name", "row_count", "non_null_count", "constant_feature", "all_null_feature", "quality_status"], top_n=40),
            "",
            "## Unknowns / blockers",
            markdown_table(unknowns, list(unknowns.columns), top_n=80),
            "",
            "## Readiness",
            markdown_table(audit, list(audit.columns)),
            "",
            "## Next stage",
            "Do not start Stage 8.5 until `ready_for_inferno_eda` is true. The next practical action is to confirm Inferno parser/nav area names, update `configs/maps/inferno.yaml`, then re-run parsing/quality with Inferno as an explicit target.",
            "",
        ]
    )


def build_notebook_json() -> str:
    cells = [
        md("# Stage 8.4 -- Vitality Inferno Onboarding"),
        code(
            "from pathlib import Path\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n\n"
            "BASE = Path('../data/gold/maps/inferno/onboarding')\n"
            "def load(name):\n"
            "    return pd.read_parquet(BASE / f'{name}.parquet')\n\n"
            "summary = load('inferno_onboarding_summary')\n"
            "availability = load('inferno_data_availability')\n"
            "regions = load('inferno_region_inventory')\n"
            "semantics = load('inferno_semantic_coverage')\n"
            "features = load('inferno_feature_coverage')\n"
            "candidate = load('inferno_candidate_feature_portability')\n"
            "snapshot = load('inferno_dataset_snapshot')\n"
            "quality = load('inferno_feature_quality')\n"
            "unknowns = load('inferno_unknowns')\n"
            "audit = load('inferno_onboarding_audit')"
        ),
        md("## Onboarding Summary"),
        code("display(summary)"),
        md("## Data Availability"),
        code("display(availability)"),
        md("## Region Inventory"),
        code("display(regions)"),
        md("## Physical to Semantic Mapping"),
        code("display(regions[['region_id', 'semantic_tags', 'status', 'notes']])"),
        md("## Semantic Coverage"),
        code("display(semantics)"),
        md("## Feature Coverage"),
        code("display(features.head(80))"),
        md("## Candidate Feature Portability"),
        code("display(candidate)"),
        md("## Dataset Snapshot"),
        code("display(snapshot)"),
        md("## Feature Quality"),
        code("display(quality.head(80))"),
        md("## Plant Distribution"),
        code("display(snapshot[['plant_A', 'plant_B', 'no_plant']])"),
        md("## Unknowns"),
        code("display(unknowns)"),
        md("## Audit"),
        code("display(audit)"),
        md("## Region Sketch"),
        code(
            "coord_cols = {'x_min', 'x_max', 'y_min', 'y_max'}\n"
            "if coord_cols <= set(regions.columns) and regions[list(coord_cols)].notna().all(axis=1).any():\n"
            "    fig, ax = plt.subplots(figsize=(7, 7))\n"
            "    for _, row in regions.dropna(subset=list(coord_cols)).iterrows():\n"
            "        rect = plt.Rectangle((row.x_min, row.y_min), row.x_max - row.x_min, row.y_max - row.y_min, fill=False)\n"
            "        ax.add_patch(rect)\n"
            "        ax.text(row.x_min, row.y_min, row.region_id)\n"
            "    ax.set_aspect('equal', adjustable='box')\n"
            "else:\n"
            "    print('No verified Inferno coordinate regions are available yet; registry currently uses unresolved named-area placeholders.')"
        ),
    ]
    notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.11"}}, "nbformat": 4, "nbformat_minor": 5}
    return json.dumps(notebook, indent=1) + "\n"


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    if frame.empty:
        return "_No rows._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def md(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict[str, object]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 8.4 first new-map onboarding.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--map", default=DEFAULT_MAP)
    parser.add_argument("--target-team", default=DEFAULT_TARGET_TEAM)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--run-pipeline", action="store_true")
    parser.add_argument("--registry-only", action="store_true")
    return parser.parse_args()


def print_summary(outputs: dict[str, Path], summary: dict[str, object]) -> None:
    print("Inferno onboarding summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_onboarding(
        args.config,
        map_name=args.map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
        run_pipeline=args.run_pipeline,
        registry_only=args.registry_only,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
