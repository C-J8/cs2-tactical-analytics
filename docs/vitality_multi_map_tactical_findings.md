# Vitality Mirage vs Inferno -- Hardened Tactical Findings

## Purpose
Consolidate Stage 8.10 raw statistical rows into auditable tactical evidence units without modifying core Gold outputs.

## Input EDA
| audit_id                      | target_team   | maps           | stage_8_10_passed   |   raw_candidates |   raw_ranked_findings |   finding_concepts |   consolidated_findings |   hardened_ranked_findings |   high_descriptive_findings |   moderate_descriptive_findings |   tentative_findings |   redundant_candidates_collapsed |   late_window_candidates_checked |   late_window_candidates_downgraded |   opponent_sensitive_findings |   demo_fragile_findings |   direction_conflicts |   cross_map_flat_pattern_rejections |   exclusion_taxonomy_changes | core_gold_unchanged   | stage_8_10_outputs_unchanged   |   critical_failures |   warnings | ready_for_stage_8_11   | status   | created_at                       |
|:------------------------------|:--------------|:---------------|:--------------------|-----------------:|----------------------:|-------------------:|------------------------:|---------------------------:|----------------------------:|--------------------------------:|---------------------:|---------------------------------:|---------------------------------:|------------------------------------:|------------------------------:|------------------------:|----------------------:|------------------------------------:|-----------------------------:|:----------------------|:-------------------------------|--------------------:|-----------:|:-----------------------|:---------|:---------------------------------|
| tactical_finding_hardening_v1 | Vitality      | Mirage,Inferno | True                |             2760 |                    25 |                 79 |                     349 |                          9 |                          10 |                              41 |                  166 |                             2411 |                             1130 |                                1130 |                             0 |                      59 |                    32 |                                 161 |                           15 | True                  | True                           |                   0 |          0 | True                   | passed   | 2026-08-25T22:33:08.117538+00:00 |

## Why Consolidation Was Needed
A feature window is not a tactical finding. This stage collapses redundant windows/cohorts, hardens direction text, applies temporal exposure checks, and evaluates opponent/demo sensitivity.

## Evidence Method
Evidence is descriptive, map-order explicit, demo-aware, and non-causal. The requested map order is Mirage as reference and Inferno as comparison.

## Map Comparison Direction
Final text names maps explicitly and never uses first-map or second-map wording.

## Temporal Exposure Rules
Late windows are downgraded when either map has exposure below the configured threshold.

## Finding Consolidation
| finding_concept_id                                  |   raw_candidate_count | representative_feature   | directions_observed   | status              |
|:----------------------------------------------------|----------------------:|:-------------------------|:----------------------|:--------------------|
| direct_feature.freeze_end_tick.non_temporal         |                     5 | freeze_end_tick          | lower                 | tentative           |
| direct_feature.half.non_temporal                    |                     5 | half                     | lower                 | tentative           |
| direct_feature.is_early_round.non_temporal          |                     5 | is_early_round           | flat|higher           | tentative           |
| direct_feature.is_late_round.non_temporal           |                     5 | is_late_round            | flat                  | tentative           |
| direct_feature.is_pistol_round.non_temporal         |                     5 | is_pistol_round          | flat                  | tentative           |
| direct_feature.round_duration_seconds.non_temporal  |                     5 | round_duration_seconds   | higher                | tentative           |
| direct_feature.round_duration_ticks.non_temporal    |                     5 | round_duration_ticks     | higher                | tentative           |
| direct_feature.round_end_tick.non_temporal          |                     5 | round_end_tick           | lower                 | tentative           |
| direct_feature.round_start_tick.non_temporal        |                     5 | round_start_tick         | lower                 | tentative           |
| direct_feature.score_diff_before_round.non_temporal |                     5 | score_diff_before_round  | flat|lower            | ok                  |
| plant_progression.freeze_end_tick.non_temporal      |                     1 | freeze_end_tick          | lower                 | tentative           |
| plant_progression.freeze_end_tick.non_temporal      |                     1 | freeze_end_tick          | higher                | tentative           |
| plant_progression.half.non_temporal                 |                     1 | half                     | flat                  | tentative           |
| plant_progression.half.non_temporal                 |                     1 | half                     | flat                  | tentative           |
| plant_progression.is_early_round.non_temporal       |                     1 | is_early_round           | flat                  | tentative           |
| plant_progression.is_early_round.non_temporal       |                     1 | is_early_round           | flat                  | tentative           |
| plant_progression.is_late_round.non_temporal        |                     1 | is_late_round            | flat                  | tentative           |
| plant_progression.is_late_round.non_temporal        |                     1 | is_late_round            | flat                  | tentative           |
| plant_progression.is_pistol_round.non_temporal      |                     1 | is_pistol_round          | flat                  | tentative           |
| plant_progression.is_pistol_round.non_temporal      |                     1 | is_pistol_round          | flat                  | tentative           |
| plant_progression.players_alive.early               |                    20 | players_alive_25s        | flat                  | tentative           |
| plant_progression.players_alive.early               |                     4 | players_alive_15s        | flat                  | tentative           |
| plant_progression.players_alive.early               |                     4 | players_alive_15s        | flat                  | tentative           |
| plant_progression.players_alive.early               |                     4 | players_alive_25s        | flat                  | tentative           |
| plant_progression.players_alive.early               |                     4 | players_alive_20s        | flat                  | tentative           |
| plant_progression.players_alive.early               |                     4 | players_alive_25s        | flat                  | tentative           |
| plant_progression.players_alive.late                |                     5 | players_alive_115s       | flat|higher           | downgraded_exposure |
| plant_progression.players_alive.late                |                     1 | players_alive_115s       | flat                  | downgraded_exposure |
| plant_progression.players_alive.late                |                     1 | players_alive_115s       | flat                  | downgraded_exposure |
| plant_progression.players_alive.late                |                     1 | players_alive_115s       | lower                 | downgraded_exposure |

