from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.features.build_feature_contract import run_feature_contract
from src.maps.build_map_registry import SEMANTIC_DESCRIPTIONS
from src.maps.identity import resolve_map_identity
from src.maps.registry import load_map_registry, load_yaml, normalize_id, registry_from_config, validate_map_registry
from src.maps.semantic import place_lookup_from_registry, normalize_place
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "inferno_region_mapping_proposal",
    "inferno_place_region_crosswalk",
    "inferno_physical_region_inventory",
    "inferno_semantic_mapping",
    "inferno_semantic_coverage",
    "inferno_region_coordinate_validation",
    "inferno_candidate_feature_portability_v2",
    "inferno_region_mapping_unknowns",
    "inferno_region_mapping_audit",
]

CONTRACT_VERSION = "v2"
MIN_MAPPED_TICK_SHARE = 0.95
ABSURD_CENTER_SPREAD = 2500.0
REVIEW_CENTER_SPREAD = 1000.0
REVIEW_VERTICAL_SPREAD = 350.0


def run_region_mapping(
    config_path: Path,
    *,
    map_name: str = "Inferno",
    target_team: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, Any]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    registry_path = project_root / "configs" / "maps" / "map_registry.yaml"
    identity = resolve_map_identity(map_name, registry_path=registry_path)
    if identity.map_id != "inferno":
        raise ValueError("Stage 8.7 only writes the Inferno region mapping.")
    target_team = target_team or project.target_teams[0]
    gold_dir = project_root / "data" / "gold"
    area_dir = gold_dir / "maps" / "area_discovery"
    output_dir = gold_dir / "maps" / "inferno" / "region_mapping"
    mapping_config_path = project_root / "configs" / "maps" / "region_mapping" / f"{identity.map_id}.yaml"
    mapping_config = load_mapping_config(mapping_config_path)
    now = now_utc()

    summary = scope_frame(read_with_fallback(area_dir / "map_area_discovery_summary"), identity.map_id, target_team)
    if summary.empty:
        raise FileNotFoundError("Stage 8.6 area discovery summary has no row for Inferno/Vitality.")
    stage_ready = bool(summary.iloc[0].get("ready_for_region_mapping"))
    if not stage_ready:
        raise ValueError("Stage 8.7 is blocked: Inferno ready_for_region_mapping is false in Stage 8.6 outputs.")

    contract_frames, contract_outputs, _ = run_feature_contract(
        config_path,
        force=force,
        dry_run=dry_run,
        target_map=project.target_maps[0],
        contract_version=CONTRACT_VERSION,
    )
    contract = contract_frames["feature_contract"]
    inputs = load_area_inputs(area_dir, identity.map_id, target_team)
    proposal = build_mapping_proposal(inputs, mapping_config)
    crosswalk = build_place_region_crosswalk(proposal)
    physical = build_physical_region_inventory(proposal, inputs["coordinates"])
    semantic_mapping = build_semantic_mapping(physical, contract, mapping_config)
    semantic_coverage = build_semantic_coverage(semantic_mapping, contract, physical)
    coordinate_validation = build_coordinate_validation(proposal, inputs["coordinates"], mapping_config)
    config_yaml = build_inferno_config(identity, physical, semantic_mapping, mapping_config)
    registry_index = build_registry_index(registry_path, inferno_active=True)
    registry_validation = validate_inferno_registry(project_root, config_yaml, crosswalk)
    candidate = build_candidate_portability(contract, semantic_coverage, read_with_fallback(gold_dir / "modeling" / "t_side_ab_candidate" / "candidate_model_feature_set"))
    unknowns = build_unknowns(crosswalk, semantic_coverage, coordinate_validation, candidate, registry_validation)
    audit = build_audit(
        identity=identity,
        target_team=target_team,
        summary=summary,
        proposal=proposal,
        crosswalk=crosswalk,
        physical=physical,
        semantic_coverage=semantic_coverage,
        candidate=candidate,
        unknowns=unknowns,
        registry_validation=registry_validation,
        contract=contract,
        project_root=project_root,
        created_at=now,
    )
    audit["mapping_config_path"] = str(mapping_config_path.relative_to(project_root))
    frames = {
        "inferno_region_mapping_proposal": proposal,
        "inferno_place_region_crosswalk": crosswalk,
        "inferno_physical_region_inventory": physical,
        "inferno_semantic_mapping": semantic_mapping,
        "inferno_semantic_coverage": semantic_coverage,
        "inferno_region_coordinate_validation": coordinate_validation,
        "inferno_candidate_feature_portability_v2": candidate,
        "inferno_region_mapping_unknowns": unknowns,
        "inferno_region_mapping_audit": audit,
    }

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs.update(write_outputs(frames, output_dir, force=force))
        outputs["inferno_config"] = write_text(yaml.safe_dump(config_yaml, sort_keys=False, allow_unicode=False), project_root / "configs" / "maps" / "inferno.yaml", force=force)
        outputs["map_registry_config"] = write_text(yaml.safe_dump(registry_index, sort_keys=False, allow_unicode=False), registry_path, force=force)
        load_map_registry("Inferno", registry_path=registry_path)
        outputs["report"] = write_text(build_markdown_report(frames), project_root / "docs" / "inferno_region_mapping.md", force=force)
        outputs["notebook"] = write_text(build_notebook_json(), project_root / "notebooks" / "21_inferno_region_mapping.ipynb", force=force)
        outputs.update({f"feature_contract_{key}": value for key, value in contract_outputs.items()})

    summary_result = {
        "observed_places": int(audit.iloc[0]["observed_places"]),
        "mapped_places": int(audit.iloc[0]["mapped_places"]),
        "mapped_tick_share": float(audit.iloc[0]["mapped_tick_share"]),
        "physical_regions": int(audit.iloc[0]["physical_regions"]),
        "required_semantics": int(audit.iloc[0]["required_semantics"]),
        "missing_semantics": int(audit.iloc[0]["missing_semantics"]),
        "candidate_features": int(audit.iloc[0]["candidate_features"]),
        "candidate_features_cross_map_comparable": int(audit.iloc[0]["candidate_features_cross_map_comparable"]),
        "ready_for_inferno_feature_run": bool(audit.iloc[0]["ready_for_inferno_feature_run"]),
        "status": str(audit.iloc[0]["status"]),
    }
    return frames, outputs, summary_result


