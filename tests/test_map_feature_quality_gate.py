from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.validation.map_feature_quality_gate import (
    GateContext,
    build_ab_label_quality,
    build_dataset_reconciliation,
    build_domain_validation,
    build_feature_missingness,
    build_feature_quality_profile,
    build_modeling_sample_readiness,
    build_scoped_frames,
    build_semantic_signal_health,
    build_temporal_feature_consistency,
    capture_core_fingerprints,
    load_quality_config,
    run_map_feature_quality_gate,
    upsert_quality_scope,
    validate_preconditions,
)


def _registry(tmp_path: Path, *, inferno_status: str = "active") -> Path:
    maps = tmp_path / "configs" / "maps"
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / "map_registry.yaml"
    path.write_text(
        f"""
registry_version: v1
maps:
- map_id: mirage
  display_name: Mirage
  game_map_name: de_mirage
  config_path: configs/maps/mirage.yaml
  status: active
- map_id: inferno
  display_name: Inferno
  game_map_name: de_inferno
  config_path: configs/maps/inferno.yaml
  status: {inferno_status}
""".strip(),
        encoding="utf-8",
    )
    return path


def _quality(tmp_path: Path) -> Path:
    path = tmp_path / "configs" / "quality" / "map_feature_quality.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
quality_version: v1
missingness: {warning_share: 0.1, critical_share: 0.5}
degeneracy: {near_constant_share: 0.6, zero_dominance_warning: 0.95, zero_dominance_critical: 1.0, minimum_unique_numeric: 2}
semantic_health: {minimum_nonzero_round_share: 0.02, minimum_demo_coverage: 0.2}
distribution_sanity: {large_zero_share_difference: 0.5, robust_location_shift_threshold: 3.0, range_overlap_warning: 0.1}
modeling_sample: {exploratory_min_total: 3, exploratory_min_class: 1, baseline_min_total: 6, baseline_min_class: 2, robust_min_total: 20, robust_min_class: 5}
review_sample: {max_rows: 10}
""".strip(),
        encoding="utf-8",
    )
    return path


def _project(tmp_path: Path) -> Path:
    path = tmp_path / "configs" / "project.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
project_name: cs2-tactical-analytics
mode: manual
date_start: "2025-10-01"
date_end: "2026-07-07"
target_maps: [Mirage]
target_teams: [Vitality]
output_formats: [csv, parquet]
""".strip(),
        encoding="utf-8",
    )
    return path


def _ctx(tmp_path: Path, *, inferno_status: str = "active") -> GateContext:
    registry = _registry(tmp_path, inferno_status=inferno_status)
    quality = load_quality_config(_quality(tmp_path))
    return GateContext(
        project_root=tmp_path,
        gold_dir=tmp_path / "data" / "gold",
        output_dir=tmp_path / "data" / "gold" / "validation" / "map_feature_quality",
        registry_path=registry,
        map_id="inferno",
        map_name="Inferno",
        target_team="Vitality",
        quality=quality,
    )


def _contract() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"feature_name": "players_alive_0_15", "feature_family": "region_position", "feature_status": "frozen", "map_scope": "global", "region_dependency": False, "cross_map_comparable": True, "cross_map_comparison_mode": "direct", "temporal": True, "window_start": 0, "window_end": 15, "window_type": "both"},
            {"feature_name": "smokes_used_0_15", "feature_family": "utility", "feature_status": "frozen", "map_scope": "global", "region_dependency": False, "cross_map_comparable": True, "cross_map_comparison_mode": "direct", "temporal": True, "window_start": 0, "window_end": 15, "window_type": "both"},
            {"feature_name": "smokes_used_0_25", "feature_family": "utility", "feature_status": "frozen", "map_scope": "global", "region_dependency": False, "cross_map_comparable": True, "cross_map_comparison_mode": "direct", "temporal": True, "window_start": 0, "window_end": 25, "window_type": "cumulative"},
            {"feature_name": "players_mid_control_0_15", "feature_family": "region_position", "feature_status": "frozen", "map_scope": "map_abstract", "region_dependency": True, "region_semantic": "mid_control", "cross_map_comparable": True, "cross_map_comparison_mode": "semantic", "temporal": True, "window_start": 0, "window_end": 15, "window_type": "both"},
            {"feature_name": "first_smoke_time", "feature_family": "utility", "feature_status": "frozen", "map_scope": "global", "region_dependency": False, "cross_map_comparable": True, "cross_map_comparison_mode": "direct", "temporal": False},
            {"feature_name": "raw_x", "feature_family": "region_position", "feature_status": "frozen", "map_scope": "global", "region_dependency": False, "cross_map_comparable": True, "cross_map_comparison_mode": "normalized_required", "temporal": False},
        ]
    )


