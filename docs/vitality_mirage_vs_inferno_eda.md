# Vitality Multi-Map Tactical EDA -- Mirage vs Inferno

## Purpose
Compare Vitality T-side tactical behavior across Mirage, Inferno using only technically eligible cross-map features.

## Data Readiness
| audit_id                  | target_team   | maps_requested   | maps_analyzed   | demos_by_map                 | rounds_by_map                  | t_rounds_by_map                |   features_evaluated |   direct_comparable_features |   semantic_comparable_features |   excluded_normalized_features |   excluded_map_specific_features |   excluded_unsupported_features |   excluded_structural_review_features | plant_cohorts_valid   | demo_aware_bootstrap_completed   |   late_window_exposure_checks |   finding_candidates |   ranked_findings |   tentative_findings |   excluded_findings |   critical_failures |   warnings | core_gold_unchanged   | modeling_readiness_level   | ready_for_stage_8_11   | status   | created_at                       |
|:--------------------------|:--------------|:-----------------|:----------------|:-----------------------------|:-------------------------------|:-------------------------------|---------------------:|-----------------------------:|-------------------------------:|-------------------------------:|---------------------------------:|--------------------------------:|--------------------------------------:|:----------------------|:---------------------------------|------------------------------:|---------------------:|------------------:|---------------------:|--------------------:|--------------------:|-----------:|:----------------------|:---------------------------|:-----------------------|:---------|:---------------------------------|
| multi_map_tactical_eda_v1 | Vitality      | Mirage,Inferno   | mirage,inferno  | {"mirage": 17, "inferno": 5} | {"mirage": 180, "inferno": 65} | {"mirage": 180, "inferno": 65} |                  475 |                          144 |                            132 |                              0 |                                0 |                             132 |                                    44 | True                  | True                             |                           836 |                 2760 |                25 |                  629 |                 199 |                   0 |          0 | True                  | exploratory_only           | True                   | passed   | 2026-08-21T19:21:45.723994+00:00 |

## Scope
| map_id   | map_name   | target_team   |   feature_eligible_demos |   rounds |   t_rounds |   ct_rounds |   planted_t_rounds |   no_plant_t_rounds |   a_plants |   b_plants |   unique_opponents | first_series_date   | last_series_date   | quality_gate_status         | modeling_readiness_level   | status   |
|:---------|:-----------|:--------------|-------------------------:|---------:|-----------:|------------:|-------------------:|--------------------:|-----------:|-----------:|-------------------:|:--------------------|:-------------------|:----------------------------|:---------------------------|:---------|
| mirage   | Mirage     | Vitality      |                       17 |      180 |        180 |         225 |                 98 |                  82 |         72 |         26 |                 10 |                     |                    | reference_or_not_applicable | nan                        | ok       |
| inferno  | Inferno    | Vitality      |                        5 |       65 |         65 |          57 |                 40 |                  25 |         22 |         18 |                  4 |                     |                    | passed                      | exploratory_only           | ok       |

## Feature Eligibility
| feature_name               | feature_family   | cross_map_comparison_mode   | eligible_for_ranked_findings   |   exclusion_reason |
|:---------------------------|:-----------------|:----------------------------|:-------------------------------|-------------------:|
| avg_pairwise_distance_10s  | region_position  | direct                      | True                           |                nan |
| avg_pairwise_distance_115s | region_position  | direct                      | True                           |                nan |
| avg_pairwise_distance_15s  | region_position  | direct                      | True                           |                nan |
| avg_pairwise_distance_20s  | region_position  | direct                      | True                           |                nan |
| avg_pairwise_distance_25s  | region_position  | direct                      | True                           |                nan |
| first_molotov_time         | utility          | direct                      | True                           |                nan |
| first_smoke_time           | utility          | direct                      | True                           |                nan |
| first_utility_time         | utility          | direct                      | True                           |                nan |
| flashes_used_0_105         | utility          | direct                      | True                           |                nan |
| flashes_used_0_115         | utility          | direct                      | True                           |                nan |
| flashes_used_0_15          | utility          | direct                      | True                           |                nan |
| flashes_used_0_20          | utility          | direct                      | True                           |                nan |
| flashes_used_0_25          | utility          | direct                      | True                           |                nan |
| flashes_used_0_35          | utility          | direct                      | True                           |                nan |
| flashes_used_0_45          | utility          | direct                      | True                           |                nan |
| flashes_used_0_55          | utility          | direct                      | True                           |                nan |
| flashes_used_0_65          | utility          | direct                      | True                           |                nan |
| flashes_used_0_75          | utility          | direct                      | True                           |                nan |
| flashes_used_0_85          | utility          | direct                      | True                           |                nan |
| flashes_used_0_95          | utility          | direct                      | True                           |                nan |
| flashes_used_105_115       | utility          | direct                      | True                           |                nan |
| flashes_used_15_25         | utility          | direct                      | True                           |                nan |
| flashes_used_25_35         | utility          | direct                      | True                           |                nan |
| flashes_used_35_45         | utility          | direct                      | True                           |                nan |
| flashes_used_45_55         | utility          | direct                      | True                           |                nan |
| flashes_used_55_65         | utility          | direct                      | True                           |                nan |
| flashes_used_65_75         | utility          | direct                      | True                           |                nan |
| flashes_used_75_85         | utility          | direct                      | True                           |                nan |
| flashes_used_85_95         | utility          | direct                      | True                           |                nan |
| flashes_used_95_105        | utility          | direct                      | True                           |                nan |

## Analysis Method
The analysis uses descriptive effect sizes, cluster bootstrap by demo/parse_id, demo-direction agreement, and explicit caveats. It does not use p-value-only ranking or causal language.

## T-Side Overview
| map_id   | map_name   |   rounds |   demos |   opponents |   plant_rate |   a_plant_rate |   b_plant_rate |   no_target_plant_rate |   median_round_duration |   win_rate |   median_score_diff_before_round |   team_smokes_start_mean |   team_smokes_start_median |   team_flashes_start_mean |   team_flashes_start_median |   team_molotovs_start_mean |   team_molotovs_start_median |   team_he_start_mean |   team_he_start_median |   team_decoys_start_mean |   team_decoys_start_median |   team_total_utility_start_mean |   team_total_utility_start_median |
|:---------|:-----------|---------:|--------:|------------:|-------------:|---------------:|---------------:|-----------------------:|------------------------:|-----------:|---------------------------------:|-------------------------:|---------------------------:|--------------------------:|----------------------------:|---------------------------:|-----------------------------:|---------------------:|-----------------------:|-------------------------:|---------------------------:|--------------------------------:|----------------------------------:|
| inferno  | Inferno    |       65 |       5 |           4 |     0.615385 |       0.338462 |       0.276923 |               0.384615 |                 135     |   0.523077 |                                1 |                  4.15385 |                          5 |                   5.01538 |                           5 |                    3.69231 |                            5 |              2.47692 |                      3 |               0          |                          0 |                         15.3385 |                                18 |
| mirage   | Mirage     |      180 |      17 |          10 |     0.544444 |       0.4      |       0.144444 |               0.455556 |                 124.969 |   0.472222 |                                1 |                  2.65    |                          3 |                   5.51667 |                           6 |                    2.90556 |                            3 |              1.31667 |                      1 |               0.00555556 |                          0 |                         12.3944 |                                14 |

