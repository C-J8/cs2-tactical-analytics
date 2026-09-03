from __future__ import annotations

from datetime import datetime

from airflow.sdk import Asset, DAG

from dags._common import PROJECT_CONFIG, run_project_module


ANALYSIS_READY = Asset("cs2://gold/inferno-analysis-modeling")


with DAG(
    dag_id="cs2_inferno_analysis_modeling",
    description="Validate, analyze, and run the frozen Inferno exploratory modeling workflow.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    render_template_as_native_obj=True,
    params={
        "target_team": "Vitality",
        "force": False,
    },
    tags=["cs2", "analysis", "modeling", "inferno"],
) as dag:
    quality_gate = run_project_module.override(task_id="inferno_feature_quality_gate")(
        "src.validation.map_feature_quality_gate",
        [
            "--config",
            PROJECT_CONFIG,
            "--target-map",
            "Inferno",
            "--target-team",
            "{{ params.target_team }}",
        ],
        force="{{ params.force }}",
    )

    repair_materialization = run_project_module.override(task_id="repair_feature_materialization")(
        "src.validation.feature_materialization_repair",
        [
            "--config",
            PROJECT_CONFIG,
            "--target-map",
            "Inferno",
            "--target-team",
            "{{ params.target_team }}",
        ],
        force="{{ params.force }}",
    )

    tactical_eda = run_project_module.override(task_id="multi_map_tactical_eda")(
        "src.analysis.multi_map_tactical_eda",
        [
            "--config",
            PROJECT_CONFIG,
            "--target-team",
            "{{ params.target_team }}",
            "--map",
            "Mirage",
            "--map",
            "Inferno",
        ],
        force="{{ params.force }}",
    )

    harden_findings = run_project_module.override(task_id="harden_tactical_findings")(
        "src.analysis.tactical_finding_hardening",
        [
            "--config",
            PROJECT_CONFIG,
            "--target-team",
            "{{ params.target_team }}",
            "--map",
            "Mirage",
            "--map",
            "Inferno",
        ],
        force="{{ params.force }}",
    )

    build_model_dataset = run_project_module.override(task_id="build_inferno_ab_dataset")(
        "src.modeling.build_map_ab_dataset",
        [
            "--config",
            PROJECT_CONFIG,
            "--model-config",
            "configs/modeling/inferno_ab_exploratory.yaml",
            "--target-map",
            "Inferno",
            "--target-team",
            "{{ params.target_team }}",
        ],
        force="{{ params.force }}",
    )

    exploratory_baseline = run_project_module.override(task_id="run_inferno_exploratory_baseline")(
        "src.modeling.inferno_ab_exploratory_baseline",
        [
            "--config",
            PROJECT_CONFIG,
            "--model-config",
            "configs/modeling/inferno_ab_exploratory.yaml",
        ],
        force="{{ params.force }}",
    )

    sample_readiness = run_project_module.override(
        task_id="check_inferno_sample_readiness",
        outlets=[ANALYSIS_READY],
    )(
        "src.modeling.inferno_sample_expansion",
        ["--config", PROJECT_CONFIG],
        force="{{ params.force }}",
    )

    (
        quality_gate
        >> repair_materialization
        >> tactical_eda
        >> harden_findings
        >> build_model_dataset
        >> exploratory_baseline
        >> sample_readiness
    )
