# Mirage Regression / Backward Compatibility Gate

## Purpose
Validate that the map-ready Mirage pipeline preserves the existing MVP behavior before onboarding a new map.

## Baseline
Baseline version: `mirage_mvp_map_ready_v1`.

## Configuration versions
Configuration files are fingerprinted in the baseline manifest.

## Datasets validated
| dataset_name                  |   rows_baseline |   rows_current | schema_match   | row_identity_match   | value_match   | status   |
|:------------------------------|----------------:|---------------:|:---------------|:---------------------|:--------------|:---------|
| feature_eligible_demos        |              18 |             18 | True           | True                 | True          | ok       |
| parse_quality                 |              23 |             23 | True           | True                 | True          | ok       |
| round_features_mvp            |             405 |            405 | False          | True                 | False         | failed   |
| region_presence_by_round      |           43961 |          43961 | True           | True                 | True          | ok       |
| utility_events                |            2336 |           4590 | False          | False                | False         | failed   |
| round_region_timeline         |           43961 |          43961 | True           | True                 | True          | ok       |
| round_state_resolved          |             405 |            405 | True           | True                 | True          | ok       |
| round_features_t_side_all     |             180 |            180 | False          | True                 | False         | failed   |
| round_features_t_side_planted |              98 |             98 | False          | True                 | False         | failed   |
| round_features_ct_side        |             225 |            225 | False          | True                 | False         | failed   |
| feature_contract              |             492 |            492 | True           | True                 | True          | ok       |
| map_registry                  |               1 |              1 | True           | True                 | True          | ok       |
| map_feature_semantic_coverage |             308 |            308 | True           | True                 | True          | ok       |
| candidate_model_selection     |               1 |              1 | True           | True                 | True          | ok       |
| candidate_model_feature_set   |              32 |             32 | True           | True                 | True          | ok       |
| candidate_model_metrics       |               1 |              1 | True           | True                 | True          | ok       |

## Feature schema compatibility
| dataset_name       | column_name             | baseline_dtype   | current_dtype   | status   |
|:-------------------|:------------------------|:-----------------|:----------------|:---------|
| round_features_mvp | flashes_used_0_20       | object           | float64         | failed   |
| round_features_mvp | he_used_0_20            | object           | float64         | failed   |
| round_features_mvp | score_diff_before_round | object           | float64         | failed   |
| round_features_mvp | flashes_used_0_15       | object           | float64         | failed   |
| round_features_mvp | he_used_0_15            | object           | float64         | failed   |
| round_features_mvp | flashes_used_15_25      | object           | float64         | failed   |
| round_features_mvp | he_used_15_25           | object           | float64         | failed   |
| round_features_mvp | flashes_used_25_35      | object           | float64         | failed   |
| round_features_mvp | he_used_25_35           | object           | float64         | failed   |
| round_features_mvp | flashes_used_35_45      | object           | float64         | failed   |
| round_features_mvp | he_used_35_45           | object           | float64         | failed   |
| round_features_mvp | flashes_used_45_55      | object           | float64         | failed   |
| round_features_mvp | he_used_45_55           | object           | float64         | failed   |
| round_features_mvp | flashes_used_55_65      | object           | float64         | failed   |
| round_features_mvp | he_used_55_65           | object           | float64         | failed   |
| round_features_mvp | flashes_used_65_75      | object           | float64         | failed   |
| round_features_mvp | he_used_65_75           | object           | float64         | failed   |
| round_features_mvp | flashes_used_75_85      | object           | float64         | failed   |
| round_features_mvp | he_used_75_85           | object           | float64         | failed   |
| round_features_mvp | flashes_used_85_95      | object           | float64         | failed   |
| round_features_mvp | he_used_85_95           | object           | float64         | failed   |
| round_features_mvp | flashes_used_95_105     | object           | float64         | failed   |
| round_features_mvp | he_used_95_105          | object           | float64         | failed   |
| round_features_mvp | flashes_used_105_115    | object           | float64         | failed   |
| round_features_mvp | he_used_105_115         | object           | float64         | failed   |
| round_features_mvp | flashes_used_0_25       | object           | float64         | failed   |
| round_features_mvp | he_used_0_25            | object           | float64         | failed   |
| round_features_mvp | flashes_used_0_35       | object           | float64         | failed   |
| round_features_mvp | he_used_0_35            | object           | float64         | failed   |
| round_features_mvp | flashes_used_0_45       | object           | float64         | failed   |

