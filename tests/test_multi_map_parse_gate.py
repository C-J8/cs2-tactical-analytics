from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.validation.multi_map_parse_gate import build_place_readiness, run_multi_map_parse_gate


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "configs/project.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-07-07"
target_maps: [Mirage]
target_teams: [Vitality]
output_formats: [csv, parquet]
dem_files_manifest_path: {(tmp_path / 'data/bronze/dem_files_manifest/dem_files_manifest.parquet').as_posix()}
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
parse_manifest_dir: {(tmp_path / 'data/bronze/parse_manifest').as_posix()}
""".strip(),
        encoding="utf-8",
    )
    _write_registry(tmp_path)
    return config


def _write_registry(tmp_path: Path) -> None:
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


def _write_inputs(tmp_path: Path) -> None:
    _write(
        tmp_path / "data/bronze/dem_files_manifest",
        "dem_files_manifest",
        [{"dem_file_id": "inferno1", "dem_file_name": "inferno.dem", "dem_path": "inferno.dem", "target_team": "Vitality", "inferred_map_name": "de_inferno", "parse_eligible": True}],
    )
    _write(
        tmp_path / "data/bronze/parse_manifest",
        "parse_manifest",
        [{"parse_id": "inferno1_awpy", "dem_file_id": "inferno1", "dem_file_name": "inferno.dem", "dem_path": "inferno.dem", "target_team": "Vitality", "map_name": "de_inferno", "parse_status": "parsed", "rows_ticks": 2, "rows_rounds": 1}],
    )
    _write(
        tmp_path / "data/bronze/parse_quality",
        "parse_quality",
        [{"parse_id": "inferno1_awpy", "dem_file_id": "inferno1", "target_team": "Vitality", "inferred_map_name": "de_inferno", "parse_status": "parsed", "parse_eligible": True, "feature_eligible": True, "quality_status": "valid_full_map"}],
    )
    silver = tmp_path / "data/silver/parsed_demos"
    silver.mkdir(parents=True)
    pd.DataFrame(
        [
            {"source_parse_id": "inferno1_awpy", "round_num": 1, "tick": 1, "steamid": "1", "target_team": "Vitality", "map_name": "de_inferno", "X": 1, "Y": 2, "Z": 3, "place": "Banana"},
            {"source_parse_id": "mirage1_awpy", "round_num": 1, "tick": 1, "steamid": "1", "target_team": "Vitality", "map_name": "Mirage", "X": 1, "Y": 2, "Z": 3, "place": "Middle"},
        ]
    ).to_parquet(silver / "ticks.parquet", index=False)
    pd.DataFrame([{"source_parse_id": "inferno1_awpy", "round_num": 1, "target_team": "Vitality", "map_name": "de_inferno"}]).to_parquet(silver / "rounds.parquet", index=False)


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def test_multi_map_parse_gate_outputs_and_place_ready(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    _write_inputs(tmp_path)

    frames, outputs, summary = run_multi_map_parse_gate(config, target_map="Inferno", target_team="Vitality", force=True)

    assert summary["canonical_target_map_id"] == "inferno"
    assert summary["selected_demos"] == 1
    assert summary["ready_for_area_discovery"]
    assert frames["place_column_readiness"].loc[0, "place_column"] == "place"
    assert frames["mirage_preservation_check"].loc[frames["mirage_preservation_check"]["dataset_name"].eq("ticks"), "unchanged"].iloc[0]
    assert outputs["multi_map_parse_audit_parquet"].exists()


def test_place_readiness_detects_last_place_name() -> None:
    ticks = pd.DataFrame({"source_parse_id": ["p1"], "X": [1], "Y": [2], "Z": [3], "last_place_name": ["Banana"]})
    readiness = build_place_readiness(ticks, selected_parse_ids={"p1"}, identity=type("I", (), {"map_id": "inferno"})(), target_team="Vitality")

    assert bool(readiness.loc[0, "ready_for_area_discovery"])
    assert readiness.loc[0, "place_column"] == "last_place_name"


def test_place_readiness_blocks_without_place_or_xyz() -> None:
    no_place = build_place_readiness(pd.DataFrame({"source_parse_id": ["p1"], "X": [1], "Y": [2], "Z": [3]}), selected_parse_ids={"p1"}, identity=type("I", (), {"map_id": "inferno"})(), target_team="Vitality")
    no_xyz = build_place_readiness(pd.DataFrame({"source_parse_id": ["p1"], "place": ["Banana"], "X": [1], "Y": [2]}), selected_parse_ids={"p1"}, identity=type("I", (), {"map_id": "inferno"})(), target_team="Vitality")
    null_place = build_place_readiness(pd.DataFrame({"source_parse_id": ["p1"], "place": [None], "X": [1], "Y": [2], "Z": [3]}), selected_parse_ids={"p1"}, identity=type("I", (), {"map_id": "inferno"})(), target_team="Vitality")

    assert not bool(no_place.loc[0, "ready_for_area_discovery"])
    assert not bool(no_xyz.loc[0, "ready_for_area_discovery"])
    assert not bool(null_place.loc[0, "ready_for_area_discovery"])
