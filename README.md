# cs2-tactical-analytics

Offline-first CS2 tactical analytics pipeline currently implemented through **Stage 8.8 -- Inferno Feature Pipeline Run & Multi-Map Gold Storage**.

Project direction:

```text
HLTV -> demos .dem -> CS2 parser -> analytical tables -> round features -> ML model -> dashboard
```

The repository currently covers catalog ingestion, local demo intake/extraction, metadata probing, Awpy parsing, parse-quality gates, full-round feature engineering, round-state resolution, side-specific datasets, auditable T-side tactical EDA, ranked findings, a concrete round-level manual-review pack, a leakage-controlled A/B baseline, baseline error interpretation, a focused feature-refinement experiment, candidate promotion, final MVP reporting, feature-contract freezing, a versioned Mirage map/region registry, a map-ready feature-engineering refactor, a formal Mirage regression gate, conservative Inferno onboarding, canonical map identity, scoped multi-map parsing, a safe multi-map parse gate, generic area discovery from real parser `place` + X/Y/Z evidence, audited Inferno physical/semantic region mapping, and scoped Inferno feature materialization into consolidated Mirage + Inferno Gold tables. Model deployment, dashboards, BigQuery, and Streamlit are not implemented yet.

## Current Status

Validated local snapshot for Vitality on Mirage + Inferno:

- 18 feature-eligible demos;
- 527 parsed rounds in consolidated `round_features_mvp`: 405 Mirage and 122 Inferno;
- 180 resolved T-side rounds;
- 225 resolved CT-side rounds;
- 98 high-confidence planted T-side rounds: 72 plant A and 26 plant B;
- 82 T-side rounds without a valid Vitality plant;
- interval and cumulative feature windows through 115 seconds;
- 11 Stage 5 analytical tables generated in CSV and Parquet;
- 10 Stage 5.1 findings tables plus a generated Markdown report;
- 75 ranked tactical candidates and 12 manual-review items;
- 20 Stage 5.2 findings covered by 151 selected finding-round pairs;
- 18 Stage 6 horizon/model evaluations with out-of-fold predictions;
- 120 Stage 6.1 selected-model errors analyzed across six horizons;
- 30 Stage 6.2 controlled horizon/feature-set/model experiments;
- 1 Stage 6.3 candidate baseline package promoted from Stage 6.2;
- 1 Stage 7 final report pack with report, appendix, presentation outline, and audit tables;
- 1 Stage 8.0 frozen feature contract with 492 current MVP features;
- 1 Stage 8.1 Mirage map registry with 15 physical regions and 8 semantic groups;
- 1 Stage 8.2 map-ready feature audit with 1511 compatibility checks passing;
- 1 Stage 8.3 Mirage regression gate with 16 datasets and 14 critical invariants passing;
- 1 Stage 8.4 Inferno onboarding package registering 5 local Inferno demos for Vitality;
- 1 Stage 8.5 multi-map parsing gate showing 5 parsed Inferno demos, 5 feature-eligible Inferno demos, Mirage preservation, and `ready_for_area_discovery = true`;
- 1 Stage 8.6 area discovery package with 23 Mirage places, 24 Inferno places, real coordinate/coverage/stability profiles, Mirage crosswalk coverage of 100% of observed ticks, and Inferno `ready_for_region_mapping = true`;
- 1 Stage 8.7 Inferno region-mapping package with 24 mapped raw places, 21 active physical regions, 4 frozen map-abstract semantics resolved, 31 candidate features audited for portability, and Mirage regression green after Feature Contract v2 metadata;
- 1 Stage 8.8 Inferno feature pipeline run with 122 Inferno rounds, 65 Inferno T-side rounds, 57 Inferno CT-side rounds, 40 high-confidence Inferno planted T-side rounds, a passing multi-map Gold gate, and `ready_for_inferno_feature_quality_gate = true`;
- 217 tests passing and `ruff check .` passing.

The Git repository intentionally excludes downloaded demos and generated Bronze/Silver/Gold datasets. Only code, configs, tests, notebooks, documentation, and the manual match seed are versioned.

## Official Pipeline Order

After local archives/demos are available, rebuild the current pipeline in this order:

```bash
python -m src.ingestion.build_match_catalog --config configs/project.yaml
python -m src.ingestion.scan_local_archives --config configs/project.yaml --extract --force
python -m src.parsing.probe_dem_metadata --config configs/project.yaml --force
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
python -m src.features.build_feature_contract --config configs/project.yaml --force
python -m src.maps.build_map_registry --config configs/project.yaml --force
python -m src.validation.mirage_regression_gate --config configs/project.yaml --force
python -m src.maps.onboard_map --config configs/project.yaml --map Inferno --target-team Vitality --force
python -m src.parsing.parse_demos --config configs/project.yaml --target-map Inferno --target-team Vitality --force
python -m src.parsing.parse_quality --config configs/project.yaml --target-map Inferno --target-team Vitality --force
python -m src.validation.multi_map_parse_gate --config configs/project.yaml --target-map Inferno --target-team Vitality --force
python -m src.maps.discover_map_areas --config configs/project.yaml --map Mirage --target-team Vitality --force
python -m src.maps.discover_map_areas --config configs/project.yaml --map Inferno --target-team Vitality --force
python -m src.maps.build_region_mapping --config configs/project.yaml --map Inferno --target-team Vitality --force
python -m src.features.run_map_pipeline --config configs/project.yaml --target-map Inferno --target-team Vitality --force
python -m src.validation.multi_map_gold_gate --config configs/project.yaml --target-map Inferno --target-team Vitality --force
```

Important dependency rules:

- rerunning `parse_demos --force` requires rebuilding parse quality and every downstream Gold stage;
- rerunning `build_round_features --force` requires rebuilding `round_state`, `side_datasets`, and Stage 5;
- `side_datasets` refuses to run without `round_state_resolved` so it cannot silently fall back to the old side proxy;
- Stage 5 reads corrected Gold tables only and does not use `round_features_mvp` for final T-side decisions.
- Stage 5.1 reads Stage 5 aggregates first and ranks conservative findings for manual review.
- Stage 5.2 links Stage 5.1 findings to concrete T-side rounds and must be rebuilt whenever Stage 5.1 changes.
- Stage 6 trains only on high-confidence planted T-side rounds and must be rebuilt whenever features, round state, or manual decisions change.
- Stage 6.1 reads Stage 6 outputs only; it interprets errors and never trains a new model.
- Stage 6.2 reuses Stage 6 leakage controls and compares fixed feature sets against the matching Stage 6 baseline.
- Stage 6.3 reads Stage 6.2 outputs only; it promotes and documents a candidate without training new models.
- Stage 7 reads prior outputs only; it consolidates the final MVP report pack and does not alter upstream data.
- Stage 8.0 reads existing feature/catalog/model metadata only; it freezes feature classifications and does not recalculate feature values.
- Stage 8.1 reads the frozen feature contract and current Mirage region mapping only; it writes map registry metadata and does not recalculate feature values.
- Stage 8.2 makes Stage 4 feature engineering consume the map registry and feature contract; it keeps Mirage feature names/values stable and writes compatibility audits.
- Stage 8.3 compares the current Mirage MVP against an explicit frozen baseline and blocks new-map onboarding on any critical regression.
- Stage 8.4 registers Inferno and writes onboarding/readiness audits under `data/gold/maps/inferno/onboarding/`; it does not train models, scrape HLTV, or overwrite Mirage feature outputs.
- Stage 8.5 resolves map names through canonical identity, parses explicit map/team scopes safely, preserves other maps during forced upserts, and validates readiness for future area discovery. It does not discover Inferno areas, edit Inferno semantic mappings, run Inferno feature engineering, train models, or build dashboards.
- Stage 8.6 discovers raw parser places and coordinate evidence for parsed maps. It does not update Mirage or Inferno registry YAML files, infer tactical semantic groups, run feature engineering, train models, or alter Stage 6 outputs.
- Stage 8.7 maps Inferno raw parser places into verified physical regions and tactical semantic groups, updates Inferno registry status to active, and adds Feature Contract v2 comparability metadata. It does not run Inferno feature engineering, round state, T-side datasets, ML, dashboards, or BigQuery.
- Stage 8.8 runs the scoped Inferno feature pipeline and writes consolidated multi-map Gold tables while preserving Mirage rows. It does not run EDA, train models, apply Mirage models to Inferno, build dashboards, or export to BigQuery.

## MVP Scope

- Initial team: Vitality
- Initial map: Mirage
- Configurable date window
- Professional matches discovered through HLTV metadata
- Offline-first manual mode with an optional conservative scrape mode

HLTV has no official public API. Scraping can be blocked or throttled, so `manual` mode is the source of truth for this stage and must keep working without internet access.

## Setup

Use Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configs

Edit these files to expand the catalog without changing code:

- `configs/project.yaml`: mode, date window, target maps, target teams, output formats, cache/rate limit.
- `configs/teams.yaml`: canonical team names, HLTV ids, aliases.
- `configs/maps.yaml`: canonical map names and aliases.
- `configs/maps/map_registry.yaml`: global index of versioned map-region registry configs.
- `configs/maps/mirage.yaml`: Mirage reference registry for physical regions, semantic groups, aliases, and bombsites.
- `configs/player_rosters.yaml`: player nicknames by team for side and plant ownership resolution.

Adding a new team only requires adding it to `configs/teams.yaml` and listing it in `target_teams`. Adding a production-ready map now also requires a map-registry config with physical regions, semantic groups, aliases, and bombsites before feature engineering is refactored to consume it.