## Feature value compatibility
| feature_name         | candidate_feature   |   changed_value_count | status   |
|:---------------------|:--------------------|----------------------:|:---------|
| first_molotov_time   | False               |                   216 | failed   |
| first_smoke_time     | False               |                   223 | failed   |
| first_utility_time   | False               |                   291 | failed   |
| flashes_used_0_105   | False               |                   405 | failed   |
| flashes_used_0_115   | False               |                   405 | failed   |
| flashes_used_0_15    | False               |                   405 | failed   |
| flashes_used_0_20    | False               |                   405 | failed   |
| flashes_used_0_25    | False               |                   405 | failed   |
| flashes_used_0_35    | False               |                   405 | failed   |
| flashes_used_0_45    | False               |                   405 | failed   |
| flashes_used_0_55    | False               |                   405 | failed   |
| flashes_used_0_65    | False               |                   405 | failed   |
| flashes_used_0_75    | False               |                   405 | failed   |
| flashes_used_0_85    | False               |                   405 | failed   |
| flashes_used_0_95    | False               |                   405 | failed   |
| flashes_used_105_115 | False               |                   405 | failed   |
| flashes_used_15_25   | False               |                   405 | failed   |
| flashes_used_25_35   | False               |                   405 | failed   |
| flashes_used_35_45   | False               |                   405 | failed   |
| flashes_used_45_55   | False               |                   405 | failed   |
| flashes_used_55_65   | False               |                   405 | failed   |
| flashes_used_65_75   | False               |                   405 | failed   |
| flashes_used_75_85   | False               |                   405 | failed   |
| flashes_used_85_95   | False               |                   405 | failed   |
| flashes_used_95_105  | False               |                   405 | failed   |
| he_used_0_105        | False               |                   405 | failed   |
| he_used_0_115        | False               |                   405 | failed   |
| he_used_0_15         | False               |                   405 | failed   |
| he_used_0_20         | False               |                   405 | failed   |
| he_used_0_25         | False               |                   405 | failed   |

## Spatial / region compatibility
| dataset_name             |   rounds_compared |   players_compared |   time_rows_baseline |   time_rows_current |   region_assignment_changes |   semantic_assignment_changes |   missing_region_rows |   extra_region_rows | exact_match   | status   | notes                      |
|:-------------------------|------------------:|-------------------:|---------------------:|--------------------:|----------------------------:|------------------------------:|----------------------:|--------------------:|:--------------|:---------|:---------------------------|
| region_presence_by_round |               405 |                  0 |                43961 |               43961 |                           0 |                             0 |                     0 |                   0 | True          | ok       | Spatial outputs unchanged. |
| round_region_timeline    |               405 |                  0 |                43961 |               43961 |                           0 |                             0 |                     0 |                   0 | True          | ok       | Spatial outputs unchanged. |

## Round state compatibility
|   rounds_compared |   side_changes |   plant_label_changes |   target_team_side_changes |   bombsite_changes |   confidence_changes |   no_plant_changes | exact_match   | status   |
|------------------:|---------------:|----------------------:|---------------------------:|-------------------:|---------------------:|-------------------:|:--------------|:---------|
|               405 |              0 |                     0 |                          0 |                  0 |                    0 |                  0 | True          | ok       |

## Side dataset compatibility
| dataset_name   |   rows_baseline |   rows_current |   row_delta | round_ids_match   | feature_columns_match   | label_distribution_match   | status   | notes                   |
|:---------------|----------------:|---------------:|------------:|:------------------|:------------------------|:---------------------------|:---------|:------------------------|
| t_side_all     |             180 |            180 |           0 | True              | True                    | True                       | ok       | Side dataset unchanged. |
| t_side_planted |              98 |             98 |           0 | True              | True                    | True                       | ok       | Side dataset unchanged. |
| ct_side        |             225 |            225 |           0 | True              | True                    | True                       | ok       | Side dataset unchanged. |

## Candidate input compatibility
| candidate_id                                     |   candidate_horizon | candidate_feature_set   | candidate_model     |   expected_feature_count |   found_feature_count | missing_features   | extra_features   |   candidate_rows_baseline |   candidate_rows_current | row_identity_match   | feature_values_match   | label_match   | compatible   | status   | notes                      |
|:-------------------------------------------------|--------------------:|:------------------------|:--------------------|-------------------------:|----------------------:|:-------------------|:-----------------|--------------------------:|-------------------------:|:---------------------|:-----------------------|:--------------|:-------------|:---------|:---------------------------|
| vitality_mirage_t_ab_35s_stable_only_logistic_v1 |                  35 | stable_only             | logistic_regression |                       31 |                    31 |                    |                  |                        98 |                       98 | True                 | True                   | True          | True         | ok       | Candidate input unchanged. |

