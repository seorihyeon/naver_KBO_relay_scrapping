# Plate Appearance Scoring Rules

The relay scorer now uses a plate-appearance state machine instead of a text-only keyword counter.

## Engine Model

Each plate appearance tracks:

- current, starting, and finishing batter
- current, starting, and finishing pitcher
- batter substitution count and pitcher substitution count
- terminal vs partial plate appearance state
- official terminal result category
- batter-credit owner and pitcher-credit owner as separate decisions

The same scoring engine is reused by:

- `check_data.py`
- `src/kbo_ingest/source_profile.py`
- `src/kbo_ingest/validation.py`
- `src/kbo_ingest/normalize_game.py`

## Official Scoring Rules

- foul-bunt third strike is a strikeout and an at-bat
- dropped third strike stays a strikeout even if the batter reaches on a wild pitch or passed ball
- a pinch hitter entering with two strikes only gives the strikeout/at-bat back to the previous batter when the PA ends in a strikeout
- walk, hit-by-pitch, hit, reach-on-error, fielder's choice, and interference stay with the substitute batter
- catcher or fielder interference counts as a plate appearance but not an at-bat
- sacrifice bunt and sacrifice fly count as plate appearances but not at-bats
- walk, intentional walk, automatic intentional walk, and hit-by-pitch do not count as at-bats
- reach-on-error, fielder's choice, force-out, and double-play outs count as at-bats unless a sacrifice or interference rule overrides them
- after a mid-count pitching change, a walk stays with the previous pitcher only for hitter-advantage counts (`2-0`, `2-1`, `3-0`, `3-1`, `3-2`)
- all non-walk results, and walks from neutral or pitcher-advantage counts, are credited to the reliever
- batter ownership and pitcher ownership are resolved independently

## Source Anomalies

If a source JSON still disagrees with the official record because the relay is duplicated, truncated, or missing lineup metadata, that discrepancy stays in `source_validation` instead of being patched with game-specific scoring exceptions.
