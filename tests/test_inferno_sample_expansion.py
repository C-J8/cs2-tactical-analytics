from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.modeling.inferno_sample_expansion import (
    build_demo_dedup_audit,
    build_gap_analysis,
    classify_data_readiness,
    load_expansion_config,
    run_inferno_sample_expansion,
)


def test_stage_8_11_1_passed_allows_execution(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)

    frames, _, summary = run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)

    assert summary["data_readiness"] == "expanded_but_limited"
    assert bool(frames["inferno_sample_expansion_audit"].iloc[0]["stage_8_11_1_passed"])


def test_missing_stage_8_11_1_blocks_execution(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)
    (tmp_path / "data/gold/modeling/inferno_ab_exploratory/modeling_integrity_refactor_regression_audit.parquet").unlink()

    with pytest.raises(FileNotFoundError):
        run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)


def test_failed_stage_8_11_1_blocks_execution(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)
    audit_path = tmp_path / "data/gold/modeling/inferno_ab_exploratory/modeling_integrity_refactor_regression_audit.parquet"
    audit = pd.read_parquet(audit_path)
    audit.loc[0, "status"] = "failed"
    audit.to_parquet(audit_path, index=False)

    with pytest.raises(ValueError, match="Stage 8.11.1 precondition failed"):
        run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)


def test_missing_frozen_experiment_config_blocks_baseline_rerun(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path, frozen_config="configs/modeling/missing.yaml")

    with pytest.raises(FileNotFoundError, match="Frozen experiment config not found"):
        run_inferno_sample_expansion(
            config_path=config,
            expansion_config_path=expansion,
            dry_run=False,
            rerun_frozen_baseline=True,
        )


def test_inventory_scopes_only_inferno_and_vitality(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)

    frames, _, _ = run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)
    inventory = frames["inferno_sample_inventory"]

    assert set(inventory["map_name"]) == {"Inferno"}
    assert set(inventory["target_team"]) == {"Vitality"}
    assert set(inventory["series_id"]) == {"series_1", "series_2", "series_3"}
    assert inventory["dem_file_id"].nunique() == 3


def test_summary_counts_series_opponents_labels_and_no_plants(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)

    frames, _, _ = run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)
    summary = frames["inferno_sample_summary"].iloc[0]
    inventory = frames["inferno_sample_inventory"]

    assert summary["total_demos"] == 3
    assert summary["total_series"] == 3
    assert summary["total_opponents"] == 2
    assert summary["a_count"] == 3
    assert summary["b_count"] == 3
    assert inventory["no_plant_t_rounds"].sum() == 3


def test_gap_analysis_targets_and_class_gaps_are_deterministic() -> None:
    summary = pd.DataFrame(
        [
            {
                "total_demos": 9,
                "total_series": 5,
                "total_opponents": 5,
                "planted_t_rounds": 70,
                "a_count": 45,
                "b_count": 25,
                "minority_share": 25 / 70,
                "modeling_groups": 5,
            }
        ]
    )
    cfg = load_expansion_config(Path("configs/modeling/inferno_sample_expansion.yaml"))

    gap = build_gap_analysis(summary, cfg).set_index("metric")

    assert gap.loc["opponents", "target_met"]
    assert gap.loc["series", "gap_absolute"] == 3
    assert gap.loc["B count", "gap_absolute"] == 5
    assert gap.loc["series", "priority"] == "critical"
    assert gap.loc["planted rounds", "priority"] == "high"


def test_independent_series_gap_is_prioritized_over_raw_round_count(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)

    frames, _, _ = run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)
    priority = frames["inferno_sample_expansion_priority"]

    assert priority.iloc[0]["diagnostic"] == "need_more_independent_series"
    assert "need more rounds" not in "|".join(priority["diagnostic"].astype(str))