## Plant Site Distribution
| map_id   | map_name   |   t_rounds |   planted_t_rounds |   a_count |   b_count |   a_share |   b_share |   per_demo_a_share_median |   per_demo_b_share_median |   bootstrap_ci_low |   bootstrap_ci_high |   demo_level_variability | notes                                                                               |
|:---------|:-----------|-----------:|-------------------:|----------:|----------:|----------:|----------:|--------------------------:|--------------------------:|-------------------:|--------------------:|-------------------------:|:------------------------------------------------------------------------------------|
| inferno  | Inferno    |         65 |                 40 |        22 |        18 |  0.55     |  0.45     |                      0.5  |                      0.5  |           0.475758 |            0.7      |                 0.154408 | A/B are compared only as target plant site choice, not as equivalent site geometry. |
| mirage   | Mirage     |        180 |                 98 |        72 |        26 |  0.734694 |  0.265306 |                      0.75 |                      0.25 |           0.595506 |            0.808857 |                 0.233104 | A/B are compared only as target plant site choice, not as equivalent site geometry. |

## Utility Inventory
| feature_name        | cohort                       | map_id   |   rounds |    mean |   median |
|:--------------------|:-----------------------------|:---------|---------:|--------:|---------:|
| team_smokes_start   | t_side_all                   | inferno  |       65 | 4.15385 |      5   |
| team_smokes_start   | t_side_all                   | mirage   |      180 | 2.65    |      3   |
| team_smokes_start   | t_side_planted               | inferno  |       40 | 4.325   |      5   |
| team_smokes_start   | t_side_planted               | mirage   |       98 | 2.7551  |      3   |
| team_smokes_start   | t_side_no_valid_target_plant | inferno  |       25 | 3.88    |      5   |
| team_smokes_start   | t_side_no_valid_target_plant | mirage   |       82 | 2.52439 |      3   |
| team_smokes_start   | t_side_a_plant               | inferno  |       22 | 4.27273 |      5   |
| team_smokes_start   | t_side_a_plant               | mirage   |       72 | 2.81944 |      3   |
| team_smokes_start   | t_side_b_plant               | inferno  |       18 | 4.38889 |      5   |
| team_smokes_start   | t_side_b_plant               | mirage   |       26 | 2.57692 |      3   |
| team_flashes_start  | t_side_all                   | inferno  |       65 | 5.01538 |      5   |
| team_flashes_start  | t_side_all                   | mirage   |      180 | 5.51667 |      6   |
| team_flashes_start  | t_side_planted               | inferno  |       40 | 5.15    |      5   |
| team_flashes_start  | t_side_planted               | mirage   |       98 | 5.80612 |      6   |
| team_flashes_start  | t_side_no_valid_target_plant | inferno  |       25 | 4.8     |      5   |
| team_flashes_start  | t_side_no_valid_target_plant | mirage   |       82 | 5.17073 |      6   |
| team_flashes_start  | t_side_a_plant               | inferno  |       22 | 5.36364 |      6   |
| team_flashes_start  | t_side_a_plant               | mirage   |       72 | 5.88889 |      6.5 |
| team_flashes_start  | t_side_b_plant               | inferno  |       18 | 4.88889 |      5   |
| team_flashes_start  | t_side_b_plant               | mirage   |       26 | 5.57692 |      6   |
| team_molotovs_start | t_side_all                   | inferno  |       65 | 3.69231 |      5   |
| team_molotovs_start | t_side_all                   | mirage   |      180 | 2.90556 |      3   |
| team_molotovs_start | t_side_planted               | inferno  |       40 | 3.8     |      5   |
| team_molotovs_start | t_side_planted               | mirage   |       98 | 3.05102 |      4   |
| team_molotovs_start | t_side_no_valid_target_plant | inferno  |       25 | 3.52    |      5   |
| team_molotovs_start | t_side_no_valid_target_plant | mirage   |       82 | 2.73171 |      3   |
| team_molotovs_start | t_side_a_plant               | inferno  |       22 | 3.95455 |      5   |
| team_molotovs_start | t_side_a_plant               | mirage   |       72 | 3.22222 |      4   |
| team_molotovs_start | t_side_b_plant               | inferno  |       18 | 3.61111 |      4   |
| team_molotovs_start | t_side_b_plant               | mirage   |       26 | 2.57692 |      2   |

## Utility Timing
| feature_name       | cohort                       |   median_difference |   cliffs_delta | effect_strength   | status   |
|:-------------------|:-----------------------------|--------------------:|---------------:|:------------------|:---------|
| flashes_used_0_105 | t_side_all                   |                -1   |    -0.00794872 | negligible        | ok       |
| flashes_used_0_105 | t_side_planted               |                -1   |     0.0142857  | negligible        | ok       |
| flashes_used_0_105 | t_side_no_valid_target_plant |                 0   |    -0.00439024 | negligible        | ok       |
| flashes_used_0_105 | t_side_a_plant               |                -1   |    -0.127525   | negligible        | ok       |
| flashes_used_0_105 | t_side_b_plant               |                 0.5 |     0.168803   | small             | ok       |
| flashes_used_0_115 | t_side_all                   |                -1   |    -0.0082906  | negligible        | ok       |
| flashes_used_0_115 | t_side_planted               |                 0   |     0.0173469  | negligible        | ok       |
| flashes_used_0_115 | t_side_no_valid_target_plant |                 0   |    -0.00439024 | negligible        | ok       |
| flashes_used_0_115 | t_side_a_plant               |                 0   |    -0.0972222  | negligible        | ok       |
| flashes_used_0_115 | t_side_b_plant               |                 0.5 |     0.138889   | negligible        | ok       |
| flashes_used_0_15  | t_side_all                   |                 0   |     0.0746154  | negligible        | ok       |
| flashes_used_0_15  | t_side_planted               |                 0   |     0.151786   | small             | ok       |
| flashes_used_0_15  | t_side_no_valid_target_plant |                 0   |    -0.0419512  | negligible        | ok       |
| flashes_used_0_15  | t_side_a_plant               |                 0   |     0.040404   | negligible        | ok       |
| flashes_used_0_15  | t_side_b_plant               |                 1   |     0.294872   | small             | ok       |
| flashes_used_0_20  | t_side_all                   |                 0   |     0.0637607  | negligible        | ok       |
| flashes_used_0_20  | t_side_planted               |                 0   |     0.0859694  | negligible        | ok       |
| flashes_used_0_20  | t_side_no_valid_target_plant |                 0   |     0.0341463  | negligible        | ok       |
| flashes_used_0_20  | t_side_a_plant               |                 0   |     0.0315657  | negligible        | ok       |
| flashes_used_0_20  | t_side_b_plant               |                 0   |     0.151709   | small             | ok       |
| flashes_used_0_25  | t_side_all                   |                 1   |     0.103419   | negligible        | ok       |
| flashes_used_0_25  | t_side_planted               |                 1   |     0.180357   | small             | ok       |
| flashes_used_0_25  | t_side_no_valid_target_plant |                 1   |     0.00243902 | negligible        | ok       |
| flashes_used_0_25  | t_side_a_plant               |                 1   |     0.125631   | negligible        | ok       |
| flashes_used_0_25  | t_side_b_plant               |                 1   |     0.247863   | small             | ok       |
| flashes_used_0_35  | t_side_all                   |                 0   |     0.107692   | negligible        | ok       |
| flashes_used_0_35  | t_side_planted               |                 0   |     0.124745   | negligible        | ok       |
| flashes_used_0_35  | t_side_no_valid_target_plant |                 0   |     0.0873171  | negligible        | ok       |
| flashes_used_0_35  | t_side_a_plant               |                 0   |     0.0656566  | negligible        | ok       |
| flashes_used_0_35  | t_side_b_plant               |                 0   |     0.207265   | small             | ok       |

