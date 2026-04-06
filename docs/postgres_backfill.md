# PostgreSQL Backfill and Validation

This document describes the reproducible PostgreSQL load/validate flow for
the 2024 and 2025 KBO game JSON files in `games/`.

## Scope

- Seasons: `2024`, `2025`
- Manifest seed: `20260404`
- Source root: `games/`
- Database DSN source: [`config/app_config.json`](/d:/Github/KBO_scrapping_analysis/config/app_config.json)

## What was added

- Manifest builder with deterministic shuffle
- Slice loader with `--offset` and `--skip-validate`
- Cumulative staged validation reports
- Full-schema validation over raw and normalized tables
- Source-vs-loader issue separation in reports

## Main Commands

Build the manifest:

```powershell
python postgres_loader.py manifest `
  --data-dir games `
  --seasons 2024 2025 `
  --seed 20260404 `
  --output reports/manifests/kbo_2024_2025_seed20260404.json
```

Run a clean staged validation load for the first 10 games:

```powershell
python postgres_loader.py load `
  --dsn "postgresql://postgres:KboLocal_20260404_QaOnly!@localhost:5432/kbo" `
  --schema sql/schema.sql `
  --manifest reports/manifests/kbo_2024_2025_seed20260404.json `
  --limit 10 `
  --reset-db `
  --report-json reports/stage_loads/load_0010_secure_v2.json `
  --run-label "KBO Stage 10 Secure v2"
```

Run a clean staged validation load for the first 100 games:

```powershell
python postgres_loader.py load `
  --dsn "postgresql://postgres:KboLocal_20260404_QaOnly!@localhost:5432/kbo" `
  --schema sql/schema.sql `
  --manifest reports/manifests/kbo_2024_2025_seed20260404.json `
  --limit 100 `
  --reset-db `
  --report-json reports/stage_loads/load_0100_secure_v2.json `
  --run-label "KBO Stage 100 Secure v2"
```

Run a clean staged validation load for the first 250 games:

```powershell
python postgres_loader.py load `
  --dsn "postgresql://postgres:KboLocal_20260404_QaOnly!@localhost:5432/kbo" `
  --schema sql/schema.sql `
  --manifest reports/manifests/kbo_2024_2025_seed20260404.json `
  --limit 250 `
  --reset-db `
  --report-json reports/stage_loads/load_0250_secure_v2.json `
  --run-label "KBO Stage 250 Secure v2"
```

Append the remaining games after a validated 250-game base load:

```powershell
python postgres_loader.py load `
  --dsn "postgresql://postgres:KboLocal_20260404_QaOnly!@localhost:5432/kbo" `
  --schema sql/schema.sql `
  --manifest reports/manifests/kbo_2024_2025_seed20260404.json `
  --offset 250 `
  --skip-validate `
  --report-json reports/final_run/append_load_report.json `
  --run-label "KBO Final Append Load"
```

Validate the fully loaded database against the full manifest with the bulk
validator:

```powershell
python scripts/bulk_validate_full.py `
  --dsn "postgresql://postgres:KboLocal_20260404_QaOnly!@localhost:5432/kbo" `
  --manifest reports/manifests/kbo_2024_2025_seed20260404.json `
  --report-json reports/final_run/full_validate_report.json
```

Use `postgres_loader.py validate` for smaller manifest slices during debugging.

## Sample-Loop Command

`sample-loop` still exists and always appends the full-manifest stage after the
requested batch sizes.

Example:

```powershell
python postgres_loader.py sample-loop `
  --dsn "postgresql://postgres:KboLocal_20260404_QaOnly!@localhost:5432/kbo" `
  --schema sql/schema.sql `
  --manifest reports/manifests/kbo_2024_2025_seed20260404.json `
  --report-dir reports/sample_loop `
  --batch-sizes 10 25 50 100 250 500
```

## Reports

- Manifest: `reports/manifests/`
- Staged load reports: `reports/stage_loads/`
- Final append/load logs: `reports/final_run/`
- Each load/validate run writes JSON and Markdown reports with:
  - table-level expected vs actual counts
  - blocking loader/schema issues
  - source JSON inconsistency issues

## Validation Rules

Validation covers every schema table, including zero-row expectations:

- Raw layer:
  - `raw_games`
  - `raw_relay_blocks`
  - `raw_text_events`
  - `raw_pitch_tracks`
  - `raw_plate_metrics`
- Dimensions and metadata:
  - `teams`
  - `players`
  - `stadiums`
  - `games`
  - `game_roster_entries`
- Normalized play/event tables:
  - `innings`
  - `plate_appearances`
  - `pa_events`
  - `pitches`
  - `pitch_tracking`
  - `batted_ball_results`
  - `baserunning_events`
  - `review_events`
  - `substitution_events`

## Important Implementation Notes

- `ptsPitchId` is not globally unique, so normalized `pitches.pitch_id` is now
  namespaced by `game_id`, while the original raw ID is preserved in
  `source_pitch_id`.
- `raw_pitch_tracks` preserves duplicate `ptsOptions` rows via
  `track_index_in_block` instead of deduplicating by `pitch_id`.
- Partial plate appearances are explicitly modeled when the relay enters a
  batter sequence but no terminal batting result is present.
- Source-inconsistent games are reported under `source_issues`; loader errors
  stay under `blocking_issues`.

## Failure Reproduction

If a stage fails, rerun the exact command written in the corresponding report.
The report JSON contains:

- the manifest slice size
- the report path
- per-table counts
- the affected game paths
- the rule/code that failed

Use the same manifest, DSN, and report path pattern to reproduce.
