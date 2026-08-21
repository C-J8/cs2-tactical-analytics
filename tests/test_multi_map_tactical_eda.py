from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.analysis.multi_map_tactical_eda import (
    build_cohorts,
    build_feature_eligibility,
    build_read_only_audit,
    capture_core_fingerprints,
    classify_t_round_outcome,
    cliffs_delta,
    cluster_bootstrap_difference,
    resolve_map_requests,
)


def test_map_aliases_canonicalize(tmp_path: Path) -> None:
    registry = write_registry(tmp_path)

    maps = resolve_map_requests(["de_mirage", "Inferno"], registry_path=registry)

    assert [item.map_id for item in maps] == ["mirage", "inferno"]


def test_t_side_cohorts_preserve_no_plant_rounds() -> None:
    rounds = pd.DataFrame(
        [
            {"target_site_model_label": "A", "label_confidence": "high", "target_team_planted": True},
            {"target_site_model_label": None, "label_confidence": None, "target_team_planted": False},
        ]
    )
    rounds["t_round_outcome"] = rounds.apply(classify_t_round_outcome, axis=1)

    cohorts = build_cohorts(rounds)

    assert int(cohorts["t_side_all"].sum()) == 2
    assert int(cohorts["t_side_planted"].sum()) == 1
    assert int(cohorts["t_side_no_valid_target_plant"].sum()) == 1


def test_feature_eligibility_excludes_unresolved_endpoint_and_raw_coordinates() -> None:
    rounds = pd.DataFrame(
        {
            "map_id": ["mirage", "inferno"],
            "smokes_to_mid_control_0_15": [0, 0],
            "team_center_x_10s": [1.0, 2.0],
            "flashes_used_0_15": [1, 2],
        }
    )
    inputs = {
        "feature_contract": pd.DataFrame(
            [
                {"feature_name": "smokes_to_mid_control_0_15", "feature_family": "utility_usage", "cross_map_comparable": True, "cross_map_comparison_mode": "semantic", "coordinate_dependency": "none", "region_semantic": "mid_control"},
                {"feature_name": "team_center_x_10s", "feature_family": "region_position", "cross_map_comparable": True, "cross_map_comparison_mode": "normalized_required", "coordinate_dependency": "raw_coordinate", "region_semantic": None},
                {"feature_name": "flashes_used_0_15", "feature_family": "utility_usage", "cross_map_comparable": True, "cross_map_comparison_mode": "direct", "coordinate_dependency": "none", "region_semantic": None},
            ]
        ),
        "cross_map_sanity": pd.DataFrame(columns=["feature_name", "structural_mismatch"]),
        "capabilities": pd.DataFrame([{"capability_id": "utility_endpoint_regions", "capability_status": "unsupported_unresolved"}]),
        "feature_missingness": pd.DataFrame(),
    }
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]

    eligibility = build_feature_eligibility(rounds, inputs, maps, target_team="Vitality", settings={"structural_review": {"exclude_from_ranked_findings": True}})
    by_feature = eligibility.set_index("feature_name")

    assert by_feature.loc["smokes_to_mid_control_0_15", "exclusion_reason"] == "unresolved_endpoint"
    assert by_feature.loc["team_center_x_10s", "exclusion_reason"] == "normalized_required"
    assert bool(by_feature.loc["flashes_used_0_15", "eligible_for_direct_comparison"]) is True


def test_structural_review_feature_is_excluded_from_ranked_findings() -> None:
    rounds = pd.DataFrame({"map_id": ["mirage", "inferno"], "players_mid_control_0_15": [1, 2]})
    inputs = {
        "feature_contract": pd.DataFrame([{"feature_name": "players_mid_control_0_15", "feature_family": "semantic_control", "cross_map_comparable": True, "cross_map_comparison_mode": "semantic", "coordinate_dependency": "none", "region_semantic": "mid_control"}]),
        "cross_map_sanity": pd.DataFrame([{"feature_name": "players_mid_control_0_15", "structural_mismatch": True}]),
        "capabilities": pd.DataFrame([{"capability_id": "utility_endpoint_regions", "capability_status": "unsupported_unresolved"}]),
        "feature_missingness": pd.DataFrame(),
    }
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]

    eligibility = build_feature_eligibility(rounds, inputs, maps, target_team="Vitality", settings={"structural_review": {"exclude_from_ranked_findings": True}})

    assert bool(eligibility.loc[0, "structural_review_flag"]) is True
    assert bool(eligibility.loc[0, "eligible_for_ranked_findings"]) is False


