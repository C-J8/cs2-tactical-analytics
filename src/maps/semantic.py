from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.maps.registry import MapRegistry, PhysicalRegion, normalize_id


@dataclass(frozen=True)
class RegionResolution:
    feature_name: str
    feature_family: str | None
    map_scope: str
    region_dependency: bool
    region_semantic: str | None
    physical_regions_used: list[str]
    registry_version: str
    resolution_source: str
    resolved: bool
    resolution_status: str
    notes: str | None = None


def legacy_region_group(region: PhysicalRegion) -> str:
    group = region.geometry.get("source_region_group")
    return str(group) if group else (region.semantic_tags[0].upper() if region.semantic_tags else "UNKNOWN")


def place_lookup_from_registry(registry: MapRegistry) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for region in registry.physical_regions.values():
        aliases = [region.display_name, region.region_id, *region.aliases]
        for alias in aliases:
            lookup[normalize_place(alias)] = (region.display_name, legacy_region_group(region))
    return lookup


def place_column_candidates_from_registry(registry: MapRegistry) -> list[str]:
    candidates = registry.coordinate_system.get("place_column_candidates")
    if isinstance(candidates, list) and candidates:
        return [str(candidate) for candidate in candidates]
    return ["last_place_name", "place_name", "player_last_place_name", "place"]


def is_player_in_semantic_region(region_group: object, registry: MapRegistry, semantic_id: str) -> bool:
    return str(region_group) in legacy_groups_for_semantic(registry, semantic_id)


def legacy_groups_for_semantic(registry: MapRegistry, semantic_id: str) -> set[str]:
    return {legacy_region_group(region) for region in registry.regions_for_semantic(semantic_id)}


def legacy_feature_groups_for_registry(registry: MapRegistry, semantic_ids: list[str] | None = None) -> dict[str, str]:
    semantics = semantic_ids or ["mid_control", "a_pressure", "b_pressure", "ct_space"]
    groups: dict[str, str] = {}
    for semantic_id in semantics:
        for group in sorted(legacy_groups_for_semantic(registry, semantic_id)):
            if group != "UNKNOWN":
                groups[group] = semantic_id
    return groups


def count_players_in_semantic_region(df: pd.DataFrame, registry: MapRegistry, semantic_id: str, *, player_column: str = "steamid") -> int:
    if df.empty or "region_group" not in df.columns or player_column not in df.columns:
        return 0
    return int(df[df["region_group"].isin(legacy_groups_for_semantic(registry, semantic_id))][player_column].nunique())


def count_rows_in_semantic_region(df: pd.DataFrame, registry: MapRegistry, semantic_id: str) -> int:
    if df.empty or "region_group" not in df.columns:
        return 0
    return int(df["region_group"].isin(legacy_groups_for_semantic(registry, semantic_id)).sum())


def resolve_feature_requirements(feature_contract: pd.DataFrame, registry: MapRegistry) -> pd.DataFrame:
    if feature_contract.empty:
        return pd.DataFrame(columns=usage_columns())
    rows = []
    for _, row in feature_contract.iterrows():
        region_dependency = bool(row.get("region_dependency"))
        map_scope = str(row.get("map_scope") or "unknown")
        semantic = normalize_optional(row.get("region_semantic"))
        if not region_dependency:
            rows.append(
                RegionResolution(
                    feature_name=str(row.get("feature_name")),
                    feature_family=normalize_optional(row.get("feature_family")),
                    map_scope=map_scope,
                    region_dependency=False,
                    region_semantic=semantic,
                    physical_regions_used=[],
                    registry_version=registry.registry_version,
                    resolution_source="global",
                    resolved=True,
                    resolution_status="not_needed",
                    notes="Global/non-region feature does not require map registry resolution.",
                ).__dict__
            )
            continue

        regions = registry.regions_for_semantic(semantic or "")
        source = "semantic_group"
        if not regions and map_scope == "map_specific":
            physical = registry.get_region((semantic or "").removeprefix("mirage_"))
            regions = [physical] if physical else []
            source = "physical_region"

        resolved = bool(regions)
        rows.append(
            RegionResolution(
                feature_name=str(row.get("feature_name")),
                feature_family=normalize_optional(row.get("feature_family")),
                map_scope=map_scope,
                region_dependency=True,
                region_semantic=semantic,
                physical_regions_used=[region.region_id for region in regions],
                registry_version=registry.registry_version,
                resolution_source=source,
                resolved=resolved,
                resolution_status="resolved" if resolved else "missing_mapping",
                notes=None if resolved else "Feature requires a semantic group or physical region that is absent from the registry.",
            ).__dict__
        )
    return pd.DataFrame(rows, columns=usage_columns())


def map_feature_unknowns(usage: pd.DataFrame, map_id: str) -> pd.DataFrame:
    rows = []
    unresolved = usage[(usage["region_dependency"] == True) & (usage["resolved"] == False)] if not usage.empty else pd.DataFrame()  # noqa: E712
    for _, row in unresolved.iterrows():
        unknown_type = "missing_region" if row.get("resolution_source") == "physical_region" else "missing_semantic"
        rows.append(
            {
                "feature_name": row.get("feature_name"),
                "map_id": map_id,
                "unknown_type": unknown_type,
                "reference_name": row.get("region_semantic"),
                "reason": row.get("notes"),
                "severity": "high",
                "recommended_action": "Add the missing semantic group or physical region before map-ready feature generation.",
            }
        )
    return pd.DataFrame(rows, columns=["feature_name", "map_id", "unknown_type", "reference_name", "reason", "severity", "recommended_action"])


def normalize_optional(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value)
    return normalize_id(text) if text else None


def normalize_place(value: object) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def usage_columns() -> list[str]:
    return [
        "feature_name",
        "feature_family",
        "map_scope",
        "region_dependency",
        "region_semantic",
        "physical_regions_used",
        "registry_version",
        "resolution_source",
        "resolved",
        "resolution_status",
        "notes",
    ]
