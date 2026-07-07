# T-side A/B Baseline Model -- Vitality Mirage

## Scope

This baseline predicts high-confidence plant A versus plant B for T-side rounds only. It is an auditable reference, not a final model.

## Dataset

|   total_rows_input |   rows_after_team_map_filter |   rows_after_t_side_filter |   rows_after_high_confidence_ab_filter |   rows_excluded_manual_review |   final_model_rows |   class_A |   class_B |   class_balance_A |   class_balance_B | manual_review_status                        | plant_time_status                                                                | status   |
|-------------------:|-----------------------------:|---------------------------:|---------------------------------------:|------------------------------:|-------------------:|----------:|----------:|------------------:|------------------:|:--------------------------------------------|:---------------------------------------------------------------------------------|:---------|
|                 98 |                           98 |                         98 |                                     98 |                             0 |                 98 |        72 |        26 |          0.734694 |          0.265306 | manual_review_pending; model is preliminary | plant_time_available_for_98_of_98; rows planted before each horizon are excluded | ok       |

## Leakage controls

Feature-catalog exclusions, manual leakage-name blocks, identifier removal, strict pre-round context allowlisting, horizon filtering, and plant-time row filtering are applied before cross-validation.

## Prediction horizons

|   horizon_seconds |   model_rows |   total_selected_features |   numeric_features |   categorical_features |   rows_excluded_plant_before_horizon |
|------------------:|-------------:|--------------------------:|-------------------:|-----------------------:|-------------------------------------:|
|                15 |           98 |                        29 |                 29 |                      0 |                                    0 |
|                25 |           98 |                        72 |                 72 |                      0 |                                    0 |
|                35 |           89 |                        94 |                 94 |                      0 |                                    9 |
|                45 |           79 |                       116 |                116 |                      0 |                                   19 |
|                55 |           69 |                       138 |                138 |                      0 |                                   29 |
|                65 |           65 |                       160 |                160 |                      0 |                                   33 |

## Class balance

The current sample is small and imbalanced: plant B has materially lower support than plant A. No-plant rounds are excluded rather than assigned an inferred site.

## Metrics by horizon

|   horizon_seconds | model_name          |   accuracy |   balanced_accuracy |   macro_f1 |     f1_A |     f1_B |   roc_auc |   support_A |   support_B |
|------------------:|:--------------------|-----------:|--------------------:|-----------:|---------:|---------:|----------:|------------:|------------:|
|                15 | majority_baseline   |   0.734694 |            0.5      |   0.423529 | 0.847059 | 0        |  0.5      |          72 |          26 |
|                15 | logistic_regression |   0.714286 |            0.670406 |   0.657171 | 0.797101 | 0.517241 |  0.746261 |          72 |          26 |
|                15 | random_forest       |   0.77551  |            0.650641 |   0.666667 | 0.857143 | 0.47619  |  0.745459 |          72 |          26 |
|                25 | majority_baseline   |   0.734694 |            0.5      |   0.423529 | 0.847059 | 0        |  0.5      |          72 |          26 |
|                25 | logistic_regression |   0.673469 |            0.581197 |   0.581197 | 0.777778 | 0.384615 |  0.69391  |          72 |          26 |
|                25 | random_forest       |   0.765306 |            0.606838 |   0.616862 | 0.855346 | 0.378378 |  0.790331 |          72 |          26 |
|                35 | majority_baseline   |   0.719101 |            0.5      |   0.418301 | 0.836601 | 0        |  0.5      |          64 |          25 |
|                35 | logistic_regression |   0.617978 |            0.56375  |   0.557084 | 0.721311 | 0.392857 |  0.5725   |          64 |          25 |
|                35 | random_forest       |   0.719101 |            0.573125 |   0.57351  | 0.822695 | 0.324324 |  0.73     |          64 |          25 |
|                45 | majority_baseline   |   0.746835 |            0.5      |   0.427536 | 0.855072 | 0        |  0.5      |          59 |          20 |
|                45 | logistic_regression |   0.582278 |            0.57161  |   0.539806 | 0.679612 | 0.4      |  0.597458 |          59 |          20 |
|                45 | random_forest       |   0.746835 |            0.566102 |   0.565934 | 0.846154 | 0.285714 |  0.760169 |          59 |          20 |
|                55 | majority_baseline   |   0.710145 |            0.5      |   0.415254 | 0.830508 | 0        |  0.5      |          49 |          20 |
|                55 | logistic_regression |   0.753623 |            0.708163 |   0.705054 | 0.824742 | 0.585366 |  0.738776 |          49 |          20 |
|                55 | random_forest       |   0.782609 |            0.669388 |   0.687971 | 0.859813 | 0.516129 |  0.867857 |          49 |          20 |
|                65 | majority_baseline   |   0.723077 |            0.5      |   0.419643 | 0.839286 | 0        |  0.5      |          47 |          18 |
|                65 | logistic_regression |   0.8      |            0.776005 |   0.761905 | 0.857143 | 0.666667 |  0.801418 |          47 |          18 |
|                65 | random_forest       |   0.815385 |            0.718085 |   0.74     | 0.88     | 0.6      |  0.921986 |          47 |          18 |

