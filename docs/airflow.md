# Airflow orchestration

Airflow is an operational layer around the existing Python pipeline. Business,
feature, validation, and modeling logic stays under `src/`; DAG files only
define dependencies, parameters, retries, and observable execution boundaries.

## Local architecture

The development stack uses Airflow 3.3.1 on Linux containers, PostgreSQL 16 for
metadata, and `LocalExecutor`. The repository is mounted at
`/opt/airflow/project`, so the current local Bronze/Silver/Gold storage contract
is preserved. DAG scheduling remains disabled by default, while ingestion itself
uses a hybrid automatic/manual acquisition contract.

The available DAGs are:

- `cs2_demo_ingestion`: catalog, archive acquisition, archive scan/extraction,
  metadata probe, parsing, and parse-quality gate;
- `cs2_gold_materialization`: the existing scoped map pipeline, including the
  multi-map Gold preservation gate;
- `cs2_inferno_analysis_modeling`: feature quality, materialization repair,
  multi-map EDA, finding hardening, the frozen exploratory baseline, and sample
  readiness.

All DAGs default to `force=false`, allow only one active run, and accept a small
set of explicit runtime parameters. Catalog building discovers HLTV matches by
configured team/date/map when possible and merges them with the manual seed.
Archive acquisition downloads each series once and reuses local files before
opening HTTP connections.

The ingestion ownership chain is deliberately linear:

```text
build_match_catalog
  -> download_archives        # archive acquisition/registration only
  -> scan_local_archives      # the only archive extraction owner
  -> probe_dem_metadata
  -> parse_demos
  -> parse_quality
```

Keeping acquisition and extraction separate prevents the same archive from
creating DEM copies under two directory conventions.

`download_archives` runs with `--require-ready`. If HLTV blocks a selected
archive, the task writes an actionable row to `demo_manifest` and fails before
`scan_local_archives`. The row contains the match page, expected archive stem,
destination directory, and an exact `--match-id ... --archive-path ...` recovery
command. After the file is registered manually, retrying the DAG resumes from
the same canonical pipeline.

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
- Do not enable a time schedule until the HLTV best-effort discovery behavior is
  monitored in practice; security challenges are expected and are never bypassed.
- Use object storage or another shared data platform before moving to remote
  workers, Celery, or Kubernetes.
- Treat Airflow retry as safe only for commands whose scoped writes are
  idempotent. Destructive full resets remain outside the DAGs.