When a demo does not expose reliable team columns, the pipeline can still infer side ownership from player names in ticks. Keep `configs/player_rosters.yaml` updated with the active/historical nicknames observed in the demos. This is especially useful when `opponent = unknown` in catalog metadata but the demo still contains recognizable player names.

## Manual Input

Fill `data/raw/manual/matches_seed.csv` with one row per match/map.

Expected columns:

```text
hltv_match_id,match_url,match_date,event_name,team_1,team_2,map_name,map_number,demo_link
```

`match_url` or `hltv_match_id` must exist. Other fields can be empty; incomplete rows are kept in the catalog with `validation_status = warning` and an explanation in `validation_notes`.

## Run

```bash
python -m src.ingestion.build_match_catalog --config configs/project.yaml
```

The command:

1. Loads project, team, and map configs.
2. Loads the manual CSV.
3. Optionally enriches rows from cached/fetched HLTV pages when `mode: scrape`.
4. Standardizes aliases and validates records.
5. Writes CSV and Parquet outputs.
6. Prints a terminal summary.

## Modes

`manual`: reads only `data/raw/manual/matches_seed.csv`, never accesses HLTV, and writes the final catalog.

`scrape`: starts from the manual CSV, attempts to fetch or reuse cached HLTV pages in `data/raw/hltv_pages/`, respects `rate_limit_seconds`, and fills missing metadata when possible. If scraping fails, manual data is preserved and warnings are emitted.

In `scrape` mode, `source_method` is assigned per row. Rows only become `manual+scrape` when the cached/fetched HTML actually fills a catalog field; rows that cannot be enriched remain `manual`.

## Outputs

Final catalog:

- `data/silver/matches_catalog/matches_catalog.csv`
- `data/silver/matches_catalog/matches_catalog.parquet`

Raw manual snapshot:

- `data/bronze/match_catalog_raw/match_catalog_raw.csv`

Final schema:

```text
series_id, hltv_match_id, match_url, match_date, event_name, team_1, team_2,
target_team, opponent, map_name, map_number, demo_link, source_method,
source_html_path, scraped_at, validation_status, validation_notes
```

## Validate

Run tests:

```bash
pytest
```

Open `notebooks/01_validate_match_catalog.ipynb` to inspect the generated Parquet catalog, counts by map/opponent, warnings, and date range.

## Stage 2

Stage 2 adds demo download orchestration, archive extraction, and a reproducible manifest. It still does not parse demos, build features, train models, or create dashboards.

### Stage 2 -- Demo Download

Input:

- Primary: `data/silver/matches_catalog/matches_catalog.parquet`
- Fallback: `data/silver/matches_catalog/matches_catalog.csv`

By default, only catalog rows with `validation_status = ok` are eligible. Use `--include-warnings` when you want to include warning rows too.

Dry-run, fully offline:

```bash
python -m src.ingestion.download_demos --config configs/project.yaml --dry-run
```

Real download:

```bash
python -m src.ingestion.download_demos --config configs/project.yaml --limit 3
```

Useful options:

```bash
python -m src.ingestion.download_demos --config configs/project.yaml --include-warnings --force
python -m src.ingestion.download_demos --config configs/project.yaml --no-extract
python -m src.ingestion.download_demos --config configs/project.yaml --catalog path/to/matches_catalog.parquet
python -m src.ingestion.download_demos --config configs/project.yaml --local-only
python -m src.ingestion.download_demos --config configs/project.yaml --archive-path path/to/downloaded-demo.rar --limit 1
```

Downloaded archives are saved under:

```text
data/raw/demo_archives/<target_team>/<map_name>/
```

Extracted `.dem` files are saved under:

```text
data/raw/demos/<target_team>/<map_name>/
```

The manifest is written to:

- `data/bronze/demo_manifest/demo_manifest.csv`
- `data/bronze/demo_manifest/demo_manifest.parquet`

The manifest records one row per downloaded/extracted demo record. If an archive contains multiple `.dem` files, each `.dem` gets its own row. Failed or missing demos are kept in the manifest with status and error details instead of stopping the whole run.

Key statuses:

- `download_status`: `downloaded`, `skipped_existing`, `failed`, `blocked_remote`, `local_existing`, `local_registered`, `missing_local_archive`, `missing_demo_link`, `dry_run`
- `extract_status`: `extracted`, `skipped_existing`, `failed`, `not_needed`, `unsupported_archive`, `dry_run`
- `status`: `ok`, `warning`, `failed`

`blocked_remote` means the remote host refused the download, commonly with HTTP 403 or 429. The pipeline records it as `status = warning` because the code and local network path worked, but the host declined access.

When HLTV blocks automatic download:

1. Run the normal command first and inspect the manifest.
2. If `download_status = blocked_remote`, download the demo manually in a browser.
3. Put the file in `data/raw/demo_archives/<target_team>/<map_name>/` using the expected base name, such as `hltv_2389666_mirage_map1.rar`.
4. Run:

```bash
python -m src.ingestion.download_demos --config configs/project.yaml --local-only --limit 1
```

`--local-only` never makes HTTP requests. It looks for the expected base name in this extension order: `.dem`, `.zip`, `.rar`, `.download`.

Alternatively, register a browser-downloaded file from any path:

```bash
python -m src.ingestion.download_demos --config configs/project.yaml --archive-path path/to/browser-download.rar --limit 1
```

This copies the file into the standard archive directory without overwriting unless `--force` is set, calculates size/hash, and then extracts when extraction is enabled.

RAR extraction is optional. The pipeline first looks for `7z`/`7za`; if neither exists, the archive remains saved and the manifest records `unsupported_archive` with a clear message. Demo parsing is reserved for Stage 3.

On Windows, install 7-Zip and add its install directory to `PATH` when `.rar` extraction reports `RAR extraction requires 7z/7za on PATH`. You can also extract the archive manually and place `.dem` files under `data/raw/demos/<target_team>/<map_name>/`.

## Stage 3

Stage 3 parses extracted `.dem` files into bronze per-demo tables and silver consolidated tables. It uses Awpy as the parser backend and does not implement feature engineering, ML, BigQuery, or dashboards.

### Bulk Local Archive Intake

When HLTV blocks automatic downloads, manually downloaded `.rar`, `.zip`, or `.dem` files can be scanned in bulk.

Default input for the current MVP:

```text
data/raw/demo_archives/Vitality/Mirage/
```

Dry-run scan:

```bash
python -m src.ingestion.scan_local_archives --config configs/project.yaml --dry-run
```

Scan and extract:

```bash
python -m src.ingestion.scan_local_archives --config configs/project.yaml --extract
```

Useful options:

```bash
python -m src.ingestion.scan_local_archives --config configs/project.yaml --input-dir path/to/archives
python -m src.ingestion.scan_local_archives --config configs/project.yaml --target-team Vitality --assumed-map Mirage
python -m src.ingestion.scan_local_archives --config configs/project.yaml --extract --limit 3
python -m src.ingestion.scan_local_archives --config configs/project.yaml --extract --force
```

The scanner writes:

- `data/bronze/local_archive_manifest/local_archive_manifest.csv`
- `data/bronze/local_archive_manifest/local_archive_manifest.parquet`
- `data/bronze/dem_files_manifest/dem_files_manifest.csv`
- `data/bronze/dem_files_manifest/dem_files_manifest.parquet`

Each local archive extracts into its own directory:

```text
data/raw/demos/<target_team>/<local_archive_id>/
```

This avoids mixing `.dem` files from different series. The scanner infers simple metadata from filenames when possible, including event name, teams, BO format, and map name. Unknown values are kept as `unknown` with notes instead of breaking the pipeline.

Some HLTV archives contain one map split across multiple files, commonly named like `m1-mirage-p1.dem` and `m1-mirage-p2.dem`. The scanner keeps those original split segments in `dem_files_manifest`, marks them with `is_split_segment = true`, and sets `parse_eligible = false` so they are not parsed as separate maps. When it finds two or more parts for the same map group, it also writes a combined candidate ending in `_merged.dem`, marks it with `is_merged_demo = true`, and makes that merged row eligible for parsing. This preserves the raw evidence and avoids inflating the Mirage count with half-map files.

`parse_demos` prefers `dem_files_manifest` when it exists. By default, it parses only rows whose `inferred_map_name` is in `target_maps`; rows with `unknown` map are skipped unless explicitly allowed:

```bash
python -m src.parsing.parse_demos --config configs/project.yaml --allow-unknown-map --limit 1
python -m src.parsing.parse_demos --config configs/project.yaml --assume-map Mirage --limit 1
```

### Stage 3.5 -- DEM Metadata Probe

A BO3/BO5 archive usually extracts multiple `.dem` files, one per map. A series may include Mirage, but not every extracted `.dem` is Mirage. Before parsing in bulk, run a lightweight metadata probe to identify each demo's map.

The probe reads `data/bronze/dem_files_manifest/dem_files_manifest.parquet`, checks unknown map rows by default, and updates:

- `inferred_map_name`
- `inference_method`
- `parse_probe_status`
- `previous_inferred_map_name`
- `probe_error_message`
- `probed_at`

Run:

```bash
python -m src.parsing.probe_dem_metadata --config configs/project.yaml
```

Useful options:

```bash
python -m src.parsing.probe_dem_metadata --config configs/project.yaml --dry-run
python -m src.parsing.probe_dem_metadata --config configs/project.yaml --include-known --force
python -m src.parsing.probe_dem_metadata --config configs/project.yaml --limit 10
```

Inference order:

