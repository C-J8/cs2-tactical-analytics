# cs2-tactical-analytics

Stage 1 builds the initial project structure and a reliable match/map catalog for a CS2 tactical analytics pipeline.

Final direction:

```text
HLTV -> demos .dem -> CS2 parser -> analytical tables -> round features -> ML model -> dashboard
```

This stage deliberately does not download demos, parse demos, train models, or build dashboards.

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
- `configs/player_rosters.yaml`: player nicknames by team for side and plant ownership resolution.

Adding a new team only requires adding it to `configs/teams.yaml` and listing it in `target_teams`. Adding a new map only requires adding it to `configs/maps.yaml` and listing it in `target_maps`.

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
python -m src.features.build_round_features --config configs/project.yaml --window-end 20
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
- early-round position features for the first 20 seconds after freeze end;
- Mirage place-name mapping into tactical region groups;
- initial utility loadout from `ticks.inventory`;
- smoke/molotov utility events from `smokes.parquet` and `infernos.parquet`;
- utility usage aggregates for the first 20 seconds;
- feature audit with warnings, null-column counts, and utility/region status.

Important limitations:

- `grenades.parquet` is detected as trajectory/tick-level and is not treated as a simple grenade-event table in this MVP.
- Target-site inference for rounds without plant is not implemented; those rounds keep a null model label.
- Silver ticks do not yet contain reliable player-to-team identity. Early position and utility features use T-side players as the attacking-side proxy and record this in `feature_audit`.
- Tickrate is assumed to be 64 ticks per second for early-window features.
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

Validation commands:

```bash
python -m pytest
python -m ruff check .
```