def _round_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"round_feature_id": "inf_1", "round_id": "r1", "parse_id": "d1", "dem_file_id": "dem1", "target_team": "Vitality", "map_name": "Inferno", "round_num": 1, "players_alive_0_15": 5, "smokes_used_0_15": 1, "smokes_used_0_25": 2, "players_mid_control_0_15": 1, "first_smoke_time": None, "raw_x": 100},
            {"round_feature_id": "inf_2", "round_id": "r2", "parse_id": "d1", "dem_file_id": "dem1", "target_team": "Vitality", "map_name": "Inferno", "round_num": 2, "players_alive_0_15": 4, "smokes_used_0_15": 0, "smokes_used_0_25": 1, "players_mid_control_0_15": 0, "first_smoke_time": None, "raw_x": 110},
            {"round_feature_id": "inf_3", "round_id": "r3", "parse_id": "d2", "dem_file_id": "dem2", "target_team": "Vitality", "map_name": "Inferno", "round_num": 3, "players_alive_0_15": 3, "smokes_used_0_15": 1, "smokes_used_0_25": 1, "players_mid_control_0_15": 1, "first_smoke_time": None, "raw_x": 120},
            {"round_feature_id": "mir_1", "round_id": "mr1", "parse_id": "md1", "dem_file_id": "mdem", "target_team": "Vitality", "map_name": "Mirage", "round_num": 1, "players_alive_0_15": 5, "smokes_used_0_15": 3, "smokes_used_0_25": 4, "players_mid_control_0_15": 1, "first_smoke_time": 5, "raw_x": 200},
        ]
    )


def _round_state() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"round_feature_id": "inf_1", "round_id": "r1", "parse_id": "d1", "target_team": "Vitality", "map_name": "Inferno", "round_num": 1, "target_team_side": "T", "bomb_planted": True, "target_team_planted": True, "target_site_model_label": "A", "label_confidence": "high", "bombsite": "A"},
            {"round_feature_id": "inf_2", "round_id": "r2", "parse_id": "d1", "target_team": "Vitality", "map_name": "Inferno", "round_num": 2, "target_team_side": "T", "bomb_planted": True, "target_team_planted": True, "target_site_model_label": "B", "label_confidence": "high", "bombsite": "B"},
            {"round_feature_id": "inf_3", "round_id": "r3", "parse_id": "d2", "target_team": "Vitality", "map_name": "Inferno", "round_num": 3, "target_team_side": "CT", "bomb_planted": False, "target_team_planted": False, "target_site_model_label": None, "label_confidence": None, "bombsite": None},
        ]
    )


def _scoped() -> dict[str, pd.DataFrame]:
    rf = _round_features().iloc[:3].copy()
    state = _round_state()
    return {
        "round_features_mvp": rf,
        "round_state_resolved": state,
        "round_features_t_side_all": rf.iloc[:2].copy(),
        "round_features_t_side_planted": rf.iloc[:2].assign(target_site_model_label=["A", "B"]).copy(),
        "round_features_ct_side": rf.iloc[2:].copy(),
        "region_presence_by_round": pd.DataFrame([{"round_feature_id": "inf_1", "window_type": "both", "window_start": 0, "window_end": 15, "region_name": "middle", "region_group": "mid_control", "players_mid_control_0_15": 1}]),
        "round_region_timeline": pd.DataFrame([{"round_feature_id": "inf_1", "window_type": "both", "window_start": 0, "window_end": 15, "region_name": "middle", "region_group": "mid_control"}]),
        "death_context_by_round": pd.DataFrame([{"death_context_id": "dc1", "round_feature_id": "inf_1"}]),
        "bomb_carrier_timeline": pd.DataFrame([{"round_feature_id": "inf_1", "window_type": "both", "window_start": 0, "window_end": 15}]),
        "round_outcome_context": rf[["round_feature_id"]].copy(),
        "utility_events": pd.DataFrame([{"utility_event_id": "u1", "round_feature_id": "inf_1"}]),
    }


def test_inactive_map_registry_blocks_precondition(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, inferno_status="onboarding")
    frames = {"round_features_mvp": _round_features(), "round_state_resolved": _round_state(), "round_features_t_side_all": _round_features().iloc[:2], "round_features_t_side_planted": _round_features().iloc[:2], "round_features_ct_side": _round_features().iloc[2:3]}

    preconditions = validate_preconditions(frames, ctx)

    assert preconditions.loc[preconditions["check_id"].eq("map_registry_active"), "status"].iloc[0] == "failed"


