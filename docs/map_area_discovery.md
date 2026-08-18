# Generic Map Area Discovery

## Purpose
Stage 8.6 discovers real parser-reported map places and coordinate evidence for already parsed maps.

## Input Data
`data/silver/parsed_demos/ticks.parquet` is scanned by scoped `source_parse_id`; the stage avoids loading full tick tables into pandas.

## Canonical Map Scope
Map scope is resolved through `src.maps.identity`, so aliases such as `Inferno`, `inferno`, and `de_inferno` point to the same canonical map id.

## Place Column
Supported place columns, in order: `last_place_name, place_name, player_last_place_name, place`.

## Discovery Method
The stage aggregates raw place names, coordinate percentiles, demo/round/player coverage, name stability, vertical spread, and deterministic coordinate samples. It does not infer tactical semantic groups.

## Mirage Results
| map_id   | map_name   | target_team   |   demo_count |   round_count |   tick_count | place_column   |   place_non_null_rows |   place_non_null_share |   unique_raw_places |   places_seen_all_demos |   places_seen_multiple_demos |   places_seen_one_demo | xyz_available   | discovery_status   | ready_for_region_mapping   | created_at                       |
|:---------|:-----------|:--------------|-------------:|--------------:|-------------:|:---------------|----------------------:|-----------------------:|--------------------:|------------------------:|-----------------------------:|-----------------------:|:----------------|:-------------------|:---------------------------|:---------------------------------|
| mirage   | Mirage     | Vitality      |           19 |           410 |     30206610 | place          |              30206608 |                      1 |                  23 |                      23 |                           23 |                      0 | True            | ok                 | True                       | 2026-08-18T20:20:40.713805+00:00 |

## Mirage Registry Crosswalk
| map_id   | map_name   | target_team   | raw_place      | normalized_place_id   |   tick_count | matched_region_id   | matched_region_display_name   | match_source   |   match_count | matched   | ambiguous   | candidate_regions   | semantic_tags   | status   | notes   |
|:---------|:-----------|:--------------|:---------------|:----------------------|-------------:|:--------------------|:------------------------------|:---------------|--------------:|:----------|:------------|:--------------------|:----------------|:---------|:--------|
| mirage   | Mirage     | Vitality      | CTSpawn        | ctspawn               |      5371557 | ct_spawn            | CT Spawn                      | alias          |             3 | True      | False       | ct_spawn            | ct_space        | matched  |         |
| mirage   | Mirage     | Vitality      | BombsiteA      | bombsitea             |      3678157 | a_site              | A Site                        | alias          |             3 | True      | False       | a_site              | site_a          | matched  |         |
| mirage   | Mirage     | Vitality      | TSpawn         | tspawn                |      3668757 | t_spawn             | T Spawn                       | alias          |             3 | True      | False       | t_spawn             | t_spawn_area    | matched  |         |
| mirage   | Mirage     | Vitality      | BombsiteB      | bombsiteb             |      1993443 | b_site              | B Site                        | alias          |             3 | True      | False       | b_site              | site_b          | matched  |         |
| mirage   | Mirage     | Vitality      | PalaceInterior | palaceinterior        |      1912691 | palace              | Palace                        | alias          |             3 | True      | False       | palace              | a_pressure      | matched  |         |
| mirage   | Mirage     | Vitality      | TopofMid       | topofmid              |      1586063 | top_mid             | Top Mid                       | alias          |             3 | True      | False       | top_mid             | mid_control     | matched  |         |
| mirage   | Mirage     | Vitality      | Middle         | middle                |      1350455 | mid                 | Mid                           | alias          |             3 | True      | False       | mid                 | mid_control     | matched  |         |
| mirage   | Mirage     | Vitality      | Catwalk        | catwalk               |      1241982 | catwalk             | Catwalk                       | region_id      |             5 | True      | False       | catwalk             | mid_control     | matched  |         |
| mirage   | Mirage     | Vitality      | Apartments     | apartments            |      1213002 | b_apps              | B Apps                        | alias          |             3 | True      | False       | b_apps              | b_pressure      | matched  |         |
| mirage   | Mirage     | Vitality      | Underpass      | underpass             |      1193279 | jungle              | Jungle                        | alias          |             3 | True      | False       | jungle              | rotation        | matched  |         |
| mirage   | Mirage     | Vitality      | PalaceAlley    | palacealley           |       940217 | palace              | Palace                        | alias          |             3 | True      | False       | palace              | a_pressure      | matched  |         |
| mirage   | Mirage     | Vitality      | SideAlley      | sidealley             |       894315 | jungle              | Jungle                        | alias          |             3 | True      | False       | jungle              | rotation        | matched  |         |
| mirage   | Mirage     | Vitality      | BackAlley      | backalley             |       776787 | b_apps              | B Apps                        | alias          |             3 | True      | False       | b_apps              | b_pressure      | matched  |         |
| mirage   | Mirage     | Vitality      | Connector      | connector             |       743773 | connector           | Connector                     | region_id      |             5 | True      | False       | connector           | mid_control     | matched  |         |
| mirage   | Mirage     | Vitality      | TRamp          | tramp                 |       555497 | a_ramp              | A Ramp                        | alias          |             3 | True      | False       | a_ramp              | a_pressure      | matched  |         |
| mirage   | Mirage     | Vitality      | Shop           | shop                  |       551051 | market              | Market                        | alias          |             3 | True      | False       | market              | ct_space        | matched  |         |
| mirage   | Mirage     | Vitality      | Jungle         | jungle                |       546534 | jungle              | Jungle                        | region_id      |             5 | True      | False       | jungle              | rotation        | matched  |         |
| mirage   | Mirage     | Vitality      | Truck          | truck                 |       508267 | ct_spawn            | CT Spawn                      | alias          |             3 | True      | False       | ct_spawn            | ct_space        | matched  |         |
| mirage   | Mirage     | Vitality      | SnipersNest    | snipersnest           |       473549 | window              | Window                        | alias          |             3 | True      | False       | window              | mid_control     | matched  |         |
| mirage   | Mirage     | Vitality      | House          | house                 |       375833 | b_apps              | B Apps                        | alias          |             3 | True      | False       | b_apps              | b_pressure      | matched  |         |
| mirage   | Mirage     | Vitality      | Stairs         | stairs                |       351426 | a_site              | A Site                        | alias          |             3 | True      | False       | a_site              | site_a          | matched  |         |
| mirage   | Mirage     | Vitality      | Ladder         | ladder                |       198950 | b_short             | B Short                       | alias          |             3 | True      | False       | b_short             | b_pressure      | matched  |         |
| mirage   | Mirage     | Vitality      | Scaffolding    | scaffolding           |        77416 | b_short             | B Short                       | alias          |             3 | True      | False       | b_short             | b_pressure      | matched  |         |