## Top Hardened Findings
|   rank | finding_concept_id                                     | category          | representative_feature          | evidence_quality     | representative_text                                                                                                            |
|-------:|:-------------------------------------------------------|:------------------|:--------------------------------|:---------------------|:-------------------------------------------------------------------------------------------------------------------------------|
|      1 | utility.smoke.early_usage                              | direct_feature    | smokes_used_0_25                | high_descriptive     | smokes used 0 25 is lower on Inferno than Mirage; interpretation is non-causal.                                                |
|      2 | utility.smoke.first_timing                             | direct_feature    | first_smoke_time                | high_descriptive     | First smoke usage occurs later on Inferno than Mirage; interpretation is non-causal.                                           |
|      3 | semantic.b_pressure.player_presence.mid                | site_pattern      | players_b_pressure_55_65        | high_descriptive     | players b pressure 55 65 is higher in B-plant rounds than A-plant rounds; interpretation is non-causal.                        |
|      4 | utility.molotov.early_usage                            | direct_feature    | molotovs_used_0_15              | high_descriptive     | molotovs used 0 15 is higher on Inferno than Mirage; interpretation is non-causal.                                             |
|      5 | utility.molotov.mid_usage                              | direct_feature    | molotovs_used_0_45              | high_descriptive     | molotovs used 0 45 is higher on Inferno than Mirage; interpretation is non-causal.                                             |
|      6 | utility.inventory.flash                                | site_pattern      | team_flashes_start              | moderate_descriptive | team flashes start is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.                               |
|      7 | plant_progression.score_diff_before_round.non_temporal | plant_progression | score_diff_before_round         | moderate_descriptive | score diff before round is higher in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label. |
|      8 | utility.inventory.molotov                              | site_pattern      | team_molotovs_start             | moderate_descriptive | team molotovs start is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.                              |
|      9 | site_choice.distribution                               | site_choice       | plant_site_distribution_b_share | moderate_descriptive | Observed planted T rounds are more balanced between A and B on Inferno than Mirage; this is plant-site choice only.            |

