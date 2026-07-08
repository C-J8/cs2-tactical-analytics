# T-side A/B Refined Experiment -- Vitality Mirage

## Scope

This focused experiment compares controlled feature sets at 15s, 35s, and 45s. It is not a final model or a hyperparameter search.

## Why this experiment exists

Stage 6.1 found many B-predicted-as-A errors. The primary objective is to improve B recall and reduce that error direction without sacrificing macro F1.

## Dataset

|   total_rows_input |   rows_after_t_side_filter |   rows_after_high_confidence_ab_filter |   rows_excluded_manual_review |   final_model_rows |   class_A |   class_B |   class_balance_A |   class_balance_B | manual_review_status                                          | status   |
|-------------------:|---------------------------:|---------------------------------------:|------------------------------:|-------------------:|----------:|----------:|------------------:|------------------:|:--------------------------------------------------------------|:---------|
|                 98 |                         98 |                                     98 |                             0 |                 98 |        72 |        26 |          0.734694 |          0.265306 | manual_review_pending; refined experiment remains preliminary | ok       |

## Feature sets

|   horizon_seconds | feature_set_name    |   model_rows |   total_selected_features |   numeric_features |   categorical_features | notes                                                                          |
|------------------:|:--------------------|-------------:|--------------------------:|-------------------:|-----------------------:|:-------------------------------------------------------------------------------|
|                15 | all_safe            |           98 |                        29 |                 29 |                      0 | All leakage-safe and horizon-safe features.                                    |
|                15 | stable_only         |           98 |                        19 |                 19 |                      0 | Stable/model-specific candidates with baseline-importance fallback.            |
|                15 | no_preround_context |           98 |                        26 |                 26 |                      0 | Removes general pre-round context while retaining initial utility inventory.   |
|                15 | region_utility_only |           98 |                        26 |                 26 |                      0 | Region, position, pressure, and utility signals only.                          |
|                15 | b_focused           |           98 |                        22 |                 22 |                      0 | Existing B-associated, error-contrast, regional-keyword, and utility features. |
|                35 | all_safe            |           89 |                        94 |                 94 |                      0 | All leakage-safe and horizon-safe features.                                    |
|                35 | stable_only         |           89 |                        31 |                 31 |                      0 | Stable/model-specific candidates with baseline-importance fallback.            |
|                35 | no_preround_context |           89 |                        91 |                 91 |                      0 | Removes general pre-round context while retaining initial utility inventory.   |
|                35 | region_utility_only |           89 |                        91 |                 91 |                      0 | Region, position, pressure, and utility signals only.                          |
|                35 | b_focused           |           89 |                        66 |                 66 |                      0 | Existing B-associated, error-contrast, regional-keyword, and utility features. |
|                45 | all_safe            |           79 |                       116 |                116 |                      0 | All leakage-safe and horizon-safe features.                                    |
|                45 | stable_only         |           79 |                        41 |                 41 |                      0 | Stable/model-specific candidates with baseline-importance fallback.            |
|                45 | no_preround_context |           79 |                       113 |                113 |                      0 | Removes general pre-round context while retaining initial utility inventory.   |
|                45 | region_utility_only |           79 |                       113 |                113 |                      0 | Region, position, pressure, and utility signals only.                          |
|                45 | b_focused           |           79 |                        81 |                 81 |                      0 | Existing B-associated, error-contrast, regional-keyword, and utility features. |

## Horizons

The default experiment keeps 15s as the early baseline and evaluates 35s/45s as practical refinement candidates. No 65s model is included by default.

## Metrics

