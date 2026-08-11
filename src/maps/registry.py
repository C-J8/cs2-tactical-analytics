from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


VALID_GEOMETRY_TYPES = {"bounding_box", "polygon", "named_area", "composite", "existing_definition"}
VALID_BOUNDARY_POLICIES = {"inclusive", "exclusive", "half_open", "existing_behavior"}


@dataclass(frozen=True)
class PhysicalRegion:
    region_id: str
    display_name: str
    geometry: dict[str, Any]
    semantic_tags: list[str]
    site_affinity: list[str]
    region_scope: str
    priority: int
    boundary_policy: str
    aliases: list[str]
    status: str
    notes: str | None = None


@dataclass(frozen=True)
class SemanticGroup:
    semantic_id: str
    description: str
    member_regions: list[str]
    status: str = "active"
    notes: str | None = None


@dataclass(frozen=True)
class Bombsite:
    bombsite: str
    region_ids: list[str]
    notes: str | None = None


@dataclass(frozen=True)
class MapRegistry:
    map_id: str
    display_name: str
    game_map_name: str
    region_schema_version: str
    registry_version: str
    coordinate_system: dict[str, Any]
    physical_regions: dict[str, PhysicalRegion]
    semantic_groups: dict[str, SemanticGroup]
    bombsites: dict[str, Bombsite]
    aliases: dict[str, list[str]]
    source_path: Path | None = None

    def get_region(self, region_id: str) -> PhysicalRegion | None:
        return self.physical_regions.get(normalize_id(region_id))

    def get_semantic_group(self, semantic_id: str) -> SemanticGroup | None:
        return self.semantic_groups.get(normalize_id(semantic_id))

    def regions_for_semantic(self, semantic_id: str) -> list[PhysicalRegion]:
        group = self.get_semantic_group(semantic_id)
        if group is None:
            return []
        return [self.physical_regions[region_id] for region_id in group.member_regions if region_id in self.physical_regions]

    def regions_for_site(self, site: str) -> list[PhysicalRegion]:
        bombsite = self.bombsites.get(str(site).upper())
        if bombsite is None:
            return []
        return [self.physical_regions[region_id] for region_id in bombsite.region_ids if region_id in self.physical_regions]


def load_map_registry(map_name: str, *, registry_path: Path = Path("configs/maps/map_registry.yaml")) -> MapRegistry:
    index = load_yaml(registry_path)
    entries = index.get("maps") or []
    map_ids = [normalize_id(str(entry.get("map_id", ""))) for entry in entries]
    duplicates = sorted({map_id for map_id in map_ids if map_id and map_ids.count(map_id) > 1})
    if duplicates:
        raise ValueError(f"Map registry index has duplicate map_id values: {duplicates}")
    requested = normalize_id(map_name)
    requested_without_prefix = requested.removeprefix("de_")
    matches = [
        entry
        for entry in entries
        if requested_without_prefix
        in {
            normalize_id(str(entry.get("map_id", ""))),
            normalize_id(str(entry.get("display_name", ""))),
            normalize_id(str(entry.get("game_map_name", ""))).removeprefix("de_"),
        }
    ]
    if not matches:
        raise ValueError(f"Map registry entry not found for map: {map_name}")
    entry = matches[0]
    config_path = Path(entry["config_path"])
    if not config_path.is_absolute():
        config_path = registry_path.parent.parent.parent / config_path
    config = load_yaml(config_path)
    registry = registry_from_config(config, registry_version=str(index.get("registry_version") or entry.get("registry_version") or "v1"), source_path=config_path)
    validate_map_registry(registry)
    return registry