## Inferno Results
| map_id   | map_name   | target_team   |   demo_count |   round_count |   tick_count | place_column   |   place_non_null_rows |   place_non_null_share |   unique_raw_places |   places_seen_all_demos |   places_seen_multiple_demos |   places_seen_one_demo | xyz_available   | discovery_status   | ready_for_region_mapping   | created_at                       |
|:---------|:-----------|:--------------|-------------:|--------------:|-------------:|:---------------|----------------------:|-----------------------:|--------------------:|------------------------:|-----------------------------:|-----------------------:|:----------------|:-------------------|:---------------------------|:---------------------------------|
| inferno  | Inferno    | Vitality      |            5 |           122 |     10081430 | place          |              10081430 |                      1 |                  24 |                      23 |                           24 |                      0 | True            | ok                 | True                       | 2026-08-18T20:20:57.660485+00:00 |

## Coordinate Profiles
| map_id   | raw_place      |   n_observations |      x_p05 |    x_median |      x_p95 |        y_p05 |   y_median |      y_p95 |     z_p05 |   z_median |     z_p95 |
|:---------|:---------------|-----------------:|-----------:|------------:|-----------:|-------------:|-----------:|-----------:|----------:|-----------:|----------:|
| mirage   | Apartments     |          1213002 | -2037.43   | -1563.53    | -1061.36   |   506.393    |   740.669  |   849.969  |  -79.9688 |  -47.9688  |  -23.9688 |
| mirage   | BackAlley      |           776787 |  -946.487  |  -442.93    |  -161.034  |   437.542    |   580.108  |   782.264  | -135.468  |  -79.9688  |  -69.0742 |
| mirage   | BombsiteA      |          3678157 |  -872.38   |  -423.442   |    54.7336 | -2399.83     | -1922.28   | -1327.37   | -179.969  | -167.969   | -102.969  |
| mirage   | BombsiteB      |          1993443 | -2502.2    | -2034.43    | -1314.53   |  -208.468    |   281.087  |   599.93   | -168.824  | -165.969   | -118.969  |
| mirage   | CTSpawn        |          5371557 | -1776      | -1656       |  -980.916  | -2443.39     | -1800      |  -882.02   | -267.602  | -263.969   | -165.129  |
| mirage   | Catwalk        |          1241982 | -1126.67   |  -823.595   |  -174.771  |  -456.176    |  -229.917  |   266.149  | -172.338  | -167.207   | -143.969  |
| mirage   | Connector      |           743773 |  -806.331  |  -678.259   |  -520.135  | -1280.62     | -1126.38   |  -900.966  | -232.771  | -167.969   | -120.175  |
| mirage   | House          |           375833 |   -75.9838 |   376.854   |   649.274  |   632.387    |   798.879  |   857.721  | -135.969  | -135.969   | -106.529  |
| mirage   | Jungle         |           546534 | -1211.08   |  -943.403   |  -788.701  | -1527.93     | -1379.9    | -1304.9    | -167.969  | -167.969   | -155.627  |
| mirage   | Ladder         |           198950 | -1247.71   | -1136.06    |  -986.908  |  -500.621    |  -215.94   |   -73.5199 | -167.969  |  -55.9688  |  -52.1406 |
| mirage   | Middle         |          1350455 | -1039.9    |  -659.467   |   -61.2344 |  -931.058    |  -746.436  |  -538.675  | -274.461  | -259.419   | -167.094  |
| mirage   | PalaceAlley    |           940217 |   563.061  |   755.444   |  1132.07   | -1679.36     | -1288.7    | -1036.08   | -263.969  | -258.354   | -108.969  |
| mirage   | PalaceInterior |          1912691 |    27.6808 |   181.842   |  1035.97   | -2368.02     | -2071.95   | -1436.91   | -175.969  |  -39.9688  |  -39.9688 |
| mirage   | Scaffolding    |            77416 |  -101.688  |     7.96979 |   143.762  | -2179.06     | -2033.74   | -1886.91   |  -39.9688 |  -39.9688  |  -25.8594 |
| mirage   | Shop           |           551051 | -2329.9    | -1911.34    | -1631.65   |  -687.92     |  -553.512  |  -298.628  | -167.969  | -167.969   | -117.469  |
| mirage   | SideAlley      |           894315 |   201.062  |   427.208   |  1040.72   |    41.5216   |   392.228  |   631.229  | -261.595  | -254.971   | -135.969  |
| mirage   | SnipersNest    |           473549 | -1266.78   | -1178.94    | -1115.14   | -1058.28     |  -721.675  |  -494.597  | -167.969  | -167.969   | -119.578  |
| mirage   | Stairs         |           351426 |  -534.064  |  -500.732   |  -402.964  | -1607.03     | -1447.88   | -1309.05   | -159.969  |  -70.4472  |  -39.9688 |
| mirage   | TRamp          |           555497 |   245.216  |   375.265   |   517.162  | -1711.95     | -1610.13   | -1465.65   | -263.969  | -182.429   | -175.969  |
| mirage   | TSpawn         |          3668757 |  1136      |  1216       |  1301.35   |  -823.677    |  -160      |   151.754  | -237.62   | -164.788   | -163.969  |
| mirage   | TopofMid       |          1586063 |   120.533  |   364.008   |   499.04   |  -908.724    |  -432.557  |   -42.8568 | -187.319  | -163.979   | -151.969  |
| mirage   | Truck          |           508267 | -2372.88   | -2175.8     | -2106.75   |   642.519    |   738.871  |   831.058  | -139.579  | -103.484   |  -39.7188 |
| mirage   | Underpass      |          1193279 | -1047.94   |  -940.443   |  -589.829  |  -458.149    |   113.829  |   453.061  | -367.969  | -263.969   |  -81.4829 |
| inferno  | Apartments     |           528750 |   237.228  |  1236.53    |  1904.48   |  -633.479    |  -257.105  |   335.973  |   97.5467 |  256.031   |  261.031  |
| inferno  | Arch           |           267679 |  1547.06   |  1779.38    |  2121.65   |  1030.2      |  1208.21   |  1496.83   |  158.319  |  169.117   |  181.188  |
| inferno  | BackAlley      |            52015 |   504.836  |   886.865   |   959.317  |  -758.81     |  -646.323  |  -358.893  |   88.0312 |   91.6612  |  100.031  |
| inferno  | Balcony        |           168711 |   948.234  |  2076.05    |  2109.88   |  -359.267    |  -232.995  |  -118.681  |  255.514  |  258.633   |  296.531  |
| inferno  | Banana         |          1754327 |    52.4426 |   387.264   |   863.87   |  1128.99     |  1875.52   |  2207.32   |   91.0445 |  136.031   |  179.562  |
| inferno  | BombsiteA      |          1115772 |  1663.4    |  2066.5     |  2399.58   |   -89.9354   |   293.684  |   986.57   |  124.027  |  160.027   |  220.031  |
| inferno  | BombsiteB      |          1276346 |    54.0208 |   580.267   |   948.741  |  2362.09     |  2735.96   |  3384.21   |  133.061  |  161.031   |  241.031  |
| inferno  | Bridge         |            18359 |  -418.693  |  -374.645   |  -325.035  |  -286.878    |   -77.4408 |    21.69   |  192.031  |  192.031   |  223.031  |
| inferno  | CTSpawn        |          1248672 |  1683.97   |  2353       |  2493      |  1806.41     |  2079      |  2724.91   |  124.032  |  134.505   |  160.031  |
| inferno  | Deck           |            15736 |   -18.5956 |   102.354   |   268.114  |    -0.960876 |    44.0587 |   109.664  |  200.531  |  208.031   |  230.055  |
| inferno  | Graveyard      |            14148 |  2445.63   |  2513.13    |  2604.05   |    34.2573   |   448.509  |   559.937  |  148.269  |  216.031   |  253.78   |
| inferno  | Kitchen        |             4663 |  -255.727  |  -199.773   |    22.7067 |    72.0312   |   252.272  |   314.341  |  192.031  |  192.031   |  201.031  |
| inferno  | Library        |           139233 |  2349.14   |  2510.38    |  2616.79   |  1100.43     |  1244.48   |  1524.44   |  157.911  |  160.031   |  209.031  |
| inferno  | LowerMid       |           170330 |  -924.184  |  -619.969   |  -383.462  |  -331.317    |   581.943  |   786.067  |  -33.228  |   -6.82446 |   48.0491 |
| inferno  | Middle         |           600563 |    61.1908 |   569.467   |  1258.65   |   447.063    |   602.454  |   901.087  |   80.0312 |   95.8541  |  123.13   |
| inferno  | Pit            |           288719 |  2076.07   |  2439.51    |  2601.75   |  -474.434    |  -182.227  |   -83.0586 |   93.4119 |   97.938   |  128.469  |
| inferno  | Quad           |            80820 |  1355.04   |  1428.57    |  1568.79   |   -89.9438   |   -77.2762 |   -32.1966 |  132.031  |  140.583   |  278.371  |

