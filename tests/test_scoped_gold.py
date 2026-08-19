from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.storage.scoped_gold import GOLD_DATASET_SPECS, make_gold_scope, upsert_gold_scope, write_scoped_dataset


def _registry(tmp_path: Path) -> Path:
    maps = tmp_path / "configs" / "maps"
    maps.mkdir(parents=True)
    registry = maps / "map_registry.yaml"
    registry.write_text(
        """
registry_version: v1
maps:
- map_id: mirage
  display_name: Mirage
  game_map_name: de_mirage
  config_path: configs/maps/mirage.yaml
- map_id: inferno
  display_name: Inferno
  game_map_name: de_inferno
  config_path: configs/maps/inferno.yaml
""".strip(),
        encoding="utf-8",
    )
    for map_id, display in [("mirage", "Mirage"), ("inferno", "Inferno")]:
        (maps / f"{map_id}.yaml").write_text(
            f"""
map_id: {map_id}
display_name: {display}
game_map_name: de_{map_id}
region_schema_version: v1
coordinate_system: {{source: test}}
physical_regions:
- region_id: mid
  display_name: Mid
  geometry: {{type: named_area, area_names: [Middle]}}
  semantic_tags: [mid_control]
  site_affinity: []
  region_scope: map_specific
  priority: 1
  boundary_policy: existing_behavior
  aliases: [Middle]
  status: active
semantic_groups:
  mid_control:
    member_regions: [mid]
bombsites:
  A: {{region_ids: [mid]}}
  B: {{region_ids: [mid]}}
aliases:
  mid: [Middle]
""".strip(),
            encoding="utf-8",
        )
    return registry


def test_scoped_upsert_replaces_only_selected_team_map_scope(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    spec = GOLD_DATASET_SPECS["round_features_mvp"]
    existing = pd.DataFrame(
        [
            {"round_feature_id": "mirage_1", "target_team": "Vitality", "map_name": "Mirage", "value": 1},
            {"round_feature_id": "inferno_old", "target_team": "Vitality", "map_name": "de_inferno", "value": 2},
        ]
    )
    incoming = pd.DataFrame([{"round_feature_id": "inferno_new", "target_team": "Vitality", "map_name": "Inferno", "value": 3}])
    scope = make_gold_scope(map_id="inferno", map_name="Inferno", target_team="Vitality", round_feature_ids={"inferno_new"})

    combined, audit = upsert_gold_scope(existing, incoming, scope, spec, registry_path=registry)

    assert combined["round_feature_id"].tolist() == ["inferno_new", "mirage_1"]
    assert audit["other_scope_unchanged"] is True
    assert audit["scope_rows_before"] == 1
    assert audit["scope_rows_after"] == 1


def test_scoped_upsert_rejects_duplicate_stable_keys(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    spec = GOLD_DATASET_SPECS["round_features_mvp"]
    incoming = pd.DataFrame(
        [
            {"round_feature_id": "same", "target_team": "Vitality", "map_name": "Inferno", "value": 1},
            {"round_feature_id": "same", "target_team": "Vitality", "map_name": "Inferno", "value": 2},
        ]
    )
    scope = make_gold_scope(map_id="inferno", map_name="Inferno", target_team="Vitality")

    with pytest.raises(ValueError, match="duplicate stable keys"):
        upsert_gold_scope(pd.DataFrame(), incoming, scope, spec, registry_path=registry)


def test_write_scoped_dataset_is_idempotent_for_inferno_scope(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    gold = tmp_path / "data" / "gold"
    spec = GOLD_DATASET_SPECS["round_features_mvp"]
    scope = make_gold_scope(map_id="inferno", map_name="Inferno", target_team="Vitality")
    incoming = pd.DataFrame([{"round_feature_id": "inferno_1", "target_team": "Vitality", "map_name": "Inferno", "value": 1}])

    write_scoped_dataset(incoming, gold, scope, spec, registry_path=registry, force=True)
    write_scoped_dataset(incoming, gold, scope, spec, registry_path=registry, force=True)
    final = pd.read_parquet(gold / "round_features" / "round_features_mvp.parquet")

    assert len(final) == 1
    assert final.loc[0, "round_feature_id"] == "inferno_1"