## Confusion matrices

|   horizon_seconds | model_name          | true_label   | predicted_label   |   count |
|------------------:|:--------------------|:-------------|:------------------|--------:|
|                15 | majority_baseline   | A            | A                 |      72 |
|                15 | majority_baseline   | A            | B                 |       0 |
|                15 | majority_baseline   | B            | A                 |      26 |
|                15 | majority_baseline   | B            | B                 |       0 |
|                15 | logistic_regression | A            | A                 |      55 |
|                15 | logistic_regression | A            | B                 |      17 |
|                15 | logistic_regression | B            | A                 |      11 |
|                15 | logistic_regression | B            | B                 |      15 |
|                15 | random_forest       | A            | A                 |      66 |
|                15 | random_forest       | A            | B                 |       6 |
|                15 | random_forest       | B            | A                 |      16 |
|                15 | random_forest       | B            | B                 |      10 |
|                25 | majority_baseline   | A            | A                 |      72 |
|                25 | majority_baseline   | A            | B                 |       0 |
|                25 | majority_baseline   | B            | A                 |      26 |
|                25 | majority_baseline   | B            | B                 |       0 |
|                25 | logistic_regression | A            | A                 |      56 |
|                25 | logistic_regression | A            | B                 |      16 |
|                25 | logistic_regression | B            | A                 |      16 |
|                25 | logistic_regression | B            | B                 |      10 |
|                25 | random_forest       | A            | A                 |      68 |
|                25 | random_forest       | A            | B                 |       4 |
|                25 | random_forest       | B            | A                 |      19 |
|                25 | random_forest       | B            | B                 |       7 |
|                35 | majority_baseline   | A            | A                 |      64 |
|                35 | majority_baseline   | A            | B                 |       0 |
|                35 | majority_baseline   | B            | A                 |      25 |
|                35 | majority_baseline   | B            | B                 |       0 |
|                35 | logistic_regression | A            | A                 |      44 |
|                35 | logistic_regression | A            | B                 |      20 |
|                35 | logistic_regression | B            | A                 |      14 |
|                35 | logistic_regression | B            | B                 |      11 |
|                35 | random_forest       | A            | A                 |      58 |
|                35 | random_forest       | A            | B                 |       6 |
|                35 | random_forest       | B            | A                 |      19 |
|                35 | random_forest       | B            | B                 |       6 |
|                45 | majority_baseline   | A            | A                 |      59 |
|                45 | majority_baseline   | A            | B                 |       0 |
|                45 | majority_baseline   | B            | A                 |      20 |
|                45 | majority_baseline   | B            | B                 |       0 |
|                45 | logistic_regression | A            | A                 |      35 |
|                45 | logistic_regression | A            | B                 |      24 |
|                45 | logistic_regression | B            | A                 |       9 |
|                45 | logistic_regression | B            | B                 |      11 |
|                45 | random_forest       | A            | A                 |      55 |
|                45 | random_forest       | A            | B                 |       4 |
|                45 | random_forest       | B            | A                 |      16 |
|                45 | random_forest       | B            | B                 |       4 |
|                55 | majority_baseline   | A            | A                 |      49 |
|                55 | majority_baseline   | A            | B                 |       0 |
|                55 | majority_baseline   | B            | A                 |      20 |
|                55 | majority_baseline   | B            | B                 |       0 |
|                55 | logistic_regression | A            | A                 |      40 |
|                55 | logistic_regression | A            | B                 |       9 |
|                55 | logistic_regression | B            | A                 |       8 |
|                55 | logistic_regression | B            | B                 |      12 |
|                55 | random_forest       | A            | A                 |      46 |
|                55 | random_forest       | A            | B                 |       3 |
|                55 | random_forest       | B            | A                 |      12 |
|                55 | random_forest       | B            | B                 |       8 |
|                65 | majority_baseline   | A            | A                 |      47 |
|                65 | majority_baseline   | A            | B                 |       0 |
|                65 | majority_baseline   | B            | A                 |      18 |
|                65 | majority_baseline   | B            | B                 |       0 |
|                65 | logistic_regression | A            | A                 |      39 |
|                65 | logistic_regression | A            | B                 |       8 |
|                65 | logistic_regression | B            | A                 |       5 |
|                65 | logistic_regression | B            | B                 |      13 |
|                65 | random_forest       | A            | A                 |      44 |
|                65 | random_forest       | A            | B                 |       3 |
|                65 | random_forest       | B            | A                 |       9 |
|                65 | random_forest       | B            | B                 |       9 |

