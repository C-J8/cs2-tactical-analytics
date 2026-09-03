# Airflow orchestration

Airflow is an operational layer around the existing Python pipeline. Business,
feature, validation, and modeling logic stays under `src/`; DAG files only
define dependencies, parameters, retries, and observable execution boundaries.

## Local architecture

The development stack uses Airflow 3.3.1 on Linux containers, PostgreSQL 16 for
metadata, and `LocalExecutor`. The repository is mounted at
`/opt/airflow/project`, so the current local Bronze/Silver/Gold storage contract
is preserved. Runs are deliberately manual because local demos and the manual
match seed remain the project's source of truth.

The available DAGs are:

- `cs2_demo_ingestion`: catalog, archive scan/extraction, metadata probe,
  parsing, and parse-quality gate;
- `cs2_gold_materialization`: the existing scoped map pipeline, including the
  multi-map Gold preservation gate;
- `cs2_inferno_analysis_modeling`: feature quality, materialization repair,
  multi-map EDA, finding hardening, the frozen exploratory baseline, and sample
  readiness.

All DAGs default to `force=false`, allow only one active run, and accept a small
set of explicit runtime parameters. They do not scrape HLTV automatically.

## Start locally

Copy the non-secret example and replace its password placeholder. The init
command fails closed when `AIRFLOW_ADMIN_PASSWORD` is absent, and safely creates
the administrator or synchronizes its password when it already exists:

```bash
cp .env.airflow.example .env.airflow
docker compose -f compose.airflow.yml build
docker compose -f compose.airflow.yml run --rm airflow-init
docker compose -f compose.airflow.yml up -d
```

Open <http://localhost:8080>, enable only the DAG you intend to use, and trigger
it with the desired map/team parameters. The expected order for a new batch is
ingestion, Gold materialization, then analysis/modeling.

Stop services without deleting metadata:

```bash
docker compose -f compose.airflow.yml down
```

Deleting volumes also deletes Airflow metadata and is intentionally not part of
the normal workflow.

## Operational rules

- Never pass dataframes or parsed demo payloads through XCom; tasks exchange
  paths and small status summaries only.
- Keep `max_active_runs=1` while Gold tables are stored on the shared local
  filesystem.
- Do not enable automatic schedules until ingestion has a stable external event
  source and the write paths are safe for concurrent runs.
- Use object storage or another shared data platform before moving to remote
  workers, Celery, or Kubernetes.
- Treat Airflow retry as safe only for commands whose scoped writes are
  idempotent. Destructive full resets remain outside the DAGs.
