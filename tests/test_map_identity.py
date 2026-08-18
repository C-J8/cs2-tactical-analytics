from __future__ import annotations

from pathlib import Path

import pytest

from src.maps.identity import canonical_map_id, canonical_map_name, known_map, resolve_map_identity, same_map, try_resolve_map_identity


def _write_registry(tmp_path: Path) -> Path:
    path = tmp_path / "configs/maps/map_registry.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """
registry_version: v1
maps:
- map_id: mirage
  display_name: Mirage
  game_map_name: de_mirage
  config_path: configs/maps/mirage.yaml
  region_schema_version: v1
  status: active
  is_reference_map: true
- map_id: inferno
  display_name: Inferno
  game_map_name: de_inferno
  config_path: configs/maps/inferno.yaml
  region_schema_version: v1
  status: onboarding
  is_reference_map: false
""".strip(),
        encoding="utf-8",
    )
    return path


def test_canonical_map_identity_aliases(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)

    assert canonical_map_id("Mirage", registry_path=registry) == "mirage"
    assert canonical_map_id("mirage", registry_path=registry) == "mirage"
    assert canonical_map_id("de_mirage", registry_path=registry) == "mirage"
    assert canonical_map_id("Inferno", registry_path=registry) == "inferno"
    assert canonical_map_id("inferno", registry_path=registry) == "inferno"
    assert canonical_map_id("de_inferno", registry_path=registry) == "inferno"
    assert canonical_map_name("de_inferno", registry_path=registry) == "Inferno"


def test_same_map_and_known_map(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)

    assert same_map("de_inferno", "Inferno", registry_path=registry)
    assert not same_map("Mirage", "Inferno", registry_path=registry)
    assert known_map("de_mirage", registry_path=registry)
    assert not known_map("de_unknown_map", registry_path=registry)


def test_unknown_map_strict_resolution_fails(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)

    assert try_resolve_map_identity("de_unknown_map", registry_path=registry) is None
    with pytest.raises(ValueError, match="Unknown map identity"):
        resolve_map_identity("de_unknown_map", registry_path=registry)
