# Minimal Game JSON Schema

## Why this schema exists

The repository no longer stores a broad copy of every Naver response field. The saved JSON now keeps only:

- fields referenced by ingestion, validation, and replay normalization code
- fields needed for manual correction in the GUI editor
- fields needed to rebuild normalized pitch / plate appearance / substitution state

The schema version is:

```json
{
  "schema_version": 2
}
```

## Code-traced consumer fields

The field set below comes from the code paths in:

- `check_data.py`
- `src/kbo_ingest/source_profile.py`
- `src/kbo_ingest/ingest_raw.py`
- `src/kbo_ingest/normalize_game.py`
- `src/kbo_ingest/pa_scoring.py`
- `tabs/replay_tab.py` indirectly through normalized PostgreSQL tables

### Top level

- `schema_version`
- `game_id`
- `game_source`
- `collected_at`
- `lineup`
- `relay`
- `record`

### `lineup.game_info`

Used for source identity, team linkage, starter checks, game metadata, and DB game rows:

- `gdate`
- `gtime`
- `hCode`
- `hName`
- `hPCode`
- `aCode`
- `aName`
- `aPCode`
- `round`
- `gameFlag`
- `stadium`
- `isPostSeason`
- `cancelFlag`
- `statusCode`

### Lineup rows

Starter rows:

- `playerCode`
- `playerName`
- `position`
- `positionName`
- `batorder`
- `backnum`
- `hitType`
- `batsThrows`
- `height`
- `weight`

Bullpen rows:

- `playerCode`
- `playerName`
- `pos`
- `hitType`
- `batsThrows`

Candidate rows:

- `playerCode`
- `playerName`
- `pos`
- `position`
- `hitType`
- `batsThrows`

### Relay block

- `title`
- `titleStyle`
- `no`
- `inn`
- `homeOrAway`
- `statusCode`
- `metricOption.homeTeamWinRate`
- `metricOption.awayTeamWinRate`
- `metricOption.wpaByPlate`
- `textOptions`
- `ptsOptions`

### Relay event

- `seqno`
- `type`
- `text`
- `pitchNum`
- `pitchResult`
- `ptsPitchId`
- `speed`
- `stuff`
- `batterRecord.pcode`
- `playerChange.type`
- `playerChange.outPlayerTurn`
- `playerChange.inPlayer.{playerId,playerCode,playerName,playerPos,position}`
- `playerChange.outPlayer.{playerId,playerCode,playerName,playerPos,position}`

### `currentGameState`

Used by validation, PA scoring, normalization, inning summaries, pitch/runner ownership, and editor repair tools:

- `homeScore`
- `awayScore`
- `homeHit`
- `awayHit`
- `homeBallFour`
- `awayBallFour`
- `homeError`
- `awayError`
- `pitcher`
- `batter`
- `strike`
- `ball`
- `out`
- `base1`
- `base2`
- `base3`

### `ptsOptions`

Used by raw pitch tracking ingestion and replay strike-zone visualization:

- `pitchId`
- `inn`
- `ballcount`
- `crossPlateX`
- `crossPlateY`
- `topSz`
- `bottomSz`
- `vx0`
- `vy0`
- `vz0`
- `ax`
- `ay`
- `az`
- `x0`
- `y0`
- `z0`
- `stance`

### `record.batter`

Player rows:

- `playerCode`
- `name`
- `batOrder`
- `ab`
- `hit`
- `bb`
- `kk`
- `hr`
- `rbi`
- `run`
- `sb`

Team totals:

- `ab`
- `hit`
- `bb`
- `kk`
- `hr`
- `rbi`
- `run`
- `sb`

### `record.pitcher`

- `pcode`
- `name`
- `inn`
- `r`
- `er`
- `hit`
- `bb`
- `kk`
- `hr`
- `ab`
- `bf`
- `pa`
- `bbhp`

## Removed fields

The following were intentionally dropped because downstream code does not consume them and the correction editor does not require them:

- `currentPlayersInfo`
- per-inning batter box fields such as `inn1`, `inn2`, ...
- record presentation-only fields such as `era`, `wls`, `gameCount`, `seasonWin`, `seasonLose`
- lineup fields like `birth`
- extra `game_info` flags such as `ptsFlag`, `optionFlag`, full team names, and other display-only metadata

## Canonical shape example

```json
{
  "schema_version": 2,
  "game_id": "20260406HHAW02026",
  "game_source": {
    "provider": "naver",
    "source_game_id": "20260406HHAW02026",
    "url": "https://m.sports.naver.com/game/20260406HHAW02026"
  },
  "collected_at": "2026-04-06T12:00:00Z",
  "lineup": { "...": "..." },
  "relay": [ [ { "...": "..." } ] ],
  "record": { "...": "..." }
}
```

## Backward compatibility

- Old JSON files are still accepted by validation and ingestion.
- `check_data.validate_game()`, `build_source_profile()`, and raw ingestion normalize old files into the minimal schema in memory.
- Saving through the correction editor writes schema v2.

## Migration

Dry-run:

```bash
python migrate_game_json.py games
```

Rewrite files in place:

```bash
python migrate_game_json.py games --in-place
```

Write migrated copies elsewhere:

```bash
python migrate_game_json.py games --output-dir migrated_games
```

## Validation after migration

You can validate migrated files with:

```bash
python check_data.py games
```

Or load them into PostgreSQL and run the existing source/normalized validation pipeline.
