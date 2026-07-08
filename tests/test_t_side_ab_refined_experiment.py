from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.modeling.t_side_ab_refined_experiment import OUTPUT_NAMES, run_t_side_ab_refined_experiment


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
    rows = [_round(index, "A" if index < 6 else "B") for index in range(12)]
    rows.extend(
        [
            {**_round(12, "A"), "target_site_model_label": None, "label_confidence": None},
            {**_round(13, "B"), "label_confidence": "low"},
        ]
    )
    _write(gold / "round_features", "round_features_t_side_planted", rows)
    _write(gold / "analysis" / "t_side_tactical_eda", "t_side_feature_catalog", _catalog())
    _write(
        gold / "analysis" / "t_side_manual_review",
        "manual_review_decision_template",
        [{"round_feature_id": row["round_feature_id"], "review_decision": "pending"} for row in rows[:12]],
    )
    baseline = gold / "modeling" / "t_side_ab_baseline"
    _write(baseline, "ab_model_metrics", _baseline_metrics())
    _write(baseline, "ab_model_predictions", _baseline_predictions())
    _write(baseline, "ab_model_feature_importance", _baseline_importance())
    return config


def _round(index: int, label: str) -> dict[str, object]:
    return {
        "round_feature_id": f"rf_{index}",
        "round_id": f"round_{index}",
        "parse_id": "parse_1",
        "dem_file_id": "demo_1",
        "series_id": f"series_{index // 2}",
        "local_archive_id": "archive_1",
        "dataset_type": "t_side_planted",
        "target_team": "Vitality",
        "opponent": "G2",
        "map_name": "Mirage",
        "round_num": index + 1,
        "half": 1,
        "target_team_side": "T",
        "target_site_model_label": label,
        "label_confidence": "high",
        "winner_team": "Vitality",
        "bomb_planted": True,
        "bombsite": label,
        "score_diff_before_round": index - 4,
        "is_pistol_round": index in {0, 6},
        "team_smokes_start": 5,
        "team_flashes_start": 4,
        "players_mid_control_0_15": index % 4,
        "players_b_pressure_0_15": index % 5,
        "smokes_to_b_pressure_0_15": index % 2,
        "time_a_pressure_15_25": index % 3,
        "winner_signal_0_15": index,
    }


def _catalog() -> list[dict[str, object]]:
    rows = []
    definitions = [
        ("round_num", "context", None, None, True),
        ("half", "context", None, None, True),
        ("score_diff_before_round", "context", None, None, True),
        ("is_pistol_round", "context", None, None, True),
        ("team_smokes_start", "utility", None, None, True),
        ("team_flashes_start", "utility", None, None, True),
        ("players_mid_control_0_15", "region_position", 0, 15, True),
        ("players_b_pressure_0_15", "region_position", 0, 15, True),
        ("smokes_to_b_pressure_0_15", "utility", 0, 15, True),
        ("time_a_pressure_15_25", "region_position", 15, 25, True),
        ("winner_signal_0_15", "outcome", 0, 15, False),
    ]
    for column, group, start, end, usable in definitions:
        rows.append(
            {
                "column_name": column,
                "inferred_feature_group": group,
                "window_start": start,
                "window_end": end,
                "window_type": "interval" if end else None,
                "usable_for_future_model": usable,
                "notes": None,
            }
        )
    return rows


def _baseline_metrics() -> list[dict[str, object]]:
    rows = []
    for model in ["logistic_regression", "random_forest"]:
        rows.append(
            {
                "horizon_seconds": 15,
                "model_name": model,
                "macro_f1": 0.60,
                "recall_B": 0.50,
            }
        )
    return rows


def _baseline_predictions() -> list[dict[str, object]]:
    rows = []
    for model in ["logistic_regression", "random_forest"]:
        for index in range(12):
            true = "A" if index < 6 else "B"
            predicted = "A" if index in {6, 7} else true
            rows.append(
                {
                    "horizon_seconds": 15,
                    "model_name": model,
                    "round_feature_id": f"rf_{index}",
                    "true_label": true,
                    "predicted_label": predicted,
                    "predicted_proba_A": 0.8 if predicted == "A" else 0.2,
                    "predicted_proba_B": 0.2 if predicted == "A" else 0.8,
                }
            )
    return rows


def _baseline_importance() -> list[dict[str, object]]:
    rows = []
    for model in ["logistic_regression", "random_forest"]:
        for rank, feature in enumerate(
            ["players_b_pressure_0_15", "players_mid_control_0_15", "team_smokes_start"],
            start=1,
        ):
            rows.append(
                {
                    "horizon": 15,
                    "model_name": model,
                    "feature_name": feature,
                    "importance_rank": rank,
                }
            )
    return rows


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def test_refined_cli_dry_run(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.modeling.t_side_ab_refined_experiment",
            "--config",
            str(config),
            "--dry-run",
            "--horizons",
            "15",
            "--model-set",
            "logistic",
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "T-side A/B Refined Experiment summary" in result.stdout
    assert not (tmp_path / "data/gold/modeling/t_side_ab_refined_experiment").exists()


def test_dataset_feature_sets_and_leakage_rules(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_refined_experiment(
        config,
        dry_run=True,
        horizons=[15],
        model_set=["logistic"],
    )
    audit = frames["ab_refined_dataset_audit"].iloc[0]
    feature_sets = frames["ab_refined_feature_sets"]

    assert audit["final_model_rows"] == 12
    assert audit["class_A"] == 6 and audit["class_B"] == 6
    assert set(feature_sets["feature_set_name"]) == {
        "all_safe",
        "stable_only",
        "no_preround_context",
        "region_utility_only",
        "b_focused",
    }
    assert feature_sets["total_selected_features"].gt(0).all()
    selected = "|".join(feature_sets["selected_feature_names"])
    assert "winner_signal_0_15" not in selected
    assert "time_a_pressure_15_25" not in selected


def test_metrics_predictions_confusion_and_errors_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_refined_experiment(
        config,
        dry_run=True,
        horizons=[15],
        model_set=["logistic"],
    )

    assert len(frames["ab_refined_metrics"]) == 5
    assert not frames["ab_refined_predictions"].empty
    assert not frames["ab_refined_confusion_matrices"].empty
    assert "B_predicted_as_A" in frames["ab_refined_error_summary"].columns


def test_baseline_comparison_and_recommendation_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_refined_experiment(
        config,
        dry_run=True,
        horizons=[15],
        model_set=["logistic"],
    )

    assert not frames["ab_refined_comparison_vs_baseline"].empty
    assert not frames["ab_refined_recommendation"].empty
    assert frames["ab_refined_recommendation"]["rank"].min() == 1


def test_outputs_and_markdown_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _, outputs, _ = run_t_side_ab_refined_experiment(
        config,
        force=True,
        horizons=[15],
        model_set=["logistic"],
    )

    assert len(outputs) == len(OUTPUT_NAMES) * 2 + 1
    assert all(path.exists() for path in outputs.values())
    assert outputs["markdown_report"].read_text(encoding="utf-8").startswith("# T-side A/B Refined Experiment")
