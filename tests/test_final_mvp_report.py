from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.reporting.build_final_mvp_report import REQUIRED_LIMITATIONS, run_final_mvp_report


def _write_fixture(tmp_path: Path) -> Path:
    config = tmp_path / "configs" / "project.yaml"
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
parsed_silver_dir: {(tmp_path / 'data/silver/parsed_demos').as_posix()}
""".strip(),
        encoding="utf-8",
    )
    gold = tmp_path / "data" / "gold"
    root = tmp_path
    _write(gold / "analysis" / "t_side_tactical_eda", "t_side_eda_overview", [_eda_overview()])
    _write(gold / "analysis" / "t_side_tactical_eda", "t_side_site_distribution", [{"t_round_outcome": "plant_A"}])
    _write(gold / "analysis" / "t_side_tactical_findings", "t_side_key_findings", _key_findings())
    _write(
        gold / "analysis" / "t_side_manual_review",
        "manual_review_decision_template",
        [{"round_feature_id": "rf_1", "review_decision": "pending"}],
    )
    candidate = gold / "modeling" / "t_side_ab_candidate"
    _write(candidate, "candidate_model_selection", [_candidate_selection()])
    _write(candidate, "candidate_model_metrics", [_candidate_metrics()])
    _write(candidate, "candidate_model_confusion_matrix", _candidate_confusion())
    _write(candidate, "candidate_model_errors", [_candidate_error()])
    _write(candidate, "candidate_model_feature_set", _candidate_feature_set())
    _write(candidate, "candidate_model_feature_importance", [_candidate_importance()])
    _write(candidate, "candidate_model_comparison_vs_baseline", [_candidate_comparison()])
    _write(candidate, "candidate_model_decision", [_candidate_decision()])
    _write(candidate, "candidate_model_audit", [{"candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1"}])
    _write(root / "data" / "bronze" / "parse_quality", "parse_quality", [{"quality_status": "valid_full_map"}])
    _write(root / "data" / "silver" / "parsed_demos", "feature_eligible_demos", [{"parse_id": "parse_1"}])
    _write(
        gold / "feature_audit",
        "side_dataset_audit",
        [
            {"dataset_type": "t_side_all", "row_count": 10, "rounds_without_label": 4},
            {"dataset_type": "t_side_planted", "row_count": 6},
        ],
    )
    _write(gold / "round_state", "round_state_audit", [{"total_rounds": 20}])
    return config


def _eda_overview() -> dict[str, object]:
    return {
        "total_t_side_rounds": 10,
        "total_plant_A": 4,
        "total_plant_B": 2,
        "total_no_plant": 4,
        "plant_rate": 0.60,
    }


def _key_findings() -> list[dict[str, object]]:
    return [
        {
            "finding_id": f"finding_{index:03d}",
            "finding_category": "A_vs_B_region",
            "finding_text": f"Fixture finding {index}",
            "support_table": "t_side_ab_region_differences",
            "support_metric": "abs_share_diff",
            "round_count": 4,
            "evidence_strength": "strong_candidate",
            "needs_manual_review": index % 2 == 0,
        }
        for index in range(1, 5)
    ]


def _candidate_selection() -> dict[str, object]:
    return {
        "candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1",
        "target_team": "Vitality",
        "target_map": "Mirage",
        "candidate_horizon_seconds": 35,
        "candidate_feature_set": "stable_only",
        "candidate_model_name": "logistic_regression",
        "selection_mode": "explicit",
        "selection_reason": "fixture",
        "source_stage": "Stage 6.2",
        "source_table": "ab_refined_metrics",
        "selected_at": "2026-07-08T00:00:00+00:00",
        "status": "selected",
    }


def _candidate_metrics() -> dict[str, object]:
    return {
        "candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1",
        "horizon_seconds": 35,
        "feature_set_name": "stable_only",
        "model_name": "logistic_regression",
        "accuracy": 0.70,
        "balanced_accuracy": 0.68,
        "macro_f1": 0.67,
        "recall_A": 0.75,
        "recall_B": 0.60,
        "precision_A": 0.80,
        "precision_B": 0.50,
        "support_A": 4,
        "support_B": 2,
        "total_errors": 2,
        "A_predicted_as_B": 1,
        "B_predicted_as_A": 1,
        "high_confidence_errors": 1,
        "high_confidence_B_predicted_as_A": 1,
    }


def _candidate_confusion() -> list[dict[str, object]]:
    return [
        {"candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1", "true_label": "A", "predicted_label": "A", "count": 3},
        {"candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1", "true_label": "A", "predicted_label": "B", "count": 1},
        {"candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1", "true_label": "B", "predicted_label": "A", "count": 1},
        {"candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1", "true_label": "B", "predicted_label": "B", "count": 1},
    ]


def _candidate_error() -> dict[str, object]:
    return {
        "candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1",
        "round_feature_id": "rf_1",
        "error_type": "B_predicted_as_A",
        "suggested_review_priority": "high",
    }


def _candidate_feature_set() -> list[dict[str, object]]:
    return [
        {
            "candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1",
            "feature_name": "__feature_set_summary__",
            "total_selected_features": 2,
        },
        {
            "candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1",
            "feature_name": "players_mid_control_0_35",
            "total_selected_features": 2,
        },
    ]


def _candidate_importance() -> dict[str, object]:
    return {
        "candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1",
        "feature_name": "players_mid_control_0_35",
        "importance_rank": 1,
    }


def _candidate_comparison() -> dict[str, object]:
    return {
        "candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1",
        "delta_macro_f1": 0.11,
        "delta_recall_B": 0.16,
        "delta_B_predicted_as_A": -1,
    }


def _candidate_decision() -> dict[str, object]:
    return {
        "candidate_id": "vitality_mirage_t_ab_35s_stable_only_logistic_v1",
        "decision": "promote_as_exploratory_candidate",
        "decision_status": "manual_review_pending",
    }


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def test_final_report_cli_dry_run(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "src.reporting.build_final_mvp_report", "--config", str(config), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Final MVP Report Pack summary" in result.stdout
    assert not (tmp_path / "data/gold/reporting/final_mvp").exists()


def test_final_report_outputs_docs_and_notebook_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, outputs, _ = run_final_mvp_report(config, force=True)

    assert len(frames["final_project_summary"]) == 1
    assert all(path.exists() for path in outputs.values())
    assert (tmp_path / "docs/final_mvp_report.md").exists()
    assert (tmp_path / "docs/final_mvp_technical_appendix.md").exists()
    assert (tmp_path / "docs/final_presentation_outline.md").exists()
    assert (tmp_path / "notebooks/13_final_mvp_report_pack.ipynb").exists()
    json.loads((tmp_path / "notebooks/13_final_mvp_report_pack.ipynb").read_text(encoding="utf-8"))


def test_stage_status_contains_stage_1_to_stage_7(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_final_mvp_report(config, dry_run=True)
    stages = set(frames["final_pipeline_stage_status"]["stage_id"])

    assert {"Stage 1", "Stage 2", "Stage 3", "Stage 3.6", "Stage 4", "Stage 4.2", "Stage 4.3", "Stage 5", "Stage 5.1", "Stage 5.2", "Stage 6", "Stage 6.1", "Stage 6.2", "Stage 6.3", "Stage 7"} <= stages


def test_dataset_snapshot_and_candidate_summary(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_final_mvp_report(config, dry_run=True)
    snapshot = frames["final_dataset_snapshot"].iloc[0]
    candidate = frames["final_model_candidate_summary"].iloc[0]

    assert snapshot["eligible_demos"] == 1
    assert snapshot["feature_rounds"] == 20
    assert snapshot["plant_A"] == 4
    assert candidate["candidate_id"] == "vitality_mirage_t_ab_35s_stable_only_logistic_v1"


def test_limitations_next_steps_manifest_and_audit(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_final_mvp_report(config, dry_run=True)

    assert set(REQUIRED_LIMITATIONS) <= set(frames["final_limitations"]["limitation_id"])
    assert not frames["final_next_steps"].empty
    assert frames["final_artifact_manifest"]["exists"].any()
    assert len(frames["final_report_audit"]) == 1