## Invariant checks
| check_id                          |   expected_value |   observed_value | passed   | severity   |
|:----------------------------------|-----------------:|-----------------:|:---------|:-----------|
| eligible_demo_count_unchanged     |               18 |               18 | True     | none       |
| feature_round_count_unchanged     |              405 |              405 | True     | none       |
| t_side_round_count_unchanged      |              180 |              180 | True     | none       |
| t_side_planted_count_unchanged    |               98 |               98 | True     | none       |
| plant_A_count_unchanged           |               72 |               72 | True     | none       |
| plant_B_count_unchanged           |               26 |               26 | True     | none       |
| no_plant_count_unchanged          |               82 |               82 | True     | none       |
| feature_column_count_unchanged    |              487 |              487 | True     | none       |
| candidate_feature_count_unchanged |               31 |               31 | True     | none       |
| candidate_rows_unchanged          |               98 |               98 | True     | none       |
| candidate_labels_unchanged        |             True |             True | True     | none       |
| region_timeline_unchanged         |             True |             True | True     | none       |
| round_state_unchanged             |             True |             True | True     | none       |
| side_datasets_unchanged           |             True |             True | True     | none       |

## Failures / warnings
| failure_id   | dataset_name       | failure_type          | column_name             | row_key   | baseline_value   | current_value   | difference   | critical   | recommended_action                                                                  |
|:-------------|:-------------------|:----------------------|:------------------------|:----------|:-----------------|:----------------|:-------------|:-----------|:------------------------------------------------------------------------------------|
| failure_1    | round_features_mvp | regression_difference | flashes_used_0_20       |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_2    | round_features_mvp | regression_difference | he_used_0_20            |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_3    | round_features_mvp | regression_difference | score_diff_before_round |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_4    | round_features_mvp | regression_difference | flashes_used_0_15       |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_5    | round_features_mvp | regression_difference | he_used_0_15            |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_6    | round_features_mvp | regression_difference | flashes_used_15_25      |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_7    | round_features_mvp | regression_difference | he_used_15_25           |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_8    | round_features_mvp | regression_difference | flashes_used_25_35      |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_9    | round_features_mvp | regression_difference | he_used_25_35           |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_10   | round_features_mvp | regression_difference | flashes_used_35_45      |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_11   | round_features_mvp | regression_difference | he_used_35_45           |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_12   | round_features_mvp | regression_difference | flashes_used_45_55      |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_13   | round_features_mvp | regression_difference | he_used_45_55           |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_14   | round_features_mvp | regression_difference | flashes_used_55_65      |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_15   | round_features_mvp | regression_difference | he_used_55_65           |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_16   | round_features_mvp | regression_difference | flashes_used_65_75      |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_17   | round_features_mvp | regression_difference | he_used_65_75           |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_18   | round_features_mvp | regression_difference | flashes_used_75_85      |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_19   | round_features_mvp | regression_difference | he_used_75_85           |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_20   | round_features_mvp | regression_difference | flashes_used_85_95      |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_21   | round_features_mvp | regression_difference | he_used_85_95           |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_22   | round_features_mvp | regression_difference | flashes_used_95_105     |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_23   | round_features_mvp | regression_difference | he_used_95_105          |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_24   | round_features_mvp | regression_difference | flashes_used_105_115    |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_25   | round_features_mvp | regression_difference | he_used_105_115         |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_26   | round_features_mvp | regression_difference | flashes_used_0_25       |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_27   | round_features_mvp | regression_difference | he_used_0_25            |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_28   | round_features_mvp | regression_difference | flashes_used_0_35       |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_29   | round_features_mvp | regression_difference | he_used_0_35            |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |
| failure_30   | round_features_mvp | regression_difference | flashes_used_0_45       |           | object           | float64         |              | True       | Inspect the upstream stage that produced this artifact before onboarding a new map. |

## Regression decision
overall_status: `failed`

## New-map readiness
ready_for_new_map_onboarding: `false`

## Next stage
Next: Stage 8.4 -- First New Map Onboarding.