1. `.dem` file name
2. archive file name
3. lightweight parser header probe via demoparser2/Awpy backend
4. fallback `unknown`

The probe does not full-parse ticks or generate analytical tables. It only reads lightweight header metadata when available. After probing, validate:

```bash
python -c "import pandas as pd; print(pd.read_parquet('data/bronze/dem_files_manifest/dem_files_manifest.parquet')['inferred_map_name'].value_counts(dropna=False))"
```

Then parse only target maps:

```bash
python -m src.parsing.parse_demos --config configs/project.yaml --limit 1 --force
```

### Stage 3 -- Demo Parsing

Make sure at least one `.dem` exists in the demo manifest. If HLTV blocked remote download, use the local/offline flow first:

```bash
python -m src.ingestion.download_demos --config configs/project.yaml --local-only --limit 1
```

Dry-run parsing:

```bash
python -m src.parsing.parse_demos --config configs/project.yaml --dry-run --limit 1
```

Controlled real parsing for one eligible Mirage demo:

```bash
python -m src.parsing.parse_demos --config configs/project.yaml --limit 1 --force
```

If the one-demo parse succeeds, parse all eligible target-map demos:

```bash
python -m src.parsing.parse_demos --config configs/project.yaml --force
```

Optional flags:

```bash
python -m src.parsing.parse_demos --config configs/project.yaml --include-warnings
python -m src.parsing.parse_demos --config configs/project.yaml --force
python -m src.parsing.parse_demos --config configs/project.yaml --manifest path/to/demo_manifest.parquet
```

With `--force`, consolidated silver Parquets in `data/silver/parsed_demos/` are rebuilt from scratch for the selected run. This avoids mixing stale parse output with newly parsed demos.

Outputs:

- Bronze parsed tables per demo: `data/bronze/parsed_demos/<target_team>/<map_name>/<series_id>/`
- Silver consolidated tables: `data/silver/parsed_demos/`
- Parse manifest: `data/bronze/parse_manifest/parse_manifest.csv` and `.parquet`
- Parse audit: `data/bronze/parse_audit/parse_audit.csv` and `.parquet`

Expected tables include `rounds`, `kills`, `damages`, `shots`, `bomb`, `smokes`, `infernos`, `grenades`, `footsteps`, and `ticks` when Awpy exposes them. Silver tables include trace columns such as `series_id`, `hltv_match_id`, `map_name`, `map_number`, `target_team`, `opponent`, `dem_path`, and `source_parse_id`.

Interpret `parse_manifest` as the per-demo control ledger:

- `parsed`: the demo was parsed and contributed rows to silver tables.
- `map_not_target`: the demo exists, but its map is outside `target_maps`.
- `map_unknown`: the map is unknown and was skipped by default.
- `split_segment_merged`: this is a preserved split segment and is not parsed as a standalone map.
- `failed` or `missing_dem`: the row needs investigation before using it downstream.

Interpret `parse_audit` as the per-table silver summary. It records row count, column count, column names, trace-column presence, and useful spatial columns such as `tick`, `X`, `Y`, and `Z`.

Quick validation:

```bash
python -c "import pandas as pd; df=pd.read_parquet('data/bronze/parse_manifest/parse_manifest.parquet'); print(df['parse_status'].value_counts(dropna=False)); print(df.groupby(['map_name','parse_status'])[['rows_rounds','rows_ticks']].agg(['count','sum']))"
python -c "import pandas as pd; print(pd.read_parquet('data/bronze/parse_audit/parse_audit.parquet')[['table_name','row_count','column_count','has_series_id','has_map_name','has_target_team','has_opponent','has_tick','has_X','has_Y','has_Z']])"
python -c "from pathlib import Path; p=Path('data/silver/parsed_demos'); print('\n'.join(f'{x.name}: {x.stat().st_size/1024/1024:.2f} MB' for x in p.glob('*.parquet')))"
```

### Stage 3.6 -- Parse Quality Gate

Some HLTV archives contain split demos, and `_merged.dem` files can be partially parseable even when the binary concatenation does not fully reconstruct the original map. The pipeline does not delete those files or rewrite the original `parse_manifest`; instead, it writes a separate quality gate for downstream stages.

Run:

```bash
python -m src.parsing.parse_quality --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.parsing.parse_quality --config configs/project.yaml --min-rounds 12
python -m src.parsing.parse_quality --config configs/project.yaml --dry-run
python -m src.parsing.parse_quality --config configs/project.yaml --parse-manifest data/bronze/parse_manifest/parse_manifest.parquet
```

Outputs:

- `data/bronze/parse_quality/parse_quality.csv`
- `data/bronze/parse_quality/parse_quality.parquet`
- `data/silver/parsed_demos/feature_eligible_demos.csv`
- `data/silver/parsed_demos/feature_eligible_demos.parquet`

Quality statuses:

- `valid_full_map`: parsed target-map demo with enough rounds and ticks.
- `suspicious_short_demo`: parsed demo below `--min-rounds`; keep it for audit, but do not use it for features.
- `missing_rounds`: parsed row has no round rows.
- `missing_ticks`: parsed row has no tick rows.
- `map_not_target`: extracted demo belongs to a non-target map.
- `split_segment_not_used`: preserved split segment excluded from feature inputs.
- `parse_failed`: parse did not produce a usable parsed demo.
- `unknown`: fallback status for unexpected cases.

The next feature-engineering stage should consume `feature_eligible_demos`, not all parsed demos. This keeps raw evidence, split segments, and suspicious parses available for inspection while preventing low-quality demos from entering model inputs.

Validation notebook:

```text
notebooks/02_validate_parsed_demo.ipynb
```

Current limitations:

- Only the Awpy backend is implemented.
- No features are generated yet.
- No model or dashboard exists yet.
- If `.rar` extraction fails, install 7-Zip or extract manually before running real parsing.

Project validation:

```bash
python -m pytest
python -m ruff check .
```

Feature engineering, ML, BigQuery export, and dashboards are intentionally not implemented in this stage.

## Stage 4 -- Feature Engineering MVP

Stage 4 creates the first round-level feature dataset for analysis/modeling experiments. It still does not train a model, export to BigQuery, or build a dashboard.

Official input:

```text
data/silver/parsed_demos/feature_eligible_demos.parquet
```

Run:

```bash
python -m src.features.build_round_features --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.features.build_round_features --config configs/project.yaml --limit-demos 3 --force
python -m src.features.build_round_features --config configs/project.yaml --dry-run
```

Outputs:

- `data/gold/round_features/round_features_mvp.csv`
- `data/gold/round_features/round_features_mvp.parquet`
- `data/gold/round_features/round_base.parquet`
- `data/gold/round_features/player_round_utility.parquet`
- `data/gold/utility_events/utility_events.parquet`
- `data/gold/region_presence/region_presence_by_round.parquet`
- `data/gold/feature_audit/feature_audit.csv`
- `data/gold/feature_audit/feature_audit.parquet`

The MVP includes:

- round context and trace columns;
- A/B target-site label when a plant site is observed;
- interval and cumulative temporal windows from freeze end through the full 115-second regulation round;
- Mirage place-name mapping into tactical region groups;
- initial utility loadout from `ticks.inventory`;
- smoke/molotov utility events from `smokes.parquet` and `infernos.parquet`;
- position, region-presence, bomb-carrier, and utility aggregates across early, mid, and late round windows;
- feature audit with warnings, null-column counts, and utility/region status.

Temporal windows are configured in `configs/project.yaml`:

```yaml
feature_windows:
  round_duration_seconds: 115
  interval_windows:
    - [0, 15]
    - [15, 25]
    - [25, 35]
    - [35, 45]
    - [45, 55]
    - [55, 65]
    - [65, 75]
    - [75, 85]
    - [85, 95]
    - [95, 105]
    - [105, 115]
  cumulative_windows:
    - [0, 15]
    - [0, 25]
    - [0, 35]
    - [0, 45]
    - [0, 55]
    - [0, 65]
    - [0, 75]
    - [0, 85]
    - [0, 95]
    - [0, 105]
    - [0, 115]
```

The first window is `0-15s` because Mirage often has instant utility, opening duels, ramp/palace pressure, underpass/mid contact, and fast B pressure before the old 20-second cutoff was useful. The remaining windows cover the whole round so late executes, fakes, saves, and desperate final moves are not discarded.

Long tables such as `region_presence_by_round`, `round_region_timeline`, and `bomb_carrier_timeline` include `window_type` to separate `interval` windows from `cumulative` windows. Wide features use column suffixes such as `players_mid_control_0_15`, `time_a_pressure_0_55`, `smokes_used_95_105`, `molotovs_used_0_115`, and `bomb_carrier_region_105_115`.

Position ticks are downsampled to one player observation per second before window aggregation so the full-round feature build remains tractable. Discrete events such as utility throws, kills, bomb drops, and plants still use their event ticks and are filtered by the real `round_end_tick`.

Important limitations:

- `grenades.parquet` is detected as trajectory/tick-level and is not treated as a simple grenade-event table in this MVP.
- Target-site inference for rounds without plant is not implemented; those rounds keep a null model label.
- Silver ticks do not yet contain reliable player-to-team identity. Early position and utility features use T-side players as the attacking-side proxy and record this in `feature_audit`.
- Tickrate is assumed to be 64 ticks per second for temporal-window features.
- ML, model training, BigQuery, and dashboards are still out of scope.

Validation notebook:

```text
notebooks/03_feature_engineering_mvp.ipynb
```

## Stage 4.1 -- Side-Specific Datasets and Round Progression