## Team Structure
| feature_name               | cohort                       | map_id   |     mean |   median | status   |
|:---------------------------|:-----------------------------|:---------|---------:|---------:|:---------|
| avg_pairwise_distance_10s  | t_side_all                   | inferno  |  872.838 |  871.176 | ok       |
| avg_pairwise_distance_10s  | t_side_all                   | mirage   |  930.399 |  947.424 | ok       |
| avg_pairwise_distance_10s  | t_side_planted               | inferno  |  873.394 |  868.737 | ok       |
| avg_pairwise_distance_10s  | t_side_planted               | mirage   |  933.374 |  943.936 | ok       |
| avg_pairwise_distance_10s  | t_side_no_valid_target_plant | inferno  |  871.949 |  890.094 | ok       |
| avg_pairwise_distance_10s  | t_side_no_valid_target_plant | mirage   |  926.843 |  952.5   | ok       |
| avg_pairwise_distance_10s  | t_side_a_plant               | inferno  |  871.12  |  856.804 | ok       |
| avg_pairwise_distance_10s  | t_side_a_plant               | mirage   |  951.252 |  973.808 | ok       |
| avg_pairwise_distance_10s  | t_side_b_plant               | inferno  |  876.174 |  878.027 | ok       |
| avg_pairwise_distance_10s  | t_side_b_plant               | mirage   |  883.867 |  830.024 | ok       |
| avg_pairwise_distance_115s | t_side_all                   | inferno  | 1353.12  | 1356.44  | ok       |
| avg_pairwise_distance_115s | t_side_all                   | mirage   | 1307.04  | 1296.38  | ok       |
| avg_pairwise_distance_115s | t_side_planted               | inferno  | 1420.53  | 1413.22  | ok       |
| avg_pairwise_distance_115s | t_side_planted               | mirage   | 1351.29  | 1320.61  | ok       |
| avg_pairwise_distance_115s | t_side_no_valid_target_plant | inferno  | 1245.28  | 1258.78  | ok       |
| avg_pairwise_distance_115s | t_side_no_valid_target_plant | mirage   | 1254.15  | 1225.25  | ok       |
| avg_pairwise_distance_115s | t_side_a_plant               | inferno  | 1433.48  | 1400.85  | ok       |
| avg_pairwise_distance_115s | t_side_a_plant               | mirage   | 1323.17  | 1303.94  | ok       |
| avg_pairwise_distance_115s | t_side_b_plant               | inferno  | 1404.69  | 1443.86  | ok       |
| avg_pairwise_distance_115s | t_side_b_plant               | mirage   | 1429.16  | 1354.72  | ok       |
| avg_pairwise_distance_15s  | t_side_all                   | inferno  | 1040.35  | 1046.07  | ok       |
| avg_pairwise_distance_15s  | t_side_all                   | mirage   | 1050.87  | 1058.99  | ok       |
| avg_pairwise_distance_15s  | t_side_planted               | inferno  | 1037.05  | 1014.97  | ok       |
| avg_pairwise_distance_15s  | t_side_planted               | mirage   | 1061.3   | 1042.53  | ok       |
| avg_pairwise_distance_15s  | t_side_no_valid_target_plant | inferno  | 1045.64  | 1070.71  | ok       |
| avg_pairwise_distance_15s  | t_side_no_valid_target_plant | mirage   | 1038.4   | 1065.3   | ok       |
| avg_pairwise_distance_15s  | t_side_a_plant               | inferno  | 1029.38  | 1012.57  | ok       |
| avg_pairwise_distance_15s  | t_side_a_plant               | mirage   | 1076.9   | 1099.47  | ok       |
| avg_pairwise_distance_15s  | t_side_b_plant               | inferno  | 1046.42  | 1047.92  | ok       |
| avg_pairwise_distance_15s  | t_side_b_plant               | mirage   | 1018.11  |  983.032 | ok       |

## Semantic Map Control
| feature_name             | cohort                       |   median_difference |   cliffs_delta | effect_strength   | status   |
|:-------------------------|:-----------------------------|--------------------:|---------------:|:------------------|:---------|
| players_a_pressure_0_105 | t_side_all                   |                 0   |      0.127179  | negligible        | ok       |
| players_a_pressure_0_105 | t_side_planted               |                 1   |      0.130867  | negligible        | ok       |
| players_a_pressure_0_105 | t_side_no_valid_target_plant |                 1   |      0.143902  | negligible        | ok       |
| players_a_pressure_0_105 | t_side_a_plant               |                 0   |      0.0170455 | negligible        | ok       |
| players_a_pressure_0_105 | t_side_b_plant               |                 0   |     -0.237179  | small             | ok       |
| players_a_pressure_0_115 | t_side_all                   |                 0   |      0.134786  | negligible        | ok       |
| players_a_pressure_0_115 | t_side_planted               |                 1   |      0.143622  | negligible        | ok       |
| players_a_pressure_0_115 | t_side_no_valid_target_plant |                 1   |      0.143902  | negligible        | ok       |
| players_a_pressure_0_115 | t_side_a_plant               |                 0   |      0.0290404 | negligible        | ok       |
| players_a_pressure_0_115 | t_side_b_plant               |                 0   |     -0.237179  | small             | ok       |
| players_a_pressure_0_15  | t_side_all                   |                 1   |      0.544359  | large             | ok       |
| players_a_pressure_0_15  | t_side_planted               |                 1   |      0.632398  | large             | ok       |
| players_a_pressure_0_15  | t_side_no_valid_target_plant |                 1   |      0.431707  | moderate          | ok       |
| players_a_pressure_0_15  | t_side_a_plant               |                 2   |      0.757576  | large             | ok       |
| players_a_pressure_0_15  | t_side_b_plant               |                 1   |      0.284188  | small             | ok       |
| players_a_pressure_0_20  | t_side_all                   |                 1   |      0.428803  | moderate          | ok       |
| players_a_pressure_0_20  | t_side_planted               |                 1   |      0.485714  | large             | ok       |
| players_a_pressure_0_20  | t_side_no_valid_target_plant |                 1   |      0.36439   | moderate          | ok       |
| players_a_pressure_0_20  | t_side_a_plant               |                 2   |      0.593434  | large             | ok       |
| players_a_pressure_0_20  | t_side_b_plant               |                 0.5 |      0.106838  | negligible        | ok       |
| players_a_pressure_0_25  | t_side_all                   |                 0   |      0.341197  | moderate          | ok       |
| players_a_pressure_0_25  | t_side_planted               |                 0   |      0.416071  | moderate          | ok       |
| players_a_pressure_0_25  | t_side_no_valid_target_plant |                 0   |      0.245854  | small             | ok       |
| players_a_pressure_0_25  | t_side_a_plant               |                 1   |      0.526515  | large             | ok       |
| players_a_pressure_0_25  | t_side_b_plant               |                 0   |      0.034188  | negligible        | ok       |
| players_a_pressure_0_35  | t_side_all                   |                 0   |      0.262051  | small             | ok       |
| players_a_pressure_0_35  | t_side_planted               |                 0   |      0.32602   | small             | ok       |
| players_a_pressure_0_35  | t_side_no_valid_target_plant |                 0   |      0.18878   | small             | ok       |
| players_a_pressure_0_35  | t_side_a_plant               |                 1   |      0.453283  | moderate          | ok       |
| players_a_pressure_0_35  | t_side_b_plant               |                 0   |     -0.145299  | negligible        | ok       |

