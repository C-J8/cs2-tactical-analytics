# Stage 8.9.1 -- Feature Materialization Repair

## Purpose
Repair real upstream feature materialization issues found by the Inferno quality gate without relaxing thresholds.

## Repairs
- Flash usage is materialized from `grenades.parquet` trajectory entities.
- HE usage is materialized from `grenades.parquet` trajectory entities.
- `score_diff_before_round` is filled from previous-round winners using resolved round state.
- Utility endpoint metadata is explicit and remains unresolved when no deterministic endpoint evidence exists.
- Mirage mid-control structural mismatches are review-only; no mapping semantics were changed.

## Current Status
repair_status: `passed`
failed_checks: `0`
warning_checks: `1`
quality_gate_status: `passed`
ready_for_stage_8_10: `True`

## Output Tables
- `utility_source_capability.csv` / `utility_source_capability.parquet`
- `utility_source_policy_audit.csv` / `utility_source_policy_audit.parquet`
- `utility_event_reconstruction_audit.csv` / `utility_event_reconstruction_audit.parquet`
- `utility_endpoint_resolution_audit.csv` / `utility_endpoint_resolution_audit.parquet`
- `score_before_round_audit.csv` / `score_before_round_audit.parquet`
- `feature_materialization_change_manifest.csv` / `feature_materialization_change_manifest.parquet`
- `mirage_feature_migration_diff.csv` / `mirage_feature_migration_diff.parquet`
- `feature_materialization_repair_audit.csv` / `feature_materialization_repair_audit.parquet`
- `utility_type_feature_sanity.csv` / `utility_type_feature_sanity.parquet`
- `mid_control_structural_review.csv` / `mid_control_structural_review.parquet`
- `feature_materialization_capabilities.csv` / `feature_materialization_capabilities.parquet`
- `quality_gate_recovery.csv` / `quality_gate_recovery.parquet`
- `feature_materialization_repair_final_audit.csv` / `feature_materialization_repair_final_audit.parquet`

## Non-Goals
This stage does not implement tactical EDA, ML, predictions, dashboard, BigQuery, or model training.
