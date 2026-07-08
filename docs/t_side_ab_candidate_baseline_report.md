# T-side A/B Candidate Baseline Report -- Vitality Mirage

## Executive summary
| decision                         | decision_status       | main_reason                                                                      |
|:---------------------------------|:----------------------|:---------------------------------------------------------------------------------|
| promote_as_exploratory_candidate | manual_review_pending | Metrics improve, but manual review is still pending, so adoption is exploratory. |

## Selected candidate
| candidate_id                                     |   candidate_horizon_seconds | candidate_feature_set   | candidate_model_name   |
|:-------------------------------------------------|----------------------------:|:------------------------|:-----------------------|
| vitality_mirage_t_ab_35s_stable_only_logistic_v1 |                          35 | stable_only             | logistic_regression    |

## Why this candidate
| selection_reason                                                |
|:----------------------------------------------------------------|
| Explicit default/current candidate requested by CLI parameters. |

## Metrics
|   macro_f1 |   recall_B |   precision_B |   support_A |   support_B |   total_errors |   B_predicted_as_A |
|-----------:|-----------:|--------------:|------------:|------------:|---------------:|-------------------:|
|   0.671101 |        0.6 |           0.5 |          64 |          25 |             25 |                 10 |

## Confusion matrix
| true_label   | predicted_label   |   count |   share_of_true_label |
|:-------------|:------------------|--------:|----------------------:|
| A            | A                 |      49 |              0.765625 |
| A            | B                 |      15 |              0.234375 |
| B            | A                 |      10 |              0.4      |
| B            | B                 |      15 |              0.6      |

## Error profile
| true_label   | predicted_label   | error_type       |   prediction_confidence | suggested_review_priority   |
|:-------------|:------------------|:-----------------|------------------------:|:----------------------------|
| A            | B                 | A_predicted_as_B |                0.758768 | high                        |
| A            | B                 | A_predicted_as_B |                0.592782 | medium                      |
| A            | B                 | A_predicted_as_B |                0.900969 | high                        |
| A            | B                 | A_predicted_as_B |                0.545311 | medium                      |
| A            | B                 | A_predicted_as_B |                0.623177 | medium                      |
| B            | A                 | B_predicted_as_A |                0.597129 | high                        |
| B            | A                 | B_predicted_as_A |                0.99385  | high                        |
| B            | A                 | B_predicted_as_A |                0.889804 | high                        |
| A            | B                 | A_predicted_as_B |                0.846991 | high                        |
| B            | A                 | B_predicted_as_A |                0.888094 | high                        |
| B            | A                 | B_predicted_as_A |                0.633969 | high                        |
| A            | B                 | A_predicted_as_B |                0.850526 | high                        |

## Feature set
|   total_selected_features |   numeric_features |   categorical_features |   rows_excluded_plant_before_horizon | notes                                                               |
|--------------------------:|-------------------:|-----------------------:|-------------------------------------:|:--------------------------------------------------------------------|
|                        31 |                 31 |                      0 |                                    9 | Stable/model-specific candidates with baseline-importance fallback. |

## Top features
| feature_name             | feature_group   |   importance_value |   importance_rank | direction   |
|:-------------------------|:----------------|-------------------:|------------------:|:------------|
| players_a_pressure_25_35 | region_position |          -1.17873  |                 1 | A           |
| players_a_pressure_0_25  | region_position |           0.910852 |                 2 | B           |
| round_num                | context         |          -0.564566 |                 3 | A           |
| time_b_pressure_0_25     | region_position |           0.471633 |                 4 | B           |
| players_alive_10s        | region_position |           0.439929 |                 5 | B           |
| players_alive_15s        | region_position |          -0.394889 |                 6 | A           |
| team_center_x_20s        | region_position |           0.392085 |                 7 | B           |
| time_a_pressure_15_25    | region_position |          -0.38574  |                 8 | A           |
| is_pistol_round          | context         |          -0.381616 |                 9 | A           |
| half                     | context         |           0.362441 |                10 | B           |

## Comparison vs previous baseline
|   delta_macro_f1 |   delta_recall_B |   delta_B_predicted_as_A | comparison_status   |
|-----------------:|-----------------:|-------------------------:|:--------------------|
|         0.114017 |             0.16 |                       -4 | improved            |

## Decision
| decision                         | required_before_final_adoption                         | recommended_next_step                                                    |
|:---------------------------------|:-------------------------------------------------------|:-------------------------------------------------------------------------|
| promote_as_exploratory_candidate | complete_manual_review|external_or_temporal_validation | Complete manual review or prepare final project report with limitations. |

## Limitations
Small sample, lower B support, pending manual review, no external validation, and no causal claims.

## Next step
Complete manual review or prepare final project report.