## Demo Coverage
| map_id   | raw_place      |   demos_with_place |   demo_coverage_share |   rounds_with_place |   round_coverage_share | coverage_status   |
|:---------|:---------------|-------------------:|----------------------:|--------------------:|-----------------------:|:------------------|
| mirage   | CTSpawn        |                 19 |                   1   |                 410 |               1        | common            |
| mirage   | BombsiteA      |                 19 |                   1   |                 410 |               1        | common            |
| mirage   | TSpawn         |                 19 |                   1   |                 410 |               1        | common            |
| mirage   | BombsiteB      |                 19 |                   1   |                 408 |               0.995122 | common            |
| mirage   | PalaceInterior |                 19 |                   1   |                 359 |               0.87561  | common            |
| mirage   | TopofMid       |                 19 |                   1   |                 367 |               0.895122 | common            |
| mirage   | Middle         |                 19 |                   1   |                 388 |               0.946341 | common            |
| mirage   | Catwalk        |                 19 |                   1   |                 368 |               0.897561 | common            |
| mirage   | Apartments     |                 19 |                   1   |                 283 |               0.690244 | common            |
| mirage   | Underpass      |                 19 |                   1   |                 349 |               0.85122  | common            |
| mirage   | PalaceAlley    |                 19 |                   1   |                 301 |               0.734146 | common            |
| mirage   | SideAlley      |                 19 |                   1   |                 390 |               0.95122  | common            |
| mirage   | BackAlley      |                 19 |                   1   |                 320 |               0.780488 | common            |
| mirage   | Connector      |                 19 |                   1   |                 363 |               0.885366 | common            |
| mirage   | TRamp          |                 19 |                   1   |                 287 |               0.7      | common            |
| mirage   | Shop           |                 19 |                   1   |                 408 |               0.995122 | common            |
| mirage   | Jungle         |                 19 |                   1   |                 389 |               0.94878  | common            |
| mirage   | Truck          |                 19 |                   1   |                 368 |               0.897561 | common            |
| mirage   | SnipersNest    |                 19 |                   1   |                 384 |               0.936585 | common            |
| mirage   | House          |                 19 |                   1   |                 326 |               0.795122 | common            |
| mirage   | Stairs         |                 19 |                   1   |                 277 |               0.67561  | common            |
| mirage   | Ladder         |                 19 |                   1   |                 137 |               0.334146 | common            |
| mirage   | Scaffolding    |                 19 |                   1   |                 180 |               0.439024 | common            |
| inferno  | Banana         |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | BombsiteB      |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | CTSpawn        |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | BombsiteA      |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | TSpawn         |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | Middle         |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | Apartments     |                  5 |                   1   |                 121 |               0.991803 | common            |
| inferno  | TopofMid       |                  5 |                   1   |                 117 |               0.959016 | common            |
| inferno  | Ruins          |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | Pit            |                  5 |                   1   |                  94 |               0.770492 | common            |
| inferno  | Arch           |                  5 |                   1   |                 113 |               0.92623  | common            |
| inferno  | TRamp          |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | SecondMid      |                  5 |                   1   |                 120 |               0.983607 | common            |
| inferno  | LowerMid       |                  5 |                   1   |                 122 |               1        | common            |
| inferno  | Balcony        |                  5 |                   1   |                 103 |               0.844262 | common            |
| inferno  | Library        |                  5 |                   1   |                 119 |               0.97541  | common            |
| inferno  | Quad           |                  5 |                   1   |                  67 |               0.54918  | common            |
| inferno  | BackAlley      |                  5 |                   1   |                  66 |               0.540984 | common            |
| inferno  | Underpass      |                  5 |                   1   |                  64 |               0.52459  | common            |
| inferno  | Bridge         |                  5 |                   1   |                  38 |               0.311475 | common            |
| inferno  | Upstairs       |                  5 |                   1   |                  45 |               0.368852 | common            |
| inferno  | Deck           |                  5 |                   1   |                  16 |               0.131148 | common            |
| inferno  | Graveyard      |                  3 |                   0.6 |                  16 |               0.131148 | moderate          |
| inferno  | Kitchen        |                  5 |                   1   |                  20 |               0.163934 | common            |

