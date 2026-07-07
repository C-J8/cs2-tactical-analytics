# T-side A/B Baseline Error Analysis -- Vitality Mirage

## Scope

This stage interprets existing out-of-fold Stage 6 predictions. It does not train or tune a new model.

## Baseline recap

|   total_prediction_rows |   unique_rounds |   horizons |   models |   best_overall_horizon | best_overall_model   |   best_macro_f1 |   best_balanced_accuracy |   majority_baseline_best_macro_f1 |   best_improvement_over_majority |   total_errors_best_model |   total_high_confidence_errors_best_model | status   |
|------------------------:|----------------:|-----------:|---------:|-----------------------:|:---------------------|----------------:|-------------------------:|----------------------------------:|---------------------------------:|--------------------------:|------------------------------------------:|:---------|
|                    1494 |              98 |          6 |        3 |                     65 | logistic_regression  |        0.761905 |                 0.776005 |                          0.427536 |                         0.342262 |                        13 |                                        10 | ok       |

## Best models by horizon

|   horizon_seconds | model_name          |   macro_f1 |   balanced_accuracy |   recall_A |   recall_B |   improvement_over_majority | interpretation_note                                      |
|------------------:|:--------------------|-----------:|--------------------:|-----------:|-----------:|----------------------------:|:---------------------------------------------------------|
|                15 | random_forest       |   0.666667 |            0.650641 |   0.916667 |   0.384615 |                    0.243137 | beats majority baseline; good A recall but weak B recall |
|                25 | random_forest       |   0.616862 |            0.606838 |   0.944444 |   0.269231 |                    0.193333 | beats majority baseline; good A recall but weak B recall |
|                35 | random_forest       |   0.57351  |            0.573125 |   0.90625  |   0.24     |                    0.155209 | beats majority baseline; good A recall but weak B recall |
|                45 | random_forest       |   0.565934 |            0.566102 |   0.932203 |   0.2      |                    0.138398 | beats majority baseline; good A recall but weak B recall |
|                55 | logistic_regression |   0.705054 |            0.708163 |   0.816327 |   0.6      |                    0.2898   | beats majority baseline                                  |
|                65 | logistic_regression |   0.761905 |            0.776005 |   0.829787 |   0.722222 |                    0.342262 | beats majority baseline                                  |

## Error overview

|   horizon_seconds | model_name          |   total_predictions |   total_errors |   error_rate |   high_confidence_errors |
|------------------:|:--------------------|--------------------:|---------------:|-------------:|-------------------------:|
|                15 | random_forest       |                  98 |             22 |     0.22449  |                       12 |
|                25 | random_forest       |                  98 |             23 |     0.234694 |                       11 |
|                35 | random_forest       |                  89 |             25 |     0.280899 |                       12 |
|                45 | random_forest       |                  79 |             20 |     0.253165 |                        6 |
|                55 | logistic_regression |                  69 |             17 |     0.246377 |                       13 |
|                65 | logistic_regression |                  65 |             13 |     0.2      |                       10 |

## High-confidence errors

|   horizon_seconds | model_name          | opponent   |   round_num | true_label   | predicted_label   |   prediction_confidence | suggested_error_reason                     |
|------------------:|:--------------------|:-----------|------------:|:-------------|:------------------|------------------------:|:-------------------------------------------|
|                55 | logistic_regression | Spirit     |          15 | B            | A                 |                1        | opponent-specific tendency may need review |
|                65 | logistic_regression | Spirit     |          15 | B            | A                 |                0.999984 | opponent-specific tendency may need review |
|                65 | logistic_regression | FURIA      |          18 | A            | B                 |                0.999907 | model may be overreacting to B-like signal |
|                55 | logistic_regression | G2         |          13 | A            | B                 |                0.999756 | opponent-specific tendency may need review |
|                55 | logistic_regression | FURIA      |          18 | A            | B                 |                0.999738 | model may be overreacting to B-like signal |
|                65 | logistic_regression | G2         |          13 | A            | B                 |                0.998709 | opponent-specific tendency may need review |
|                55 | logistic_regression | G2         |          27 | B            | A                 |                0.996966 | opponent-specific tendency may need review |
|                35 | random_forest       | Spirit     |          15 | B            | A                 |                0.99     | opponent-specific tendency may need review |
|                55 | logistic_regression | BC.Game    |          16 | B            | A                 |                0.988975 | model may be overusing A-majority pattern  |
|                65 | logistic_regression | Spirit     |          17 | A            | B                 |                0.976456 | opponent-specific tendency may need review |

