from __future__ import annotations

import pandas as pd

from src.analysis.tactical_finding_hardening import (
    apply_hardened_quality,
    apply_temporal_exposure,
    build_finding_demo_sensitivity,
    build_direction_consistency,
    build_hardened_cross_map_site_patterns,
    build_raw_finding_evidence,
    build_tactical_finding_groups,
    classify_interpretation,
    evaluate_finding_effect,
    taxonomy_reason,
    temporal_exposure_sensitivity,
)


SETTINGS = {
    "temporal": {"late_window_start_seconds": 75, "minimum_exposure_share": 0.70},
    "time_bands": {"early_end": 35, "mid_end": 75},
    "evidence": {"high_min_demo_agreement": 0.75, "moderate_min_demo_agreement": 0.60, "minimum_effect_strength": 0.147},
    "site_pattern": {"zero_effect_epsilon": 1e-9},
}


def test_map_order_preserves_reference_and_comparison_values() -> None:
    inputs = stage_inputs(
        candidates=[
            candidate("mm_eda_0001", "first_smoke_time", "t_side_all", "direct_feature"),
        ],
        direct=[
            comparison("first_smoke_time", "t_side_all", inferno_median=30.0, mirage_median=10.0, effect=-0.9),
        ],
    )

    raw = build_raw_finding_evidence(inputs, [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")], SETTINGS)
    row = raw.iloc[0]

    assert row["reference_map_id"] == "mirage"
    assert row["comparison_map_id"] == "inferno"
    assert row["reference_value"] == 10.0
    assert row["comparison_value"] == 30.0
    assert row["direction"] == "higher"
    assert "later on Inferno than Mirage" in row["finding_text"]
    assert "second map" not in row["finding_text"]


def test_reversed_map_order_keeps_math_consistent() -> None:
    inputs = stage_inputs(
        candidates=[
            candidate("mm_eda_0001", "first_smoke_time", "t_side_all", "direct_feature"),
        ],
        direct=[
            comparison("first_smoke_time", "t_side_all", inferno_median=30.0, mirage_median=10.0, effect=-0.9),
        ],
    )

    raw = build_raw_finding_evidence(inputs, [DummyMap("inferno", "Inferno"), DummyMap("mirage", "Mirage")], SETTINGS)
    row = raw.iloc[0]

    assert row["reference_value"] == 30.0
    assert row["comparison_value"] == 10.0
    assert row["direction"] == "lower"
    assert "earlier on Mirage than Inferno" in row["finding_text"]


def test_late_window_exposure_flags_low_exposure_and_blocks_high_quality() -> None:
    inputs = stage_inputs(
        candidates=[
            candidate("mm_eda_0002", "smokes_used_95_105", "t_side_all", "direct_feature"),
        ],
        direct=[
            comparison("smokes_used_95_105", "t_side_all", inferno_median=2.0, mirage_median=1.0, effect=0.8),
        ],
    )
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]
    raw = build_raw_finding_evidence(inputs, maps, SETTINGS)
    temporal = pd.DataFrame(
        [
            {"feature_name": "smokes_used_95_105", "map_id": "mirage", "exposure_share": 0.40},
            {"feature_name": "smokes_used_95_105", "map_id": "inferno", "exposure_share": 0.90},
        ]
    )

    exposed = apply_temporal_exposure(raw, temporal, maps, SETTINGS)
    hardened = apply_hardened_quality(exposed, SETTINGS)

    assert bool(hardened.loc[0, "late_window_exposure_flag"]) is True
    assert hardened.loc[0, "evidence_quality_hardened"] != "high_descriptive"
    assert bool(hardened.loc[0, "eligible_after_hardening"]) is False


def test_late_point_without_exposure_profile_is_blocked() -> None:
    inputs = stage_inputs(
        candidates=[
            candidate("mm_eda_0007", "team_spread_115s", "t_side_all", "direct_feature"),
        ],
        direct=[
            comparison("team_spread_115s", "t_side_all", inferno_median=2.0, mirage_median=1.0, effect=0.8),
        ],
    )
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]
    raw = build_raw_finding_evidence(inputs, maps, SETTINGS)
    exposed = apply_temporal_exposure(raw, pd.DataFrame(), maps, SETTINGS)
    hardened = apply_hardened_quality(exposed, SETTINGS)

    assert bool(hardened.loc[0, "late_window_exposure_flag"]) is True
    assert bool(hardened.loc[0, "eligible_after_hardening"]) is False


