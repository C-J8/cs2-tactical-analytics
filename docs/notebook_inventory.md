# Notebook Inventory

This project keeps notebooks as lightweight inspection views. They are intentionally checked in without outputs so the repository stays small and reproducible.

## Current Working Views

| Notebook | Purpose |
|---|---|
| `03_feature_engineering_mvp.ipynb` | Inspect MVP round-feature outputs and temporal windows. |
| `04_side_datasets_and_progression.ipynb` | Inspect T-side/CT-side derived datasets. |
| `05_round_state_resolution.ipynb` | Inspect resolved round side, planting ownership, and A/B label quality. |
| `25_vitality_multi_map_tactical_eda.ipynb` | Inspect Mirage vs Inferno tactical EDA outputs. |
| `26_tactical_finding_hardening.ipynb` | Inspect consolidated and hardened tactical findings. |
| `27_inferno_ab_exploratory_baseline.ipynb` | Inspect the Inferno exploratory A/B baseline outputs. |

## Historical Stage Views

| Notebook | Stage |
|---|---|
| `01_validate_match_catalog.ipynb` | Match catalog validation. |
| `02_validate_parsed_demo.ipynb` | Parsed-demo validation. |
| `06_t_side_tactical_eda.ipynb` | Original Mirage T-side EDA. |
| `07_t_side_tactical_findings.ipynb` | Original Mirage tactical findings. |
| `08_t_side_manual_review_pack.ipynb` | Manual-review pack. |
| `09_t_side_ab_baseline_model.ipynb` | Mirage A/B baseline. |
| `10_t_side_ab_error_analysis.ipynb` | Mirage baseline error analysis. |
| `11_t_side_ab_refined_experiment.ipynb` | Refined Mirage experiment. |
| `12_t_side_ab_candidate_promotion.ipynb` | Candidate promotion package. |
| `13_final_mvp_report_pack.ipynb` | Final MVP report pack. |
| `14_feature_contract.ipynb` | Feature contract inspection. |
| `15_map_region_registry.ipynb` | Map registry inspection. |
| `16_map_ready_feature_refactor.ipynb` | Map-ready feature refactor audit. |
| `17_mirage_regression_gate.ipynb` | Mirage regression gate. |
| `18_inferno_onboarding.ipynb` | Inferno onboarding. |
| `19_multi_map_parsing.ipynb` | Multi-map parsing gate. |
| `20_map_area_discovery.ipynb` | Raw map-area discovery. |
| `21_inferno_region_mapping.ipynb` | Inferno region mapping. |
| `22_inferno_feature_pipeline.ipynb` | Scoped Inferno feature pipeline. |
| `23_inferno_feature_quality.ipynb` | Inferno feature-quality gate. |
| `24_feature_materialization_repair.ipynb` | Feature materialization repair. |

## Simplification Policy

- Keep notebooks output-free in Git.
- Prefer Markdown reports for narrative conclusions.
- Prefer notebooks only for local inspection of generated tables.
- Do not delete historical notebooks until their matching stage reports and tests cover the same workflow.