|   horizon_seconds | feature_set_name    | model_name          |   macro_f1 |   balanced_accuracy |   recall_A |   recall_B |   B_predicted_as_A |   high_confidence_B_predicted_as_A |
|------------------:|:--------------------|:--------------------|-----------:|--------------------:|-----------:|-----------:|-------------------:|-----------------------------------:|
|                15 | all_safe            | logistic_regression |   0.657171 |            0.670406 |   0.763889 |   0.576923 |                 11 |                                  5 |
|                15 | all_safe            | random_forest       |   0.666667 |            0.650641 |   0.916667 |   0.384615 |                 16 |                                 11 |
|                15 | stable_only         | logistic_regression |   0.624149 |            0.637286 |   0.736111 |   0.538462 |                 12 |                                  6 |
|                15 | stable_only         | random_forest       |   0.706938 |            0.689103 |   0.916667 |   0.461538 |                 14 |                                 12 |
|                15 | no_preround_context | logistic_regression |   0.666036 |            0.67735  |   0.777778 |   0.576923 |                 11 |                                  3 |
|                15 | no_preround_context | random_forest       |   0.623077 |            0.612179 |   0.916667 |   0.307692 |                 18 |                                 10 |
|                15 | region_utility_only | logistic_regression |   0.666036 |            0.67735  |   0.777778 |   0.576923 |                 11 |                                  3 |
|                15 | region_utility_only | random_forest       |   0.623077 |            0.612179 |   0.916667 |   0.307692 |                 18 |                                 10 |
|                15 | b_focused           | logistic_regression |   0.651989 |            0.68109  |   0.708333 |   0.653846 |                  9 |                                  4 |
|                15 | b_focused           | random_forest       |   0.666667 |            0.650641 |   0.916667 |   0.384615 |                 16 |                                 11 |
|                35 | all_safe            | logistic_regression |   0.557084 |            0.56375  |   0.6875   |   0.44     |                 14 |                                 11 |
|                35 | all_safe            | random_forest       |   0.565038 |            0.565312 |   0.890625 |   0.24     |                 19 |                                 10 |
|                35 | stable_only         | logistic_regression |   0.671101 |            0.682813 |   0.765625 |   0.6      |                 10 |                                  4 |
|                35 | stable_only         | random_forest       |   0.565038 |            0.565312 |   0.890625 |   0.24     |                 19 |                                  8 |
|                35 | no_preround_context | logistic_regression |   0.539542 |            0.54375  |   0.6875   |   0.4      |                 15 |                                 11 |
|                35 | no_preround_context | random_forest       |   0.61698  |            0.60875  |   0.9375   |   0.28     |                 18 |                                  9 |
|                35 | region_utility_only | logistic_regression |   0.539542 |            0.54375  |   0.6875   |   0.4      |                 15 |                                 11 |
|                35 | region_utility_only | random_forest       |   0.61698  |            0.60875  |   0.9375   |   0.28     |                 18 |                                  9 |
|                35 | b_focused           | logistic_regression |   0.613423 |            0.635938 |   0.671875 |   0.6      |                 10 |                                  9 |
|                35 | b_focused           | random_forest       |   0.57351  |            0.573125 |   0.90625  |   0.24     |                 19 |                                 11 |
|                45 | all_safe            | logistic_regression |   0.539806 |            0.57161  |   0.59322  |   0.55     |                  9 |                                  6 |
|                45 | all_safe            | random_forest       |   0.565934 |            0.566102 |   0.932203 |   0.2      |                 16 |                                  6 |
|                45 | stable_only         | logistic_regression |   0.696461 |            0.70678  |   0.813559 |   0.6      |                  8 |                                  5 |
|                45 | stable_only         | random_forest       |   0.629687 |            0.616102 |   0.932203 |   0.3      |                 14 |                                  5 |
|                45 | no_preround_context | logistic_regression |   0.557423 |            0.59661  |   0.59322  |   0.6      |                  8 |                                  7 |
|                45 | no_preround_context | random_forest       |   0.539627 |            0.549576 |   0.949153 |   0.15     |                 17 |                                  5 |
|                45 | region_utility_only | logistic_regression |   0.557423 |            0.59661  |   0.59322  |   0.6      |                  8 |                                  7 |
|                45 | region_utility_only | random_forest       |   0.539627 |            0.549576 |   0.949153 |   0.15     |                 17 |                                  5 |
|                45 | b_focused           | logistic_regression |   0.522265 |            0.538559 |   0.627119 |   0.45     |                 11 |                                  7 |
|                45 | b_focused           | random_forest       |   0.522527 |            0.532627 |   0.915254 |   0.15     |                 17 |                                  5 |

## B-error analysis