## Utility Findings
| finding_concept_id                                  | representative_feature     | evidence_quality     | representative_text                                                                               |
|:----------------------------------------------------|:---------------------------|:---------------------|:--------------------------------------------------------------------------------------------------|
| direct_feature.freeze_end_tick.non_temporal         | freeze_end_tick            | tentative            | freeze end tick is lower on Inferno than Mirage; interpretation is non-causal.                    |
| direct_feature.half.non_temporal                    | half                       | tentative            | half is lower on Inferno than Mirage; interpretation is non-causal.                               |
| direct_feature.is_early_round.non_temporal          | is_early_round             | tentative            | is_early_round is descriptively flat between Mirage and Inferno; interpretation is non-causal.    |
| direct_feature.is_late_round.non_temporal           | is_late_round              | tentative            | is_late_round is descriptively flat between Mirage and Inferno; interpretation is non-causal.     |
| direct_feature.is_pistol_round.non_temporal         | is_pistol_round            | insufficient         | is_pistol_round is descriptively flat between Mirage and Inferno; interpretation is non-causal.   |
| direct_feature.round_duration_seconds.non_temporal  | round_duration_seconds     | tentative            | round duration seconds is higher on Inferno than Mirage; interpretation is non-causal.            |
| direct_feature.round_duration_ticks.non_temporal    | round_duration_ticks       | tentative            | round duration ticks is higher on Inferno than Mirage; interpretation is non-causal.              |
| direct_feature.round_end_tick.non_temporal          | round_end_tick             | tentative            | round end tick is lower on Inferno than Mirage; interpretation is non-causal.                     |
| direct_feature.round_start_tick.non_temporal        | round_start_tick           | tentative            | round start tick is lower on Inferno than Mirage; interpretation is non-causal.                   |
| direct_feature.score_diff_before_round.non_temporal | score_diff_before_round    | moderate_descriptive | score diff before round is lower on Inferno than Mirage; interpretation is non-causal.            |
| plant_progression.players_alive.early               | players_alive_25s          | tentative            | players_alive_25s is descriptively flat between Mirage and Inferno; interpretation is non-causal. |
| plant_progression.players_alive.late                | players_alive_115s         | tentative            | players alive 115s is higher on Inferno than Mirage; interpretation is non-causal.                |
| structure.pairwise_distance.early                   | avg_pairwise_distance_10s  | moderate_descriptive | avg pairwise distance 10s is lower on Inferno than Mirage; interpretation is non-causal.          |
| structure.pairwise_distance.late                    | avg_pairwise_distance_115s | tentative            | avg pairwise distance 115s is higher on Inferno than Mirage; interpretation is non-causal.        |
| structure.team_spread.early                         | team_spread_10s            | moderate_descriptive | team spread 10s is lower on Inferno than Mirage; interpretation is non-causal.                    |

## Team Structure Findings
| finding_concept_id                | representative_feature     | evidence_quality     | representative_text                                                                                                              |
|:----------------------------------|:---------------------------|:---------------------|:---------------------------------------------------------------------------------------------------------------------------------|
| structure.pairwise_distance.early | avg_pairwise_distance_10s  | moderate_descriptive | avg pairwise distance 10s is lower on Inferno than Mirage; interpretation is non-causal.                                         |
| structure.pairwise_distance.early | avg_pairwise_distance_20s  | tentative            | avg_pairwise_distance_20s is descriptively flat between Mirage and Inferno; interpretation is non-causal.                        |
| structure.pairwise_distance.early | avg_pairwise_distance_15s  | insufficient         | avg pairwise distance 15s is higher in B-plant rounds than A-plant rounds; interpretation is non-causal.                         |
| structure.pairwise_distance.early | avg_pairwise_distance_15s  | insufficient         | avg pairwise distance 15s is higher in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label. |
| structure.pairwise_distance.early | avg_pairwise_distance_20s  | moderate_descriptive | avg pairwise distance 20s is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.                          |
| structure.pairwise_distance.early | avg_pairwise_distance_25s  | insufficient         | avg pairwise distance 25s is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label.  |
| structure.pairwise_distance.late  | avg_pairwise_distance_115s | tentative            | avg pairwise distance 115s is higher on Inferno than Mirage; interpretation is non-causal.                                       |
| structure.pairwise_distance.late  | avg_pairwise_distance_115s | tentative            | avg_pairwise_distance_115s is descriptively flat between Mirage and Inferno; interpretation is non-causal.                       |
| structure.pairwise_distance.late  | avg_pairwise_distance_115s | insufficient         | avg pairwise distance 115s is higher in B-plant rounds than A-plant rounds; interpretation is non-causal.                        |
| structure.pairwise_distance.late  | avg_pairwise_distance_115s | tentative            | avg pairwise distance 115s is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label. |
| structure.pairwise_distance.late  | avg_pairwise_distance_115s | tentative            | avg pairwise distance 115s is higher in B-plant rounds than A-plant rounds; interpretation is non-causal.                        |
| structure.pairwise_distance.late  | avg_pairwise_distance_115s | tentative            | avg pairwise distance 115s is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label. |
| structure.team_spread.early       | team_spread_10s            | moderate_descriptive | team spread 10s is lower on Inferno than Mirage; interpretation is non-causal.                                                   |
| structure.team_spread.early       | team_spread_20s            | tentative            | team_spread_20s is descriptively flat between Mirage and Inferno; interpretation is non-causal.                                  |
| structure.team_spread.early       | team_spread_15s            | insufficient         | team spread 15s is higher in B-plant rounds than A-plant rounds; interpretation is non-causal.                                   |

