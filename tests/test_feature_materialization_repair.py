from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.validation.feature_materialization_repair import run_feature_materialization_repair_audit


def test_feature_materialization_repair_audit_dry_run(tmp_path: Path) -> None:
    config_path = write_project(tmp_path)
    write_registry(tmp_path)
    gold = tmp_path / "data" / "gold"
    write_gold_frame(
        gold / "round_features",
        "round_features_mvp",
        [
            {
                "round_feature_id": "inferno_1",
                "round_id": "parse1_r1",
                "parse_id": "parse1",
                "target_team": "Vitality",
                "map_name": "Inferno",
                "flashes_used_0_15": 1,
                "he_used_0_15": 1,
                "score_diff_before_round": 0,
            }
        ],
    )
    write_gold_frame(
        gold / "round_state",
        "round_state_resolved",
        [{"round_id": "parse1_r1", "parse_id": "parse1", "round_num": 1, "target_team": "Vitality", "map_name": "Inferno"}],
    )
    write_gold_frame(
        gold / "utility_events",
        "utility_events",
        [
            {
                "utility_event_id": "u1",
                "round_feature_id": "inferno_1",
                "round_id": "parse1_r1",
                "series_id": "s1",
                "target_team": "Vitality",
                "player_name": "ZywOo",
                "player_steamid": "1",
                "utility_type": "flash",
                "event_tick": 100,
                "seconds_from_freeze_end": 1.0,
                "throw_x": 0,
                "throw_y": 0,
                "throw_z": 0,
                "throw_place": None,
                "throw_region_name": "UNKNOWN",
                "throw_region_group": "UNKNOWN",
                "end_x": 10,
                "end_y": 10,
                "end_z": 0,
                "end_place": None,
                "end_region_name": "UNKNOWN",
                "end_region_group": "UNKNOWN",
                "source_table": "grenades",
                "source_granularity": "trajectory_level",
                "source_entity_id": "10",
                "endpoint_resolution_method": "unresolved",
                "endpoint_resolution_confidence": "none",
            }
        ],
    )
    quality_dir = gold / "validation" / "map_feature_quality"
    write_gold_frame(
        quality_dir,
        "map_feature_quality_audit",
        [{"map_id": "inferno", "target_team": "Vitality", "critical_failures": 0, "unexpected_missing_features": 0, "status": "passed"}],
    )
    write_gold_frame(quality_dir, "map_feature_missingness", [{"map_id": "inferno", "target_team": "Vitality", "blocking": False}])
    write_gold_frame(quality_dir, "mirage_inferno_feature_sanity", [{"map_id": "inferno", "target_team": "Vitality", "feature_name": "players_mid_control_0_15", "structural_mismatch": False}])

    outputs, paths, summary = run_feature_materialization_repair_audit(
        config_path,
        target_map="Inferno",
        target_team="Vitality",
        dry_run=True,
    )

    assert paths == {}
    assert summary["repair_status"] == "passed"
    assert outputs["feature_materialization_repair_final_audit"].loc[0, "failed_checks"] == 0
    assert outputs["utility_endpoint_resolution_audit"].loc[0, "endpoint_resolution_method"] == "unresolved"


def write_project(tmp_path: Path) -> Path:
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True)
    path = config_dir / "project.yaml"
    path.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-06-05"
target_maps: [Inferno]
target_teams: [Vitality]
output_formats: [csv, parquet]
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
player_rosters_path: {(tmp_path / 'configs/player_rosters.yaml').as_posix()}
""".strip(),
        encoding="utf-8",
    )
    (config_dir / "player_rosters.yaml").write_text("teams: []\n", encoding="utf-8")
    return path


def write_registry(tmp_path: Path) -> None:
    maps = tmp_path / "configs" / "maps"
    maps.mkdir(parents=True)
    (maps / "map_registry.yaml").write_text(
        """
registry_version: v1
maps:
- map_id: inferno
  display_name: Inferno
  game_map_name: de_inferno
  config_path: configs/maps/inferno.yaml
""".strip(),
        encoding="utf-8",
    )
    (maps / "inferno.yaml").write_text(
        """
map_id: inferno
display_name: Inferno
game_map_name: de_inferno
region_schema_version: v1
coordinate_system: {source: test}
physical_regions: []
semantic_groups: {}
bombsites: {}
aliases: {}
""".strip(),
        encoding="utf-8",
    )


def write_gold_frame(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(directory / f"{name}.parquet", index=False)