## A Pressure
| map_id   | feature_name                 | window_type   |   window_start |   window_end |   mean |   median |   exposure_share | exposure_status   |
|:---------|:-----------------------------|:--------------|---------------:|-------------:|-------:|---------:|-----------------:|:------------------|
| inferno  | molotovs_to_a_pressure_0_105 | cumulative    |              0 |          105 |      0 |        0 |         0.553846 | ok                |
| mirage   | molotovs_to_a_pressure_0_105 | cumulative    |              0 |          105 |      0 |        0 |         0.338889 | ok                |
| inferno  | molotovs_to_a_pressure_0_115 | cumulative    |              0 |          115 |      0 |        0 |         0.415385 | ok                |
| mirage   | molotovs_to_a_pressure_0_115 | cumulative    |              0 |          115 |      0 |        0 |         0.244444 | ok                |
| inferno  | molotovs_to_a_pressure_0_15  | cumulative    |              0 |           15 |      0 |        0 |         1        | ok                |
| mirage   | molotovs_to_a_pressure_0_15  | cumulative    |              0 |           15 |      0 |        0 |         1        | ok                |
| inferno  | molotovs_to_a_pressure_0_20  | cumulative    |              0 |           20 |      0 |        0 |         1        | ok                |
| mirage   | molotovs_to_a_pressure_0_20  | cumulative    |              0 |           20 |      0 |        0 |         0.994444 | ok                |
| inferno  | molotovs_to_a_pressure_0_25  | cumulative    |              0 |           25 |      0 |        0 |         1        | ok                |
| mirage   | molotovs_to_a_pressure_0_25  | cumulative    |              0 |           25 |      0 |        0 |         0.994444 | ok                |
| inferno  | molotovs_to_a_pressure_0_35  | cumulative    |              0 |           35 |      0 |        0 |         0.984615 | ok                |
| mirage   | molotovs_to_a_pressure_0_35  | cumulative    |              0 |           35 |      0 |        0 |         0.983333 | ok                |
| inferno  | molotovs_to_a_pressure_0_45  | cumulative    |              0 |           45 |      0 |        0 |         0.953846 | ok                |
| mirage   | molotovs_to_a_pressure_0_45  | cumulative    |              0 |           45 |      0 |        0 |         0.927778 | ok                |
| inferno  | molotovs_to_a_pressure_0_55  | cumulative    |              0 |           55 |      0 |        0 |         0.907692 | ok                |
| mirage   | molotovs_to_a_pressure_0_55  | cumulative    |              0 |           55 |      0 |        0 |         0.85     | ok                |
| inferno  | molotovs_to_a_pressure_0_65  | cumulative    |              0 |           65 |      0 |        0 |         0.907692 | ok                |
| mirage   | molotovs_to_a_pressure_0_65  | cumulative    |              0 |           65 |      0 |        0 |         0.788889 | ok                |
| inferno  | molotovs_to_a_pressure_0_75  | cumulative    |              0 |           75 |      0 |        0 |         0.846154 | ok                |
| mirage   | molotovs_to_a_pressure_0_75  | cumulative    |              0 |           75 |      0 |        0 |         0.666667 | ok                |

## B Pressure
| map_id   | feature_name                 | window_type   |   window_start |   window_end |   mean |   median |   exposure_share | exposure_status   |
|:---------|:-----------------------------|:--------------|---------------:|-------------:|-------:|---------:|-----------------:|:------------------|
| inferno  | molotovs_to_b_pressure_0_105 | cumulative    |              0 |          105 |      0 |        0 |         0.553846 | ok                |
| mirage   | molotovs_to_b_pressure_0_105 | cumulative    |              0 |          105 |      0 |        0 |         0.338889 | ok                |
| inferno  | molotovs_to_b_pressure_0_115 | cumulative    |              0 |          115 |      0 |        0 |         0.415385 | ok                |
| mirage   | molotovs_to_b_pressure_0_115 | cumulative    |              0 |          115 |      0 |        0 |         0.244444 | ok                |
| inferno  | molotovs_to_b_pressure_0_15  | cumulative    |              0 |           15 |      0 |        0 |         1        | ok                |
| mirage   | molotovs_to_b_pressure_0_15  | cumulative    |              0 |           15 |      0 |        0 |         1        | ok                |
| inferno  | molotovs_to_b_pressure_0_20  | cumulative    |              0 |           20 |      0 |        0 |         1        | ok                |
| mirage   | molotovs_to_b_pressure_0_20  | cumulative    |              0 |           20 |      0 |        0 |         0.994444 | ok                |
| inferno  | molotovs_to_b_pressure_0_25  | cumulative    |              0 |           25 |      0 |        0 |         1        | ok                |
| mirage   | molotovs_to_b_pressure_0_25  | cumulative    |              0 |           25 |      0 |        0 |         0.994444 | ok                |
| inferno  | molotovs_to_b_pressure_0_35  | cumulative    |              0 |           35 |      0 |        0 |         0.984615 | ok                |
| mirage   | molotovs_to_b_pressure_0_35  | cumulative    |              0 |           35 |      0 |        0 |         0.983333 | ok                |
| inferno  | molotovs_to_b_pressure_0_45  | cumulative    |              0 |           45 |      0 |        0 |         0.953846 | ok                |
| mirage   | molotovs_to_b_pressure_0_45  | cumulative    |              0 |           45 |      0 |        0 |         0.927778 | ok                |
| inferno  | molotovs_to_b_pressure_0_55  | cumulative    |              0 |           55 |      0 |        0 |         0.907692 | ok                |
| mirage   | molotovs_to_b_pressure_0_55  | cumulative    |              0 |           55 |      0 |        0 |         0.85     | ok                |
| inferno  | molotovs_to_b_pressure_0_65  | cumulative    |              0 |           65 |      0 |        0 |         0.907692 | ok                |
| mirage   | molotovs_to_b_pressure_0_65  | cumulative    |              0 |           65 |      0 |        0 |         0.788889 | ok                |
| inferno  | molotovs_to_b_pressure_0_75  | cumulative    |              0 |           75 |      0 |        0 |         0.846154 | ok                |
| mirage   | molotovs_to_b_pressure_0_75  | cumulative    |              0 |           75 |      0 |        0 |         0.666667 | ok                |