Stage 4.1 separates tactical questions by side and adds progression context for rounds without a plant. A/B is not treated as a universal round label: it is a strong modeling label only when the attacking side has an observed A/B plant.

Run:

```bash
python -m src.features.round_state --config configs/project.yaml --force
python -m src.features.side_datasets --config configs/project.yaml --force
```

`side_datasets` now requires `data/gold/round_state/round_state_resolved.parquet`. This prevents accidentally rebuilding side datasets from the old T-side proxy.

Outputs:

- `data/gold/round_features/round_features_t_side_all.csv`
- `data/gold/round_features/round_features_t_side_all.parquet`
- `data/gold/round_features/round_features_t_side_planted.csv`
- `data/gold/round_features/round_features_t_side_planted.parquet`
- `data/gold/round_features/round_features_ct_side.csv`
- `data/gold/round_features/round_features_ct_side.parquet`
- `data/gold/round_progression/round_region_timeline.csv`
- `data/gold/round_progression/round_region_timeline.parquet`
- `data/gold/round_progression/death_context_by_round.csv`
- `data/gold/round_progression/death_context_by_round.parquet`
- `data/gold/round_progression/bomb_carrier_timeline.csv`
- `data/gold/round_progression/bomb_carrier_timeline.parquet`
- `data/gold/round_progression/round_outcome_context.csv`
- `data/gold/round_progression/round_outcome_context.parquet`
- `data/gold/feature_audit/side_dataset_audit.csv`
- `data/gold/feature_audit/side_dataset_audit.parquet`

Dataset roles:

- `round_features_t_side_all`: all attacking-side rounds for progression and clustering analysis, including rounds without plant.
- `round_features_t_side_planted`: only attacking-side rounds with observed A/B plant. This is the future A/B modeling dataset.
- `round_features_ct_side`: defensive-side analysis dataset. After Stage 4.2, this uses resolved round state instead of the old attacking-side proxy.

Rounds without plant keep `target_site_model_label = null`. They are analyzed through:

- `round_progression_signature`;
- `round_outcome_type`;
- regional pressure over time;
- first/last death context;
- bomb carrier location when C4 is visible in inventory.

The current progression tables are intentionally explanatory and auditable rather than final model features. ML, model training, BigQuery, and dashboards remain out of scope.

Validation notebook:

```text
notebooks/04_side_datasets_and_progression.ipynb
```

## Stage 4.2 -- Round State Resolution

Stage 4.2 adds an official round-state layer before using side-specific features for modeling. A/B is not a universal label for every round: it is only a reliable target-team label when Vitality is T-side, the bomb was planted, the planting player belongs to Vitality, and the observed site is A or B.

Run:

```bash
python -m src.features.round_state --config configs/project.yaml --force
python -m src.features.side_datasets --config configs/project.yaml --force
```

Outputs:

- `data/gold/round_state/round_state_resolved.csv`
- `data/gold/round_state/round_state_resolved.parquet`
- `data/gold/round_state/round_state_audit.csv`
- `data/gold/round_state/round_state_audit.parquet`

`round_state_resolved` has one row per round and resolves:

- real `target_team_side` and `opponent_side`;
- plant ownership through `planting_team`, `target_team_planted`, and `opponent_planted`;
- conservative `target_site_model_label`;
- `label_confidence`;
- quality notes for unknown side or non-target plants.

Side resolution uses explicit round team columns when available. When parsed rounds do not expose `team_t`/`team_ct`, the current MVP falls back to tick-level player/side evidence for the known Vitality roster.

Player/team evidence comes from:

```text
configs/player_rosters.yaml
```

This file stores team rosters and aliases used to identify which side belongs to which team and who planted the bomb. A player name can appear in more than one roster because rosters change over time; in that case, the resolver uses the side context for that specific round and avoids guessing when the evidence is still ambiguous.

After this stage, side datasets are rebuilt from `round_state_resolved`:

- `round_features_t_side_all`: only rounds where `target_team_side = T`.
- `round_features_t_side_planted`: only T-side rounds with `target_site_model_label in {A, B}` and `label_confidence = high`. This is the future dataset for A/B model experiments.
- `round_features_ct_side`: only rounds where `target_team_side = CT`.

Rounds without plant keep `target_site_model_label = null`. Opponent plants also do not become Vitality A/B labels. T-side and CT-side analysis stay separate because the tactical question and label semantics are different for attack and defense.

Validation notebook:

```text
notebooks/05_round_state_resolution.ipynb
```

## Stage 5 -- T-side Tactical EDA

Stage 5 transforms the corrected Gold tables into an auditable offensive tactical analysis. The current MVP scope is strictly Vitality T-side on Mirage. CT-side tables remain preserved for a future defensive-analysis stage and are not expanded here.

Run:

```bash
python -m src.analysis.t_side_eda --config configs/project.yaml --force
```

Dry-run:

```bash
python -m src.analysis.t_side_eda --config configs/project.yaml --dry-run
```

Official inputs:

- `data/gold/round_features/round_features_t_side_all.parquet`
- `data/gold/round_features/round_features_t_side_planted.parquet`
- `data/gold/round_progression/round_region_timeline.parquet`
- `data/gold/round_progression/death_context_by_round.parquet`
- `data/gold/round_progression/bomb_carrier_timeline.parquet`
- `data/gold/round_progression/round_outcome_context.parquet`
- `data/gold/round_state/round_state_resolved.parquet`
- `data/gold/utility_events/utility_events.parquet` for event-level smoke/molotov summaries

Outputs are written under:

```text
data/gold/analysis/t_side_tactical_eda/
```

Generated in CSV and Parquet:

- `t_side_eda_overview`
- `t_side_site_distribution`
- `t_side_opponent_summary`
- `t_side_window_region_summary`
- `t_side_window_utility_summary`
- `t_side_no_plant_summary`
- `t_side_death_summary`
- `t_side_bomb_carrier_summary`
- `t_side_progression_signature_summary`
- `t_side_feature_catalog`
- `t_side_eda_audit`

The output tables cover:

- overall A/B/no-plant distribution and T-side win rates;
- opponent-level plant and win-rate summaries;
- interval and cumulative region presence through 115 seconds;
- utility by temporal window and tactical region;
- no-plant failure context, first deaths, C4 location/drop context, and progression signatures;
- an auditable feature catalog that marks labels, post-plant fields, final outcomes, and identifiers as unavailable for future modeling.

The analytical `t_round_outcome` is conservative: `plant_A` and `plant_B` require high-confidence target-team labels; rounds without a valid target-team A/B plant become `no_plant`; inconsistent rows remain `unknown`. Opponent plants are never converted into Vitality labels.

Validation notebook:

```text
notebooks/06_t_side_tactical_eda.ipynb
```

Stage 5 does not train a model, build a dashboard, export to BigQuery, or deepen CT-side analysis. It prepares the next step: a baseline A/B model using only `round_features_t_side_planted` and excluding every leakage field identified in `t_side_feature_catalog`.

Validated Stage 5 snapshot:

| Metric | Value |
| --- | ---: |
| T-side rounds | 180 |
| Plant A | 72 |
| Plant B | 26 |
| No plant | 82 |
| Unknown outcome | 0 |
| Plant rate | 54.44% |
| A share when planted | 73.47% |
| B share when planted | 26.53% |
| T-side win rate | 47.22% |

These values describe the current local Gold snapshot and can change when new demos are added or upstream parsing is rebuilt.

## Stage 5.1 -- T-side Tactical Findings

Stage 5 produces organized T-side EDA tables. Stage 5.1 reads those aggregates and turns them into ranked, auditable tactical candidates for manual inspection. It compares plant A vs plant B regions and utility, identifies candidate timing breakpoints, ranks no-plant/C4 patterns, summarizes opponent tendencies and progression signatures, and creates a review queue.

Run:

```bash
python -m src.analysis.t_side_findings --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.analysis.t_side_findings --config configs/project.yaml --dry-run
python -m src.analysis.t_side_findings --config configs/project.yaml --min-rounds 3 --top-n 15 --force
```

Primary inputs are the eleven Parquet outputs from:

```text
data/gold/analysis/t_side_tactical_eda/
```

Outputs are written under:

```text
data/gold/analysis/t_side_tactical_findings/
```

Generated in CSV and Parquet:

- `t_side_key_findings`
- `t_side_ab_region_differences`
- `t_side_ab_utility_differences`
- `t_side_ab_timing_breakpoints`
- `t_side_no_plant_failure_findings`
- `t_side_bomb_carrier_findings`
- `t_side_opponent_tendencies`
- `t_side_progression_findings`
- `t_side_manual_review_queue`
- `t_side_findings_audit`

The command also generates:

```text
docs/t_side_tactical_findings.md
```

The Markdown report is built from the current output tables, including small top-five summaries. Finding text uses conservative language and always keeps round counts/evidence strength available. `min_rounds` suppresses strong labels for sparse evidence, and interval/cumulative windows remain separate.

Validated Stage 5.1 snapshot:

| Metric | Value |
| --- | ---: |
| Ranked key findings | 75 |
| A/B region comparisons | 172 |
| A/B utility comparisons | 135 |
| Timing windows evaluated | 22 |
| Manual-review items | 12 |
| First strong interval signal | 15-25s, utility-led |
| Highest interval signal | 75-85s, region-led |
| Findings audit | ok |

These outputs are exploratory candidates supported by the current sample, not causal conclusions. The manual-review queue keeps the underlying filters and evidence available for validation before any modeling step.

Validation notebook:

```text
notebooks/07_t_side_tactical_findings.ipynb
```