def test_fully_exposed_temporal_effect_is_calculated_when_possible() -> None:
    inputs = stage_inputs(
        candidates=[candidate("mm_eda_0010", "smokes_used_75_85", "t_side_all", "direct_feature")],
        direct=[comparison("smokes_used_75_85", "t_side_all", inferno_median=3.0, mirage_median=1.0, effect=0.8)],
    )
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]
    raw = build_raw_finding_evidence(inputs, maps, SETTINGS)
    temporal = pd.DataFrame(
        [
            {"feature_name": "smokes_used_75_85", "map_id": "mirage", "exposure_share": 1.0},
            {"feature_name": "smokes_used_75_85", "map_id": "inferno", "exposure_share": 1.0},
        ]
    )
    rounds = pd.DataFrame(
        [
            {"map_id": "mirage", "parse_id": f"m{i}", "smokes_used_75_85": i, "round_duration_seconds": 90}
            for i in range(1, 5)
        ]
        + [
            {"map_id": "inferno", "parse_id": f"i{i}", "smokes_used_75_85": i + 2, "round_duration_seconds": 90}
            for i in range(1, 5)
        ]
    )

    exposed = apply_temporal_exposure(raw, temporal, maps, SETTINGS, rounds=rounds)

    assert bool(exposed.loc[0, "fully_exposed_analysis_available"]) is True
    assert exposed.loc[0, "exposure_sensitivity_status"] == "stable"
    assert exposed.loc[0, "fully_exposed_effect"] == 2.0


def test_fully_exposed_temporal_reversal_is_detected() -> None:
    settings = {**SETTINGS, "temporal": {"late_window_start_seconds": 75, "minimum_exposure_share": 0.40}}
    inputs = stage_inputs(
        candidates=[candidate("mm_eda_0011", "smokes_used_75_85", "t_side_all", "direct_feature")],
        direct=[comparison("smokes_used_75_85", "t_side_all", inferno_median=3.0, mirage_median=1.0, effect=0.8)],
    )
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]
    raw = build_raw_finding_evidence(inputs, maps, SETTINGS)
    temporal = pd.DataFrame(
        [
            {"feature_name": "smokes_used_75_85", "map_id": "mirage", "exposure_share": 0.50},
            {"feature_name": "smokes_used_75_85", "map_id": "inferno", "exposure_share": 0.50},
        ]
    )
    rounds = pd.DataFrame(
        [
            {"map_id": "mirage", "parse_id": f"m{i}", "smokes_used_75_85": 10, "round_duration_seconds": 90}
            for i in range(3)
        ]
        + [
            {"map_id": "inferno", "parse_id": f"i{i}", "smokes_used_75_85": 0, "round_duration_seconds": 90}
            for i in range(3)
        ]
        + [
            {"map_id": "mirage", "parse_id": f"ms{i}", "smokes_used_75_85": 0, "round_duration_seconds": 70}
            for i in range(4)
        ]
        + [
            {"map_id": "inferno", "parse_id": f"is{i}", "smokes_used_75_85": 20, "round_duration_seconds": 70}
            for i in range(4)
        ]
    )

    exposed = apply_temporal_exposure(raw, temporal, maps, settings, rounds=rounds)

    assert exposed.loc[0, "exposure_sensitivity_status"] == "reversed"
    assert bool(exposed.loc[0, "same_direction_after_exposure_filter"]) is False


def test_real_leave_one_demo_out_removes_each_demo_and_counts_flips() -> None:
    finding = pd.DataFrame(
        [
            {
                **candidate("mm_eda_0012", "smokes_used_0_35", "t_side_all", "direct_feature"),
                "direction": "higher",
                "comparison_type": "cross_map",
                "finding_concept_id": "utility.smokes.early",
                "eligible_before_hardening": True,
            }
        ]
    )
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]
    rounds = pd.DataFrame(
        [
            {"map_id": "mirage", "parse_id": "m1", "smokes_used_0_35": 1},
            {"map_id": "mirage", "parse_id": "m2", "smokes_used_0_35": 1},
            {"map_id": "inferno", "parse_id": "i1", "smokes_used_0_35": 4},
            {"map_id": "inferno", "parse_id": "i2", "smokes_used_0_35": 0},
        ]
    )

    sensitivity = build_finding_demo_sensitivity(finding, rounds, maps).iloc[0]

    assert sensitivity["sensitivity_method"] == "leave_one_demo_out"
    assert int(sensitivity["demos_evaluated"]) == 4
    assert int(sensitivity["leave_one_demo_out_checks"]) == 4
    assert int(sensitivity["direction_flips"]) >= 1


