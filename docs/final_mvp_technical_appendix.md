# Technical Appendix -- CS2 Tactical Analytics MVP

## Pipeline lineage
|   lineage_step | source_artifact                    | derived_artifact              | artifact_type     | purpose                                            | used_in_report   | notes                                            |
|---------------:|:-----------------------------------|:------------------------------|:------------------|:---------------------------------------------------|:-----------------|:-------------------------------------------------|
|              1 | manual matches seed                | matches_catalog               | catalog           | Defines match/map targets                          | True             | Offline-first source.                            |
|              2 | local demo archives                | dem_files_manifest            | archive manifest  | Tracks local files and extraction                  | True             | HLTV remote blocking handled manually.           |
|              3 | dem_files_manifest                 | silver parsed demo tables     | parsed data       | Consolidates parser output                         | True             | Only target-map eligible demos feed features.    |
|              4 | parse_manifest and parse_quality   | feature_eligible_demos        | quality gate      | Removes suspicious demos                           | True             | Quality gate is separate from raw parser output. |
|              5 | silver parsed demo tables          | round_features_mvp            | features          | Builds round features                              | True             | Uses full 115s windows.                          |
|              6 | round features and parsed evidence | round_state_resolved          | state table       | Resolves side and plant ownership                  | True             | Prevents opponent plants becoming target labels. |
|              7 | round_state_resolved               | round_features_t_side_planted | model dataset     | Creates high-confidence planted T-side A/B dataset | True             | No-plant outside the model.                      |
|              8 | T-side feature tables              | t_side_tactical_eda           | analysis          | Exploratory tactical summaries                     | True             | Observed associations only.                      |
|              9 | t_side_tactical_eda                | t_side_key_findings           | analysis          | Ranks candidate findings                           | True             | Manual review required.                          |
|             10 | round_features_t_side_planted      | ab_model_metrics              | model outputs     | Baseline A/B model                                 | True             | Leakage-controlled CV.                           |
|             11 | ab_model_predictions               | ab_error_analysis             | error analysis    | Summarizes errors                                  | True             | No retraining.                                   |
|             12 | ab_refined_experiment              | candidate_model_selection     | candidate package | Promotes exploratory candidate                     | True             | Stage 6.3 freezes config.                        |
|             13 | all prior gold outputs             | final_mvp_report              | report            | Final MVP documentation pack                       | True             | Stage 7 does not alter upstream data.            |

## Data quality gates
|   eligible_demos |   valid_full_map_demos |   feature_rounds |   t_side_rounds |   t_side_planted_rounds |   plant_A |   plant_B |   no_plant |   candidate_prediction_rows |   candidate_error_rows |   candidate_feature_count | manual_review_status   |
|-----------------:|-----------------------:|-----------------:|----------------:|------------------------:|----------:|----------:|-----------:|----------------------------:|-----------------------:|--------------------------:|:-----------------------|
|               18 |                     18 |              405 |             180 |                      98 |        72 |        26 |         82 |                          89 |                     25 |                        31 | pending                |

## Feature engineering summary
Feature engineering uses interval and cumulative windows through the full 115-second round.

## Round state resolution
Round state resolves target side, plant ownership, and conservative A/B labels before modeling.

## Side-specific datasets
T-side all, T-side planted, and CT-side datasets are separated to avoid label misuse.

## EDA and findings
|   finding_rank | finding_category   | evidence_strength   | manual_review_status                             |
|---------------:|:-------------------|:--------------------|:-------------------------------------------------|
|              1 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|              2 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|              3 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|              4 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|              5 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|              6 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|              7 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|              8 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|              9 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|             10 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|             11 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |
|             12 | A_vs_B_region      | strong_candidate    | candidate_pattern; current_manual_review=pending |

## Manual review pack
The manual review template remains the gate before treating findings or the candidate as final.

## Baseline modeling
Stage 6 uses leakage-controlled stratified out-of-fold validation.

## Error analysis
| candidate_id                                     |   total_errors |   A_predicted_as_B |   B_predicted_as_A |   high_confidence_errors |   high_confidence_B_predicted_as_A | top_error_priority   | error_interpretation                                                             | recommended_review_action                                              |
|:-------------------------------------------------|---------------:|-------------------:|-------------------:|-------------------------:|-----------------------------------:|:---------------------|:---------------------------------------------------------------------------------|:-----------------------------------------------------------------------|
| vitality_mirage_t_ab_35s_stable_only_logistic_v1 |             25 |                 15 |                 10 |                       13 |                                  4 | high                 | Errors are mixed across A and B directions; review high-confidence misses first. | Prioritize B_predicted_as_A and high-confidence errors in demo review. |