Stage 5.1 does not train a model, make causal claims, build a dashboard, export to BigQuery, or deepen CT-side analysis.

## Stage 5.2 -- T-side Manual Review Pack

Stage 5.1 ranks descriptive tactical findings. Stage 5.2 turns those findings into concrete T-side rounds for qualitative review, preserving the source filter, temporal window, region, evidence metric, and review question. Plant A/B examples require high-confidence labels; no-plant examples remain separate and never receive an inferred site label.

Run:

```bash
python -m src.analysis.t_side_manual_review --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.analysis.t_side_manual_review --config configs/project.yaml --dry-run
python -m src.analysis.t_side_manual_review --config configs/project.yaml --top-n-findings 20 --max-rounds-per-finding 8 --force
python -m src.analysis.t_side_manual_review --config configs/project.yaml --include-weak --force
```

The command writes seven CSV/Parquet tables under:

```text
data/gold/analysis/t_side_manual_review/
```

The outputs contain the selected rounds, finding-to-round map, row-level evidence, queue summary, editable manual-decision template, model-readiness checks, and audit. It also generates:

```text
docs/t_side_manual_review_pack.md
notebooks/08_t_side_manual_review_pack.ipynb
```

Validated Stage 5.2 snapshot:

| Metric | Value |
| --- | ---: |
| Findings selected | 20 |
| Findings with round examples | 20 |
| Selected finding-round pairs | 151 |
| Evidence rows | 151 |
| Output tables | 7 |
| Audit | ok |

The same round may support multiple findings, so 151 represents finding-round review pairs rather than 151 unique matches. The generated decision template starts as `pending` and is intended to record whether each inspected round supports, partially supports, contradicts, or cannot resolve its finding.

Stage 5.2 does not train a model. Pending decisions do not block the preliminary baseline, but they are recorded as a limitation and must be completed before treating the model as more than exploratory.

## Stage 6 -- Leakage-Controlled T-side A/B Baseline Model

Stage 6 trains the first auditable baseline for predicting plant A versus plant B. Its only training source is `round_features_t_side_planted`, filtered to Vitality T-side Mirage rounds with labels A/B and `label_confidence=high`. No-plant rounds remain outside the model.

Run:

```bash
python -m src.modeling.t_side_ab_baseline --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.modeling.t_side_ab_baseline --config configs/project.yaml --dry-run
python -m src.modeling.t_side_ab_baseline --config configs/project.yaml --horizons 15,25,35 --model-set baseline,logistic --force
python -m src.modeling.t_side_ab_baseline --config configs/project.yaml --include-opponent --force
```

The default run evaluates majority baseline, balanced logistic regression, and balanced random forest at 15, 25, 35, 45, 55, and 65 seconds. Metrics and predictions are out-of-fold with stratified cross-validation. Imputation, scaling, and one-hot encoding are fitted inside each training fold.

Leakage controls combine:

- `t_side_feature_catalog.usable_for_future_model`;
- explicit blocking of labels, outcomes, winner, plant, quality, audit, and identifier fields;
- a strict allowlist for context without a temporal suffix;
- inclusion only when a feature window ends at or before the horizon;
- exclusion of rounds planted before the evaluated horizon when plant time is available.

Primary inputs:

```text
data/gold/round_features/round_features_t_side_planted.parquet
data/gold/analysis/t_side_tactical_eda/t_side_feature_catalog.parquet
data/gold/analysis/t_side_manual_review/
```

Eight CSV/Parquet outputs are written under:

```text
data/gold/modeling/t_side_ab_baseline/
```

The outputs cover dataset audit, feature sets, metrics, confusion matrices, out-of-fold predictions, feature importance, horizon comparison, and readiness audit. The stage also generates:

```text
docs/t_side_ab_baseline_report.md
notebooks/09_t_side_ab_baseline_model.ipynb
```

Validated Stage 6 snapshot:

| Metric | Value |
| --- | ---: |
| High-confidence A/B rows | 98 |
| Plant A / Plant B | 72 / 26 |
| Horizons | 6 |
| Models per horizon | 3 |
| Metric rows | 18 |
| Out-of-fold prediction rows | 1,494 |
| Best 15s macro F1 | 0.667, random forest |
| Best 65s macro F1 | 0.762, logistic regression |
| Readiness checks | 10 passing |

This is a baseline, not a final model. Later horizons contain more features but exclude rounds planted before the cutoff, so cohort sizes fall from 98 rounds at 15/25s to 65 rounds at 65s. Scores across horizons therefore are not direct causal comparisons. Manual review is still pending, class B has lower support, and no hyperparameter tuning or external validation has been performed.

## Stage 6.1 -- T-side A/B Baseline Error Analysis and Interpretation

Stage 6.1 analyzes the existing Stage 6 out-of-fold predictions without fitting or tuning any model. It selects the best non-majority model at each horizon by default, measures error confidence and direction, compares A/B behavior, checks opponent concentrations, summarizes feature-importance stability, and creates a practical demo-review queue.

Run:

```bash
python -m src.modeling.t_side_ab_error_analysis --config configs/project.yaml --force
```

Useful focus options:

```bash
python -m src.modeling.t_side_ab_error_analysis --config configs/project.yaml --dry-run
python -m src.modeling.t_side_ab_error_analysis --config configs/project.yaml --focus-model logistic_regression --focus-horizon 55 --force
python -m src.modeling.t_side_ab_error_analysis --config configs/project.yaml --focus-model all --top-n 30 --force
```

The official inputs are the eight Stage 6 tables under:

```text
data/gold/modeling/t_side_ab_baseline/
```

Round features, outcome context, round state, Stage 5.2 review tables, and the feature catalog are optional enrichments. Round state resolves opponents when Stage 6 predictions still contain `unknown`; missing auxiliary inputs produce audit warnings rather than aborting the analysis.

Thirteen CSV/Parquet outputs are written under:

```text
data/gold/modeling/t_side_ab_error_analysis/
```

They cover overview, errors by horizon/model, error rounds, high-confidence errors, opponent and class behavior, prediction types, feature stability, feature/error contrast, horizon recommendations, interpretation summary, manual-review queue, and audit. The stage also generates:

```text
docs/t_side_ab_error_analysis_report.md
notebooks/10_t_side_ab_error_analysis.ipynb
```

Validated Stage 6.1 snapshot using `best_by_horizon`:

| Metric | Value |
| --- | ---: |
| Selected OOF prediction rows | 498 |
| Error rows | 120 |
| B predicted as A | 83 |
| A predicted as B | 37 |
| High-confidence errors | 64 |
| High-confidence B predicted as A | 45 |
| Stable descriptive feature candidates | 15 |
| Feature/error contrast rows | 424 |
| Manual-review queue | 20 rounds |
| Audit | ok |

Every selected model beats the majority baseline in macro F1 at its own horizon, but the error analysis shows that early random-forest models still have weak B recall. The 15s horizon remains useful as the early baseline; 35/45s are candidates for a focused next experiment; 65s is not recommended as the primary horizon because it is later and uses a smaller filtered cohort.

This stage does not establish causal feature effects or production readiness. Plant B remains the lower-support class, no-plant remains outside the model, larger horizons use different cohorts, and manual review is still pending.

## Stage 6.2 -- Focused T-side A/B Feature Refinement Experiment

Stage 6.1 showed that many baseline errors were B predicted as A, including high-confidence mistakes. Stage 6.2 runs a fixed, auditable experiment over five controlled feature sets at 15s, 35s, and 45s. It trains only balanced logistic regression and balanced random forest, then compares every result with the same Stage 6 horizon/model baseline.

Run:

```bash
python -m src.modeling.t_side_ab_refined_experiment --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.modeling.t_side_ab_refined_experiment --config configs/project.yaml --dry-run
python -m src.modeling.t_side_ab_refined_experiment --config configs/project.yaml --horizons 15,35 --model-set logistic --force
python -m src.modeling.t_side_ab_refined_experiment --config configs/project.yaml --feature-sets stable_only,b_focused --force
```

Default feature sets:

- `all_safe`: all Stage 6 leakage-safe and horizon-safe features;
- `stable_only`: stable/model-specific Stage 6.1 candidates, with a baseline-importance fallback;
- `no_preround_context`: removes general pre-round context while retaining initial utility inventory;
- `region_utility_only`: keeps tactical region, position, pressure, and utility signals;
- `b_focused`: existing B-associated, error-contrast, keyword, and utility features.

No-plant remains outside the experiment. Labels must be high-confidence A/B, identifiers never become training features, features cannot end after the horizon, and rounds planted before a horizon are excluded using the same Stage 6 logic. Manual-review exclusions are applied when available; an all-pending review keeps the experiment preliminary.

Ten CSV/Parquet outputs are written under:

```text
data/gold/modeling/t_side_ab_refined_experiment/
```

The outputs include dataset and feature-set audits, metrics, confusion matrices, out-of-fold predictions, importance, B-error summaries, comparison with Stage 6, ranked recommendations, and audit. The stage also generates:

```text
docs/t_side_ab_refined_experiment_report.md
notebooks/11_t_side_ab_refined_experiment.ipynb
```

Validated Stage 6.2 snapshot:

| Metric | Value |
| --- | ---: |
| High-confidence A/B input rows | 98 |
| Horizons / feature sets / models | 3 / 5 / 2 |
| Controlled experiments | 30 |
| Out-of-fold prediction rows | 2,660 |
| Top recommendation | 35s stable_only logistic |
| Top macro F1 | 0.671 |
| Top recall_B | 0.600 |
| Delta macro F1 vs matching baseline | +0.114 |
| Delta recall_B vs matching baseline | +0.160 |
| Delta B predicted as A | -4 |
| Audit | ok |

