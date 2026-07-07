# T-side Manual Review Pack -- Vitality Mirage

## Scope

This pack links conservative Stage 5.1 findings to concrete T-side rounds and row-level evidence.

## Why this stage exists

Manual review separates repeatable tactical candidates from sparse patterns before any A/B model is trained.

## Review summary

|   total_review_rounds |   total_findings_covered |   findings_without_round_examples |   plant_A_rounds |   plant_B_rounds |   no_plant_rounds |   high_priority_items |   medium_priority_items |   low_priority_items |   opponents_covered |   series_covered |   late_round_examples | status   |
|----------------------:|-------------------------:|----------------------------------:|-----------------:|-----------------:|------------------:|----------------------:|------------------------:|---------------------:|--------------------:|-----------------:|----------------------:|:---------|
|                   151 |                       20 |                                 0 |               45 |               51 |                55 |                    80 |                      71 |                    0 |                  10 |               17 |                     8 | ok       |

## Top findings selected

| finding_id       | finding_category   | evidence_strength   |   selected_rounds | review_status         |
|:-----------------|:-------------------|:--------------------|------------------:|:----------------------|
| finding_005      | A_vs_B_region      | strong_candidate    |                 8 | pending_manual_review |
| finding_026      | A_vs_B_utility     | strong_candidate    |                 8 | pending_manual_review |
| finding_031      | timing             | strong_candidate    |                 8 | pending_manual_review |
| queue_review_001 | no_plant           | strong_candidate    |                 8 | pending_manual_review |
| finding_065      | opponent           | medium_candidate    |                 8 | pending_manual_review |
| finding_050      | bomb_carrier       | medium_candidate    |                 8 | pending_manual_review |
| finding_074      | progression        | medium_candidate    |                 4 | pending_manual_review |
| finding_004      | A_vs_B_region      | strong_candidate    |                 8 | pending_manual_review |
| finding_027      | A_vs_B_utility     | strong_candidate    |                 8 | pending_manual_review |
| queue_review_002 | no_plant           | strong_candidate    |                 8 | pending_manual_review |

## Rounds to review first

| review_round_id      | finding_category   | review_priority   | opponent    |   round_num | t_round_outcome   | suggested_focus                               |
|:---------------------|:-------------------|:------------------|:------------|------------:|:------------------|:----------------------------------------------|
| finding_005_round_01 | A_vs_B_region      | high              | The MongolZ |          14 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_02 | A_vs_B_region      | high              | The MongolZ |          16 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_03 | A_vs_B_region      | high              | B8          |          18 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_04 | A_vs_B_region      | high              | FUT         |          14 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_05 | A_vs_B_region      | high              | The MongolZ |          14 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_06 | A_vs_B_region      | high              | GamerLegion |          13 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_07 | A_vs_B_region      | high              | The MongolZ |          14 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_08 | A_vs_B_region      | high              | G2          |          16 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_026_round_01 | A_vs_B_utility     | high              | The MongolZ |          16 | plant_B           | A_vs_B_utility / B_PRESSURE / 0-95s / plant_B |
| finding_026_round_02 | A_vs_B_utility     | high              | BC.Game     |          17 | plant_B           | A_vs_B_utility / B_PRESSURE / 0-95s / plant_B |

## A/B examples

| review_round_id      | finding_category   | review_priority   | opponent    |   round_num | t_round_outcome   | suggested_focus                               |
|:---------------------|:-------------------|:------------------|:------------|------------:|:------------------|:----------------------------------------------|
| finding_005_round_01 | A_vs_B_region      | high              | The MongolZ |          14 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_02 | A_vs_B_region      | high              | The MongolZ |          16 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_03 | A_vs_B_region      | high              | B8          |          18 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_04 | A_vs_B_region      | high              | FUT         |          14 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_05 | A_vs_B_region      | high              | The MongolZ |          14 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_06 | A_vs_B_region      | high              | GamerLegion |          13 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_07 | A_vs_B_region      | high              | The MongolZ |          14 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_005_round_08 | A_vs_B_region      | high              | G2          |          16 | plant_B           | A_vs_B_region / B_PRESSURE / 35-45s / plant_B |
| finding_026_round_01 | A_vs_B_utility     | high              | The MongolZ |          16 | plant_B           | A_vs_B_utility / B_PRESSURE / 0-95s / plant_B |
| finding_026_round_02 | A_vs_B_utility     | high              | BC.Game     |          17 | plant_B           | A_vs_B_utility / B_PRESSURE / 0-95s / plant_B |

## No-plant examples

| review_round_id           | finding_category   | review_priority   | opponent   |   round_num | t_round_outcome   | suggested_focus               |
|:--------------------------|:-------------------|:------------------|:-----------|------------:|:------------------|:------------------------------|
| finding_031_round_04      | timing             | high              | Spirit     |          24 | no_plant          | timing / 0-115s               |
| queue_review_001_round_01 | no_plant           | high              | Spirit     |           4 | no_plant          | no_plant / UNKNOWN / no_plant |
| queue_review_001_round_02 | no_plant           | high              | Spirit     |           5 | no_plant          | no_plant / UNKNOWN / no_plant |
| queue_review_001_round_03 | no_plant           | high              | Falcons    |           7 | no_plant          | no_plant / UNKNOWN / no_plant |
| queue_review_001_round_04 | no_plant           | high              | Spirit     |          15 | no_plant          | no_plant / UNKNOWN / no_plant |
| queue_review_001_round_05 | no_plant           | high              | Spirit     |          16 | no_plant          | no_plant / UNKNOWN / no_plant |
| queue_review_001_round_06 | no_plant           | high              | G2         |          17 | no_plant          | no_plant / UNKNOWN / no_plant |
| queue_review_001_round_07 | no_plant           | high              | Spirit     |          18 | no_plant          | no_plant / UNKNOWN / no_plant |
| queue_review_001_round_08 | no_plant           | high              | G2         |          19 | no_plant          | no_plant / UNKNOWN / no_plant |
| finding_065_round_01      | opponent           | medium            | Spirit     |           4 | no_plant          | opponent                      |