## A vs B Within Mirage
| feature_name               |   a_n |   b_n |   difference |   cliffs_delta | effect_strength   | status   |
|:---------------------------|------:|------:|-------------:|---------------:|:------------------|:---------|
| avg_pairwise_distance_10s  |    72 |    26 |  -143.785    |    -0.227564   | small             | ok       |
| avg_pairwise_distance_115s |    72 |    26 |    50.7827   |     0.266026   | small             | ok       |
| avg_pairwise_distance_15s  |    72 |    26 |  -116.443    |    -0.228632   | small             | ok       |
| avg_pairwise_distance_20s  |    72 |    26 |  -122.051    |    -0.205128   | small             | ok       |
| avg_pairwise_distance_25s  |    72 |    26 |   -95.9103   |    -0.16453    | small             | ok       |
| first_molotov_time         |    69 |    24 |     0.15625  |     0.089372   | negligible        | ok       |
| first_smoke_time           |    72 |    26 |     0.25     |     0.0753205  | negligible        | ok       |
| first_utility_time         |    72 |    26 |    -0.101562 |    -0.110043   | negligible        | ok       |
| flashes_used_0_105         |    72 |    26 |     0.5      |     0.0592949  | negligible        | ok       |
| flashes_used_0_115         |    72 |    26 |    -0.5      |     0.0443376  | negligible        | ok       |
| flashes_used_0_15          |    72 |    26 |     0        |     0.0315171  | negligible        | ok       |
| flashes_used_0_20          |    72 |    26 |     0        |    -0.00961538 | negligible        | ok       |
| flashes_used_0_25          |    72 |    26 |     0        |     0.0560897  | negligible        | ok       |
| flashes_used_0_35          |    72 |    26 |     0        |     0.0582265  | negligible        | ok       |
| flashes_used_0_45          |    72 |    26 |     0        |     0.0705128  | negligible        | ok       |
| flashes_used_0_55          |    72 |    26 |     0        |     0.0950855  | negligible        | ok       |
| flashes_used_0_65          |    72 |    26 |     0        |     0.0544872  | negligible        | ok       |
| flashes_used_0_75          |    72 |    26 |     0        |     0.0619658  | negligible        | ok       |
| flashes_used_0_85          |    72 |    26 |     0        |     0.0512821  | negligible        | ok       |
| flashes_used_0_95          |    72 |    26 |     0.5      |     0.0758547  | negligible        | ok       |

## A vs B Within Inferno
| feature_name               |   a_n |   b_n |   difference |   cliffs_delta | effect_strength   | status   |
|:---------------------------|------:|------:|-------------:|---------------:|:------------------|:---------|
| avg_pairwise_distance_10s  |    22 |    18 |    21.2234   |     0.0555556  | negligible        | ok       |
| avg_pairwise_distance_115s |    22 |    18 |    43.0109   |    -0.0353535  | negligible        | ok       |
| avg_pairwise_distance_15s  |    22 |    18 |    35.3557   |     0.0959596  | negligible        | ok       |
| avg_pairwise_distance_20s  |    22 |    18 |    -8.9507   |     0.0555556  | negligible        | ok       |
| avg_pairwise_distance_25s  |    22 |    18 |    53.4477   |     0.00505051 | negligible        | ok       |
| first_molotov_time         |    20 |    17 |     0.132812 |     0.132353   | negligible        | ok       |
| first_smoke_time           |    21 |    18 |    -4.24219  |    -0.10582    | negligible        | ok       |
| first_utility_time         |    22 |    18 |     0.1875   |    -0.00505051 | negligible        | ok       |
| flashes_used_0_105         |    22 |    18 |    -1        |    -0.308081   | small             | ok       |
| flashes_used_0_115         |    22 |    18 |    -1        |    -0.270202   | small             | ok       |
| flashes_used_0_15          |    22 |    18 |    -1        |    -0.222222   | small             | ok       |
| flashes_used_0_20          |    22 |    18 |     0        |    -0.108586   | negligible        | ok       |
| flashes_used_0_25          |    22 |    18 |     0        |    -0.0757576  | negligible        | ok       |
| flashes_used_0_35          |    22 |    18 |     0        |    -0.0909091  | negligible        | ok       |
| flashes_used_0_45          |    22 |    18 |    -1        |    -0.179293   | small             | ok       |
| flashes_used_0_55          |    22 |    18 |    -0.5      |    -0.166667   | small             | ok       |
| flashes_used_0_65          |    22 |    18 |    -0.5      |    -0.179293   | small             | ok       |
| flashes_used_0_75          |    22 |    18 |    -1        |    -0.252525   | small             | ok       |
| flashes_used_0_85          |    22 |    18 |    -1.5      |    -0.30303    | small             | ok       |
| flashes_used_0_95          |    22 |    18 |    -1        |    -0.366162   | moderate          | ok       |

## Cross-Map Site Patterns
| feature_name               |   inferno_a_b_effect |   mirage_a_b_effect | same_direction   | effect_strength_inferno   | effect_strength_mirage   |   demo_support | status                     | notes                                                            |
|:---------------------------|---------------------:|--------------------:|:-----------------|:--------------------------|:-------------------------|---------------:|:---------------------------|:-----------------------------------------------------------------|
| avg_pairwise_distance_10s  |            21.2234   |         -143.785    | False            | negligible                | small                    |       0.5      | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| avg_pairwise_distance_115s |            43.0109   |           50.7827   | True             | negligible                | small                    |       0.7      | ok                         | Compares within-map A-vs-B effect directions, not site geometry. |
| avg_pairwise_distance_15s  |            35.3557   |         -116.443    | False            | negligible                | small                    |       0.6      | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| avg_pairwise_distance_20s  |            -8.9507   |         -122.051    | True             | negligible                | small                    |       0.6      | ok                         | Compares within-map A-vs-B effect directions, not site geometry. |
| avg_pairwise_distance_25s  |            53.4477   |          -95.9103   | False            | negligible                | small                    |       0.6      | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| first_molotov_time         |             0.132812 |            0.15625  | True             | negligible                | negligible               |       0.6      | ok                         | Compares within-map A-vs-B effect directions, not site geometry. |
| first_smoke_time           |            -4.24219  |            0.25     | False            | negligible                | negligible               |       0.612903 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| first_utility_time         |             0.1875   |           -0.101562 | False            | negligible                | negligible               |       0.612903 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_105         |            -1        |            0.5      | False            | small                     | negligible               |       0.677419 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_115         |            -1        |           -0.5      | True             | small                     | negligible               |       0.677419 | ok                         | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_15          |            -1        |            0        | False            | small                     | negligible               |       0.516129 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_20          |             0        |            0        | True             | negligible                | negligible               |       0.580645 | ok                         | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_25          |             0        |            0        | True             | negligible                | negligible               |       0.483871 | ok                         | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_35          |             0        |            0        | True             | negligible                | negligible               |       0.612903 | ok                         | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_45          |            -1        |            0        | False            | small                     | negligible               |       0.612903 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_55          |            -0.5      |            0        | False            | small                     | negligible               |       0.677419 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_65          |            -0.5      |            0        | False            | small                     | negligible               |       0.645161 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_75          |            -1        |            0        | False            | small                     | negligible               |       0.709677 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_85          |            -1.5      |            0        | False            | small                     | negligible               |       0.612903 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |
| flashes_used_0_95          |            -1        |            0.5      | False            | moderate                  | negligible               |       0.612903 | opposite_or_flat_direction | Compares within-map A-vs-B effect directions, not site geometry. |

## Planted vs No-Plant
| map_id   | feature_name               |   planted_n |   no_plant_n |   difference_no_plant_minus_planted | status   |
|:---------|:---------------------------|------------:|-------------:|------------------------------------:|:---------|
| inferno  | avg_pairwise_distance_10s  |          40 |           25 |                           21.3568   | ok       |
| inferno  | avg_pairwise_distance_115s |          40 |           25 |                         -154.437    | ok       |
| inferno  | avg_pairwise_distance_15s  |          40 |           25 |                           55.7378   | ok       |
| inferno  | avg_pairwise_distance_20s  |          40 |           25 |                           32.8315   | ok       |
| inferno  | avg_pairwise_distance_25s  |          40 |           25 |                           73.3019   | ok       |
| inferno  | first_molotov_time         |          37 |           22 |                            0.171875 | ok       |
| inferno  | first_smoke_time           |          39 |           22 |                           -4.89844  | ok       |
| inferno  | first_utility_time         |          40 |           23 |                           -0.226562 | ok       |
| inferno  | flashes_used_0_105         |          40 |           25 |                           -1        | ok       |
| inferno  | flashes_used_0_115         |          40 |           25 |                           -1        | ok       |
| inferno  | flashes_used_0_15          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_20          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_25          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_35          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_45          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_55          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_65          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_75          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_85          |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_0_95          |          40 |           25 |                           -1        | ok       |
| inferno  | flashes_used_105_115       |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_15_25         |          40 |           25 |                            1        | ok       |
| inferno  | flashes_used_25_35         |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_35_45         |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_45_55         |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_55_65         |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_65_75         |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_75_85         |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_85_95         |          40 |           25 |                            0        | ok       |
| inferno  | flashes_used_95_105        |          40 |           25 |                            0        | ok       |