def test_dedup_flags_identical_hash_but_not_filename_alone() -> None:
    dem_files = pd.DataFrame(
        [
            {
                "dem_file_id": "demo_1",
                "dem_path": "same_name.dem",
                "original_dem_file_name": "same_name.dem",
                "dem_sha256": "abc",
                "dem_file_size_bytes": 10,
                "target_team": "Vitality",
                "inferred_map_name": "Inferno",
            },
            {
                "dem_file_id": "demo_2",
                "dem_path": "same_name.dem",
                "original_dem_file_name": "same_name.dem",
                "dem_sha256": "abc",
                "dem_file_size_bytes": 10,
                "target_team": "Vitality",
                "inferred_map_name": "Inferno",
            },
            {
                "dem_file_id": "demo_3",
                "dem_path": "same_name.dem",
                "original_dem_file_name": "same_name.dem",
                "dem_sha256": "different",
                "dem_file_size_bytes": 11,
                "target_team": "Vitality",
                "inferred_map_name": "Inferno",
            },
        ]
    )

    audit = build_demo_dedup_audit(dem_files, pd.DataFrame(), target_map="Inferno", target_team="Vitality")

    assert audit.loc[audit["existing_dem_file_id"].eq("demo_1"), "possible_duplicate"].iloc[0]
    assert not audit.loc[audit["existing_dem_file_id"].eq("demo_3"), "possible_duplicate"].iloc[0]


def test_readiness_distinguishes_limited_sample_from_quality_failure(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)
    frames, _, _ = run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)

    assert frames["inferno_sample_summary"].iloc[0]["status"] == "expanded_but_limited"

    failed_scorecard = frames["inferno_modeling_readiness_scorecard"].copy()
    failed_scorecard.loc[failed_scorecard["check_name"].eq("quality gate"), "passed"] = False
    failed = classify_data_readiness(failed_scorecard, frames["inferno_sample_summary"], load_expansion_config(expansion))
    assert failed == "insufficient"


def test_no_new_data_case_writes_gaps_and_next_targets(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path, include_rounds=False)

    frames, _, summary = run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)

    assert summary["stage_completed"]
    assert frames["inferno_sample_inventory"].empty
    assert not frames["inferno_sample_gap_analysis"].empty
    assert not frames["inferno_next_data_targets"].empty


def test_dry_run_does_not_write_stage_outputs(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)

    run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, dry_run=True)

    assert not (tmp_path / "data/gold/modeling/inferno_sample_expansion").exists()


def test_force_writes_all_manifest_outputs(tmp_path: Path) -> None:
    config, expansion = write_stage_812_fixture(tmp_path)

    frames, outputs, _ = run_inferno_sample_expansion(config_path=config, expansion_config_path=expansion, force=True)

    assert set(frames) >= {"inferno_sample_inventory", "inferno_sample_expansion_audit"}
    assert len(outputs) == 40
    assert (tmp_path / "docs/inferno_sample_expansion.md").exists()
    assert (tmp_path / "notebooks/29_inferno_sample_expansion.ipynb").exists()


def test_safety_exclusions_are_kept_out_of_runner() -> None:
    source = Path("src/modeling/inferno_sample_expansion.py").read_text(encoding="utf-8").casefold()

    forbidden = ["import airflow", "gridsearchcv(", "optuna.", "requests.", "hltv.org/"]
    assert not any(token in source for token in forbidden)