|   horizon_seconds | feature_set_name    | model_name          |   total_errors |   B_predicted_as_A |   high_confidence_B_predicted_as_A | interpretation_note                                |
|------------------:|:--------------------|:--------------------|---------------:|-------------------:|-----------------------------------:|:---------------------------------------------------|
|                15 | all_safe            | logistic_regression |             28 |                 11 |                                  5 | A/B error directions are mixed                     |
|                15 | all_safe            | random_forest       |             22 |                 16 |                                 11 | B_predicted_as_A dominates; 11 are high-confidence |
|                15 | b_focused           | logistic_regression |             30 |                  9 |                                  4 | A/B error directions are mixed                     |
|                15 | b_focused           | random_forest       |             22 |                 16 |                                 11 | B_predicted_as_A dominates; 11 are high-confidence |
|                15 | no_preround_context | logistic_regression |             27 |                 11 |                                  3 | A/B error directions are mixed                     |
|                15 | no_preround_context | random_forest       |             24 |                 18 |                                 10 | B_predicted_as_A dominates; 10 are high-confidence |
|                15 | region_utility_only | logistic_regression |             27 |                 11 |                                  3 | A/B error directions are mixed                     |
|                15 | region_utility_only | random_forest       |             24 |                 18 |                                 10 | B_predicted_as_A dominates; 10 are high-confidence |
|                15 | stable_only         | logistic_regression |             31 |                 12 |                                  6 | A/B error directions are mixed                     |
|                15 | stable_only         | random_forest       |             20 |                 14 |                                 12 | B_predicted_as_A dominates; 12 are high-confidence |
|                35 | all_safe            | logistic_regression |             34 |                 14 |                                 11 | A/B error directions are mixed                     |
|                35 | all_safe            | random_forest       |             26 |                 19 |                                 10 | B_predicted_as_A dominates; 10 are high-confidence |
|                35 | b_focused           | logistic_regression |             31 |                 10 |                                  9 | A/B error directions are mixed                     |
|                35 | b_focused           | random_forest       |             25 |                 19 |                                 11 | B_predicted_as_A dominates; 11 are high-confidence |
|                35 | no_preround_context | logistic_regression |             35 |                 15 |                                 11 | A/B error directions are mixed                     |
|                35 | no_preround_context | random_forest       |             22 |                 18 |                                  9 | B_predicted_as_A dominates; 9 are high-confidence  |
|                35 | region_utility_only | logistic_regression |             35 |                 15 |                                 11 | A/B error directions are mixed                     |
|                35 | region_utility_only | random_forest       |             22 |                 18 |                                  9 | B_predicted_as_A dominates; 9 are high-confidence  |
|                35 | stable_only         | logistic_regression |             25 |                 10 |                                  4 | A/B error directions are mixed                     |
|                35 | stable_only         | random_forest       |             26 |                 19 |                                  8 | B_predicted_as_A dominates; 8 are high-confidence  |
|                45 | all_safe            | logistic_regression |             33 |                  9 |                                  6 | A/B error directions are mixed                     |
|                45 | all_safe            | random_forest       |             20 |                 16 |                                  6 | B_predicted_as_A dominates; 6 are high-confidence  |
|                45 | b_focused           | logistic_regression |             33 |                 11 |                                  7 | A/B error directions are mixed                     |
|                45 | b_focused           | random_forest       |             22 |                 17 |                                  5 | B_predicted_as_A dominates; 5 are high-confidence  |
|                45 | no_preround_context | logistic_regression |             32 |                  8 |                                  7 | A/B error directions are mixed                     |
|                45 | no_preround_context | random_forest       |             20 |                 17 |                                  5 | B_predicted_as_A dominates; 5 are high-confidence  |
|                45 | region_utility_only | logistic_regression |             32 |                  8 |                                  7 | A/B error directions are mixed                     |
|                45 | region_utility_only | random_forest       |             20 |                 17 |                                  5 | B_predicted_as_A dominates; 5 are high-confidence  |
|                45 | stable_only         | logistic_regression |             19 |                  8 |                                  5 | A/B error directions are mixed                     |
|                45 | stable_only         | random_forest       |             18 |                 14 |                                  5 | B_predicted_as_A dominates; 5 are high-confidence  |

## Comparison vs Stage 6 baseline

