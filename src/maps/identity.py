from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.maps.registry import normalize_id


DEFAULT_REGISTRY_PATH = Path("configs/maps/map_registry.yaml")
DEFAULT_LEGACY_MAPS_PATH = Path("configs/maps.yaml")


@dataclass(frozen=True)
class MapIdentity:
    map_id: str
    display_name: str
    game_map_name: str
    aliases: tuple[str, ...]


def canonical_map_id(value: object, *, registry_path: Path = DEFAULT_REGISTRY_PATH) -> str:
    return resolve_map_identity(value, registry_path=registry_path).map_id


def canonical_map_name(value: object, *, registry_path: Path = DEFAULT_REGISTRY_PATH) -> str:
    return resolve_map_identity(value, registry_path=registry_path).display_name


def same_map(left: object, right: object, *, registry_path: Path = DEFAULT_REGISTRY_PATH) -> bool:
    left_identity = try_resolve_map_identity(left, registry_path=registry_path)
    right_identity = try_resolve_map_identity(right, registry_path=registry_path)
    return bool(left_identity and right_identity and left_identity.map_id == right_identity.map_id)


def known_map(value: object, *, registry_path: Path = DEFAULT_REGISTRY_PATH) -> bool:
    return try_resolve_map_identity(value, registry_path=registry_path) is not None


def resolve_map_identity(value: object, *, registry_path: Path = DEFAULT_REGISTRY_PATH) -> MapIdentity:
    identity = try_resolve_map_identity(value, registry_path=registry_path)
    if identity is None:
        raise ValueError(f"Unknown map identity: {value!r}")
    return identity


def try_resolve_map_identity(value: object, *, registry_path: Path = DEFAULT_REGISTRY_PATH) -> MapIdentity | None:
    key = normalize_map_key(value)
    if not key:
        return None
    for identity in load_map_identities(registry_path=registry_path):
        keys = identity_keys(identity)
        if key in keys or key.removeprefix("de_") in keys:
            return identity
    return None


def load_map_identities(*, registry_path: Path = DEFAULT_REGISTRY_PATH) -> list[MapIdentity]:
    identities = identities_from_registry(registry_path)
    if identities:
        return identities
    identities = identities_from_legacy_maps(DEFAULT_LEGACY_MAPS_PATH)
    if identities:
        return identities
    return [
        MapIdentity("mirage", "Mirage", "de_mirage", ("Mirage", "mirage", "de_mirage")),
        MapIdentity("inferno", "Inferno", "de_inferno", ("Inferno", "inferno", "de_inferno")),
    ]


def identities_from_registry(path: Path) -> list[MapIdentity]:
    if not path.exists():
        return []
    content = load_yaml(path)
    rows = []
    for entry in content.get("maps", []):
        map_id = normalize_id(str(entry.get("map_id") or ""))
        display_name = str(entry.get("display_name") or map_id)
        game_map_name = str(entry.get("game_map_name") or f"de_{map_id}")
        aliases = tuple(str(value) for value in entry.get("aliases", []))
        rows.append(MapIdentity(map_id, display_name, game_map_name, tuple(dict.fromkeys((display_name, game_map_name, map_id, *aliases)))))
    return [row for row in rows if row.map_id]


def identities_from_legacy_maps(path: Path) -> list[MapIdentity]:
    if not path.exists():
        return []
    content = load_yaml(path)
    rows = []
    for entry in content.get("maps", []):
        display_name = str(entry.get("map_name") or "")
        map_id = normalize_id(display_name)
        if not map_id:
            continue
        aliases = tuple(str(value) for value in entry.get("aliases", []))
        game_map_name = next((alias for alias in aliases if normalize_map_key(alias).startswith("de_")), f"de_{map_id}")
        rows.append(MapIdentity(map_id, display_name, game_map_name, tuple(dict.fromkeys((display_name, game_map_name, map_id, *aliases)))))
    return rows


def identity_keys(identity: MapIdentity) -> set[str]:
    keys = {normalize_map_key(identity.map_id), normalize_map_key(identity.display_name), normalize_map_key(identity.game_map_name)}
    keys.update(normalize_map_key(alias) for alias in identity.aliases)
    keys.update(key.removeprefix("de_") for key in list(keys))
    return {key for key in keys if key}


def normalize_map_key(value: object) -> str:
    return normalize_id(str(value or "")).lower()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}
    if not isinstance(content, dict):
        return {}
    return content