def write_stage_812_fixture(
    tmp_path: Path,
    *,
    include_rounds: bool = True,
    frozen_config: str = "configs/modeling/inferno_ab_exploratory.yaml",
) -> tuple[Path, Path]:
    config = tmp_path / "configs/project.yaml"
    expansion = tmp_path / "configs/modeling/inferno_sample_expansion.yaml"
    model_config = tmp_path / "configs/modeling/inferno_ab_exploratory.yaml"
    config.parent.mkdir(parents=True)
    expansion.parent.mkdir(parents=True)
    config.write_text(
        """
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-07-07"
target_maps: [Inferno]
target_teams: [Vitality]
output_formats: [csv, parquet]
parsed_silver_dir: data/silver/parsed_demos
""".strip(),
        encoding="utf-8",
    )
    expansion.write_text(
        f"""
sample_expansion:
  version: v1
  target_map: Inferno
  target_team: Vitality
readiness:
  minimum_demos: 4
  minimum_series: 4
  minimum_planted_t_rounds: 8
  minimum_class_count: 4
  minimum_opponents: 3
  minimum_valid_logo_groups: 4
balance:
  minimum_minority_share: 0.25
quality:
  require_high_confidence_labels: true
  require_feature_quality_gate: true
  require_materialization_gate: true
frozen_experiment:
  config: {frozen_config}
""".strip(),
        encoding="utf-8",
    )
    model_config.write_text("experiment:\n  output_subdir: inferno_ab_exploratory\n", encoding="utf-8")
    gold = tmp_path / "data/gold"
    write_stage_gate(gold)
    write_quality_gates(gold)
    if include_rounds:
        write_round_sources(gold)
        write_baseline_outputs(gold)
        write_bronze_manifests(tmp_path)
    else:
        write_baseline_outputs(gold, empty=True)
    return config, expansion


def write_stage_gate(gold: Path) -> None:
    path = gold / "modeling/inferno_ab_exploratory"
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "status": "passed",
                "modeling_evidence_fail_closed": True,
                "cross_map_lodo_valid": True,
                "within_map_ab_lodo_valid": True,
                "planted_vs_no_plant_lodo_valid": True,
                "cross_map_exposure_valid": True,
                "within_map_exposure_valid": True,
                "refactor_regression_passed": True,
                "core_gold_unchanged": True,
            }
        ]
    ).to_parquet(path / "modeling_integrity_refactor_regression_audit.parquet", index=False)


def write_quality_gates(gold: Path) -> None:
    quality = gold / "validation/map_feature_quality"
    materialization = gold / "validation/feature_materialization_repair"
    quality.mkdir(parents=True, exist_ok=True)
    materialization.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"map_id": "inferno", "target_team": "Vitality", "status": "passed"}]).to_parquet(quality / "map_feature_quality_audit.parquet", index=False)
    pd.DataFrame([{"map_id": "inferno", "target_team": "Vitality", "status": "passed"}]).to_parquet(
        materialization / "feature_materialization_repair_final_audit.parquet", index=False
    )


def write_round_sources(gold: Path) -> None:
    rounds = []
    for series, demo, opponent, labels in [
        ("series_1", "demo_1", "Falcons", ["A", "B", None]),
        ("series_2", "demo_2", "G2", ["A", "B", None]),
        ("series_3", "demo_3", "G2", ["A", "B", None]),
    ]:
        for index, label in enumerate(labels, start=1):
            rounds.append(
                {
                    "round_feature_id": f"{demo}_r{index}",
                    "round_id": f"{demo}_r{index}",
                    "parse_id": f"{demo}_awpy",
                    "dem_file_id": demo,
                    "series_id": series,
                    "target_team": "Vitality",
                    "opponent": opponent,
                    "map_name": "Inferno",
                    "target_team_side": "T",
                    "target_site_model_label": label,
                    "label_confidence": "high" if label else None,
                    "feature_quality_status": "ok" if label else "missing_label",
                }
            )
    rounds.append(
        {
            "round_feature_id": "mirage_r1",
            "round_id": "mirage_r1",
            "parse_id": "mirage_awpy",
            "dem_file_id": "mirage_demo",
            "series_id": "mirage_series",
            "target_team": "Vitality",
            "opponent": "Falcons",
            "map_name": "Mirage",
            "target_team_side": "T",
            "target_site_model_label": "A",
            "label_confidence": "high",
            "feature_quality_status": "ok",
        }
    )
    frame = pd.DataFrame(rounds)
    out = gold / "round_features"
    out.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out / "round_features_mvp.parquet", index=False)
    frame.to_parquet(out / "round_features_t_side_all.parquet", index=False)
    frame[frame["target_site_model_label"].isin(["A", "B"])].to_parquet(out / "round_features_t_side_planted.parquet", index=False)
    frame.iloc[0:0].to_parquet(out / "round_features_ct_side.parquet", index=False)
    state = gold / "round_state"
    state.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(state / "round_state_resolved.parquet", index=False)