## Outcome Context
| map_id   | map_name   | outcome_group   |   rounds |   win_rate |   median_round_duration | notes                                                       |
|:---------|:-----------|:----------------|---------:|-----------:|------------------------:|:------------------------------------------------------------|
| inferno  | Inferno    | t_side_all      |       65 |  0.523077  |                 135     | Outcome context is separated from tactical feature ranking. |
| inferno  | Inferno    | plant_A         |       22 |  0.818182  |                 143.219 | Outcome context is separated from tactical feature ranking. |
| inferno  | Inferno    | plant_B         |       18 |  0.777778  |                 144.461 | Outcome context is separated from tactical feature ranking. |
| inferno  | Inferno    | no_plant        |       25 |  0.08      |                 131.719 | Outcome context is separated from tactical feature ranking. |
| mirage   | Mirage     | t_side_all      |      180 |  0.472222  |                 124.969 | Outcome context is separated from tactical feature ranking. |
| mirage   | Mirage     | plant_A         |       72 |  0.777778  |                 137.039 | Outcome context is separated from tactical feature ranking. |
| mirage   | Mirage     | plant_B         |       26 |  0.846154  |                 143.883 | Outcome context is separated from tactical feature ranking. |
| mirage   | Mirage     | no_plant        |       82 |  0.0853659 |                 105.031 | Outcome context is separated from tactical feature ranking. |

## Demo-Level Stability
| map_id   | feature_name     | parse_id                                                                                                                                                                                                   |   demo_metric | supports_global_direction   | outlier_demo   |
|:---------|:-----------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------:|:----------------------------|:---------------|
| inferno  | first_smoke_time | blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_vitality_vs_falcons_m1_inferno_awpy        |     32.3977   | True                        | False          |
| inferno  | first_smoke_time | blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_parivision_vs_vitality_m2_inferno_awpy             |     30.2296   | True                        | False          |
| inferno  | first_smoke_time | hltv_2389666_mirage_map1_hltv_2389666_mirage_map1_furia_vs_vitality_m2_inferno_awpy                                                                                                                        |     26.5014   | True                        | False          |
| inferno  | first_smoke_time | iem_rio_2026_vitality_vs_g2_bo3_yhor34ca9po02urfkioto9_iem_rio_2026_vitality_vs_g2_bo3_yhor34ca9po02urfkioto9_vitality_vs_g2_m2_inferno_awpy                                                               |     30.3571   | True                        | False          |
| inferno  | first_smoke_time | pgl_cluj_napoca_2026_vitality_vs_g2_bo3_qyj9k9myd7qwvfmck2zjt5_pgl_cluj_napoca_2026_vitality_vs_g2_bo3_qyj9k9myd7qwvfmck2zjt5_vitality_vs_g2_m2_inferno_awpy                                               |     31.0638   | True                        | False          |
| mirage   | first_smoke_time | blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_vitality_vs_falcons_m3_mirage_awpy         |      7.85156  | True                        | False          |
| mirage   | first_smoke_time | blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_parivision_vs_vitality_m1_mirage_awpy              |      7.99306  | True                        | False          |
| mirage   | first_smoke_time | blast_open_rotterdam_2026_the_mongolz_vs_vitality_bo3_7auu3ecxrnld4gicqznp8l_blast_open_rotterdam_2026_the_mongolz_vs_vitality_bo3_7auu3ecxrnld4gicqznp8l_the_mongolz_vs_vitality_m1_mirage_awpy           |      6.06875  | True                        | False          |
| mirage   | first_smoke_time | blast_rivals_2025_season_2_spirit_vs_vitality_bo3_ktwhzrlsnkwccs0u9bilr3_blast_rivals_2025_season_2_spirit_vs_vitality_bo3_ktwhzrlsnkwccs0u9bilr3_spirit_vs_vitality_m3_mirage_awpy                        |      8.27284  | True                        | False          |
| mirage   | first_smoke_time | blast_rivals_2026_season_1_vitality_vs_fut_bo3_9ryfk_nffwu4txdghnjdks_blast_rivals_2026_season_1_vitality_vs_fut_bo3_9ryfk_nffwu4txdghnjdks_vitality_vs_fut_m1_mirage_awpy                                 |      6.84152  | True                        | False          |
| mirage   | first_smoke_time | blast_rivals_2026_season_1_vitality_vs_g2_bo3_qfgfmj4pq03xqpia9_8d_x_blast_rivals_2026_season_1_vitality_vs_g2_bo3_qfgfmj4pq03xqpia9_8d_x_vitality_vs_g2_m1_mirage_awpy                                    |      6.63393  | True                        | False          |
| mirage   | first_smoke_time | blast_rivals_2026_season_1_vitality_vs_gamerlegion_bo3_6ue9htrzonzoylj1b6cesc_blast_rivals_2026_season_1_vitality_vs_gamerlegion_bo3_6ue9htrzonzoylj1b6cesc_vitality_vs_gamerlegion_m1_mirage_awpy         |     13.8203   | True                        | False          |
| mirage   | first_smoke_time | hltv_2389666_mirage_map1_hltv_2389666_mirage_map1_furia_vs_vitality_m1_mirage_awpy                                                                                                                         |      7.22135  | True                        | False          |
| mirage   | first_smoke_time | iem_atlanta_2026_b8_vs_vitality_bo3_ngrbmccg2mu5ussmd_vhgx_iem_atlanta_2026_b8_vs_vitality_bo3_ngrbmccg2mu5ussmd_vhgx_b8_vs_vitality_m1_mirage_awpy                                                        |      9.40312  | True                        | False          |
| mirage   | first_smoke_time | iem_atlanta_2026_vitality_vs_bcgame_bo3_vvbtcwcwhl6039kdua2crf_iem_atlanta_2026_vitality_vs_bcgame_bo3_vvbtcwcwhl6039kdua2crf_vitality_vs_bc_game_m1_mirage_awpy                                           |     20.6641   | True                        | False          |
| mirage   | first_smoke_time | iem_rio_2026_spirit_vs_vitality_bo5_ur_lubgmexrzwqni8kfjnv_iem_rio_2026_spirit_vs_vitality_bo5_ur_lubgmexrzwqni8kfjnv_spirit_vs_vitality_m1_mirage_awpy                                                    |      7.39844  | True                        | False          |
| mirage   | first_smoke_time | iem_rio_2026_vitality_vs_falcons_bo3_o2ctrym3k5wqt8xytmqysq_iem_rio_2026_vitality_vs_falcons_bo3_o2ctrym3k5wqt8xytmqysq_vitality_vs_falcons_m1_mirage_awpy                                                 |      8.25     | True                        | False          |
| mirage   | first_smoke_time | pgl_cluj_napoca_2026_vitality_vs_g2_bo3_qyj9k9myd7qwvfmck2zjt5_pgl_cluj_napoca_2026_vitality_vs_g2_bo3_qyj9k9myd7qwvfmck2zjt5_vitality_vs_g2_m1_mirage_awpy                                                |      7.71591  | True                        | False          |
| mirage   | first_smoke_time | pgl_cluj_napoca_2026_vitality_vs_the_mongolz_bo3_hnieeahew5z1jrp1o7fbaw_pgl_cluj_napoca_2026_vitality_vs_the_mongolz_bo3_hnieeahew5z1jrp1o7fbaw_vitality_vs_the_mongolz_m1_mirage_awpy                     |      7.51989  | True                        | False          |
| mirage   | first_smoke_time | pgl_cluj_napoca_2026_vitality_vs_the_mongolz_bo3_v1_atgvjp_hiqnmb5rnmc_pgl_cluj_napoca_2026_vitality_vs_the_mongolz_bo3_v1_atgvjp_hiqnmb5rnmc_vitality_vs_the_mongolz_m1_mirage_awpy                       |      6.75893  | True                        | False          |
| mirage   | first_smoke_time | starladder_budapest_major_2025_spirit_vs_vitality_bo3_if7bxbrmdshvo9kscxua2z_starladder_budapest_major_2025_spirit_vs_vitality_bo3_if7bxbrmdshvo9kscxua2z_spirit_vs_vitality_m1_mirage_awpy                |      7.30974  | True                        | False          |
| mirage   | first_smoke_time | starladder_budapest_major_2025_vitality_vs_the_mongolz_bo3_xqowskoqxopqt1nllulf7g_starladder_budapest_major_2025_vitality_vs_the_mongolz_bo3_xqowskoqxopqt1nllulf7g_vitality_vs_the_mongolz_m1_mirage_awpy |     18.3073   | True                        | False          |
| inferno  | smokes_used_0_25 | blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_vitality_vs_falcons_m1_inferno_awpy        |      0.416667 | True                        | False          |
| inferno  | smokes_used_0_25 | blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_parivision_vs_vitality_m2_inferno_awpy             |      0.733333 | True                        | False          |
| inferno  | smokes_used_0_25 | hltv_2389666_mirage_map1_hltv_2389666_mirage_map1_furia_vs_vitality_m2_inferno_awpy                                                                                                                        |      0.5      | True                        | False          |
| inferno  | smokes_used_0_25 | iem_rio_2026_vitality_vs_g2_bo3_yhor34ca9po02urfkioto9_iem_rio_2026_vitality_vs_g2_bo3_yhor34ca9po02urfkioto9_vitality_vs_g2_m2_inferno_awpy                                                               |      0.642857 | True                        | False          |
| inferno  | smokes_used_0_25 | pgl_cluj_napoca_2026_vitality_vs_g2_bo3_qyj9k9myd7qwvfmck2zjt5_pgl_cluj_napoca_2026_vitality_vs_g2_bo3_qyj9k9myd7qwvfmck2zjt5_vitality_vs_g2_m2_inferno_awpy                                               |      0.5      | True                        | False          |
| mirage   | smokes_used_0_25 | blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_vitality_vs_falcons_m3_mirage_awpy         |      1.75     | True                        | False          |
| mirage   | smokes_used_0_25 | blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_parivision_vs_vitality_m1_mirage_awpy              |      2        | True                        | False          |
| mirage   | smokes_used_0_25 | blast_open_rotterdam_2026_the_mongolz_vs_vitality_bo3_7auu3ecxrnld4gicqznp8l_blast_open_rotterdam_2026_the_mongolz_vs_vitality_bo3_7auu3ecxrnld4gicqznp8l_the_mongolz_vs_vitality_m1_mirage_awpy           |      2.6      | True                        | False          |