The 45s `stable_only + logistic` experiment reached a higher raw macro F1 (`0.696`) and the same recall_B (`0.600`), but its recall_B gain over the matching baseline was smaller (`+0.050`). The ranked recommendation therefore keeps 35s first because the experiment's primary objective is improving B behavior, not maximizing one aggregate metric.

Stage 6.2 is not a final model or a tuning sweep. The sample remains small and imbalanced, random round-level folds are not external validation, and manual review remains pending. The next decision is whether to promote one candidate as the next baseline or complete qualitative error review first.

## Stage 6.3 -- T-side A/B Candidate Baseline Promotion and Model Card

Stage 6.3 does not train a new model. It reads the Stage 6.2 experiment outputs, selects one candidate, freezes its configuration, writes auditable candidate tables, and generates presentation-ready documentation.

Run:

```bash
python -m src.modeling.t_side_ab_candidate_promotion --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.modeling.t_side_ab_candidate_promotion --config configs/project.yaml --dry-run
python -m src.modeling.t_side_ab_candidate_promotion --config configs/project.yaml --selection-mode top_recommendation --force
python -m src.modeling.t_side_ab_candidate_promotion --config configs/project.yaml --candidate-horizon 35 --candidate-feature-set stable_only --candidate-model logistic_regression --force
```

The default promoted candidate is:

```text
35s + stable_only + logistic_regression
```

Selection modes:

- `explicit`: uses the requested horizon, feature set, and model;
- `top_recommendation`: uses the first row of `ab_refined_recommendation`;
- `best_macro_f1`: picks the highest macro F1;
- `best_b_recall`: prioritizes recall_B when macro F1 is not worse than baseline;
- `balanced_objective`: combines macro F1, recall_B, and reduced B-predicted-as-A errors.

Ten CSV/Parquet outputs are written under:

```text
data/gold/modeling/t_side_ab_candidate/
```

The outputs cover selection, metrics, confusion matrix, out-of-fold predictions, error queue, feature set, feature importance, comparison versus Stage 6 baseline, final decision, and audit. The stage also generates:

```text
docs/t_side_ab_candidate_model_card.md
docs/t_side_ab_candidate_baseline_report.md
configs/modeling/t_side_ab_candidate_baseline.yaml
notebooks/12_t_side_ab_candidate_promotion.ipynb
```

Validated Stage 6.3 snapshot:

| Metric | Value |
| --- | ---: |
| Candidate | 35s stable_only logistic_regression |
| Candidate id | vitality_mirage_t_ab_35s_stable_only_logistic_v1 |
| Candidate prediction rows | 89 |
| Candidate error rows | 25 |
| Selected feature count | 31 |
| Macro F1 | 0.671 |
| Recall_B | 0.600 |
| Delta macro F1 vs matching baseline | +0.114 |
| Delta recall_B vs matching baseline | +0.160 |
| Delta B predicted as A | -4 |
| Decision | promote_as_exploratory_candidate |
| Audit | warning |

The decision is exploratory because manual review is still pending. Stage 6.3 is useful for reporting and comparison, but it does not make the model final, causal, externally validated, production-ready, or safe to treat as tactical truth without reviewing demos. No-plant rounds remain outside the A/B model.

## Stage 7 -- Final MVP Report Pack

Stage 7 is a documentation and closure stage. It does not train models, tune parameters, create features, change upstream datasets, build a dashboard, export to BigQuery, generate PDF/PPTX, or claim production readiness.

Run:

```bash
python -m src.reporting.build_final_mvp_report --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.reporting.build_final_mvp_report --config configs/project.yaml --dry-run
python -m src.reporting.build_final_mvp_report --config configs/project.yaml --report-version v1 --force
python -m src.reporting.build_final_mvp_report --config configs/project.yaml --include-technical-appendix false --force
```

Stage 7 reads the outputs from Stage 5 through Stage 6.3 and consolidates:

- final project summary;
- pipeline stage status;
- data lineage from demos to candidate model;
- dataset snapshot;
- tactical findings summary;
- promoted candidate metrics and error summary;
- limitations and next steps;
- artifact manifest;
- final report audit.

Eleven CSV/Parquet outputs are written under:

```text
data/gold/reporting/final_mvp/
```

The stage also generates:

```text
docs/final_mvp_report.md
docs/final_mvp_technical_appendix.md
docs/final_presentation_outline.md
notebooks/13_final_mvp_report_pack.ipynb
```

Validated Stage 7 snapshot:

| Metric | Value |
| --- | ---: |
| Report version | v1 |
| Stage-status rows | 15 |
| Lineage rows | 13 |
| Tactical finding rows | 12 |
| Artifact manifest rows | 10 |
| Eligible demos | 18 |
| Feature rounds | 405 |
| T-side rounds | 180 |
| T-side planted rounds | 98 |
| Candidate prediction rows | 89 |
| Candidate error rows | 25 |
| Candidate feature count | 31 |
| Final report audit | warning |

The audit remains `warning` because manual review is still pending. The final MVP report therefore presents the current candidate as exploratory and keeps no-plant, CT-side, causal claims, deployment, and external validation explicitly out of scope.

## Stage 8.0 -- Feature Contract & Freeze

Stage 8.0 freezes the current MVP feature inventory as metadata. It does not create new features, recalculate round features, rename columns, alter labels, train models, build a dashboard, or remove any existing dataset columns.

Run:

```bash
python -m src.features.build_feature_contract --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.features.build_feature_contract --config configs/project.yaml --dry-run
python -m src.features.build_feature_contract --config configs/project.yaml --target-map Mirage --contract-version v1 --force
```

The contract classifies each known feature by family, semantic role, lifecycle phase, temporal window, leakage risk, model/dashboard eligibility, side scope, map portability, region dependency, and horizon eligibility. It becomes the source of truth for future map expansion work.

Map portability terms:

- `global`: feature can be reused across maps without a map-specific region definition, such as round context or starting utility inventory.
- `map_abstract`: feature is portable in concept but requires each map to define the semantic region, such as `mid_control`, `a_pressure`, or `b_pressure`.
- `map_specific`: feature depends on a named or geometric concept that is not automatically portable.
- `unknown`: feature requires manual classification before expansion.

`modeling_allowed` and `dashboard_allowed` are intentionally separate. A feature can be useful for EDA/dashboard display while still being blocked from modeling because it is an identifier, target label, post-round outcome, plant result, or quality/audit field.

Seven CSV/Parquet outputs are written under:

```text
data/gold/features/feature_contract/
```

The stage also generates:

```text
configs/features/feature_contract.yaml
docs/feature_contract.md
notebooks/14_feature_contract.ipynb
```

Validated Stage 8.0 snapshot:

| Metric | Value |
| --- | ---: |
| Total features | 492 |
| Modeling-allowed features | 471 |
| Dashboard-allowed features | 479 |
| Temporal features | 448 |
| Global features | 184 |
| Map-abstract features | 308 |
| Map-specific features | 0 |
| Features requiring map registry | 308 |
| Unknown classification rows | 22 |
| Audit | warning |

The audit is `warning` because the contract intentionally preserves a review queue for uncertain classifications. Stage 8.1 will use this contract to define the Map Geometry & Region Registry, especially for map-abstract features that require semantic regions per map.

## Stage 8.1 -- Map Geometry & Region Registry

Stage 8.1 formalizes Mirage as the reference map registry. It separates physical map regions, tactical semantic groups, aliases, bombsites, and feature-contract coverage into versioned metadata.

Run:

```bash
python -m src.maps.build_map_registry --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.maps.build_map_registry --config configs/project.yaml --dry-run
python -m src.maps.build_map_registry --config configs/project.yaml --map Mirage --registry-version v1 --force
```

This stage does not refactor feature engineering yet. It does not recalculate `round_features_mvp`, `round_features_t_side_all`, `round_features_t_side_planted`, model outputs, EDA outputs, or final reports. It migrates the existing Mirage place-name region mapping from `configs/maps/mirage_regions.yaml` into a registry schema without inventing coordinates or changing current region behavior.

The registry separates:

- physical regions: concrete Mirage places such as `palace`, `a_ramp`, `connector`, `b_apps`, and `market`;
- semantic groups: portable tactical concepts such as `mid_control`, `a_pressure`, `b_pressure`, `ct_space`, `site_a`, and `site_b`;
- bombsites: explicit A/B site membership for future plant/site-pressure logic;
- feature coverage: every frozen feature with `region_dependency = true` is checked against the registry.

Eight CSV/Parquet outputs are written under:

```text
data/gold/maps/map_registry/
```

The stage also generates:

```text
configs/maps/map_registry.yaml
configs/maps/mirage.yaml
docs/map_geometry_region_registry.md
notebooks/15_map_region_registry.ipynb
```

Validated Stage 8.1 snapshot:

| Metric | Value |
| --- | ---: |
| Maps registered | 1 |
| Reference map | mirage |
| Physical regions | 15 |
| Semantic groups | 8 |
| Region-semantic mappings | 15 |
| Bombsite mappings | 2 |
| Region-dependent features | 308 |
| Resolved region features | 308 |
| Unresolved region features | 0 |
| Candidate region features | 11 |
| Candidate region features unresolved | 0 |
| Unknown rows | 0 |
| Ready for Stage 8.2 map-feature refactor | true |
| Audit | ok |

Mirage is the only production registry in this stage. New maps are intentionally out of scope until their physical regions, semantic mappings, and bombsites can be reviewed explicitly.

