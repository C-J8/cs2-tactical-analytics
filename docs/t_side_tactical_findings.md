# T-side Tactical Findings -- Vitality Mirage

## Scope

This report ranks conservative tactical candidates for Vitality T-side on Mirage. It does not claim causality and does not train a model.

## Data snapshot

- T-side rounds: 180
- Plant A: 72
- Plant B: 26
- No plant: 82
- Plant rate: 54.4%

## Main A/B tendencies

| window_type   |   window_start |   window_end | region_group   |   share_diff_A_minus_B | evidence_strength   |
|:--------------|---------------:|-------------:|:---------------|-----------------------:|:--------------------|
| interval      |             65 |           75 | A_PRESSURE     |               0.571581 | strong_candidate    |
| interval      |             55 |           65 | A_PRESSURE     |               0.53953  | strong_candidate    |
| interval      |             55 |           65 | B_PRESSURE     |              -0.536325 | strong_candidate    |
| interval      |             45 |           55 | B_PRESSURE     |              -0.53312  | strong_candidate    |
| interval      |             35 |           45 | B_PRESSURE     |              -0.488248 | strong_candidate    |

## Timing signals

| window_type   |   window_start |   window_end |   combined_signal_score | dominant_signal   | signal_period     |
|:--------------|---------------:|-------------:|------------------------:|:------------------|:------------------|
| cumulative    |              0 |          115 |                0.562668 | both              | late_round_signal |
| cumulative    |              0 |          105 |                0.547946 | both              | late_round_signal |
| cumulative    |              0 |           95 |                0.519118 | both              | late_round_signal |
| cumulative    |              0 |           85 |                0.453614 | both              | late_round_signal |
| cumulative    |              0 |           75 |                0.402107 | both              | late_round_signal |

## Utility signals

| window_type   |   window_start |   window_end | region_group   |   diff_avg_utilities_per_round_A_minus_B | evidence_strength   |
|:--------------|---------------:|-------------:|:---------------|-----------------------------------------:|:--------------------|
| cumulative    |              0 |          115 | A_PRESSURE     |                                  1.77457 | strong_candidate    |
| cumulative    |              0 |           85 | A_PRESSURE     |                                  1.71581 | strong_candidate    |
| cumulative    |              0 |           95 | A_PRESSURE     |                                  1.74679 | strong_candidate    |
| cumulative    |              0 |          105 | A_PRESSURE     |                                  1.74679 | strong_candidate    |
| cumulative    |              0 |           75 | A_PRESSURE     |                                  1.61859 | strong_candidate    |

## No-plant patterns

| finding_type                  | finding_value          |   round_count |   round_share | evidence_strength   |
|:------------------------------|:-----------------------|--------------:|--------------:|:--------------------|
| bomb_drop_region              | UNKNOWN                |            82 |      1        | medium_candidate    |
| round_failure_context         | bomb_lost_UNKNOWN      |            80 |      0.97561  | medium_candidate    |
| round_outcome_type            | bomb_lost_before_plant |            80 |      0.97561  | medium_candidate    |
| bomb_last_known_region        | UNKNOWN                |            74 |      0.902439 | medium_candidate    |
| final_pressure_region_105_115 | UNKNOWN                |            67 |      0.817073 | medium_candidate    |

## Bomb carrier and C4 patterns

| context_type     |   window_start |   window_end | region_group   | t_round_outcome   |   round_count |
|:-----------------|---------------:|-------------:|:---------------|:------------------|--------------:|
| carrier_region   |             95 |          105 | BOMB_SITE_A    | plant_A           |            15 |
| bomb_drop_region |             95 |          105 | UNKNOWN        | no_plant          |            12 |
| carrier_region   |            105 |          115 | BOMB_SITE_A    | plant_A           |            12 |
| carrier_region   |             95 |          105 | BOMB_SITE_B    | plant_B           |             8 |
| carrier_region   |             95 |          105 | BOMB_SITE_A    | no_plant          |             7 |

## Opponent tendencies

| opponent    |   total_t_side_rounds |   plant_rate |   no_plant_share | tendency_label   |
|:------------|----------------------:|-------------:|-----------------:|:-----------------|
| Spirit      |                    48 |     0.479167 |         0.520833 | high_no_plant    |
| The MongolZ |                    37 |     0.621622 |         0.378378 | A_leaning        |
| G2          |                    27 |     0.444444 |         0.555556 | high_no_plant    |
| Falcons     |                    23 |     0.347826 |         0.652174 | high_no_plant    |
| FURIA       |                    12 |     0.666667 |         0.333333 | A_leaning        |

## Progression signatures

| round_progression_signature                                                               | t_round_outcome   |   count |     share |   winrate |
|:------------------------------------------------------------------------------------------|:------------------|--------:|----------:|----------:|
| B_PRESSURE>MID_CONTROL>MID_CONTROL>MID_CONTROL>MID_CONTROL>MID_CONTROL>MID_CONTROL        | no_plant          |       3 | 0.0365854 |  0        |
| A_PRESSURE>A_PRESSURE>BOMB_SITE_A>BOMB_SITE_A>BOMB_SITE_A>BOMB_SITE_A>BOMB_SITE_A>PLANT_A | plant_A           |       4 | 0.0555556 |  0.5      |
| A_PRESSURE>A_PRESSURE>A_PRESSURE>BOMB_SITE_A>BOMB_SITE_A>BOMB_SITE_A>BOMB_SITE_A>PLANT_A  | plant_A           |       3 | 0.0416667 |  0.666667 |

## Manual review queue

| priority   | reason                                      | suggested_filter                                                    | expected_question                                               |
|:-----------|:--------------------------------------------|:--------------------------------------------------------------------|:----------------------------------------------------------------|
| high       | No-plant C4 context needs demo inspection   | t_round_outcome=no_plant and bomb_drop_region=UNKNOWN               | Where is C4 control lost before a valid plant?                  |
| high       | No-plant C4 context needs demo inspection   | t_round_outcome=no_plant and bomb_last_known_region=UNKNOWN         | Where is C4 control lost before a valid plant?                  |
| high       | No-plant C4 context needs demo inspection   | t_round_outcome=no_plant and bomb:carrier_region:95_105=BOMB_SITE_A | Where is C4 control lost before a valid plant?                  |
| medium     | Late-round A/B utility difference is sparse | window_type=interval, window=95-105, region=BOMB_SITE_B             | Is late utility planned, reactive, or caused by a small sample? |
| medium     | Late-round A/B utility difference is sparse | window_type=interval, window=95-105, region=BOMB_SITE_A             | Is late utility planned, reactive, or caused by a small sample? |

## Limitations

- Findings are descriptive candidates derived from the current sample.
- Percentages always require inspection alongside round counts.
- Sparse and late-round signals are explicitly queued for manual demo review.
- CT-side analysis, causal claims, and rounds without a valid A/B label remain outside model scope.

## Next step

Build a leakage-controlled baseline A/B model using only high-confidence rows from `round_features_t_side_planted` after manual review of the candidates above.