## Place Stability
| map_id   | map_name   | target_team   | raw_place      |   demo_count |   coordinate_center_x |   coordinate_center_y |   coordinate_center_z |   between_demo_center_std_x |   between_demo_center_std_y |   between_demo_center_std_z | coordinate_consistency_status   | notes   |
|:---------|:-----------|:--------------|:---------------|-------------:|----------------------:|----------------------:|----------------------:|----------------------------:|----------------------------:|----------------------------:|:--------------------------------|:--------|
| mirage   | Mirage     | Vitality      | Apartments     |           19 |           -1539.69    |              719.639  |             -55.6021  |                    73.3007  |                    23.9403  |                    5.80061  | stable                          |         |
| mirage   | Mirage     | Vitality      | BackAlley      |           19 |            -500.903   |              588.69   |             -87.0762  |                    48.8204  |                    16.0673  |                    3.12289  | stable                          |         |
| mirage   | Mirage     | Vitality      | BombsiteA      |           19 |            -429.115   |            -1886.84   |            -162.974   |                    42.6094  |                    49.1391  |                    3.06036  | stable                          |         |
| mirage   | Mirage     | Vitality      | BombsiteB      |           19 |           -1998.31    |              260.327  |            -159.763   |                    56.9465  |                    36.6531  |                    2.39887  | stable                          |         |
| mirage   | Mirage     | Vitality      | CTSpawn        |           19 |           -1524.95    |            -1738.58   |            -230.01    |                    23.7928  |                    38.9196  |                    3.94082  | stable                          |         |
| mirage   | Mirage     | Vitality      | Catwalk        |           19 |            -758.417   |             -162.15   |            -165.288   |                    48.5986  |                    43.7284  |                    2.31008  | stable                          |         |
| mirage   | Mirage     | Vitality      | Connector      |           19 |            -665.955   |            -1108.58   |            -174.667   |                    30.5187  |                    22.5698  |                    5.88428  | stable                          |         |
| mirage   | Mirage     | Vitality      | House          |           19 |             336.858   |              771.04   |            -133.1     |                    39.1208  |                    16.3256  |                    2.00062  | stable                          |         |
| mirage   | Mirage     | Vitality      | Jungle         |           19 |            -960.117   |            -1398.86   |            -164.996   |                    25.6409  |                    20.442   |                    0.878843 | stable                          |         |
| mirage   | Mirage     | Vitality      | Ladder         |           19 |           -1114.61    |             -257.063  |             -82.4504  |                    29.7495  |                    55.6234  |                   16.2327   | stable                          |         |
| mirage   | Mirage     | Vitality      | Middle         |           19 |            -601.999   |             -732.838  |            -237.22    |                    68.7823  |                    19.7522  |                    8.40829  | stable                          |         |
| mirage   | Mirage     | Vitality      | PalaceAlley    |           19 |             785.575   |            -1333.02   |            -216.151   |                    30.8633  |                    34.2091  |                   13.2102   | stable                          |         |
| mirage   | Mirage     | Vitality      | PalaceInterior |           19 |             357.79    |            -1989.75   |             -78.9352  |                    41.5137  |                    50.1857  |                    7.97222  | stable                          |         |
| mirage   | Mirage     | Vitality      | Scaffolding    |           19 |              -5.34175 |            -2042.5    |             -38.1436  |                    39.1429  |                    55.1759  |                    2.53479  | stable                          |         |
| mirage   | Mirage     | Vitality      | Shop           |           19 |           -1934.75    |             -527.35   |            -160.619   |                    42.9927  |                    19.451   |                    2.10465  | stable                          |         |
| mirage   | Mirage     | Vitality      | SideAlley      |           19 |             544.661   |              363.931  |            -237.945   |                    31.5243  |                    22.5939  |                    4.05551  | stable                          |         |
| mirage   | Mirage     | Vitality      | SnipersNest    |           19 |           -1187.63    |             -729.516  |            -157.997   |                    10.2284  |                    36.8511  |                    3.24105  | stable                          |         |
| mirage   | Mirage     | Vitality      | Stairs         |           19 |            -493.584   |            -1448.02   |             -83.5369  |                    16.7777  |                    38.7946  |                   18.0536   | stable                          |         |
| mirage   | Mirage     | Vitality      | TRamp          |           19 |             372.346   |            -1608.16   |            -198.645   |                    22.0221  |                    26.9553  |                    7.5793   | stable                          |         |
| mirage   | Mirage     | Vitality      | TSpawn         |           19 |            1206.17    |             -182.105  |            -170.97    |                     6.0515  |                    12.511   |                    1.31485  | stable                          |         |
| mirage   | Mirage     | Vitality      | TopofMid       |           19 |             324.69    |             -427.385  |            -163.866   |                    16.2456  |                    48.7064  |                    1.01704  | stable                          |         |
| mirage   | Mirage     | Vitality      | Truck          |           19 |           -2204.78    |              741.645  |             -96.5893  |                    20.1252  |                    12.6382  |                    7.19168  | stable                          |         |
| mirage   | Mirage     | Vitality      | Underpass      |           19 |            -898.376   |               47.7199 |            -255.378   |                    23.6603  |                    73.1171  |                   23.2159   | stable                          |         |
| inferno  | Inferno    | Vitality      | Apartments     |            5 |            1248.8     |             -193.784  |             209.994   |                    76.9082  |                    30.5511  |                    7.85503  | stable                          |         |
| inferno  | Inferno    | Vitality      | Arch           |            5 |            1770.03    |             1211.34   |             170.717   |                    33.9968  |                    24.7637  |                    1.7592   | stable                          |         |
| inferno  | Inferno    | Vitality      | BackAlley      |            5 |             834.165   |             -618.562  |              93.8179  |                    16.6273  |                    23.7943  |                    0.633971 | stable                          |         |
| inferno  | Inferno    | Vitality      | Balcony        |            5 |            1961.68    |             -235.239  |             267.792   |                    41.6952  |                    21.2004  |                    4.2998   | stable                          |         |
| inferno  | Inferno    | Vitality      | Banana         |            5 |             425.125   |             1767.54   |             129.447   |                    16.3305  |                    24.6011  |                    1.04039  | stable                          |         |
| inferno  | Inferno    | Vitality      | BombsiteA      |            5 |            2048.73    |              357.433  |             156.149   |                    21.2501  |                    45.0562  |                    3.46045  | stable                          |         |
| inferno  | Inferno    | Vitality      | BombsiteB      |            5 |             569.101   |             2776.79   |             164.236   |                    24.4452  |                    26.7637  |                    1.29402  | stable                          |         |
| inferno  | Inferno    | Vitality      | Bridge         |            5 |            -374.44    |             -110.568  |             194.741   |                    15.4946  |                    44.8312  |                    0.970711 | stable                          |         |
| inferno  | Inferno    | Vitality      | CTSpawn        |            5 |            2286.04    |             2125.18   |             136.877   |                    11.0838  |                    10.5234  |                    0.380938 | stable                          |         |
| inferno  | Inferno    | Vitality      | Deck           |            5 |             112.914   |               54.3033 |             209.77    |                    30.9697  |                    20.8623  |                   10.0731   | stable                          |         |
| inferno  | Inferno    | Vitality      | Graveyard      |            3 |            2522.16    |              377.04   |             213.94    |                    21.0339  |                    87.6417  |                   11.2752   | stable                          |         |
| inferno  | Inferno    | Vitality      | Kitchen        |            5 |            -135.028   |              239.499  |             194.024   |                    32.7174  |                    30.8485  |                    0.875898 | stable                          |         |
| inferno  | Inferno    | Vitality      | Library        |            5 |            2502.17    |             1274.33   |             166       |                    11.1542  |                    17.9968  |                    4.86747  | stable                          |         |
| inferno  | Inferno    | Vitality      | LowerMid       |            5 |            -636.293   |              464.973  |              -3.20693 |                    15.9299  |                    51.0823  |                    5.2441   | stable                          |         |
| inferno  | Inferno    | Vitality      | Middle         |            5 |             605.293   |              632.276  |              95.6756  |                    24.3009  |                     7.10551 |                    0.393291 | stable                          |         |
| inferno  | Inferno    | Vitality      | Pit            |            5 |            2371.52    |             -219.702  |             101.777   |                    20.5283  |                    21.5777  |                    0.827332 | stable                          |         |
| inferno  | Inferno    | Vitality      | Quad           |            5 |            1450.74    |              -64.0561 |             151.067   |                    16.2519  |                     5.48175 |                   12.4581   | stable                          |         |
| inferno  | Inferno    | Vitality      | Ruins          |            5 |            1202.13    |             2902.54   |             134.358   |                    12.0397  |                    37.8805  |                    4.04203  | stable                          |         |
| inferno  | Inferno    | Vitality      | SecondMid      |            5 |             517.351   |               14.6767 |              89.5473  |                    63.9215  |                    41.1184  |                    3.77638  | stable                          |         |
| inferno  | Inferno    | Vitality      | TRamp          |            5 |            -166.7     |              867.034  |              47.1588  |                    21.2949  |                     8.29455 |                    5.62086  | stable                          |         |
| inferno  | Inferno    | Vitality      | TSpawn         |            5 |           -1560.93    |              359.998  |             -61.2297  |                     2.44466 |                     7.29523 |                    0.266269 | stable                          |         |
| inferno  | Inferno    | Vitality      | TopofMid       |            5 |            1401.47    |              622.32   |             142.857   |                     8.66007 |                    67.1533  |                    2.59144  | stable                          |         |
| inferno  | Inferno    | Vitality      | Underpass      |            5 |             287.771   |              554.606  |              15.1253  |                     4.11151 |                    40.2672  |                    1.46139  | stable                          |         |
| inferno  | Inferno    | Vitality      | Upstairs       |            5 |            -493.402   |              205.438  |             170.545   |                    15.5854  |                    30.4492  |                   13.062    | stable                          |         |