|   horizon_seconds | feature_set_name    | model_name          |   delta_macro_f1 |   delta_recall_B |   delta_B_predicted_as_A | comparison_status   |
|------------------:|:--------------------|:--------------------|-----------------:|-----------------:|-------------------------:|:--------------------|
|                15 | all_safe            | logistic_regression |       0          |        0         |                        0 | mixed               |
|                15 | all_safe            | random_forest       |       0          |        0         |                        0 | mixed               |
|                15 | stable_only         | logistic_regression |      -0.033022   |       -0.0384615 |                        1 | worse               |
|                15 | stable_only         | random_forest       |       0.0402711  |        0.0769231 |                       -2 | improved            |
|                15 | no_preround_context | logistic_regression |       0.00886418 |        0         |                        0 | improved            |
|                15 | no_preround_context | random_forest       |      -0.0435897  |       -0.0769231 |                        2 | worse               |
|                15 | region_utility_only | logistic_regression |       0.00886418 |        0         |                        0 | improved            |
|                15 | region_utility_only | random_forest       |      -0.0435897  |       -0.0769231 |                        2 | worse               |
|                15 | b_focused           | logistic_regression |      -0.00518278 |        0.0769231 |                       -2 | b_recall_improved   |
|                15 | b_focused           | random_forest       |       0          |        0         |                        0 | mixed               |
|                35 | all_safe            | logistic_regression |       0          |        0         |                        0 | mixed               |
|                35 | all_safe            | random_forest       |      -0.00847209 |        0         |                        0 | mixed               |
|                35 | stable_only         | logistic_regression |       0.114017   |        0.16      |                       -4 | improved            |
|                35 | stable_only         | random_forest       |      -0.00847209 |        0         |                        0 | mixed               |
|                35 | no_preround_context | logistic_regression |      -0.0175426  |       -0.04      |                        1 | worse               |
|                35 | no_preround_context | random_forest       |       0.04347    |        0.04      |                       -1 | improved            |
|                35 | region_utility_only | logistic_regression |      -0.0175426  |       -0.04      |                        1 | worse               |
|                35 | region_utility_only | random_forest       |       0.04347    |        0.04      |                       -1 | improved            |
|                35 | b_focused           | logistic_regression |       0.0563387  |        0.16      |                       -4 | improved            |
|                35 | b_focused           | random_forest       |       0          |        0         |                        0 | mixed               |
|                45 | all_safe            | logistic_regression |       0          |        0         |                        0 | mixed               |
|                45 | all_safe            | random_forest       |       0          |        0         |                        0 | mixed               |
|                45 | stable_only         | logistic_regression |       0.156655   |        0.05      |                       -1 | improved            |
|                45 | stable_only         | random_forest       |       0.0637534  |        0.1       |                       -2 | improved            |
|                45 | no_preround_context | logistic_regression |       0.0176171  |        0.05      |                       -1 | improved            |
|                45 | no_preround_context | random_forest       |      -0.026307   |       -0.05      |                        1 | worse               |
|                45 | region_utility_only | logistic_regression |       0.0176171  |        0.05      |                       -1 | improved            |
|                45 | region_utility_only | random_forest       |      -0.026307   |       -0.05      |                        1 | worse               |
|                45 | b_focused           | logistic_regression |      -0.0175408  |       -0.1       |                        2 | worse               |
|                45 | b_focused           | random_forest       |      -0.0434066  |       -0.05      |                        1 | worse               |

## Feature importance