## Semantic Control Findings
| finding_concept_id                        | representative_feature   | evidence_quality   | representative_text                                                                                                             |
|:------------------------------------------|:-------------------------|:-------------------|:--------------------------------------------------------------------------------------------------------------------------------|
| semantic.a_pressure.player_presence.early | players_a_pressure_0_15  | tentative          | players a pressure 0 15 is lower on Inferno than Mirage; interpretation is non-causal.                                          |
| semantic.a_pressure.player_presence.early | players_a_pressure_0_20  | insufficient       | players_a_pressure_0_20 is descriptively flat between Mirage and Inferno; interpretation is non-causal.                         |
| semantic.a_pressure.player_presence.early | players_a_pressure_0_20  | insufficient       | players a pressure 0 20 is higher in B-plant rounds than A-plant rounds; interpretation is non-causal.                          |
| semantic.a_pressure.player_presence.early | players_a_pressure_25_35 | insufficient       | players_a_pressure_25_35 is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal. |
| semantic.a_pressure.player_presence.early | players_a_pressure_0_15  | tentative          | players a pressure 0 15 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.                           |
| semantic.a_pressure.player_presence.early | players_a_pressure_15_25 | tentative          | players_a_pressure_15_25 is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal. |
| semantic.a_pressure.player_presence.late  | players_a_pressure_85_95 | tentative          | players_a_pressure_85_95 is descriptively flat between Mirage and Inferno; interpretation is non-causal.                        |
| semantic.a_pressure.player_presence.late  | players_a_pressure_0_85  | tentative          | players_a_pressure_0_85 is descriptively flat between Mirage and Inferno; interpretation is non-causal.                         |
| semantic.a_pressure.player_presence.late  | players_a_pressure_0_105 | tentative          | players a pressure 0 105 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.                          |
| semantic.a_pressure.player_presence.late  | players_a_pressure_75_85 | tentative          | players a pressure 75 85 is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label.  |
| semantic.a_pressure.player_presence.late  | players_a_pressure_0_115 | tentative          | players a pressure 0 115 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.                          |
| semantic.a_pressure.player_presence.late  | players_a_pressure_0_115 | tentative          | players a pressure 0 115 is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label.  |
| semantic.a_pressure.player_presence.mid   | players_a_pressure_0_45  | tentative          | players a pressure 0 45 is lower on Inferno than Mirage; interpretation is non-causal.                                          |
| semantic.a_pressure.player_presence.mid   | players_a_pressure_0_65  | tentative          | players_a_pressure_0_65 is descriptively flat between Mirage and Inferno; interpretation is non-causal.                         |
| semantic.a_pressure.player_presence.mid   | players_a_pressure_55_65 | tentative          | players a pressure 55 65 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.                          |