## Vertical Profiles
| map_id   | map_name   | target_team   | raw_place      |      z_min |   z_median |      z_max |   z_range |     z_std | vertical_complexity_flag   | notes   |
|:---------|:-----------|:--------------|:---------------|-----------:|-----------:|-----------:|----------:|----------:|:---------------------------|:--------|
| mirage   | Mirage     | Vitality      | Apartments     | -168.607   |  -47.9688  |   40.8594  |  209.466  |  20.7353  | False                      |         |
| mirage   | Mirage     | Vitality      | BackAlley      | -367.969   |  -79.9688  |   11.4062  |  379.375  |  27.4346  | False                      |         |
| mirage   | Mirage     | Vitality      | BombsiteA      | -197.47    | -167.969   |   28.8438  |  226.313  |  26.1596  | False                      |         |
| mirage   | Mirage     | Vitality      | BombsiteB      | -171.538   | -165.969   |  -15.3125  |  156.225  |  16.8454  | False                      |         |
| mirage   | Mirage     | Vitality      | CTSpawn        | -300.432   | -263.969   |   21.0312  |  321.463  |  50.1319  | False                      |         |
| mirage   | Mirage     | Vitality      | Catwalk        | -263.969   | -167.207   |  -38.125   |  225.844  |  14.3961  | False                      |         |
| mirage   | Mirage     | Vitality      | Connector      | -263.969   | -167.969   |  -84.0322  |  179.937  |  28.1737  | False                      |         |
| mirage   | Mirage     | Vitality      | House          | -255.172   | -135.969   |  -53.3438  |  201.828  |  11.2798  | False                      |         |
| mirage   | Mirage     | Vitality      | Jungle         | -179.969   | -167.969   | -101.156   |   78.8125 |   7.01598 | False                      |         |
| mirage   | Mirage     | Vitality      | Ladder         | -167.969   |  -55.9688  |    2.8125  |  170.781  |  45.7784  | False                      |         |
| mirage   | Mirage     | Vitality      | Middle         | -291.459   | -259.419   |    7.71875 |  299.178  |  38.8429  | False                      |         |
| mirage   | Mirage     | Vitality      | PalaceAlley    | -263.969   | -258.354   |    9.85938 |  273.828  |  68.6329  | False                      |         |
| mirage   | Mirage     | Vitality      | PalaceInterior | -240.438   |  -39.9688  |   41.9375  |  282.375  |  58.5865  | False                      |         |
| mirage   | Mirage     | Vitality      | Scaffolding    |  -82.4688  |  -39.9688  |   24.8594  |  107.328  |  10.539   | False                      |         |
| mirage   | Mirage     | Vitality      | Shop           | -167.969   | -167.969   |  -62.0625  |  105.906  |  16.4508  | False                      |         |
| mirage   | Mirage     | Vitality      | SideAlley      | -266.608   | -254.971   |  -59.1406  |  207.468  |  34.4332  | False                      |         |
| mirage   | Mirage     | Vitality      | SnipersNest    | -263.969   | -167.969   |  -34.0312  |  229.938  |  20.9882  | False                      |         |
| mirage   | Mirage     | Vitality      | Stairs         | -167.969   |  -70.4472  |   24.8594  |  192.828  |  46.758   | False                      |         |
| mirage   | Mirage     | Vitality      | TRamp          | -263.969   | -182.429   |  -92.4062  |  171.562  |  34.2905  | False                      |         |
| mirage   | Mirage     | Vitality      | TSpawn         | -264.459   | -164.788   |  -55.4844  |  208.975  |  22.2702  | False                      |         |
| mirage   | Mirage     | Vitality      | TopofMid       | -208.13    | -163.979   |  -24.0312  |  184.098  |  13.9721  | False                      |         |
| mirage   | Mirage     | Vitality      | Truck          | -168.544   | -103.484   |   25.1094  |  193.654  |  35.2996  | False                      |         |
| mirage   | Mirage     | Vitality      | Underpass      | -367.969   | -263.969   |   16.7188  |  384.688  | 103.391   | False                      |         |
| inferno  | Inferno    | Vitality      | Apartments     |   88.0312  |  256.031   |  325.859   |  237.828  |  61.9455  | False                      |         |
| inferno  | Inferno    | Vitality      | Arch           |  155.501   |  169.117   |  241.859   |   86.3585 |  12.4217  | False                      |         |
| inferno  | Inferno    | Vitality      | BackAlley      |   88.0312  |   91.6612  |  159.625   |   71.5938 |   8.19538 | False                      |         |
| inferno  | Inferno    | Vitality      | Balcony        |   89.0312  |  258.633   |  345.562   |  256.531  |  18.7309  | False                      |         |
| inferno  | Inferno    | Vitality      | Banana         |   81.1233  |  136.031   |  281.859   |  200.736  |  24.33    | False                      |         |
| inferno  | Inferno    | Vitality      | BombsiteA      |  102.418   |  160.027   |  331.719   |  229.301  |  26.8228  | False                      |         |
| inferno  | Inferno    | Vitality      | BombsiteB      |  124.578   |  161.031   |  343.859   |  219.282  |  34.4679  | False                      |         |
| inferno  | Inferno    | Vitality      | Bridge         |  150.609   |  192.031   |  257.578   |  106.969  |  10.0021  | False                      |         |
| inferno  | Inferno    | Vitality      | CTSpawn        |  124.032   |  134.505   |  280.828   |  156.796  |  12.6746  | False                      |         |
| inferno  | Inferno    | Vitality      | Deck           |   22.4406  |  208.031   |  285.344   |  262.903  |  27.2102  | False                      |         |
| inferno  | Inferno    | Vitality      | Graveyard      |  123.707   |  216.031   |  291.859   |  168.152  |  24.4943  | False                      |         |
| inferno  | Inferno    | Vitality      | Kitchen        |  192.031   |  192.031   |  249.047   |   57.0156 |   6.30761 | False                      |         |
| inferno  | Inferno    | Vitality      | Library        |  157.433   |  160.031   |  225.875   |   68.4423 |  16.0267  | False                      |         |
| inferno  | Inferno    | Vitality      | LowerMid       |  -33.6581  |   -6.82446 |  131.859   |  165.517  |  30.8926  | False                      |         |
| inferno  | Inferno    | Vitality      | Middle         |   22.2349  |   95.8541  |  224.328   |  202.093  |  17.2984  | False                      |         |
| inferno  | Inferno    | Vitality      | Pit            |   89.539   |   97.938   |  266.844   |  177.305  |  13.0926  | False                      |         |
| inferno  | Inferno    | Vitality      | Quad           |  132.031   |  140.583   |  344.812   |  212.781  |  42.694   | False                      |         |
| inferno  | Inferno    | Vitality      | Ruins          |  124.032   |  128.031   |  300.484   |  176.453  |  24.3759  | False                      |         |
| inferno  | Inferno    | Vitality      | SecondMid      |    3.578   |   89.0312  |  312.984   |  309.406  |  48.7129  | False                      |         |
| inferno  | Inferno    | Vitality      | TRamp          |  -32.8706  |   56.2235  |  146.031   |  178.902  |  33.5883  | False                      |         |
| inferno  | Inferno    | Vitality      | TSpawn         |  -70.1613  |  -63.9688  |   71.8438  |  142.005  |  12.6047  | False                      |         |
| inferno  | Inferno    | Vitality      | TopofMid       |  117.641   |  134.457   |  281.594   |  163.952  |  20.6329  | False                      |         |
| inferno  | Inferno    | Vitality      | Underpass      |   -8.46875 |   17.3875  |   85.1875  |   93.6562 |  16.8616  | False                      |         |
| inferno  | Inferno    | Vitality      | Upstairs       |   49.0312  |  192.031   |  256.859   |  207.828  |  42.7041  | False                      |         |

