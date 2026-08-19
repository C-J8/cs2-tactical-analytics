# Inferno Feature Quality & Tactical Readiness Gate

## Purpose
Validate whether the scoped Inferno Gold features are technically reliable for analysis and whether the A/B sample is ready for modeling experiments.

## Stage 8.8 Input
Map/team scope: `Inferno` / `Vitality`.

## Dataset Reconciliation
| dataset_name                  |   row_count |   duplicate_key_count |   missing_key_count | relationship_passed   | status   | notes                      |
|:------------------------------|------------:|----------------------:|--------------------:|:----------------------|:---------|:---------------------------|
| round_features_mvp            |         122 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| round_state_resolved          |         122 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| round_features_t_side_all     |          65 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| round_features_t_side_planted |          40 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| round_features_ct_side        |          57 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| region_presence_by_round      |       17760 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| round_region_timeline         |       17760 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| death_context_by_round        |         786 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| bomb_carrier_timeline         |        2684 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| round_outcome_context         |         122 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |
| utility_events                |         782 |                     0 |                   0 | True                  | ok       | Scoped dataset reconciled. |

## Feature Missingness
| feature_name            |   missing_share | expected_missingness   | severity   | status   | notes                                                   |
|:------------------------|----------------:|:-----------------------|:-----------|:---------|:--------------------------------------------------------|
| flashes_used_0_20       |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_0_20            |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| score_diff_before_round |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_0_15       |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_0_15            |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_15_25      |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_15_25           |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_25_35      |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_25_35           |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_35_45      |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_35_45           |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_45_55      |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_45_55           |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_55_65      |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_55_65           |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_65_75      |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_65_75           |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_75_85      |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_75_85           |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_85_95      |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_85_95           |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_95_105     |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_95_105          |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_105_115    |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_105_115         |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_0_25       |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_0_25            |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_0_35       |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| he_used_0_35            |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |
| flashes_used_0_45       |               1 | False                  | critical   | failed   | Unexpected missingness assessed against quality config. |

## Feature Domains
| feature_name              | domain_rule    |   invalid_rows | severity   | status   |
|:--------------------------|:---------------|---------------:|:-----------|:---------|
| team_spread_20s           | unknown_domain |              0 | none       | skipped  |
| avg_pairwise_distance_10s | unknown_domain |              0 | none       | skipped  |
| avg_pairwise_distance_20s | unknown_domain |              0 | none       | skipped  |
| players_mid_0_20          | unknown_domain |              0 | none       | skipped  |
| time_mid_control_0_20     | unknown_domain |              0 | none       | skipped  |
| time_a_pressure_0_20      | unknown_domain |              0 | none       | skipped  |
| time_b_pressure_0_20      | unknown_domain |              0 | none       | skipped  |
| team_smokes_start         | unknown_domain |              0 | none       | skipped  |
| team_flashes_start        | unknown_domain |              0 | none       | skipped  |
| team_molotovs_start       | unknown_domain |              0 | none       | skipped  |
| team_he_start             | unknown_domain |              0 | none       | skipped  |
| time_a_pressure_0_115     | unknown_domain |              0 | none       | skipped  |
| time_b_pressure_0_115     | unknown_domain |              0 | none       | skipped  |
| time_ct_space_0_115       | unknown_domain |              0 | none       | skipped  |
| time_ct_space_0_20        | unknown_domain |              0 | none       | skipped  |
| time_a_pressure_0_95      | unknown_domain |              0 | none       | skipped  |
| time_b_pressure_0_95      | unknown_domain |              0 | none       | skipped  |
| time_ct_space_0_95        | unknown_domain |              0 | none       | skipped  |
| time_mid_control_0_105    | unknown_domain |              0 | none       | skipped  |
| time_a_pressure_0_105     | unknown_domain |              0 | none       | skipped  |
| time_b_pressure_0_105     | unknown_domain |              0 | none       | skipped  |
| time_ct_space_0_105       | unknown_domain |              0 | none       | skipped  |
| time_mid_control_0_115    | unknown_domain |              0 | none       | skipped  |
| team_decoys_start         | unknown_domain |              0 | none       | skipped  |
| team_total_utility_start  | unknown_domain |              0 | none       | skipped  |
| first_smoke_time          | unknown_domain |              0 | none       | skipped  |
| first_molotov_time        | unknown_domain |              0 | none       | skipped  |
| first_utility_time        | unknown_domain |              0 | none       | skipped  |
| time_a_pressure_0_75      | unknown_domain |              0 | none       | skipped  |
| time_b_pressure_0_75      | unknown_domain |              0 | none       | skipped  |