def test_structural_review_semantic_excludes_related_features_from_ranked_findings() -> None:
    rounds = pd.DataFrame({"map_id": ["mirage", "inferno"], "time_mid_control_0_35": [1.0, 2.0]})
    inputs = {
        "feature_contract": pd.DataFrame([{"feature_name": "time_mid_control_0_35", "feature_family": "semantic_control", "cross_map_comparable": True, "cross_map_comparison_mode": "semantic", "coordinate_dependency": "none", "region_semantic": "mid_control"}]),
        "cross_map_sanity": pd.DataFrame([{"feature_name": "players_mid_control_0_15", "region_semantic": "mid_control", "structural_mismatch": True}]),
        "capabilities": pd.DataFrame([{"capability_id": "utility_endpoint_regions", "capability_status": "unsupported_unresolved"}]),
        "feature_missingness": pd.DataFrame(),
    }
    maps = [DummyMap("mirage", "Mirage"), DummyMap("inferno", "Inferno")]

    eligibility = build_feature_eligibility(rounds, inputs, maps, target_team="Vitality", settings={"structural_review": {"exclude_from_ranked_findings": True}})

    assert bool(eligibility.loc[0, "structural_review_flag"]) is True
    assert bool(eligibility.loc[0, "eligible_for_ranked_findings"]) is False
    assert eligibility.loc[0, "exclusion_reason"] == "structural_review"


def test_cluster_bootstrap_is_deterministic_by_demo() -> None:
    settings = {"bootstrap": {"enabled": True, "resamples": 100, "confidence_level": 0.95, "random_seed": 7}}
    left = pd.DataFrame({"parse_id": ["a", "a", "b", "b"], "feature": [1, 1, 2, 2]})
    right = pd.DataFrame({"parse_id": ["c", "c", "d", "d"], "feature": [3, 3, 4, 4]})

    first = cluster_bootstrap_difference(left, "feature", right, "feature", statistic="median_difference", settings=settings)
    second = cluster_bootstrap_difference(left, "feature", right, "feature", statistic="median_difference", settings=settings)

    assert first == second
    assert first[0] is not None and first[1] is not None
    assert cliffs_delta(left["feature"], right["feature"]) > 0


def test_read_only_audit_detects_unchanged_core(tmp_path: Path) -> None:
    gold = tmp_path / "data" / "gold"
    (gold / "round_features").mkdir(parents=True)
    pd.DataFrame([{"round_feature_id": "r1"}]).to_parquet(gold / "round_features" / "round_features_mvp.parquet", index=False)

    before = capture_core_fingerprints(tmp_path, gold)
    after = capture_core_fingerprints(tmp_path, gold)
    audit = build_read_only_audit(before, after)

    assert audit["status"].eq("ok").all()


class DummyMap:
    def __init__(self, map_id: str, map_name: str) -> None:
        self.map_id = map_id
        self.map_name = map_name


def write_registry(tmp_path: Path) -> Path:
    maps = tmp_path / "configs" / "maps"
    maps.mkdir(parents=True)
    path = maps / "map_registry.yaml"
    path.write_text(
        """
registry_version: v1
maps:
- map_id: mirage
  display_name: Mirage
  game_map_name: de_mirage
  config_path: configs/maps/mirage.yaml
- map_id: inferno
  display_name: Inferno
  game_map_name: de_inferno
  config_path: configs/maps/inferno.yaml
""".strip(),
        encoding="utf-8",
    )
    for map_id, display in [("mirage", "Mirage"), ("inferno", "Inferno")]:
        (maps / f"{map_id}.yaml").write_text(
            f"""
map_id: {map_id}
display_name: {display}
game_map_name: de_{map_id}
region_schema_version: v1
coordinate_system: {{source: test}}
physical_regions: []
semantic_groups: {{}}
bombsites: {{}}
aliases: {{}}
""".strip(),
            encoding="utf-8",
        )
    return path