## A vs B class behavior

|   horizon_seconds | model_name          | true_label   |   total_predictions |   errors |   error_rate |   recall | interpretation_note                     |
|------------------:|:--------------------|:-------------|--------------------:|---------:|-------------:|---------:|:----------------------------------------|
|                15 | random_forest       | A            |                  72 |        6 |    0.0833333 | 0.916667 | A recall should be read with support=72 |
|                15 | random_forest       | B            |                  26 |       16 |    0.615385  | 0.384615 | B recall is weak                        |
|                25 | random_forest       | A            |                  72 |        4 |    0.0555556 | 0.944444 | A recall should be read with support=72 |
|                25 | random_forest       | B            |                  26 |       19 |    0.730769  | 0.269231 | B recall is weak                        |
|                35 | random_forest       | A            |                  64 |        6 |    0.09375   | 0.90625  | A recall should be read with support=64 |
|                35 | random_forest       | B            |                  25 |       19 |    0.76      | 0.24     | B recall is weak                        |
|                45 | random_forest       | A            |                  59 |        4 |    0.0677966 | 0.932203 | A recall should be read with support=59 |
|                45 | random_forest       | B            |                  20 |       16 |    0.8       | 0.2      | B recall is weak                        |
|                55 | logistic_regression | A            |                  49 |        9 |    0.183673  | 0.816327 | A recall should be read with support=49 |
|                55 | logistic_regression | B            |                  20 |        8 |    0.4       | 0.6      | B recall should be read with support=20 |
|                65 | logistic_regression | A            |                  47 |        8 |    0.170213  | 0.829787 | A recall should be read with support=47 |
|                65 | logistic_regression | B            |                  18 |        5 |    0.277778  | 0.722222 | B recall should be read with support=18 |

## Opponent-level errors

|   horizon_seconds | model_name          | opponent    |   total_predictions |   total_errors |   error_rate | most_common_error_type   | interpretation_note                                    |
|------------------:|:--------------------|:------------|--------------------:|---------------:|-------------:|:-------------------------|:-------------------------------------------------------|
|                35 | random_forest       | GamerLegion |                   1 |              1 |     1        | B_predicted_as_A         | sparse opponent sample                                 |
|                25 | random_forest       | BC.Game     |                   6 |              4 |     0.666667 | B_predicted_as_A         | high observed error rate; most common B_predicted_as_A |
|                45 | random_forest       | B8          |                   3 |              2 |     0.666667 | A_predicted_as_B         | high observed error rate; most common A_predicted_as_B |
|                35 | random_forest       | BC.Game     |                   5 |              3 |     0.6      | B_predicted_as_A         | high observed error rate; most common B_predicted_as_A |
|                45 | random_forest       | BC.Game     |                   5 |              3 |     0.6      | B_predicted_as_A         | high observed error rate; most common B_predicted_as_A |
|                55 | logistic_regression | G2          |                   8 |              4 |     0.5      | A_predicted_as_B         | high observed error rate; most common A_predicted_as_B |
|                15 | random_forest       | BC.Game     |                   6 |              3 |     0.5      | B_predicted_as_A         | high observed error rate; most common B_predicted_as_A |
|                45 | random_forest       | FUT         |                   4 |              2 |     0.5      | B_predicted_as_A         | high observed error rate; most common B_predicted_as_A |
|                35 | random_forest       | FUT         |                   5 |              2 |     0.4      | B_predicted_as_A         | no strong opponent-specific error concentration        |
|                55 | logistic_regression | BC.Game     |                   5 |              2 |     0.4      | B_predicted_as_A         | no strong opponent-specific error concentration        |
|                55 | logistic_regression | FURIA       |                   5 |              2 |     0.4      | B_predicted_as_A         | no strong opponent-specific error concentration        |
|                65 | logistic_regression | FURIA       |                   5 |              2 |     0.4      | A_predicted_as_B         | no strong opponent-specific error concentration        |
|                25 | random_forest       | FURIA       |                   8 |              3 |     0.375    | A_predicted_as_B         | no strong opponent-specific error concentration        |
|                35 | random_forest       | The MongolZ |                  21 |              7 |     0.333333 | B_predicted_as_A         | no strong opponent-specific error concentration        |
|                55 | logistic_regression | B8          |                   3 |              1 |     0.333333 | A_predicted_as_B         | no strong opponent-specific error concentration        |