## Degenerate Features
| feature_name                  |   zero_share | constant   | near_constant   | all_zero   | severity   | status   | notes                                                                                                |
|:------------------------------|-------------:|:-----------|:----------------|:-----------|:-----------|:---------|:-----------------------------------------------------------------------------------------------------|
| smokes_to_mid_control_0_20    |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_a_pressure_0_20     |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_b_pressure_0_20     |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_mid_control_0_20  |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_a_pressure_0_20   |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_b_pressure_0_20   |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| players_ct_space_0_15         |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| time_ct_space_0_15            |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_mid_control_0_15    |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_mid_control_0_15  |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_a_pressure_0_15     |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_a_pressure_0_15   |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_b_pressure_0_15     |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_b_pressure_0_15   |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_mid_control_15_25   |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_mid_control_15_25 |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_a_pressure_15_25    |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_a_pressure_15_25  |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_b_pressure_15_25    |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_b_pressure_15_25  |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_mid_control_25_35   |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_mid_control_25_35 |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_a_pressure_25_35    |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_a_pressure_25_35  |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_b_pressure_25_35    |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_b_pressure_25_35  |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_mid_control_35_45   |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_mid_control_35_45 |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| smokes_to_a_pressure_35_45    |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |
| molotovs_to_a_pressure_35_45  |            1 | True       | True            | True       | warning    | warning  | Individual required semantic feature is all zero; semantic-level health decides whether this blocks. |

## Per-Demo Health
| map_id   | target_team   | parse_id                                                                                                                                                                                            |   rounds |   t_rounds |   ct_rounds |   feature_missingness_warning_count |   degenerate_feature_count |   semantic_failure_count |   plant_labels |   a_labels |   b_labels | status   |
|:---------|:--------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------:|-----------:|------------:|------------------------------------:|---------------------------:|-------------------------:|---------------:|-----------:|-----------:|:---------|
| inferno  | Vitality      | blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_blast_bounty_2026_season_1_finals_vitality_vs_falcons_bo3_m75xkivwc3yzkebdtp1s9_vitality_vs_falcons_m1_inferno_awpy |       23 |         12 |          11 |                                   0 |                        211 |                        0 |              6 |          5 |          1 | warning  |
| inferno  | Vitality      | blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_blast_open_rotterdam_2026_parivision_vs_vitality_bo3_hiwqxfbgrevcywe8xglmbb_parivision_vs_vitality_m2_inferno_awpy      |       28 |         15 |          13 |                                   0 |                        197 |                        0 |             11 |          6 |          5 | warning  |
| inferno  | Vitality      | hltv_2389666_mirage_map1_hltv_2389666_mirage_map1_furia_vs_vitality_m2_inferno_awpy                                                                                                                 |       21 |         12 |           9 |                                   0 |                        197 |                        0 |              8 |          4 |          4 | warning  |
| inferno  | Vitality      | iem_rio_2026_vitality_vs_g2_bo3_yhor34ca9po02urfkioto9_iem_rio_2026_vitality_vs_g2_bo3_yhor34ca9po02urfkioto9_vitality_vs_g2_m2_inferno_awpy                                                        |       29 |         14 |          15 |                                   0 |                        207 |                        0 |              9 |          4 |          5 | warning  |
| inferno  | Vitality      | pgl_cluj_napoca_2026_vitality_vs_g2_bo3_qyj9k9myd7qwvfmck2zjt5_pgl_cluj_napoca_2026_vitality_vs_g2_bo3_qyj9k9myd7qwvfmck2zjt5_vitality_vs_g2_m2_inferno_awpy                                        |       21 |         12 |           9 |                                   0 |                        203 |                        0 |              6 |          3 |          3 | warning  |

## Semantic Signal Health
| semantic_id   |   required_feature_count |   materialized_feature_count |   round_signal_share |   demo_signal_share | status   | notes                                           |
|:--------------|-------------------------:|-----------------------------:|---------------------:|--------------------:|:---------|:------------------------------------------------|
| a_pressure    |                       88 |                           88 |             0.844262 |                   1 | ok       | Semantic signal assessed from Feature Contract. |
| b_pressure    |                       88 |                           88 |             0.92623  |                   1 | ok       | Semantic signal assessed from Feature Contract. |
| ct_space      |                       44 |                           44 |             0.295082 |                   1 | ok       | Semantic signal assessed from Feature Contract. |
| mid_control   |                       88 |                           88 |             1        |                   1 | ok       | Semantic signal assessed from Feature Contract. |