def registry_from_config(config: dict[str, Any], *, registry_version: str, source_path: Path | None = None) -> MapRegistry:
    validate_config_uniqueness(config)
    physical = {
        normalize_id(region["region_id"]): PhysicalRegion(
            region_id=normalize_id(region["region_id"]),
            display_name=str(region.get("display_name") or region["region_id"]),
            geometry=dict(region.get("geometry") or {}),
            semantic_tags=[normalize_id(value) for value in region.get("semantic_tags", [])],
            site_affinity=[str(value).upper() for value in region.get("site_affinity", [])],
            region_scope=str(region.get("region_scope") or "map_specific"),
            priority=int(region.get("priority", 0)),
            boundary_policy=str(region.get("boundary_policy") or config.get("boundary_policy") or "existing_behavior"),
            aliases=[str(value) for value in region.get("aliases", [])],
            status=str(region.get("status") or "active"),
            notes=region.get("notes"),
        )
        for region in config.get("physical_regions", [])
    }
    semantic = {
        normalize_id(key): SemanticGroup(
            semantic_id=normalize_id(key),
            description=str(value.get("description") or ""),
            member_regions=[normalize_id(region_id) for region_id in value.get("member_regions", [])],
            status=str(value.get("status") or "active"),
            notes=value.get("notes"),
        )
        for key, value in (config.get("semantic_groups") or {}).items()
    }
    bombsites = {
        str(key).upper(): Bombsite(
            bombsite=str(key).upper(),
            region_ids=[normalize_id(region_id) for region_id in value.get("region_ids", [])],
            notes=value.get("notes"),
        )
        for key, value in (config.get("bombsites") or {}).items()
    }
    aliases = {normalize_id(key): [str(value) for value in values] for key, values in (config.get("aliases") or {}).items()}
    return MapRegistry(
        map_id=normalize_id(str(config.get("map_id") or "")),
        display_name=str(config.get("display_name") or ""),
        game_map_name=str(config.get("game_map_name") or ""),
        region_schema_version=str(config.get("region_schema_version") or ""),
        registry_version=registry_version,
        coordinate_system=dict(config.get("coordinate_system") or {}),
        physical_regions=physical,
        semantic_groups=semantic,
        bombsites=bombsites,
        aliases=aliases,
        source_path=source_path,
    )


def validate_map_registry(registry: MapRegistry) -> None:
    if not registry.map_id:
        raise ValueError("Map registry config must include map_id.")
    if not registry.region_schema_version:
        raise ValueError("Map registry config must include region_schema_version.")
    if len(registry.physical_regions) == 0:
        raise ValueError("Map registry config must define at least one physical region.")
    for region in registry.physical_regions.values():
        geometry_type = str(region.geometry.get("type") or "")
        if geometry_type not in VALID_GEOMETRY_TYPES:
            raise ValueError(f"Invalid geometry type for region {region.region_id}: {geometry_type}")
        if region.boundary_policy not in VALID_BOUNDARY_POLICIES:
            raise ValueError(f"Invalid boundary policy for region {region.region_id}: {region.boundary_policy}")
        if not isinstance(region.priority, (int, float)):
            raise ValueError(f"Region priority must be numeric: {region.region_id}")
    physical_ids = set(registry.physical_regions)
    for semantic_id, group in registry.semantic_groups.items():
        missing = sorted(set(group.member_regions) - physical_ids)
        if missing:
            raise ValueError(f"Semantic group {semantic_id} references unknown regions: {missing}")
    for site, bombsite in registry.bombsites.items():
        missing = sorted(set(bombsite.region_ids) - physical_ids)
        if missing:
            raise ValueError(f"Bombsite {site} references unknown regions: {missing}")
    for alias_target in registry.aliases:
        if alias_target not in physical_ids:
            raise ValueError(f"Alias target references unknown region: {alias_target}")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Map registry YAML not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}
    if not isinstance(content, dict):
        raise ValueError(f"Map registry YAML must contain a mapping: {path}")
    return content


def validate_config_uniqueness(config: dict[str, Any]) -> None:
    physical_ids = [normalize_id(str(region.get("region_id", ""))) for region in config.get("physical_regions", [])]
    duplicate_physical = sorted({region_id for region_id in physical_ids if region_id and physical_ids.count(region_id) > 1})
    if duplicate_physical:
        raise ValueError(f"Map registry config has duplicate physical region ids: {duplicate_physical}")

    semantic_ids = [normalize_id(str(key)) for key in (config.get("semantic_groups") or {})]
    duplicate_semantic = sorted({semantic_id for semantic_id in semantic_ids if semantic_id and semantic_ids.count(semantic_id) > 1})
    if duplicate_semantic:
        raise ValueError(f"Map registry config has duplicate semantic group ids: {duplicate_semantic}")


def normalize_id(value: str) -> str:
    return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())