## C4/bomb carrier examples

| review_round_id      | finding_category   | review_priority   | opponent    |   round_num | t_round_outcome   | suggested_focus            |
|:---------------------|:-------------------|:------------------|:------------|------------:|:------------------|:---------------------------|
| finding_050_round_01 | bomb_carrier       | medium            | Spirit      |           9 | plant_A           | bomb_carrier / 95.0-105.0s |
| finding_050_round_02 | bomb_carrier       | medium            | PARIVISION  |          14 | plant_A           | bomb_carrier / 95.0-105.0s |
| finding_050_round_03 | bomb_carrier       | medium            | FUT         |          15 | plant_A           | bomb_carrier / 95.0-105.0s |
| finding_050_round_04 | bomb_carrier       | medium            | The MongolZ |          16 | plant_A           | bomb_carrier / 95.0-105.0s |
| finding_050_round_05 | bomb_carrier       | medium            | B8          |          17 | plant_A           | bomb_carrier / 95.0-105.0s |
| finding_050_round_06 | bomb_carrier       | medium            | G2          |          17 | plant_A           | bomb_carrier / 95.0-105.0s |
| finding_050_round_07 | bomb_carrier       | medium            | PARIVISION  |          18 | plant_A           | bomb_carrier / 95.0-105.0s |
| finding_050_round_08 | bomb_carrier       | medium            | The MongolZ |          18 | plant_A           | bomb_carrier / 95.0-105.0s |
| finding_051_round_01 | bomb_carrier       | medium            | Falcons     |           2 | no_plant          | bomb_carrier / 95.0-105.0s |
| finding_051_round_02 | bomb_carrier       | medium            | Spirit      |           2 | no_plant          | bomb_carrier / 95.0-105.0s |

## Late-round examples

| review_round_id           | finding_category   | review_priority   | opponent   |   round_num | t_round_outcome   | suggested_focus                             |
|:--------------------------|:-------------------|:------------------|:-----------|------------:|:------------------|:--------------------------------------------|
| queue_review_003_round_01 | no_plant           | high              | Spirit     |           4 | no_plant          | no_plant / BOMB_SITE_A / 95-105s / no_plant |
| queue_review_003_round_02 | no_plant           | high              | Spirit     |           5 | no_plant          | no_plant / BOMB_SITE_A / 95-105s / no_plant |
| queue_review_003_round_03 | no_plant           | high              | Falcons    |           7 | no_plant          | no_plant / BOMB_SITE_A / 95-105s / no_plant |
| queue_review_003_round_04 | no_plant           | high              | Spirit     |          15 | no_plant          | no_plant / BOMB_SITE_A / 95-105s / no_plant |
| queue_review_003_round_05 | no_plant           | high              | Spirit     |          16 | no_plant          | no_plant / BOMB_SITE_A / 95-105s / no_plant |
| queue_review_003_round_06 | no_plant           | high              | G2         |          17 | no_plant          | no_plant / BOMB_SITE_A / 95-105s / no_plant |
| queue_review_003_round_07 | no_plant           | high              | Spirit     |          18 | no_plant          | no_plant / BOMB_SITE_A / 95-105s / no_plant |
| queue_review_003_round_08 | no_plant           | high              | G2         |          19 | no_plant          | no_plant / BOMB_SITE_A / 95-105s / no_plant |

## Manual decision template

Fill `manual_review_decision_template.csv` after inspecting each selected demo round.

## Model readiness

| readiness_check              | status   | evidence                                                     | recommendation                                         |
|:-----------------------------|:---------|:-------------------------------------------------------------|:-------------------------------------------------------|
| high_confidence_ab_dataset   | pass     | A=72, B=26                                                   | Keep only high-confidence A/B rows.                    |
| feature_catalog_exists       | pass     | rows=492                                                     | Use the catalog to define predictors.                  |
| leakage_fields_marked        | pass     | Catalog notes identify post-round/target leakage fields.     | Exclude all leakage-marked fields.                     |
| stage_5_1_audit_ok           | pass     | status=ok                                                    | Resolve Stage 5.1 warnings before modeling.            |
| manual_review_pack_generated | pass     | rounds=151                                                   | Complete the decision template.                        |
| enough_plant_A_examples      | pass     | plant_A=72                                                   | Retain class-aware validation.                         |
| enough_plant_B_examples      | pass     | plant_B=26                                                   | Use conservative validation because B is smaller.      |
| enough_ab_findings           | pass     | findings=9                                                   | Use findings only as motivation, not feature proof.    |
| no_plant_separated           | pass     | labels=['A', 'B']                                            | Do not infer A/B for no-plant rounds.                  |
| prediction_horizon_required  | fail     | Windows reach 115s; a pre-plant horizon is not selected yet. | Choose and document a leakage-safe prediction horizon. |
| overall_readiness            | pass     | 9 of 10 checks passed.                                       | ready_for_baseline_after_manual_review                 |

## Limitations

- Findings remain descriptive candidates, not causal claims.
- Repeated rounds can support more than one finding.
- No-plant rounds never receive an inferred A/B label.
- A leakage-safe prediction horizon must be chosen before modeling.

## Next step

Complete manual decisions, then design a leakage-controlled A/B baseline using only high-confidence planted T-side rounds.
