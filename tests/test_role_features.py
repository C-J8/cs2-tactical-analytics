import numpy as np
import pandas as pd

from src.features.build_role_features import (
    FEATURE_ENGINE,
    add_target_team_projection,
    build_output_views,
    convex_hull_area,
    median_distance_to_centroid,
    median_pairwise_distance,
)
from src.features.run_map_pipeline import PIPELINE_STEPS


def test_dispersion_metrics_have_explicit_geometric_meaning() -> None:
    points = np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 4.0]])

    assert median_pairwise_distance(points) == 4.0
    assert convex_hull_area(points) == 6.0
    assert median_distance_to_centroid(points) > 0


def test_target_team_projection_switches_with_resolved_side_without_duplicate_ids() -> None:
    frame = pd.DataFrame(
        {
            "round_feature_id": ["r1", "r2"],
            "target_team_side": ["T", "CT"],
            "attack_players_alive_10s_snapshot": [5, 4],
            "defense_players_alive_10s_snapshot": [3, 2],
        }
    )

    projected = add_target_team_projection(frame)

    assert projected.columns.is_unique
    assert projected["target_team_players_alive_10s_snapshot"].tolist() == [5, 2]
    assert projected["opponent_players_alive_10s_snapshot"].tolist() == [3, 4]


def test_role_feature_outputs_use_canonical_names_without_version_suffix() -> None:
    canonical = pd.DataFrame(
        {
            "round_feature_id": ["r1"],
            "feature_engine": [FEATURE_ENGINE],
            "target_site_model_label": ["A"],
            "label_confidence": ["high"],
            "attack_players_alive_10s_snapshot": [5],
            "defense_players_alive_10s_snapshot": [5],
        }
    )
    dictionary = pd.DataFrame(
        {
            "feature_name": ["attack_players_alive_10s_snapshot", "defense_players_alive_10s_snapshot"],
            "map_scope": ["global", "global"],
        }
    )

    frames = build_output_views(canonical, dictionary, pd.DataFrame(), pd.DataFrame())

    assert FEATURE_ENGINE == "role-aware"
    assert set(frames) == {
        "round_role_features",
        "round_attack_features",
        "round_defense_features",
        "round_target_team_features",
        "round_map_features",
        "feature_dictionary",
        "feature_aliases",
        "role_feature_audit",
    }
    assert all("v2" not in name for name in frames)


def test_map_pipeline_exposes_one_canonical_role_feature_stage() -> None:
    assert "legacy_round_features" in PIPELINE_STEPS
    assert "role_features" in PIPELINE_STEPS
    assert all("v2" not in step for step in PIPELINE_STEPS)
