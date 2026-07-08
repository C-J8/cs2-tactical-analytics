from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config.schemas import load_project_config
from src.utils.io import ensure_dir, read_catalog
from src.utils.logging import configure_logging


OUTPUT_NAMES = [
    "final_project_summary",
    "final_pipeline_stage_status",
    "final_data_lineage",
    "final_dataset_snapshot",
    "final_tactical_findings_summary",
    "final_model_candidate_summary",
    "final_model_error_summary",
    "final_limitations",
    "final_next_steps",
    "final_artifact_manifest",
    "final_report_audit",
]

DEFAULT_REPORT_VERSION = "v1"
REQUIRED_LIMITATIONS = [
    "small_sample",
    "class_B_lower_support",
    "manual_review_pending",
    "round_level_cv_only",
    "no_external_validation",
    "no_plant_out_of_scope",
    "ct_side_out_of_scope",
    "no_causal_claims",
    "demo_parse_dependency",
    "feature_interpretation_limits",
]


INPUT_SPECS = {
    "eda_overview": ("gold", "analysis/t_side_tactical_eda/t_side_eda_overview.parquet", True),
    "site_distribution": ("gold", "analysis/t_side_tactical_eda/t_side_site_distribution.parquet", True),
    "opponent_summary": ("gold", "analysis/t_side_tactical_eda/t_side_opponent_summary.parquet", False),
    "key_findings": ("gold", "analysis/t_side_tactical_findings/t_side_key_findings.parquet", True),
    "timing_breakpoints": (
        "gold",
        "analysis/t_side_tactical_findings/t_side_ab_timing_breakpoints.parquet",
        False,
    ),
    "findings_review_queue": (
        "gold",
        "analysis/t_side_tactical_findings/t_side_manual_review_queue.parquet",
        False,
    ),
    "manual_review_summary": ("gold", "analysis/t_side_manual_review/manual_review_summary.parquet", False),
    "manual_review_template": (
        "gold",
        "analysis/t_side_manual_review/manual_review_decision_template.parquet",
        True,
    ),
    "manual_review_readiness": (
        "gold",
        "analysis/t_side_manual_review/manual_review_model_readiness.parquet",
        False,
    ),
    "baseline_metrics": ("gold", "modeling/t_side_ab_baseline/ab_model_metrics.parquet", False),
    "error_overview": ("gold", "modeling/t_side_ab_error_analysis/ab_error_overview.parquet", False),
    "horizon_recommendation": (
        "gold",
        "modeling/t_side_ab_error_analysis/ab_horizon_practical_recommendation.parquet",
        False,
    ),
    "refined_recommendation": (
        "gold",
        "modeling/t_side_ab_refined_experiment/ab_refined_recommendation.parquet",
        False,
    ),
    "candidate_selection": ("gold", "modeling/t_side_ab_candidate/candidate_model_selection.parquet", True),
    "candidate_metrics": ("gold", "modeling/t_side_ab_candidate/candidate_model_metrics.parquet", True),
    "candidate_confusion": (
        "gold",
        "modeling/t_side_ab_candidate/candidate_model_confusion_matrix.parquet",
        True,
    ),
    "candidate_errors": ("gold", "modeling/t_side_ab_candidate/candidate_model_errors.parquet", True),
    "candidate_feature_set": ("gold", "modeling/t_side_ab_candidate/candidate_model_feature_set.parquet", True),
    "candidate_importance": (
        "gold",
        "modeling/t_side_ab_candidate/candidate_model_feature_importance.parquet",
        True,
    ),
    "candidate_comparison": (
        "gold",
        "modeling/t_side_ab_candidate/candidate_model_comparison_vs_baseline.parquet",
        True,
    ),
    "candidate_decision": ("gold", "modeling/t_side_ab_candidate/candidate_model_decision.parquet", True),
    "candidate_audit": ("gold", "modeling/t_side_ab_candidate/candidate_model_audit.parquet", True),
    "parse_audit": ("root", "data/bronze/parse_audit/parse_audit.parquet", False),
    "parse_quality": ("root", "data/bronze/parse_quality/parse_quality.parquet", False),
    "feature_eligible_demos": ("root", "data/silver/parsed_demos/feature_eligible_demos.parquet", False),
    "feature_audit": ("gold", "feature_audit/feature_audit.parquet", False),
    "side_dataset_audit": ("gold", "feature_audit/side_dataset_audit.parquet", False),
    "round_state_audit": ("gold", "round_state/round_state_audit.parquet", False),
}


