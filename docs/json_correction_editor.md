# JSON Correction Editor

## Run

```bash
python kbo_integrated_gui.py
```

Open the `수정/보정` tab.

## Open a file

1. Set `Root` to the directory that contains your game JSON files.
2. Use `Search` to filter by season, date, or game id.
3. Pick a file from the left list.
4. Click `파일 열기`.

## Main workflow

- `Game Info`: edit game metadata such as date, teams, starter pitcher ids, stadium, and flags.
- `Lineup`: switch between `home_starter / home_bullpen / home_candidate / away_*`, select a row, edit it on the right, then apply.
- `Relay`: inspect relay by inning/block/event.
  - Switch `Event / PA` view to inspect the same block as raw events or plate appearances.
  - Add, delete, duplicate, and move blocks/events.
  - Edit `type / seqno / text / pitchNum / pitchResult / ptsPitchId / stuff / playerChange / currentGameState`.
  - Filter by inning, half, event type, free-text search, duplicates-only, and missing/error-only.
  - `seq 재정렬` rewrites relay `seqno` in current order.
  - `빈 state 채우기` fills missing `currentGameState` fields from the previous event in the selected block.
- `Record`: switch between batter/pitcher home-away tables, edit the selected row, or recalculate batter totals.
- `검증 결과`: run `check_data.validate_game()` plus relay anomaly checks. Clicking a finding moves the editor to the related relay or record location when possible.
- `Auto Preview`: preview the correction engine output before applying it.
- `Diff`: preview unsaved changes against the last saved version.
- `History`: review session actions and backup files.

## Structured correction actions

### Structured Add

Use this panel to add a relay event without editing raw JSON text.

- Supported templates: `pitch / bat_result / baserunning / substitution / review / other`
- Minimum inputs:
  - insert position (`before / after`)
  - batter id or pitcher id when relevant
  - template-specific meaning such as `result_type`, `pitchResult`, or custom text
- Optional inputs:
  - `pitchNum`
  - `ptsPitchId`
  - up to 3 runner movements

### Missing PA

Use `누락 타석 삽입` when an entire plate appearance is missing.

- Minimum inputs:
  - batter
  - pitcher
  - insert position
  - final result
- Optional inputs:
  - pitch list
  - `pitchResult / pitchNum / ptsPitchId`
  - runner movements

The editor generates the intro event, optional pitch events, the terminal result event, optional baserunning events, then rebuilds the game.

### Meaning Edit

Use `결과 의미 수정` when the event exists but its baseball meaning is wrong.

Examples:

- `아웃` -> `2루타`
- `실책 출루` -> `안타`
- replace only the final result text while preserving the same batter/pitcher

When applied, the editor rebuilds downstream `currentGameState`, scoreboard fields, and record totals.

### PA Split / Merge

Use `타석 분리` when two batters were merged into one PA, or `이전 타석과 병합` when they should belong to one PA.

- Split inputs:
  - first batter/result
  - second batter/result
  - optional runner movements for each side
- Merge inputs:
  - merged batter id/name when both segments should be credited to one batter

## Auto correction engine

Structured correction actions call an internal rebuild engine. It recalculates:

- `seqno`
- `currentGameState`
- balls / strikes / outs
- base occupancy
- score / hit / walk / error totals
- plate appearance boundaries
- `record.batter` and `record.pitcher`

Validation also adds `auto_rebuild_drift` warnings when the current relay state differs from what the rebuild engine would produce.

## Save / backup / restore

- `저장`: writes the edited game JSON back to the real file on disk.
- Before save, the editor writes:
  - `.history/<game_stem>/*.bak`
  - `.history/<game_stem>/*.patch`
  - `.history/<game_stem>/changes.jsonl`
- `Undo / Redo`: session-local history.
- `세션 되돌리기`: revert to the payload as it was when the file was opened.
- `백업 복원`: restore the latest saved `.bak` over the working game file.

## Safety notes

- The editor is a structured editor, not a raw JSON text box.
- Saves always write pretty JSON.
- Existing old-schema files are migrated to the minimal schema when loaded and saved.
- Structured correction actions always rebuild the full game state after the edit so later events stay in sync.