## Plant-Site Findings
| finding_concept_id                        | representative_feature   | evidence_quality   | representative_text                                                                                               |
|:------------------------------------------|:-------------------------|:-------------------|:------------------------------------------------------------------------------------------------------------------|
| plant_progression.players_alive.early     | players_alive_15s        | tentative          | players_alive_15s is descriptively flat between Mirage and Inferno; interpretation is non-causal.                 |
| plant_progression.players_alive.early     | players_alive_15s        | insufficient       | players_alive_15s is descriptively flat between A-plant rounds and B-plant rounds; interpretation is non-causal.  |
| plant_progression.players_alive.early     | players_alive_20s        | insufficient       | players_alive_20s is descriptively flat between A-plant rounds and B-plant rounds; interpretation is non-causal.  |
| plant_progression.players_alive.late      | players_alive_115s       | insufficient       | players_alive_115s is descriptively flat between Mirage and Inferno; interpretation is non-causal.                |
| plant_progression.players_alive.late      | players_alive_115s       | insufficient       | players_alive_115s is descriptively flat between A-plant rounds and B-plant rounds; interpretation is non-causal. |
| plant_progression.players_alive.late      | players_alive_115s       | insufficient       | players alive 115s is higher in B-plant rounds than A-plant rounds; interpretation is non-causal.                 |
| semantic.a_pressure.player_presence.early | players_a_pressure_0_20  | insufficient       | players_a_pressure_0_20 is descriptively flat between Mirage and Inferno; interpretation is non-causal.           |
| semantic.a_pressure.player_presence.early | players_a_pressure_0_20  | insufficient       | players a pressure 0 20 is higher in B-plant rounds than A-plant rounds; interpretation is non-causal.            |
| semantic.a_pressure.player_presence.early | players_a_pressure_0_15  | tentative          | players a pressure 0 15 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.             |
| semantic.a_pressure.player_presence.late  | players_a_pressure_0_85  | tentative          | players_a_pressure_0_85 is descriptively flat between Mirage and Inferno; interpretation is non-causal.           |
| semantic.a_pressure.player_presence.late  | players_a_pressure_0_105 | tentative          | players a pressure 0 105 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.            |
| semantic.a_pressure.player_presence.late  | players_a_pressure_0_115 | tentative          | players a pressure 0 115 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.            |
| semantic.a_pressure.player_presence.mid   | players_a_pressure_0_65  | tentative          | players_a_pressure_0_65 is descriptively flat between Mirage and Inferno; interpretation is non-causal.           |
| semantic.a_pressure.player_presence.mid   | players_a_pressure_55_65 | tentative          | players a pressure 55 65 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.            |
| semantic.a_pressure.player_presence.mid   | players_a_pressure_0_65  | tentative          | players a pressure 0 65 is lower in B-plant rounds than A-plant rounds; interpretation is non-causal.             |

## A/B Pattern Findings
| feature_name               | mirage_direction   | inferno_direction   | same_nonflat_direction   | status                     |
|:---------------------------|:-------------------|:--------------------|:-------------------------|:---------------------------|
| avg_pairwise_distance_10s  | negative           | positive            | False                    | opposite_or_weak_direction |
| avg_pairwise_distance_115s | positive           | positive            | True                     | ok                         |
| avg_pairwise_distance_15s  | negative           | positive            | False                    | opposite_or_weak_direction |
| avg_pairwise_distance_20s  | negative           | negative            | True                     | ok                         |
| avg_pairwise_distance_25s  | negative           | positive            | False                    | opposite_or_weak_direction |
| first_molotov_time         | positive           | positive            | True                     | ok                         |
| first_smoke_time           | positive           | negative            | False                    | opposite_or_weak_direction |
| first_utility_time         | negative           | positive            | False                    | opposite_or_weak_direction |
| flashes_used_0_105         | positive           | negative            | False                    | opposite_or_weak_direction |
| flashes_used_0_115         | negative           | negative            | True                     | ok                         |
| flashes_used_0_15          | flat               | negative            | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_20          | flat               | flat                | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_25          | flat               | flat                | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_35          | flat               | flat                | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_45          | flat               | negative            | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_55          | flat               | negative            | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_65          | flat               | negative            | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_75          | flat               | negative            | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_85          | flat               | negative            | False                    | flat_on_one_or_more_maps   |
| flashes_used_0_95          | positive           | negative            | False                    | opposite_or_weak_direction |