def run_final_mvp_report(
    config_path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    target_team: str | None = None,
    target_map: str | None = None,
    report_version: str = DEFAULT_REPORT_VERSION,
    include_technical_appendix: bool = True,
) -> tuple[dict[str, pd.DataFrame], dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    project_root = config_path.resolve().parent.parent
    gold_dir = project.parsed_silver_dir.parent.parent / "gold"
    target_team = target_team or project.target_teams[0]
    target_map = target_map or project.target_maps[0]
    created_at = datetime.now(timezone.utc).isoformat()

    inputs, missing_optional, missing_required = load_inputs(project_root, gold_dir)
    if missing_required:
        raise FileNotFoundError(f"Required Stage 7 inputs missing: {', '.join(missing_required)}")

    frames = build_frames(
        inputs,
        target_team=target_team,
        target_map=target_map,
        report_version=report_version,
        missing_optional=missing_optional,
        created_at=created_at,
    )
    documents = build_documents(frames, include_technical_appendix=include_technical_appendix)

    outputs: dict[str, Path] = {}
    if not dry_run:
        output_dir = gold_dir / "reporting" / "final_mvp"
        outputs.update(write_outputs(frames, output_dir, force=force))
        docs_dir = project_root / "docs"
        outputs["final_mvp_report"] = write_text(documents["report"], docs_dir / "final_mvp_report.md", force=force)
        if include_technical_appendix:
            outputs["technical_appendix"] = write_text(
                documents["appendix"],
                docs_dir / "final_mvp_technical_appendix.md",
                force=force,
            )
        outputs["presentation_outline"] = write_text(
            documents["outline"],
            docs_dir / "final_presentation_outline.md",
            force=force,
        )
        outputs["notebook"] = write_text(
            build_notebook_json(),
            project_root / "notebooks" / "13_final_mvp_report_pack.ipynb",
            force=force,
        )

    summary = {
        "summary_rows": len(frames["final_project_summary"]),
        "stage_rows": len(frames["final_pipeline_stage_status"]),
        "lineage_rows": len(frames["final_data_lineage"]),
        "finding_rows": len(frames["final_tactical_findings_summary"]),
        "artifact_rows": len(frames["final_artifact_manifest"]),
        "output_tables": len(frames),
    }
    return frames, outputs, summary


def load_inputs(project_root: Path, gold_dir: Path) -> tuple[dict[str, pd.DataFrame], list[str], list[str]]:
    inputs: dict[str, pd.DataFrame] = {}
    missing_optional: list[str] = []
    missing_required: list[str] = []
    for name, (base, relative, required) in INPUT_SPECS.items():
        path = (gold_dir / relative) if base == "gold" else (project_root / relative)
        if path.exists():
            inputs[name] = read_catalog(path)
        else:
            inputs[name] = pd.DataFrame()
            if required:
                missing_required.append(name)
            else:
                missing_optional.append(name)
    return inputs, missing_optional, missing_required


def build_frames(
    inputs: dict[str, pd.DataFrame],
    *,
    target_team: str,
    target_map: str,
    report_version: str,
    missing_optional: list[str],
    created_at: str,
) -> dict[str, pd.DataFrame]:
    candidate = candidate_context(inputs)
    manual_status = manual_review_status(inputs["manual_review_template"])
    dataset_snapshot = build_dataset_snapshot(inputs, candidate=candidate, manual_status=manual_status)
    candidate_summary = build_candidate_summary(inputs)
    error_summary = build_error_summary(inputs, candidate["candidate_id"])
    limitations = build_limitations(manual_status)
    next_steps = build_next_steps()
    artifact_manifest = build_artifact_manifest(candidate)
    frames = {
        "final_project_summary": build_project_summary(
            target_team=target_team,
            target_map=target_map,
            report_version=report_version,
            candidate=candidate,
            manual_status=manual_status,
            created_at=created_at,
        ),
        "final_pipeline_stage_status": build_stage_status(),
        "final_data_lineage": build_data_lineage(),
        "final_dataset_snapshot": dataset_snapshot,
        "final_tactical_findings_summary": build_tactical_findings(inputs, manual_status),
        "final_model_candidate_summary": candidate_summary,
        "final_model_error_summary": error_summary,
        "final_limitations": limitations,
        "final_next_steps": next_steps,
        "final_artifact_manifest": artifact_manifest,
    }
    frames["final_report_audit"] = build_audit(
        frames,
        report_version=report_version,
        target_team=target_team,
        target_map=target_map,
        missing_optional=missing_optional,
        manual_status=manual_status,
        created_at=created_at,
    )
    return frames


def candidate_context(inputs: dict[str, pd.DataFrame]) -> dict[str, Any]:
    selection = first_row(inputs["candidate_selection"])
    decision = first_row(inputs["candidate_decision"])
    metrics = first_row(inputs["candidate_metrics"])
    comparison = first_row(inputs["candidate_comparison"])
    candidate_id = selection.get("candidate_id")
    if not candidate_id:
        raise ValueError("Candidate promotion output is empty; run Stage 6.3 first.")
    return {
        "candidate_id": candidate_id,
        "decision": decision.get("decision", "unknown"),
        "decision_status": decision.get("decision_status", "unknown"),
        "horizon_seconds": selection.get("candidate_horizon_seconds", metrics.get("horizon_seconds")),
        "feature_set_name": selection.get("candidate_feature_set", metrics.get("feature_set_name")),
        "model_name": selection.get("candidate_model_name", metrics.get("model_name")),
        "macro_f1": metrics.get("macro_f1"),
        "recall_B": metrics.get("recall_B"),
        "delta_macro_f1": comparison.get("delta_macro_f1"),
        "delta_recall_B": comparison.get("delta_recall_B"),
        "delta_B_predicted_as_A": comparison.get("delta_B_predicted_as_A"),
    }


def first_row(frame: pd.DataFrame) -> dict[str, Any]:
    return frame.iloc[0].to_dict() if not frame.empty else {}


def manual_review_status(template: pd.DataFrame) -> str:
    if template.empty or "review_decision" not in template.columns:
        return "missing"
    values = set(template["review_decision"].fillna("").astype(str).str.strip().str.casefold())
    values.discard("")
    if not values or values <= {"pending"}:
        return "pending"
    return "applied_or_partial"


def build_project_summary(
    *,
    target_team: str,
    target_map: str,
    report_version: str,
    candidate: dict[str, Any],
    manual_status: str,
    created_at: str,
) -> pd.DataFrame:
    candidate_label = (
        f"{int(candidate['horizon_seconds'])}s {candidate['feature_set_name']} {candidate['model_name']}"
    )
    main_result = (
        f"{candidate_label} candidate improved macro F1 and recall_B versus the matching Stage 6 baseline "
        "while reducing B_predicted_as_A errors."
    )
    return pd.DataFrame(
        [
            {
                "project_name": "cs2-tactical-analytics",
                "target_team": target_team,
                "target_map": target_map,
                "scope": f"{target_team} T-side {target_map} planted-round A/B site prediction",
                "report_version": report_version,
                "candidate_id": candidate["candidate_id"],
                "candidate_decision": candidate["decision"],
                "candidate_status": candidate["decision_status"],
                "main_result": main_result,
                "main_limitation": f"manual_review_{manual_status}; small sample; no external validation",
                "recommended_next_step": "complete_manual_review",
                "created_at": created_at,
            }
        ]
    )


def build_stage_status() -> pd.DataFrame:
    rows = [
        stage("Stage 1", "Match Catalog", "Build match/map catalog", "manual seed", "matches_catalog", "ok", "Offline seed remains source of truth."),
        stage("Stage 2", "Local Demo Archive", "Register and extract local archives", "matches_catalog", "demo manifests", "ok", "Supports HLTV manual download flow."),
        stage("Stage 3", "Demo Parsing", "Parse target-map demos", "dem_files_manifest", "silver parsed tables", "ok", "Awpy tables feed downstream stages."),
        stage("Stage 3.6", "Parse Quality Gate", "Filter feature-eligible demos", "parse_manifest", "feature_eligible_demos", "ok", "Prevents short/suspicious demos from entering features."),
        stage("Stage 4", "Feature Engineering", "Build full-round features", "silver parsed tables", "round_features_mvp", "ok", "Uses configured windows through 115s."),
        stage("Stage 4.2", "Round State Resolution", "Resolve T/CT and plant ownership", "round features and parsed evidence", "round_state_resolved", "ok", "A/B labels only for target-team T-side plants."),
        stage("Stage 4.3", "Side Datasets", "Split T-side and CT-side datasets", "round_state_resolved", "side datasets", "ok", "T-side planted feeds A/B modeling."),
        stage("Stage 5", "T-side EDA", "Summarize tactical patterns", "T-side gold tables", "t_side_tactical_eda", "ok", "Exploratory, not causal."),
        stage("Stage 5.1", "Tactical Findings", "Rank candidate tactical findings", "Stage 5 aggregates", "t_side_key_findings", "ok", "Findings require review."),
        stage("Stage 5.2", "Manual Review Pack", "Create concrete review queue", "Stage 5.1 findings", "manual_review_template", "warning", "Review remains pending."),
        stage("Stage 6", "A/B Baseline", "Train leakage-controlled baseline", "t_side_planted", "ab_model_metrics", "ok", "High-confidence planted rounds only."),
        stage("Stage 6.1", "Error Analysis", "Interpret baseline errors", "Stage 6 outputs", "ab_error_analysis", "ok", "No new model training."),
        stage("Stage 6.2", "Refined Experiment", "Compare fixed feature sets", "Stage 6 controls", "ab_refined_recommendation", "ok", "Selected 35s stable_only logistic candidate."),
        stage("Stage 6.3", "Candidate Promotion", "Freeze candidate and model card", "Stage 6.2 outputs", "candidate package", "warning", "Exploratory until manual review is complete."),
        stage("Stage 7", "Final MVP Report Pack", "Consolidate final report package", "Prior stage outputs", "final_mvp report pack", "ok", "Documentation-only closure stage."),
    ]
    return pd.DataFrame(rows)


def stage(
    stage_id: str,
    stage_name: str,
    purpose: str,
    main_input: str,
    main_output: str,
    status: str,
    notes: str,
) -> dict[str, str]:
    return {
        "stage_id": stage_id,
        "stage_name": stage_name,
        "purpose": purpose,
        "main_input": main_input,
        "main_output": main_output,
        "status": status,
        "notes": notes,
    }


def build_data_lineage() -> pd.DataFrame:
    rows = [
        lineage(1, "manual matches seed", "matches_catalog", "catalog", "Defines match/map targets", True, "Offline-first source."),
        lineage(2, "local demo archives", "dem_files_manifest", "archive manifest", "Tracks local files and extraction", True, "HLTV remote blocking handled manually."),
        lineage(3, "dem_files_manifest", "silver parsed demo tables", "parsed data", "Consolidates parser output", True, "Only target-map eligible demos feed features."),
        lineage(4, "parse_manifest and parse_quality", "feature_eligible_demos", "quality gate", "Removes suspicious demos", True, "Quality gate is separate from raw parser output."),
        lineage(5, "silver parsed demo tables", "round_features_mvp", "features", "Builds round features", True, "Uses full 115s windows."),
        lineage(6, "round features and parsed evidence", "round_state_resolved", "state table", "Resolves side and plant ownership", True, "Prevents opponent plants becoming target labels."),
        lineage(7, "round_state_resolved", "round_features_t_side_planted", "model dataset", "Creates high-confidence planted T-side A/B dataset", True, "No-plant outside the model."),
        lineage(8, "T-side feature tables", "t_side_tactical_eda", "analysis", "Exploratory tactical summaries", True, "Observed associations only."),
        lineage(9, "t_side_tactical_eda", "t_side_key_findings", "analysis", "Ranks candidate findings", True, "Manual review required."),
        lineage(10, "round_features_t_side_planted", "ab_model_metrics", "model outputs", "Baseline A/B model", True, "Leakage-controlled CV."),
        lineage(11, "ab_model_predictions", "ab_error_analysis", "error analysis", "Summarizes errors", True, "No retraining."),
        lineage(12, "ab_refined_experiment", "candidate_model_selection", "candidate package", "Promotes exploratory candidate", True, "Stage 6.3 freezes config."),
        lineage(13, "all prior gold outputs", "final_mvp_report", "report", "Final MVP documentation pack", True, "Stage 7 does not alter upstream data."),
    ]
    return pd.DataFrame(rows)


def lineage(
    lineage_step: int,
    source_artifact: str,
    derived_artifact: str,
    artifact_type: str,
    purpose: str,
    used_in_report: bool,
    notes: str,
) -> dict[str, Any]:
    return {
        "lineage_step": lineage_step,
        "source_artifact": source_artifact,
        "derived_artifact": derived_artifact,
        "artifact_type": artifact_type,
        "purpose": purpose,
        "used_in_report": used_in_report,
        "notes": notes,
    }


def build_dataset_snapshot(
    inputs: dict[str, pd.DataFrame],
    *,
    candidate: dict[str, Any],
    manual_status: str,
) -> pd.DataFrame:
    feature_eligible = inputs["feature_eligible_demos"]
    parse_quality = inputs["parse_quality"]
    overview = first_row(inputs["eda_overview"])
    round_state = first_row(inputs["round_state_audit"])
    side_audit = inputs["side_dataset_audit"]
    planted = side_audit[side_audit.get("dataset_type", pd.Series(dtype=str)).eq("t_side_planted")]
    t_side_all = side_audit[side_audit.get("dataset_type", pd.Series(dtype=str)).eq("t_side_all")]
    metrics = first_row(inputs["candidate_metrics"])
    predictions = inputs["candidate_selection"]
    feature_set = inputs["candidate_feature_set"]
    feature_rows = feature_set[~feature_set.get("feature_name", pd.Series(dtype=str)).eq("__feature_set_summary__")]
    return pd.DataFrame(
        [
            {
                "eligible_demos": int(len(feature_eligible)) if not feature_eligible.empty else np.nan,
                "valid_full_map_demos": int(parse_quality["quality_status"].eq("valid_full_map").sum())
                if "quality_status" in parse_quality.columns
                else np.nan,
                "feature_rounds": int(round_state.get("total_rounds", np.nan)),
                "t_side_rounds": int(overview.get("total_t_side_rounds", first_value(t_side_all, "row_count"))),
                "t_side_planted_rounds": int(first_value(planted, "row_count", metrics.get("support_A", 0) + metrics.get("support_B", 0))),
                "plant_A": int(overview.get("total_plant_A", metrics.get("support_A", 0))),
                "plant_B": int(overview.get("total_plant_B", metrics.get("support_B", 0))),
                "no_plant": int(overview.get("total_no_plant", np.nan)),
                "candidate_prediction_rows": int(metrics.get("support_A", 0) + metrics.get("support_B", 0))
                if not predictions.empty
                else np.nan,
                "candidate_error_rows": int(metrics.get("total_errors", np.nan)),
                "candidate_feature_count": int(len(feature_rows)) if not feature_rows.empty else np.nan,
                "manual_review_status": manual_status,
            }
        ]
    )


def first_value(frame: pd.DataFrame, column: str, default: Any = np.nan) -> Any:
    if frame.empty or column not in frame.columns:
        return default
    return frame.iloc[0][column]


def build_tactical_findings(inputs: dict[str, pd.DataFrame], manual_status: str) -> pd.DataFrame:
    findings = inputs["key_findings"].copy()
    if findings.empty:
        return pd.DataFrame(
            columns=[
                "finding_rank",
                "finding_category",
                "finding_text",
                "evidence_strength",
                "support_table",
                "support_metric",
                "manual_review_status",
                "report_use",
            ]
        )
    findings = findings.head(12).copy().reset_index(drop=True)
    findings["finding_rank"] = findings.index + 1
    findings["finding_text"] = findings["finding_text"].map(conservative_finding_text)
    findings["manual_review_status"] = np.where(
        findings.get("needs_manual_review", False),
        f"requires_demo_review; current_manual_review={manual_status}",
        f"candidate_pattern; current_manual_review={manual_status}",
    )
    findings["report_use"] = "Use as candidate observed association, not causal claim."
    return findings[
        [
            "finding_rank",
            "finding_category",
            "finding_text",
            "evidence_strength",
            "support_table",
            "support_metric",
            "manual_review_status",
            "report_use",
        ]
    ]


def conservative_finding_text(text: Any) -> str:
    return f"Candidate pattern: {text} Requires demo review before tactical interpretation."


def build_candidate_summary(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    metrics = inputs["candidate_metrics"].copy()
    comparison = inputs["candidate_comparison"].copy()
    decision = first_row(inputs["candidate_decision"])
    if metrics.empty:
        return pd.DataFrame(columns=model_candidate_columns())
    merged = metrics.merge(
        comparison[
            [
                "candidate_id",
                "delta_macro_f1",
                "delta_recall_B",
                "delta_B_predicted_as_A",
            ]
        ],
        on="candidate_id",
        how="left",
    )
    merged["decision"] = decision.get("decision")
    merged["decision_status"] = decision.get("decision_status")
    return merged.rename(
        columns={
            "delta_macro_f1": "delta_macro_f1_vs_baseline",
            "delta_recall_B": "delta_recall_B_vs_baseline",
            "delta_B_predicted_as_A": "delta_B_predicted_as_A_vs_baseline",
        }
    ).reindex(columns=model_candidate_columns())


def model_candidate_columns() -> list[str]:
    return [
        "candidate_id",
        "horizon_seconds",
        "feature_set_name",
        "model_name",
        "macro_f1",
        "balanced_accuracy",
        "recall_A",
        "recall_B",
        "precision_A",
        "precision_B",
        "support_A",
        "support_B",
        "total_errors",
        "B_predicted_as_A",
        "high_confidence_B_predicted_as_A",
        "delta_macro_f1_vs_baseline",
        "delta_recall_B_vs_baseline",
        "delta_B_predicted_as_A_vs_baseline",
        "decision",
        "decision_status",
    ]


def build_error_summary(inputs: dict[str, pd.DataFrame], candidate_id: str) -> pd.DataFrame:
    metrics = first_row(inputs["candidate_metrics"])
    errors = inputs["candidate_errors"]
    priorities = errors["suggested_review_priority"].value_counts() if "suggested_review_priority" in errors else pd.Series()
    total_errors = int(metrics.get("total_errors", len(errors)))
    b_to_a = int(metrics.get("B_predicted_as_A", 0))
    a_to_b = int(metrics.get("A_predicted_as_B", 0))
    high_errors = int(metrics.get("high_confidence_errors", 0))
    high_b = int(metrics.get("high_confidence_B_predicted_as_A", 0))
    return pd.DataFrame(
        [
            {
                "candidate_id": candidate_id,
                "total_errors": total_errors,
                "A_predicted_as_B": a_to_b,
                "B_predicted_as_A": b_to_a,
                "high_confidence_errors": high_errors,
                "high_confidence_B_predicted_as_A": high_b,
                "top_error_priority": priorities.index[0] if not priorities.empty else "none",
                "error_interpretation": error_interpretation(total_errors, b_to_a, high_b),
                "recommended_review_action": "Prioritize B_predicted_as_A and high-confidence errors in demo review.",
            }
        ]
    )


def error_interpretation(total_errors: int, b_to_a: int, high_b: int) -> str:
    if total_errors == 0:
        return "No out-of-fold errors recorded for the candidate."
    if b_to_a >= total_errors / 2:
        return f"B_predicted_as_A remains the main error direction; {high_b} are high-confidence."
    return "Errors are mixed across A and B directions; review high-confidence misses first."


def build_limitations(manual_status: str) -> pd.DataFrame:
    definitions = {
        "small_sample": ("data", "Current MVP sample is small.", "Metrics can vary materially.", "Add more demos.", "high"),
        "class_B_lower_support": ("data", "Plant B has lower support than plant A.", "B metrics are less stable.", "Collect more B examples.", "high"),
        "manual_review_pending": ("validation", f"Manual review is {manual_status}.", "Candidate remains exploratory.", "Complete review template.", "high"),
        "round_level_cv_only": ("validation", "Validation uses round-level CV.", "May overstate generalization.", "Try temporal or series split.", "medium"),
        "no_external_validation": ("validation", "No external validation set exists yet.", "Generalization is unknown.", "Hold out future matches.", "high"),
        "no_plant_out_of_scope": ("scope", "No-plant rounds are outside A/B model.", "Model covers only planted rounds.", "Treat no-plant as separate task.", "medium"),
        "ct_side_out_of_scope": ("scope", "CT-side is not modeled in this MVP.", "Defensive insights remain separate.", "Plan CT-side stage later.", "medium"),
        "no_causal_claims": ("interpretation", "Findings are associations, not causes.", "Avoid tactical overclaiming.", "Use demo review and experiments.", "high"),
        "demo_parse_dependency": ("data_quality", "All outputs depend on parsed demo quality.", "Parser gaps can affect features.", "Keep quality gate and audits.", "medium"),
        "feature_interpretation_limits": ("interpretation", "Feature importance is descriptive.", "Coefficients are not tactical truth.", "Use examples and review context.", "medium"),
    }
    return pd.DataFrame(
        [
            {
                "limitation_id": key,
                "category": category,
                "limitation_text": text,
                "impact": impact,
                "mitigation_or_next_step": mitigation,
                "severity": severity,
            }
            for key, (category, text, impact, mitigation, severity) in definitions.items()
        ]
    )


def build_next_steps() -> pd.DataFrame:
    rows = [
        ("complete_manual_review", "Validate findings and candidate errors against demos.", "Stage 5.2 review pack", "high", "analyst"),
        ("inspect_candidate_errors", "Understand remaining B_predicted_as_A misses.", "Stage 6.3 error table", "high", "analyst"),
        ("freeze_report_examples", "Pick clear examples for presentation.", "manual review decisions", "medium", "analyst"),
        ("consider_temporal_or_series_split", "Test generalization more honestly.", "more data or enough series", "high", "modeling"),
        ("expand_maps_or_teams", "Check whether patterns hold beyond Mirage/Vitality.", "stable MVP pipeline", "medium", "data"),
        ("evaluate_no_plant_as_separate_task", "Model failed attacks without forcing A/B labels.", "more no-plant review", "medium", "modeling"),
        ("prepare_final_presentation", "Turn the report pack into a concise story.", "Stage 7 outputs", "medium", "analyst"),
    ]
    return pd.DataFrame(
        [
            {
                "step_rank": index,
                "next_step": name,
                "purpose": purpose,
                "depends_on": depends_on,
                "priority": priority,
                "recommended_owner": owner,
            }
            for index, (name, purpose, depends_on, priority, owner) in enumerate(rows, start=1)
        ]
    )


def build_artifact_manifest(candidate: dict[str, Any]) -> pd.DataFrame:
    artifacts = [
        artifact("final_mvp_report", "docs/final_mvp_report.md", "markdown", "Stage 7", True, "Final readable MVP report."),
        artifact("technical_appendix", "docs/final_mvp_technical_appendix.md", "markdown", "Stage 7", True, "Reproducibility and lineage appendix."),
        artifact("presentation_outline", "docs/final_presentation_outline.md", "markdown", "Stage 7", True, "Slide outline without PPTX generation."),
        artifact("candidate_model_card", "docs/t_side_ab_candidate_model_card.md", "markdown", "Stage 6.3", True, "Candidate model card."),
        artifact("candidate_config", "configs/modeling/t_side_ab_candidate_baseline.yaml", "yaml", "Stage 6.3", True, "Frozen candidate configuration."),
        artifact("candidate_metrics", "data/gold/modeling/t_side_ab_candidate/candidate_model_metrics.parquet", "parquet", "Stage 6.3", True, "Candidate metrics."),
        artifact("candidate_errors", "data/gold/modeling/t_side_ab_candidate/candidate_model_errors.parquet", "parquet", "Stage 6.3", True, "Candidate error queue."),
        artifact("t_side_key_findings", "data/gold/analysis/t_side_tactical_findings/t_side_key_findings.parquet", "parquet", "Stage 5.1", True, "Ranked tactical findings."),
        artifact("manual_review_template", "data/gold/analysis/t_side_manual_review/manual_review_decision_template.parquet", "parquet", "Stage 5.2", True, "Pending manual review ledger."),
        artifact("final_notebook", "notebooks/13_final_mvp_report_pack.ipynb", "notebook", "Stage 7", True, "Report pack inspection notebook."),
    ]
    frame = pd.DataFrame(artifacts)
    frame["exists"] = frame.apply(lambda row: bool(row["stage"] == "Stage 7" or Path(row["artifact_path"]).exists()), axis=1)
    frame.loc[frame["artifact_name"].eq("final_mvp_report"), "description"] += f" Candidate: {candidate['candidate_id']}."
    return frame


def artifact(
    artifact_name: str,
    artifact_path: str,
    artifact_type: str,
    stage: str,
    used_in_final_report: bool,
    description: str,
) -> dict[str, Any]:
    return {
        "artifact_name": artifact_name,
        "artifact_path": artifact_path,
        "artifact_type": artifact_type,
        "stage": stage,
        "exists": False,
        "used_in_final_report": used_in_final_report,
        "description": description,
    }


def build_audit(
    frames: dict[str, pd.DataFrame],
    *,
    report_version: str,
    target_team: str,
    target_map: str,
    missing_optional: list[str],
    manual_status: str,
    created_at: str,
) -> pd.DataFrame:
    status = "warning" if missing_optional or manual_status == "pending" else "ok"
    return pd.DataFrame(
        [
            {
                "audit_id": "final_mvp_report_pack",
                "report_version": report_version,
                "target_team": target_team,
                "target_map": target_map,
                "required_inputs_found": True,
                "missing_optional_inputs": "|".join(missing_optional) if missing_optional else "none",
                "output_tables": len(frames) + 1,
                "documents_written": 3,
                "notebook_written": True,
                "status": status,
                "created_at": created_at,
            }
        ]
    )


def build_documents(frames: dict[str, pd.DataFrame], *, include_technical_appendix: bool) -> dict[str, str]:
    report = build_final_report(frames)
    appendix = build_technical_appendix(frames) if include_technical_appendix else ""
    outline = build_presentation_outline(frames)
    return {"report": report, "appendix": appendix, "outline": outline}


def build_final_report(frames: dict[str, pd.DataFrame]) -> str:
    summary = frames["final_project_summary"]
    snapshot = frames["final_dataset_snapshot"]
    findings = frames["final_tactical_findings_summary"].head(6)
    candidate = frames["final_model_candidate_summary"]
    errors = frames["final_model_error_summary"]
    features = frames["final_artifact_manifest"][frames["final_artifact_manifest"]["artifact_name"].eq("candidate_config")]
    limitations = frames["final_limitations"]
    decision = summary.iloc[0]["candidate_decision"]
    return "\n".join(
        [
            "# Final MVP Report -- CS2 Tactical Analytics",
            "",
            "## Executive summary",
            markdown_table(summary, ["scope", "candidate_id", "candidate_decision", "main_result", "main_limitation"]),
            "",
            "## Project scope",
            "The MVP covers Vitality T-side Mirage planted-round A/B site prediction. No-plant and CT-side modeling remain out of scope.",
            "",
            "## Data and pipeline",
            markdown_table(snapshot, list(snapshot.columns)),
            "",
            "## T-side tactical findings",
            markdown_table(findings, ["finding_rank", "finding_category", "finding_text", "evidence_strength"]),
            "",
            "## Modeling task",
            "The model predicts target-team plant A versus plant B only for high-confidence planted T-side rounds.",
            "",
            "## Baseline and refinement",
            "Stage 6 established the leakage-controlled baseline. Stage 6.2 compared fixed feature sets and horizons without tuning.",
            "",
            "## Promoted candidate",
            markdown_table(candidate, ["candidate_id", "horizon_seconds", "feature_set_name", "model_name", "decision", "decision_status"]),
            "",
            "## Candidate performance",
            markdown_table(candidate, ["macro_f1", "balanced_accuracy", "recall_A", "recall_B", "support_A", "support_B", "delta_macro_f1_vs_baseline", "delta_recall_B_vs_baseline", "delta_B_predicted_as_A_vs_baseline"]),
            "",
            "## Error profile",
            markdown_table(errors, list(errors.columns)),
            "",
            "## Feature summary",
            markdown_table(features, ["artifact_name", "artifact_path", "description"]),
            "",
            "## Limitations",
            markdown_table(limitations, ["limitation_id", "impact", "mitigation_or_next_step", "severity"]),
            "",
            "## Decision",
            f"The current candidate decision is `{decision}`. It remains exploratory while manual review is pending.",
            "",
            "## Recommended next steps",
            markdown_table(frames["final_next_steps"], ["step_rank", "next_step", "purpose", "priority"]),
            "",
        ]
    )


def build_technical_appendix(frames: dict[str, pd.DataFrame]) -> str:
    commands = [
        "python -m src.ingestion.build_match_catalog --config configs/project.yaml",
        "python -m src.ingestion.scan_local_archives --config configs/project.yaml --extract --force",
        "python -m src.parsing.probe_dem_metadata --config configs/project.yaml --include-known --force",
        "python -m src.parsing.parse_demos --config configs/project.yaml --force",
        "python -m src.parsing.parse_quality --config configs/project.yaml --force",
        "python -m src.features.build_round_features --config configs/project.yaml --force",
        "python -m src.features.round_state --config configs/project.yaml --force",
        "python -m src.features.side_datasets --config configs/project.yaml --force",
        "python -m src.analysis.t_side_eda --config configs/project.yaml --force",
        "python -m src.analysis.t_side_findings --config configs/project.yaml --force",
        "python -m src.analysis.t_side_manual_review --config configs/project.yaml --force",
        "python -m src.modeling.t_side_ab_baseline --config configs/project.yaml --force",
        "python -m src.modeling.t_side_ab_error_analysis --config configs/project.yaml --force",
        "python -m src.modeling.t_side_ab_refined_experiment --config configs/project.yaml --force",
        "python -m src.modeling.t_side_ab_candidate_promotion --config configs/project.yaml --force",
        "python -m src.reporting.build_final_mvp_report --config configs/project.yaml --force",
    ]
    return "\n".join(
        [
            "# Technical Appendix -- CS2 Tactical Analytics MVP",
            "",
            "## Pipeline lineage",
            markdown_table(frames["final_data_lineage"], list(frames["final_data_lineage"].columns), top_n=30),
            "",
            "## Data quality gates",
            markdown_table(frames["final_dataset_snapshot"], list(frames["final_dataset_snapshot"].columns)),
            "",
            "## Feature engineering summary",
            "Feature engineering uses interval and cumulative windows through the full 115-second round.",
            "",
            "## Round state resolution",
            "Round state resolves target side, plant ownership, and conservative A/B labels before modeling.",
            "",
            "## Side-specific datasets",
            "T-side all, T-side planted, and CT-side datasets are separated to avoid label misuse.",
            "",
            "## EDA and findings",
            markdown_table(frames["final_tactical_findings_summary"], ["finding_rank", "finding_category", "evidence_strength", "manual_review_status"], top_n=12),
            "",
            "## Manual review pack",
            "The manual review template remains the gate before treating findings or the candidate as final.",
            "",
            "## Baseline modeling",
            "Stage 6 uses leakage-controlled stratified out-of-fold validation.",
            "",
            "## Error analysis",
            markdown_table(frames["final_model_error_summary"], list(frames["final_model_error_summary"].columns)),
            "",
            "## Refined experiment",
            "Stage 6.2 evaluates fixed feature sets at selected horizons; it is not a hyperparameter search.",
            "",
            "## Candidate promotion",
            markdown_table(frames["final_model_candidate_summary"], list(frames["final_model_candidate_summary"].columns)),
            "",
            "## Artifact manifest",
            markdown_table(frames["final_artifact_manifest"], list(frames["final_artifact_manifest"].columns), top_n=40),
            "",
            "## Reproducibility commands",
            "```bash",
            "\n".join(commands),
            "```",
            "",
        ]
    )


def build_presentation_outline(frames: dict[str, pd.DataFrame]) -> str:
    slides = [
        ("Title", "Introduce the MVP.", "CS2 Tactical Analytics; Vitality Mirage; offline-first pipeline", "Project title and scope", "Frame the work as an MVP, not a product."),
        ("Problem and motivation", "Explain why tactical data needs structure.", "Demos are rich but hard to compare; manual review needs prioritization", "Pipeline diagram", "Emphasize analyst workflow."),
        ("Scope", "Set boundaries.", "Vitality T-side Mirage; planted A/B only; no CT-side/no-plant model", "Scope table", "Boundaries protect interpretation."),
        ("Data pipeline", "Show how raw demos become features.", "Catalog; archives; parsing; quality; features; state; modeling", "Lineage table", "Point to auditability."),
        ("Dataset snapshot", "Summarize sample size.", "Demos; T rounds; planted rounds; A/B balance", "Dataset snapshot table", "Mention class imbalance."),
        ("Tactical EDA", "Show descriptive analysis layer.", "Region, utility, no-plant, progression summaries", "EDA overview", "No causal claims."),
        ("Key findings", "Present candidate patterns.", "Top ranked associations require demo review", "Top findings table", "Language should stay conservative."),
        ("Modeling task", "Define label and exclusions.", "High-confidence T-side planted A/B only", "Target definition", "No-plant is separate."),
        ("Baseline model", "Explain Stage 6.", "Leakage-controlled CV; horizon filters; baseline comparison", "Baseline metrics", "Avoid production claims."),
        ("Error analysis", "Explain what failed.", "B-predicted-as-A remained important", "Error summary", "Motivates refinement."),
        ("Refined candidate", "Show selected candidate.", "35s stable_only logistic_regression", "Candidate summary", "Chosen for B behavior improvement."),
        ("Candidate model card", "State decision and cautions.", "Exploratory candidate; manual review pending", "Model card excerpt", "Be explicit about limitations."),
        ("Limitations", "Make risks visible.", "Small sample; lower B support; no external validation", "Limitations table", "This builds trust."),
        ("Next steps", "Give a practical roadmap.", "Manual review; inspect errors; temporal split; expand scope", "Next steps table", "Sequence matters."),
        ("Closing", "Summarize value.", "Auditable offline pipeline and candidate report pack", "Final summary", "Close with what is ready now."),
    ]
    sections = ["# Presentation Outline -- CS2 Tactical Analytics MVP", ""]
    for index, (title, objective, bullets, figure, note) in enumerate(slides, start=1):
        sections.extend(
            [
                f"## Slide {index} -- {title}",
                f"- title: {title}",
                f"- objective: {objective}",
                f"- bullet points: {bullets}",
                f"- suggested table/figure: {figure}",
                f"- speaker note: {note}",
                "",
            ]
        )
    return "\n".join(sections)


def markdown_table(frame: pd.DataFrame, columns: list[str], *, top_n: int = 20) -> str:
    if frame.empty:
        return "_No rows available._"
    available = [column for column in columns if column in frame.columns]
    return frame[available].head(top_n).to_markdown(index=False)


def write_outputs(frames: dict[str, pd.DataFrame], output_dir: Path, *, force: bool) -> dict[str, Path]:
    ensure_dir(output_dir)
    outputs: dict[str, Path] = {}
    for name in OUTPUT_NAMES:
        for suffix in ["csv", "parquet"]:
            path = output_dir / f"{name}.{suffix}"
            if force or not path.exists():
                if suffix == "csv":
                    frames[name].to_csv(path, index=False)
                else:
                    frames[name].to_parquet(path, index=False)
            outputs[f"{name}_{suffix}"] = path
    return outputs


def write_text(content: str, path: Path, *, force: bool) -> Path:
    ensure_dir(path.parent)
    if force or not path.exists():
        path.write_text(content, encoding="utf-8")
    return path


def build_notebook_json() -> str:
    cells = [
        markdown_cell("# Stage 7 -- Final MVP Report Pack\n\nInspect the consolidated final MVP report outputs."),
        code_cell(
            "from pathlib import Path\n\n"
            "import matplotlib.pyplot as plt\n"
            "import pandas as pd\n\n"
            "BASE = Path('../data/gold/reporting/final_mvp')\n"
            "CANDIDATE_BASE = Path('../data/gold/modeling/t_side_ab_candidate')\n\n"
            "def load_table(name):\n"
            "    return pd.read_parquet(BASE / f'{name}.parquet')\n\n"
            "project_summary = load_table('final_project_summary')\n"
            "dataset_snapshot = load_table('final_dataset_snapshot')\n"
            "stage_status = load_table('final_pipeline_stage_status')\n"
            "tactical_findings = load_table('final_tactical_findings_summary')\n"
            "candidate_summary = load_table('final_model_candidate_summary')\n"
            "model_error_summary = load_table('final_model_error_summary')\n"
            "limitations = load_table('final_limitations')\n"
            "next_steps = load_table('final_next_steps')\n"
            "artifact_manifest = load_table('final_artifact_manifest')\n"
            "report_audit = load_table('final_report_audit')\n"
            "confusion = pd.read_parquet(CANDIDATE_BASE / 'candidate_model_confusion_matrix.parquet')"
        ),
        markdown_cell("## Project Summary"),
        code_cell("display(project_summary)"),
        markdown_cell("## Dataset Snapshot"),
        code_cell("display(dataset_snapshot)"),
        markdown_cell("## Stage Status"),
        code_cell("display(stage_status)"),
        markdown_cell("## Tactical Findings"),
        code_cell("display(tactical_findings.head(12))"),
        markdown_cell("## Candidate Summary"),
        code_cell("display(candidate_summary)"),
        markdown_cell("## Confusion Matrix"),
        code_cell(
            "matrix = confusion.pivot(index='true_label', columns='predicted_label', values='count').fillna(0)\n"
            "display(matrix)\n"
            "ax = matrix.plot(kind='bar', figsize=(6, 4), rot=0)\n"
            "ax.set_title('Candidate confusion matrix')\n"
            "ax.set_xlabel('True label')\n"
            "ax.set_ylabel('Rounds')\n"
            "plt.tight_layout()"
        ),
        markdown_cell("## Model Error Summary"),
        code_cell("display(model_error_summary)"),
        markdown_cell("## Limitations"),
        code_cell("display(limitations)"),
        markdown_cell("## Next Steps"),
        code_cell("display(next_steps)\ndisplay(artifact_manifest)\ndisplay(report_audit)"),
        markdown_cell("Final MVP report package generated"),
    ]
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.11",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=1) + "\n"


def markdown_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def code_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Final MVP Report Pack summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


def parse_bool(value: str) -> bool:
    return value.strip().casefold() not in {"0", "false", "no", "n"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the final MVP report pack from existing project outputs.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--target-team", default=None)
    parser.add_argument("--target-map", default=None)
    parser.add_argument("--report-version", default=DEFAULT_REPORT_VERSION)
    parser.add_argument("--include-technical-appendix", type=parse_bool, default=True)
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_final_mvp_report(
        args.config,
        force=args.force,
        dry_run=args.dry_run,
        target_team=args.target_team,
        target_map=args.target_map,
        report_version=args.report_version,
        include_technical_appendix=args.include_technical_appendix,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
