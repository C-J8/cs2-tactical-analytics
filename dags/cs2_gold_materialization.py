from __future__ import annotations

from datetime import datetime

from airflow.sdk import Asset, DAG

from dags._common import PROJECT_CONFIG, run_project_module


GOLD_READY = Asset("cs2://gold/scoped-map-features")


with DAG(
    dag_id="cs2_gold_materialization",
    description="Build scoped round features, round state, side datasets, and the multi-map Gold gate.",
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
    tags=["cs2", "features", "gold"],
) as dag:
    materialize_gold = run_project_module.override(
        task_id="run_scoped_map_pipeline",
        outlets=[GOLD_READY],
    )(
        "src.features.run_map_pipeline",
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
