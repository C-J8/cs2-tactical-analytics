# Modeling Integrity & Refactor Regression

## Purpose

Stage 8.11.1 validates the Stage 8.11 Inferno A/B exploratory baseline after the shared-helper refactor. This is an integrity gate, not a model-improvement stage.

## Refactor Context

The repository now uses shared helpers in `src/utils/io.py`, `src/utils/reports.py`, and `src/utils/notebooks.py`. Stage 8.11.1 verifies that these helpers preserve pipeline behavior and that modeling does not silently approve incomplete evidence.

## Quality Artifact Lineage

The modeling dataset builder now reads real Stage 8.9 quality artifacts:

- `data/gold/validation/map_feature_quality/map_feature_quality_profile.{csv,parquet}`
- `data/gold/validation/map_feature_quality/map_feature_missingness.{csv,parquet}`
- `data/gold/validation/map_feature_quality/map_feature_degeneracy.{csv,parquet}`
- `data/gold/validation/map_feature_quality/map_feature_quality_audit.{csv,parquet}`

Legacy filenames such as `map_feature_quality_feature_audit` are not required.

## Fail-Closed Modeling Evidence

Mandatory quality/materialization artifacts must exist and contain the requested map/team scope. If a mandatory artifact is missing, the model dataset builder raises a precondition error.

If a candidate feature lacks row-level evidence, it receives `unknown_not_approved` and cannot enter the model.

## Feature Approval

A feature is approved only when it is present in the modeling source, horizon-safe, leakage-safe, quality-approved, materialization-supported, nonconstant in the modeling dataset, not an unresolved endpoint, and not a raw coordinate requiring normalization.

Current approved features: 8 of 11 candidate features.

## Comparison-Aware Finding Sensitivity

Stage 8.10.1 now dispatches sensitivity by comparison type:

- `cross_map`
- `<map_id>_A_vs_B`
- `<map_id>_planted_vs_no_plant`
- `cross_map_site_choice_distribution`

Unknown comparison types fail closed with `unsupported_comparison_type`.

## Leave-One-Demo-Out Revalidation

LODO no longer assumes cross-map behavior for every finding. The corrected pass produced:

- demo-fragile findings: 9
- stable LODO findings: 849
- hardened ranked findings: 9

## Fully-Exposed Revalidation

Fully-exposed sensitivity now recomputes the same comparison type as the original finding. The corrected pass produced:

- fully-exposed available findings: 2313
- exposure reversals: 661

## Complete Modeling Metrics

OOF metrics now include accuracy, balanced accuracy, macro F1, F1_A, F1_B, precision/recall by class, MCC, ROC AUC, Brier score, log loss, and confusion matrix counts.

Current OOF metrics:

- macro F1: 0.472
- balanced accuracy: 0.472
- MCC: -0.055
- ROC AUC: 0.487
- Brier score: 0.261
- log loss: 0.715
- confusion matrix: A->A 11, A->B 11, B->A 10, B->B 8

## Round-Level Error Analysis

`inferno_ab_error_analysis` is now one row per OOF error and retains `round_feature_id`, `round_id`, `parse_id`, `series_id`, `model_group_id`, fold metadata, predicted probabilities, true-class probability, confidence, and selected predictors with `feature__` prefixes.

Current row-level OOF errors: 21.

The aggregate error view is stored separately in `inferno_ab_error_summary`.

## Shared I/O Policy

`read_table_pair` keeps Parquet priority. CSV fallback supports:

- default mode with normal numeric inference;
- `string_preserving` mode for textual IDs, empty strings, and literal values such as `NA`;
- explicit failure for unsupported policies.

## Refactor Regression Tests

Shared-helper tests cover output writing, overwrite behavior, empty DataFrames, Parquet priority, CSV string preservation, unsupported policy failure, Markdown table behavior, and output-free notebook behavior.

Representative Stage 8.10.1 and Stage 8.11 tests cover comparison dispatch, LODO, fully-exposed sensitivity, fail-closed evidence, metrics, and round-level error analysis.

## Frozen Stage 8.11 Revalidation

The rerun preserved the frozen methodology:

- primary horizon: 35 seconds
- model: logistic regression
- penalty: L2
- C: 0.1
- threshold: 0.5
- validation: leave-one-group-out using `series_id`
- null method: group-aware label permutation
- no tuning, GridSearchCV, Optuna, model promotion, dashboard, BigQuery, new map, or new team

## Before / After Results

Core Stage 8.11 results remained stable after integrity correction:

- rows: 40
- A/B labels: 22 / 18
- groups: 5
- selected features: 8
- OOF macro F1: 0.472
- balanced accuracy: 0.472
- signal status: `no_signal`

The Stage 8.10.1 sensitivity counts changed because the old code was using cross-map fallback for within-map comparisons.

## Remaining Limitations

The Inferno A/B sample is still small: 40 planted T-side rounds across 5 groups. The current result remains exploratory and `no_signal`; this should lead to sample expansion/readiness work, not tuning.

## Readiness

`modeling_integrity_refactor_regression_audit` currently reports:

- `status = passed`
- `unknown_features_approved = false`
- `metrics_pack_complete = true`
- `round_level_error_analysis = true`
- `frozen_methodology_preserved = true`
- `core_gold_unchanged = true`
- `ready_for_stage_8_12 = true`
