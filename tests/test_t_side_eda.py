from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.analysis.t_side_eda import OUTPUT_NAMES, build_feature_catalog, run_t_side_eda
from src.features.feature_windows import FeatureWindow


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "configs" / "project.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-07-06"
target_maps:
  - Mirage
target_teams:
  - Vitality
output_formats:
  - csv
  - parquet
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
feature_windows:
  round_duration_seconds: 115
  interval_windows:
    - [0, 15]
    - [15, 115]
  cumulative_windows:
    - [0, 15]
    - [0, 115]
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_gold_inputs(tmp_path: Path) -> Path:
    config_path = _write_config(tmp_path)
    gold = tmp_path / "data/gold"
    round_dir = gold / "round_features"
    progression_dir = gold / "round_progression"
    state_dir = gold / "round_state"
    utility_dir = gold / "utility_events"
    for path in [round_dir, progression_dir, state_dir, utility_dir]:
        path.mkdir(parents=True)

    t_side_all = pd.DataFrame(
        [
            _round("r1", "T", "A", "high", True, "T"),
            _round("r2", "T", "B", "high", True, "CT"),
            _round("r3", "T", None, None, False, "T"),
            _round("r4", "CT", None, None, False, "CT"),
        ]
    )
    t_side_all.to_parquet(round_dir / "round_features_t_side_all.parquet", index=False)
    t_side_all[t_side_all["round_id"].isin(["r1", "r2"])].to_parquet(
        round_dir / "round_features_t_side_planted.parquet", index=False
    )

    state = pd.DataFrame(
        [
            {"round_id": "r1", "team_t": "Vitality", "team_ct": "G2", "target_team_planted": True, "opponent_planted": False, "planting_team": "Vitality"},
            {"round_id": "r2", "team_t": "Vitality", "team_ct": "Spirit", "target_team_planted": True, "opponent_planted": False, "planting_team": "Vitality"},
            {"round_id": "r3", "team_t": "Vitality", "team_ct": "FURIA", "target_team_planted": False, "opponent_planted": False, "planting_team": None},
            {"round_id": "r4", "team_t": "G2", "team_ct": "Vitality", "target_team_planted": False, "opponent_planted": False, "planting_team": None},
        ]
    )
    state.to_parquet(state_dir / "round_state_resolved.parquet", index=False)

    timeline_rows = []
    for round_id in ["r1", "r2", "r3", "r4"]:
        for window_type, start, end in [("interval", 0, 15), ("interval", 15, 115), ("cumulative", 0, 15), ("cumulative", 0, 115)]:
            timeline_rows.append(
                {
                    "round_feature_id": round_id,
                    "window_type": window_type,
                    "window_start": start,
                    "window_end": end,
                    "region_group": "MID_CONTROL" if round_id != "r2" else "B_PRESSURE",
                    "players_count_avg": 2.0,
                    "players_count_max": 4,
                    "time_spent_total": 10,
                }
            )
    pd.DataFrame(timeline_rows).to_parquet(progression_dir / "round_region_timeline.parquet", index=False)

    deaths = pd.DataFrame(
        [
            {"round_feature_id": "r1", "death_order": 1, "death_tick": 100, "seconds_from_freeze_end": 10.0, "death_region_group": "MID_CONTROL", "is_target_team_death": False, "is_opponent_death": True},
            {"round_feature_id": "r3", "death_order": 1, "death_tick": 200, "seconds_from_freeze_end": 100.0, "death_region_group": "A_PRESSURE", "is_target_team_death": True, "is_opponent_death": False},
        ]
    )
    deaths.to_parquet(progression_dir / "death_context_by_round.parquet", index=False)

    bomb = pd.DataFrame(
        [
            {"round_feature_id": "r1", "window_type": "interval", "window_start": 0, "window_end": 15, "bomb_carrier_region_group": "MID_CONTROL", "bomb_dropped": False, "bomb_drop_region_group": None},
            {"round_feature_id": "r3", "window_type": "interval", "window_start": 105, "window_end": 115, "bomb_carrier_region_group": "A_PRESSURE", "bomb_dropped": True, "bomb_drop_region_group": "A_PRESSURE"},
        ]
    )
    bomb.to_parquet(progression_dir / "bomb_carrier_timeline.parquet", index=False)

    outcomes = pd.DataFrame(
        [
            _outcome("r1", "MID_CONTROL>A_PRESSURE>PLANT_A", "A_PRESSURE", "plant_A"),
            _outcome("r2", "B_PRESSURE>PLANT_B", "B_PRESSURE", "plant_B"),
            _outcome("r3", "MID_CONTROL>no_plant", "MID_CONTROL", "no_plant_target_team_win"),
            _outcome("r4", "CT_CONTEXT", "MID_CONTROL", "unknown"),
        ]
    )
    outcomes.to_parquet(progression_dir / "round_outcome_context.parquet", index=False)

    utility = pd.DataFrame(
        [
            {"round_feature_id": "r1", "utility_type": "smoke", "seconds_from_freeze_end": 10.0, "end_region_group": "UNKNOWN", "throw_region_group": "MID_CONTROL"},
            {"round_feature_id": "r2", "utility_type": "molotov", "seconds_from_freeze_end": 100.0, "end_region_group": "B_PRESSURE", "throw_region_group": "B_PRESSURE"},
            {"round_feature_id": "r3", "utility_type": "smoke", "seconds_from_freeze_end": 110.0, "end_region_group": "UNKNOWN", "throw_region_group": "A_PRESSURE"},
        ]
    )
    utility.to_parquet(utility_dir / "utility_events.parquet", index=False)
    return config_path


