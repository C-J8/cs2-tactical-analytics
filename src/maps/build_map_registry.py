from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.config.schemas import load_project_config
from src.features.region_mapping import load_region_config
from src.maps.registry import MapRegistry, load_map_registry, normalize_id, registry_from_config, validate_map_registry
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "map_registry",
    "map_region_registry",
    "map_semantic_groups",
    "map_region_semantic_mapping",
    "map_bombsite_registry",
    "map_feature_semantic_coverage",
    "map_region_unknowns",
    "map_registry_audit",
]

DEFAULT_REGISTRY_VERSION = "v1"
REGION_GROUP_TO_SEMANTIC = {
    "T_SPAWN_AREA": "t_spawn_area",
    "MID_CONTROL": "mid_control",
    "A_PRESSURE": "a_pressure",
    "BOMB_SITE_A": "site_a",
    "B_PRESSURE": "b_pressure",
    "BOMB_SITE_B": "site_b",
    "CT_SPACE": "ct_space",
    "ROTATION_AREA": "rotation",
}
SEMANTIC_DESCRIPTIONS = {
    "t_spawn_area": "Map-dependent areas representing the T-side spawn/start space.",
    "mid_control": "Map-dependent areas representing meaningful control of central tactical space.",
    "a_pressure": "Regions representing meaningful attacking pressure toward bombsite A.",
    "b_pressure": "Regions representing meaningful attacking pressure toward bombsite B.",
    "site_a": "Physical bombsite A regions.",
    "site_b": "Physical bombsite B regions.",
    "ct_space": "Defensive or CT-side space used by current region mapping.",
    "rotation": "Connector or rotation areas linking major tactical spaces.",
}
VALID_GEOMETRY_TYPES = {"bounding_box", "polygon", "named_area", "composite", "existing_definition"}


