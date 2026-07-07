from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.analysis.t_side_findings import FINDING_OUTPUT_NAMES, run_t_side_findings


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
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_stage5_inputs(tmp_path: Path) -> Path:
    config_path = _write_config(tmp_path)
    stage5 = tmp_path / "data/gold/analysis/t_side_tactical_eda"
    stage5.mkdir(parents=True)
    _write(stage5, "t_side_eda_overview", [{"total_t_side_rounds": 12, "total_plant_A": 5, "total_plant_B": 4, "total_no_plant": 3, "total_unknown": 0, "plant_rate": 0.75}])
    _write(stage5, "t_side_site_distribution", [{"t_round_outcome": "plant_A", "round_count": 5}, {"t_round_outcome": "plant_B", "round_count": 4}, {"t_round_outcome": "no_plant", "round_count": 3}])
    _write(
        stage5,
        "t_side_opponent_summary",
        [
            {"opponent": "G2", "total_t_side_rounds": 7, "plant_A": 4, "plant_B": 1, "no_plant": 2, "plant_rate": 5 / 7, "A_share_when_planted": 0.8, "B_share_when_planted": 0.2, "winrate": 0.5},
            {"opponent": "Spirit", "total_t_side_rounds": 5, "plant_A": 1, "plant_B": 3, "no_plant": 1, "plant_rate": 0.8, "A_share_when_planted": 0.25, "B_share_when_planted": 0.75, "winrate": 0.6},
        ],
    )
    _write(stage5, "t_side_window_region_summary", _region_rows())
    _write(stage5, "t_side_window_utility_summary", _utility_rows())
    _write(
        stage5,
        "t_side_no_plant_summary",
        [
            {"first_target_team_death_region": "MID_CONTROL", "first_contact_region": "MID_CONTROL", "bomb_drop_region": "A_PRESSURE", "bomb_last_known_region": "A_PRESSURE", "max_pressure_region_0_115": "MID_CONTROL", "max_pressure_region_0_55": "MID_CONTROL", "final_pressure_region_105_115": "A_PRESSURE", "round_failure_context": "bomb_lost_A_PRESSURE", "round_outcome_type": "bomb_lost_before_plant", "round_count": 2, "round_share": 2 / 3},
            {"first_target_team_death_region": "B_PRESSURE", "first_contact_region": "B_PRESSURE", "bomb_drop_region": "UNKNOWN", "bomb_last_known_region": "B_PRESSURE", "max_pressure_region_0_115": "B_PRESSURE", "max_pressure_region_0_55": "B_PRESSURE", "final_pressure_region_105_115": "UNKNOWN", "round_failure_context": "first_target_death_B_PRESSURE", "round_outcome_type": "no_plant_target_team_loss", "round_count": 1, "round_share": 1 / 3},
        ],
    )
    _write(stage5, "t_side_death_summary", [{"death_type": "first_target_team_death", "region_group": "MID_CONTROL", "t_round_outcome": "no_plant", "window_type": "interval", "window_start": 0, "window_end": 15, "is_no_plant": True, "round_count": 3, "round_share": 1.0}])
    _write(
        stage5,
        "t_side_bomb_carrier_summary",
        [
            {"context_type": "carrier_region", "window_type": "interval", "window_start": 105, "window_end": 115, "region_group": "A_PRESSURE", "t_round_outcome": "no_plant", "is_late_round": True, "round_count": 3, "round_share": 1.0},
            {"context_type": "carrier_region", "window_type": "interval", "window_start": 95, "window_end": 105, "region_group": "B_PRESSURE", "t_round_outcome": "plant_B", "is_late_round": True, "round_count": 3, "round_share": 0.75},
        ],
    )
    _write(
        stage5,
        "t_side_progression_signature_summary",
        [
            {"round_progression_signature": "MID_CONTROL>A_PRESSURE>PLANT_A", "t_round_outcome": "plant_A", "count": 4, "share": 0.8, "winrate": 0.75, "opponents": "G2, Spirit"},
            {"round_progression_signature": "B_PRESSURE>PLANT_B", "t_round_outcome": "plant_B", "count": 3, "share": 0.75, "winrate": 2 / 3, "opponents": "Spirit"},
            {"round_progression_signature": "MID_CONTROL>no_plant", "t_round_outcome": "no_plant", "count": 3, "share": 1.0, "winrate": 0.0, "opponents": "G2"},
        ],
    )
    _write(stage5, "t_side_feature_catalog", [{"column_name": "players_mid_control_0_15", "usable_for_future_model": True}])
    _write(stage5, "t_side_eda_audit", [{"audit_id": "t_side_tactical_eda", "status": "ok", "max_window_end": 115}])
    return config_path