def test_build_scoped_frames_excludes_other_map_rows(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    frames = {"round_features_mvp": _round_features(), "round_state_resolved": _round_state()}

    scoped = build_scoped_frames(frames, ctx)

    assert set(scoped["round_features_mvp"]["map_name"]) == {"Inferno"}
    assert set(scoped["round_features_mvp"]["round_feature_id"]) == {"inf_1", "inf_2", "inf_3"}


def test_dataset_reconciliation_detects_missing_round_state_row(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    scoped = _scoped()
    scoped["round_state_resolved"] = scoped["round_state_resolved"].iloc[:2].copy()

    reconciliation = build_dataset_reconciliation(scoped, ctx)

    state_row = reconciliation[reconciliation["dataset_name"].eq("round_state_resolved")].iloc[0]
    assert state_row["status"] == "failed"


def test_feature_profile_detects_all_null_constant_all_zero_and_near_constant(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    frame = _round_features().iloc[:3].copy()
    frame["all_zero_feature"] = 0
    frame["constant_feature"] = 7
    frame["near_constant_feature"] = [1, 1, 2]
    contract = pd.concat(
        [
            _contract(),
            pd.DataFrame(
                [
                    {"feature_name": "all_zero_feature", "feature_family": "utility"},
                    {"feature_name": "constant_feature", "feature_family": "utility"},
                    {"feature_name": "near_constant_feature", "feature_family": "utility"},
                ]
            ),
        ],
        ignore_index=True,
    )

    profile = build_feature_quality_profile(frame, contract, ctx)

    assert profile.loc[profile["feature_name"].eq("first_smoke_time"), "all_null"].iloc[0]
    assert profile.loc[profile["feature_name"].eq("all_zero_feature"), "all_zero"].iloc[0]
    assert profile.loc[profile["feature_name"].eq("constant_feature"), "constant"].iloc[0]
    assert profile.loc[profile["feature_name"].eq("near_constant_feature"), "near_constant"].iloc[0]


def test_expected_structural_missingness_does_not_block(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    frame = _round_features().iloc[:3].copy()
    contract = _contract()
    profile = build_feature_quality_profile(frame, contract, ctx)

    missing = build_feature_missingness(profile, frame, _round_state(), contract, ctx)

    row = missing[missing["feature_name"].eq("first_smoke_time")].iloc[0]
    assert row["expected_missingness"]
    assert not row["blocking"]


def test_domain_validation_detects_invalid_players_and_utility(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    frame = _round_features().iloc[:3].copy()
    frame.loc[0, "players_alive_0_15"] = 6
    frame.loc[1, "smokes_used_0_15"] = -1

    domains = build_domain_validation(frame, _contract(), ctx)

    assert domains.loc[domains["feature_name"].eq("players_alive_0_15"), "status"].iloc[0] == "failed"
    assert domains.loc[domains["feature_name"].eq("smokes_used_0_15"), "status"].iloc[0] == "failed"


def test_temporal_cumulative_decrease_is_detected(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    frame = _round_features().iloc[:3].copy()
    frame.loc[0, "smokes_used_0_25"] = 0

    temporal = build_temporal_feature_consistency(frame, _contract(), ctx)

    assert int(temporal["monotonicity_violations"].sum()) == 1


def test_semantic_required_signal_passes_when_nonzero(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)

    semantic = build_semantic_signal_health(_round_features().iloc[:3], _contract(), ctx)

    assert semantic.loc[semantic["semantic_id"].eq("mid_control"), "status"].iloc[0] == "ok"


def test_label_quality_requires_two_classes_and_detects_invalid_label(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    scoped = _scoped()
    scoped["round_features_t_side_planted"] = scoped["round_features_t_side_planted"].assign(target_site_model_label=["A", "C"])

    labels = build_ab_label_quality(scoped, ctx)

    assert labels.iloc[0]["label_status"] == "failed"


def test_sample_readiness_uses_config_thresholds(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    label_quality = build_ab_label_quality(_scoped(), ctx)

    readiness = build_modeling_sample_readiness(label_quality, ctx)

    assert readiness.iloc[0]["sample_status"] == "insufficient"
    assert not readiness.iloc[0]["ready_for_baseline_modeling"]


def test_quality_scope_upsert_is_idempotent_and_preserves_other_map(tmp_path: Path) -> None:
    existing = pd.DataFrame([{"map_id": "mirage", "target_team": "Vitality", "value": 1}])
    incoming = pd.DataFrame([{"map_id": "inferno", "target_team": "Vitality", "value": 2}])

    once = upsert_quality_scope(existing, incoming, map_id="inferno", target_team="Vitality")
    twice = upsert_quality_scope(once, incoming, map_id="inferno", target_team="Vitality")

    assert len(twice) == 2
    assert set(twice["map_id"]) == {"mirage", "inferno"}


def test_read_only_fingerprint_unchanged_for_same_frames(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    frames = {"round_features_mvp": _round_features(), "round_state_resolved": _round_state()}

    before = capture_core_fingerprints(frames, ctx)
    after = capture_core_fingerprints(frames, ctx)

    assert before["content_hash"].tolist() == after["content_hash"].tolist()


def test_full_gate_writes_outputs_and_does_not_duplicate_scope(tmp_path: Path) -> None:
    config = _project(tmp_path)
    registry = _registry(tmp_path)
    quality = _quality(tmp_path)
    gold = tmp_path / "data" / "gold"
    (gold / "round_features").mkdir(parents=True)
    (gold / "round_state").mkdir(parents=True)
    (gold / "region_presence").mkdir(parents=True)
    (gold / "round_progression").mkdir(parents=True)
    (gold / "utility_events").mkdir(parents=True)
    (gold / "features" / "feature_contract").mkdir(parents=True)
    (gold / "validation" / "multi_map_gold").mkdir(parents=True)
    (gold / "validation" / "mirage_regression_gate").mkdir(parents=True)
    _round_features().to_parquet(gold / "round_features" / "round_features_mvp.parquet", index=False)
    _round_state().to_parquet(gold / "round_state" / "round_state_resolved.parquet", index=False)
    _round_features().iloc[:2].to_parquet(gold / "round_features" / "round_features_t_side_all.parquet", index=False)
    _round_features().iloc[:2].assign(target_site_model_label=["A", "B"]).to_parquet(gold / "round_features" / "round_features_t_side_planted.parquet", index=False)
    _round_features().iloc[2:3].to_parquet(gold / "round_features" / "round_features_ct_side.parquet", index=False)
    pd.DataFrame([{"round_feature_id": "inf_1", "window_type": "both", "window_start": 0, "window_end": 15, "region_name": "middle", "region_group": "mid_control", "players_mid_control_0_15": 1}]).to_parquet(gold / "region_presence" / "region_presence_by_round.parquet", index=False)
    pd.DataFrame([{"round_feature_id": "inf_1", "window_type": "both", "window_start": 0, "window_end": 15, "region_name": "middle", "region_group": "mid_control"}]).to_parquet(gold / "round_progression" / "round_region_timeline.parquet", index=False)
    pd.DataFrame([{"death_context_id": "dc1", "round_feature_id": "inf_1"}]).to_parquet(gold / "round_progression" / "death_context_by_round.parquet", index=False)
    pd.DataFrame([{"round_feature_id": "inf_1", "window_type": "both", "window_start": 0, "window_end": 15}]).to_parquet(gold / "round_progression" / "bomb_carrier_timeline.parquet", index=False)
    _round_features()[["round_feature_id"]].iloc[:3].to_parquet(gold / "round_progression" / "round_outcome_context.parquet", index=False)
    pd.DataFrame([{"utility_event_id": "u1", "round_feature_id": "inf_1"}]).to_parquet(gold / "utility_events" / "utility_events.parquet", index=False)
    _contract().to_parquet(gold / "features" / "feature_contract" / "feature_contract.parquet", index=False)
    pd.DataFrame([{"canonical_target_map_id": "inferno", "target_team": "Vitality", "ready_for_inferno_feature_quality_gate": True, "overall_status": "passed"}]).to_parquet(gold / "validation" / "multi_map_gold" / "multi_map_gold_audit.parquet", index=False)
    pd.DataFrame([{"overall_status": "passed"}]).to_parquet(gold / "validation" / "mirage_regression_gate" / "mirage_regression_summary.parquet", index=False)

    run_map_feature_quality_gate(config, target_map="Inferno", target_team="Vitality", force=True, quality_config=quality, map_registry_path=registry)
    run_map_feature_quality_gate(config, target_map="Inferno", target_team="Vitality", force=True, quality_config=quality, map_registry_path=registry)

    audit = pd.read_parquet(gold / "validation" / "map_feature_quality" / "map_feature_quality_audit.parquet")
    assert len(audit[audit["map_id"].eq("inferno")]) == 1