## Feature importance

|   horizon | model_name          | feature_name              | feature_group   |   importance_value |   importance_rank | direction   |
|----------:|:--------------------|:--------------------------|:----------------|-------------------:|------------------:|:------------|
|        15 | logistic_regression | time_mid_control_0_15     | region_position |          0.884562  |                 1 | B           |
|        15 | logistic_regression | team_molotovs_start       | utility         |         -0.797187  |                 2 | A           |
|        15 | logistic_regression | time_b_pressure_0_15      | region_position |          0.746247  |                 3 | B           |
|        15 | logistic_regression | is_pistol_round           | context         |         -0.67488   |                 4 | A           |
|        15 | logistic_regression | team_he_start             | utility         |          0.611712  |                 5 | B           |
|        15 | random_forest       | team_center_y_10s         | region_position |          0.0850924 |                 1 |             |
|        15 | random_forest       | time_a_pressure_0_15      | region_position |          0.0825026 |                 2 |             |
|        15 | random_forest       | team_center_x_15s         | region_position |          0.0800929 |                 3 |             |
|        15 | random_forest       | team_center_y_15s         | region_position |          0.0750545 |                 4 |             |
|        15 | random_forest       | avg_pairwise_distance_15s | region_position |          0.0588763 |                 5 |             |
|        25 | logistic_regression | team_molotovs_start       | utility         |         -0.823124  |                 1 | A           |
|        25 | logistic_regression | is_pistol_round           | context         |         -0.729986  |                 2 | A           |
|        25 | logistic_regression | players_mid_control_0_15  | region_position |         -0.619742  |                 3 | A           |
|        25 | logistic_regression | time_b_pressure_15_25     | region_position |          0.612019  |                 4 | B           |
|        25 | logistic_regression | team_he_start             | utility         |          0.568169  |                 5 | B           |
|        25 | random_forest       | time_a_pressure_0_25      | region_position |          0.0558036 |                 1 |             |
|        25 | random_forest       | team_center_y_25s         | region_position |          0.0503762 |                 2 |             |
|        25 | random_forest       | team_center_y_20s         | region_position |          0.0422899 |                 3 |             |
|        25 | random_forest       | team_center_y_10s         | region_position |          0.0390285 |                 4 |             |
|        25 | random_forest       | time_a_pressure_0_20      | region_position |          0.038091  |                 5 |             |
|        35 | logistic_regression | players_b_pressure_0_20   | region_position |         -0.783104  |                 1 | A           |
|        35 | logistic_regression | players_a_pressure_25_35  | region_position |         -0.757726  |                 2 | A           |
|        35 | logistic_regression | players_mid_control_25_35 | region_position |          0.731655  |                 3 | B           |
|        35 | logistic_regression | players_a_pressure_0_25   | region_position |          0.712961  |                 4 | B           |
|        35 | logistic_regression | team_molotovs_start       | utility         |         -0.710415  |                 5 | A           |
|        35 | random_forest       | time_a_pressure_0_35      | region_position |          0.0412427 |                 1 |             |
|        35 | random_forest       | players_a_pressure_25_35  | region_position |          0.0395022 |                 2 |             |
|        35 | random_forest       | time_a_pressure_0_25      | region_position |          0.0345521 |                 3 |             |
|        35 | random_forest       | time_a_pressure_25_35     | region_position |          0.0331854 |                 4 |             |
|        35 | random_forest       | time_a_pressure_0_20      | region_position |          0.0323364 |                 5 |             |
|        45 | logistic_regression | players_mid_control_0_45  | region_position |          1.18465   |                 1 | B           |
|        45 | logistic_regression | time_b_pressure_35_45     | region_position |          1.15897   |                 2 | B           |
|        45 | logistic_regression | players_a_pressure_0_25   | region_position |          0.752721  |                 3 | B           |
|        45 | logistic_regression | molotovs_used_35_45       | utility         |         -0.700666  |                 4 | A           |
|        45 | logistic_regression | team_flashes_start        | utility         |          0.617316  |                 5 | B           |
|        45 | random_forest       | time_b_pressure_35_45     | region_position |          0.0557395 |                 1 |             |
|        45 | random_forest       | time_b_pressure_0_45      | region_position |          0.0422165 |                 2 |             |
|        45 | random_forest       | time_a_pressure_35_45     | region_position |          0.0324743 |                 3 |             |
|        45 | random_forest       | time_mid_control_0_45     | region_position |          0.029167  |                 4 |             |
|        45 | random_forest       | time_a_pressure_0_45      | region_position |          0.0261384 |                 5 |             |
|        55 | logistic_regression | time_b_pressure_45_55     | region_position |          0.859246  |                 1 | B           |
|        55 | logistic_regression | time_a_pressure_45_55     | region_position |         -0.836959  |                 2 | A           |
|        55 | logistic_regression | players_b_pressure_45_55  | region_position |          0.721781  |                 3 | B           |
|        55 | logistic_regression | players_mid_control_0_45  | region_position |          0.678458  |                 4 | B           |
|        55 | logistic_regression | players_a_pressure_0_25   | region_position |          0.604043  |                 5 | B           |
|        55 | random_forest       | time_b_pressure_45_55     | region_position |          0.0578705 |                 1 |             |
|        55 | random_forest       | time_b_pressure_0_55      | region_position |          0.0397037 |                 2 |             |
|        55 | random_forest       | time_b_pressure_35_45     | region_position |          0.0342745 |                 3 |             |
|        55 | random_forest       | players_b_pressure_45_55  | region_position |          0.0301428 |                 4 |             |
|        55 | random_forest       | time_mid_control_0_45     | region_position |          0.0265762 |                 5 |             |
|        65 | logistic_regression | players_b_pressure_55_65  | region_position |          0.815347  |                 1 | B           |
|        65 | logistic_regression | time_b_pressure_55_65     | region_position |          0.783892  |                 2 | B           |
|        65 | logistic_regression | time_a_pressure_55_65     | region_position |         -0.669634  |                 3 | A           |
|        65 | logistic_regression | players_a_pressure_55_65  | region_position |         -0.661284  |                 4 | A           |
|        65 | logistic_regression | is_pistol_round           | context         |         -0.626948  |                 5 | A           |
|        65 | random_forest       | players_b_pressure_55_65  | region_position |          0.0808833 |                 1 |             |
|        65 | random_forest       | time_b_pressure_55_65     | region_position |          0.0568644 |                 2 |             |
|        65 | random_forest       | time_a_pressure_0_65      | region_position |          0.035629  |                 3 |             |
|        65 | random_forest       | players_a_pressure_55_65  | region_position |          0.0349068 |                 4 |             |
|        65 | random_forest       | time_a_pressure_55_65     | region_position |          0.0329293 |                 5 |             |

