from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from src.modeling.t_side_ab_baseline import (
    OUTPUT_NAMES,
    load_inputs,
    prepare_model_dataset,
    run_t_side_ab_baseline,
    select_features_for_horizon,
)


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
    rows = [_model_row(index, "A" if index < 6 else "B") for index in range(12)]
    rows.extend(
        [
            {**_model_row(12, "A"), "target_site_model_label": None, "label_confidence": None, "bomb_planted": False},
            {**_model_row(13, "B"), "label_confidence": "low"},
        ]
    )
    _write(gold / "round_features", "round_features_t_side_planted", rows)
    _write(gold / "analysis" / "t_side_tactical_eda", "t_side_feature_catalog", _catalog_rows())
    manual = gold / "analysis" / "t_side_manual_review"
    _write(manual, "manual_review_model_readiness", [{"readiness_check": "overall", "status": "pass"}])
    _write(
        manual,
        "manual_review_decision_template",
        [{"round_feature_id": row["round_feature_id"], "review_decision": "pending"} for row in rows[:12]],
    )
    _write(manual, "manual_review_rounds", [{"round_feature_id": row["round_feature_id"]} for row in rows[:12]])
    _write(
        gold / "round_state",
        "round_state_resolved",
        [
            {
                "round_id": row["round_id"],
                "plant_tick": 6400,
                "freeze_end_tick": 0,
            }
            for row in rows
        ],
    )
    return config


def _model_row(index: int, label: str) -> dict[str, object]:
    return {
        "round_feature_id": f"rf_{index}",
        "round_id": f"round_{index}",
        "parse_id": "parse_1",
        "dem_file_id": "demo_1",
        "series_id": f"series_{index // 2}",
        "local_archive_id": "archive_1",
        "dataset_type": "t_side_planted",
        "target_team": "Vitality",
        "opponent": "G2" if index % 2 else "Spirit",
        "map_name": "Mirage",
        "round_num": index + 1,
        "half": 1,
        "target_team_side": "T",
        "target_site_model_label": label,
        "label_confidence": "high",
        "winner_team": "Vitality",
        "bomb_planted": True,
        "bombsite": label,
        "freeze_end_tick": 0,
        "score_diff_before_round": index - 5,
        "is_pistol_round": index in {0, 6},
        "team_smokes_start": 5,
        "players_mid_control_0_15": index % 4,
        "team_center_x_15s": float(index),
        "players_a_pressure_15_25": index % 3,
        "players_b_pressure_25_35": index % 5,
        "unsafe_metric_0_15": index,
        "round_end_tick": 9000,
    }


def _catalog_rows() -> list[dict[str, object]]:
    rows = []
    for column, group, start, end, usable in [
        ("round_num", "context", None, None, True),
        ("half", "context", None, None, True),
        ("score_diff_before_round", "context", None, None, True),
        ("is_pistol_round", "context", None, None, True),
        ("team_smokes_start", "utility", None, None, True),
        ("players_mid_control_0_15", "region_position", 0, 15, True),
        ("team_center_x_15s", "region_position", None, None, True),
        ("players_a_pressure_15_25", "region_position", 15, 25, True),
        ("players_b_pressure_25_35", "region_position", 25, 35, True),
        ("unsafe_metric_0_15", "audit", 0, 15, False),
        ("winner_team", "outcome", None, None, False),
        ("target_site_model_label", "label", None, None, False),
        ("round_end_tick", "context", None, None, True),
    ]:
        rows.append(
            {
                "column_name": column,
                "inferred_feature_group": group,
                "window_start": start,
                "window_end": end,
                "window_type": "interval" if start not in {None, 0} else "cumulative" if end else None,
                "usable_for_future_model": usable,
                "notes": None,
            }
        )
    return rows


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def test_baseline_cli_dry_run_does_not_write_outputs(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.modeling.t_side_ab_baseline",
            "--config",
            str(config),
            "--dry-run",
            "--horizons",
            "15",
            "--model-set",
            "baseline,logistic",
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "T-side A/B Baseline Model summary" in result.stdout
    assert not (tmp_path / "data/gold/modeling/t_side_ab_baseline").exists()


def test_model_dataset_filters_to_high_confidence_ab(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    gold = config.parent.parent / "data" / "gold"
    dataset, audit = prepare_model_dataset(load_inputs(gold), target_team="Vitality", target_map="Mirage")

    assert set(dataset["target_site_model_label"]) == {"A", "B"}
    assert set(dataset["label_confidence"]) == {"high"}
    assert "no_plant" not in set(dataset["target_site_model_label"])
    assert audit.iloc[0]["final_model_rows"] == 12


def test_feature_selection_blocks_leakage_and_future_windows(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    gold = config.parent.parent / "data" / "gold"
    inputs = load_inputs(gold)
    dataset, _ = prepare_model_dataset(inputs, target_team="Vitality", target_map="Mirage")
    features_15, _ = select_features_for_horizon(dataset, inputs["feature_catalog"], horizon=15, include_opponent=False)
    features_25, _ = select_features_for_horizon(dataset, inputs["feature_catalog"], horizon=25, include_opponent=False)

    assert "players_mid_control_0_15" in features_15
    assert "team_center_x_15s" in features_15
    assert "players_a_pressure_15_25" not in features_15
    assert "players_a_pressure_15_25" in features_25
    assert "players_b_pressure_25_35" not in features_25
    assert "winner_team" not in features_25
    assert "unsafe_metric_0_15" not in features_25
    assert "round_end_tick" not in features_25
    assert "round_feature_id" not in features_25


def test_metrics_predictions_confusion_and_importance_are_generated(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_t_side_ab_baseline(
        config,
        dry_run=True,
        horizons=[15, 25],
        model_set=["baseline", "logistic"],
    )

    assert set(frames["ab_model_metrics"]["model_name"]) == {"majority_baseline", "logistic_regression"}
    assert not frames["ab_model_confusion_matrices"].empty
    assert not frames["ab_model_predictions"].empty
    assert set(frames["ab_model_predictions"]["true_label"]) == {"A", "B"}
    assert not frames["ab_model_feature_importance"].empty


def test_outputs_and_markdown_report_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    _, outputs, _ = run_t_side_ab_baseline(
        config,
        force=True,
        horizons=[15],
        model_set=["baseline", "logistic"],
    )

    assert len(outputs) == len(OUTPUT_NAMES) * 2 + 1
    assert all(path.exists() for path in outputs.values())
    assert outputs["markdown_report"].read_text(encoding="utf-8").startswith("# T-side A/B Baseline Model")
