# Inferno Physical Region & Tactical Semantic Mapping

## Purpose
Formalize Inferno parser places into auditable physical regions and tactical semantic groups before running Inferno features.

## Stage 8.6 Evidence
|   observed_places |   observed_ticks |   mapped_places |   mapped_tick_share | stage_8_6_ready   | ready_for_inferno_feature_run   | status   |
|------------------:|-----------------:|----------------:|--------------------:|:------------------|:--------------------------------|:---------|
|                24 |         10080330 |              24 |                   1 | True              | True                            | ok       |

## Raw Parser Places
| raw_place   |   tick_count |   demo_count |   round_count |   x_median |   y_median |   z_median |
|:------------|-------------:|-------------:|--------------:|-----------:|-----------:|-----------:|
| Banana      |      1754327 |            5 |           122 |    387.264 |  1875.52   |  136.031   |
| BombsiteB   |      1276346 |            5 |           122 |    580.267 |  2735.96   |  161.031   |
| CTSpawn     |      1248672 |            5 |           122 |   2353     |  2079      |  134.505   |
| BombsiteA   |      1115772 |            5 |           122 |   2066.5   |   293.684  |  160.027   |
| TSpawn      |      1040577 |            5 |           122 |  -1604.13  |   419.577  |  -63.9688  |
| Middle      |       600563 |            5 |           122 |    569.467 |   602.454  |   95.8541  |
| Apartments  |       528750 |            5 |           121 |   1236.53  |  -257.105  |  256.031   |
| TopofMid    |       396177 |            5 |           117 |   1397.25  |   587.202  |  134.457   |
| Ruins       |       327388 |            5 |           122 |   1177.86  |  2814.6    |  128.031   |
| Pit         |       288719 |            5 |            94 |   2439.51  |  -182.227  |   97.938   |
| Arch        |       267679 |            5 |           113 |   1779.38  |  1208.21   |  169.117   |
| TRamp       |       258618 |            5 |           122 |   -128.695 |   884.041  |   56.2235  |
| SecondMid   |       254234 |            5 |           120 |    717.635 |   -19.7757 |   89.0312  |
| LowerMid    |       170330 |            5 |           122 |   -619.969 |   581.943  |   -6.82446 |
| Balcony     |       168711 |            5 |           103 |   2076.05  |  -232.995  |  258.633   |
| Library     |       139233 |            5 |           119 |   2510.38  |  1244.48   |  160.031   |
| Quad        |        80820 |            5 |            67 |   1428.57  |   -77.2762 |  140.583   |
| BackAlley   |        52015 |            5 |            66 |    886.865 |  -646.323  |   91.6612  |
| Underpass   |        40808 |            5 |            64 |    288.883 |   648.063  |   17.3875  |
| Bridge      |        18359 |            5 |            38 |   -374.645 |   -77.4408 |  192.031   |
| Upstairs    |        17685 |            5 |            45 |   -510.683 |   219.524  |  192.031   |
| Deck        |        15736 |            5 |            16 |    102.354 |    44.0587 |  208.031   |
| Graveyard   |        14148 |            3 |            16 |   2513.13  |   448.509  |  216.031   |
| Kitchen     |         4663 |            5 |            20 |   -199.773 |   252.272  |  192.031   |

## Physical Region Mapping
| raw_place   | proposed_region_id   | mapping_type   | mapping_confidence   | semantic_tags            | review_status   |
|:------------|:---------------------|:---------------|:---------------------|:-------------------------|:----------------|
| Banana      | banana               | direct         | high                 | b_pressure               | accepted        |
| BombsiteB   | bombsiteb            | direct         | high                 | site_b                   | accepted        |
| CTSpawn     | ctspawn              | direct         | high                 | ct_space                 | accepted        |
| BombsiteA   | bombsitea            | direct         | high                 | site_a                   | accepted        |
| TSpawn      | tspawn               | direct         | high                 | t_spawn_area             | accepted        |
| Middle      | middle               | direct         | high                 | mid_control              | accepted        |
| Apartments  | apartments           | direct         | high                 | a_pressure               | accepted        |
| TopofMid    | topofmid             | direct         | high                 | mid_control              | accepted        |
| Ruins       | ruins                | direct         | high                 | b_pressure               | accepted        |
| Pit         | pit                  | direct         | high                 | a_pressure               | accepted        |
| Arch        | arch                 | direct         | high                 | ct_space|rotation        | accepted        |
| TRamp       | tramp                | direct         | high                 | t_spawn_area|mid_control | accepted        |
| SecondMid   | secondmid            | direct         | high                 | mid_control              | accepted        |
| LowerMid    | lowermid             | direct         | high                 | mid_control              | accepted        |
| Balcony     | balcony              | direct         | high                 | a_pressure               | accepted        |
| Library     | library              | direct         | high                 | ct_space|rotation        | accepted        |
| Quad        | quad                 | direct         | high                 | a_pressure               | accepted        |
| BackAlley   | backalley            | direct         | high                 | a_pressure               | accepted        |
| Underpass   | underpass            | direct         | high                 | mid_control|rotation     | accepted        |
| Bridge      | second_mid_upper     | grouped        | medium               | mid_control|rotation     | accepted        |
| Upstairs    | second_mid_upper     | grouped        | medium               | mid_control|rotation     | accepted        |
| Deck        | second_mid_upper     | grouped        | medium               | mid_control|rotation     | accepted        |
| Graveyard   | graveyard            | direct         | high                 | a_pressure               | accepted        |
| Kitchen     | second_mid_upper     | grouped        | medium               | mid_control|rotation     | accepted        |

