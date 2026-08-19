# Feature Contract -- CS2 Tactical Analytics

## Purpose
Freeze the current MVP feature inventory as metadata without changing existing feature values.

## Why the feature contract exists
The contract separates modeling safety, dashboard usefulness, map portability, and leakage policy before map expansion.

## Current feature inventory
| audit_id                | feature_contract_version   |   total_features |   frozen_features |   exploratory_features |   deprecated_features |   internal_features |   blocked_features |   global_features |   map_abstract_features |   map_specific_features |   unknown_map_scope |   modeling_allowed_features |   dashboard_allowed_features |   temporal_features |   mirage_specific_features |   features_requiring_map_registry |   unknown_classification_rows | missing_optional_inputs   | config_written   | report_written   | status   | created_at                       |
|:------------------------|:---------------------------|-----------------:|------------------:|-----------------------:|----------------------:|--------------------:|-------------------:|------------------:|------------------------:|------------------------:|--------------------:|----------------------------:|-----------------------------:|--------------------:|---------------------------:|----------------------------------:|------------------------------:|:--------------------------|:-----------------|:-----------------|:---------|:---------------------------------|
| feature_contract_freeze | v2                         |              492 |               471 |                      0 |                     0 |                   5 |                 16 |               184 |                     308 |                       0 |                   0 |                         471 |                          479 |                 448 |                          0 |                               308 |                            22 | none                      | True             | True             | warning  | 2026-08-18T23:03:45.341290+00:00 |

## Feature families
| group_type     | group_value     |   feature_count |   temporal_features |   modeling_features |   dashboard_features |   mirage_specific_features |   unknown_features |
|:---------------|:----------------|----------------:|--------------------:|--------------------:|---------------------:|---------------------------:|-------------------:|
| feature_family | bomb            |               2 |                   0 |                   0 |                    2 |                          0 |                  0 |
| feature_family | identity        |               7 |                   0 |                   0 |                    0 |                          0 |                  0 |
| feature_family | label           |               4 |                   0 |                   0 |                    4 |                          0 |                  0 |
| feature_family | other           |               8 |                   0 |                   8 |                    8 |                          0 |                  0 |
| feature_family | outcome         |               2 |                   0 |                   0 |                    2 |                          0 |                  0 |
| feature_family | quality         |               6 |                   0 |                   0 |                    0 |                          0 |                  0 |
| feature_family | region_position |             206 |                 206 |                 206 |                  206 |                          0 |                  0 |
| feature_family | round_context   |               4 |                   0 |                   4 |                    4 |                          0 |                  0 |
| feature_family | team_context    |               2 |                   0 |                   2 |                    2 |                          0 |                  0 |
| feature_family | utility         |             251 |                 242 |                 251 |                  251 |                          0 |                  0 |