## Horizon comparison

|   horizon_seconds | best_model_by_macro_f1   |   best_macro_f1 |   best_balanced_accuracy |   majority_baseline_macro_f1 |   improvement_over_majority |   selected_features | interpretation_note                                                                      |
|------------------:|:-------------------------|----------------:|-------------------------:|-----------------------------:|----------------------------:|--------------------:|:-----------------------------------------------------------------------------------------|
|                15 | random_forest            |        0.666667 |                 0.670406 |                     0.423529 |                    0.243137 |                  29 | Positive out-of-fold macro F1 difference; validate stability before drawing conclusions. |
|                25 | random_forest            |        0.616862 |                 0.606838 |                     0.423529 |                    0.193333 |                  72 | Positive out-of-fold macro F1 difference; validate stability before drawing conclusions. |
|                35 | random_forest            |        0.57351  |                 0.573125 |                     0.418301 |                    0.155209 |                  94 | Positive out-of-fold macro F1 difference; validate stability before drawing conclusions. |
|                45 | random_forest            |        0.565934 |                 0.57161  |                     0.427536 |                    0.138398 |                 116 | Positive out-of-fold macro F1 difference; validate stability before drawing conclusions. |
|                55 | logistic_regression      |        0.705054 |                 0.708163 |                     0.415254 |                    0.2898   |                 138 | Positive out-of-fold macro F1 difference; validate stability before drawing conclusions. |
|                65 | logistic_regression      |        0.761905 |                 0.776005 |                     0.419643 |                    0.342262 |                 160 | Positive out-of-fold macro F1 difference; validate stability before drawing conclusions. |

## Limitations

- Metrics are out-of-fold estimates from only the current Vitality Mirage sample.
- Plant B has lower support, so class-specific metrics can vary substantially.
- Later horizons exclude rounds planted before the cutoff, so horizon rows use different cohort sizes and are not directly causal comparisons.
- Manual review is still pending; the model remains preliminary.
- Feature importance is descriptive and does not establish causality.
- No hyperparameter tuning or external validation is performed.

## Next step

Complete manual review, inspect recurring errors, and refine leakage-safe features before considering a stronger model.