## Feature importance stability

| clean_feature_name        | feature_group   |   models_appeared |   horizons_appeared |   appearances |   mean_rank | stability_label   | direction_summary   |
|:--------------------------|:----------------|------------------:|--------------------:|--------------:|------------:|:------------------|:--------------------|
| team_center_x_15s         | region_position |                 2 |                   4 |             4 |    12       | stable_candidate  | B                   |
| time_a_pressure_0_15      | region_position |                 1 |                   3 |             3 |     4.66667 | stable_candidate  | not_applicable      |
| team_center_y_10s         | region_position |                 1 |                   3 |             3 |     7       | stable_candidate  | not_applicable      |
| time_a_pressure_0_20      | region_position |                 1 |                   3 |             3 |     8       | stable_candidate  | not_applicable      |
| team_center_y_25s         | region_position |                 1 |                   3 |             3 |     8.33333 | stable_candidate  | not_applicable      |
| avg_pairwise_distance_15s | region_position |                 1 |                   3 |             3 |     8.66667 | stable_candidate  | not_applicable      |
| team_center_x_10s         | region_position |                 1 |                   3 |             3 |    12.6667  | stable_candidate  | not_applicable      |
| round_num                 | context         |                 1 |                   3 |             3 |    13.6667  | stable_candidate  | not_applicable      |
| avg_pairwise_distance_10s | region_position |                 1 |                   3 |             3 |    14       | stable_candidate  | not_applicable      |
| team_center_x_25s         | region_position |                 1 |                   3 |             3 |    14       | stable_candidate  | not_applicable      |

## Feature/error contrast

|   horizon_seconds | model_name          | feature_name      | prediction_group   |   count |   mean_value |   median_value |   missing_rate |
|------------------:|:--------------------|:------------------|:-------------------|--------:|-------------:|---------------:|---------------:|
|                15 | random_forest       | team_center_x_15s | A_predicted_as_B   |       6 |      394.038 |        365.522 |              0 |
|                15 | random_forest       | team_center_x_15s | B_predicted_as_A   |      16 |      604.934 |        590.144 |              0 |
|                15 | random_forest       | team_center_x_15s | correct_A          |      66 |      710.119 |        677.965 |              0 |
|                15 | random_forest       | team_center_x_15s | correct_B          |      10 |      342.326 |        371.006 |              0 |
|                25 | random_forest       | team_center_x_15s | A_predicted_as_B   |       4 |      310.015 |        336.072 |              0 |
|                25 | random_forest       | team_center_x_15s | B_predicted_as_A   |      19 |      591.737 |        588.854 |              0 |
|                25 | random_forest       | team_center_x_15s | correct_A          |      68 |      705.765 |        660.885 |              0 |
|                25 | random_forest       | team_center_x_15s | correct_B          |       7 |      265.601 |        298.227 |              0 |
|                35 | random_forest       | team_center_x_15s | A_predicted_as_B   |       6 |      438.771 |        432.721 |              0 |
|                35 | random_forest       | team_center_x_15s | B_predicted_as_A   |      19 |      520.259 |        576.556 |              0 |
|                35 | random_forest       | team_center_x_15s | correct_A          |      58 |      687.315 |        647.349 |              0 |
|                35 | random_forest       | team_center_x_15s | correct_B          |       6 |      486.509 |        469.823 |              0 |
|                45 | random_forest       | team_center_x_15s | A_predicted_as_B   |       4 |      581.882 |        618.732 |              0 |
|                45 | random_forest       | team_center_x_15s | B_predicted_as_A   |      16 |      615.642 |        596.505 |              0 |
|                45 | random_forest       | team_center_x_15s | correct_A          |      55 |      645.826 |        616.949 |              0 |
|                45 | random_forest       | team_center_x_15s | correct_B          |       4 |      467.375 |        469.823 |              0 |
|                55 | logistic_regression | team_center_x_15s | A_predicted_as_B   |       9 |      609.062 |        623.412 |              0 |
|                55 | logistic_regression | team_center_x_15s | B_predicted_as_A   |       8 |      627.855 |        583.995 |              0 |
|                55 | logistic_regression | team_center_x_15s | correct_A          |      40 |      606.161 |        598.998 |              0 |
|                55 | logistic_regression | team_center_x_15s | correct_B          |      12 |      558.078 |        569.349 |              0 |

