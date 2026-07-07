# cs2-tactical-analytics

Offline-first CS2 tactical analytics pipeline currently implemented through **Stage 5.2 -- T-side Manual Review Pack**.

Project direction:

```text
HLTV -> demos .dem -> CS2 parser -> analytical tables -> round features -> ML model -> dashboard
```

The repository currently covers catalog ingestion, local demo intake/extraction, metadata probing, Awpy parsing, parse-quality gates, full-round feature engineering, round-state resolution, side-specific datasets, auditable T-side tactical EDA, ranked findings, and a concrete round-level manual-review pack. ML, model training, dashboards, BigQuery, and Streamlit are not implemented yet.

## Current Status

Validated local snapshot for Vitality on Mirage:

- 18 feature-eligible demos;
- 405 parsed rounds in `round_features_mvp`;
- 180 resolved T-side rounds;
- 225 resolved CT-side rounds;
- 98 high-confidence planted T-side rounds: 72 plant A and 26 plant B;
- 82 T-side rounds without a valid Vitality plant;
- interval and cumulative feature windows through 115 seconds;
- 11 Stage 5 analytical tables generated in CSV and Parquet;
- 10 Stage 5.1 findings tables plus a generated Markdown report;
- 75 ranked tactical candidates and 12 manual-review items;
- 20 Stage 5.2 findings covered by 151 selected finding-round pairs;
- 110 tests passing and `ruff check .` passing.

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
```

Important dependency rules:

- rerunning `parse_demos --force` requires rebuilding parse quality and every downstream Gold stage;
- rerunning `build_round_features --force` requires rebuilding `round_state`, `side_datasets`, and Stage 5;
- `side_datasets` refuses to run without `round_state_resolved` so it cannot silently fall back to the old side proxy;
- Stage 5 reads corrected Gold tables only and does not use `round_features_mvp` for final T-side decisions.
- Stage 5.1 reads Stage 5 aggregates first and ranks conservative findings for manual review.
- Stage 5.2 links Stage 5.1 findings to concrete T-side rounds and must be rebuilt whenever Stage 5.1 changes.

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

Stage 5.2 does not train a model. The next step is a leakage-controlled A/B baseline only after the manual decisions are completed and a pre-plant prediction horizon is chosen.

Validation commands:

```bash
python -m pytest
python -m ruff check .
```