## Unknowns
| map_id   | map_name   | target_team   | unknown_type        | raw_place   |   observation_count | severity   | blocking   | reason                                       | recommended_action                                                 |
|:---------|:-----------|:--------------|:--------------------|:------------|--------------------:|:-----------|:-----------|:---------------------------------------------|:-------------------------------------------------------------------|
| mirage   | Mirage     | Vitality      | null_place          |             |                   2 | medium     | False      | Place value is null.                         | Keep rows out of region mapping until parser source is understood. |
| mirage   | Mirage     | Vitality      | empty_place         |             |                3607 | medium     | False      | Place value is empty or whitespace-only.     | Review parser output; do not invent a correction.                  |
| mirage   | Mirage     | Vitality      | invalid_coordinates |             |                   2 | medium     | False      | At least one coordinate axis is null or NaN. | Exclude these observations from coordinate profiles.               |
| inferno  | Inferno    | Vitality      | empty_place         |             |                1100 | medium     | False      | Place value is empty or whitespace-only.     | Review parser output; do not invent a correction.                  |

## Limitations
No callouts, bounding boxes, semantic groups, or Inferno registry entries are invented here. Mirage registry differences are reported, not corrected.

## Readiness
| audit_id                            | map_id   | map_name   | target_team   |   source_demos |   source_rounds |   source_ticks | place_column   |   place_non_null_rows |   place_non_null_share |   unique_places |   coordinate_profiles_generated |   coverage_profiles_generated |   stability_profiles_generated |   unknown_count |   critical_unknown_count | registry_crosswalk_available   |   registry_matched_places |   registry_unmatched_places |   registry_matched_tick_share | ready_for_region_mapping   | status   | created_at                       |
|:------------------------------------|:---------|:-----------|:--------------|---------------:|----------------:|---------------:|:---------------|----------------------:|-----------------------:|----------------:|--------------------------------:|------------------------------:|-------------------------------:|----------------:|-------------------------:|:-------------------------------|--------------------------:|----------------------------:|------------------------------:|:---------------------------|:---------|:---------------------------------|
| map_area_discovery_mirage_vitality  | mirage   | Mirage     | Vitality      |             19 |             410 |       30206610 | place          |              30206608 |                      1 |              23 |                              23 |                            23 |                             23 |               3 |                        0 | True                           |                        23 |                           0 |                             1 | True                       | ok       | 2026-08-18T20:20:40.714807+00:00 |
| map_area_discovery_inferno_vitality | inferno  | Inferno    | Vitality      |              5 |             122 |       10081430 | place          |              10081430 |                      1 |              24 |                              24 |                            24 |                             24 |               1 |                        0 | False                          |                         0 |                           0 |                             0 | True                       | ok       | 2026-08-18T20:20:57.660985+00:00 |