## Plant vs No-Plant Findings
| finding_concept_id                                    | representative_feature   | evidence_quality   | representative_text                                                                                                          |
|:------------------------------------------------------|:-------------------------|:-------------------|:-----------------------------------------------------------------------------------------------------------------------------|
| plant_progression.freeze_end_tick.non_temporal        | freeze_end_tick          | insufficient       | freeze end tick is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label.        |
| plant_progression.freeze_end_tick.non_temporal        | freeze_end_tick          | insufficient       | freeze end tick is higher in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label.       |
| plant_progression.half.non_temporal                   | half                     | tentative          | half is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.                  |
| plant_progression.half.non_temporal                   | half                     | insufficient       | half is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.                  |
| plant_progression.is_early_round.non_temporal         | is_early_round           | insufficient       | is_early_round is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.        |
| plant_progression.is_early_round.non_temporal         | is_early_round           | insufficient       | is_early_round is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.        |
| plant_progression.is_late_round.non_temporal          | is_late_round            | tentative          | is_late_round is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.         |
| plant_progression.is_late_round.non_temporal          | is_late_round            | insufficient       | is_late_round is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.         |
| plant_progression.is_pistol_round.non_temporal        | is_pistol_round          | insufficient       | is_pistol_round is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.       |
| plant_progression.is_pistol_round.non_temporal        | is_pistol_round          | insufficient       | is_pistol_round is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.       |
| plant_progression.players_alive.early                 | players_alive_25s        | tentative          | players_alive_25s is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.     |
| plant_progression.players_alive.early                 | players_alive_25s        | insufficient       | players_alive_25s is descriptively flat between planted rounds and no-target-plant rounds; interpretation is non-causal.     |
| plant_progression.players_alive.late                  | players_alive_115s       | tentative          | players alive 115s is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label.     |
| plant_progression.players_alive.late                  | players_alive_115s       | tentative          | players alive 115s is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label.     |
| plant_progression.round_duration_seconds.non_temporal | round_duration_seconds   | tentative          | round duration seconds is lower in no-target-plant rounds than planted rounds; no-plant is descriptive, not a failure label. |

## Findings Downgraded by Exposure
| finding_id   | finding_concept_id               | feature_name               |   reference_exposure_share |   comparison_exposure_share | exposure_sensitivity_status   |
|:-------------|:---------------------------------|:---------------------------|---------------------------:|----------------------------:|:------------------------------|
| mm_eda_0006  | structure.pairwise_distance.late | avg_pairwise_distance_115s |                 nan        |                  nan        | insufficient_exposure         |
| mm_eda_0007  | structure.pairwise_distance.late | avg_pairwise_distance_115s |                 nan        |                  nan        | insufficient_exposure         |
| mm_eda_0008  | structure.pairwise_distance.late | avg_pairwise_distance_115s |                 nan        |                  nan        | insufficient_exposure         |
| mm_eda_0009  | structure.pairwise_distance.late | avg_pairwise_distance_115s |                 nan        |                  nan        | insufficient_exposure         |
| mm_eda_0010  | structure.pairwise_distance.late | avg_pairwise_distance_115s |                 nan        |                  nan        | insufficient_exposure         |
| mm_eda_0041  | utility.flash.late_usage         | flashes_used_0_105         |                   0.338889 |                    0.553846 | insufficient_exposure         |
| mm_eda_0042  | utility.flash.late_usage         | flashes_used_0_105         |                   0.338889 |                    0.553846 | insufficient_exposure         |
| mm_eda_0043  | utility.flash.late_usage         | flashes_used_0_105         |                   0.338889 |                    0.553846 | insufficient_exposure         |
| mm_eda_0044  | utility.flash.late_usage         | flashes_used_0_105         |                   0.338889 |                    0.553846 | insufficient_exposure         |
| mm_eda_0045  | utility.flash.late_usage         | flashes_used_0_105         |                   0.338889 |                    0.553846 | insufficient_exposure         |
| mm_eda_0046  | utility.flash.late_usage         | flashes_used_0_115         |                   0.244444 |                    0.415385 | insufficient_exposure         |
| mm_eda_0047  | utility.flash.late_usage         | flashes_used_0_115         |                   0.244444 |                    0.415385 | insufficient_exposure         |
| mm_eda_0048  | utility.flash.late_usage         | flashes_used_0_115         |                   0.244444 |                    0.415385 | insufficient_exposure         |
| mm_eda_0049  | utility.flash.late_usage         | flashes_used_0_115         |                   0.244444 |                    0.415385 | insufficient_exposure         |
| mm_eda_0050  | utility.flash.late_usage         | flashes_used_0_115         |                   0.244444 |                    0.415385 | insufficient_exposure         |
| mm_eda_0086  | utility.flash.mid_usage          | flashes_used_0_75          |                   0.666667 |                    0.846154 | insufficient_exposure         |
| mm_eda_0087  | utility.flash.mid_usage          | flashes_used_0_75          |                   0.666667 |                    0.846154 | insufficient_exposure         |
| mm_eda_0088  | utility.flash.mid_usage          | flashes_used_0_75          |                   0.666667 |                    0.846154 | insufficient_exposure         |
| mm_eda_0089  | utility.flash.mid_usage          | flashes_used_0_75          |                   0.666667 |                    0.846154 | insufficient_exposure         |
| mm_eda_0090  | utility.flash.mid_usage          | flashes_used_0_75          |                   0.666667 |                    0.846154 | insufficient_exposure         |