|   horizon_seconds | feature_set_name    | model_name          | feature_name              | feature_group   |   importance_value |   importance_rank | direction   |
|------------------:|:--------------------|:--------------------|:--------------------------|:----------------|-------------------:|------------------:|:------------|
|                15 | all_safe            | logistic_regression | time_mid_control_0_15     | region_position |          0.884562  |                 1 | B           |
|                15 | all_safe            | logistic_regression | team_molotovs_start       | utility         |         -0.797187  |                 2 | A           |
|                15 | all_safe            | logistic_regression | time_b_pressure_0_15      | region_position |          0.746247  |                 3 | B           |
|                15 | all_safe            | random_forest       | time_a_pressure_0_15      | region_position |          0.0902635 |                 1 |             |
|                15 | all_safe            | random_forest       | team_center_x_15s         | region_position |          0.0810378 |                 2 |             |
|                15 | all_safe            | random_forest       | team_center_y_10s         | region_position |          0.0753605 |                 3 |             |
|                15 | b_focused           | logistic_regression | time_mid_control_0_15     | region_position |          0.95591   |                 1 | B           |
|                15 | b_focused           | logistic_regression | team_molotovs_start       | utility         |         -0.946118  |                 2 | A           |
|                15 | b_focused           | logistic_regression | time_b_pressure_0_15      | region_position |          0.851641  |                 3 | B           |
|                15 | b_focused           | random_forest       | time_a_pressure_0_15      | region_position |          0.111488  |                 1 |             |
|                15 | b_focused           | random_forest       | team_center_y_10s         | region_position |          0.105433  |                 2 |             |
|                15 | b_focused           | random_forest       | team_center_y_15s         | region_position |          0.0966219 |                 3 |             |
|                15 | no_preround_context | logistic_regression | team_molotovs_start       | utility         |         -0.933384  |                 1 | A           |
|                15 | no_preround_context | logistic_regression | time_mid_control_0_15     | region_position |          0.769702  |                 2 | B           |
|                15 | no_preround_context | logistic_regression | time_b_pressure_0_15      | region_position |          0.695514  |                 3 | B           |
|                15 | no_preround_context | random_forest       | time_a_pressure_0_15      | region_position |          0.103263  |                 1 |             |
|                15 | no_preround_context | random_forest       | team_center_y_15s         | region_position |          0.102029  |                 2 |             |
|                15 | no_preround_context | random_forest       | team_center_y_10s         | region_position |          0.081556  |                 3 |             |
|                15 | region_utility_only | logistic_regression | team_molotovs_start       | utility         |         -0.933384  |                 1 | A           |
|                15 | region_utility_only | logistic_regression | time_mid_control_0_15     | region_position |          0.769702  |                 2 | B           |
|                15 | region_utility_only | logistic_regression | time_b_pressure_0_15      | region_position |          0.695514  |                 3 | B           |
|                15 | region_utility_only | random_forest       | time_a_pressure_0_15      | region_position |          0.103263  |                 1 |             |
|                15 | region_utility_only | random_forest       | team_center_y_15s         | region_position |          0.102029  |                 2 |             |
|                15 | region_utility_only | random_forest       | team_center_y_10s         | region_position |          0.081556  |                 3 |             |
|                15 | stable_only         | logistic_regression | time_b_pressure_0_15      | region_position |          0.699293  |                 1 | B           |
|                15 | stable_only         | logistic_regression | round_num                 | context         |         -0.662672  |                 2 | A           |
|                15 | stable_only         | logistic_regression | is_pistol_round           | context         |         -0.634497  |                 3 | A           |
|                15 | stable_only         | random_forest       | team_center_y_15s         | region_position |          0.11398   |                 1 |             |
|                15 | stable_only         | random_forest       | time_a_pressure_0_15      | region_position |          0.112871  |                 2 |             |
|                15 | stable_only         | random_forest       | team_center_y_10s         | region_position |          0.0962258 |                 3 |             |
|                35 | all_safe            | logistic_regression | players_b_pressure_0_20   | region_position |         -0.783104  |                 1 | A           |
|                35 | all_safe            | logistic_regression | players_a_pressure_25_35  | region_position |         -0.757726  |                 2 | A           |
|                35 | all_safe            | logistic_regression | players_mid_control_25_35 | region_position |          0.731655  |                 3 | B           |
|                35 | all_safe            | random_forest       | time_a_pressure_0_25      | region_position |          0.0396787 |                 1 |             |
|                35 | all_safe            | random_forest       | players_a_pressure_25_35  | region_position |          0.0393059 |                 2 |             |
|                35 | all_safe            | random_forest       | time_a_pressure_0_35      | region_position |          0.0383373 |                 3 |             |
|                35 | b_focused           | logistic_regression | players_mid_control_25_35 | region_position |          0.877103  |                 1 | B           |
|                35 | b_focused           | logistic_regression | team_molotovs_start       | utility         |         -0.8368    |                 2 | A           |
|                35 | b_focused           | logistic_regression | players_a_pressure_0_25   | region_position |          0.724603  |                 3 | B           |
|                35 | b_focused           | random_forest       | time_a_pressure_0_35      | region_position |          0.0585895 |                 1 |             |
|                35 | b_focused           | random_forest       | time_a_pressure_0_25      | region_position |          0.0419301 |                 2 |             |
|                35 | b_focused           | random_forest       | time_a_pressure_0_20      | region_position |          0.040261  |                 3 |             |
|                35 | no_preround_context | logistic_regression | players_a_pressure_25_35  | region_position |         -0.856665  |                 1 | A           |
|                35 | no_preround_context | logistic_regression | players_mid_control_25_35 | region_position |          0.821037  |                 2 | B           |
|                35 | no_preround_context | logistic_regression | players_b_pressure_0_20   | region_position |         -0.817008  |                 3 | A           |