## Temporal features
| feature_name               | feature_family   |   window_start |   window_end | window_type   |   minimum_prediction_horizon |
|:---------------------------|:-----------------|---------------:|-------------:|:--------------|-----------------------------:|
| avg_pairwise_distance_10s  | region_position  |              0 |           10 | point         |                           10 |
| avg_pairwise_distance_115s | region_position  |              0 |          115 | point         |                          115 |
| avg_pairwise_distance_15s  | region_position  |              0 |           15 | point         |                           15 |
| avg_pairwise_distance_20s  | region_position  |              0 |           20 | point         |                           20 |
| avg_pairwise_distance_25s  | region_position  |              0 |           25 | point         |                           25 |
| flashes_used_0_105         | utility          |              0 |          105 | cumulative    |                          105 |
| flashes_used_0_115         | utility          |              0 |          115 | cumulative    |                          115 |
| flashes_used_0_15          | utility          |              0 |           15 | both          |                           15 |
| flashes_used_0_20          | utility          |              0 |           20 | legacy        |                           20 |
| flashes_used_0_25          | utility          |              0 |           25 | cumulative    |                           25 |
| flashes_used_0_35          | utility          |              0 |           35 | cumulative    |                           35 |
| flashes_used_0_45          | utility          |              0 |           45 | cumulative    |                           45 |
| flashes_used_0_55          | utility          |              0 |           55 | cumulative    |                           55 |
| flashes_used_0_65          | utility          |              0 |           65 | cumulative    |                           65 |
| flashes_used_0_75          | utility          |              0 |           75 | cumulative    |                           75 |
| flashes_used_0_85          | utility          |              0 |           85 | cumulative    |                           85 |
| flashes_used_0_95          | utility          |              0 |           95 | cumulative    |                           95 |
| flashes_used_105_115       | utility          |            105 |          115 | interval      |                          115 |
| flashes_used_15_25         | utility          |             15 |           25 | interval      |                           25 |
| flashes_used_25_35         | utility          |             25 |           35 | interval      |                           35 |
| flashes_used_35_45         | utility          |             35 |           45 | interval      |                           45 |
| flashes_used_45_55         | utility          |             45 |           55 | interval      |                           55 |
| flashes_used_55_65         | utility          |             55 |           65 | interval      |                           65 |
| flashes_used_65_75         | utility          |             65 |           75 | interval      |                           75 |
| flashes_used_75_85         | utility          |             75 |           85 | interval      |                           85 |
| flashes_used_85_95         | utility          |             85 |           95 | interval      |                           95 |
| flashes_used_95_105        | utility          |             95 |          105 | interval      |                          105 |
| he_used_0_105              | utility          |              0 |          105 | cumulative    |                          105 |
| he_used_0_115              | utility          |              0 |          115 | cumulative    |                          115 |
| he_used_0_15               | utility          |              0 |           15 | both          |                           15 |

## Leakage policy
Labels, identifiers, post-round outcomes, plant result fields, quality/audit metadata, and known leakage fields are blocked from modeling.

## Modeling-safe features
| feature_name               |   minimum_prediction_horizon | used_in_stage6_candidate   | modeling_status   |
|:---------------------------|-----------------------------:|:---------------------------|:------------------|
| avg_pairwise_distance_10s  |                           10 | True                       | approved          |
| avg_pairwise_distance_115s |                          115 | False                      | unused            |
| avg_pairwise_distance_15s  |                           15 | True                       | approved          |
| avg_pairwise_distance_20s  |                           20 | False                      | approved          |
| avg_pairwise_distance_25s  |                           25 | False                      | approved          |
| first_molotov_time         |                          nan | False                      | unused            |
| first_smoke_time           |                          nan | False                      | unused            |
| first_utility_time         |                          nan | False                      | unused            |
| flashes_used_0_105         |                          105 | False                      | unused            |
| flashes_used_0_115         |                          115 | False                      | unused            |
| flashes_used_0_15          |                           15 | False                      | unused            |
| flashes_used_0_20          |                           20 | False                      | unused            |
| flashes_used_0_25          |                           25 | False                      | unused            |
| flashes_used_0_35          |                           35 | False                      | unused            |
| flashes_used_0_45          |                           45 | False                      | unused            |
| flashes_used_0_55          |                           55 | False                      | unused            |
| flashes_used_0_65          |                           65 | False                      | unused            |
| flashes_used_0_75          |                           75 | False                      | unused            |
| flashes_used_0_85          |                           85 | False                      | unused            |
| flashes_used_0_95          |                           95 | False                      | unused            |
| flashes_used_105_115       |                          115 | False                      | unused            |
| flashes_used_15_25         |                           25 | False                      | unused            |
| flashes_used_25_35         |                           35 | False                      | unused            |
| flashes_used_35_45         |                           45 | False                      | unused            |
| flashes_used_45_55         |                           55 | False                      | unused            |
| flashes_used_55_65         |                           65 | False                      | unused            |
| flashes_used_65_75         |                           75 | False                      | unused            |
| flashes_used_75_85         |                           85 | False                      | unused            |
| flashes_used_85_95         |                           95 | False                      | unused            |
| flashes_used_95_105        |                          105 | False                      | unused            |