## Refined experiment
Stage 6.2 evaluates fixed feature sets at selected horizons; it is not a hyperparameter search.

## Candidate promotion
| candidate_id                                     |   horizon_seconds | feature_set_name   | model_name          |   macro_f1 |   balanced_accuracy |   recall_A |   recall_B |   precision_A |   precision_B |   support_A |   support_B |   total_errors |   B_predicted_as_A |   high_confidence_B_predicted_as_A |   delta_macro_f1_vs_baseline |   delta_recall_B_vs_baseline |   delta_B_predicted_as_A_vs_baseline | decision                         | decision_status       |
|:-------------------------------------------------|------------------:|:-------------------|:--------------------|-----------:|--------------------:|-----------:|-----------:|--------------:|--------------:|------------:|------------:|---------------:|-------------------:|-----------------------------------:|-----------------------------:|-----------------------------:|-------------------------------------:|:---------------------------------|:----------------------|
| vitality_mirage_t_ab_35s_stable_only_logistic_v1 |                35 | stable_only        | logistic_regression |   0.671101 |            0.682813 |   0.765625 |        0.6 |      0.830508 |           0.5 |          64 |          25 |             25 |                 10 |                                  4 |                     0.114017 |                         0.16 |                                   -4 | promote_as_exploratory_candidate | manual_review_pending |

## Artifact manifest
| artifact_name          | artifact_path                                                                   | artifact_type   | stage     | exists   | used_in_final_report   | description                                                                             |
|:-----------------------|:--------------------------------------------------------------------------------|:----------------|:----------|:---------|:-----------------------|:----------------------------------------------------------------------------------------|
| final_mvp_report       | docs/final_mvp_report.md                                                        | markdown        | Stage 7   | True     | True                   | Final readable MVP report. Candidate: vitality_mirage_t_ab_35s_stable_only_logistic_v1. |
| technical_appendix     | docs/final_mvp_technical_appendix.md                                            | markdown        | Stage 7   | True     | True                   | Reproducibility and lineage appendix.                                                   |
| presentation_outline   | docs/final_presentation_outline.md                                              | markdown        | Stage 7   | True     | True                   | Slide outline without PPTX generation.                                                  |
| candidate_model_card   | docs/t_side_ab_candidate_model_card.md                                          | markdown        | Stage 6.3 | True     | True                   | Candidate model card.                                                                   |
| candidate_config       | configs/modeling/t_side_ab_candidate_baseline.yaml                              | yaml            | Stage 6.3 | True     | True                   | Frozen candidate configuration.                                                         |
| candidate_metrics      | data/gold/modeling/t_side_ab_candidate/candidate_model_metrics.parquet          | parquet         | Stage 6.3 | True     | True                   | Candidate metrics.                                                                      |
| candidate_errors       | data/gold/modeling/t_side_ab_candidate/candidate_model_errors.parquet           | parquet         | Stage 6.3 | True     | True                   | Candidate error queue.                                                                  |
| t_side_key_findings    | data/gold/analysis/t_side_tactical_findings/t_side_key_findings.parquet         | parquet         | Stage 5.1 | True     | True                   | Ranked tactical findings.                                                               |
| manual_review_template | data/gold/analysis/t_side_manual_review/manual_review_decision_template.parquet | parquet         | Stage 5.2 | True     | True                   | Pending manual review ledger.                                                           |
| final_notebook         | notebooks/13_final_mvp_report_pack.ipynb                                        | notebook        | Stage 7   | True     | True                   | Report pack inspection notebook.                                                        |

## Reproducibility commands
```bash
python -m src.ingestion.build_match_catalog --config configs/project.yaml
python -m src.ingestion.scan_local_archives --config configs/project.yaml --extract --force
python -m src.parsing.probe_dem_metadata --config configs/project.yaml --include-known --force
python -m src.parsing.parse_demos --config configs/project.yaml --force
python -m src.parsing.parse_quality --config configs/project.yaml --force
python -m src.features.build_round_features --config configs/project.yaml --force
python -m src.features.round_state --config configs/project.yaml --force
python -m src.features.side_datasets --config configs/project.yaml --force
python -m src.analysis.t_side_eda --config configs/project.yaml --force
python -m src.analysis.t_side_findings --config configs/project.yaml --force
python -m src.analysis.t_side_manual_review --config configs/project.yaml --force
python -m src.modeling.t_side_ab_baseline --config configs/project.yaml --force
python -m src.modeling.t_side_ab_error_analysis --config configs/project.yaml --force
python -m src.modeling.t_side_ab_refined_experiment --config configs/project.yaml --force
python -m src.modeling.t_side_ab_candidate_promotion --config configs/project.yaml --force
python -m src.reporting.build_final_mvp_report --config configs/project.yaml --force
```
