# Mirage region review

This pack supports the explicit manual sign-off required by the Mirage consolidation contract.
It combines the pinned Awpy radar, observed player-place centroids, and the canonical region crosswalk.

## Automated prerequisites

- Status: `ready_for_manual_signoff`
- Configured/observed regions: `23/23`
- Raw places reviewed: `23`
- Unmatched / ambiguous / outside radar: `0 / 0 / 0`
- Radar hash matches pinned manifest: `True`

## Overlay

![Mirage region review overlay](../data/gold/validation/mirage_region_review/mirage_region_review_overlay.png)

## Review table

| raw_place      | matched_region_id   | semantic_tags   |   tick_count |   radar_x |   radar_y | review_status   |
|:---------------|:--------------------|:----------------|-------------:|----------:|----------:|:----------------|
| TRamp          | a_ramp              | a_pressure      |       555497 |   721.053 |   664.627 | ready           |
| BombsiteA      | a_site              | site_a          |      3678157 |   561.312 |   727.057 | ready           |
| Apartments     | b_apps              | b_pressure      |      1213002 |   333.295 |   194.466 | ready           |
| Ladder         | b_short             | b_pressure      |       198950 |   418.787 |   385.788 | ready           |
| BombsiteB      | b_site              | site_b          |      1993443 |   239.115 |   286.383 | ready           |
| BackAlley      | back_alley          | b_pressure      |       776787 |   557.414 |   226.578 | ready           |
| Catwalk        | catwalk             | mid_control     |      1241982 |   481.281 |   388.583 | ready           |
| Connector      | connector           | mid_control     |       743773 |   510.348 |   567.877 | ready           |
| CTSpawn        | ct_spawn            | ct_space        |      5371557 |   314.8   |   702.6   | ready           |
| House          | house               | b_pressure      |       375833 |   721.371 |   182.824 | ready           |
| Jungle         | jungle              | rotation        |       546534 |   457.319 |   618.58  | ready           |
| Shop           | market              | ct_space        |       551051 |   263.731 |   453.302 | ready           |
| Middle         | mid                 | mid_control     |      1350455 |   514.107 |   491.887 | ready           |
| PalaceInterior | palace              | a_pressure      |      1912691 |   682.368 |   756.99  | ready           |
| PalaceAlley    | palace_alley        | a_pressure      |       940217 |   797.089 |   600.34  | ready           |
| Scaffolding    | scaffolding         | b_pressure      |        77416 |   647.594 |   749.349 | ready           |
| SideAlley      | side_alley          | rotation        |       894315 |   731.442 |   264.154 | ready           |
| Stairs         | stairs              | site_a          |       351426 |   545.854 |   632.175 | ready           |
| TSpawn         | t_spawn             | t_spawn_area    |      3668757 |   889.2   |   374.6   | ready           |
| TopofMid       | top_mid             | mid_control     |      1586063 |   718.802 |   429.111 | ready           |

## Sign-off rule

The reviewer must inspect the overlay and table, confirm A/B/mid/CT/rotation placement, and then record their identity, timestamp, reviewed region IDs, and this report path in `configs/quality/mirage_consolidation_evidence.yaml`.