def _round(round_id: str, side: str, label: str | None, confidence: str | None, planted: bool, winner_side: str) -> dict[str, object]:
    return {
        "round_feature_id": round_id,
        "round_id": round_id,
        "parse_id": f"parse_{round_id}",
        "dem_file_id": f"dem_{round_id}",
        "series_id": "series_1" if round_id in {"r1", "r2"} else "series_2",
        "target_team": "Vitality",
        "opponent": "unknown",
        "map_name": "Mirage",
        "target_team_side": side,
        "target_site_model_label": label,
        "target_site_observed": label,
        "label_confidence": confidence,
        "label_source": "target_team_plant" if label else "missing",
        "bomb_planted": planted,
        "winner_side": winner_side,
        "winner_team": "unknown",
        "smokes_used_0_15": 1,
        "players_mid_control_0_15": 2,
    }


def _outcome(round_id: str, signature: str, region: str, outcome_type: str) -> dict[str, object]:
    return {
        "round_feature_id": round_id,
        "round_progression_signature": signature,
        "first_target_team_death_region": region,
        "last_target_team_death_region": region,
        "first_contact_region": region,
        "bomb_drop_region": region,
        "bomb_last_known_region": region,
        "max_pressure_region_0_115": region,
        "max_pressure_region_0_55": region,
        "final_pressure_region_105_115": region,
        "round_failure_context": "first_target_death" if "no_plant" in outcome_type else None,
        "round_outcome_type": outcome_type,
    }


def test_cli_runs_in_dry_run_without_writing_outputs(tmp_path: Path) -> None:
    config_path = _write_gold_inputs(tmp_path)

    result = subprocess.run(
        [sys.executable, "-m", "src.analysis.t_side_eda", "--config", str(config_path), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "total_t_side_rounds: 3" in result.stdout
    assert not (tmp_path / "data/gold/analysis/t_side_tactical_eda").exists()


def test_stage5_outputs_and_totals_are_correct(tmp_path: Path) -> None:
    config_path = _write_gold_inputs(tmp_path)

    frames, outputs, summary = run_t_side_eda(config_path, force=True)

    overview = frames["t_side_eda_overview"].iloc[0]
    assert summary == {"total_t_side_rounds": 3, "plant_A": 1, "plant_B": 1, "no_plant": 1, "unknown": 0, "output_tables": 11}
    assert overview["total_t_side_rounds"] == 3
    assert overview["total_plant_A"] == 1
    assert overview["total_plant_B"] == 1
    assert overview["total_no_plant"] == 1
    assert frames["t_side_eda_audit"].loc[0, "ct_rows_in_analysis"] == 0
    assert frames["t_side_eda_audit"].loc[0, "planted_input_all_high_confidence"]
    assert len(outputs) == len(OUTPUT_NAMES) * 2
    assert all(path.exists() for path in outputs.values())


def test_window_outputs_preserve_types_and_reach_115(tmp_path: Path) -> None:
    config_path = _write_gold_inputs(tmp_path)

    frames, _, _ = run_t_side_eda(config_path, dry_run=True)

    region = frames["t_side_window_region_summary"]
    utility = frames["t_side_window_utility_summary"]
    assert set(region["window_type"]) == {"interval", "cumulative"}
    assert set(utility["window_type"]) == {"interval", "cumulative"}
    assert region["window_end"].max() == 115
    assert utility["window_end"].max() == 115


def test_feature_catalog_marks_labels_and_outcomes_as_leakage() -> None:
    catalog = build_feature_catalog(
        ["target_site_model_label", "label_confidence", "winner_side", "players_mid_control_0_15", "smokes_used_15_115"],
        [FeatureWindow(0, 15, "interval"), FeatureWindow(0, 15, "cumulative"), FeatureWindow(15, 115, "interval")],
    ).set_index("column_name")

    assert not bool(catalog.loc["target_site_model_label", "usable_for_future_model"])
    assert not bool(catalog.loc["label_confidence", "usable_for_future_model"])
    assert not bool(catalog.loc["winner_side", "usable_for_future_model"])
    assert bool(catalog.loc["players_mid_control_0_15", "usable_for_future_model"])
    assert catalog.loc["players_mid_control_0_15", "window_type"] == "both"
    assert catalog.loc["smokes_used_15_115", "window_type"] == "interval"
