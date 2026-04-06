from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Any

import psycopg

from src.kbo_ingest.pa_scoring import classify_terminal_pa_text


TABLE_NAMES = [
    "raw_games",
    "raw_relay_blocks",
    "raw_text_events",
    "raw_pitch_tracks",
    "raw_plate_metrics",
    "teams",
    "players",
    "stadiums",
    "games",
    "game_roster_entries",
    "innings",
    "plate_appearances",
    "pa_events",
    "pitches",
    "pitch_tracking",
    "batted_ball_results",
    "baserunning_events",
    "review_events",
    "substitution_events",
]


def _normalize_source_path(path_text: str) -> str:
    return path_text.replace("\\", "/")


def _make_issue(issue_type: str, scope: str, code: str, message: str, *, path: str | None = None) -> dict[str, Any]:
    issue = {
        "type": issue_type,
        "scope": scope,
        "code": code,
        "message": message,
    }
    if path:
        issue["path"] = path
    return issue


def _parse_expected_actual(message: str) -> tuple[int, int] | None:
    match = re.search(r"expected\s+(-?\d+),\s+got\s+(-?\d+)", message)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _is_source_derived_issue(issue: dict[str, Any], source_problem_paths: set[str]) -> bool:
    path = issue.get("path")
    if not path or path not in source_problem_paths:
        return False
    code = issue.get("code", "")
    if code == "inning_summary_mismatch":
        return True
    if code in {"terminal_pa_count_mismatch", "partial_pa_count_mismatch", "empty_result_text_mismatch"}:
        return True
    if code.startswith("count_mismatch:plate_appearances"):
        return True
    if code.startswith("batter_total_mismatch:"):
        return True
    if code.startswith("pitcher_total_mismatch:"):
        return True
    return False


def _state_bool_expr(field_name: str) -> str:
    return f"""CASE
        WHEN raw_payload->'currentGameState'->>'{field_name}' IS NULL THEN FALSE
        WHEN raw_payload->'currentGameState'->>'{field_name}' IN ('', '0', 'false', 'False') THEN FALSE
        ELSE TRUE
    END"""


def _aggregate_table_expectations(entries: list[dict[str, Any]]) -> dict[str, int]:
    expected = Counter({table_name: 0 for table_name in TABLE_NAMES})
    for entry in entries:
        for table_name, count in (entry.get("expected_counts") or {}).items():
            expected[table_name] += int(count)

    expected["teams"] = len({entry["home_team_code"] for entry in entries} | {entry["away_team_code"] for entry in entries})
    expected["players"] = len({player_id for entry in entries for player_id in entry.get("expected_player_ids", [])})
    expected["stadiums"] = len({entry["stadium_name"] for entry in entries if entry.get("stadium_name")})
    return dict(expected)


def _expected_pitch_tracking_gap(entry: dict[str, Any]) -> int:
    expected_counts = entry.get("expected_counts") or {}
    expected_pitches = int(expected_counts.get("pitches", 0) or 0)
    expected_pitch_tracking = int(expected_counts.get("pitch_tracking", 0) or 0)
    return max(expected_pitches - expected_pitch_tracking, 0)


BATTER_VALIDATION_STATS = ("pa", "ab", "hit", "bb", "ibb", "so", "hbp", "sh", "sf", "ci", "roe", "fc", "dp", "hr")
PITCHER_VALIDATION_STATS = ("bf", "pa", "ab", "hit", "bb", "ibb", "so", "hbp", "hr", "bbhp")


def _pitcher_stats_from_batter_delta(delta: dict[str, int]) -> dict[str, int]:
    return {
        "bf": int(delta.get("pa", 0) or 0),
        "pa": int(delta.get("pa", 0) or 0),
        "ab": int(delta.get("ab", 0) or 0),
        "hit": int(delta.get("hit", 0) or 0),
        "bb": int(delta.get("bb", 0) or 0),
        "ibb": int(delta.get("ibb", 0) or 0),
        "so": int(delta.get("so", 0) or 0),
        "hbp": int(delta.get("hbp", 0) or 0),
        "hr": int(delta.get("hr", 0) or 0),
        "bbhp": int((delta.get("bb", 0) or 0) + (delta.get("hbp", 0) or 0)),
    }


def _compare_side_totals(
    issues: list[dict[str, Any]],
    *,
    path: str,
    prefix: str,
    stats: tuple[str, ...],
    expected: dict[str, dict[str, dict[str, int]]] | dict[str, dict[str, int]],
    actual: dict[str, dict[str, dict[str, int]]] | dict[str, dict[str, int]],
) -> None:
    for side in ("home", "away"):
        expected_side = expected.get(side, {}) if isinstance(expected, dict) else {}
        actual_side = actual.get(side, {}) if isinstance(actual, dict) else {}
        expected_player_ids = set(expected_side.keys())
        actual_player_ids = set(actual_side.keys())
        for player_id in sorted(expected_player_ids | actual_player_ids):
            expected_row = expected_side.get(player_id, {})
            actual_row = actual_side.get(player_id, {})
            for stat_name in stats:
                expected_value = int(expected_row.get(stat_name, 0) or 0)
                actual_value = int(actual_row.get(stat_name, 0) or 0)
                if expected_value != actual_value:
                    issues.append(
                        _make_issue(
                            "normalized_logic",
                            "aggregate",
                            f"{prefix}:{side}:{player_id}:{stat_name}",
                            f"{side} {player_id} {stat_name} expected {expected_value}, got {actual_value}",
                            path=path,
                        )
                    )