Stage 8.2 will make feature engineering consume `configs/maps/map_registry.yaml`, `configs/maps/mirage.yaml`, and `configs/features/feature_contract.yaml` while preserving current Mirage feature values.

## Stage 8.2 -- Map-Ready Feature Refactor

Stage 8.2 refactors the spatial feature path so map-dependent features resolve through the map registry and the frozen feature contract instead of reading Mirage-specific region definitions directly inside the feature engine.

Run:

```bash
python -m src.features.build_round_features --config configs/project.yaml --force
python -m src.features.side_datasets --config configs/project.yaml --force
```

Useful options:

```bash
python -m src.features.build_round_features --config configs/project.yaml --dry-run
python -m src.features.build_round_features --config configs/project.yaml --map-registry configs/maps/map_registry.yaml --feature-contract data/gold/features/feature_contract/feature_contract.parquet --force
```

What changed architecturally:

- `build_round_features` loads `configs/maps/map_registry.yaml` and resolves the active map before region features are generated.
- Mirage place-name aliases now come from `configs/maps/mirage.yaml`, which was migrated from the previous `mirage_regions.yaml`.
- Map-abstract features such as `players_mid_control_*`, `players_a_pressure_*`, and `players_b_pressure_*` resolve through semantic groups.
- Global features bypass the registry.
- `side_datasets` uses the same registry-backed lookup when rebuilding region timeline, death context, bomb carrier timeline, and outcome context.
- No new map, feature, model, label, dashboard, or training stage was added.

The main feature output names remain unchanged. Stage 8.2 still writes:

```text
data/gold/round_features/round_features_mvp.*
data/gold/region_presence/region_presence_by_round.parquet
data/gold/round_progression/round_region_timeline.*
data/gold/round_features/round_features_t_side_all.*
data/gold/round_features/round_features_t_side_planted.*
```

The new audits are written under:

```text
data/gold/feature_audit/map_feature_refactor_audit.*
data/gold/feature_audit/map_feature_registry_usage.*
data/gold/feature_audit/map_feature_compatibility.*
data/gold/feature_audit/map_feature_unknowns.*
```

Validated Stage 8.2 snapshot:

| Metric | Value |
| --- | ---: |
| Rounds processed | 405 |
| Features generated | 487 |
| Region-dependent features | 308 |
| Resolved region features | 308 |
| Unresolved region features | 0 |
| Candidate features expected | 31 |
| Candidate features found | 31 |
| Candidate features missing | 0 |
| Candidate feature values changed | 0 |
| Compatibility checks | 1511 |
| Compatibility check status | passed |
| Map feature engine ready | true |
| Audit | ok |

Stage 8.2 includes a deterministic tick-selection step for player/second buckets. This is necessary so repeated feature builds compare cleanly at strict numeric tolerance.

The detailed report and notebook are:

```text
docs/map_ready_feature_refactor.md
notebooks/16_map_ready_feature_refactor.ipynb
```

Stage 8.3 will be the formal Mirage Regression / Backward Compatibility Gate with a full downstream rerun.

## Stage 8.3 -- Mirage Regression / Backward Compatibility Gate

Stage 8.3 is the formal regression gate for the map-ready refactor. It does not train a model, add a map, tune thresholds, improve regions, or change labels. It compares the current Mirage MVP outputs against an explicitly created frozen baseline.

Create the baseline explicitly the first time:

```bash
python -m src.validation.mirage_regression_gate --config configs/project.yaml --baseline-mode create --force
```

Run the normal gate:

```bash
python -m src.validation.mirage_regression_gate --config configs/project.yaml --force
```

Optional rerun mode refreshes the validation stages before comparing:

```bash
python -m src.validation.mirage_regression_gate --config configs/project.yaml --rerun --force
```

The gate validates:

- feature-eligible demos;
- parse-quality output when available;
- `round_features_mvp`;
- `region_presence_by_round`;
- `round_region_timeline`;
- `round_state_resolved`;
- T-side, planted T-side, and CT-side datasets;
- feature contract and map registry metadata;
- Stage 6.3 candidate selection, feature set, metrics, and candidate input rows.

The baseline manifest is stored under:

```text
data/gold/validation/mirage_regression_baseline/
```

Gate outputs are written under:

```text
data/gold/validation/mirage_regression_gate/
```

The generated report and notebook are:

```text
docs/mirage_regression_gate.md
notebooks/17_mirage_regression_gate.ipynb
```

Validated Stage 8.3 snapshot:

| Metric | Value |
| --- | ---: |
| Datasets checked | 16 |
| Datasets passed | 16 |
| Datasets failed | 0 |
| Schema checks | 2218 |
| Row checks | 16 |
| Feature value checks | 487 |
| Critical invariants | 14 |
| Critical invariants failed | 0 |
| Candidate compatible | true |
| Feature engine compatible | true |
| Round state compatible | true |
| Side datasets compatible | true |
| ready_for_new_map_onboarding | true |
| Overall status | passed |

New map onboarding should only start when:

```text
ready_for_new_map_onboarding = true
```

## Stage 8.4 -- First New Map Onboarding: Vitality Inferno

Stage 8.4 adds Inferno as the first non-Mirage map in the project architecture. Vitality remains the only target team and the intended analytical scope remains T-side. This stage does not train a new model, reuse Mirage predictions, scrape HLTV, change frozen feature definitions, or add another team/map.

Run the onboarding audit:

```bash
python -m src.maps.onboard_map --config configs/project.yaml --map Inferno --target-team Vitality --force
```

Optional pipeline execution is guarded and conservative:

```bash
python -m src.maps.onboard_map --config configs/project.yaml --map Inferno --target-team Vitality --run-pipeline --force
```

The required precondition is still Stage 8.3:

```text
ready_for_new_map_onboarding = true
```

If the Mirage regression gate has not passed, Stage 8.4 aborts. `--force` cannot bypass that rule.

Stage 8.4 writes:

```text
data/gold/maps/inferno/onboarding/
docs/inferno_onboarding_report.md
notebooks/18_inferno_onboarding.ipynb
configs/maps/inferno.yaml
```

The onboarding outputs include:

- data availability;
- region inventory;
- semantic coverage;
- full feature-contract coverage;
- Mirage candidate feature portability as metadata only;
- dataset snapshot;
- feature quality checks when data exists;
- unknowns/blockers;
- readiness audit.

Current Stage 8.4 snapshot:

| Metric | Value |
| --- | ---: |
| Map registered | Inferno |
| Target team | Vitality |
| Local Inferno demos found | 5 |
| Parsed Inferno demos in silver tables | 0 |
| Feature-eligible Inferno demos | 0 |
| Required map-abstract semantics | 4 |
| Resolved required semantics | 0 |
| Mirage candidate features portable now | 20 of 31 |
| pipeline_execution_status | blocked_by_data |
| ready_for_inferno_feature_run | false |
| ready_for_inferno_eda | false |
| ready_for_inferno_modeling_evaluation | false |

Important interpretation: feature portability does not mean the Mirage model works on Inferno. It only says a feature definition is global or could be produced through the same semantic name once Inferno has verified physical region mappings.

The current Inferno registry intentionally uses `named_area` placeholders marked `unresolved`. This is deliberate. No Inferno Awpy/nav area inventory is available locally yet, and the project should not invent coordinates or fake area names.

## Stage 8.5 -- Canonical Map Identity & Safe Multi-Map Parsing

Stage 8.5 makes map selection official and safe before the project starts area discovery for Inferno. Raw names such as `Inferno`, `inferno`, and `de_inferno` now resolve to one canonical map identity from `configs/maps/map_registry.yaml`.

The canonical map identity layer lives in:

```text
src/maps/identity.py
```

The main helpers are:

- `canonical_map_id`;
- `canonical_map_name`;
- `same_map`;
- `resolve_map_identity`;
- `try_resolve_map_identity`;
- `known_map`.

Scoped parsing now supports explicit map/team overrides:

```bash
python -m src.parsing.parse_demos --config configs/project.yaml --target-map Inferno --target-team Vitality --force
python -m src.parsing.parse_quality --config configs/project.yaml --target-map Inferno --target-team Vitality --force
```

Safe write rules:

- default parsing still follows `project.target_maps`, currently Mirage;
- `--target-map Inferno` accepts aliases such as `Inferno`, `inferno`, and `de_inferno`;
- scoped `--force` removes and rewrites only rows for the selected `source_parse_id` values;
- full silver reset requires explicit `--reset-silver --force`;
- parse manifests and parse-quality outputs are upserted by scope so Mirage rows stay preserved.

The Stage 8.5 gate is:

```bash
python -m src.validation.multi_map_parse_gate --config configs/project.yaml --target-map Inferno --target-team Vitality --force
```

It writes:

```text
data/gold/validation/multi_map_parsing/
docs/multi_map_parsing.md
notebooks/19_multi_map_parsing.ipynb
```

The gate checks:

- canonical map identity resolution;
- parse-scope inventory;
- parse-scope status;
- scoped silver upsert safety;
- parse-manifest preservation;
- parse-quality preservation;
- place-column readiness;
- Mirage preservation;
- final multi-map parse audit.

Current Stage 8.5 snapshot:

| Metric | Value |
| --- | ---: |
| Target map | Inferno |
| Canonical target map id | inferno |
| Target team | Vitality |
| Selected Inferno demos | 5 |
| Parsed Inferno demos | 5 |
| Feature-eligible Inferno demos | 5 |
| Mirage feature-eligible demos preserved | 18 |
| `place` rows available for Inferno | 10081430 |
| ready_for_area_discovery | true |
| critical_failures | 0 |
| Gate status | ok |

