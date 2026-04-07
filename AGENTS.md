# AGENTS.md

## Purpose

This repository collects KBO relay JSON from Naver, corrects broken source games in a structured GUI, ingests corrected games into PostgreSQL, and validates / replays normalized baseball state.

Agents working in this repository should prioritize **data correctness, schema discipline, and reproducible validation** over broad refactors or convenience shortcuts.

## Read these first

Before making changes, review the documents that match your task.

- `README.md`
- `docs/minimal_game_json_schema.md`
- `docs/json_correction_editor.md`
- `docs/gui_architecture.md`
- `docs/postgres_backfill.md`

## Documentation language rule

Project-facing documentation should be written in **Korean**.

This applies to newly added or substantially updated:

- files under `docs/`
- user-facing workflow guides
- repository usage notes
- correction / ingestion / replay operation manuals

Code comments, internal identifiers, and test names may remain in English when that is clearer, but end-user documentation should default to Korean.

## Repository invariants

### 1) Saved game JSON must stay on the minimal schema

The canonical saved payload is the repository's minimal schema (`schema_version = 2`).
Do not expand saved JSON back into a broad copy of the Naver response.

Keep only the fields required for:

- ingestion
- validation
- replay normalization
- structured correction in the GUI

If you change payload shape, update both code and docs together.

### 2) Relay edits must preserve rebuild semantics

This project does not treat correction as raw text editing. Structured edits are expected to rebuild downstream state.

When changing correction, normalization, or relay-edit logic, preserve automatic recomputation of:

- `seqno`
- `currentGameState`
- balls / strikes / outs
- base occupancy
- score / hit / walk / error totals
- plate appearance boundaries
- `record.batter`
- `record.pitcher`

### 3) Validation is a core product feature

`check_data.validate_game()` is not just a helper; it is part of the product.
Do not weaken validation just to make broken data pass.

Prefer fixing the source, correction flow, or normalization logic instead of muting checks.

### 4) Backup / history behavior must remain safe

GUI saves and in-place migrations are expected to keep backup artifacts under `.history/<game_stem>/`.

Do not remove or weaken generation of:

- `.bak`
- `.patch`
- `changes.jsonl`

unless the replacement is clearly safer.

## Architecture rules

### GUI structure

`kbo_integrated_gui.py` should remain a thin entry point.
Application startup belongs in `gui.app_shell.run()`.

For GUI work:

- keep controllers in `tabs/` focused on UI coordination
- move heavy logic into `gui/<feature>_service.py` or `gui/<feature>/...`
- keep reusable widgets in `gui/components/`
- use shared background job infrastructure for long-running work
- avoid embedding scraping, DB logic, normalization, or replay derivation directly in tab classes

### State management

Preserve the split in `gui/state.py`:

- model = pure application state
- presenter = DearPyGui widget updates
- facade / app state = dispatch and subscription layer

Do not re-entangle pure state with direct widget mutation.

### Background work

Long-running work should use the shared `JobRunner` in `gui/jobs/`.
Do not block the DearPyGui UI loop with scraping, ingestion, or heavy validation.

### Replay structure

Keep replay responsibilities separated:

- SQL / data loading in repository classes
- derived baseball state in state builders
- navigation / indexing in navigation helpers
- anomaly detection in detector classes
- drawing in renderer classes

If a change mixes these layers together again, split responsibilities before adding more logic.

## Data and ingestion rules

### Pitch IDs and raw tracking data

The PostgreSQL loading flow depends on these assumptions:

- `ptsPitchId` is **not** globally unique
- normalized `pitches.pitch_id` must remain namespaced by game
- the original raw pitch id must remain preserved separately
- duplicate raw tracking rows must not be silently deduplicated away when the source emitted them

### Partial plate appearances must remain modeled

Source data may contain incomplete batter sequences without a clean terminal result.
Do not assume every plate appearance ends with a fully formed terminal batting event.

### Keep source issues separate from loader issues

Source-data inconsistencies and loader / schema failures must remain separate reporting categories.
Do not merge them into one bucket.

## Editing guidance

### When changing JSON schema or normalization

Also review:

- `check_data.py`
- `src/kbo_ingest/game_json.py`
- `src/kbo_ingest/normalize_game.py`
- `src/kbo_ingest/pa_scoring.py`
- ingestion-related code paths referenced by `docs/minimal_game_json_schema.md`

### When changing GUI layout or jobs

Keep pure logic testable without requiring the actual GUI to open.

### When changing replay logic

Prefer focused fixture-based tests over manual inspection alone.

## Validation commands

Run the smallest meaningful verification set for your change.

### JSON / schema / correction work

```bash
python check_data.py games
```

Migration dry-run:

```bash
python migrate_game_json.py games
```

In-place migration with backup / patch generation:

```bash
python migrate_game_json.py games --in-place
```

### GUI / replay refactors

```bash
pytest tests/test_gui_job_runner.py tests/test_gui_layout_manager.py tests/test_replay_refactor.py
```

Prefer targeted runs over unrelated full-suite runs while iterating.

## Change checklist

Before finishing a task, verify:

1. Does the change preserve minimal-schema discipline?
2. If relay / correction logic changed, does downstream rebuild still work?
3. If GUI logic changed, is heavy work still off the UI thread?
4. If replay logic changed, are repository / state / navigation / renderer responsibilities still separated?
5. Did you run the narrowest meaningful validation command or tests?
6. If workflow or behavior changed, did you update the relevant document in `docs/`?
7. If documentation was added or updated, is it written in Korean?

## Preferred contribution style

- Make small, reviewable changes.
- Preserve existing CLI entry points and workflow names unless there is a strong reason to change them.
- Add focused tests for pure logic.
- Avoid speculative cleanup unrelated to the task.
- Favor explicit baseball/data invariants over convenience shortcuts.
