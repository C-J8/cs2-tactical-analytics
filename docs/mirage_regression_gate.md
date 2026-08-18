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
| round_features_mvp            |             405 |            405 | True           | True                 | True          | ok       |
| region_presence_by_round      |           43961 |          43961 | True           | True                 | True          | ok       |
| utility_events                |            2336 |           2336 | True           | True                 | True          | ok       |
| round_region_timeline         |           43961 |          43961 | True           | True                 | True          | ok       |
| round_state_resolved          |             405 |            405 | True           | True                 | True          | ok       |
| round_features_t_side_all     |             180 |            180 | True           | True                 | True          | ok       |
| round_features_t_side_planted |              98 |             98 | True           | True                 | True          | ok       |
| round_features_ct_side        |             225 |            225 | True           | True                 | True          | ok       |
| feature_contract              |             492 |            492 | True           | True                 | True          | ok       |
| map_registry                  |               1 |              1 | True           | True                 | True          | ok       |
| map_feature_semantic_coverage |             308 |            308 | True           | True                 | True          | ok       |
| candidate_model_selection     |               1 |              1 | True           | True                 | True          | ok       |
| candidate_model_feature_set   |              32 |             32 | True           | True                 | True          | ok       |
| candidate_model_metrics       |               1 |              1 | True           | True                 | True          | ok       |

## Feature schema compatibility
_No rows._

## Feature value compatibility
_No rows._

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
_No rows._

## Regression decision
overall_status: `passed`

## New-map readiness
ready_for_new_map_onboarding: `true`

## Next stage
Next: Stage 8.4 -- First New Map Onboarding.
