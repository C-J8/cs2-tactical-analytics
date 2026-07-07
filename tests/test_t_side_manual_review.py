from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.analysis.t_side_manual_review import OUTPUT_NAMES, run_t_side_manual_review


def _write_fixture(tmp_path: Path) -> Path:
    config_path = tmp_path / "configs" / "project.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"""
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-07-07"
target_maps: [Mirage]
target_teams: [Vitality]
output_formats: [csv, parquet]
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
dem_files_manifest_path: {(tmp_path / 'data/bronze/dem_files_manifest/dem_files_manifest.parquet').as_posix()}
""".strip(),
        encoding="utf-8",
    )
    gold = tmp_path / "data" / "gold"
    findings_dir = gold / "analysis" / "t_side_tactical_findings"
    eda_dir = gold / "analysis" / "t_side_tactical_eda"
    findings_dir.mkdir(parents=True)
    eda_dir.mkdir(parents=True)

    base_rounds = [
        _round("r_a", "plant_A", "A", "high", 1),
        _round("r_b", "plant_B", "B", "high", 2),
        _round("r_n", "no_plant", None, None, 3),
        {**_round("r_ct", "no_plant", None, None, 4), "target_team_side": "CT"},
    ]
    _write(gold / "round_features", "round_features_t_side_all", base_rounds)
    _write(gold / "round_features", "round_features_t_side_planted", base_rounds[:2])
    _write(
        gold / "round_progression",
        "round_region_timeline",
        [
            _region("r_a", "A_PRESSURE", 20, 3),
            _region("r_b", "B_PRESSURE", 18, 3),
            _region("r_n", "MID_CONTROL", 15, 2),
        ],
    )
    _write(
        gold / "round_progression",
        "death_context_by_round",
        [
            {
                "round_feature_id": "r_n",
                "death_order": 1,
                "death_tick": 100,
                "is_target_team_death": True,
                "death_region_group": "MID_CONTROL",
            }
        ],
    )
    _write(
        gold / "round_progression",
        "bomb_carrier_timeline",
        [
            {
                "round_feature_id": "r_n",
                "window_type": "interval",
                "window_start": 105,
                "window_end": 115,
                "bomb_carrier_region_group": "MID_CONTROL",
                "bomb_drop_region_group": "A_PRESSURE",
            }
        ],
    )
    _write(gold / "round_progression", "round_outcome_context", [_context(row) for row in base_rounds])
    _write(gold / "round_state", "round_state_resolved", [{"round_id": row["round_id"]} for row in base_rounds])
    _write(
        gold / "utility_events",
        "utility_events",
        [
            _utility("u_a", "r_a", "A_PRESSURE", 7),
            _utility("u_b", "r_b", "B_PRESSURE", 8),
        ],
    )
    _write(
        eda_dir,
        "t_side_feature_catalog",
        [
            {"column_name": "players_mid_control_0_15", "usable_for_future_model": True, "notes": "predictor"},
            {"column_name": "target_site_model_label", "usable_for_future_model": False, "notes": "target leakage"},
        ],
    )
    _write_finding_inputs(findings_dir)
    return config_path


def _round(round_id: str, outcome: str, label: str | None, confidence: str | None, round_num: int) -> dict[str, object]:
    return {
        "round_feature_id": round_id,
        "round_id": round_id,
        "series_id": "series_1",
        "dem_file_id": "demo_1",
        "parse_id": "parse_1",
        "target_team": "Vitality",
        "opponent": "G2",
        "map_name": "Mirage",
        "round_num": round_num,
        "half": 1,
        "target_team_side": "T",
        "target_site_model_label": label,
        "label_confidence": confidence,
        "winner_side": "T" if outcome != "no_plant" else "CT",
        "winner_team": "Vitality" if outcome != "no_plant" else "G2",
        "bomb_planted": outcome != "no_plant",
    }


def _context(row: dict[str, object]) -> dict[str, object]:
    label = row["target_site_model_label"]
    outcome = f"plant_{label}" if label else "bomb_lost_before_plant"
    return {
        "round_feature_id": row["round_feature_id"],
        "round_progression_signature": f"MID_CONTROL>{outcome}",
        "round_outcome_type": outcome,
        "first_target_team_death_region": "MID_CONTROL",
        "first_contact_region": "MID_CONTROL",
        "bomb_drop_region": "A_PRESSURE" if label is None else None,
        "bomb_last_known_region": "MID_CONTROL" if label is None else None,
        "max_pressure_region_0_115": "MID_CONTROL",
        "max_pressure_region_0_55": "MID_CONTROL",
        "final_pressure_region_105_115": "MID_CONTROL",
    }


def _region(round_id: str, region: str, time_spent: int, players: int) -> dict[str, object]:
    return {
        "round_feature_id": round_id,
        "window_type": "interval",
        "window_start": 0,
        "window_end": 15,
        "region_group": region,
        "players_count_avg": float(players),
        "players_count_max": players,
        "time_spent_total": time_spent,
    }


def _utility(event_id: str, round_id: str, region: str, seconds: int) -> dict[str, object]:
    return {
        "utility_event_id": event_id,
        "round_feature_id": round_id,
        "utility_type": "smoke",
        "seconds_from_freeze_end": seconds,
        "end_region_group": region,
        "throw_region_group": "T_SPAWN_AREA",
    }


def _write_finding_inputs(directory: Path) -> None:
    key = [
        {
            "finding_id": "finding_001",
            "finding_category": "A_vs_B_region",
            "finding_text": "A_PRESSURE in interval 0-15s appears more associated with plant_A by 50.0% share difference.",
            "support_table": "t_side_ab_region_differences",
            "support_metric": "abs_share_diff",
            "round_count": 4,
            "evidence_strength": "strong_candidate",
            "needs_manual_review": False,
        },
        {
            "finding_id": "finding_002",
            "finding_category": "A_vs_B_region",
            "finding_text": "B_PRESSURE in interval 0-15s appears more associated with plant_B by 45.0% share difference.",
            "support_table": "t_side_ab_region_differences",
            "support_metric": "abs_share_diff",
            "round_count": 3,
            "evidence_strength": "strong_candidate",
            "needs_manual_review": False,
        },
        {
            "finding_id": "finding_003",
            "finding_category": "no_plant",
            "finding_text": "No-plant rounds show bomb drop region around A_PRESSURE in 1 rounds (33.3%), suggesting this context should be manually reviewed.",
            "support_table": "t_side_no_plant_failure_findings",
            "support_metric": "round_share",
            "round_count": 1,
            "evidence_strength": "medium_candidate",
            "needs_manual_review": True,
        },
    ]
    _write(directory, "t_side_key_findings", key)
    _write(
        directory,
        "t_side_ab_region_differences",
        [
            {"window_type": "interval", "window_start": 0, "window_end": 15, "region_group": "A_PRESSURE"},
            {"window_type": "interval", "window_start": 0, "window_end": 15, "region_group": "B_PRESSURE"},
        ],
    )
    _write(directory, "t_side_ab_utility_differences", [], columns=["window_type", "window_start", "window_end", "region_group"])
    _write(directory, "t_side_ab_timing_breakpoints", [], columns=["window_type", "window_start", "window_end"])
    _write(
        directory,
        "t_side_no_plant_failure_findings",
        [
            {
                "t_round_outcome": "no_plant",
                "finding_type": "bomb_drop_region",
                "finding_value": "A_PRESSURE",
                "round_count": 1,
                "round_share": 1.0,
                "evidence_strength": "medium_candidate",
                "finding_text": key[2]["finding_text"],
            }
        ],
    )
    _write(directory, "t_side_bomb_carrier_findings", [], columns=["finding_text"])
    _write(directory, "t_side_opponent_tendencies", [], columns=["finding_text"])
    _write(directory, "t_side_progression_findings", [], columns=["finding_text"])
    _write(
        directory,
        "t_side_manual_review_queue",
        [
            {
                "review_id": "review_001",
                "priority": "high",
                "reason": "Inspect no-plant bomb loss",
                "suggested_filter": "t_round_outcome=no_plant and bomb_drop_region=A_PRESSURE",
                "related_table": "t_side_no_plant_failure_findings",
                "expected_question": "Where was C4 control lost?",
            }
        ],
    )
    _write(directory, "t_side_findings_audit", [{"status": "ok", "max_window_end": 115}])


def _write(directory: Path, name: str, rows: list[dict[str, object]], columns: list[str] | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_parquet(directory / f"{name}.parquet", index=False)


def test_manual_review_cli_dry_run_does_not_write_outputs(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "src.analysis.t_side_manual_review", "--config", str(config), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "T-side Manual Review Pack summary" in result.stdout
    assert not (tmp_path / "data/gold/analysis/t_side_manual_review").exists()


def test_manual_review_outputs_and_report_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, outputs, _ = run_t_side_manual_review(config, force=True, top_n_findings=10)

    assert len(outputs) == len(OUTPUT_NAMES) * 2 + 1
    assert all(path.exists() for path in outputs.values())
    assert not frames["manual_review_rounds"].empty
    assert outputs["markdown_report"].read_text(encoding="utf-8").startswith("# T-side Manual Review Pack")


def test_review_rounds_keep_t_side_outcome_and_label_rules(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_manual_review(config, dry_run=True, top_n_findings=10)
    review = frames["manual_review_rounds"]

    assert set(review["target_team_side"]) == {"T"}
    assert set(review["t_round_outcome"]) <= {"plant_A", "plant_B", "no_plant"}
    no_plant = review[review["finding_category"] == "no_plant"]
    assert set(no_plant["t_round_outcome"]) == {"no_plant"}
    ab = review[review["finding_category"].str.startswith("A_vs_B")]
    assert set(ab["label_confidence"]) == {"high"}


def test_evidence_preserves_window_and_decisions_are_pending(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_manual_review(config, dry_run=True, top_n_findings=10)
    evidence = frames["manual_review_evidence_by_round"]
    decisions = frames["manual_review_decision_template"]

    regional = evidence[evidence["evidence_type"] == "region_presence"]
    assert set(regional["window_start"]) == {0}
    assert set(regional["window_end"]) == {15}
    assert set(decisions["review_decision"]) == {"pending"}


def test_readiness_and_audit_are_generated(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_manual_review(config, dry_run=True, top_n_findings=10)

    assert "overall_readiness" in set(frames["manual_review_model_readiness"]["readiness_check"])
    assert frames["manual_review_audit"].iloc[0]["status"] == "ok"
