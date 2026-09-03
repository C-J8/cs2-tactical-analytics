# Inferno Sample Expansion & Modeling Readiness

## Purpose

Stage 8.12 measures whether the Inferno/Vitality T-side A/B sample is large and independent enough for a more reliable frozen-baseline re-evaluation. It is not a tuning stage.

## Starting Sample

- Demos: 5
- Series: 5
- Opponents: 4
- Planted T-side model rows: 40
- A/B: 22 / 18
- Model groups: 5

## Expansion Strategy

The stage prioritizes independent series, independent demos, A/B plant coverage, temporal coverage, and opponent diversity over raw round count.

## Intake

No HLTV scraper or parallel intake path is implemented. New demos must enter through the existing manual/local pipeline.

## New Demos

- Demos added by this run: 0
- Frozen baseline rerun: False

## Duplicate Protection

Duplicate detection uses deterministic identifiers such as content hash and canonical demo identity; filename alone is not enough.

## Data Lineage

New-demo lineage is emitted in `inferno_expansion_lineage`. Empty lineage means no new demo was processed by Stage 8.12.

## Parse / Feature Quality

The stage requires the existing feature-quality and materialization gates and reports readiness without relaxing thresholds.

## A/B Label Coverage

- Minority class: B
- Minority count/share: 18 / 0.45

## Independent Series Coverage

- Independent series: 5

## Opponent Diversity

- Opponents: 4

## Sample Concentration

See `inferno_sample_concentration_audit` for concentration by series, demo, opponent, and month.

## Modeling Readiness

- Data readiness: `expanded_but_limited`
- Modeling sample ready: `False`
- Recommended next action: `continue_sample_expansion`

## Frozen Baseline Before / After

| metric            | before                | after                 |   difference |   before_rows |   after_rows |   before_groups |   after_groups |   before_A |   after_A |   before_B |   after_B | interpretation          | status   |
|:------------------|:----------------------|:----------------------|-------------:|--------------:|-------------:|----------------:|---------------:|-----------:|----------:|-----------:|----------:|:------------------------|:---------|
| macro_f1          | 0.47203016970458833   | 0.47203016970458833   |            0 |            40 |           40 |               5 |              5 |         22 |        22 |         18 |        18 | unchanged               | ok       |
| balanced_accuracy | 0.4722222222222222    | 0.4722222222222222    |            0 |            40 |           40 |               5 |              5 |         22 |        22 |         18 |        18 | unchanged               | ok       |
| MCC               | -0.055346306015210976 | -0.055346306015210976 |            0 |            40 |           40 |               5 |              5 |         22 |        22 |         18 |        18 | unchanged               | ok       |
| null_percentile   | 0.47                  | 0.47                  |            0 |            40 |           40 |               5 |              5 |         22 |        22 |         18 |        18 | unchanged               | ok       |
| signal_status     | no_signal             | no_signal             |              |            40 |           40 |               5 |              5 |         22 |        22 |         18 |        18 | signal status unchanged | ok       |

## Learning-Curve Context

The learning curve is diagnostic only; it does not select the best sample size.

## Temporal Generalization Context

Temporal holdout is only emitted when enough dated independent series exist and never replaces LOGO.

## Remaining Data Gaps

| metric         |   current_value |   target_value |   gap_absolute | target_met   | priority   | notes                                                           |
|:---------------|----------------:|---------------:|---------------:|:-------------|:-----------|:----------------------------------------------------------------|
| demos          |            5    |          10    |              5 | False        | high       | Independent demos are preferred over more rounds from one demo. |
| series         |            5    |           8    |              3 | False        | critical   | Independent series are the primary readiness unit.              |
| opponents      |            4    |           5    |              1 | False        | medium     | Opponent diversity reduces overfitting to one matchup.          |
| planted rounds |           40    |          80    |             40 | False        | high       | A/B labels exist only on high-confidence planted T rounds.      |
| A count        |           22    |          30    |              8 | False        | high       | A class coverage must be sufficient independently.              |
| B count        |           18    |          30    |             12 | False        | high       | B class coverage must be sufficient independently.              |
| minority share |            0.45 |           0.25 |              0 | True         | met        | Class balance matters even when raw rows increase.              |
| model groups   |            5    |           8    |              3 | False        | critical   | LOGO validation needs enough independent held-out groups.       |

## Next Data Targets

|   priority | target_type                      |   needed_count | reason                                            | status   |
|-----------:|:---------------------------------|---------------:|:--------------------------------------------------|:---------|
|          1 | independent_series               |              3 | Only 5.0 current series; target is 8.0.           | open     |
|          2 | valid_logo_groups                |              3 | Only 5.0 current model groups; target is 8.0.     | open     |
|          3 | high_confidence_planted_t_rounds |             40 | Only 40.0 current planted rounds; target is 80.0. | open     |
|          4 | B_planted_rounds                 |             12 | Only 18.0 current B count; target is 30.0.        | open     |
|          5 | A_planted_rounds                 |              8 | Only 22.0 current A count; target is 30.0.        | open     |
|          6 | feature_eligible_demos           |              5 | Only 5.0 current demos; target is 10.0.           | open     |
|          7 | new_opponents                    |              1 | Only 4.0 current opponents; target is 5.0.        | open     |

## Limitations

Stage 8.12 does not add scraping, tune models, search horizons, promote models, build dashboards, export BigQuery, or add a new map/team.

## Next Stage

Choose Stage 8.13 from the readiness result: continued sample expansion, A/B signal diagnosis, or robustness study.