def test_inferno_a_vs_b_dispatch_uses_inferno_only() -> None:
    finding = pd.Series({"feature_name": "smokes_used_0_35", "comparison_type": "inferno_A_vs_B", "cohort": "t_side_planted"})
    rounds = pd.DataFrame(
        [
            {"map_id": "inferno", "target_site_model_label": "A", "label_confidence": "high", "smokes_used_0_35": 1},
            {"map_id": "inferno", "target_site_model_label": "B", "label_confidence": "high", "smokes_used_0_35": 4},
            {"map_id": "mirage", "target_site_model_label": "B", "label_confidence": "high", "smokes_used_0_35": 99},
        ]
    )

    effect = evaluate_finding_effect(rounds, finding, [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")])

    assert effect["effect"] == 3.0
    assert effect["effect_method"] == "within_map_b_minus_a_median"


def test_planted_vs_no_plant_dispatch_uses_same_map_only() -> None:
    finding = pd.Series({"feature_name": "flashes_used_0_35", "comparison_type": "mirage_planted_vs_no_plant", "cohort": "planted_vs_no_plant"})
    rounds = pd.DataFrame(
        [
            {"map_id": "mirage", "target_site_model_label": "A", "label_confidence": "high", "flashes_used_0_35": 4},
            {"map_id": "mirage", "target_site_model_label": "unknown", "label_confidence": "", "flashes_used_0_35": 1},
            {"map_id": "inferno", "target_site_model_label": "unknown", "label_confidence": "", "flashes_used_0_35": 99},
        ]
    )

    effect = evaluate_finding_effect(rounds, finding, [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")])

    assert effect["effect"] == -3.0
    assert effect["effect_method"] == "within_map_no_plant_minus_planted_median"


def test_unknown_comparison_type_fails_closed() -> None:
    finding = pd.Series({"feature_name": "smokes_used_0_35", "comparison_type": "mystery"})
    rounds = pd.DataFrame([{"map_id": "inferno", "smokes_used_0_35": 1}])

    effect = evaluate_finding_effect(rounds, finding, [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")])

    assert effect["status"] == "unsupported_comparison_type"


def test_within_map_lodo_recomputes_b_minus_a_after_removal() -> None:
    finding = pd.DataFrame(
        [
            {
                **candidate("mm_eda_0013", "smokes_used_0_35", "t_side_planted", "direct_feature"),
                "direction": "higher",
                "comparison_type": "inferno_A_vs_B",
                "finding_concept_id": "inferno.site.smokes",
                "eligible_before_hardening": True,
            }
        ]
    )
    rounds = pd.DataFrame(
        [
            {"map_id": "inferno", "parse_id": "a1", "target_site_model_label": "A", "label_confidence": "high", "smokes_used_0_35": 1},
            {"map_id": "inferno", "parse_id": "a2", "target_site_model_label": "A", "label_confidence": "high", "smokes_used_0_35": 1},
            {"map_id": "inferno", "parse_id": "b1", "target_site_model_label": "B", "label_confidence": "high", "smokes_used_0_35": 4},
            {"map_id": "inferno", "parse_id": "b2", "target_site_model_label": "B", "label_confidence": "high", "smokes_used_0_35": 0},
            {"map_id": "mirage", "parse_id": "m1", "target_site_model_label": "B", "label_confidence": "high", "smokes_used_0_35": 99},
        ]
    )

    sensitivity = build_finding_demo_sensitivity(finding, rounds, [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]).iloc[0]

    assert sensitivity["effect_method"] == "within_map_b_minus_a_median"
    assert int(sensitivity["demos_evaluated"]) == 4


def test_fully_exposed_a_vs_b_uses_dispatcher() -> None:
    finding = pd.Series({"feature_name": "smokes_used_75_85", "comparison_type": "inferno_A_vs_B", "cohort": "t_side_planted", "window_end": 85})
    rounds = pd.DataFrame(
        [
            {"map_id": "inferno", "target_site_model_label": "A", "label_confidence": "high", "smokes_used_75_85": 1, "round_duration_seconds": 90},
            {"map_id": "inferno", "target_site_model_label": "A", "label_confidence": "high", "smokes_used_75_85": 1, "round_duration_seconds": 90},
            {"map_id": "inferno", "target_site_model_label": "A", "label_confidence": "high", "smokes_used_75_85": 1, "round_duration_seconds": 90},
            {"map_id": "inferno", "target_site_model_label": "B", "label_confidence": "high", "smokes_used_75_85": 3, "round_duration_seconds": 90},
            {"map_id": "inferno", "target_site_model_label": "B", "label_confidence": "high", "smokes_used_75_85": 3, "round_duration_seconds": 90},
            {"map_id": "inferno", "target_site_model_label": "B", "label_confidence": "high", "smokes_used_75_85": 3, "round_duration_seconds": 90},
        ]
    )

    sensitivity = temporal_exposure_sensitivity(finding, rounds, [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")], 0.70)

    assert sensitivity["fully_exposed_effect"] == 2.0
    assert sensitivity["fully_exposed_rows_reference"] == 3
    assert sensitivity["fully_exposed_rows_comparison"] == 3


def test_early_windows_same_direction_consolidate_to_one_concept() -> None:
    inputs = stage_inputs(
        candidates=[
            candidate("mm_eda_0003", "smokes_used_0_15", "t_side_all", "direct_feature"),
            candidate("mm_eda_0004", "smokes_used_0_25", "t_side_planted", "direct_feature"),
        ],
        direct=[
            comparison("smokes_used_0_15", "t_side_all", inferno_median=3.0, mirage_median=1.0, effect=0.8),
            comparison("smokes_used_0_25", "t_side_planted", inferno_median=4.0, mirage_median=2.0, effect=0.7),
        ],
    )
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]
    raw = build_raw_finding_evidence(inputs, maps, SETTINGS)
    raw = apply_temporal_exposure(raw, pd.DataFrame(), maps, SETTINGS)
    raw = apply_hardened_quality(raw, SETTINGS)
    consistency = build_direction_consistency(raw, SETTINGS)
    groups, support = build_tactical_finding_groups(raw, consistency, SETTINGS)

    assert groups["finding_concept_id"].nunique() == 1
    assert int(groups.iloc[0]["raw_candidate_count"]) == 2
    assert set(support["support_role"]) <= {"representative", "supporting"}


def test_cross_map_site_patterns_require_nonflat_same_direction() -> None:
    cross_site = pd.DataFrame(
        [
            {"feature_name": "smokes_used_0_15", "mirage_a_b_effect": 0.0, "inferno_a_b_effect": 0.0, "effect_strength_mirage": "negligible", "effect_strength_inferno": "negligible", "demo_support": 1.0},
            {"feature_name": "flashes_used_0_15", "mirage_a_b_effect": 2.0, "inferno_a_b_effect": 3.0, "effect_strength_mirage": "large", "effect_strength_inferno": "large", "demo_support": 0.8},
        ]
    )

    hardened = build_hardened_cross_map_site_patterns(cross_site, SETTINGS).set_index("feature_name")

    assert bool(hardened.loc["smokes_used_0_15", "same_nonflat_direction"]) is False
    assert hardened.loc["smokes_used_0_15", "status"] == "flat_on_one_or_more_maps"
    assert bool(hardened.loc["flashes_used_0_15", "same_nonflat_direction"]) is True


def test_taxonomy_prefers_normalized_required_before_not_cross_map_comparable() -> None:
    row = pd.Series(
        {
            "feature_name": "team_center_x_10s",
            "coordinate_dependency": "raw_coordinate",
            "cross_map_comparison_mode": "unknown",
            "exclusion_reason": "not_cross_map_comparable",
            "structural_review_flag": False,
        }
    )

    assert taxonomy_reason(row) == "normalized_required"


def test_late_players_alive_is_outcome_adjacent() -> None:
    row = pd.Series({"feature_name": "players_alive_115s", "window_end": 115, "category": "plant_progression"})

    assert classify_interpretation(row) == "outcome_adjacent"


def candidate(finding_id: str, feature: str, cohort: str, category: str) -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "category": category,
        "cohort": cohort,
        "feature_name": feature,
        "semantic_id": None,
        "comparison": "cross_map",
        "direction": "lower",
        "effect_size": 0.8,
        "effect_strength": "large",
        "bootstrap_ci_low": 0.1,
        "bootstrap_ci_high": 0.2,
        "demo_direction_agreement": 1.0,
        "mirage_n": 10,
        "inferno_n": 10,
        "mirage_demos": 3,
        "inferno_demos": 3,
        "structural_review_flag": False,
        "late_window_exposure_flag": False,
        "opponent_dependency_flag": False,
        "evidence_quality": "high_descriptive",
        "eligible_for_ranking": True,
        "exclusion_reason": None,
        "finding_text_draft": "old text on the second map",
    }


def comparison(feature: str, cohort: str, *, inferno_median: float, mirage_median: float, effect: float) -> dict[str, object]:
    return {
        "feature_name": feature,
        "feature_family": "utility",
        "cohort": cohort,
        "inferno_n": 10,
        "mirage_n": 10,
        "inferno_demos": 3,
        "mirage_demos": 3,
        "inferno_mean": inferno_median,
        "mirage_mean": mirage_median,
        "inferno_median": inferno_median,
        "mirage_median": mirage_median,
        "cliffs_delta": effect,
        "demo_direction_agreement": 1.0,
        "effect_strength": "large",
        "status": "ok",
    }


def stage_inputs(candidates: list[dict[str, object]], direct: list[dict[str, object]]) -> dict[str, pd.DataFrame]:
    return {
        "multi_map_finding_candidates": pd.DataFrame(candidates),
        "direct_feature_comparison": pd.DataFrame(direct),
        "semantic_feature_comparison": pd.DataFrame(),
        "within_map_site_comparison": pd.DataFrame(),
        "cross_map_site_pattern_comparison": pd.DataFrame(),
        "plant_vs_no_plant_comparison": pd.DataFrame(),
    }


class DummyMap:
    def __init__(self, map_id: str, map_name: str) -> None:
        self.map_id = map_id
        self.map_name = map_name
