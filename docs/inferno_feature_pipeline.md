# Stage 8.8 -- Inferno Feature Pipeline Run & Multi-Map Gold Storage

## Purpose

Stage 8.8 runs the validated Inferno scope through the analytical feature pipeline and stores the result in consolidated Gold tables alongside Mirage.

The important architectural change is scoped Gold upsert: `--force` replaces only the selected target team + canonical map identity. It does not rewrite unrelated maps.

## Commands

```bash
python -m src.features.run_map_pipeline --config configs/project.yaml --target-map Inferno --target-team Vitality --force
python -m src.validation.multi_map_gold_gate --config configs/project.yaml --target-map Inferno --target-team Vitality --force
```

## Consolidated Outputs

These historical paths now hold multiple maps:

```text
data/gold/round_features/round_features_mvp.parquet
data/gold/round_features/round_base.parquet
data/gold/round_features/player_round_utility.parquet
data/gold/utility_events/utility_events.parquet
data/gold/region_presence/region_presence_by_round.parquet
data/gold/round_state/round_state_resolved.parquet
data/gold/round_features/round_features_t_side_all.parquet
data/gold/round_features/round_features_t_side_planted.parquet
data/gold/round_features/round_features_ct_side.parquet
data/gold/round_progression/round_region_timeline.parquet
data/gold/round_progression/death_context_by_round.parquet
data/gold/round_progression/bomb_carrier_timeline.parquet
data/gold/round_progression/round_outcome_context.parquet
```

## Current Snapshot

| Dataset | Mirage rows | Inferno rows |
| --- | ---: | ---: |
| `round_features_mvp` | 405 | 122 |
| `region_presence_by_round` | 43,961 | 17,760 |
| `round_state_resolved` | 405 | 122 |
| `round_features_t_side_all` | 180 | 65 |
| `round_features_t_side_planted` | 98 | 40 |
| `round_features_ct_side` | 225 | 57 |
| `round_region_timeline` | 43,961 | 17,760 |
| `death_context_by_round` | 2,736 | 786 |
| `bomb_carrier_timeline` | 8,910 | 2,684 |
| `round_outcome_context` | 405 | 122 |

The Inferno side split is now resolved as 65 T-side rounds and 57 CT-side rounds for Vitality. The planted T-side A/B candidate dataset has 40 high-confidence rows.

## Validation

`src.validation.multi_map_gold_gate` writes:

```text
data/gold/validation/multi_map_gold/gold_scope_inventory.parquet
data/gold/validation/multi_map_gold/gold_scoped_upsert_audit.parquet
data/gold/validation/multi_map_gold/gold_key_collision_audit.parquet
data/gold/validation/multi_map_gold/mirage_gold_preservation.parquet
data/gold/validation/multi_map_gold/inferno_feature_materialization.parquet
data/gold/validation/multi_map_gold/inferno_candidate_feature_materialization.parquet
data/gold/validation/multi_map_gold/inferno_semantic_feature_sanity.parquet
data/gold/validation/multi_map_gold/inferno_round_state_summary.parquet
data/gold/validation/multi_map_gold/inferno_side_dataset_summary.parquet
data/gold/validation/multi_map_gold/multi_map_gold_audit.parquet
```

Latest local gate status:

```text
overall_status = passed
blocking_issues = 0
inferno_round_features = 122
ready_for_inferno_feature_quality_gate = true
```

## Out Of Scope

Stage 8.8 does not run Inferno EDA, train models, retrain Mirage models, apply the Mirage model to Inferno, create dashboards, export to BigQuery, or add a new team/map.