def _fetch_global_actual_counts(cur: psycopg.Cursor) -> dict[str, int]:
    actual: dict[str, int] = {}
    for table_name in TABLE_NAMES:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        actual[table_name] = cur.fetchone()[0]
    return actual


def _validate_game_metadata(cur: psycopg.Cursor, entry: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None, int | None]:
    issues: list[dict[str, Any]] = []
    path = entry["path"]
    cur.execute(
        """
        SELECT
            rg.raw_game_id,
            rg.source_file_hash,
            rg.raw_json IS NOT NULL AS has_raw_json,
            REPLACE(rg.source_file_name, E'\\\\', '/') AS raw_source_file_name,
            g.game_id,
            REPLACE(g.source_file_name, E'\\\\', '/') AS game_source_file_name,
            g.source_game_key,
            g.game_date::text,
            g.game_time,
            g.round_no,
            g.game_flag,
            g.is_postseason,
            g.cancel_flag,
            g.status_code,
            ht.team_code AS home_team_code,
            at.team_code AS away_team_code,
            s.stadium_name
        FROM games g
        JOIN raw_games rg ON rg.raw_game_id = g.raw_game_id
        LEFT JOIN teams ht ON ht.team_id = g.home_team_id
        LEFT JOIN teams at ON at.team_id = g.away_team_id
        LEFT JOIN stadiums s ON s.stadium_id = g.stadium_id
        WHERE REPLACE(g.source_file_name, E'\\\\', '/') = %s
        """,
        (path,),
    )
    rows = cur.fetchall()
    if not rows:
        issues.append(_make_issue("raw_ingest", "game", "missing_game_row", "games/raw_games row not found", path=path))
        return issues, None, None
    if len(rows) != 1:
        issues.append(_make_issue("raw_ingest", "game", "duplicate_game_row", f"expected 1 row, found {len(rows)}", path=path))
        return issues, None, None

    row = rows[0]
    raw_game_id = row[0]
    game_id = row[4]
    comparisons = [
        ("source_file_hash", row[1], entry["source_file_hash"]),
        ("raw_source_file_name", row[3], path),
        ("game_source_file_name", row[5], path),
        ("source_game_key", row[6], entry["source_game_key"]),
        ("game_date", row[7], entry["game_date"]),
        ("game_time", row[8], entry["game_time"]),
        ("round_no", row[9], entry["round_no"]),
        ("game_flag", row[10], entry["game_flag"]),
        ("is_postseason", row[11], entry["is_postseason"]),
        ("cancel_flag", row[12], entry["cancel_flag"]),
        ("status_code", row[13], entry["status_code"]),
        ("home_team_code", row[14], entry["home_team_code"]),
        ("away_team_code", row[15], entry["away_team_code"]),
        ("stadium_name", row[16], entry["stadium_name"]),
    ]
    if not row[2]:
        issues.append(_make_issue("raw_ingest", "game", "missing_raw_json", "raw_json is NULL", path=path))
    for field_name, actual_value, expected_value in comparisons:
        if actual_value != expected_value:
            issues.append(
                _make_issue(
                    "raw_ingest",
                    "game",
                    f"metadata_mismatch:{field_name}",
                    f"{field_name} expected {expected_value!r}, got {actual_value!r}",
                    path=path,
                )
            )
    return issues, raw_game_id, game_id


