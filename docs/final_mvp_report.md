# Final MVP Report -- CS2 Tactical Analytics

## Executive summary
| scope                                                    | candidate_id                                     | candidate_decision               | main_result                                                                                                                                               | main_limitation                                             |
|:---------------------------------------------------------|:-------------------------------------------------|:---------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------|
| Vitality T-side Mirage planted-round A/B site prediction | vitality_mirage_t_ab_35s_stable_only_logistic_v1 | promote_as_exploratory_candidate | 35s stable_only logistic_regression candidate improved macro F1 and recall_B versus the matching Stage 6 baseline while reducing B_predicted_as_A errors. | manual_review_pending; small sample; no external validation |

## Project scope
The MVP covers Vitality T-side Mirage planted-round A/B site prediction. No-plant and CT-side modeling remain out of scope.

## Data and pipeline
|   eligible_demos |   valid_full_map_demos |   feature_rounds |   t_side_rounds |   t_side_planted_rounds |   plant_A |   plant_B |   no_plant |   candidate_prediction_rows |   candidate_error_rows |   candidate_feature_count | manual_review_status   |
|-----------------:|-----------------------:|-----------------:|----------------:|------------------------:|----------:|----------:|-----------:|----------------------------:|-----------------------:|--------------------------:|:-----------------------|
|               18 |                     18 |              405 |             180 |                      98 |        72 |        26 |         82 |                          89 |                     25 |                        31 | pending                |

## T-side tactical findings
|   finding_rank | finding_category   | finding_text                                                                                                                                                          | evidence_strength   |
|---------------:|:-------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------|
|              1 | A_vs_B_region      | Candidate pattern: A_PRESSURE in interval 65-75s appears more associated with plant_A by 57.2% share difference. Requires demo review before tactical interpretation. | strong_candidate    |
|              2 | A_vs_B_region      | Candidate pattern: A_PRESSURE in interval 55-65s appears more associated with plant_A by 54.0% share difference. Requires demo review before tactical interpretation. | strong_candidate    |
|              3 | A_vs_B_region      | Candidate pattern: B_PRESSURE in interval 55-65s appears more associated with plant_B by 53.6% share difference. Requires demo review before tactical interpretation. | strong_candidate    |
|              4 | A_vs_B_region      | Candidate pattern: B_PRESSURE in interval 45-55s appears more associated with plant_B by 53.3% share difference. Requires demo review before tactical interpretation. | strong_candidate    |
|              5 | A_vs_B_region      | Candidate pattern: B_PRESSURE in interval 35-45s appears more associated with plant_B by 48.8% share difference. Requires demo review before tactical interpretation. | strong_candidate    |
|              6 | A_vs_B_region      | Candidate pattern: A_PRESSURE in interval 25-35s appears more associated with plant_A by 46.9% share difference. Requires demo review before tactical interpretation. | strong_candidate    |

## Modeling task
The model predicts target-team plant A versus plant B only for high-confidence planted T-side rounds.

## Baseline and refinement
Stage 6 established the leakage-controlled baseline. Stage 6.2 compared fixed feature sets and horizons without tuning.

## Promoted candidate
| candidate_id                                     |   horizon_seconds | feature_set_name   | model_name          | decision                         | decision_status       |
|:-------------------------------------------------|------------------:|:-------------------|:--------------------|:---------------------------------|:----------------------|
| vitality_mirage_t_ab_35s_stable_only_logistic_v1 |                35 | stable_only        | logistic_regression | promote_as_exploratory_candidate | manual_review_pending |

## Candidate performance
|   macro_f1 |   balanced_accuracy |   recall_A |   recall_B |   support_A |   support_B |   delta_macro_f1_vs_baseline |   delta_recall_B_vs_baseline |   delta_B_predicted_as_A_vs_baseline |
|-----------:|--------------------:|-----------:|-----------:|------------:|------------:|-----------------------------:|-----------------------------:|-------------------------------------:|
|   0.671101 |            0.682813 |   0.765625 |        0.6 |          64 |          25 |                     0.114017 |                         0.16 |                                   -4 |

## Error profile
| candidate_id                                     |   total_errors |   A_predicted_as_B |   B_predicted_as_A |   high_confidence_errors |   high_confidence_B_predicted_as_A | top_error_priority   | error_interpretation                                                             | recommended_review_action                                              |
|:-------------------------------------------------|---------------:|-------------------:|-------------------:|-------------------------:|-----------------------------------:|:---------------------|:---------------------------------------------------------------------------------|:-----------------------------------------------------------------------|
| vitality_mirage_t_ab_35s_stable_only_logistic_v1 |             25 |                 15 |                 10 |                       13 |                                  4 | high                 | Errors are mixed across A and B directions; review high-confidence misses first. | Prioritize B_predicted_as_A and high-confidence errors in demo review. |

## Feature summary
| artifact_name    | artifact_path                                      | description                     |
|:-----------------|:---------------------------------------------------|:--------------------------------|
| candidate_config | configs/modeling/t_side_ab_candidate_baseline.yaml | Frozen candidate configuration. |

## Limitations
| limitation_id                 | impact                               | mitigation_or_next_step          | severity   |
|:------------------------------|:-------------------------------------|:---------------------------------|:-----------|
| small_sample                  | Metrics can vary materially.         | Add more demos.                  | high       |
| class_B_lower_support         | B metrics are less stable.           | Collect more B examples.         | high       |
| manual_review_pending         | Candidate remains exploratory.       | Complete review template.        | high       |
| round_level_cv_only           | May overstate generalization.        | Try temporal or series split.    | medium     |
| no_external_validation        | Generalization is unknown.           | Hold out future matches.         | high       |
| no_plant_out_of_scope         | Model covers only planted rounds.    | Treat no-plant as separate task. | medium     |
| ct_side_out_of_scope          | Defensive insights remain separate.  | Plan CT-side stage later.        | medium     |
| no_causal_claims              | Avoid tactical overclaiming.         | Use demo review and experiments. | high       |
| demo_parse_dependency         | Parser gaps can affect features.     | Keep quality gate and audits.    | medium     |
| feature_interpretation_limits | Coefficients are not tactical truth. | Use examples and review context. | medium     |

## Decision
The current candidate decision is `promote_as_exploratory_candidate`. It remains exploratory while manual review is pending.

## Recommended next steps
|   step_rank | next_step                          | purpose                                               | priority   |
|------------:|:-----------------------------------|:------------------------------------------------------|:-----------|
|           1 | complete_manual_review             | Validate findings and candidate errors against demos. | high       |
|           2 | inspect_candidate_errors           | Understand remaining B_predicted_as_A misses.         | high       |
|           3 | freeze_report_examples             | Pick clear examples for presentation.                 | medium     |
|           4 | consider_temporal_or_series_split  | Test generalization more honestly.                    | high       |
|           5 | expand_maps_or_teams               | Check whether patterns hold beyond Mirage/Vitality.   | medium     |
|           6 | evaluate_no_plant_as_separate_task | Model failed attacks without forcing A/B labels.      | medium     |
|           7 | prepare_final_presentation         | Turn the report pack into a concise story.            | medium     |