Stage 8.5 deliberately does not discover Inferno areas, edit `configs/maps/inferno.yaml` semantic mappings, run Inferno feature engineering, train models, build dashboards, or use BigQuery.

## Stage 8.6 -- Generic Map Area Discovery

Stage 8.6 discovers real parser-reported places for any parsed canonical map scope. It reads scoped rows from `data/silver/parsed_demos/ticks.parquet`, using `source_parse_id` from the parse manifest and canonical map identity instead of textual map equality.

Run Mirage as the reference map:

```bash
python -m src.maps.discover_map_areas --config configs/project.yaml --map Mirage --target-team Vitality --force
```

Run Inferno as the first new discovered map:

```bash
python -m src.maps.discover_map_areas --config configs/project.yaml --map Inferno --target-team Vitality --force
```

The stage writes consolidated CSV and Parquet outputs under:

```text
data/gold/maps/area_discovery/
```

Main outputs:

- `map_area_discovery_summary`;
- `map_place_inventory`;
- `map_place_coordinates`;
- `map_place_by_demo`;
- `map_place_coverage`;
- `map_place_name_stability`;
- `map_place_vertical_profile`;
- `map_place_coordinate_sample`;
- `map_area_discovery_unknowns`;
- `mirage_place_registry_crosswalk`;
- `mirage_area_discovery_validation`;
- `inferno_place_discovery`;
- `map_area_discovery_audit`.

Documentation and notebook:

```text
docs/map_area_discovery.md
notebooks/20_map_area_discovery.ipynb
```

Current Stage 8.6 snapshot:

| Metric | Mirage | Inferno |
| --- | ---: | ---: |
| Target team | Vitality | Vitality |
| Source demos | 19 | 5 |
| Source rounds | 410 | 122 |
| Source ticks | 30206610 | 10081430 |
| Place column | place | place |
| Place non-null share | 100% | 100% |
| Unique raw places | 23 | 24 |
| Ready for region mapping | true | true |
| Status | ok | ok |

Mirage is used as a validation reference. The current Mirage registry explains 100% of observed Mirage tick places in this local sample, with 23 matched observed places and no unmatched observed places.

Inferno now has real raw-place, coordinate, coverage, stability, vertical-profile, and sample outputs. Stage 8.6 does not decide that raw places such as `Banana`, `BombsiteA`, `Middle`, or `Apartments` belong to tactical groups like `b_pressure`, `site_a`, or `mid_control`; that physical-to-semantic mapping is handled by Stage 8.7.

## Stage 8.7 -- Inferno Physical Region & Tactical Semantic Mapping

Stage 8.7 formalizes Inferno in the map registry using Stage 8.6 evidence. It maps raw parser places to physical regions, maps physical regions to tactical semantic groups, validates bombsites, updates Feature Contract metadata to v2, and confirms Mirage behavior through the regression gate.

Run the mapping:

```bash
python -m src.maps.build_region_mapping --config configs/project.yaml --map Inferno --target-team Vitality --force
```

Then refresh registry outputs and run the Mirage regression gate:

```bash
python -m src.maps.build_map_registry --config configs/project.yaml --force
python -m src.validation.mirage_regression_gate --config configs/project.yaml --target-map Mirage --target-team Vitality --force
```

Stage 8.7 writes:

```text
data/gold/maps/inferno/region_mapping/
docs/inferno_region_mapping.md
notebooks/21_inferno_region_mapping.ipynb
configs/maps/inferno.yaml
configs/maps/map_registry.yaml
```

Main outputs:

- `inferno_region_mapping_proposal`;
- `inferno_place_region_crosswalk`;
- `inferno_physical_region_inventory`;
- `inferno_semantic_mapping`;
- `inferno_semantic_coverage`;
- `inferno_region_coordinate_validation`;
- `inferno_candidate_feature_portability_v2`;
- `inferno_region_mapping_unknowns`;
- `inferno_region_mapping_audit`.

Current Stage 8.7 snapshot:

| Metric | Value |
| --- | ---: |
| Raw Inferno places observed | 24 |
| Raw Inferno places mapped | 24 |
| Mapped tick share | 100% |
| Active physical regions | 21 |
| Required frozen map-abstract semantics | 4 |
| Missing required semantics | 0 |
| Candidate features audited | 31 |
| Candidate features cross-map comparable | 22 |
| Mirage regression datasets failed | 0 |
| ready_for_inferno_feature_run | true |

Inferno uses `geometry.type: named_area` with `geometry.area_names` as the official source-place mapping. The registry lookup now resolves `region_id`, `display_name`, `aliases`, `geometry.area_names`, and `geometry.source_place_aliases`, preserving Mirage compatibility while allowing parser-native names like `Banana` and `BombsiteA` to resolve directly.

The verified physical-to-semantic layers are:

- raw parser place -> physical region;
- physical region -> tactical semantic group;
- tactical semantic group -> map-abstract feature.

Examples:

| Raw place | Physical region | Semantic |
| --- | --- | --- |
| `Banana` | `banana` | `b_pressure` |
| `BombsiteA` | `bombsitea` | `site_a` |
| `BombsiteB` | `bombsiteb` | `site_b` |
| `Middle` | `middle` | `mid_control` |
| `CTSpawn` | `ctspawn` | `ct_space` |
| `Bridge`, `Upstairs`, `Deck`, `Kitchen` | `second_mid_upper` | `mid_control`, `rotation` |

Feature Contract v2 separates generation portability from cross-map analytical comparability:

- utility counts can be `direct` comparable;
- semantic-region features compare through `semantic` mode once each map has validated semantics;
- raw coordinate features such as `team_center_x_*` are available to generate but are not directly comparable without normalization;
- map-specific Mirage terms remain `map_specific_only`.

Important interpretation: `available_on_inferno = true` does not mean a Mirage-trained model can predict Inferno. It only means the feature can be generated safely for Inferno. Model transfer and multi-map modeling remain out of scope until a later stage.

Stage 8.7 deliberately does not run Inferno feature engineering, Inferno round state, Inferno T-side/CT-side datasets, ML, dashboards, BigQuery, or a new map/team onboarding.

## Stage 8.8 -- Inferno Feature Pipeline Run & Multi-Map Gold Storage

Stage 8.8 runs the analytical feature pipeline for the validated Inferno scope and stores outputs in consolidated Gold tables that contain both Mirage and Inferno. Forced reruns replace only the selected logical scope, defined by target team plus canonical map identity, so historical Mirage rows remain intact.

Run the scoped Inferno pipeline:

```bash
python -m src.features.run_map_pipeline --config configs/project.yaml --target-map Inferno --target-team Vitality --force
```

Validate the consolidated Gold layer:

```bash
python -m src.validation.multi_map_gold_gate --config configs/project.yaml --target-map Inferno --target-team Vitality --force
```

The orchestrator runs only:

- `src.features.build_round_features`;
- `src.features.round_state`;
- `src.features.side_datasets`;
- `src.validation.multi_map_gold_gate`.

It deliberately does not run Inferno EDA, train or retrain models, apply a Mirage model to Inferno, build dashboards, use Streamlit, or export to BigQuery.

Main consolidated Gold tables now include Mirage + Inferno:

- `data/gold/round_features/round_features_mvp.parquet`;
- `data/gold/round_features/round_base.parquet`;
- `data/gold/round_features/player_round_utility.parquet`;
- `data/gold/utility_events/utility_events.parquet`;
- `data/gold/region_presence/region_presence_by_round.parquet`;
- `data/gold/round_state/round_state_resolved.parquet`;
- `data/gold/round_features/round_features_t_side_all.parquet`;
- `data/gold/round_features/round_features_t_side_planted.parquet`;
- `data/gold/round_features/round_features_ct_side.parquet`;
- `data/gold/round_progression/round_region_timeline.parquet`;
- `data/gold/round_progression/death_context_by_round.parquet`;
- `data/gold/round_progression/bomb_carrier_timeline.parquet`;
- `data/gold/round_progression/round_outcome_context.parquet`.

Validation outputs are written under:

```text
data/gold/validation/multi_map_gold/
```

The gate writes scope inventory, scoped upsert audit, key collision audit, Mirage preservation checks, Inferno feature materialization, candidate feature materialization, semantic feature sanity, round-state summary, side-dataset summary, and a final `multi_map_gold_audit`.

Current Stage 8.8 snapshot:

| Dataset | Mirage rows | Inferno rows |
| --- | ---: | ---: |
| `round_features_mvp` | 405 | 122 |
| `region_presence_by_round` | 43,961 | 17,760 |
| `round_state_resolved` | 405 | 122 |
| `round_features_t_side_all` | 180 | 65 |
| `round_features_t_side_planted` | 98 | 40 |
| `round_features_ct_side` | 225 | 57 |
| `round_region_timeline` | 43,961 | 17,760 |
| `death_context_by_round` | 2,736 | 786 |
| `bomb_carrier_timeline` | 8,910 | 2,684 |
| `round_outcome_context` | 405 | 122 |

`src/storage/scoped_gold.py` owns the generic upsert behavior for Gold tables. It uses stable keys and canonical map identity, writes atomically through temp files and `os.replace`, and refuses unsafe duplicate-key states instead of relying on row order.

Docs/notebook:

```text
docs/inferno_feature_pipeline.md
notebooks/22_inferno_feature_pipeline.ipynb
```

Validation commands:

```bash
python -m pytest
python -m ruff check .
```