def load_area_inputs(area_dir: Path, map_id: str, target_team: str) -> dict[str, pd.DataFrame]:
    return {
        "inventory": scope_frame(read_with_fallback(area_dir / "inferno_place_discovery"), map_id, target_team),
        "coordinates": scope_frame(read_with_fallback(area_dir / "map_place_coordinates"), map_id, target_team),
        "coverage": scope_frame(read_with_fallback(area_dir / "map_place_coverage"), map_id, target_team),
        "stability": scope_frame(read_with_fallback(area_dir / "map_place_name_stability"), map_id, target_team),
        "vertical": scope_frame(read_with_fallback(area_dir / "map_place_vertical_profile"), map_id, target_team),
    }


def scope_frame(frame: pd.DataFrame, map_id: str, target_team: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    if "map_id" in result.columns:
        result = result[result["map_id"].astype(str).map(normalize_id).eq(map_id)].copy()
    if "target_team" in result.columns:
        result = result[result["target_team"].astype(str).str.casefold().eq(target_team.casefold())].copy()
    return result.reset_index(drop=True)


def load_mapping_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Region mapping policy config not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Region mapping policy config must be a mapping: {path}")
    if "place_mappings" not in config or not isinstance(config["place_mappings"], dict):
        raise ValueError(f"Region mapping policy config missing place_mappings: {path}")
    return config


def normalized_place_mappings(mapping_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mappings = mapping_config.get("place_mappings", {})
    return {normalize_id(str(key)): value for key, value in mappings.items() if isinstance(value, dict)}


def mapping_semantics(mapping_config: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for mapping in normalized_place_mappings(mapping_config).values():
        tags.update(str(tag) for tag in mapping.get("semantic_tags", []) if str(tag))
    return tags


def build_mapping_proposal(inputs: dict[str, pd.DataFrame], mapping_config: dict[str, Any]) -> pd.DataFrame:
    inventory = inputs["inventory"].copy()
    if inventory.empty:
        raise FileNotFoundError("Stage 8.6 inferno_place_discovery is empty.")
    stability = inputs["stability"][["raw_place", "coordinate_consistency_status"]].drop_duplicates("raw_place") if not inputs["stability"].empty else pd.DataFrame()
    proposal = inventory.merge(stability, on="raw_place", how="left")
    rows = []
    for _, row in proposal.sort_values("tick_count", ascending=False).iterrows():
        normalized = str(row["normalized_place_id"])
        mapped = mapping_for_place(normalized, str(row["raw_place"]), mapping_config)
        evidence = [
            f"tick_count={int(row.get('tick_count', 0))}",
            f"demo_count={int(row.get('demo_count', 0))}",
            f"round_count={int(row.get('round_count', 0))}",
            f"coordinate_status={row.get('coordinate_consistency_status') or 'unknown'}",
        ]
        rows.append(
            {
                "map_id": row.get("map_id"),
                "raw_place": row.get("raw_place"),
                "normalized_place_id": normalized,
                "tick_count": int(row.get("tick_count", 0)),
                "tick_share": safe_share(row.get("tick_count", 0), inventory["tick_count"].sum()),
                "demo_count": int(row.get("demo_count", 0)),
                "round_count": int(row.get("round_count", 0)),
                "x_median": row.get("x_median"),
                "y_median": row.get("y_median"),
                "z_median": row.get("z_median"),
                "coordinate_consistency_status": row.get("coordinate_consistency_status") or "unknown",
                "proposed_region_id": mapped["region_id"],
                "proposed_region_display_name": mapped["display_name"],
                "mapping_type": mapped["mapping_type"],
                "mapping_confidence": mapped["mapping_confidence"],
                "semantic_tags": "|".join(mapped["semantic_tags"]),
                "evidence": "; ".join(evidence),
                "review_status": mapped["review_status"],
                "review_basis": "|".join(mapped["review_basis"]),
                "notes": mapped["notes"],
            }
        )
    return pd.DataFrame(rows)


def mapping_for_place(normalized: str, raw_place: str, mapping_config: dict[str, Any]) -> dict[str, Any]:
    configured = normalized_place_mappings(mapping_config).get(normalized)
    if not configured:
        return {
            "region_id": None,
            "display_name": humanize_place(raw_place),
            "mapping_type": "unresolved",
            "mapping_confidence": "low",
            "semantic_tags": [],
            "review_status": "review_required",
            "review_basis": ["parser_place_name"],
            "notes": "No mapping policy entry exists for this parser place.",
        }
    return {
        "region_id": configured.get("region_id"),
        "display_name": configured.get("display_name") or humanize_place(raw_place),
        "mapping_type": configured.get("mapping_type", "direct"),
        "mapping_confidence": configured.get("mapping_confidence", "medium"),
        "semantic_tags": list(configured.get("semantic_tags", [])),
        "review_status": configured.get("review_status", "accepted_from_config"),
        "review_basis": list(configured.get("review_basis", [])),
        "notes": configured.get("notes", "Mapped from region mapping policy config."),
    }


def build_place_region_crosswalk(proposal: pd.DataFrame) -> pd.DataFrame:
    frame = proposal.copy()
    frame["region_id"] = frame["proposed_region_id"]
    frame["region_display_name"] = frame["proposed_region_display_name"]
    frame["mapped"] = frame["region_id"].notna() & frame["region_id"].astype(str).ne("")
    frame["ambiguous"] = frame["normalized_place_id"].duplicated(keep=False)
    frame["review_required"] = frame["review_status"].eq("review_required") | frame["ambiguous"]
    return frame[
        [
            "raw_place",
            "normalized_place_id",
            "tick_count",
            "tick_share",
            "region_id",
            "region_display_name",
            "mapping_type",
            "mapping_confidence",
            "semantic_tags",
            "mapped",
            "ambiguous",
            "review_required",
            "review_status",
            "review_basis",
            "notes",
        ]
    ].copy()


def build_physical_region_inventory(proposal: pd.DataFrame, coordinates: pd.DataFrame) -> pd.DataFrame:
    mapped = proposal[proposal["proposed_region_id"].notna() & proposal["proposed_region_id"].astype(str).ne("")].copy()
    coord = coordinates.drop_duplicates("raw_place") if not coordinates.empty else pd.DataFrame()
    merged = mapped.merge(coord, on=["raw_place", "normalized_place_id"], how="left", suffixes=("", "_coord"))
    rows = []
    total_ticks = int(mapped["tick_count"].sum())
    for region_id, group in merged.groupby("proposed_region_id", sort=True):
        tags = sorted(set(tag for value in group["semantic_tags"].dropna().astype(str) for tag in value.split("|") if tag))
        area_names = sorted(group["raw_place"].dropna().astype(str).unique())
        rows.append(
            {
                "region_id": region_id,
                "display_name": group["proposed_region_display_name"].dropna().astype(str).iloc[0],
                "geometry_type": "named_area",
                "source_place_count": len(area_names),
                "source_places": "|".join(area_names),
                "tick_count": int(group["tick_count"].sum()),
                "tick_share": safe_share(group["tick_count"].sum(), total_ticks),
                "semantic_tags": "|".join(tags),
                "mapping_confidence": aggregate_confidence(group["mapping_confidence"]),
                "status": "active",
                "notes": region_notes(group),
            }
        )
    return pd.DataFrame(rows).sort_values(["tick_count", "region_id"], ascending=[False, True]).reset_index(drop=True)


def build_semantic_mapping(physical: pd.DataFrame, contract: pd.DataFrame, mapping_config: dict[str, Any]) -> pd.DataFrame:
    required = required_semantics(contract)
    all_semantics = sorted(required | mapping_semantics(mapping_config) | {"site_a", "site_b", "t_spawn_area", "rotation"})
    rows = []
    for semantic_id in all_semantics:
        members = physical[physical["semantic_tags"].fillna("").str.split("|").map(lambda values: semantic_id in values)]
        features = required_features(contract, semantic_id)
        source_places = sorted(set(place for value in members["source_places"].dropna().astype(str) for place in value.split("|") if place))
        resolved = not members.empty
        coverage = "resolved" if resolved else ("missing" if semantic_id in required else "not_applicable")
        rows.append(
            {
                "semantic_id": semantic_id,
                "required_by_feature_count": len(features),
                "required_features": "|".join(features),
                "physical_region_count": len(members),
                "physical_regions": "|".join(members["region_id"].astype(str)),
                "source_places": "|".join(source_places),
                "mapping_confidence": aggregate_confidence(members["mapping_confidence"]) if resolved else "low",
                "mapping_basis": mapping_basis_for_semantic(semantic_id, required=semantic_id in required),
                "resolved": resolved,
                "coverage_status": coverage,
                "notes": "Resolved from observed Inferno parser places." if resolved else "No reliable Inferno physical regions mapped for this semantic.",
            }
        )
    return pd.DataFrame(rows)


def build_semantic_coverage(semantic_mapping: pd.DataFrame, contract: pd.DataFrame, physical: pd.DataFrame) -> pd.DataFrame:
    rows = []
    tick_by_region = physical.set_index("region_id")["tick_count"].to_dict() if not physical.empty else {}
    total_ticks = float(physical["tick_count"].sum()) if not physical.empty else 0.0
    for _, row in semantic_mapping.iterrows():
        semantic_id = str(row["semantic_id"])
        features = required_features(contract, semantic_id)
        blocking = bool(features and not row["resolved"])
        region_ids = split_pipe(row["physical_regions"])
        observed_ticks = int(sum(tick_by_region.get(region_id, 0) for region_id in region_ids))
        rows.append(
            {
                "semantic_id": semantic_id,
                "frozen_feature_count": len(features),
                "resolved": bool(row["resolved"]),
                "physical_regions": row["physical_regions"],
                "source_places": row["source_places"],
                "observed_tick_count": observed_ticks,
                "observed_tick_share": safe_share(observed_ticks, total_ticks),
                "coverage_status": "missing" if blocking else row["coverage_status"],
                "blocking": blocking,
                "notes": "Critical frozen semantic is covered." if features and row["resolved"] else row["notes"],
            }
        )
    frame = pd.DataFrame(rows)
    return frame


def build_coordinate_validation(proposal: pd.DataFrame, coordinates: pd.DataFrame, mapping_config: dict[str, Any] | None = None) -> pd.DataFrame:
    mapping_config = mapping_config or {}
    thresholds = mapping_config.get("thresholds", {})
    absurd_center_spread = float(thresholds.get("absurd_center_spread", ABSURD_CENTER_SPREAD))
    review_center_spread = float(thresholds.get("review_center_spread", REVIEW_CENTER_SPREAD))
    review_vertical_spread = float(thresholds.get("review_vertical_spread", REVIEW_VERTICAL_SPREAD))
    coord = coordinates.drop_duplicates("raw_place") if not coordinates.empty else pd.DataFrame()
    merged = proposal.merge(coord, on=["raw_place", "normalized_place_id"], how="left", suffixes=("", "_coord"))
    rows = []
    for region_id, group in merged.groupby("proposed_region_id", dropna=True, sort=True):
        places = sorted(group["raw_place"].dropna().astype(str).unique())
        center_spread = max_center_spread(group)
        vertical_spread = numeric_range(group, "z_min", "z_max")
        if center_spread > absurd_center_spread:
            status = "failed"
            notes = "Grouped source places are spatially incompatible."
        elif center_spread > review_center_spread or vertical_spread > review_vertical_spread:
            status = "review_required"
            notes = "Grouped/source place spread is elevated and should be manually reviewed."
        else:
            status = "ok"
            notes = "Coordinate distribution is plausible for named-area mapping."
        rows.append(
            {
                "region_id": region_id,
                "source_place_count": len(places),
                "source_places": "|".join(places),
                "x_min": group.get("x_min", pd.Series(dtype=float)).min(),
                "x_max": group.get("x_max", pd.Series(dtype=float)).max(),
                "y_min": group.get("y_min", pd.Series(dtype=float)).min(),
                "y_max": group.get("y_max", pd.Series(dtype=float)).max(),
                "z_min": group.get("z_min", pd.Series(dtype=float)).min(),
                "z_max": group.get("z_max", pd.Series(dtype=float)).max(),
                "center_spread": center_spread,
                "vertical_spread": vertical_spread,
                "coordinate_consistency": aggregate_coordinate_consistency(group),
                "status": status,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def build_inferno_config(identity, physical: pd.DataFrame, semantic_mapping: pd.DataFrame, mapping_config: dict[str, Any]) -> dict[str, Any]:
    physical_regions = []
    aliases = {}
    for index, row in enumerate(physical.to_dict("records"), start=1):
        area_names = split_pipe(row["source_places"])
        semantic_tags = split_pipe(row["semantic_tags"])
        region_id = str(row["region_id"])
        aliases[region_id] = sorted(set([str(row["display_name"]), region_id, *area_names]))
        physical_regions.append(
            {
                "region_id": region_id,
                "display_name": row["display_name"],
                "geometry": {
                    "type": "named_area",
                    "source": "stage_8_6_parser_place_inventory",
                    "area_names": area_names,
                    "notes": "Uses observed CS2 parser/nav place names; no custom bbox added in Stage 8.7.",
                },
                "semantic_tags": semantic_tags,
                "site_affinity": site_affinity(semantic_tags),
                "region_scope": "map_specific",
                "priority": 100 - index,
                "boundary_policy": "existing_behavior",
                "aliases": aliases[region_id],
                "status": "active",
                "notes": row["notes"],
            }
        )
    semantic_groups = {
        row["semantic_id"]: {
            "description": SEMANTIC_DESCRIPTIONS.get(row["semantic_id"], f"Inferno tactical semantic group: {row['semantic_id']}."),
            "member_regions": split_pipe(row["physical_regions"]),
            "status": "active" if bool(row["resolved"]) else "unresolved",
            "notes": row["notes"],
        }
        for row in semantic_mapping.to_dict("records")
        if split_pipe(row["physical_regions"]) or bool(row["required_by_feature_count"])
    }
    return {
        "map_id": identity.map_id,
        "display_name": identity.display_name,
        "game_map_name": identity.game_map_name,
        "region_schema_version": "v1",
        "boundary_policy": "existing_behavior",
        "coordinate_system": {
            "source": "awpy_parser_named_areas",
            "axis_x": "x",
            "axis_y": "y",
            "axis_z": "z",
            "place_column_candidates": ["last_place_name", "place_name", "player_last_place_name", "place"],
            "notes": "Inferno registry uses Stage 8.6 observed parser place names through geometry.area_names.",
        },
        "physical_regions": physical_regions,
        "semantic_groups": semantic_groups,
        "aliases": aliases,
        "bombsites": {
            site: {"region_ids": [region_id], "notes": f"Resolved from region mapping policy config for site {site}."}
            for site, region_id in mapping_config.get("bombsites", {"A": "bombsitea", "B": "bombsiteb"}).items()
        },
    }


def build_registry_index(registry_path: Path, *, inferno_active: bool) -> dict[str, Any]:
    index = load_yaml(registry_path)
    maps = index.setdefault("maps", [])
    inferno = None
    for entry in maps:
        if normalize_id(str(entry.get("map_id") or "")) == "inferno":
            inferno = entry
            break
    if inferno is None:
        inferno = {
            "map_id": "inferno",
            "display_name": "Inferno",
            "game_map_name": "de_inferno",
            "config_path": "configs/maps/inferno.yaml",
            "region_schema_version": "v1",
            "is_reference_map": False,
        }
        maps.append(inferno)
    inferno.update(
        {
            "status": "active" if inferno_active else "onboarding",
            "is_reference_map": False,
            "notes": "Inferno physical region and tactical semantic mapping resolved from Stage 8.6 observed parser places.",
        }
    )
    return index


def validate_inferno_registry(project_root: Path, config_yaml: dict[str, Any], crosswalk: pd.DataFrame) -> dict[str, Any]:
    registry = registry_from_config(config_yaml, registry_version="v1", source_path=project_root / "configs" / "maps" / "inferno.yaml")
    validate_map_registry(registry)
    lookup = place_lookup_from_registry(registry)
    unresolved_places = []
    conflicting = []
    for _, row in crosswalk[crosswalk["mapped"]].iterrows():
        key = normalize_place(row["raw_place"])
        if key not in lookup:
            unresolved_places.append(str(row["raw_place"]))
        elif normalize_id(lookup[key][0]) != normalize_id(str(row["region_display_name"])):
            conflicting.append(str(row["raw_place"]))
    bombsite_a = "bombsitea" in {region.region_id for region in registry.regions_for_site("A")}
    bombsite_b = "bombsiteb" in {region.region_id for region in registry.regions_for_site("B")}
    return {
        "valid": not unresolved_places and not conflicting and bombsite_a and bombsite_b,
        "unresolved_places": unresolved_places,
        "conflicting_places": conflicting,
        "bombsite_a_resolved": bombsite_a,
        "bombsite_b_resolved": bombsite_b,
    }


def build_candidate_portability(contract: pd.DataFrame, semantic_coverage: pd.DataFrame, candidate_set: pd.DataFrame) -> pd.DataFrame:
    features = candidate_features(candidate_set)
    contract_by_feature = contract.drop_duplicates("feature_name").set_index("feature_name")
    resolved_semantics = set(semantic_coverage[semantic_coverage["resolved"]]["semantic_id"]) if not semantic_coverage.empty else set()
    rows = []
    for index, item in enumerate(features, start=1):
        feature_name = item["feature_name"]
        row = contract_by_feature.loc[feature_name] if feature_name in contract_by_feature.index else pd.Series(dtype=object)
        required_semantic = row.get("region_semantic")
        semantic_resolved = bool(not required_semantic or pd.isna(required_semantic) or required_semantic in resolved_semantics)
        map_scope = row.get("map_scope", "unknown")
        available = bool(map_scope == "global" or (map_scope == "map_abstract" and semantic_resolved))
        if row.empty:
            status = "not_in_contract"
            notes = "Candidate feature is absent from the current Feature Contract."
        elif map_scope == "map_specific":
            status = "map_specific"
            notes = "Feature is generated from a map-specific Mirage term and is not available on Inferno without a manual equivalent."
        elif not semantic_resolved:
            status = "missing_semantic"
            notes = "Required tactical semantic is not resolved in Inferno."
        elif available and bool(row.get("cross_map_comparable")):
            status = "available_comparable"
            notes = "Feature can be generated on Inferno and compared through the contract mode."
        elif available:
            status = "available_not_comparable"
            notes = "Feature can be generated on Inferno, but direct cross-map comparison is not approved."
        else:
            status = "unknown"
            notes = "Portability status could not be determined."
        rows.append(
            {
                "candidate_id": item.get("candidate_id") or f"candidate_feature_{index:03d}",
                "feature_name": feature_name,
                "generation_scope": row.get("generation_scope", map_scope),
                "coordinate_dependency": row.get("coordinate_dependency", "unknown"),
                "available_on_inferno": available,
                "cross_map_comparable": bool(row.get("cross_map_comparable", False)),
                "cross_map_comparison_mode": row.get("cross_map_comparison_mode", "unknown"),
                "required_semantic": required_semantic,
                "semantic_resolved": semantic_resolved,
                "status": status,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)


def build_unknowns(
    crosswalk: pd.DataFrame,
    semantic_coverage: pd.DataFrame,
    coordinate_validation: pd.DataFrame,
    candidate: pd.DataFrame,
    registry_validation: dict[str, Any],
) -> pd.DataFrame:
    rows = []
    unknown_id = 1
    for _, row in crosswalk[~crosswalk["mapped"]].iterrows():
        rows.append(unknown(unknown_id, raw_place=row["raw_place"], category="unmapped_place", reason="Raw place has no physical region mapping.", severity="medium", blocking=False, action="Review Stage 8.6 evidence and add a named_area mapping if needed."))
        unknown_id += 1
    for _, row in semantic_coverage[semantic_coverage["blocking"]].iterrows():
        rows.append(unknown(unknown_id, semantic_id=row["semantic_id"], category="missing_semantic", reason="Critical frozen map-abstract semantic is missing for Inferno.", severity="high", blocking=True, action="Map observed physical regions to this semantic before feature generation."))
        unknown_id += 1
    for _, row in coordinate_validation[coordinate_validation["status"].isin(["review_required", "failed"])].iterrows():
        rows.append(unknown(unknown_id, region_id=row["region_id"], category="coordinate_inconsistency", reason=row["notes"], severity="high" if row["status"] == "failed" else "medium", blocking=row["status"] == "failed", action="Inspect coordinate samples before using the grouped physical region."))
        unknown_id += 1
    for _, row in candidate[candidate["status"].isin(["map_specific", "missing_semantic", "not_in_contract"])].iterrows():
        rows.append(unknown(unknown_id, feature_name=row["feature_name"], semantic_id=row.get("required_semantic"), category="feature_portability", reason=row["notes"], severity="medium", blocking=False, action="Keep this feature out of direct Mirage x Inferno comparisons until resolved."))
        unknown_id += 1
    for place in registry_validation.get("unresolved_places", []):
        rows.append(unknown(unknown_id, raw_place=place, category="registry_issue", reason="Mapped raw place does not resolve through registry lookup.", severity="high", blocking=True, action="Fix geometry.area_names or aliases."))
        unknown_id += 1
    for place in registry_validation.get("conflicting_places", []):
        rows.append(unknown(unknown_id, raw_place=place, category="ambiguous_physical_region", reason="Raw place resolves to a conflicting physical region.", severity="high", blocking=True, action="Remove duplicate/conflicting raw-place mapping."))
        unknown_id += 1
    if not registry_validation.get("bombsite_a_resolved"):
        rows.append(unknown(unknown_id, category="registry_issue", reason="Bombsite A is not resolved.", severity="high", blocking=True, action="Map BombsiteA to bombsite A."))
        unknown_id += 1
    if not registry_validation.get("bombsite_b_resolved"):
        rows.append(unknown(unknown_id, category="registry_issue", reason="Bombsite B is not resolved.", severity="high", blocking=True, action="Map BombsiteB to bombsite B."))
    return pd.DataFrame(rows, columns=["unknown_id", "raw_place", "region_id", "semantic_id", "feature_name", "category", "reason", "severity", "blocking", "recommended_action"])


def build_audit(
    *,
    identity,
    target_team: str,
    summary: pd.DataFrame,
    proposal: pd.DataFrame,
    crosswalk: pd.DataFrame,
    physical: pd.DataFrame,
    semantic_coverage: pd.DataFrame,
    candidate: pd.DataFrame,
    unknowns: pd.DataFrame,
    registry_validation: dict[str, Any],
    contract: pd.DataFrame,
    project_root: Path,
    created_at: str,
) -> pd.DataFrame:
    mapped = crosswalk[crosswalk["mapped"]]
    required = semantic_coverage[semantic_coverage["frozen_feature_count"] > 0]
    missing = required[~required["resolved"]]
    candidate_available = candidate[candidate["available_on_inferno"]] if not candidate.empty else pd.DataFrame()
    critical_unknowns = int(unknowns["blocking"].sum()) if not unknowns.empty else 0
    mirage_passed = latest_mirage_regression_passed(project_root)
    registry_valid = bool(registry_validation["valid"])
    source_ticks = int(first_numeric(summary.iloc[0], "source_ticks", "tick_count", default=int(crosswalk["tick_count"].sum())))
    non_null_place_ticks = int(first_numeric(summary.iloc[0], "non_null_place_ticks", "place_non_null_rows", default=source_ticks))
    valid_named_place_ticks = int(first_numeric(summary.iloc[0], "valid_named_place_ticks", "valid_place_rows", default=int(crosswalk["tick_count"].sum())))
    blank_place_ticks = int(first_numeric(summary.iloc[0], "blank_place_ticks", default=max(non_null_place_ticks - valid_named_place_ticks, 0)))
    invalid_place_ticks = int(first_numeric(summary.iloc[0], "invalid_place_ticks", default=max(source_ticks - non_null_place_ticks, 0)))
    mapped_ticks = int(mapped["tick_count"].sum())
    mapped_share_of_valid_named_place_ticks = safe_share(mapped_ticks, valid_named_place_ticks)
    mapped_share_of_all_ticks = safe_share(mapped_ticks, source_ticks)
    mapped_tick_share = mapped_share_of_valid_named_place_ticks
    ready = bool(
        bool(summary.iloc[0]["ready_for_region_mapping"])
        and registry_valid
        and registry_validation["bombsite_a_resolved"]
        and registry_validation["bombsite_b_resolved"]
        and missing.empty
        and mapped_share_of_valid_named_place_ticks >= MIN_MAPPED_TICK_SHARE
        and critical_unknowns == 0
        and mirage_passed
    )
    return pd.DataFrame(
        [
            {
                "audit_id": "inferno_region_mapping_stage_8_7",
                "map_id": identity.map_id,
                "target_team": target_team,
                "stage_8_6_ready": bool(summary.iloc[0]["ready_for_region_mapping"]),
                "observed_places": len(crosswalk),
                "mapped_places": int(crosswalk["mapped"].sum()),
                "unmapped_places": int((~crosswalk["mapped"]).sum()),
                "observed_ticks": valid_named_place_ticks,
                "source_ticks": source_ticks,
                "non_null_place_ticks": non_null_place_ticks,
                "valid_named_place_ticks": valid_named_place_ticks,
                "blank_place_ticks": blank_place_ticks,
                "invalid_place_ticks": invalid_place_ticks,
                "mapped_ticks": mapped_ticks,
                "mapped_tick_share": mapped_tick_share,
                "mapped_share_of_valid_named_place_ticks": mapped_share_of_valid_named_place_ticks,
                "mapped_share_of_all_ticks": mapped_share_of_all_ticks,
                "physical_regions": len(physical),
                "required_semantics": len(required),
                "resolved_semantics": int(required["resolved"].sum()),
                "missing_semantics": len(missing),
                "bombsite_a_resolved": bool(registry_validation["bombsite_a_resolved"]),
                "bombsite_b_resolved": bool(registry_validation["bombsite_b_resolved"]),
                "frozen_map_abstract_features": int(required["frozen_feature_count"].sum()),
                "supported_map_abstract_features": int(required[required["resolved"]]["frozen_feature_count"].sum()),
                "unsupported_map_abstract_features": int(missing["frozen_feature_count"].sum()) if not missing.empty else 0,
                "candidate_features": len(candidate),
                "candidate_features_available": len(candidate_available),
                "candidate_features_cross_map_comparable": int(candidate["cross_map_comparable"].sum()) if not candidate.empty else 0,
                "feature_contract_version": contract["feature_contract_version"].iloc[0] if not contract.empty else CONTRACT_VERSION,
                "mirage_regression_passed": mirage_passed,
                "critical_unknowns": critical_unknowns,
                "warnings": int(len(unknowns) - critical_unknowns),
                "ready_for_inferno_feature_run": ready,
                "status": "ok" if ready else "warning",
                "created_at": created_at,
            }
        ]
    )


def read_with_fallback(base_path: Path) -> pd.DataFrame:
    parquet = base_path.with_suffix(".parquet")
    csv = base_path.with_suffix(".csv")
    if parquet.exists():
        return read_catalog(parquet)
    if csv.exists():
        return read_catalog(csv)
    return pd.DataFrame()


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs = {}
    for name in OUTPUT_NAMES:
        outputs.update(write_pair(frames[name], output_dir / name, force=force))
    return outputs


def write_pair(frame: pd.DataFrame, base_path: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(base_path.parent)
    frame = sanitize_for_parquet(frame)
    csv_path = base_path.with_suffix(".csv")
    parquet_path = base_path.with_suffix(".parquet")
    if force or not csv_path.exists():
        frame.to_csv(csv_path, index=False)
    if force or not parquet_path.exists():
        frame.to_parquet(parquet_path, index=False)
    return {csv_path.name: csv_path, parquet_path.name: parquet_path}


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def sanitize_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if result[column].dtype == "object":
            result[column] = result[column].map(lambda value: None if value is None or pd.isna(value) else value)
    return result


def required_semantics(contract: pd.DataFrame) -> set[str]:
    if contract.empty:
        return set()
    selected = contract[
        contract["feature_status"].eq("frozen")
        & contract["map_scope"].eq("map_abstract")
        & contract["region_dependency"].fillna(False)
    ]
    return {str(value) for value in selected["region_semantic"].dropna().unique() if str(value) != "unknown"}


def required_features(contract: pd.DataFrame, semantic_id: str) -> list[str]:
    if contract.empty:
        return []
    selected = contract[
        contract["feature_status"].eq("frozen")
        & contract["map_scope"].eq("map_abstract")
        & contract["region_dependency"].fillna(False)
        & contract["region_semantic"].eq(semantic_id)
    ]
    return sorted(selected["feature_name"].dropna().astype(str).tolist())


def candidate_features(candidate_set: pd.DataFrame) -> list[dict[str, Any]]:
    if candidate_set.empty or "feature_name" not in candidate_set.columns:
        return []
    rows = []
    for _, row in candidate_set.iterrows():
        name = str(row.get("feature_name") or "")
        if not name or name.startswith("__"):
            continue
        rows.append({"candidate_id": row.get("candidate_id"), "feature_name": name})
    return rows


def latest_mirage_regression_passed(project_root: Path) -> bool:
    path = project_root / "data" / "gold" / "validation" / "mirage_regression_gate" / "mirage_regression_summary.parquet"
    if not path.exists():
        return False
    frame = read_catalog(path)
    if frame.empty:
        return False
    return str(frame.iloc[0].get("overall_status") or "").casefold() == "passed"


def unknown(
    unknown_id: int,
    *,
    raw_place: object = None,
    region_id: object = None,
    semantic_id: object = None,
    feature_name: object = None,
    category: str,
    reason: str,
    severity: str,
    blocking: bool,
    action: str,
) -> dict[str, Any]:
    return {
        "unknown_id": f"inferno_region_mapping_unknown_{unknown_id:03d}",
        "raw_place": raw_place,
        "region_id": region_id,
        "semantic_id": semantic_id,
        "feature_name": feature_name,
        "category": category,
        "reason": reason,
        "severity": severity,
        "blocking": blocking,
        "recommended_action": action,
    }


def aggregate_confidence(values: pd.Series) -> str:
    ordered = {"high": 3, "medium": 2, "low": 1}
    scores = [ordered.get(str(value), 1) for value in values.dropna()]
    if not scores:
        return "low"
    return {3: "high", 2: "medium", 1: "low"}[min(scores)]


def aggregate_coordinate_consistency(group: pd.DataFrame) -> str:
    values = set(group.get("coordinate_consistency_status", pd.Series(dtype=str)).dropna().astype(str))
    if not values:
        return "unknown"
    if values == {"stable"}:
        return "stable"
    return "|".join(sorted(values))


def region_notes(group: pd.DataFrame) -> str:
    if set(group["mapping_type"]) == {"grouped"}:
        return "Grouped named-area physical region from Stage 8.6 place evidence."
    return group["notes"].dropna().astype(str).iloc[0]


def site_affinity(tags: list[str]) -> list[str]:
    sites = []
    if "site_a" in tags or "a_pressure" in tags:
        sites.append("A")
    if "site_b" in tags or "b_pressure" in tags:
        sites.append("B")
    return sites


def mapping_basis_for_semantic(semantic_id: str, *, required: bool) -> str:
    basis = ["raw_place_name", "coordinate_location", "manual_tactical_interpretation"]
    if required:
        basis.append("Feature Contract frozen map-abstract requirement")
    if semantic_id in {"mid_control", "a_pressure", "b_pressure", "ct_space", "rotation"}:
        basis.append("Mirage semantic definition")
    return "|".join(basis)


def max_center_spread(group: pd.DataFrame) -> float:
    centers = [
        (float(row["x_median"]), float(row["y_median"]), float(row["z_median"]))
        for _, row in group.dropna(subset=["x_median", "y_median", "z_median"]).iterrows()
    ]
    if len(centers) < 2:
        return 0.0
    return max(math.dist(left, right) for index, left in enumerate(centers) for right in centers[index + 1 :])


def numeric_range(group: pd.DataFrame, min_column: str, max_column: str) -> float:
    if min_column not in group.columns or max_column not in group.columns:
        return 0.0
    low = pd.to_numeric(group[min_column], errors="coerce").min()
    high = pd.to_numeric(group[max_column], errors="coerce").max()
    if pd.isna(low) or pd.isna(high):
        return 0.0
    return float(high - low)


def split_pipe(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None and str(item)]
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    return [item for item in str(value).split("|") if item]


def safe_share(value: object, total: object) -> float:
    total_float = float(total or 0)
    return float(value or 0) / total_float if total_float else 0.0


def first_numeric(row: pd.Series, *columns: str, default: int = 0) -> float:
    for column in columns:
        if column in row.index:
            value = row.get(column)
            try:
                if pd.notna(value):
                    return float(value)
            except (TypeError, ValueError):
                continue
    return float(default)


def humanize_place(value: str) -> str:
    text = str(value)
    return text[:1].upper() + text[1:]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_markdown_report(frames: dict[str, pd.DataFrame]) -> str:
    audit = frames["inferno_region_mapping_audit"]
    proposal = frames["inferno_region_mapping_proposal"]
    semantic = frames["inferno_semantic_mapping"]
    coverage = frames["inferno_semantic_coverage"]
    coordinate = frames["inferno_region_coordinate_validation"]
    candidate = frames["inferno_candidate_feature_portability_v2"]
    unknowns = frames["inferno_region_mapping_unknowns"]
    grouped = proposal[proposal["mapping_type"].eq("grouped")]
    return "\n".join(
        [
            "# Inferno Physical Region & Tactical Semantic Mapping",
            "",
            "## Purpose",
            "Formalize Inferno parser places into auditable physical regions and tactical semantic groups before running Inferno features.",
            "",
            "## Stage 8.6 Evidence",
            markdown_table(audit, ["observed_places", "source_ticks", "valid_named_place_ticks", "blank_place_ticks", "mapped_ticks", "mapped_share_of_valid_named_place_ticks", "mapped_share_of_all_ticks", "stage_8_6_ready", "ready_for_inferno_feature_run", "status"]),
            "",
            "## Raw Parser Places",
            markdown_table(proposal, ["raw_place", "tick_count", "demo_count", "round_count", "x_median", "y_median", "z_median"], top_n=40),
            "",
            "## Physical Region Mapping",
            markdown_table(proposal, ["raw_place", "proposed_region_id", "mapping_type", "mapping_confidence", "semantic_tags", "review_status"], top_n=40),
            "",
            "## Grouped Places",
            markdown_table(grouped, ["raw_place", "proposed_region_id", "semantic_tags", "mapping_confidence", "review_status", "review_basis", "notes"], top_n=20),
            "",
            "## Unresolved Places",
            markdown_table(proposal[proposal["mapping_type"].eq("unresolved")], ["raw_place", "notes"]),
            "",
            "## Bombsites",
            "BombsiteA resolves to `bombsitea` / A and BombsiteB resolves to `bombsiteb` / B through `geometry.area_names`.",
            "",
            "## Tactical Semantic Groups",
            markdown_table(semantic, ["semantic_id", "physical_region_count", "physical_regions", "source_places", "mapping_confidence", "coverage_status"], top_n=30),
            "",
            "## Semantic Coverage",
            markdown_table(coverage, ["semantic_id", "frozen_feature_count", "resolved", "physical_regions", "coverage_status", "blocking"], top_n=30),
            "",
            "## Coordinate Validation",
            markdown_table(coordinate, ["region_id", "source_place_count", "source_places", "center_spread", "vertical_spread", "status"], top_n=40),
            "",
            "## Feature Contract v2",
            "Feature Contract v2 adds generation scope, coordinate dependency, and cross-map comparability metadata without changing feature names or feature values.",
            "",
            "## Cross-Map Comparability",
            "A feature being available on Inferno does not mean a Mirage-trained model can predict Inferno. Raw coordinate features require normalization; semantic-region features require validated semantic mapping.",
            "",
            "## Candidate Feature Portability",
            markdown_table(candidate, ["feature_name", "generation_scope", "coordinate_dependency", "available_on_inferno", "cross_map_comparable", "cross_map_comparison_mode", "status"], top_n=40),
            "",
            "## Mirage Regression",
            f"Latest recorded Mirage regression passed: `{str(bool(audit.iloc[0]['mirage_regression_passed'])).lower()}`.",
            "",
            "## Unknowns",
            markdown_table(unknowns, list(unknowns.columns), top_n=40),
            "",
            "## Readiness",
            markdown_table(audit, list(audit.columns)),
            "",
            "## Next Stage",
            "Next: Stage 8.8 -- Inferno Feature Pipeline Run & Multi-Map Gold Storage. Do not start it automatically.",
            "",
        ]
    )


def build_notebook_json() -> str:
    cells = [
        md("# Stage 8.7 -- Inferno Region Mapping"),
        code("from pathlib import Path\nimport matplotlib.pyplot as plt\nimport pandas as pd\nBASE = Path('../data/gold/maps/inferno/region_mapping')\nAREA = Path('../data/gold/maps/area_discovery')\ndef load(name):\n    return pd.read_parquet(BASE / f'{name}.parquet')\nproposal = load('inferno_region_mapping_proposal')\ncrosswalk = load('inferno_place_region_crosswalk')\nphysical = load('inferno_physical_region_inventory')\nsemantic = load('inferno_semantic_mapping')\ncoverage = load('inferno_semantic_coverage')\ncoordinate = load('inferno_region_coordinate_validation')\ncandidate = load('inferno_candidate_feature_portability_v2')\nunknowns = load('inferno_region_mapping_unknowns')\naudit = load('inferno_region_mapping_audit')\nsample = pd.read_parquet(AREA / 'map_place_coordinate_sample.parquet')\nsample = sample[sample['map_id'].eq('inferno')]"),
        md("## Stage 8.6 Inferno Discovery"),
        code("display(audit)"),
        md("## Raw Places"),
        code("display(proposal[['raw_place','tick_count','demo_count','round_count','x_median','y_median','z_median']])"),
        md("## Physical Mapping"),
        code("display(crosswalk)"),
        md("## Coordinate Centers"),
        code("fig, ax = plt.subplots(figsize=(8, 7))\nax.scatter(proposal['x_median'], proposal['y_median'], s=proposal['tick_share'] * 5000 + 20)\nfor _, row in proposal.iterrows():\n    ax.text(row['x_median'], row['y_median'], row['raw_place'], fontsize=8)\nax.set_title('Inferno observed parser places')\nax.set_xlabel('x')\nax.set_ylabel('y')\nax.set_aspect('equal', adjustable='datalim')\nplt.tight_layout()"),
        md("## Grouped Places"),
        code("display(proposal[proposal['mapping_type'].eq('grouped')])"),
        md("## second_mid_upper Coordinate Review"),
        code("import math\nsecond = proposal[proposal['proposed_region_id'].eq('second_mid_upper')].copy()\ncenters = second[['raw_place','x_median','y_median','z_median']].dropna()\npairs = []\nfor i, left in centers.iterrows():\n    for j, right in centers.iterrows():\n        if j <= i:\n            continue\n        pairs.append({'left': left['raw_place'], 'right': right['raw_place'], 'distance': math.dist((left['x_median'], left['y_median'], left['z_median']), (right['x_median'], right['y_median'], right['z_median']))})\npairwise = pd.DataFrame(pairs)\ndisplay(second[['raw_place','proposed_region_id','mapping_confidence','review_status','review_basis','x_median','y_median','z_median']])\ndisplay(pairwise)\nprint('max_center_spread=', 0 if pairwise.empty else pairwise['distance'].max())\nprint('vertical_spread=', second['z_median'].max() - second['z_median'].min())\nassert pairwise.empty or pairwise['distance'].max() <= 1000"),
        md("## Physical Regions"),
        code("display(physical)"),
        md("## Semantic Groups"),
        code("display(semantic)"),
        md("## Semantic Coverage"),
        code("display(coverage)"),
        md("## Candidate Portability"),
        code("display(candidate)"),
        md("## Unknowns"),
        code("display(unknowns)"),
        md("## Mirage Regression Status"),
        code("display(audit[['mirage_regression_passed','ready_for_inferno_feature_run','status']])"),
        md("## Readiness"),
        code("display(audit.T)"),
    ]
    notebook = {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python", "version": "3.11"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1) + "\n"


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    if frame.empty:
        return "_No rows available._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def md(source: str) -> dict[str, object]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code(source: str) -> dict[str, object]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def print_summary(outputs: dict[str, Path], summary: dict[str, Any]) -> None:
    print("Inferno region mapping summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Stage 8.7 Inferno physical region and tactical semantic mapping.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--map", default="Inferno")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_region_mapping(
        args.config,
        map_name=args.map,
        target_team=args.target_team,
        force=args.force,
        dry_run=args.dry_run,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