## Recommendation

|   rank |   horizon_seconds | feature_set_name    | model_name          |   macro_f1 |   recall_B |   B_predicted_as_A |   high_confidence_B_predicted_as_A |   delta_macro_f1_vs_baseline |   delta_recall_B_vs_baseline |   delta_B_predicted_as_A_vs_baseline | practical_note                                                                                                 | recommendation              |
|-------:|------------------:|:--------------------|:--------------------|-----------:|-----------:|-------------------:|-----------------------------------:|-----------------------------:|-----------------------------:|-------------------------------------:|:---------------------------------------------------------------------------------------------------------------|:----------------------------|
|      1 |                35 | stable_only         | logistic_regression |   0.671101 |   0.6      |                 10 |                                  4 |                   0.114017   |                    0.16      |                                   -4 | 35s stable_only with logistic_regression: delta macro F1 +0.114, delta recall_B +0.160, delta B->A -4.         | candidate_for_next_baseline |
|      2 |                35 | b_focused           | logistic_regression |   0.613423 |   0.6      |                 10 |                                  9 |                   0.0563387  |                    0.16      |                                   -4 | 35s b_focused with logistic_regression: delta macro F1 +0.056, delta recall_B +0.160, delta B->A -4.           | candidate_for_next_baseline |
|      3 |                45 | stable_only         | random_forest       |   0.629687 |   0.3      |                 14 |                                  5 |                   0.0637534  |                    0.1       |                                   -2 | 45s stable_only with random_forest: delta macro F1 +0.064, delta recall_B +0.100, delta B->A -2.               | candidate_for_next_baseline |
|      4 |                45 | stable_only         | logistic_regression |   0.696461 |   0.6      |                  8 |                                  5 |                   0.156655   |                    0.05      |                                   -1 | 45s stable_only with logistic_regression: delta macro F1 +0.157, delta recall_B +0.050, delta B->A -1.         | candidate_for_next_baseline |
|      5 |                45 | no_preround_context | logistic_regression |   0.557423 |   0.6      |                  8 |                                  7 |                   0.0176171  |                    0.05      |                                   -1 | 45s no_preround_context with logistic_regression: delta macro F1 +0.018, delta recall_B +0.050, delta B->A -1. | candidate_for_next_baseline |
|      6 |                45 | region_utility_only | logistic_regression |   0.557423 |   0.6      |                  8 |                                  7 |                   0.0176171  |                    0.05      |                                   -1 | 45s region_utility_only with logistic_regression: delta macro F1 +0.018, delta recall_B +0.050, delta B->A -1. | candidate_for_next_baseline |
|      7 |                35 | no_preround_context | random_forest       |   0.61698  |   0.28     |                 18 |                                  9 |                   0.04347    |                    0.04      |                                   -1 | 35s no_preround_context with random_forest: delta macro F1 +0.043, delta recall_B +0.040, delta B->A -1.       | candidate_for_next_baseline |
|      8 |                35 | region_utility_only | random_forest       |   0.61698  |   0.28     |                 18 |                                  9 |                   0.04347    |                    0.04      |                                   -1 | 35s region_utility_only with random_forest: delta macro F1 +0.043, delta recall_B +0.040, delta B->A -1.       | candidate_for_next_baseline |
|      9 |                15 | b_focused           | logistic_regression |   0.651989 |   0.653846 |                  9 |                                  4 |                  -0.00518278 |                    0.0769231 |                                   -2 | 15s b_focused with logistic_regression: delta macro F1 -0.005, delta recall_B +0.077, delta B->A -2.           | use_as_early_read_baseline  |
|     10 |                15 | stable_only         | random_forest       |   0.706938 |   0.461538 |                 14 |                                 12 |                   0.0402711  |                    0.0769231 |                                   -2 | 15s stable_only with random_forest: delta macro F1 +0.040, delta recall_B +0.077, delta B->A -2.               | use_as_early_read_baseline  |

## Limitations

- Plant B remains the lower-support class; no-plant rounds remain outside the task.
- Manual review is pending, so every recommendation remains preliminary.
- Comparisons reuse the same small sample and random round-level folds.
- Feature selection and importance are descriptive, not causal.
- No heavy tuning, new algorithm family, or external validation is performed.

## Next step

Choose one candidate baseline only if B recall improves without materially worsening B-predicted-as-A errors; otherwise complete manual review first.
