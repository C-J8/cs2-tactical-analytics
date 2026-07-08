# Model Card -- Vitality Mirage T-side A/B Candidate Baseline

## Model identity
| candidate_id                                     | target_team   | target_map   |   candidate_horizon_seconds | candidate_feature_set   | candidate_model_name   | selection_mode   | selection_reason                                                | source_stage                                                  | source_table       | selected_at                      | status   |
|:-------------------------------------------------|:--------------|:-------------|----------------------------:|:------------------------|:-----------------------|:-----------------|:----------------------------------------------------------------|:--------------------------------------------------------------|:-------------------|:---------------------------------|:---------|
| vitality_mirage_t_ab_35s_stable_only_logistic_v1 | Vitality      | Mirage       |                          35 | stable_only             | logistic_regression    | explicit         | Explicit default/current candidate requested by CLI parameters. | Stage 6.2 -- Focused T-side A/B Feature Refinement Experiment | ab_refined_metrics | 2026-07-08T20:57:56.033963+00:00 | selected |

## Intended use
Predict A/B only for high-confidence planted T-side rounds in the current MVP scope.

## Not intended use
This is not a final model, production deployment, causal explanation, CT-side model, or no-plant model.

## Data
| candidate_id                                     |   selected_prediction_rows |   selected_error_rows |   selected_feature_count | status   |
|:-------------------------------------------------|---------------------------:|----------------------:|-------------------------:|:---------|
| vitality_mirage_t_ab_35s_stable_only_logistic_v1 |                         89 |                    25 |                       31 | warning  |

## Target definition
The target is the observed target-team plant site. No-plant rounds are excluded.

## Candidate configuration
|   candidate_horizon_seconds | candidate_feature_set   | candidate_model_name   | selection_mode   | selection_reason                                                |
|----------------------------:|:------------------------|:-----------------------|:-----------------|:----------------------------------------------------------------|
|                          35 | stable_only             | logistic_regression    | explicit         | Explicit default/current candidate requested by CLI parameters. |

## Features
|   horizon_seconds | feature_set_name   |   total_selected_features |   numeric_features |   categorical_features | notes                                                               |
|------------------:|:-------------------|--------------------------:|-------------------:|-----------------------:|:--------------------------------------------------------------------|
|                35 | stable_only        |                        31 |                 31 |                      0 | Stable/model-specific candidates with baseline-importance fallback. |

## Leakage controls
Feature catalog exclusions, manual leakage-name blocks, identifier removal, horizon filtering, and pre-plant row filtering are preserved from Stage 6.

## Evaluation method
Metrics are out-of-fold stratified cross-validation estimates from the existing Stage 6.2 experiment.

## Metrics
|   accuracy |   balanced_accuracy |   macro_f1 |     f1_A |     f1_B |   recall_A |   recall_B |   support_A |   support_B |   total_errors |   B_predicted_as_A |
|-----------:|--------------------:|-----------:|---------:|---------:|-----------:|-----------:|------------:|------------:|---------------:|-------------------:|
|   0.719101 |            0.682813 |   0.671101 | 0.796748 | 0.545455 |   0.765625 |        0.6 |          64 |          25 |             25 |                 10 |

## Comparison against Stage 6 baseline
|   refined_macro_f1 |   baseline_macro_f1 |   delta_macro_f1 |   refined_recall_B |   baseline_recall_B |   delta_recall_B |   delta_B_predicted_as_A | comparison_status   |
|-------------------:|--------------------:|-----------------:|-------------------:|--------------------:|-----------------:|-------------------------:|:--------------------|
|           0.671101 |            0.557084 |         0.114017 |                0.6 |                0.44 |             0.16 |                       -4 | improved            |