## Grouped Places
| raw_place   | proposed_region_id   | semantic_tags        | notes                                                                             |
|:------------|:---------------------|:---------------------|:----------------------------------------------------------------------------------|
| Bridge      | second_mid_upper     | mid_control|rotation | Grouped with nearby elevated connector places from Stage 8.6 coordinate evidence. |
| Upstairs    | second_mid_upper     | mid_control|rotation | Grouped with nearby elevated connector places from Stage 8.6 coordinate evidence. |
| Deck        | second_mid_upper     | mid_control|rotation | Grouped with nearby elevated connector places from Stage 8.6 coordinate evidence. |
| Kitchen     | second_mid_upper     | mid_control|rotation | Grouped with nearby elevated connector places from Stage 8.6 coordinate evidence. |

## Unresolved Places
_No rows available._

## Bombsites
BombsiteA resolves to `bombsitea` / A and BombsiteB resolves to `bombsiteb` / B through `geometry.area_names`.

## Tactical Semantic Groups
| semantic_id   |   physical_region_count | physical_regions                                                    | source_places                                                                   | mapping_confidence   | coverage_status   |
|:--------------|------------------------:|:--------------------------------------------------------------------|:--------------------------------------------------------------------------------|:---------------------|:------------------|
| a_pressure    |                       6 | apartments|pit|balcony|quad|backalley|graveyard                     | Apartments|BackAlley|Balcony|Graveyard|Pit|Quad                                 | high                 | resolved          |
| b_pressure    |                       2 | banana|ruins                                                        | Banana|Ruins                                                                    | high                 | resolved          |
| ct_space      |                       3 | ctspawn|arch|library                                                | Arch|CTSpawn|Library                                                            | high                 | resolved          |
| mid_control   |                       7 | middle|topofmid|tramp|secondmid|lowermid|second_mid_upper|underpass | Bridge|Deck|Kitchen|LowerMid|Middle|SecondMid|TRamp|TopofMid|Underpass|Upstairs | medium               | resolved          |
| rotation      |                       4 | arch|library|second_mid_upper|underpass                             | Arch|Bridge|Deck|Kitchen|Library|Underpass|Upstairs                             | medium               | resolved          |
| site_a        |                       1 | bombsitea                                                           | BombsiteA                                                                       | high                 | resolved          |
| site_b        |                       1 | bombsiteb                                                           | BombsiteB                                                                       | high                 | resolved          |
| t_spawn_area  |                       2 | tspawn|tramp                                                        | TRamp|TSpawn                                                                    | high                 | resolved          |

## Semantic Coverage
| semantic_id   |   frozen_feature_count | resolved   | physical_regions                                                    | coverage_status   | blocking   |
|:--------------|-----------------------:|:-----------|:--------------------------------------------------------------------|:------------------|:-----------|
| a_pressure    |                     88 | True       | apartments|pit|balcony|quad|backalley|graveyard                     | resolved          | False      |
| b_pressure    |                     88 | True       | banana|ruins                                                        | resolved          | False      |
| ct_space      |                     44 | True       | ctspawn|arch|library                                                | resolved          | False      |
| mid_control   |                     88 | True       | middle|topofmid|tramp|secondmid|lowermid|second_mid_upper|underpass | resolved          | False      |
| rotation      |                      0 | True       | arch|library|second_mid_upper|underpass                             | resolved          | False      |
| site_a        |                      0 | True       | bombsitea                                                           | resolved          | False      |
| site_b        |                      0 | True       | bombsiteb                                                           | resolved          | False      |
| t_spawn_area  |                      0 | True       | tspawn|tramp                                                        | resolved          | False      |