## Ranked Tactical Findings
|   rank | finding_id   | category          | feature_name             | effect_strength   | evidence_quality   | finding_text_draft                                                                                               |
|-------:|:-------------|:------------------|:-------------------------|:------------------|:-------------------|:-----------------------------------------------------------------------------------------------------------------|
|      1 | mm_eda_0033  | direct_feature    | first_smoke_time         | large             | high_descriptive   | first_smoke_time is descriptively lower on the second map in this comparison; interpretation is non-causal.      |
|      2 | mm_eda_0034  | direct_feature    | first_smoke_time         | large             | high_descriptive   | first_smoke_time is descriptively lower on the second map in this comparison; interpretation is non-causal.      |
|      3 | mm_eda_0031  | direct_feature    | first_smoke_time         | large             | high_descriptive   | first_smoke_time is descriptively lower on the second map in this comparison; interpretation is non-causal.      |
|      4 | mm_eda_0032  | direct_feature    | first_smoke_time         | large             | high_descriptive   | first_smoke_time is descriptively lower on the second map in this comparison; interpretation is non-causal.      |
|      5 | mm_eda_1505  | site_pattern      | players_b_pressure_65_75 | large             | high_descriptive   | Inferno A-vs-B planted rounds differ descriptively on players_b_pressure_65_75.                                  |
|      6 | mm_eda_1487  | site_pattern      | players_b_pressure_0_105 | large             | high_descriptive   | Inferno A-vs-B planted rounds differ descriptively on players_b_pressure_0_105.                                  |
|      7 | mm_eda_1488  | site_pattern      | players_b_pressure_0_115 | large             | high_descriptive   | Inferno A-vs-B planted rounds differ descriptively on players_b_pressure_0_115.                                  |
|      8 | mm_eda_0469  | direct_feature    | smokes_used_0_25         | large             | high_descriptive   | smokes_used_0_25 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|      9 | mm_eda_0459  | direct_feature    | smokes_used_0_15         | large             | high_descriptive   | smokes_used_0_15 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     10 | mm_eda_1497  | site_pattern      | players_b_pressure_0_85  | large             | high_descriptive   | Inferno A-vs-B planted rounds differ descriptively on players_b_pressure_0_85.                                   |
|     11 | mm_eda_0467  | direct_feature    | smokes_used_0_25         | large             | high_descriptive   | smokes_used_0_25 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     12 | mm_eda_1504  | site_pattern      | players_b_pressure_55_65 | large             | high_descriptive   | Inferno A-vs-B planted rounds differ descriptively on players_b_pressure_55_65.                                  |
|     13 | mm_eda_1498  | site_pattern      | players_b_pressure_0_95  | large             | high_descriptive   | Inferno A-vs-B planted rounds differ descriptively on players_b_pressure_0_95.                                   |
|     14 | mm_eda_1062  | semantic_feature  | time_a_pressure_0_15     | large             | high_descriptive   | time_a_pressure_0_15 is descriptively higher on the second map in this comparison; interpretation is non-causal. |
|     15 | mm_eda_0457  | direct_feature    | smokes_used_0_15         | large             | high_descriptive   | smokes_used_0_15 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     16 | mm_eda_2311  | plant_progression | players_alive_115s       | large             | high_descriptive   | Inferno planted and no-target-plant rounds differ descriptively on players_alive_115s.                           |
|     17 | mm_eda_0464  | direct_feature    | smokes_used_0_20         | large             | high_descriptive   | smokes_used_0_20 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     18 | mm_eda_0470  | direct_feature    | smokes_used_0_25         | large             | high_descriptive   | smokes_used_0_25 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     19 | mm_eda_1496  | site_pattern      | players_b_pressure_0_75  | large             | high_descriptive   | Inferno A-vs-B planted rounds differ descriptively on players_b_pressure_0_75.                                   |
|     20 | mm_eda_0474  | direct_feature    | smokes_used_0_35         | large             | high_descriptive   | smokes_used_0_35 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     21 | mm_eda_0472  | direct_feature    | smokes_used_0_35         | large             | high_descriptive   | smokes_used_0_35 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     22 | mm_eda_0577  | direct_feature    | team_smokes_start        | large             | high_descriptive   | team_smokes_start is descriptively lower on the second map in this comparison; interpretation is non-causal.     |
|     23 | mm_eda_0456  | direct_feature    | smokes_used_0_15         | large             | high_descriptive   | smokes_used_0_15 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     24 | mm_eda_0489  | direct_feature    | smokes_used_0_65         | large             | high_descriptive   | smokes_used_0_65 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |
|     25 | mm_eda_0466  | direct_feature    | smokes_used_0_25         | large             | high_descriptive   | smokes_used_0_25 is descriptively higher on the second map in this comparison; interpretation is non-causal.     |