## Region Presence
| region_id              | region_group   |   presence_share | status   | notes                       |
|:-----------------------|:---------------|-----------------:|:---------|:----------------------------|
| Apartments             | A_PRESSURE     |                1 | ok       | Region has observed signal. |
| Arch                   | CT_SPACE       |                1 | ok       | Region has observed signal. |
| Back Alley             | A_PRESSURE     |                1 | ok       | Region has observed signal. |
| Balcony                | A_PRESSURE     |                1 | ok       | Region has observed signal. |
| Banana                 | B_PRESSURE     |                1 | ok       | Region has observed signal. |
| Bombsite A             | SITE_A         |                1 | ok       | Region has observed signal. |
| Bombsite B             | SITE_B         |                1 | ok       | Region has observed signal. |
| CT Spawn               | CT_SPACE       |                1 | ok       | Region has observed signal. |
| Graveyard              | A_PRESSURE     |                1 | ok       | Region has observed signal. |
| Library                | CT_SPACE       |                1 | ok       | Region has observed signal. |
| Lower Mid              | MID_CONTROL    |                1 | ok       | Region has observed signal. |
| Middle                 | MID_CONTROL    |                1 | ok       | Region has observed signal. |
| Pit                    | A_PRESSURE     |                1 | ok       | Region has observed signal. |
| Quad                   | A_PRESSURE     |                1 | ok       | Region has observed signal. |
| Ruins                  | B_PRESSURE     |                1 | ok       | Region has observed signal. |
| Second Mid             | MID_CONTROL    |                1 | ok       | Region has observed signal. |
| Second Mid Upper Route | MID_CONTROL    |                1 | ok       | Region has observed signal. |
| T Ramp                 | MID_CONTROL    |                1 | ok       | Region has observed signal. |
| T Spawn                | T_SPAWN_AREA   |                1 | ok       | Region has observed signal. |
| Top of Mid             | MID_CONTROL    |                1 | ok       | Region has observed signal. |
| Underpass              | MID_CONTROL    |                1 | ok       | Region has observed signal. |

## Temporal Consistency
| feature_group           | semantic_id   |   windows_checked |   monotonicity_violations | status   | notes                             |
|:------------------------|:--------------|------------------:|--------------------------:|:---------|:----------------------------------|
| flashes_used            | nan           |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| he_used                 | nan           |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| molotovs_to_a_pressure  | a_pressure    |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| molotovs_to_b_pressure  | b_pressure    |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| molotovs_to_mid_control | mid_control   |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| molotovs_used           | nan           |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| players_a_pressure      | a_pressure    |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| players_b_pressure      | b_pressure    |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| players_ct_space        | ct_space      |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| players_mid_control     | mid_control   |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| smokes_to_a_pressure    | a_pressure    |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| smokes_to_b_pressure    | b_pressure    |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| smokes_to_mid_control   | mid_control   |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| smokes_used             | nan           |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| time_a_pressure         | a_pressure    |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| time_b_pressure         | b_pressure    |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| time_ct_space           | ct_space      |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| time_mid_control        | mid_control   |                11 |                         0 | ok       | Cumulative windows are monotonic. |
| total_utility_used      | nan           |                11 |                         0 | ok       | Cumulative windows are monotonic. |

## Side Health
| feature_name                  |   t_zero_share |   ct_zero_share | side_asymmetry_flag   | status   | notes                                                              |
|:------------------------------|---------------:|----------------:|:----------------------|:---------|:-------------------------------------------------------------------|
| is_defense_analysis_candidate |      1         |       0         | True                  | warning  | Large T/CT zero-share asymmetry; tactical interpretation deferred. |
| is_progression_candidate      |      0         |       1         | True                  | warning  | Large T/CT zero-share asymmetry; tactical interpretation deferred. |
| winner_side                   |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_95_105     |      0.830769  |       0.912281  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_85_95      |      0.615385  |       0.719298  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_75_85      |      0.661538  |       0.596491  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_65_75      |      0.630769  |       0.701754  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_55_65      |      0.646154  |       0.666667  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_45_55      |      0.707692  |       0.666667  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_35_45      |      0.584615  |       0.596491  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_25_35      |      0.661538  |       0.649123  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_15_25      |      0.615385  |       0.491228  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_105_115    |      0.923077  |       0.947368  | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_0_95       |      0.0307692 |       0.0350877 | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_0_85       |      0.0307692 |       0.0526316 | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_0_75       |      0.0307692 |       0.0526316 | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_0_65       |      0.0307692 |       0.0701754 | False                 | ok       | T/CT distribution assessed.                                        |
| total_utility_used_0_55       |      0.0307692 |       0.0701754 | False                 | ok       | T/CT distribution assessed.                                        |
| flashes_used_0_35             |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| flashes_used_0_25             |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| flashes_used_0_20             |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| flashes_used_0_15             |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| flashes_used_0_115            |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| flashes_used_0_105            |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| first_utility_time            |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| first_smoke_time              |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| first_molotov_time            |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| bombsite                      |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |
| bomb_planted                  |      0.384615  |       0.508772  | False                 | ok       | T/CT distribution assessed.                                        |
| avg_pairwise_distance_25s     |      0         |       0         | False                 | ok       | T/CT distribution assessed.                                        |