def write_baseline_outputs(gold: Path, *, empty: bool = False) -> None:
    out = gold / "modeling/inferno_ab_exploratory"
    out.mkdir(parents=True, exist_ok=True)
    dataset = pd.DataFrame()
    if not empty:
        labels = ["A", "B", "A", "B", "A", "B"]
        dataset = pd.DataFrame(
            [
                {
                    "round_feature_id": f"demo_{(idx // 2) + 1}_r{idx + 1}",
                    "round_id": f"r{idx + 1}",
                    "parse_id": f"demo_{(idx // 2) + 1}_awpy",
                    "series_id": f"series_{(idx // 2) + 1}",
                    "dem_file_id": f"demo_{(idx // 2) + 1}",
                    "target_team": "Vitality",
                    "map_name": "Inferno",
                    "label": label,
                    "model_group_id": f"series_{(idx // 2) + 1}",
                }
                for idx, label in enumerate(labels)
            ]
        )
    dataset.to_parquet(out / "inferno_ab_model_dataset.parquet", index=False)
    pd.DataFrame([{"macro_f1": 0.5, "balanced_accuracy": 0.5, "MCC": 0.0, "f1_A": 0.5, "f1_B": 0.5, "recall_A": 0.5, "recall_B": 0.5, "ROC_AUC": 0.5, "Brier_score": 0.25, "log_loss": 0.7}]).to_parquet(
        out / "inferno_ab_oof_metrics.parquet",
        index=False,
    )
    pd.DataFrame([{"observed_percentile": 0.5}]).to_parquet(out / "inferno_ab_null_summary.parquet", index=False)
    pd.DataFrame([{"metric": "macro_f1", "ci_low": 0.4, "ci_high": 0.6}]).to_parquet(out / "inferno_ab_metric_uncertainty.parquet", index=False)
    pd.DataFrame([{"macro_f1": 0.4}, {"macro_f1": 0.6}]).to_parquet(out / "inferno_ab_fold_metrics.parquet", index=False)
    pd.DataFrame([{"sign_agreement": 1.0}]).to_parquet(out / "inferno_ab_coefficient_stability.parquet", index=False)
    pd.DataFrame([{"exploratory_signal_status": "no_signal"}]).to_parquet(out / "inferno_ab_exploratory_model_audit.parquet", index=False)


def write_bronze_manifests(tmp_path: Path) -> None:
    parse_dir = tmp_path / "data/bronze/parse_manifest"
    dem_dir = tmp_path / "data/bronze/dem_files_manifest"
    parse_dir.mkdir(parents=True, exist_ok=True)
    dem_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"parse_id": f"demo_{idx}_awpy", "dem_file_id": f"demo_{idx}", "series_id": f"series_{idx}", "opponent": opponent, "parse_status": "parsed", "match_date": f"2026-01-0{idx}"}
            for idx, opponent in enumerate(["Falcons", "G2", "G2"], start=1)
        ]
    ).to_parquet(parse_dir / "parse_manifest.parquet", index=False)
    pd.DataFrame(
        [
            {
                "dem_file_id": f"demo_{idx}",
                "dem_path": f"demo_{idx}.dem",
                "dem_sha256": f"hash_{idx}",
                "dem_file_size_bytes": idx,
                "target_team": "Vitality",
                "inferred_map_name": "Inferno",
            }
            for idx in range(1, 4)
        ]
    ).to_parquet(dem_dir / "dem_files_manifest.parquet", index=False)