## Tentative Findings
| finding_id   | category       | feature_name               | evidence_quality   | finding_text_draft                                                                                                    |
|:-------------|:---------------|:---------------------------|:-------------------|:----------------------------------------------------------------------------------------------------------------------|
| mm_eda_0001  | direct_feature | avg_pairwise_distance_10s  | tentative          | avg_pairwise_distance_10s is descriptively higher on the second map in this comparison; interpretation is non-causal. |
| mm_eda_0002  | direct_feature | avg_pairwise_distance_10s  | tentative          | avg_pairwise_distance_10s is descriptively higher on the second map in this comparison; interpretation is non-causal. |
| mm_eda_0003  | direct_feature | avg_pairwise_distance_10s  | tentative          | avg_pairwise_distance_10s is descriptively higher on the second map in this comparison; interpretation is non-causal. |
| mm_eda_0007  | direct_feature | avg_pairwise_distance_115s | tentative          | avg_pairwise_distance_115s is descriptively lower on the second map in this comparison; interpretation is non-causal. |
| mm_eda_0014  | direct_feature | avg_pairwise_distance_15s  | tentative          | avg_pairwise_distance_15s is descriptively higher on the second map in this comparison; interpretation is non-causal. |
| mm_eda_0015  | direct_feature | avg_pairwise_distance_15s  | tentative          | avg_pairwise_distance_15s is descriptively lower on the second map in this comparison; interpretation is non-causal.  |
| mm_eda_0019  | direct_feature | avg_pairwise_distance_20s  | tentative          | avg_pairwise_distance_20s is descriptively higher on the second map in this comparison; interpretation is non-causal. |
| mm_eda_0020  | direct_feature | avg_pairwise_distance_20s  | tentative          | avg_pairwise_distance_20s is descriptively lower on the second map in this comparison; interpretation is non-causal.  |
| mm_eda_0030  | direct_feature | first_molotov_time         | tentative          | first_molotov_time is descriptively higher on the second map in this comparison; interpretation is non-causal.        |
| mm_eda_0045  | direct_feature | flashes_used_0_105         | tentative          | flashes_used_0_105 is descriptively higher on the second map in this comparison; interpretation is non-causal.        |
| mm_eda_0052  | direct_feature | flashes_used_0_15          | tentative          | flashes_used_0_15 is descriptively flat on the second map in this comparison; interpretation is non-causal.           |
| mm_eda_0055  | direct_feature | flashes_used_0_15          | tentative          | flashes_used_0_15 is descriptively higher on the second map in this comparison; interpretation is non-causal.         |
| mm_eda_0060  | direct_feature | flashes_used_0_20          | tentative          | flashes_used_0_20 is descriptively flat on the second map in this comparison; interpretation is non-causal.           |
| mm_eda_0062  | direct_feature | flashes_used_0_25          | tentative          | flashes_used_0_25 is descriptively higher on the second map in this comparison; interpretation is non-causal.         |
| mm_eda_0065  | direct_feature | flashes_used_0_25          | tentative          | flashes_used_0_25 is descriptively higher on the second map in this comparison; interpretation is non-causal.         |
| mm_eda_0070  | direct_feature | flashes_used_0_35          | tentative          | flashes_used_0_35 is descriptively flat on the second map in this comparison; interpretation is non-causal.           |
| mm_eda_0075  | direct_feature | flashes_used_0_45          | tentative          | flashes_used_0_45 is descriptively higher on the second map in this comparison; interpretation is non-causal.         |
| mm_eda_0080  | direct_feature | flashes_used_0_55          | tentative          | flashes_used_0_55 is descriptively higher on the second map in this comparison; interpretation is non-causal.         |
| mm_eda_0085  | direct_feature | flashes_used_0_65          | tentative          | flashes_used_0_65 is descriptively flat on the second map in this comparison; interpretation is non-causal.           |
| mm_eda_0090  | direct_feature | flashes_used_0_75          | tentative          | flashes_used_0_75 is descriptively higher on the second map in this comparison; interpretation is non-causal.         |
| mm_eda_0095  | direct_feature | flashes_used_0_85          | tentative          | flashes_used_0_85 is descriptively higher on the second map in this comparison; interpretation is non-causal.         |
| mm_eda_0100  | direct_feature | flashes_used_0_95          | tentative          | flashes_used_0_95 is descriptively higher on the second map in this comparison; interpretation is non-causal.         |
| mm_eda_0115  | direct_feature | flashes_used_25_35         | tentative          | flashes_used_25_35 is descriptively flat on the second map in this comparison; interpretation is non-causal.          |
| mm_eda_0120  | direct_feature | flashes_used_35_45         | tentative          | flashes_used_35_45 is descriptively flat on the second map in this comparison; interpretation is non-causal.          |
| mm_eda_0163  | direct_feature | he_used_0_105              | tentative          | he_used_0_105 is descriptively flat on the second map in this comparison; interpretation is non-causal.               |

## Excluded Features / Unsupported Comparisons
| feature_name                   | candidate_claim                                  | reason              |
|:-------------------------------|:-------------------------------------------------|:--------------------|
| molotovs_to_a_pressure_0_105   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_115   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_15    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_20    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_25    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_35    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_45    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_55    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_65    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_75    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_85    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_0_95    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_105_115 | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_15_25   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_25_35   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_35_45   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_45_55   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_55_65   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_65_75   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_75_85   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_85_95   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_a_pressure_95_105  | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_b_pressure_0_105   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_b_pressure_0_115   | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_b_pressure_0_15    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_b_pressure_0_20    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_b_pressure_0_25    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_b_pressure_0_35    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_b_pressure_0_45    | Feature excluded before tactical interpretation. | unresolved_endpoint |
| molotovs_to_b_pressure_0_55    | Feature excluded before tactical interpretation. | unresolved_endpoint |

## Structural Caveats
Mid-control structural review flags are not promoted to strong ranked findings. Utility endpoint destination features are excluded when endpoint resolution is unresolved.

## Sample Limitations
Modeling readiness is carried forward as `exploratory_only`; Stage 8.10 does not change modeling readiness levels.

## Modeling Readiness
This stage prepares descriptive EDA only. It does not train models or generate predictions.

## Next Stage
If `ready_for_stage_8_11` is true, the next stage can be an Inferno A/B exploratory baseline. Stage 8.10 does not start that work automatically.