def _validate_raw_layer(cur: psycopg.Cursor, entry: dict[str, Any], raw_game_id: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    path = entry["path"]
    cur.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM raw_relay_blocks WHERE raw_game_id = %(raw_game_id)s) AS raw_relay_blocks,
            (SELECT COUNT(*)
             FROM raw_text_events rte
             JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rte.raw_block_id
             WHERE rrb.raw_game_id = %(raw_game_id)s) AS raw_text_events,
            (SELECT COUNT(*)
             FROM raw_pitch_tracks rpt
             JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rpt.raw_block_id
             WHERE rrb.raw_game_id = %(raw_game_id)s) AS raw_pitch_tracks,
            (SELECT COUNT(*)
             FROM raw_plate_metrics rpm
             JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rpm.raw_block_id
             WHERE rrb.raw_game_id = %(raw_game_id)s) AS raw_plate_metrics,
            (SELECT COUNT(*)
             FROM raw_relay_blocks
             WHERE raw_game_id = %(raw_game_id)s
               AND (
                    title IS DISTINCT FROM raw_block_json->>'title'
                 OR title_style IS DISTINCT FROM raw_block_json->>'titleStyle'
                 OR block_no IS DISTINCT FROM NULLIF(raw_block_json->>'no', '')::int
                 OR inning_no IS DISTINCT FROM NULLIF(raw_block_json->>'inn', '')::int
                 OR home_or_away IS DISTINCT FROM raw_block_json->>'homeOrAway'
                 OR status_code IS DISTINCT FROM raw_block_json->>'statusCode'
               )) AS raw_block_mismatches,
            (SELECT COUNT(*)
             FROM raw_text_events rte
             JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rte.raw_block_id
             WHERE rrb.raw_game_id = %(raw_game_id)s
               AND (
                    seqno IS DISTINCT FROM NULLIF(rte.raw_event_json->>'seqno', '')::int
                 OR type_code IS DISTINCT FROM NULLIF(rte.raw_event_json->>'type', '')::int
                 OR text IS DISTINCT FROM rte.raw_event_json->>'text'
                 OR pitch_num IS DISTINCT FROM NULLIF(rte.raw_event_json->>'pitchNum', '')::int
                 OR pitch_result IS DISTINCT FROM rte.raw_event_json->>'pitchResult'
                 OR pts_pitch_id IS DISTINCT FROM rte.raw_event_json->>'ptsPitchId'
                 OR stuff_text IS DISTINCT FROM rte.raw_event_json->>'stuff'
               )) AS raw_text_mismatches,
            (SELECT COUNT(*)
             FROM raw_pitch_tracks rpt
             JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rpt.raw_block_id
             WHERE rrb.raw_game_id = %(raw_game_id)s
               AND (
                    pitch_id IS DISTINCT FROM rpt.raw_track_json->>'pitchId'
                 OR inn IS DISTINCT FROM NULLIF(rpt.raw_track_json->>'inn', '')::int
                 OR ballcount IS DISTINCT FROM rpt.raw_track_json->>'ballcount'
                 OR stance IS DISTINCT FROM rpt.raw_track_json->>'stance'
               )) AS raw_track_mismatches
        """,
        {"raw_game_id": raw_game_id},
    )
    row = cur.fetchone()
    actual_counts = {
        "raw_relay_blocks": row[0],
        "raw_text_events": row[1],
        "raw_pitch_tracks": row[2],
        "raw_plate_metrics": row[3],
    }
    for table_name, expected_count in (entry.get("expected_counts") or {}).items():
        if table_name in actual_counts and actual_counts[table_name] != expected_count:
            issues.append(
                _make_issue(
                    "raw_ingest",
                    "raw",
                    f"count_mismatch:{table_name}",
                    f"{table_name} expected {expected_count}, got {actual_counts[table_name]}",
                    path=path,
                )
            )
    if row[4]:
        issues.append(_make_issue("raw_ingest", "raw", "raw_block_mismatch", f"raw block field mismatches={row[4]}", path=path))
    if row[5]:
        issues.append(_make_issue("raw_ingest", "raw", "raw_text_mismatch", f"raw text field mismatches={row[5]}", path=path))
    if row[6]:
        issues.append(_make_issue("raw_ingest", "raw", "raw_track_mismatch", f"raw pitch track field mismatches={row[6]}", path=path))
    return issues


def _validate_normalized_game(cur: psycopg.Cursor, entry: dict[str, Any], game_id: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    path = entry["path"]

    cur.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM game_roster_entries WHERE game_id = %(game_id)s) AS roster_count,
            (SELECT COUNT(*) FROM innings WHERE game_id = %(game_id)s) AS innings_count,
            (SELECT COUNT(*) FROM plate_appearances WHERE game_id = %(game_id)s) AS pa_count,
            (SELECT COUNT(*) FROM pa_events WHERE game_id = %(game_id)s) AS pa_event_count,
            (SELECT COUNT(*) FROM pitches WHERE game_id = %(game_id)s) AS pitch_count,
            (SELECT COUNT(*)
             FROM pitch_tracking pt
             JOIN pitches p ON p.pitch_id = pt.pitch_id
             WHERE p.game_id = %(game_id)s) AS pitch_tracking_count,
            (SELECT COUNT(*)
             FROM batted_ball_results bbr
             JOIN plate_appearances pa ON pa.pa_id = bbr.pa_id
             WHERE pa.game_id = %(game_id)s) AS batted_ball_results_count,
            (SELECT COUNT(*) FROM baserunning_events WHERE game_id = %(game_id)s) AS baserunning_count,
            (SELECT COUNT(*) FROM review_events WHERE game_id = %(game_id)s) AS review_count,
            (SELECT COUNT(*) FROM substitution_events WHERE game_id = %(game_id)s) AS substitution_count,
            (SELECT COUNT(*) FROM pa_events WHERE game_id = %(game_id)s AND (home_score IS NULL OR away_score IS NULL)) AS score_null_count,
            (SELECT COUNT(*) FROM pa_events WHERE game_id = %(game_id)s AND (home_hits IS NULL OR away_hits IS NULL OR home_errors IS NULL OR away_errors IS NULL)) AS scoreboard_null_count,
            (SELECT COUNT(*) FROM baserunning_events WHERE game_id = %(game_id)s AND runner_name_raw IS NULL) AS baserunning_runner_null_count,
            (SELECT COUNT(*) FROM substitution_events WHERE game_id = %(game_id)s AND (in_player_id IS NULL OR out_player_id IS NULL)) AS substitution_player_null_count,
            (SELECT COUNT(*) FROM review_events WHERE game_id = %(game_id)s AND review_target_text IS NULL) AS review_target_null_count
        """,
        {"game_id": game_id},
    )
    row = cur.fetchone()
    actual_counts = {
        "game_roster_entries": row[0],
        "innings": row[1],
        "plate_appearances": row[2],
        "pa_events": row[3],
        "pitches": row[4],
        "pitch_tracking": row[5],
        "batted_ball_results": row[6],
        "baserunning_events": row[7],
        "review_events": row[8],
        "substitution_events": row[9],
    }
    for table_name, expected_count in (entry.get("expected_counts") or {}).items():
        if table_name in actual_counts and actual_counts[table_name] != expected_count:
            issues.append(
                _make_issue(
                    "normalized_logic",
                    "normalized",
                    f"count_mismatch:{table_name}",
                    f"{table_name} expected {expected_count}, got {actual_counts[table_name]}",
                    path=path,
                )
            )
    if row[10]:
        issues.append(_make_issue("normalized_logic", "normalized", "score_nulls", f"pa_events with NULL score fields={row[10]}", path=path))
    if row[11]:
        issues.append(_make_issue("normalized_logic", "normalized", "scoreboard_nulls", f"pa_events with NULL hit/error fields={row[11]}", path=path))
    if row[12]:
        issues.append(_make_issue("normalized_logic", "normalized", "baserunning_runner_nulls", f"baserunning_events with NULL runner_name_raw={row[12]}", path=path))
    expected_substitution_nulls = int((entry.get("expected_null_counts") or {}).get("substitution_missing_player_id_count", 0))
    if row[13] != expected_substitution_nulls:
        issues.append(
            _make_issue(
                "normalized_logic",
                "normalized",
                "substitution_player_nulls",
                f"substitution_events missing player ids expected {expected_substitution_nulls}, got {row[13]}",
                path=path,
            )
        )
    if row[14]:
        issues.append(_make_issue("normalized_logic", "normalized", "review_target_nulls", f"review_events missing review_target_text={row[14]}", path=path))

    cur.execute(
        """
        SELECT COUNT(*), COALESCE(MAX(pa_seq_game), 0), COUNT(DISTINCT pa_seq_game)
        FROM plate_appearances
        WHERE game_id = %s
        """,
        (game_id,),
    )
    pa_count, pa_max_seq, pa_distinct = cur.fetchone()
    if pa_count and (pa_count != pa_max_seq or pa_count != pa_distinct):
        issues.append(_make_issue("normalized_logic", "normalized", "pa_seq_gap", f"PA sequence count={pa_count}, max={pa_max_seq}, distinct={pa_distinct}", path=path))

    cur.execute(
        """
        SELECT inning_id, COUNT(*), COALESCE(MAX(pa_seq_in_half), 0), COUNT(DISTINCT pa_seq_in_half), COALESCE(MIN(pa_seq_in_half), 0)
        FROM plate_appearances
        WHERE game_id = %s
        GROUP BY inning_id
        """,
        (game_id,),
    )
    for inning_id, count_rows, max_seq, distinct_seq, min_seq in cur.fetchall():
        if count_rows and (count_rows != max_seq or count_rows != distinct_seq or min_seq != 1):
            issues.append(_make_issue("normalized_logic", "normalized", "pa_seq_in_half_gap", f"inning_id={inning_id} count={count_rows}, max={max_seq}, distinct={distinct_seq}, min={min_seq}", path=path))

    cur.execute(
        """
        SELECT COUNT(*), COALESCE(MAX(event_seq_game), 0), COUNT(DISTINCT event_seq_game)
        FROM pa_events
        WHERE game_id = %s
        """,
        (game_id,),
    )
    event_count, event_max_seq, event_distinct = cur.fetchone()
    if event_count and (event_count != event_max_seq or event_count != event_distinct):
        issues.append(_make_issue("normalized_logic", "normalized", "event_seq_gap", f"event sequence count={event_count}, max={event_max_seq}, distinct={event_distinct}", path=path))

    cur.execute(
        f"""
        SELECT
            COUNT(*) FILTER (WHERE home_score IS DISTINCT FROM NULLIF(raw_payload->'currentGameState'->>'homeScore', '')::int),
            COUNT(*) FILTER (WHERE away_score IS DISTINCT FROM NULLIF(raw_payload->'currentGameState'->>'awayScore', '')::int),
            COUNT(*) FILTER (WHERE outs IS DISTINCT FROM NULLIF(raw_payload->'currentGameState'->>'out', '')::int),
            COUNT(*) FILTER (WHERE balls IS DISTINCT FROM NULLIF(raw_payload->'currentGameState'->>'ball', '')::int),
            COUNT(*) FILTER (WHERE strikes IS DISTINCT FROM NULLIF(raw_payload->'currentGameState'->>'strike', '')::int),
            COUNT(*) FILTER (WHERE base1_occupied IS DISTINCT FROM ({_state_bool_expr('base1')})),
            COUNT(*) FILTER (WHERE base2_occupied IS DISTINCT FROM ({_state_bool_expr('base2')})),
            COUNT(*) FILTER (WHERE base3_occupied IS DISTINCT FROM ({_state_bool_expr('base3')}))
        FROM pa_events
        WHERE game_id = %s
        """,
        (game_id,),
    )
    state_mismatches = cur.fetchone()
    state_fields = ["home_score", "away_score", "outs", "balls", "strikes", "base1", "base2", "base3"]
    for field_name, mismatch_count in zip(state_fields, state_mismatches):
        if mismatch_count:
            issues.append(_make_issue("normalized_logic", "normalized", f"state_mismatch:{field_name}", f"{field_name} mismatches={mismatch_count}", path=path))

    cur.execute(
        """
        SELECT home_score, away_score, home_hits, away_hits, home_errors, away_errors
        FROM pa_events
        WHERE game_id = %s
        ORDER BY event_seq_game DESC
        LIMIT 1
        """,
        (game_id,),
    )
    final_state = cur.fetchone()
    expected_scoreboard = entry.get("scoreboard") or {}
    if final_state:
        comparisons = [
            ("homeScore", final_state[0], expected_scoreboard.get("homeScore")),
            ("awayScore", final_state[1], expected_scoreboard.get("awayScore")),
            ("homeHit", final_state[2], expected_scoreboard.get("homeHit")),
            ("awayHit", final_state[3], expected_scoreboard.get("awayHit")),
            ("homeError", final_state[4], expected_scoreboard.get("homeError")),
            ("awayError", final_state[5], expected_scoreboard.get("awayError")),
        ]
        for field_name, actual_value, expected_value in comparisons:
            if expected_value is not None and actual_value != expected_value:
                issues.append(_make_issue("normalized_logic", "aggregate", f"scoreboard_mismatch:{field_name}", f"{field_name} expected {expected_value}, got {actual_value}", path=path))
    else:
        issues.append(_make_issue("normalized_logic", "aggregate", "missing_final_state", "no pa_events found for final scoreboard", path=path))

    cur.execute(
        """
        SELECT inning_no, half, runs_scored, hits_in_half, errors_in_half, walks_in_half
        FROM innings
        WHERE game_id = %s
        ORDER BY inning_no, half
        """,
        (game_id,),
    )
    actual_innings = [
        {
            "inning_no": row[0],
            "half": row[1],
            "runs_scored": row[2],
            "hits_in_half": row[3],
            "errors_in_half": row[4],
            "walks_in_half": row[5],
        }
        for row in cur.fetchall()
    ]
    expected_innings = [
        {
            "inning_no": row["inning_no"],
            "half": row["half"],
            "runs_scored": row["runs_scored"],
            "hits_in_half": row["hits_in_half"],
            "errors_in_half": row["errors_in_half"],
            "walks_in_half": row["walks_in_half"],
        }
        for row in entry.get("inning_expectations", [])
    ]
    if actual_innings != expected_innings:
        issues.append(_make_issue("normalized_logic", "aggregate", "inning_summary_mismatch", "innings summary rows do not match source expectations", path=path))

    cur.execute(
        """
        SELECT i.half, pa.batter_id, pa.pitcher_id, pa.result_text, COALESCE(pa.is_terminal, FALSE)
        FROM plate_appearances pa
        JOIN innings i ON i.inning_id = pa.inning_id
        WHERE pa.game_id = %s
        """,
        (game_id,),
    )
    actual_batter_team_totals = {"home": Counter(), "away": Counter()}
    actual_pitcher_team_totals = {"home": Counter(), "away": Counter()}
    actual_batter_totals_by_player: dict[str, dict[str, Counter]] = {"home": {}, "away": {}}
    actual_pitcher_totals_by_player: dict[str, dict[str, Counter]] = {"home": {}, "away": {}}
    expected_terminal_pa_count = int(entry.get("expected_terminal_plate_appearances", 0))
    expected_partial_pa_count = int(entry.get("expected_partial_plate_appearances", 0))
    empty_result_text_count = 0
    terminal_pa_count = 0
    nonterminal_pa_count = 0
    terminal_empty_result_text_count = 0
    nonterminal_with_result_text_count = 0
    terminal_missing_batter_id_count = 0
    terminal_missing_pitcher_id_count = 0
    for half, batter_id, pitcher_id, result_text, is_terminal in cur.fetchall():
        if is_terminal:
            terminal_pa_count += 1
        else:
            nonterminal_pa_count += 1
        if not result_text:
            empty_result_text_count += 1
            if is_terminal:
                terminal_empty_result_text_count += 1
            continue
        if not is_terminal:
            nonterminal_with_result_text_count += 1
        side = "away" if half == "top" else "home"
        defense_side = "home" if side == "away" else "away"
        delta = dict(classify_terminal_pa_text(result_text).stats)
        pitcher_delta = _pitcher_stats_from_batter_delta(delta)
        actual_batter_team_totals[side].update(delta)
        actual_pitcher_team_totals[defense_side].update(pitcher_delta)
        if batter_id:
            actual_batter_totals_by_player[side].setdefault(str(batter_id), Counter()).update(delta)
        elif is_terminal:
            terminal_missing_batter_id_count += 1
        if pitcher_id:
            actual_pitcher_totals_by_player[defense_side].setdefault(str(pitcher_id), Counter()).update(pitcher_delta)
        elif is_terminal:
            terminal_missing_pitcher_id_count += 1

    if terminal_pa_count != expected_terminal_pa_count:
        issues.append(
            _make_issue(
                "normalized_logic",
                "aggregate",
                "terminal_pa_count_mismatch",
                f"terminal plate_appearances expected {expected_terminal_pa_count}, got {terminal_pa_count}",
                path=path,
            )
        )
    if nonterminal_pa_count != expected_partial_pa_count:
        issues.append(
            _make_issue(
                "normalized_logic",
                "aggregate",
                "partial_pa_count_mismatch",
                f"partial plate_appearances expected {expected_partial_pa_count}, got {nonterminal_pa_count}",
                path=path,
            )
        )
    if empty_result_text_count != expected_partial_pa_count:
        issues.append(
            _make_issue(
                "normalized_logic",
                "aggregate",
                "empty_result_text_mismatch",
                f"empty result_text plate_appearances expected {expected_partial_pa_count}, got {empty_result_text_count}",
                path=path,
            )
        )
    if terminal_empty_result_text_count:
        issues.append(
            _make_issue(
                "normalized_logic",
                "aggregate",
                "terminal_pa_missing_result_text",
                f"terminal plate_appearances with empty result_text={terminal_empty_result_text_count}",
                path=path,
            )
        )
    if nonterminal_with_result_text_count:
        issues.append(
            _make_issue(
                "normalized_logic",
                "aggregate",
                "partial_pa_has_result_text",
                f"partial plate_appearances with non-empty result_text={nonterminal_with_result_text_count}",
                path=path,
            )
        )

    if terminal_missing_batter_id_count:
        issues.append(
            _make_issue(
                "normalized_logic",
                "aggregate",
                "terminal_pa_missing_batter_id",
                f"terminal plate_appearances with NULL batter_id={terminal_missing_batter_id_count}",
                path=path,
            )
        )
    if terminal_missing_pitcher_id_count:
        issues.append(
            _make_issue(
                "normalized_logic",
                "aggregate",
                "terminal_pa_missing_pitcher_id",
                f"terminal plate_appearances with NULL pitcher_id={terminal_missing_pitcher_id_count}",
                path=path,
            )
        )

    expected_batter_totals = entry.get("expected_batter_totals") or entry.get("relay_batter_totals") or {}
    expected_batter_by_player = entry.get("expected_batter_totals_by_player") or {"home": {}, "away": {}}
    actual_batter_with_team = {
        side: {
            "TEAM": dict(actual_batter_team_totals[side]),
            **{player_id: dict(row) for player_id, row in actual_batter_totals_by_player[side].items()},
        }
        for side in ("home", "away")
    }
    expected_batter_with_team = {
        side: {
            "TEAM": dict((expected_batter_totals or {}).get(side, {})),
            **{player_id: dict(row) for player_id, row in (expected_batter_by_player or {}).get(side, {}).items()},
        }
        for side in ("home", "away")
    }
    _compare_side_totals(
        issues,
        path=path,
        prefix="batter_total_mismatch",
        stats=BATTER_VALIDATION_STATS,
        expected=expected_batter_with_team,
        actual=actual_batter_with_team,
    )

    expected_pitcher_totals = entry.get("expected_pitcher_totals") or entry.get("record_pitcher_totals") or {}
    expected_pitcher_by_player = entry.get("expected_pitcher_totals_by_player") or {"home": {}, "away": {}}
    actual_pitcher_with_team = {
        side: {
            "TEAM": dict(actual_pitcher_team_totals[side]),
            **{player_id: dict(row) for player_id, row in actual_pitcher_totals_by_player[side].items()},
        }
        for side in ("home", "away")
    }
    expected_pitcher_with_team = {
        side: {
            "TEAM": dict((expected_pitcher_totals or {}).get(side, {})),
            **{player_id: dict(row) for player_id, row in (expected_pitcher_by_player or {}).get(side, {}).items()},
        }
        for side in ("home", "away")
    }
    _compare_side_totals(
        issues,
        path=path,
        prefix="pitcher_total_mismatch",
        stats=PITCHER_VALIDATION_STATS,
        expected=expected_pitcher_with_team,
        actual=actual_pitcher_with_team,
    )

    cur.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE p.pa_id IS NULL OR p.event_id IS NULL OR p.inning_id IS NULL),
            COUNT(*) FILTER (WHERE pt.pitch_id IS NULL)
        FROM pitches p
        LEFT JOIN pitch_tracking pt ON pt.pitch_id = p.pitch_id
        WHERE p.game_id = %s
        """,
        (game_id,),
    )
    pitch_orphan_count, pitch_tracking_missing_count = cur.fetchone()
    if pitch_orphan_count:
        issues.append(_make_issue("normalized_logic", "normalized", "pitch_fk_nulls", f"pitches with NULL foreign keys={pitch_orphan_count}", path=path))
    expected_pitch_tracking_gap = _expected_pitch_tracking_gap(entry)
    if pitch_tracking_missing_count != expected_pitch_tracking_gap:
        issues.append(
            _make_issue(
                "normalized_logic",
                "normalized",
                "pitch_tracking_gap_mismatch",
                f"pitches without pitch_tracking expected {expected_pitch_tracking_gap}, got {pitch_tracking_missing_count}",
                path=path,
            )
        )

    cur.execute(
        """
        SELECT
            (SELECT COUNT(*)
             FROM baserunning_events be
             JOIN pa_events pe ON pe.event_id = be.event_id
             WHERE be.game_id = %s
               AND (be.pa_id IS DISTINCT FROM pe.pa_id OR be.inning_id IS DISTINCT FROM pe.inning_id)) AS baserunning_link_mismatch,
            (SELECT COUNT(*)
             FROM review_events re
             JOIN pa_events pe ON pe.event_id = re.event_id
             WHERE re.game_id = %s
               AND (re.pa_id IS DISTINCT FROM pe.pa_id OR re.inning_id IS DISTINCT FROM pe.inning_id)) AS review_link_mismatch,
            (SELECT COUNT(*)
             FROM substitution_events se
             JOIN pa_events pe ON pe.event_id = se.event_id
             WHERE se.game_id = %s
               AND (se.pa_id IS DISTINCT FROM pe.pa_id OR se.inning_id IS DISTINCT FROM pe.inning_id)) AS substitution_link_mismatch
        """,
        (game_id, game_id, game_id),
    )
    link_mismatches = cur.fetchone()
    link_names = ["baserunning_link_mismatch", "review_link_mismatch", "substitution_link_mismatch"]
    for link_name, mismatch_count in zip(link_names, link_mismatches):
        if mismatch_count:
            issues.append(_make_issue("normalized_logic", "normalized", link_name, f"{link_name}={mismatch_count}", path=path))
    return issues


def validate_loaded_entries(conn: psycopg.Connection, entries: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    source_issues: list[dict[str, Any]] = []
    source_problem_paths = {
        entry["path"]
        for entry in entries
        if not (entry.get("source_validation") or {}).get("ok", True)
    }
    with conn.cursor() as cur:
        expected_counts = _aggregate_table_expectations(entries)
        actual_counts = _fetch_global_actual_counts(cur)
        table_counts: dict[str, dict[str, int]] = {}
        for table_name in TABLE_NAMES:
            table_counts[table_name] = {
                "expected": expected_counts.get(table_name, 0),
                "actual": actual_counts.get(table_name, 0),
            }
            if table_counts[table_name]["expected"] != table_counts[table_name]["actual"]:
                issues.append(
                    _make_issue(
                        "raw_ingest" if table_name.startswith("raw_") else "normalized_logic",
                        "global",
                        f"table_count_mismatch:{table_name}",
                        f"{table_name} expected {table_counts[table_name]['expected']}, got {table_counts[table_name]['actual']}",
                    )
                )

        cur.execute("SELECT COUNT(*), COUNT(DISTINCT source_file_hash), COUNT(DISTINCT REPLACE(source_file_name, E'\\\\', '/')) FROM raw_games")
        raw_game_count, raw_hash_count, raw_name_count = cur.fetchone()
        if raw_game_count != raw_hash_count:
            issues.append(_make_issue("raw_ingest", "global", "raw_hash_duplicate", f"raw_games count={raw_game_count}, distinct hashes={raw_hash_count}"))
        if raw_game_count != raw_name_count:
            issues.append(_make_issue("raw_ingest", "global", "raw_name_duplicate", f"raw_games count={raw_game_count}, distinct file names={raw_name_count}"))

        for entry in entries:
            path = entry["path"]
            source_validation = entry.get("source_validation") or {}
            for message in source_validation.get("issues", []):
                source_issues.append(_make_issue("source_json", "source", "source_consistency_issue", message, path=path))

            metadata_issues, raw_game_id, game_id = _validate_game_metadata(cur, entry)
            issues.extend(metadata_issues)
            if raw_game_id is None or game_id is None:
                continue
            issues.extend(_validate_raw_layer(cur, entry, raw_game_id))
            issues.extend(_validate_normalized_game(cur, entry, game_id))

    source_table_diffs = Counter()
    remaining_issues: list[dict[str, Any]] = []
    for issue in issues:
        if _is_source_derived_issue(issue, source_problem_paths):
            source_issues.append(
                _make_issue(
                    "source_json",
                    issue.get("scope", "source"),
                    issue.get("code", "source_derived_issue"),
                    issue.get("message", ""),
                    path=issue.get("path"),
                )
            )
            if issue.get("code", "").startswith("count_mismatch:"):
                parsed = _parse_expected_actual(issue.get("message", ""))
                if parsed:
                    expected_value, actual_value = parsed
                    table_name = issue["code"].split(":", 1)[1]
                    source_table_diffs[table_name] += actual_value - expected_value
            continue
        remaining_issues.append(issue)

    issues = []
    for issue in remaining_issues:
        code = issue.get("code", "")
        if code.startswith("table_count_mismatch:"):
            parsed = _parse_expected_actual(issue.get("message", ""))
            table_name = code.split(":", 1)[1]
            if parsed:
                expected_value, actual_value = parsed
                if actual_value - expected_value == source_table_diffs.get(table_name, 0):
                    source_issues.append(
                        _make_issue(
                            "source_json",
                            issue.get("scope", "source"),
                            code,
                            issue.get("message", ""),
                            path=issue.get("path"),
                        )
                    )
                    continue
        issues.append(issue)

    issue_type_counter = Counter(issue["type"] for issue in issues)
    source_type_counter = Counter(issue["type"] for issue in source_issues)
    return {
        "ok": not issues,
        "loaded_game_count": len(entries),
        "table_counts": table_counts,
        "blocking_issue_count": len(issues),
        "source_issue_count": len(source_issues),
        "blocking_issue_types": dict(issue_type_counter),
        "source_issue_types": dict(source_type_counter),
        "blocking_issues": issues,
        "source_issues": source_issues,
    }


def _validate_single_entry(dsn: str, entry: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entry_issues: list[dict[str, Any]] = []
    entry_source_issues: list[dict[str, Any]] = []
    path = entry["path"]
    source_validation = entry.get("source_validation") or {}
    for message in source_validation.get("issues", []):
        entry_source_issues.append(_make_issue("source_json", "source", "source_consistency_issue", message, path=path))

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            metadata_issues, raw_game_id, game_id = _validate_game_metadata(cur, entry)
            entry_issues.extend(metadata_issues)
            if raw_game_id is not None and game_id is not None:
                entry_issues.extend(_validate_raw_layer(cur, entry, raw_game_id))
                entry_issues.extend(_validate_normalized_game(cur, entry, game_id))
    return entry_issues, entry_source_issues


def validate_loaded_entries_parallel(
    dsn: str,
    entries: list[dict[str, Any]],
    *,
    workers: int = 4,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    source_issues: list[dict[str, Any]] = []
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            expected_counts = _aggregate_table_expectations(entries)
            actual_counts = _fetch_global_actual_counts(cur)
            table_counts: dict[str, dict[str, int]] = {}
            for table_name in TABLE_NAMES:
                table_counts[table_name] = {
                    "expected": expected_counts.get(table_name, 0),
                    "actual": actual_counts.get(table_name, 0),
                }
                if table_counts[table_name]["expected"] != table_counts[table_name]["actual"]:
                    issues.append(
                        _make_issue(
                            "raw_ingest" if table_name.startswith("raw_") else "normalized_logic",
                            "global",
                            f"table_count_mismatch:{table_name}",
                            f"{table_name} expected {table_counts[table_name]['expected']}, got {table_counts[table_name]['actual']}",
                        )
                    )

            cur.execute("SELECT COUNT(*), COUNT(DISTINCT source_file_hash), COUNT(DISTINCT REPLACE(source_file_name, E'\\\\', '/')) FROM raw_games")
            raw_game_count, raw_hash_count, raw_name_count = cur.fetchone()
            if raw_game_count != raw_hash_count:
                issues.append(_make_issue("raw_ingest", "global", "raw_hash_duplicate", f"raw_games count={raw_game_count}, distinct hashes={raw_hash_count}"))
            if raw_game_count != raw_name_count:
                issues.append(_make_issue("raw_ingest", "global", "raw_name_duplicate", f"raw_games count={raw_game_count}, distinct file names={raw_name_count}"))

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        for entry_issues, entry_source_issues in executor.map(lambda item: _validate_single_entry(dsn, item), entries):
            issues.extend(entry_issues)
            source_issues.extend(entry_source_issues)

    source_problem_paths = {
        entry["path"]
        for entry in entries
        if not (entry.get("source_validation") or {}).get("ok", True)
    }
    source_table_diffs = Counter()
    remaining_issues: list[dict[str, Any]] = []
    for issue in issues:
        if _is_source_derived_issue(issue, source_problem_paths):
            source_issues.append(
                _make_issue(
                    "source_json",
                    issue.get("scope", "source"),
                    issue.get("code", "source_derived_issue"),
                    issue.get("message", ""),
                    path=issue.get("path"),
                )
            )
            if issue.get("code", "").startswith("count_mismatch:"):
                parsed = _parse_expected_actual(issue.get("message", ""))
                if parsed:
                    expected_value, actual_value = parsed
                    table_name = issue["code"].split(":", 1)[1]
                    source_table_diffs[table_name] += actual_value - expected_value
            continue
        remaining_issues.append(issue)

    issues = []
    for issue in remaining_issues:
        code = issue.get("code", "")
        if code.startswith("table_count_mismatch:"):
            parsed = _parse_expected_actual(issue.get("message", ""))
            table_name = code.split(":", 1)[1]
            if parsed:
                expected_value, actual_value = parsed
                if actual_value - expected_value == source_table_diffs.get(table_name, 0):
                    source_issues.append(
                        _make_issue(
                            "source_json",
                            issue.get("scope", "source"),
                            code,
                            issue.get("message", ""),
                            path=issue.get("path"),
                        )
                    )
                    continue
        issues.append(issue)

    issue_type_counter = Counter(issue["type"] for issue in issues)
    source_type_counter = Counter(issue["type"] for issue in source_issues)
    return {
        "ok": not issues,
        "loaded_game_count": len(entries),
        "table_counts": table_counts,
        "blocking_issue_count": len(issues),
        "source_issue_count": len(source_issues),
        "blocking_issue_types": dict(issue_type_counter),
        "source_issue_types": dict(source_type_counter),
        "blocking_issues": issues,
        "source_issues": source_issues,
    }