## Findings Sensitive to One Demo
| finding_id   | finding_concept_id                |   demos_evaluated |   direction_flips | status   |
|:-------------|:----------------------------------|------------------:|------------------:|:---------|
| mm_eda_0005  | structure.pairwise_distance.early |                14 |                 1 | warning  |
| mm_eda_0008  | structure.pairwise_distance.late  |                15 |                 1 | warning  |
| mm_eda_0011  | structure.pairwise_distance.early |                17 |                 1 | warning  |
| mm_eda_0016  | structure.pairwise_distance.early |                17 |                 1 | warning  |
| mm_eda_0020  | structure.pairwise_distance.early |                14 |                 1 | warning  |
| mm_eda_0021  | structure.pairwise_distance.early |                17 |                 1 | warning  |
| mm_eda_0025  | structure.pairwise_distance.early |                14 |                 1 | warning  |
| mm_eda_0041  | utility.flash.late_usage          |                17 |                 1 | warning  |
| mm_eda_0046  | utility.flash.late_usage          |                17 |                 1 | warning  |
| mm_eda_0054  | utility.flash.early_usage         |                17 |                 1 | warning  |
| mm_eda_0056  | utility.flash.early_usage         |                17 |                 1 | warning  |
| mm_eda_0058  | utility.flash.early_usage         |                15 |                 1 | warning  |
| mm_eda_0059  | utility.flash.early_usage         |                17 |                 1 | warning  |
| mm_eda_0061  | utility.flash.early_usage         |                17 |                 1 | warning  |
| mm_eda_0063  | utility.flash.early_usage         |                15 |                 1 | warning  |
| mm_eda_0064  | utility.flash.early_usage         |                17 |                 1 | warning  |
| mm_eda_0069  | utility.flash.early_usage         |                17 |                 1 | warning  |
| mm_eda_0076  | utility.flash.mid_usage           |                17 |                 1 | warning  |
| mm_eda_0077  | utility.flash.mid_usage           |                17 |                 1 | warning  |
| mm_eda_0078  | utility.flash.mid_usage           |                15 |                 1 | warning  |

## Findings Sensitive to Opponent
_No rows._

## Contradictory Evidence
| finding_concept_id                                  |   conflicting_candidate_count | severity   | requires_manual_review   |
|:----------------------------------------------------|------------------------------:|:-----------|:-------------------------|
| direct_feature.freeze_end_tick.non_temporal         |                             0 | none       | False                    |
| direct_feature.half.non_temporal                    |                             0 | none       | False                    |
| direct_feature.is_early_round.non_temporal          |                             0 | none       | False                    |
| direct_feature.is_late_round.non_temporal           |                             0 | none       | False                    |
| direct_feature.is_pistol_round.non_temporal         |                             0 | none       | False                    |
| direct_feature.round_duration_seconds.non_temporal  |                             0 | none       | False                    |
| direct_feature.round_duration_ticks.non_temporal    |                             0 | none       | False                    |
| direct_feature.round_end_tick.non_temporal          |                             0 | none       | False                    |
| direct_feature.round_start_tick.non_temporal        |                             0 | none       | False                    |
| direct_feature.score_diff_before_round.non_temporal |                             0 | none       | False                    |
| plant_progression.freeze_end_tick.non_temporal      |                             0 | none       | False                    |
| plant_progression.freeze_end_tick.non_temporal      |                             0 | none       | False                    |
| plant_progression.half.non_temporal                 |                             0 | none       | False                    |
| plant_progression.half.non_temporal                 |                             0 | none       | False                    |
| plant_progression.is_early_round.non_temporal       |                             0 | none       | False                    |
| plant_progression.is_early_round.non_temporal       |                             0 | none       | False                    |
| plant_progression.is_late_round.non_temporal        |                             0 | none       | False                    |
| plant_progression.is_late_round.non_temporal        |                             0 | none       | False                    |
| plant_progression.is_pistol_round.non_temporal      |                             0 | none       | False                    |
| plant_progression.is_pistol_round.non_temporal      |                             0 | none       | False                    |

