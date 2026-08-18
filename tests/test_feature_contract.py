from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

from src.features.build_feature_contract import OUTPUT_NAMES, run_feature_contract


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
feature_windows:
  round_duration_seconds: 115
  interval_windows:
    - [0, 15]
    - [15, 25]
    - [25, 35]
    - [35, 45]
    - [45, 55]
    - [55, 65]
    - [65, 75]
    - [75, 85]
    - [85, 95]
    - [95, 105]
    - [105, 115]
  cumulative_windows:
    - [0, 15]
    - [0, 25]
    - [0, 35]
    - [0, 45]
    - [0, 55]
    - [0, 65]
    - [0, 75]
    - [0, 85]
    - [0, 95]
    - [0, 105]
    - [0, 115]
""".strip(),
        encoding="utf-8",
    )
    gold = tmp_path / "data" / "gold"
    _write(gold / "analysis" / "t_side_tactical_eda", "t_side_feature_catalog", _catalog_rows())
    rows = [_round_row()]
    _write(gold / "round_features", "round_features_mvp", rows)
    _write(gold / "round_features", "round_features_t_side_all", rows)
    _write(gold / "round_features", "round_features_t_side_planted", rows)
    _write(
        gold / "modeling" / "t_side_ab_baseline",
        "ab_model_feature_sets",
        [{"selected_feature_names": "team_smokes_start|players_mid_control_0_35|players_palace_control_0_15"}],
    )
    _write(
        gold / "modeling" / "t_side_ab_baseline",
        "ab_model_feature_importance",
        [{"feature_name": "players_mid_control_0_35", "importance_rank": 1, "importance_value": 0.5}],
    )
    _write(
        gold / "modeling" / "t_side_ab_candidate",
        "candidate_model_feature_set",
        [{"feature_name": "team_smokes_start"}, {"feature_name": "players_mid_control_0_35"}],
    )
    _write(
        gold / "modeling" / "t_side_ab_candidate",
        "candidate_model_feature_importance",
        [{"feature_name": "team_smokes_start", "importance_rank": 1, "importance_value": 0.7}],
    )
    return config


def _catalog_rows() -> list[dict[str, object]]:
    return [
        _catalog("round_feature_id", "context", None, None, None, False, "identifier/metadata column"),
        _catalog("team_smokes_start", "utility", None, None, None, True, None),
        _catalog("team_center_x_10s", "region_position", 0, 10, "point", True, None),
        _catalog("players_mid_control_0_35", "region_position", 0, 35, "cumulative", True, None),
        _catalog("players_a_pressure_15_25", "region_position", 15, 25, "interval", True, None),
        _catalog("players_palace_control_0_15", "region_position", 0, 15, "interval", True, None),
        _catalog("target_site_model_label", "label", None, None, None, False, "target leakage"),
        _catalog("winner_team", "outcome", None, None, None, False, "post-round outcome"),
        _catalog("feature_quality_status", "audit", None, None, None, False, "quality metadata"),
    ]


def _catalog(
    column: str,
    group: str,
    start: int | None,
    end: int | None,
    window_type: str | None,
    usable: bool,
    notes: str | None,
) -> dict[str, object]:
    return {
        "column_name": column,
        "inferred_feature_group": group,
        "window_start": start,
        "window_end": end,
        "window_type": window_type,
        "usable_for_future_model": usable,
        "notes": notes,
    }


def _round_row() -> dict[str, object]:
    return {
        "round_feature_id": "rf_1",
        "team_smokes_start": 5,
        "team_center_x_10s": 12.0,
        "players_mid_control_0_35": 2,
        "players_a_pressure_15_25": 1,
        "players_palace_control_0_15": 1,
        "target_site_model_label": "A",
        "winner_team": "Vitality",
        "feature_quality_status": "ok",
        "mystery_signal": 1.0,
    }


def _write(directory: Path, name: str, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(directory / f"{name}.parquet", index=False)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_feature_contract_cli_dry_run(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "src.features.build_feature_contract", "--config", str(config), "--dry-run"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Feature Contract summary" in result.stdout
    assert not (tmp_path / "data/gold/features/feature_contract").exists()


def test_feature_contract_outputs_and_one_row_per_feature(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, outputs, _ = run_feature_contract(config, force=True)
    contract = frames["feature_contract"]

    assert len(outputs) == len(OUTPUT_NAMES) * 2 + 3
    assert all(path.exists() for path in outputs.values())
    assert contract["feature_name"].is_unique
    assert {"team_smokes_start", "players_mid_control_0_35"} <= set(contract["feature_name"])


def test_temporal_horizon_leakage_identifier_and_label_rules(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_feature_contract(config, dry_run=True)
    contract = frames["feature_contract"].set_index("feature_name")

    mid = contract.loc["players_mid_control_0_35"]
    assert bool(mid["temporal"])
    assert mid["window_start"] == 0
    assert mid["window_end"] == 35
    assert not bool(mid["horizon_15_allowed"])
    assert bool(mid["horizon_35_allowed"])
    assert not bool(contract.loc["target_site_model_label", "modeling_allowed"])
    assert not bool(contract.loc["winner_team", "modeling_allowed"])
    assert not bool(contract.loc["round_feature_id", "modeling_allowed"])


def test_global_map_abstract_and_mirage_specific_are_identified(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_feature_contract(config, dry_run=True)
    contract = frames["feature_contract"].set_index("feature_name")

    assert contract.loc["team_smokes_start", "map_scope"] == "global"
    assert contract.loc["players_mid_control_0_35", "map_scope"] == "map_abstract"
    assert contract.loc["players_palace_control_0_15", "map_scope"] == "map_specific"
    assert bool(contract.loc["players_palace_control_0_15", "mirage_specific"])


def test_readiness_unknowns_yaml_doc_notebook_are_created(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, outputs, _ = run_feature_contract(config, force=True)

    assert not frames["feature_contract_unknowns"].empty
    assert not frames["feature_contract_map_readiness"].empty
    assert not frames["feature_contract_modeling_readiness"].empty
    assert not frames["feature_contract_dashboard_readiness"].empty
    parsed_yaml = yaml.safe_load(outputs["config_yaml"].read_text(encoding="utf-8"))
    assert parsed_yaml["feature_contract_version"] == "v2"
    feature = next(item for item in parsed_yaml["features"] if item["feature_name"] == "team_smokes_start")
    assert feature["generation_scope"] == "global"
    assert feature["coordinate_dependency"] == "none"
    assert feature["cross_map_comparable"] is True
    assert outputs["report"].read_text(encoding="utf-8").startswith("# Feature Contract")
    json.loads(outputs["notebook"].read_text(encoding="utf-8"))


def test_feature_contract_v2_comparability_metadata(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    frames, _, _ = run_feature_contract(config, dry_run=True)
    contract = frames["feature_contract"].set_index("feature_name")

    assert contract.loc["team_smokes_start", "cross_map_comparison_mode"] == "direct"
    assert contract.loc["team_center_x_10s", "coordinate_dependency"] == "raw_map_coordinates"
    assert not bool(contract.loc["team_center_x_10s", "cross_map_comparable"])
    assert contract.loc["players_mid_control_0_35", "cross_map_comparison_mode"] == "semantic"
    assert contract.loc["players_palace_control_0_15", "cross_map_comparison_mode"] == "map_specific_only"


def test_feature_contract_does_not_modify_upstream_datasets(tmp_path: Path) -> None:
    config = _write_fixture(tmp_path)
    upstream = [
        tmp_path / "data/gold/round_features/round_features_mvp.parquet",
        tmp_path / "data/gold/round_features/round_features_t_side_all.parquet",
        tmp_path / "data/gold/round_features/round_features_t_side_planted.parquet",
    ]
    before = {path: _sha256(path) for path in upstream}
    run_feature_contract(config, force=True)
    after = {path: _sha256(path) for path in upstream}

    assert after == before