## Coordinate Validation
| region_id        |   source_place_count | source_places                |   center_spread |   vertical_spread | status   |
|:-----------------|---------------------:|:-----------------------------|----------------:|------------------:|:---------|
| apartments       |                    1 | Apartments                   |           0     |          237.828  | ok       |
| arch             |                    1 | Arch                         |           0     |           86.3585 | ok       |
| backalley        |                    1 | BackAlley                    |           0     |           71.5938 | ok       |
| balcony          |                    1 | Balcony                      |           0     |          256.531  | ok       |
| banana           |                    1 | Banana                       |           0     |          200.736  | ok       |
| bombsitea        |                    1 | BombsiteA                    |           0     |          229.301  | ok       |
| bombsiteb        |                    1 | BombsiteB                    |           0     |          219.282  | ok       |
| ctspawn          |                    1 | CTSpawn                      |           0     |          156.796  | ok       |
| graveyard        |                    1 | Graveyard                    |           0     |          168.152  | ok       |
| library          |                    1 | Library                      |           0     |           68.4423 | ok       |
| lowermid         |                    1 | LowerMid                     |           0     |          165.517  | ok       |
| middle           |                    1 | Middle                       |           0     |          202.093  | ok       |
| pit              |                    1 | Pit                          |           0     |          177.305  | ok       |
| quad             |                    1 | Quad                         |           0     |          212.781  | ok       |
| ruins            |                    1 | Ruins                        |           0     |          176.453  | ok       |
| second_mid_upper |                    4 | Bridge|Deck|Kitchen|Upstairs |         637.855 |          262.903  | ok       |
| secondmid        |                    1 | SecondMid                    |           0     |          309.406  | ok       |
| topofmid         |                    1 | TopofMid                     |           0     |          163.952  | ok       |
| tramp            |                    1 | TRamp                        |           0     |          178.902  | ok       |
| tspawn           |                    1 | TSpawn                       |           0     |          142.005  | ok       |
| underpass        |                    1 | Underpass                    |           0     |           93.6562 | ok       |

## Feature Contract v2
Feature Contract v2 adds generation scope, coordinate dependency, and cross-map comparability metadata without changing feature names or feature values.

## Cross-Map Comparability
A feature being available on Inferno does not mean a Mirage-trained model can predict Inferno. Raw coordinate features require normalization; semantic-region features require validated semantic mapping.

## Candidate Feature Portability
| feature_name              | generation_scope   | coordinate_dependency   | available_on_inferno   | cross_map_comparable   | cross_map_comparison_mode   | status                   |
|:--------------------------|:-------------------|:------------------------|:-----------------------|:-----------------------|:----------------------------|:-------------------------|
| round_num                 | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| half                      | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| team_center_x_10s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| team_center_y_10s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| team_center_z_10s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| team_center_x_20s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| team_center_y_20s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| team_spread_10s           | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| avg_pairwise_distance_10s | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| players_alive_10s         | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| time_a_pressure_0_20      | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| team_smokes_start         | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| team_flashes_start        | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| is_pistol_round           | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| team_center_x_15s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| team_center_y_15s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| team_spread_15s           | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| avg_pairwise_distance_15s | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| players_alive_15s         | global             | none                    | True                   | True                   | direct                      | available_comparable     |
| team_center_x_25s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| team_center_y_25s         | global             | raw_map_coordinates     | True                   | False                  | normalized_required         | available_not_comparable |
| players_a_pressure_0_15   | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| time_a_pressure_0_15      | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| time_b_pressure_0_15      | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| time_a_pressure_15_25     | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| players_a_pressure_25_35  | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| time_a_pressure_25_35     | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| players_a_pressure_0_25   | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| time_a_pressure_0_25      | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| time_b_pressure_0_25      | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |
| time_a_pressure_0_35      | map_abstract       | region_semantic         | True                   | True                   | semantic                    | available_comparable     |

## Mirage Regression
Latest recorded Mirage regression passed: `true`.

## Unknowns
_No rows available._

## Readiness
| audit_id                         | map_id   | target_team   | stage_8_6_ready   |   observed_places |   mapped_places |   unmapped_places |   observed_ticks |   mapped_ticks |   mapped_tick_share |   physical_regions |   required_semantics |   resolved_semantics |   missing_semantics | bombsite_a_resolved   | bombsite_b_resolved   |   frozen_map_abstract_features |   supported_map_abstract_features |   unsupported_map_abstract_features |   candidate_features |   candidate_features_available |   candidate_features_cross_map_comparable | feature_contract_version   | mirage_regression_passed   |   critical_unknowns |   warnings | ready_for_inferno_feature_run   | status   | created_at                       |
|:---------------------------------|:---------|:--------------|:------------------|------------------:|----------------:|------------------:|-----------------:|---------------:|--------------------:|-------------------:|---------------------:|---------------------:|--------------------:|:----------------------|:----------------------|-------------------------------:|----------------------------------:|------------------------------------:|---------------------:|-------------------------------:|------------------------------------------:|:---------------------------|:---------------------------|--------------------:|-----------:|:--------------------------------|:---------|:---------------------------------|
| inferno_region_mapping_stage_8_7 | inferno  | Vitality      | True              |                24 |              24 |                 0 |         10080330 |       10080330 |                   1 |                 21 |                    4 |                    4 |                   0 | True                  | True                  |                            308 |                               308 |                                   0 |                   31 |                             31 |                                        22 | v2                         | True                       |                   0 |          0 | True                            | ok       | 2026-08-18T20:49:43.577243+00:00 |

## Next Stage
Next: Stage 8.8 -- Inferno Feature Pipeline Run & Multi-Map Gold Storage. Do not start it automatically.