## Error profile
| round_feature_id                                                                                                                                                                                       | true_label   | predicted_label   |   prediction_confidence | error_type       | suggested_review_priority   |
|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-------------|:------------------|------------------------:|:-----------------|:----------------------------|
| blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_vitality_vs_falcons_m3_mirage_awpy_r1  | A            | B                 |                0.758768 | A_predicted_as_B | high                        |
| blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_vitality_vs_falcons_m3_mirage_awpy_r5  | A            | B                 |                0.592782 | A_predicted_as_B | medium                      |
| blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_vitality_vs_falcons_m3_mirage_awpy_r8  | A            | B                 |                0.900969 | A_predicted_as_B | high                        |
| blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_parivision_vs_vitality_m1_mirage_awpy_r14      | A            | B                 |                0.545311 | A_predicted_as_B | medium                      |
| blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_parivision_vs_vitality_m1_mirage_awpy_r18      | A            | B                 |                0.623177 | A_predicted_as_B | medium                      |
| blast_open_rotterdam_2026_the_mongolz_vs_vitality_bo3_7auu3ecxrnld4gicqznp8l_blast_open_rotterdam_2026_the_mongolz_vs_vitality_bo3_7auu3ecxrnld4gicqznp8l_the_mongolz_vs_vitality_m1_mirage_awpy_r14   | B            | A                 |                0.597129 | B_predicted_as_A | high                        |
| blast_rivals_2025_season_2_spirit_vs_vitality_bo3_ktwhzrlsnkwccs0u9bilr3_blast_rivals_2025_season_2_spirit_vs_vitality_bo3_ktwhzrlsnkwccs0u9bilr3_spirit_vs_vitality_m3_mirage_awpy_r15                | B            | A                 |                0.99385  | B_predicted_as_A | high                        |
| blast_rivals_2025_season_2_spirit_vs_vitality_bo3_ktwhzrlsnkwccs0u9bilr3_blast_rivals_2025_season_2_spirit_vs_vitality_bo3_ktwhzrlsnkwccs0u9bilr3_spirit_vs_vitality_m3_mirage_awpy_r25                | B            | A                 |                0.889804 | B_predicted_as_A | high                        |
| blast_rivals_2026_season_1_vitality_vs_fut_bo3_9ryfk_nffwu4txdghnjdks_blast_rivals_2026_season_1_vitality_vs_fut_bo3_9ryfk_nffwu4txdghnjdks_vitality_vs_fut_m1_mirage_awpy_r15                         | A            | B                 |                0.846991 | A_predicted_as_B | high                        |
| blast_rivals_2026_season_1_vitality_vs_g2_bo3_qfgfmj4pq03xqpia9_8d_x_blast_rivals_2026_season_1_vitality_vs_g2_bo3_qfgfmj4pq03xqpia9_8d_x_vitality_vs_g2_m1_mirage_awpy_r27                            | B            | A                 |                0.888094 | B_predicted_as_A | high                        |
| blast_rivals_2026_season_1_vitality_vs_gamerlegion_bo3_6ue9htrzonzoylj1b6cesc_blast_rivals_2026_season_1_vitality_vs_gamerlegion_bo3_6ue9htrzonzoylj1b6cesc_vitality_vs_gamerlegion_m1_mirage_awpy_r13 | B            | A                 |                0.633969 | B_predicted_as_A | high                        |
| hltv_2389666_mirage_map1_hltv_2389666_mirage_map1_furia_vs_vitality_m1_mirage_awpy_r18                                                                                                                 | A            | B                 |                0.850526 | A_predicted_as_B | high                        |

## Known limitations
- Small sample and class imbalance remain material limitations.
- Plant B has lower support.
- Validation is still round-level CV, not temporal or external validation.
- Manual review may change confidence in the candidate.
- Feature importance is descriptive and does not establish causality.

## Manual review status
| decision_status       | required_before_final_adoption                         |
|:----------------------|:-------------------------------------------------------|
| manual_review_pending | complete_manual_review|external_or_temporal_validation |

## Ethical / practical cautions
Do not treat predictions as tactical truth without reviewing demos and match context.

## Recommendation
| decision                         | main_reason                                                                      | supporting_metrics                                                                                                    |
|:---------------------------------|:---------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------|
| promote_as_exploratory_candidate | Metrics improve, but manual review is still pending, so adoption is exploratory. | macro_f1=0.671|recall_B=0.600|B_predicted_as_A=10|delta_macro_f1=0.114|delta_recall_B=0.160|delta_B_predicted_as_A=-4 |

## Next step
Complete manual review or prepare a final project report that preserves the limitations above.