## Next Stage
Stage 8.7 should use these raw-place outputs to review and formalize Inferno physical regions and tactical semantic groups.

## Inferno Place Discovery
| raw_place   |   tick_count |   demo_count |   round_count |   demo_coverage_share | coverage_status   |   x_median |   y_median |   z_median |
|:------------|-------------:|-------------:|--------------:|----------------------:|:------------------|-----------:|-----------:|-----------:|
| Banana      |      1754327 |            5 |           122 |                   1   | common            |    387.264 |  1875.52   |  136.031   |
| BombsiteB   |      1276346 |            5 |           122 |                   1   | common            |    580.267 |  2735.96   |  161.031   |
| CTSpawn     |      1248672 |            5 |           122 |                   1   | common            |   2353     |  2079      |  134.505   |
| BombsiteA   |      1115772 |            5 |           122 |                   1   | common            |   2066.5   |   293.684  |  160.027   |
| TSpawn      |      1040577 |            5 |           122 |                   1   | common            |  -1604.13  |   419.577  |  -63.9688  |
| Middle      |       600563 |            5 |           122 |                   1   | common            |    569.467 |   602.454  |   95.8541  |
| Apartments  |       528750 |            5 |           121 |                   1   | common            |   1236.53  |  -257.105  |  256.031   |
| TopofMid    |       396177 |            5 |           117 |                   1   | common            |   1397.25  |   587.202  |  134.457   |
| Ruins       |       327388 |            5 |           122 |                   1   | common            |   1177.86  |  2814.6    |  128.031   |
| Pit         |       288719 |            5 |            94 |                   1   | common            |   2439.51  |  -182.227  |   97.938   |
| Arch        |       267679 |            5 |           113 |                   1   | common            |   1779.38  |  1208.21   |  169.117   |
| TRamp       |       258618 |            5 |           122 |                   1   | common            |   -128.695 |   884.041  |   56.2235  |
| SecondMid   |       254234 |            5 |           120 |                   1   | common            |    717.635 |   -19.7757 |   89.0312  |
| LowerMid    |       170330 |            5 |           122 |                   1   | common            |   -619.969 |   581.943  |   -6.82446 |
| Balcony     |       168711 |            5 |           103 |                   1   | common            |   2076.05  |  -232.995  |  258.633   |
| Library     |       139233 |            5 |           119 |                   1   | common            |   2510.38  |  1244.48   |  160.031   |
| Quad        |        80820 |            5 |            67 |                   1   | common            |   1428.57  |   -77.2762 |  140.583   |
| BackAlley   |        52015 |            5 |            66 |                   1   | common            |    886.865 |  -646.323  |   91.6612  |
| Underpass   |        40808 |            5 |            64 |                   1   | common            |    288.883 |   648.063  |   17.3875  |
| Bridge      |        18359 |            5 |            38 |                   1   | common            |   -374.645 |   -77.4408 |  192.031   |
| Upstairs    |        17685 |            5 |            45 |                   1   | common            |   -510.683 |   219.524  |  192.031   |
| Deck        |        15736 |            5 |            16 |                   1   | common            |    102.354 |    44.0587 |  208.031   |
| Graveyard   |        14148 |            3 |            16 |                   0.6 | moderate          |   2513.13  |   448.509  |  216.031   |
| Kitchen     |         4663 |            5 |            20 |                   1   | common            |   -199.773 |   252.272  |  192.031   |

## Mirage Discovery Validation
| map_id   | map_name   | target_team   |   observed_places |   matched_places |   unmatched_places |   ambiguous_places |   matched_tick_share |   unmatched_tick_share |   registry_regions |   registry_regions_observed |   registry_regions_not_observed |   critical_mismatch_count | status   |
|:---------|:-----------|:--------------|------------------:|-----------------:|-------------------:|-------------------:|---------------------:|-----------------------:|-------------------:|----------------------------:|--------------------------------:|--------------------------:|:---------|
| mirage   | Mirage     | Vitality      |                23 |               23 |                  0 |                  0 |                    1 |                      0 |                 15 |                          15 |                               0 |                         0 | ok       |
