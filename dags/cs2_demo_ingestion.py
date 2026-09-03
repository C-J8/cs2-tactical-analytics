from __future__ import annotations

from datetime import datetime

from airflow.sdk import Asset, DAG

from dags._common import PROJECT_CONFIG, run_project_module


PARSE_QUALITY_READY = Asset("cs2://silver/parse-quality")


with DAG(
    dag_id="cs2_demo_ingestion",
    description="Catalog, extract, probe, parse, and validate locally supplied CS2 demos.",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    render_template_as_native_obj=True,
    params={
        "target_map": "Inferno",
        "target_team": "Vitality",
        "force": False,
    },
    tags=["cs2", "ingestion", "offline-first"],
) as dag:
    build_catalog = run_project_module.override(task_id="build_match_catalog")(
        "src.ingestion.build_match_catalog",
        ["--config", PROJECT_CONFIG],
    )

    scan_archives = run_project_module.override(task_id="scan_local_archives")(
        "src.ingestion.scan_local_archives",
        [
            "--config",
            PROJECT_CONFIG,
            "--extract",
            "--target-team",
            "{{ params.target_team }}",
        ],
        force="{{ params.force }}",
    )

    probe_metadata = run_project_module.override(task_id="probe_dem_metadata")(
        "src.parsing.probe_dem_metadata",
        ["--config", PROJECT_CONFIG],
        force="{{ params.force }}",
    )

    parse_demos = run_project_module.override(task_id="parse_demos")(
        "src.parsing.parse_demos",
        [
            "--config",
            PROJECT_CONFIG,
            "--target-map",
            "{{ params.target_map }}",
            "--target-team",
            "{{ params.target_team }}",
        ],
        force="{{ params.force }}",
    )

    parse_quality = run_project_module.override(
        task_id="parse_quality",
        outlets=[PARSE_QUALITY_READY],
    )(
        "src.parsing.parse_quality",
        [
            "--config",
            PROJECT_CONFIG,
            "--target-map",
            "{{ params.target_map }}",
            "--target-team",
            "{{ params.target_team }}",
        ],
        force="{{ params.force }}",
    )

    build_catalog >> scan_archives >> probe_metadata >> parse_demos >> parse_quality