## A/B Label Quality
| map_id   | target_team   |   t_rounds |   plant_rounds |   target_team_plant_rounds |   high_confidence_plant_labels |   a_labels |   b_labels |   a_share |   b_share | minority_class   |   minority_class_count |   minority_class_share |   missing_site |   invalid_site |   duplicate_rounds |   demos_with_a |   demos_with_b | label_status   | notes                                              |
|:---------|:--------------|-----------:|---------------:|---------------------------:|-------------------------------:|-----------:|-----------:|----------:|----------:|:-----------------|-----------------------:|-----------------------:|---------------:|---------------:|-------------------:|---------------:|---------------:|:---------------|:---------------------------------------------------|
| inferno  | Vitality      |         65 |             68 |                         40 |                             40 |         22 |         18 |      0.55 |      0.45 | B                |                     18 |                   0.45 |              0 |              0 |                  0 |              5 |              5 | ok             | A/B labels are high-confidence T-side plants only. |

## Sample Size
| map_id   | target_team   |   t_rounds |   planted_t_rounds |   a_count |   b_count |   minority_class_count | unique_demos   |   demos_with_both_classes | sample_status    | ready_for_exploratory_modeling   | ready_for_baseline_modeling   | ready_for_robust_modeling   | blocking_reason   | limitations                                             | notes                                             |
|:---------|:--------------|-----------:|-------------------:|----------:|----------:|-----------------------:|:---------------|--------------------------:|:-----------------|:---------------------------------|:------------------------------|:----------------------------|:------------------|:--------------------------------------------------------|:--------------------------------------------------|
| inferno  | Vitality      |         65 |                 40 |        22 |        18 |                     18 |                |                         5 | exploratory_only | True                             | False                         | False                       |                   | Small sample; use only controlled exploratory analysis. | Readiness derives from quality config thresholds. |

