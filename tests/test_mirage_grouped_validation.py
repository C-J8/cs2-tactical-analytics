import pandas as pd

from src.modeling.mirage_ab_grouped_validation import evaluate_scheme


def test_grouped_validation_never_leaks_groups_between_folds() -> None:
    rows = []
    for group in range(6):
        for row in range(4):
            label = "B" if (group + row) % 3 == 0 else "A"
            rows.append(
                {
                    "round_feature_id": f"g{group}_r{row}",
                    "round_id": f"g{group}_r{row}",
                    "parse_id": f"p{group}",
                    "series_id": f"s{group}",
                    "resolved_group_id": f"s{group}",
                    "opponent": "x",
                    "round_num": row + 1,
                    "feature_a": group + row,
                    "feature_b": row,
                    "label": label,
                }
            )
    dataset = pd.DataFrame(rows)
    config = {
        "candidate_id": "candidate",
        "positive_class": "B",
        "probability_threshold": 0.5,
        "primary_validation": {"n_splits": 3, "shuffle": True, "random_state": 7},
        "model": {"imputer": "median", "class_weight": "balanced", "max_iter": 2000, "random_state": 7},
    }

    result = evaluate_scheme(
        dataset,
        ["feature_a", "feature_b"],
        config,
        scheme="stratified_group_kfold",
        group_column="series_id",
    )

    assert len(result["oof"]) == len(dataset)
    assert result["isolation"]["group_overlap_count"].eq(0).all()
    assert result["isolation"]["status"].eq("passed").all()
