# KBO Naver Relay Collection / Correction / Ingestion

This repository collects KBO game JSON from Naver, lets you correct bad source JSON in a structured DearPyGui editor, and loads the corrected games into PostgreSQL for replay and validation.

## Main entry points

### Integrated GUI

```bash
python kbo_integrated_gui.py
```

Tabs:

- `데이터 수집`: collect Naver games into `games/**/*.json`
- `수정/보정`: open a game JSON, edit `lineup / relay / record`, insert missing PAs/events, apply meaning-based result fixes, split/merge merged PAs, run validation, save with backup/history
- `데이터 적재`: create schema and ingest JSON into PostgreSQL
- `Replay / 검증`: inspect normalized replay data from PostgreSQL

### Batch migration to the minimal schema

Dry-run against a directory:

```bash
python migrate_game_json.py games
```

Rewrite files in place with backup + patch:

```bash
python migrate_game_json.py games --in-place
```

Write migrated files into another directory:

```bash
python migrate_game_json.py games --output-dir migrated_games
```

## Notes

- Collected JSON now uses the repository's minimal schema (`schema_version = 2`).
- Older JSON files are still accepted by validation/ingestion because they are normalized on load.
- Editor saves create `.history/<game_stem>/*.bak`, `*.patch`, and `changes.jsonl`.

## Docs

- Editor usage: [`docs/json_correction_editor.md`](docs/json_correction_editor.md)
- Minimal schema + field analysis + migration notes: [`docs/minimal_game_json_schema.md`](docs/minimal_game_json_schema.md)
- PostgreSQL loading flow: [`docs/postgres_backfill.md`](docs/postgres_backfill.md)
