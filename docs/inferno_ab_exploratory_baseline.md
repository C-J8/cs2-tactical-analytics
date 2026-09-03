# Inferno A/B Exploratory Baseline

## Purpose
Estimate whether early-round Inferno features contain reproducible exploratory signal for Vitality T-side eventual A/B plant site.

## Why This Is Exploratory
The sample is small and validation is leave-one-series-out. The model is not promoted and is not a production artifact.

## Dataset
Rows: 40. A/B: 22/18. Groups: 5.

## Prediction Horizon
Primary horizon: 35 seconds after freeze end, chosen from the historical Mirage 35s candidate context before Inferno modeling.

## Leakage Rules
Plant, outcome, label, raw coordinate, endpoint, and post-horizon features are excluded.

## Modeling Preconditions
| check_name                                    | passed   | status   |
|:----------------------------------------------|:---------|:---------|
| feature_contract_present                      | True     | ok       |
| stage_8_9_quality_artifacts_present           | True     | ok       |
| stage_8_9_quality_gate_passed                 | True     | ok       |
| stage_8_9_1_materialization_artifacts_present | True     | ok       |
| stage_8_9_1_repair_gate_passed                | True     | ok       |
| stage_8_10_1_hardening_present                | True     | ok       |
| modeling_source_table_present                 | True     | ok       |
| grouping_valid                                | True     | ok       |
| minimum_groups_met                            | True     | ok       |
| quality_evidence_complete                     | True     | ok       |
| materialization_evidence_complete             | True     | ok       |

## Feature Evidence
| feature_name              | quality_status       | materialization_status   | approved_for_modeling   | approval_reason                |
|:--------------------------|:---------------------|:-------------------------|:------------------------|:-------------------------------|
| score_diff_before_round   | passed               | supported                | True                    | approved                       |
| team_total_utility_start  | passed               | supported                | True                    | approved                       |
| smokes_used_0_35          | passed               | supported                | True                    | approved                       |
| flashes_used_0_35         | passed               | supported                | True                    | approved                       |
| molotovs_used_0_35        | passed               | supported                | True                    | approved                       |
| he_used_0_35              | passed               | supported                | True                    | approved                       |
| team_spread_35s           | unknown_not_approved | unknown_not_approved     | False                   | not_present_in_modeling_source |
| avg_pairwise_distance_35s | unknown_not_approved | unknown_not_approved     | False                   | not_present_in_modeling_source |
| players_mid_control_0_35  | warning              | supported                | False                   | constant_or_degenerate         |
| players_a_pressure_0_35   | passed               | supported                | True                    | approved                       |
| players_b_pressure_0_35   | passed               | supported                | True                    | approved                       |

## Feature Set
| feature_name              | family              | included   | exclusion_reason               |
|:--------------------------|:--------------------|:-----------|:-------------------------------|
| score_diff_before_round   | pre_round_context   | True       |                                |
| team_total_utility_start  | utility_inventory   | True       |                                |
| smokes_used_0_35          | early_utility_usage | True       |                                |
| flashes_used_0_35         | early_utility_usage | True       |                                |
| molotovs_used_0_35        | early_utility_usage | True       |                                |
| he_used_0_35              | early_utility_usage | True       |                                |
| team_spread_35s           | team_structure      | False      | not_present_in_modeling_source |
| avg_pairwise_distance_35s | team_structure      | False      | not_present_in_modeling_source |
| players_mid_control_0_35  | semantic_control    | False      | constant_or_degenerate         |
| players_a_pressure_0_35   | semantic_control    | True       |                                |
| players_b_pressure_0_35   | semantic_control    | True       |                                |

## Validation Strategy
Leave-one-series-out validation with preprocessing fitted only inside each training fold.

## OOF Performance
Macro F1: 0.472. Balanced accuracy: 0.472. MCC: -0.055. ROC AUC: 0.487. Brier: 0.261. Log loss: 0.715.
Recall A/B: 0.500/0.444. F1 A/B: 0.512/0.432. Confusion: A->A 11, A->B 11, B->A 10, B->B 8.

## Null Permutation Test
Observed macro F1 percentile: 0.470; null median: 0.486.

## Metric Uncertainty
| metric            |   estimate |   ci_low |   ci_high |   resamples | clustered_by   | status   |
|:------------------|-----------:|---------:|----------:|------------:|:---------------|:---------|
| macro_f1          |   0.47203  | 0.401471 |  0.525    |        2000 | model_group_id | ok       |
| balanced_accuracy |   0.472222 | 0.43     |  0.532581 |        2000 | model_group_id | ok       |
| recall_A          |   0.5      | 0.318182 |  0.684211 |        2000 | model_group_id | ok       |
| recall_B          |   0.444444 | 0.332955 |  0.636364 |        2000 | model_group_id | ok       |

## Exploratory Signal Assessment
Signal status: `no_signal`. Model status: `exploratory_only`.

## Round-Level Error Analysis
OOF error rows: 21. Aggregate counts are stored in `inferno_ab_error_summary`.

## Stage 8.11.1 Integrity
Integrity status: `passed`. Unknown approved features: `False`. Frozen methodology preserved: `True`.

## Readiness
`ready_for_stage_8_12 = True`.