## Dashboard-safe features
| feature_name               | semantic_role    | recommended_visualization_role   | recommended_filter_role   |
|:---------------------------|:-----------------|:---------------------------------|:--------------------------|
| avg_pairwise_distance_10s  | spatial_control  | timeseries                       | none                      |
| avg_pairwise_distance_115s | spatial_control  | timeseries                       | none                      |
| avg_pairwise_distance_15s  | spatial_control  | timeseries                       | none                      |
| avg_pairwise_distance_20s  | spatial_control  | timeseries                       | none                      |
| avg_pairwise_distance_25s  | spatial_control  | timeseries                       | none                      |
| bomb_planted               | bomb_progression | metric                           | none                      |
| bombsite                   | bomb_progression | metric                           | none                      |
| first_molotov_time         | utility_usage    | metric                           | none                      |
| first_smoke_time           | utility_usage    | metric                           | none                      |
| first_utility_time         | utility_usage    | metric                           | none                      |
| flashes_used_0_105         | utility_usage    | timeseries                       | none                      |
| flashes_used_0_115         | utility_usage    | timeseries                       | none                      |
| flashes_used_0_15          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_20          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_25          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_35          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_45          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_55          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_65          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_75          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_85          | utility_usage    | timeseries                       | none                      |
| flashes_used_0_95          | utility_usage    | timeseries                       | none                      |
| flashes_used_105_115       | utility_usage    | timeseries                       | none                      |
| flashes_used_15_25         | utility_usage    | timeseries                       | none                      |
| flashes_used_25_35         | utility_usage    | timeseries                       | none                      |
| flashes_used_35_45         | utility_usage    | timeseries                       | none                      |
| flashes_used_45_55         | utility_usage    | timeseries                       | none                      |
| flashes_used_55_65         | utility_usage    | timeseries                       | none                      |
| flashes_used_65_75         | utility_usage    | timeseries                       | none                      |
| flashes_used_75_85         | utility_usage    | timeseries                       | none                      |

## Map portability
| group_type   | group_value   |   feature_count |   temporal_features |   modeling_features |   dashboard_features |   mirage_specific_features |   unknown_features |
|:-------------|:--------------|----------------:|--------------------:|--------------------:|---------------------:|---------------------------:|-------------------:|
| map_scope    | global        |             184 |                 140 |                 163 |                  171 |                          0 |                  0 |
| map_scope    | map_abstract  |             308 |                 308 |                 308 |                  308 |                          0 |                  0 |

## Cross-map comparability
| group_type                | group_value         |   feature_count |   temporal_features |   modeling_features |   dashboard_features |   mirage_specific_features |   unknown_features |
|:--------------------------|:--------------------|----------------:|--------------------:|--------------------:|---------------------:|---------------------------:|-------------------:|
| cross_map_comparison_mode | direct              |             169 |                 125 |                 148 |                  156 |                          0 |                  0 |
| cross_map_comparison_mode | normalized_required |              15 |                  15 |                  15 |                   15 |                          0 |                  0 |
| cross_map_comparison_mode | semantic            |             308 |                 308 |                 308 |                  308 |                          0 |                  0 |

## Global features
| feature_name               | feature_family   | coordinate_dependency   | cross_map_comparison_mode   | modeling_allowed   | dashboard_allowed   |
|:---------------------------|:-----------------|:------------------------|:----------------------------|:-------------------|:--------------------|
| avg_pairwise_distance_10s  | region_position  | none                    | direct                      | True               | True                |
| avg_pairwise_distance_115s | region_position  | none                    | direct                      | True               | True                |
| avg_pairwise_distance_15s  | region_position  | none                    | direct                      | True               | True                |
| avg_pairwise_distance_20s  | region_position  | none                    | direct                      | True               | True                |
| avg_pairwise_distance_25s  | region_position  | none                    | direct                      | True               | True                |
| bomb_planted               | bomb             | none                    | direct                      | False              | True                |
| bombsite                   | bomb             | none                    | direct                      | False              | True                |
| dataset_type               | quality          | none                    | direct                      | False              | False               |
| dem_file_id                | identity         | none                    | direct                      | False              | False               |
| feature_notes              | quality          | none                    | direct                      | False              | False               |
| feature_quality_status     | quality          | none                    | direct                      | False              | False               |
| first_molotov_time         | utility          | none                    | direct                      | True               | True                |
| first_smoke_time           | utility          | none                    | direct                      | True               | True                |
| first_utility_time         | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_105         | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_115         | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_15          | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_20          | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_25          | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_35          | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_45          | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_55          | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_65          | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_75          | utility          | none                    | direct                      | True               | True                |
| flashes_used_0_85          | utility          | none                    | direct                      | True               | True                |