def _region_rows() -> list[dict[str, object]]:
    rows = []
    for window_type, start, end in [("interval", 0, 15), ("interval", 105, 115), ("cumulative", 0, 115)]:
        rows.extend(
            [
                {"window_type": window_type, "window_start": start, "window_end": end, "region_group": "A_PRESSURE", "t_round_outcome": "plant_A", "round_count": 5, "avg_players_count": 2.5, "max_players_count": 5, "avg_time_spent": 20.0, "round_share_with_region": 1.0},
                {"window_type": window_type, "window_start": start, "window_end": end, "region_group": "A_PRESSURE", "t_round_outcome": "plant_B", "round_count": 3, "avg_players_count": 1.0, "max_players_count": 3, "avg_time_spent": 5.0, "round_share_with_region": 0.25},
                {"window_type": window_type, "window_start": start, "window_end": end, "region_group": "B_PRESSURE", "t_round_outcome": "plant_A", "round_count": 3, "avg_players_count": 1.0, "max_players_count": 3, "avg_time_spent": 6.0, "round_share_with_region": 0.2},
                {"window_type": window_type, "window_start": start, "window_end": end, "region_group": "B_PRESSURE", "t_round_outcome": "plant_B", "round_count": 4, "avg_players_count": 2.5, "max_players_count": 5, "avg_time_spent": 18.0, "round_share_with_region": 1.0},
            ]
        )
    return rows


def _utility_rows() -> list[dict[str, object]]:
    rows = []
    for window_type, start, end in [("interval", 0, 15), ("interval", 105, 115), ("cumulative", 0, 115)]:
        for outcome, total, average, share, rounds in [("plant_A", 10, 2.0, 0.8, 4), ("plant_B", 4, 1.0, 0.25, 3)]:
            rows.append(
                {"window_type": window_type, "window_start": start, "window_end": end, "region_group": "MID_CONTROL", "t_round_outcome": outcome, "total_utilities": total, "avg_utilities_per_round": average, "smokes_per_round": average * 0.6, "molotovs_per_round": average * 0.4, "flashes_per_round": 0.0, "he_per_round": 0.0, "rounds_with_utility": rounds, "round_share_with_utility": share}
            )
    return rows


def _write(stage5: Path, name: str, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_parquet(stage5 / f"{name}.parquet", index=False)


def test_findings_cli_dry_run(tmp_path: Path) -> None:
    config_path = _write_stage5_inputs(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "src.analysis.t_side_findings", "--config", str(config_path), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "T-side Tactical Findings summary" in result.stdout
    assert not (tmp_path / "data/gold/analysis/t_side_tactical_findings").exists()


def test_findings_outputs_and_markdown_are_created(tmp_path: Path) -> None:
    config_path = _write_stage5_inputs(tmp_path)
    frames, outputs, _ = run_t_side_findings(config_path, force=True, min_rounds=3, top_n=5)

    assert len(outputs) == len(FINDING_OUTPUT_NAMES) * 2 + 1
    assert all(path.exists() for path in outputs.values())
    assert outputs["markdown_report"].read_text(encoding="utf-8").startswith("# T-side Tactical Findings -- Vitality Mirage")
    assert not frames["t_side_key_findings"].empty
    assert not frames["t_side_manual_review_queue"].empty


def test_ab_differences_and_timing_preserve_windows(tmp_path: Path) -> None:
    config_path = _write_stage5_inputs(tmp_path)
    frames, _, _ = run_t_side_findings(config_path, dry_run=True, min_rounds=3)

    region = frames["t_side_ab_region_differences"]
    utility = frames["t_side_ab_utility_differences"]
    timing = frames["t_side_ab_timing_breakpoints"]
    assert {"rounds_A", "rounds_B", "share_diff_A_minus_B"}.issubset(region.columns)
    assert set(utility["window_type"]) == {"interval", "cumulative"}
    assert timing["window_end"].max() == 115


def test_no_plant_findings_are_scoped_to_no_plant(tmp_path: Path) -> None:
    config_path = _write_stage5_inputs(tmp_path)
    frames, _, _ = run_t_side_findings(config_path, dry_run=True, min_rounds=3)
    no_plant = frames["t_side_no_plant_failure_findings"]

    assert not no_plant.empty
    assert set(no_plant["t_round_outcome"]) == {"no_plant"}
