# Mirage Baseline Renewal

This report records an explicit, governed replacement of the frozen Mirage regression baseline.

- Previous baseline: `mirage_mvp_map_ready_v1`
- New baseline: `mirage_consolidated_v1`
- Approved by: `user_requested_mirage_consolidation`
- Reason: Utility lineage repair plus separation of 23 verified physical Mirage regions; round labels, semantic assignments, side datasets, and candidate-model inputs remained stable.
- Previous archive: `data\gold\validation\mirage_regression_baseline_archive\mirage_mvp_map_ready_v1_20261005t142409z`
- Datasets changed: `9` of `16`
- Previous critical differences: `306`
- Failed invariants allowed by policy: `region_timeline_unchanged`
- Candidate inputs and labels stable: `true`
- Semantic assignment changes: `0`

The prior baseline remains recoverable. Renewal is refused when round/label/model-input invariants drift, when semantic assignments change, or when unexpected row identities change.