## Map-abstract features
| feature_name                   | region_semantic   | cross_map_comparable   | cross_map_comparison_mode   | modeling_allowed   | notes                                 |
|:-------------------------------|:------------------|:-----------------------|:----------------------------|:-------------------|:--------------------------------------|
| molotovs_to_a_pressure_0_105   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_115   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_15    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_20    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_25    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_35    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_45    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_55    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_65    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_75    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_85    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_0_95    | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_105_115 | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_15_25   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_25_35   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_35_45   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_45_55   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_55_65   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_65_75   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_75_85   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_85_95   | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_a_pressure_95_105  | a_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_b_pressure_0_105   | b_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_b_pressure_0_115   | b_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |
| molotovs_to_b_pressure_0_15    | b_pressure        | True                   | semantic                    | True               | Requires active map region semantics. |

## Mirage-specific features
_No rows available._

## Features requiring map registry
| feature_name                   | map_scope    | region_semantic   | recommended_action                                      |
|:-------------------------------|:-------------|:------------------|:--------------------------------------------------------|
| molotovs_to_a_pressure_0_105   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_115   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_15    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_20    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_25    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_35    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_45    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_55    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_65    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_75    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_85    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_0_95    | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_105_115 | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_15_25   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_25_35   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_35_45   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_45_55   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_55_65   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_65_75   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_75_85   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_85_95   | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_a_pressure_95_105  | map_abstract | a_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_b_pressure_0_105   | map_abstract | b_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_b_pressure_0_115   | map_abstract | b_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_b_pressure_0_15    | map_abstract | b_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_b_pressure_0_20    | map_abstract | b_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_b_pressure_0_25    | map_abstract | b_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_b_pressure_0_35    | map_abstract | b_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_b_pressure_0_45    | map_abstract | b_pressure        | Define equivalent semantic region per map in Stage 8.1. |
| molotovs_to_b_pressure_0_55    | map_abstract | b_pressure        | Define equivalent semantic region per map in Stage 8.1. |

## Unknown / review queue
| feature_name           | unknown_field   | current_value   | reason                                 | recommended_manual_action               | severity   |
|:-----------------------|:----------------|:----------------|:---------------------------------------|:----------------------------------------|:-----------|
| bomb_planted           | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| bombsite               | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| first_molotov_time     | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| first_smoke_time       | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| first_utility_time     | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| freeze_end_tick        | feature_family  | other           | No confident family classification.    | Classify manually before expansion.     | medium     |
| freeze_end_tick        | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| is_early_round         | feature_family  | other           | No confident family classification.    | Classify manually before expansion.     | medium     |
| is_early_round         | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| is_late_round          | feature_family  | other           | No confident family classification.    | Classify manually before expansion.     | medium     |
| is_late_round          | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| is_pistol_round        | feature_family  | other           | No confident family classification.    | Classify manually before expansion.     | medium     |
| map_name               | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| opponent               | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| round_duration_seconds | feature_family  | other           | No confident family classification.    | Classify manually before expansion.     | medium     |
| round_duration_seconds | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| round_duration_ticks   | feature_family  | other           | No confident family classification.    | Classify manually before expansion.     | medium     |
| round_duration_ticks   | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| round_end_tick         | feature_family  | other           | No confident family classification.    | Classify manually before expansion.     | medium     |
| round_end_tick         | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |
| round_start_tick       | feature_family  | other           | No confident family classification.    | Classify manually before expansion.     | medium     |
| target_team            | lifecycle_phase | unknown         | Lifecycle phase could not be inferred. | Set pre_round/in_round/post_* manually. | low        |

## Frozen contract
`configs/features/feature_contract.yaml` stores the frozen contract subset for future stages.

## Next stage
Next: Stage 8.1 -- Map Geometry & Region Registry