## Excluded Comparisons
| feature_name                   | hardened_exclusion_reason   | secondary_exclusion_reasons   | taxonomy_changed   |
|:-------------------------------|:----------------------------|:------------------------------|:-------------------|
| molotovs_to_a_pressure_0_105   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_115   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_15    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_20    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_25    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_35    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_45    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_55    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_65    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_75    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_85    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_0_95    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_105_115 | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_15_25   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_25_35   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_35_45   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_45_55   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_55_65   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_65_75   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_75_85   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_85_95   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_a_pressure_95_105  | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_b_pressure_0_105   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_b_pressure_0_115   | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_b_pressure_0_15    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_b_pressure_0_20    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_b_pressure_0_25    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_b_pressure_0_35    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_b_pressure_0_45    | unresolved_endpoint         | unresolved_endpoint           | False              |
| molotovs_to_b_pressure_0_55    | unresolved_endpoint         | unresolved_endpoint           | False              |

## Modeling Context
| finding_concept_id                                  | representative_feature   | safe_as_modeling_context   | leakage_risk    | notes                            |
|:----------------------------------------------------|:-------------------------|:---------------------------|:----------------|:---------------------------------|
| direct_feature.freeze_end_tick.non_temporal         | freeze_end_tick          | False                      | review_required | Not automatic feature selection. |
| direct_feature.half.non_temporal                    | half                     | False                      | review_required | Not automatic feature selection. |
| direct_feature.is_early_round.non_temporal          | is_early_round           | False                      | review_required | Not automatic feature selection. |
| direct_feature.is_late_round.non_temporal           | is_late_round            | False                      | review_required | Not automatic feature selection. |
| direct_feature.is_pistol_round.non_temporal         | is_pistol_round          | False                      | review_required | Not automatic feature selection. |
| direct_feature.round_duration_seconds.non_temporal  | round_duration_seconds   | False                      | horizon_risk    | Not automatic feature selection. |
| direct_feature.round_duration_ticks.non_temporal    | round_duration_ticks     | False                      | horizon_risk    | Not automatic feature selection. |
| direct_feature.round_end_tick.non_temporal          | round_end_tick           | False                      | review_required | Not automatic feature selection. |
| direct_feature.round_start_tick.non_temporal        | round_start_tick         | False                      | review_required | Not automatic feature selection. |
| direct_feature.score_diff_before_round.non_temporal | score_diff_before_round  | True                       | review_required | Not automatic feature selection. |
| plant_progression.freeze_end_tick.non_temporal      | freeze_end_tick          | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.freeze_end_tick.non_temporal      | freeze_end_tick          | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.half.non_temporal                 | half                     | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.half.non_temporal                 | half                     | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.is_early_round.non_temporal       | is_early_round           | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.is_early_round.non_temporal       | is_early_round           | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.is_late_round.non_temporal        | is_late_round            | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.is_late_round.non_temporal        | is_late_round            | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.is_pistol_round.non_temporal      | is_pistol_round          | False                      | horizon_risk    | Not automatic feature selection. |
| plant_progression.is_pistol_round.non_temporal      | is_pistol_round          | False                      | horizon_risk    | Not automatic feature selection. |

## Sample Limitations
The Inferno sample remains small and exploratory. Hardened findings are context for Stage 8.11, not automatic feature selection.

## Readiness
`ready_for_stage_8_11 = True`.

## Next Stage
Stage 8.11 can run an Inferno A/B exploratory baseline if readiness remains true. This report does not start model training.