## Mirage vs Inferno Comparable Features
| feature_name                 | comparison_mode   |   mirage_zero_share |   inferno_zero_share |   robust_location_shift | structural_mismatch   | status   | notes                                                                               |
|:-----------------------------|:------------------|--------------------:|---------------------:|------------------------:|:----------------------|:---------|:------------------------------------------------------------------------------------|
| time_mid_control_0_15        | semantic          |           0.195062  |            0         |                3.34066  | False                 | warning  | Cross-map comparable distribution profiled.                                         |
| players_mid_control_0_15     | semantic          |           0.195062  |            0         |                8        | False                 | warning  | Cross-map comparable distribution profiled.                                         |
| players_mid_control_0_25     | semantic          |           0.175309  |            0         |                3        | False                 | warning  | Cross-map comparable distribution profiled.                                         |
| players_mid_control_0_35     | semantic          |           0.158025  |            0         |                3        | False                 | warning  | Cross-map comparable distribution profiled.                                         |
| players_mid_control_0_45     | semantic          |           0.140741  |            0         |                3        | False                 | warning  | Cross-map comparable distribution profiled.                                         |
| players_mid_control_0_55     | semantic          |           0.130864  |            0         |                3        | True                  | warning  | Potential structural comparable-feature mismatch; tactical interpretation deferred. |
| players_mid_control_0_65     | semantic          |           0.128395  |            0         |                2        | True                  | warning  | Potential structural comparable-feature mismatch; tactical interpretation deferred. |
| players_mid_control_0_75     | semantic          |           0.125926  |            0         |                1.33333  | True                  | warning  | Potential structural comparable-feature mismatch; tactical interpretation deferred. |
| players_mid_control_0_85     | semantic          |           0.123457  |            0         |                1.33333  | True                  | warning  | Potential structural comparable-feature mismatch; tactical interpretation deferred. |
| players_mid_control_0_95     | semantic          |           0.120988  |            0         |                1.33333  | True                  | warning  | Potential structural comparable-feature mismatch; tactical interpretation deferred. |
| players_mid_0_20             | semantic          |           0.182716  |            0         |                6        | False                 | warning  | Cross-map comparable distribution profiled.                                         |
| players_mid_control_0_105    | semantic          |           0.118519  |            0         |                1.33333  | True                  | warning  | Potential structural comparable-feature mismatch; tactical interpretation deferred. |
| players_mid_control_0_115    | semantic          |           0.118519  |            0         |                1.33333  | True                  | warning  | Potential structural comparable-feature mismatch; tactical interpretation deferred. |
| total_utility_used_105_115   | direct            |           0.985185  |            0.934426  |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_95      | direct            |           0.0567901 |            0.0327869 |                0.285714 | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_85      | direct            |           0.0567901 |            0.0409836 |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_75      | direct            |           0.0567901 |            0.0409836 |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_65      | direct            |           0.0641975 |            0.0491803 |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_55      | direct            |           0.0641975 |            0.0491803 |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_45      | direct            |           0.0641975 |            0.0901639 |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_35      | direct            |           0.0641975 |            0.114754  |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_25      | direct            |           0.0765432 |            0.122951  |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_20      | direct            |           0.103704  |            0.131148  |                0.666667 | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_15      | direct            |           0.123457  |            0.131148  |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_115     | direct            |           0.0567901 |            0.0245902 |                0.285714 | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| total_utility_used_0_105     | direct            |           0.0567901 |            0.0245902 |                0.285714 | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| time_mid_control_95_105      | semantic          |           0.691358  |            0.696721  |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| time_mid_control_85_95       | semantic          |           0.614815  |            0.557377  |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| time_mid_control_75_85       | semantic          |           0.520988  |            0.467213  |                0.324324 | False                 | ok       | Cross-map comparable distribution profiled.                                         |
| molotovs_to_a_pressure_0_115 | semantic          |           1         |            1         |                0        | False                 | ok       | Cross-map comparable distribution profiled.                                         |

## Non-Comparable Features
| feature_name       | reason                                                                                                       | comparison_mode     |
|:-------------------|:-------------------------------------------------------------------------------------------------------------|:--------------------|
| team_center_x_10s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_x_115s | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_x_15s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_x_20s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_x_25s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_y_10s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_y_115s | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_y_15s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_y_20s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_y_25s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_z_10s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_z_115s | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_z_15s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_z_20s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |
| team_center_z_25s  | Raw map coordinates can be generated on multiple maps but are not directly comparable without normalization. | normalized_required |

## Round-Level Flags
_No rows._

## Quality Scorecard
| map_id   | target_team   | category             |   checks |   passed |   warnings |   failed |   blocking_failures | status   | notes                                        |
|:---------|:--------------|:---------------------|---------:|---------:|-----------:|---------:|--------------------:|:---------|:---------------------------------------------|
| inferno  | Vitality      | dataset_integrity    |       11 |       11 |          0 |        0 |                   0 | ok       | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | feature_missingness  |      477 |      432 |          0 |       45 |                  45 | failed   | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | feature_domains      |      477 |      339 |          0 |        0 |                   0 | ok       | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | feature_degeneracy   |      477 |      325 |        152 |        0 |                   0 | warning  | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | semantic_health      |        4 |        4 |          0 |        0 |                   0 | ok       | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | temporal_consistency |       19 |       19 |          0 |        0 |                   0 | ok       | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | round_state          |        7 |        7 |          0 |        0 |                   0 | ok       | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | label_quality        |       40 |       40 |          0 |        0 |                   0 | ok       | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | cross_map_sanity     |      409 |      396 |         13 |        0 |                   0 | warning  | Category assessed by Stage 8.9 quality gate. |
| inferno  | Vitality      | sample_size          |        1 |        0 |          0 |        0 |                   0 | ok       | Category assessed by Stage 8.9 quality gate. |

## Modeling Limitations
Small sample; use only controlled exploratory analysis.

## Readiness
ready_for_multi_map_eda: `False`
ready_for_inferno_modeling_experiment: `False`
modeling_readiness_level: `exploratory_only`
status: `failed`

## Next Stage
If multi-map EDA is ready, the next stage is Stage 8.10 -- Vitality Multi-Map Tactical EDA: Mirage vs Inferno. This report does not make tactical conclusions.