## Practical horizon recommendation

|   horizon_seconds | best_model          |   best_macro_f1 |   best_balanced_accuracy |   improvement_over_majority |   model_rows |   selected_features |   total_errors |   high_confidence_errors | practical_tradeoff                 | recommendation                       |
|------------------:|:--------------------|----------------:|-------------------------:|----------------------------:|-------------:|--------------------:|---------------:|-------------------------:|:-----------------------------------|:-------------------------------------|
|                15 | random_forest       |        0.666667 |                 0.650641 |                    0.243137 |           98 |                  29 |             22 |                       12 | early_but_weaker_signal            | keep_for_early_prediction_baseline   |
|                25 | random_forest       |        0.616862 |                 0.606838 |                    0.193333 |           98 |                  72 |             23 |                       11 | early_but_weaker_signal            | keep_for_early_prediction_baseline   |
|                35 | random_forest       |        0.57351  |                 0.573125 |                    0.155209 |           89 |                  94 |             25 |                       12 | balanced_signal_and_round_count    | use_as_main_next_experiment          |
|                45 | random_forest       |        0.565934 |                 0.566102 |                    0.138398 |           79 |                 116 |             20 |                        6 | balanced_signal_and_round_count    | use_as_main_next_experiment          |
|                55 | logistic_regression |        0.705054 |                 0.708163 |                    0.2898   |           69 |                 138 |             17 |                       13 | stronger_signal_but_smaller_cohort | inspect_before_using                 |
|                65 | logistic_regression |        0.761905 |                 0.776005 |                    0.342262 |           65 |                 160 |             13 |                       10 | late_round_less_actionable         | avoid_as_primary_due_to_small_cohort |

## Manual review queue

| review_id        | priority   |   horizon_seconds | model_name          | opponent    |   round_num | error_type       |   prediction_confidence | reason                                                                         |
|:-----------------|:-----------|------------------:|:--------------------|:------------|------------:|:-----------------|------------------------:|:-------------------------------------------------------------------------------|
| error_review_001 | high       |                55 | logistic_regression | G2          |          27 | B_predicted_as_A |                0.996966 | opponent-specific tendency may need review; repeated in 5 selected predictions |
| error_review_002 | high       |                25 | random_forest       | The MongolZ |          14 | B_predicted_as_A |                0.895    | opponent-specific tendency may need review; repeated in 4 selected predictions |
| error_review_003 | high       |                25 | random_forest       | FUT         |          14 | B_predicted_as_A |                0.865    | model may be overusing A-majority pattern; repeated in 4 selected predictions  |
| error_review_004 | high       |                15 | random_forest       | BC.Game     |          17 | B_predicted_as_A |                0.82     | model may be overusing A-majority pattern; repeated in 4 selected predictions  |
| error_review_005 | high       |                45 | random_forest       | G2          |          16 | B_predicted_as_A |                0.805    | opponent-specific tendency may need review; repeated in 4 selected predictions |
| error_review_006 | high       |                15 | random_forest       | BC.Game     |          18 | B_predicted_as_A |                0.79     | model may be overusing A-majority pattern; repeated in 4 selected predictions  |
| error_review_007 | high       |                15 | random_forest       | The MongolZ |          14 | B_predicted_as_A |                0.785    | opponent-specific tendency may need review; repeated in 5 selected predictions |
| error_review_008 | high       |                15 | random_forest       | BC.Game     |          19 | B_predicted_as_A |                0.775    | model may be overusing A-majority pattern; repeated in 5 selected predictions  |
| error_review_009 | high       |                55 | logistic_regression | Spirit      |          15 | B_predicted_as_A |                1        | opponent-specific tendency may need review; repeated in 6 selected predictions |
| error_review_010 | high       |                65 | logistic_regression | Spirit      |          25 | B_predicted_as_A |                0.967925 | opponent-specific tendency may need review; repeated in 5 selected predictions |

## Limitations

- This analysis reuses the same small, imbalanced Stage 6 sample and does not establish production readiness.
- Plant B has lower support than plant A; no-plant rounds remain outside the A/B task.
- Larger horizons use different, smaller cohorts after pre-plant filtering.
- Feature importance and error contrasts are descriptive, not causal.
- Random round-level folds are not external or future-series validation.

## Next step

Complete the error review queue, then refine leakage-safe features or run one focused model experiment.
