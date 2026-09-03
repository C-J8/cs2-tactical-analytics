from __future__ import annotations

from pathlib import Path

from airflow.models import DagBag


EXPECTED_DAGS = {
    "cs2_demo_ingestion",
    "cs2_gold_materialization",
    "cs2_inferno_analysis_modeling",
}


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    dag_bag = DagBag(dag_folder=str(project_root / "dags"))

    if dag_bag.import_errors:
        errors = "\n\n".join(f"{path}\n{error}" for path, error in sorted(dag_bag.import_errors.items()))
        raise SystemExit(f"Airflow DAG import errors:\n{errors}")

    missing = EXPECTED_DAGS.difference(dag_bag.dag_ids)
    if missing:
        raise SystemExit(f"Missing expected DAGs: {', '.join(sorted(missing))}")

    print(f"Loaded {len(EXPECTED_DAGS)} expected DAGs without import errors.")


if __name__ == "__main__":
    main()