def run_map_registry(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    map_name: str | None = None,
    registry_version: str = DEFAULT_REGISTRY_VERSION,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    map_name = map_name or project.target_maps[0]
    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    maps_dir = project_root / "configs" / "maps"
    registry_index, map_config = build_configs_from_existing(maps_dir, map_name=map_name, registry_version=registry_version)
    registry = registry_from_config(map_config, registry_version=registry_version, source_path=maps_dir / f"{normalize_id(map_name)}.yaml")
    validate_map_registry(registry)

    inputs, missing_optional = load_inputs(gold_dir, project_root)
    coverage = build_feature_coverage(registry, inputs["feature_contract"])
    frames = {
        "map_registry": build_map_registry_frame(registry_index, registry),
        "map_region_registry": build_region_registry_frame(registry),
        "map_semantic_groups": build_semantic_groups_frame(registry, inputs["feature_contract"]),
        "map_region_semantic_mapping": build_semantic_mapping_frame(registry),
        "map_bombsite_registry": build_bombsite_frame(registry),
        "map_feature_semantic_coverage": coverage,
        "map_region_unknowns": build_unknowns(registry, coverage),
    }
    frames["map_registry_audit"] = build_audit(
        registry,
        frames,
        inputs["candidate_feature_set"],
        missing_optional=missing_optional,
        registry_version=registry_version,
        config_written=not dry_run,
        report_written=not dry_run,
    )

    outputs: dict[str, Path] = {}
    if not dry_run:
        outputs["map_registry_config"] = write_text(
            yaml.safe_dump(registry_index, sort_keys=False, allow_unicode=False),
            maps_dir / "map_registry.yaml",
            force=force,
        )
        outputs["mirage_config"] = write_text(
            yaml.safe_dump(map_config, sort_keys=False, allow_unicode=False),
            maps_dir / "mirage.yaml",
            force=force,
        )
        # Validate the on-disk loader path, not just the in-memory migration.
        load_map_registry(map_name, registry_path=maps_dir / "map_registry.yaml")
        output_dir = gold_dir / "maps" / "map_registry"
        outputs.update(write_outputs(frames, output_dir, force=force))
        outputs["report"] = write_text(
            build_markdown_report(frames),
            project_root / "docs" / "map_geometry_region_registry.md",
            force=force,
        )
        outputs["notebook"] = write_text(
            build_notebook_json(),
            project_root / "notebooks" / "15_map_region_registry.ipynb",
            force=force,
        )

    summary = {
        "maps_registered": len(frames["map_registry"]),
        "physical_regions": len(frames["map_region_registry"]),
        "semantic_groups": len(frames["map_semantic_groups"]),
        "region_mappings": len(frames["map_region_semantic_mapping"]),
        "region_dependent_features": len(frames["map_feature_semantic_coverage"]),
        "unknown_rows": len(frames["map_region_unknowns"]),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def build_configs_from_existing(maps_dir: Path, *, map_name: str, registry_version: str) -> tuple[dict[str, Any], dict[str, Any]]:
    source = load_region_config(maps_dir / "mirage_regions.yaml")
    if normalize_id(map_name) != "mirage":
        raise ValueError("Stage 8.1 only migrates the current reference map: Mirage.")
    map_config = migrate_mirage_config(source)
    registry_index = {
        "registry_version": registry_version,
        "maps": [
            {
                "map_id": "mirage",
                "display_name": "Mirage",
                "game_map_name": "de_mirage",
                "config_path": "configs/maps/mirage.yaml",
                "region_schema_version": "v1",
                "status": "active",
                "is_reference_map": True,
                "notes": "Reference map migrated from configs/maps/mirage_regions.yaml.",
            }
        ],
    }
    return registry_index, map_config


def migrate_mirage_config(source: dict[str, Any]) -> dict[str, Any]:
    semantic_members: dict[str, list[str]] = {}
    physical_regions = []
    aliases: dict[str, list[str]] = {}
    for index, region in enumerate(source.get("regions", []), start=1):
        region_name = str(region.get("region_name") or "")
        region_id = normalize_id(region_name)
        semantic_id = REGION_GROUP_TO_SEMANTIC.get(str(region.get("region_group") or ""), normalize_id(str(region.get("region_group") or "unknown")))
        semantic_members.setdefault(semantic_id, []).append(region_id)
        site_affinity = site_affinity_for_semantic(semantic_id)
        region_aliases = [str(value) for value in region.get("aliases", [])]
        aliases[region_id] = sorted(set([region_name, *region_aliases]))
        physical_regions.append(
            {
                "region_id": region_id,
                "display_name": region_name,
                "geometry": {
                    "type": "named_area",
                    "source": "migrated_from_current_pipeline",
                    "source_region_group": region.get("region_group"),
                    "source_place_aliases": region_aliases,
                    "notes": "Awpy/place-name area migrated without coordinate boundary changes.",
                },
                "semantic_tags": [semantic_id],
                "site_affinity": site_affinity,
                "region_scope": "map_specific",
                "priority": 100 - index,
                "boundary_policy": "existing_behavior",
                "aliases": list(aliases[region_id]),
                "status": "active",
                "notes": "Migrated from configs/maps/mirage_regions.yaml.",
            }
        )
    semantic_groups = {
        semantic_id: {
            "description": SEMANTIC_DESCRIPTIONS.get(semantic_id, f"Semantic group migrated from existing region group {semantic_id}."),
            "member_regions": list(members),
            "status": "active",
            "notes": "Migrated from current place-name region mapping.",
        }
        for semantic_id, members in sorted(semantic_members.items())
    }
    return {
        "map_id": "mirage",
        "display_name": "Mirage",
        "game_map_name": "de_mirage",
        "region_schema_version": "v1",
        "boundary_policy": "existing_behavior",
        "coordinate_system": {
            "source": "existing_project_geometry",
            "axis_x": "x",
            "axis_y": "y",
            "axis_z": "z",
            "notes": "Current pipeline uses Awpy/place-name region aliases rather than custom coordinate boxes.",
        },
        "physical_regions": physical_regions,
        "semantic_groups": semantic_groups,
        "aliases": aliases,
        "bombsites": {
            "A": {"region_ids": list(semantic_members.get("site_a", [])), "notes": "Bombsite A migrated from BOMB_SITE_A region group."},
            "B": {"region_ids": list(semantic_members.get("site_b", [])), "notes": "Bombsite B migrated from BOMB_SITE_B region group."},
        },
    }


def site_affinity_for_semantic(semantic_id: str) -> list[str]:
    if semantic_id in {"a_pressure", "site_a"}:
        return ["A"]
    if semantic_id in {"b_pressure", "site_b"}:
        return ["B"]
    return []


def load_inputs(gold_dir: Path, project_root: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    missing_optional: list[str] = []
    feature_contract = read_with_fallback(gold_dir / "features" / "feature_contract" / "feature_contract")
    if feature_contract.empty:
        raise FileNotFoundError("Stage 8.1 requires Stage 8.0 feature_contract output.")
    map_readiness = read_with_fallback(gold_dir / "features" / "feature_contract" / "feature_contract_map_readiness")
    if map_readiness.empty:
        missing_optional.append("feature_contract_map_readiness")
    config_path = project_root / "configs" / "features" / "feature_contract.yaml"
    if not config_path.exists():
        missing_optional.append("feature_contract_yaml")
    candidate = read_with_fallback(gold_dir / "modeling" / "t_side_ab_candidate" / "candidate_model_feature_set")
    if candidate.empty:
        missing_optional.append("candidate_model_feature_set")
    return {
        "feature_contract": feature_contract,
        "map_readiness": map_readiness,
        "candidate_feature_set": candidate,
    }, missing_optional


def read_with_fallback(base_path: Path) -> pd.DataFrame:
    parquet = base_path.with_suffix(".parquet")
    csv = base_path.with_suffix(".csv")
    if parquet.exists():
        return read_catalog(parquet)
    if csv.exists():
        return read_catalog(csv)
    return pd.DataFrame()


def build_map_registry_frame(index: dict[str, Any], registry: MapRegistry) -> pd.DataFrame:
    rows = []
    for entry in index.get("maps", []):
        rows.append(
            {
                "registry_version": index.get("registry_version"),
                "map_id": entry.get("map_id"),
                "display_name": entry.get("display_name"),
                "game_map_name": entry.get("game_map_name"),
                "region_schema_version": entry.get("region_schema_version"),
                "config_path": entry.get("config_path"),
                "status": entry.get("status"),
                "is_reference_map": bool(entry.get("is_reference_map")),
                "physical_region_count": len(registry.physical_regions),
                "semantic_group_count": len(registry.semantic_groups),
                "bombsite_count": len(registry.bombsites),
                "notes": entry.get("notes"),
            }
        )
    return pd.DataFrame(rows)


def build_region_registry_frame(registry: MapRegistry) -> pd.DataFrame:
    rows = []
    for region in registry.physical_regions.values():
        geometry = region.geometry
        rows.append(
            {
                "registry_version": registry.registry_version,
                "map_id": registry.map_id,
                "region_id": region.region_id,
                "display_name": region.display_name,
                "geometry_type": geometry.get("type"),
                "geometry_source": geometry.get("source"),
                "x_min": geometry.get("x_min"),
                "x_max": geometry.get("x_max"),
                "y_min": geometry.get("y_min"),
                "y_max": geometry.get("y_max"),
                "z_min": geometry.get("z_min"),
                "z_max": geometry.get("z_max"),
                "priority": region.priority,
                "boundary_policy": region.boundary_policy,
                "site_affinity": "|".join(region.site_affinity),
                "region_scope": region.region_scope,
                "semantic_tag_count": len(region.semantic_tags),
                "semantic_tags": "|".join(region.semantic_tags),
                "alias_count": len(region.aliases),
                "aliases": "|".join(region.aliases),
                "status": region.status,
                "notes": region.notes,
            }
        )
    return pd.DataFrame(rows)


def build_semantic_groups_frame(registry: MapRegistry, feature_contract: pd.DataFrame) -> pd.DataFrame:
    usage = feature_contract["region_semantic"].value_counts() if "region_semantic" in feature_contract.columns else pd.Series(dtype=int)
    rows = []
    for group in registry.semantic_groups.values():
        rows.append(
            {
                "registry_version": registry.registry_version,
                "map_id": registry.map_id,
                "semantic_id": group.semantic_id,
                "description": group.description,
                "member_region_count": len(group.member_regions),
                "member_regions": "|".join(group.member_regions),
                "feature_contract_usage_count": int(usage.get(group.semantic_id, 0)),
                "status": group.status,
                "notes": group.notes,
            }
        )
    return pd.DataFrame(rows)


def build_semantic_mapping_frame(registry: MapRegistry) -> pd.DataFrame:
    rows = []
    for semantic in registry.semantic_groups.values():
        for region_id in semantic.member_regions:
            rows.append(
                {
                    "map_id": registry.map_id,
                    "region_id": region_id,
                    "semantic_id": semantic.semantic_id,
                    "mapping_source": "existing_pipeline",
                    "confidence": "high",
                    "status": "active",
                    "notes": "Migrated from existing region_group mapping.",
                }
            )
    return pd.DataFrame(rows)


def build_bombsite_frame(registry: MapRegistry) -> pd.DataFrame:
    rows = []
    for site, bombsite in registry.bombsites.items():
        for region_id in bombsite.region_ids:
            rows.append(
                {
                    "map_id": registry.map_id,
                    "bombsite": site,
                    "region_id": region_id,
                    "mapping_role": "site_region",
                    "priority": registry.physical_regions[region_id].priority if region_id in registry.physical_regions else None,
                    "status": "active" if region_id in registry.physical_regions else "invalid",
                    "notes": bombsite.notes,
                }
            )
    return pd.DataFrame(rows)


def build_feature_coverage(registry: MapRegistry, feature_contract: pd.DataFrame) -> pd.DataFrame:
    if feature_contract.empty:
        return pd.DataFrame()
    data = feature_contract[feature_contract["region_dependency"].fillna(False)].copy()
    rows = []
    for _, row in data.iterrows():
        semantic = normalize_id(str(row.get("region_semantic") or ""))
        map_scope = str(row.get("map_scope") or "unknown")
        regions = registry.regions_for_semantic(semantic)
        if not regions and map_scope == "map_specific":
            candidate_region = normalize_specific_region(semantic)
            region = registry.get_region(candidate_region)
            regions = [region] if region else []
        semantic_exists = bool(semantic in registry.semantic_groups or regions)
        map_ready = bool(semantic_exists and regions)
        blocking_reason = "none" if map_ready else f"missing_semantic_or_region:{semantic or 'unknown'}"
        action = "Ready for Mirage registry use." if map_ready else "Add semantic group or physical region mapping before refactor."
        rows.append(
            {
                "feature_name": row["feature_name"],
                "feature_family": row.get("feature_family"),
                "semantic_role": row.get("semantic_role"),
                "region_semantic": semantic or None,
                "map_scope": map_scope,
                "mirage_specific": bool(row.get("mirage_specific")),
                "semantic_exists_in_registry": semantic_exists,
                "physical_region_count": len(regions),
                "physical_regions": "|".join(region.region_id for region in regions),
                "map_ready": map_ready,
                "requires_equivalent_decision_for_new_maps": bool(map_scope == "map_specific"),
                "blocking_reason": blocking_reason,
                "recommended_action": action,
            }
        )
    return pd.DataFrame(rows)


def normalize_specific_region(semantic: str) -> str:
    return semantic.removeprefix("mirage_")


def build_unknowns(registry: MapRegistry, coverage: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in coverage.iterrows():
        if not bool(row["map_ready"]):
            rows.append(
                unknown_row(
                    registry.map_id,
                    "unknown_semantic",
                    str(row["region_semantic"]),
                    "feature_contract",
                    f"Feature {row['feature_name']} has no resolved semantic/region mapping.",
                    "high",
                    "Add semantic group or explicit map-specific region mapping.",
                )
            )
    for region in registry.physical_regions.values():
        if not region.geometry.get("type"):
            rows.append(
                unknown_row(
                    registry.map_id,
                    "missing_geometry",
                    region.region_id,
                    "map_registry",
                    "Region has no geometry type.",
                    "high",
                    "Set geometry.type before using registry.",
                )
            )
    return pd.DataFrame(
        rows,
        columns=["map_id", "unknown_type", "reference_name", "source", "reason", "severity", "recommended_action"],
    )


def unknown_row(
    map_id: str,
    unknown_type: str,
    reference_name: str,
    source: str,
    reason: str,
    severity: str,
    recommended_action: str,
) -> dict[str, str]:
    return {
        "map_id": map_id,
        "unknown_type": unknown_type,
        "reference_name": reference_name,
        "source": source,
        "reason": reason,
        "severity": severity,
        "recommended_action": recommended_action,
    }


def build_audit(
    registry: MapRegistry,
    frames: dict[str, pd.DataFrame],
    candidate_feature_set: pd.DataFrame,
    *,
    missing_optional: list[str],
    registry_version: str,
    config_written: bool,
    report_written: bool,
) -> pd.DataFrame:
    coverage = frames["map_feature_semantic_coverage"]
    unknowns = frames["map_region_unknowns"]
    candidate_features = candidate_region_features(coverage, candidate_feature_set)
    invalid_region_references = 0
    invalid_semantic_references = 0
    invalid_alias_references = 0
    unresolved = int((~coverage["map_ready"]).sum()) if not coverage.empty else 0
    candidate_unresolved = int((~candidate_features["map_ready"]).sum()) if not candidate_features.empty else 0
    bombsites_ok = {"A", "B"} <= set(registry.bombsites) and all(registry.bombsites[site].region_ids for site in ["A", "B"])
    ready = bool(
        unresolved == 0
        and candidate_unresolved == 0
        and bombsites_ok
        and not any([invalid_region_references, invalid_semantic_references, invalid_alias_references])
    )
    status = "warning" if not unknowns.empty or missing_optional else "ok"
    return pd.DataFrame(
        [
            {
                "audit_id": "map_geometry_region_registry",
                "registry_version": registry_version,
                "maps_registered": 1,
                "reference_map": registry.map_id,
                "physical_regions": len(registry.physical_regions),
                "semantic_groups": len(registry.semantic_groups),
                "region_semantic_mappings": len(frames["map_region_semantic_mapping"]),
                "bombsite_mappings": len(frames["map_bombsite_registry"]),
                "region_dependent_features": len(coverage),
                "resolved_region_features": int(coverage["map_ready"].sum()) if not coverage.empty else 0,
                "unresolved_region_features": unresolved,
                "candidate_region_features": len(candidate_features),
                "candidate_region_features_resolved": int(candidate_features["map_ready"].sum()) if not candidate_features.empty else 0,
                "candidate_region_features_unresolved": candidate_unresolved,
                "ready_for_map_feature_refactor": ready,
                "unknown_rows": len(unknowns),
                "invalid_region_references": invalid_region_references,
                "invalid_semantic_references": invalid_semantic_references,
                "invalid_alias_references": invalid_alias_references,
                "missing_optional_inputs": "|".join(missing_optional) if missing_optional else "none",
                "config_written": config_written,
                "report_written": report_written,
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )


def candidate_region_features(coverage: pd.DataFrame, candidate_feature_set: pd.DataFrame) -> pd.DataFrame:
    if coverage.empty or candidate_feature_set.empty or "feature_name" not in candidate_feature_set.columns:
        return coverage.iloc[0:0].copy()
    names = set(candidate_feature_set["feature_name"].dropna().astype(str))
    names.discard("__feature_set_summary__")
    return coverage[coverage["feature_name"].isin(names)].copy()


def build_markdown_report(frames: dict[str, pd.DataFrame]) -> str:
    registry = frames["map_registry"]
    regions = frames["map_region_registry"]
    groups = frames["map_semantic_groups"]
    mapping = frames["map_region_semantic_mapping"]
    bombsites = frames["map_bombsite_registry"]
    coverage = frames["map_feature_semantic_coverage"]
    unknowns = frames["map_region_unknowns"]
    audit = frames["map_registry_audit"]
    return "\n".join(
        [
            "# Map Geometry & Region Registry",
            "",
            "## Purpose",
            "Define an auditable map/region registry that separates physical map areas from tactical semantics.",
            "",
            "## Why map geometry must be configurable",
            "Map-abstract features can only expand safely when each map declares the regions behind shared semantics.",
            "",
            "## Current reference map",
            markdown_table(registry, list(registry.columns)),
            "",
            "## Coordinate system",
            "The current Mirage implementation uses Awpy/place-name areas, not project-owned coordinate bounding boxes.",
            "",
            "## Physical regions",
            markdown_table(regions, ["region_id", "display_name", "geometry_type", "geometry_source", "priority", "semantic_tags", "aliases"], top_n=30),
            "",
            "## Semantic regions",
            markdown_table(groups, list(groups.columns), top_n=30),
            "",
            "## Physical-to-semantic mapping",
            markdown_table(mapping, list(mapping.columns), top_n=40),
            "",
            "## Bombsites",
            markdown_table(bombsites, list(bombsites.columns)),
            "",
            "## Feature contract coverage",
            markdown_table(coverage, ["feature_name", "region_semantic", "map_scope", "physical_region_count", "map_ready", "blocking_reason"], top_n=40),
            "",
            "## Map-abstract features",
            markdown_table(coverage[coverage["map_scope"].eq("map_abstract")], ["feature_name", "region_semantic", "physical_regions", "map_ready"], top_n=40),
            "",
            "## Mirage-specific features",
            markdown_table(coverage[coverage["mirage_specific"]], ["feature_name", "region_semantic", "physical_regions", "map_ready"], top_n=30),
            "",
            "## Unknown / unresolved mappings",
            markdown_table(unknowns, list(unknowns.columns), top_n=30),
            "",
            "## Backward compatibility",
            "This stage writes configuration and metadata only. It does not recalculate round features or model outputs.",
            "",
            "## Adding a new map",
            "1. create `configs/maps/<map>.yaml`",
            "2. register map in `map_registry.yaml`",
            "3. define coordinate system",
            "4. define physical regions",
            "5. map physical regions to semantic groups",
            "6. define bombsites",
            "7. validate feature-contract coverage",
            "8. run registry audit",
            "9. only then run feature engineering",
            "",
            "## Next stage",
            "Next: Stage 8.2 -- Map-Ready Feature Refactor",
            "",
            "## Audit",
            markdown_table(audit, list(audit.columns)),
            "",
        ]
    )


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    if frame.empty:
        return "_No rows available._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def build_notebook_json() -> str:
    cells = [
        markdown_cell("# Stage 8.1 -- Map Geometry & Region Registry\n\nInspect Mirage registry metadata."),
        code_cell(
            "from pathlib import Path\n\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n\n"
            "BASE = Path('../data/gold/maps/map_registry')\n\n"
            "def load_table(name):\n"
            "    return pd.read_parquet(BASE / f'{name}.parquet')\n\n"
            "registry = load_table('map_registry')\n"
            "regions = load_table('map_region_registry')\n"
            "semantic_groups = load_table('map_semantic_groups')\n"
            "mapping = load_table('map_region_semantic_mapping')\n"
            "bombsites = load_table('map_bombsite_registry')\n"
            "coverage = load_table('map_feature_semantic_coverage')\n"
            "unknowns = load_table('map_region_unknowns')\n"
            "audit = load_table('map_registry_audit')"
        ),
        markdown_cell("## Physical Regions"),
        code_cell("display(regions)"),
        markdown_cell("## Semantic Groups"),
        code_cell("display(semantic_groups)"),
        markdown_cell("## Physical to Semantic Mapping"),
        code_cell("display(mapping)"),
        markdown_cell("## Bombsites"),
        code_cell("display(bombsites)"),
        markdown_cell("## Feature Contract Coverage"),
        code_cell("display(coverage.head(50))"),
        markdown_cell("## Unknowns"),
        code_cell("display(unknowns)"),
        markdown_cell("## Audit"),
        code_cell("display(audit)"),
        markdown_cell("## Coordinate Sketch"),
        code_cell(
            "bbox = regions.dropna(subset=['x_min', 'x_max', 'y_min', 'y_max'])\n"
            "if bbox.empty:\n"
            "    print('No coordinate bounding boxes are registered yet; Mirage currently uses named Awpy/place areas.')\n"
            "else:\n"
            "    fig, ax = plt.subplots(figsize=(6, 6))\n"
            "    for _, row in bbox.iterrows():\n"
            "        rect = plt.Rectangle((row.x_min, row.y_min), row.x_max - row.x_min, row.y_max - row.y_min, fill=False)\n"
            "        ax.add_patch(rect)\n"
            "        ax.text(row.x_min, row.y_min, row.region_id)\n"
            "    ax.set_aspect('equal', adjustable='box')\n"
            "    plt.tight_layout()"
        ),
    ]
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.11",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1) + "\n"


def markdown_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                if suffix == "csv":
                    frames[name].to_csv(path, index=False)
                else:
                    frames[name].to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Map Registry summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the map geometry and region registry.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--map", default=None)
    parser.add_argument("--registry-version", default=DEFAULT_REGISTRY_VERSION)
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_map_registry(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        map_name=args.map,
        registry_version=args.registry_version,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
