from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import json
from pathlib import Path
import re
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from check_data import classify_pa_text
from src.kbo_ingest.validation import TABLE_NAMES, _aggregate_table_expectations, _expected_pitch_tracking_gap


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk full-manifest validator for KBO PostgreSQL data")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report-json", required=True)
    return parser.parse_args()


def normalize_path(path_text: str) -> str:
    return path_text.replace("\\", "/")


def make_issue(issue_type: str, scope: str, code: str, message: str, *, path: str | None = None) -> dict:
    issue = {"type": issue_type, "scope": scope, "code": code, "message": message}
    if path:
        issue["path"] = path
    return issue


def parse_expected_actual(message: str) -> tuple[int, int] | None:
    match = re.search(r"expected\s+(-?\d+),\s+got\s+(-?\d+)", message)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def bulk_count_map(cur: psycopg.Cursor, sql: str) -> dict[int, int]:
    cur.execute(sql)
    return {int(key): int(value) for key, value in cur.fetchall()}


def write_markdown_report(report: dict, report_path: Path) -> None:
    lines = [
        "# KBO Bulk Validation Report",
        "",
        f"- Loaded games: {report.get('loaded_game_count', 0)}",
        f"- Blocking issues: {report.get('blocking_issue_count', 0)}",
        f"- Source issues: {report.get('source_issue_count', 0)}",
        "",
        "## Table Counts",
        "",
        "| Table | Expected | Actual |",
        "| --- | ---: | ---: |",
    ]
    for table_name, counts in report.get("table_counts", {}).items():
        lines.append(f"| {table_name} | {counts['expected']} | {counts['actual']} |")

    lines.extend(["", "## Blocking Issues", ""])
    blocking_issues = report.get("blocking_issues", [])[:50]
    if blocking_issues:
        for issue in blocking_issues:
            lines.append(f"- [{issue['type']}] {issue.get('path', issue['scope'])}: {issue['message']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Source Issues", ""])
    source_issues = report.get("source_issues", [])[:50]
    if source_issues:
        for issue in source_issues:
            lines.append(f"- {issue.get('path', issue['scope'])}: {issue['message']}")
    else:
        lines.append("- None")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    entries = manifest["entries"]
    entry_by_path = {entry["path"]: entry for entry in entries}
    source_problem_paths = {
        entry["path"]
        for entry in entries
        if not (entry.get("source_validation") or {}).get("ok", True)
    }

    issues: list[dict] = []
    source_issues: list[dict] = []
    source_table_diffs = Counter()

    for entry in entries:
        for message in (entry.get("source_validation") or {}).get("issues", []):
            source_issues.append(make_issue("source_json", "source", "source_consistency_issue", message, path=entry["path"]))

    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            expected_counts = _aggregate_table_expectations(entries)
            actual_counts = {}
            for table_name in TABLE_NAMES:
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                actual_counts[table_name] = int(cur.fetchone()[0])

            table_counts = {
                table_name: {
                    "expected": expected_counts.get(table_name, 0),
                    "actual": actual_counts.get(table_name, 0),
                }
                for table_name in TABLE_NAMES
            }

            cur.execute("SELECT COUNT(*), COUNT(DISTINCT source_file_hash), COUNT(DISTINCT REPLACE(source_file_name, E'\\\\', '/')) FROM raw_games")
            raw_game_count, raw_hash_count, raw_name_count = cur.fetchone()
            if raw_game_count != raw_hash_count:
                issues.append(make_issue("raw_ingest", "global", "raw_hash_duplicate", f"raw_games count={raw_game_count}, distinct hashes={raw_hash_count}"))
            if raw_game_count != raw_name_count:
                issues.append(make_issue("raw_ingest", "global", "raw_name_duplicate", f"raw_games count={raw_game_count}, distinct file names={raw_name_count}"))

            cur.execute(
                """
                SELECT
                    rg.raw_game_id,
                    REPLACE(rg.source_file_name, E'\\\\', '/') AS path,
                    rg.source_file_hash,
                    rg.raw_json IS NOT NULL AS has_raw_json,
                    g.game_id,
                    REPLACE(g.source_file_name, E'\\\\', '/') AS game_path,
                    g.source_game_key,
                    g.game_date::text,
                    g.game_time,
                    g.round_no,
                    g.game_flag,
                    g.is_postseason,
                    g.cancel_flag,
                    g.status_code,
                    ht.team_code,
                    at.team_code,
                    s.stadium_name
                FROM games g
                JOIN raw_games rg ON rg.raw_game_id = g.raw_game_id
                LEFT JOIN teams ht ON ht.team_id = g.home_team_id
                LEFT JOIN teams at ON at.team_id = g.away_team_id
                LEFT JOIN stadiums s ON s.stadium_id = g.stadium_id
                """
            )
            metadata_rows = cur.fetchall()

            metadata_by_path: dict[str, dict] = {}
            raw_game_id_by_path: dict[str, int] = {}
            game_id_by_path: dict[str, int] = {}
            for row in metadata_rows:
                path = row[1]
                metadata_by_path[path] = {
                    "source_file_hash": row[2],
                    "has_raw_json": row[3],
                    "game_path": row[5],
                    "source_game_key": row[6],
                    "game_date": row[7],
                    "game_time": row[8],
                    "round_no": row[9],
                    "game_flag": row[10],
                    "is_postseason": row[11],
                    "cancel_flag": row[12],
                    "status_code": row[13],
                    "home_team_code": row[14],
                    "away_team_code": row[15],
                    "stadium_name": row[16],
                }
                raw_game_id_by_path[path] = int(row[0])
                game_id_by_path[path] = int(row[4])

            raw_relay_counts = bulk_count_map(cur, "SELECT raw_game_id, COUNT(*) FROM raw_relay_blocks GROUP BY raw_game_id")
            raw_text_counts = bulk_count_map(cur, "SELECT rrb.raw_game_id, COUNT(*) FROM raw_text_events rte JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rte.raw_block_id GROUP BY rrb.raw_game_id")
            raw_track_counts = bulk_count_map(cur, "SELECT rrb.raw_game_id, COUNT(*) FROM raw_pitch_tracks rpt JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rpt.raw_block_id GROUP BY rrb.raw_game_id")
            raw_metric_counts = bulk_count_map(cur, "SELECT rrb.raw_game_id, COUNT(*) FROM raw_plate_metrics rpm JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rpm.raw_block_id GROUP BY rrb.raw_game_id")

            cur.execute(
                """
                SELECT raw_game_id,
                       COUNT(*) FILTER (
                           WHERE title IS DISTINCT FROM raw_block_json->>'title'
                              OR title_style IS DISTINCT FROM raw_block_json->>'titleStyle'
                              OR block_no IS DISTINCT FROM NULLIF(raw_block_json->>'no', '')::int
                              OR inning_no IS DISTINCT FROM NULLIF(raw_block_json->>'inn', '')::int
                              OR home_or_away IS DISTINCT FROM raw_block_json->>'homeOrAway'
                              OR status_code IS DISTINCT FROM raw_block_json->>'statusCode'
                       )
                FROM raw_relay_blocks
                GROUP BY raw_game_id
                """
            )
            raw_block_mismatches = {int(game_id): int(count) for game_id, count in cur.fetchall()}

            cur.execute(
                """
                SELECT rrb.raw_game_id,
                       COUNT(*) FILTER (
                           WHERE seqno IS DISTINCT FROM NULLIF(rte.raw_event_json->>'seqno', '')::int
                              OR type_code IS DISTINCT FROM NULLIF(rte.raw_event_json->>'type', '')::int
                              OR text IS DISTINCT FROM rte.raw_event_json->>'text'
                              OR pitch_num IS DISTINCT FROM NULLIF(rte.raw_event_json->>'pitchNum', '')::int
                              OR pitch_result IS DISTINCT FROM rte.raw_event_json->>'pitchResult'
                              OR pts_pitch_id IS DISTINCT FROM rte.raw_event_json->>'ptsPitchId'
                              OR stuff_text IS DISTINCT FROM rte.raw_event_json->>'stuff'
                       )
                FROM raw_text_events rte
                JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rte.raw_block_id
                GROUP BY rrb.raw_game_id
                """
            )
            raw_text_mismatches = {int(game_id): int(count) for game_id, count in cur.fetchall()}

            cur.execute(
                """
                SELECT rrb.raw_game_id,
                       COUNT(*) FILTER (
                           WHERE pitch_id IS DISTINCT FROM rpt.raw_track_json->>'pitchId'
                              OR inn IS DISTINCT FROM NULLIF(rpt.raw_track_json->>'inn', '')::int
                              OR ballcount IS DISTINCT FROM rpt.raw_track_json->>'ballcount'
                              OR stance IS DISTINCT FROM rpt.raw_track_json->>'stance'
                       )
                FROM raw_pitch_tracks rpt
                JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rpt.raw_block_id
                GROUP BY rrb.raw_game_id
                """
            )
            raw_track_mismatches = {int(game_id): int(count) for game_id, count in cur.fetchall()}

            roster_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM game_roster_entries GROUP BY game_id")
            innings_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM innings GROUP BY game_id")
            pa_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM plate_appearances GROUP BY game_id")
            pa_event_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM pa_events GROUP BY game_id")
            pitch_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM pitches GROUP BY game_id")
            pitch_tracking_counts = bulk_count_map(cur, "SELECT p.game_id, COUNT(*) FROM pitch_tracking pt JOIN pitches p ON p.pitch_id = pt.pitch_id GROUP BY p.game_id")
            batted_ball_counts = bulk_count_map(cur, "SELECT pa.game_id, COUNT(*) FROM batted_ball_results b JOIN plate_appearances pa ON pa.pa_id = b.pa_id GROUP BY pa.game_id")
            baserunning_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM baserunning_events GROUP BY game_id")
            review_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM review_events GROUP BY game_id")
            substitution_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM substitution_events GROUP BY game_id")

            cur.execute(
                """
                SELECT
                    game_id,
                    COUNT(*) FILTER (WHERE home_score IS NULL OR away_score IS NULL),
                    COUNT(*) FILTER (WHERE home_hits IS NULL OR away_hits IS NULL OR home_errors IS NULL OR away_errors IS NULL)
                FROM pa_events
                GROUP BY game_id
                """
            )
            pa_null_counts = {int(game_id): (int(score_nulls), int(scoreboard_nulls)) for game_id, score_nulls, scoreboard_nulls in cur.fetchall()}

            baserunning_runner_null_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM baserunning_events WHERE runner_name_raw IS NULL GROUP BY game_id")
            substitution_null_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM substitution_events WHERE in_player_id IS NULL OR out_player_id IS NULL GROUP BY game_id")
            review_target_null_counts = bulk_count_map(cur, "SELECT game_id, COUNT(*) FROM review_events WHERE review_target_text IS NULL GROUP BY game_id")

            cur.execute(
                """
                SELECT game_id, COUNT(*), COALESCE(MAX(pa_seq_game), 0), COUNT(DISTINCT pa_seq_game)
                FROM plate_appearances
                GROUP BY game_id
                """
            )
            pa_seq_stats = {int(game_id): (int(count_rows), int(max_seq), int(distinct_seq)) for game_id, count_rows, max_seq, distinct_seq in cur.fetchall()}

            cur.execute(
                """
                SELECT game_id, inning_id, COUNT(*), COALESCE(MAX(pa_seq_in_half), 0), COUNT(DISTINCT pa_seq_in_half), COALESCE(MIN(pa_seq_in_half), 0)
                FROM plate_appearances
                GROUP BY game_id, inning_id
                """
            )
            pa_seq_in_half_stats: dict[int, list[tuple[int, int, int, int, int]]] = defaultdict(list)
            for game_id, inning_id, count_rows, max_seq, distinct_seq, min_seq in cur.fetchall():
                pa_seq_in_half_stats[int(game_id)].append((int(inning_id), int(count_rows), int(max_seq), int(distinct_seq), int(min_seq)))

            cur.execute(
                """
                SELECT game_id, COUNT(*), COALESCE(MAX(event_seq_game), 0), COUNT(DISTINCT event_seq_game)
                FROM pa_events
                GROUP BY game_id
                """
            )
            pa_event_seq_stats = {int(game_id): (int(count_rows), int(max_seq), int(distinct_seq)) for game_id, count_rows, max_seq, distinct_seq in cur.fetchall()}

            cur.execute(
                """
                SELECT game_id, inning_no, half, runs_scored, hits_in_half, errors_in_half, walks_in_half
                FROM innings
                ORDER BY game_id, inning_no, half
                """
            )
            innings_by_game: dict[int, list[dict]] = defaultdict(list)
            for game_id, inning_no, half, runs_scored, hits_in_half, errors_in_half, walks_in_half in cur.fetchall():
                innings_by_game[int(game_id)].append(
                    {
                        "inning_no": int(inning_no),
                        "half": half,
                        "runs_scored": runs_scored,
                        "hits_in_half": hits_in_half,
                        "errors_in_half": errors_in_half,
                        "walks_in_half": walks_in_half,
                    }
                )

            cur.execute(
                """
                SELECT pa.game_id, i.half, COALESCE(pa.result_text, ''), COALESCE(pa.is_terminal, FALSE)
                FROM plate_appearances pa
                JOIN innings i ON i.inning_id = pa.inning_id
                """
            )
            batter_totals_by_game: dict[int, dict[str, Counter]] = defaultdict(lambda: {"home": Counter(), "away": Counter()})
            terminal_counts_by_game = Counter()
            partial_counts_by_game = Counter()
            empty_result_counts_by_game = Counter()
            for game_id, half, result_text, is_terminal in cur.fetchall():
                game_id = int(game_id)
                side = "away" if half == "top" else "home"
                if is_terminal:
                    terminal_counts_by_game[game_id] += 1
                else:
                    partial_counts_by_game[game_id] += 1
                if not result_text:
                    empty_result_counts_by_game[game_id] += 1
                    continue
                batter_totals_by_game[game_id][side].update(classify_pa_text(result_text))

            cur.execute(
                """
                SELECT
                    p.game_id,
                    COUNT(*) FILTER (WHERE p.pa_id IS NULL OR p.event_id IS NULL OR p.inning_id IS NULL),
                    COUNT(*) FILTER (WHERE pt.pitch_id IS NULL)
                FROM pitches p
                LEFT JOIN pitch_tracking pt ON pt.pitch_id = p.pitch_id
                GROUP BY p.game_id
                """
            )
            pitch_link_counts = {int(game_id): (int(orphan_count), int(missing_tracking)) for game_id, orphan_count, missing_tracking in cur.fetchall()}

            cur.execute(
                """
                SELECT
                    be.game_id,
                    COUNT(*) FILTER (WHERE be.pa_id IS DISTINCT FROM pe.pa_id OR be.inning_id IS DISTINCT FROM pe.inning_id)
                FROM baserunning_events be
                JOIN pa_events pe ON pe.event_id = be.event_id
                GROUP BY be.game_id
                """
            )
            baserunning_link_mismatches = {int(game_id): int(count) for game_id, count in cur.fetchall()}
            cur.execute(
                """
                SELECT
                    re.game_id,
                    COUNT(*) FILTER (WHERE re.pa_id IS DISTINCT FROM pe.pa_id OR re.inning_id IS DISTINCT FROM pe.inning_id)
                FROM review_events re
                JOIN pa_events pe ON pe.event_id = re.event_id
                GROUP BY re.game_id
                """
            )
            review_link_mismatches = {int(game_id): int(count) for game_id, count in cur.fetchall()}
            cur.execute(
                """
                SELECT
                    se.game_id,
                    COUNT(*) FILTER (WHERE se.pa_id IS DISTINCT FROM pe.pa_id OR se.inning_id IS DISTINCT FROM pe.inning_id)
                FROM substitution_events se
                JOIN pa_events pe ON pe.event_id = se.event_id
                GROUP BY se.game_id
                """
            )
            substitution_link_mismatches = {int(game_id): int(count) for game_id, count in cur.fetchall()}

    for path, entry in entry_by_path.items():
        metadata = metadata_by_path.get(path)
        if not metadata:
            issues.append(make_issue("raw_ingest", "game", "missing_game_row", "games/raw_games row not found", path=path))
            continue
        raw_game_id = raw_game_id_by_path[path]
        game_id = game_id_by_path[path]

        if not metadata["has_raw_json"]:
            issues.append(make_issue("raw_ingest", "game", "missing_raw_json", "raw_json is NULL", path=path))
        for field_name, actual_value, expected_value in [
            ("source_file_hash", metadata["source_file_hash"], entry["source_file_hash"]),
            ("game_path", metadata["game_path"], path),
            ("source_game_key", metadata["source_game_key"], entry["source_game_key"]),
            ("game_date", metadata["game_date"], entry["game_date"]),
            ("game_time", metadata["game_time"], entry["game_time"]),
            ("round_no", metadata["round_no"], entry["round_no"]),
            ("game_flag", metadata["game_flag"], entry["game_flag"]),
            ("is_postseason", metadata["is_postseason"], entry["is_postseason"]),
            ("cancel_flag", metadata["cancel_flag"], entry["cancel_flag"]),
            ("status_code", metadata["status_code"], entry["status_code"]),
            ("home_team_code", metadata["home_team_code"], entry["home_team_code"]),
            ("away_team_code", metadata["away_team_code"], entry["away_team_code"]),
            ("stadium_name", metadata["stadium_name"], entry["stadium_name"]),
        ]:
            if actual_value != expected_value:
                issues.append(make_issue("raw_ingest", "game", f"metadata_mismatch:{field_name}", f"{field_name} expected {expected_value!r}, got {actual_value!r}", path=path))

        raw_actuals = {
            "raw_relay_blocks": raw_relay_counts.get(raw_game_id, 0),
            "raw_text_events": raw_text_counts.get(raw_game_id, 0),
            "raw_pitch_tracks": raw_track_counts.get(raw_game_id, 0),
            "raw_plate_metrics": raw_metric_counts.get(raw_game_id, 0),
        }
        for table_name, actual_value in raw_actuals.items():
            expected_value = int((entry.get("expected_counts") or {}).get(table_name, 0))
            if actual_value != expected_value:
                issues.append(make_issue("raw_ingest", "raw", f"count_mismatch:{table_name}", f"{table_name} expected {expected_value}, got {actual_value}", path=path))
        if raw_block_mismatches.get(raw_game_id, 0):
            issues.append(make_issue("raw_ingest", "raw", "raw_block_mismatch", f"raw block field mismatches={raw_block_mismatches[raw_game_id]}", path=path))
        if raw_text_mismatches.get(raw_game_id, 0):
            issues.append(make_issue("raw_ingest", "raw", "raw_text_mismatch", f"raw text field mismatches={raw_text_mismatches[raw_game_id]}", path=path))
        if raw_track_mismatches.get(raw_game_id, 0):
            issues.append(make_issue("raw_ingest", "raw", "raw_track_mismatch", f"raw pitch track field mismatches={raw_track_mismatches[raw_game_id]}", path=path))

        normalized_actuals = {
            "game_roster_entries": roster_counts.get(game_id, 0),
            "innings": innings_counts.get(game_id, 0),
            "plate_appearances": pa_counts.get(game_id, 0),
            "pa_events": pa_event_counts.get(game_id, 0),
            "pitches": pitch_counts.get(game_id, 0),
            "pitch_tracking": pitch_tracking_counts.get(game_id, 0),
            "batted_ball_results": batted_ball_counts.get(game_id, 0),
            "baserunning_events": baserunning_counts.get(game_id, 0),
            "review_events": review_counts.get(game_id, 0),
            "substitution_events": substitution_counts.get(game_id, 0),
        }
        for table_name, actual_value in normalized_actuals.items():
            expected_value = int((entry.get("expected_counts") or {}).get(table_name, 0))
            if actual_value != expected_value:
                issues.append(make_issue("normalized_logic", "normalized", f"count_mismatch:{table_name}", f"{table_name} expected {expected_value}, got {actual_value}", path=path))

        score_nulls, scoreboard_nulls = pa_null_counts.get(game_id, (0, 0))
        if score_nulls:
            issues.append(make_issue("normalized_logic", "normalized", "score_nulls", f"pa_events with NULL score fields={score_nulls}", path=path))
        if scoreboard_nulls:
            issues.append(make_issue("normalized_logic", "normalized", "scoreboard_nulls", f"pa_events with NULL hit/error fields={scoreboard_nulls}", path=path))
        if baserunning_runner_null_counts.get(game_id, 0):
            issues.append(make_issue("normalized_logic", "normalized", "baserunning_runner_nulls", f"baserunning_events with NULL runner_name_raw={baserunning_runner_null_counts[game_id]}", path=path))
        expected_sub_nulls = int((entry.get("expected_null_counts") or {}).get("substitution_missing_player_id_count", 0))
        if substitution_null_counts.get(game_id, 0) != expected_sub_nulls:
            issues.append(make_issue("normalized_logic", "normalized", "substitution_player_nulls", f"substitution_events missing player ids expected {expected_sub_nulls}, got {substitution_null_counts.get(game_id, 0)}", path=path))
        if review_target_null_counts.get(game_id, 0):
            issues.append(make_issue("normalized_logic", "normalized", "review_target_nulls", f"review_events missing review_target_text={review_target_null_counts[game_id]}", path=path))

        pa_stat = pa_seq_stats.get(game_id, (0, 0, 0))
        if pa_stat[0] and (pa_stat[0] != pa_stat[1] or pa_stat[0] != pa_stat[2]):
            issues.append(make_issue("normalized_logic", "normalized", "pa_seq_gap", f"PA sequence count={pa_stat[0]}, max={pa_stat[1]}, distinct={pa_stat[2]}", path=path))
        for inning_id, count_rows, max_seq, distinct_seq, min_seq in pa_seq_in_half_stats.get(game_id, []):
            if count_rows and (count_rows != max_seq or count_rows != distinct_seq or min_seq != 1):
                issues.append(make_issue("normalized_logic", "normalized", "pa_seq_in_half_gap", f"inning_id={inning_id} count={count_rows}, max={max_seq}, distinct={distinct_seq}, min={min_seq}", path=path))
        event_stat = pa_event_seq_stats.get(game_id, (0, 0, 0))
        if event_stat[0] and (event_stat[0] != event_stat[1] or event_stat[0] != event_stat[2]):
            issues.append(make_issue("normalized_logic", "normalized", "event_seq_gap", f"event sequence count={event_stat[0]}, max={event_stat[1]}, distinct={event_stat[2]}", path=path))

        actual_innings = innings_by_game.get(game_id, [])
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
            issues.append(make_issue("normalized_logic", "aggregate", "inning_summary_mismatch", "innings summary rows do not match source expectations", path=path))

        expected_terminal = int(entry.get("expected_terminal_plate_appearances", 0))
        expected_partial = int(entry.get("expected_partial_plate_appearances", 0))
        actual_terminal = int(terminal_counts_by_game.get(game_id, 0))
        actual_partial = int(partial_counts_by_game.get(game_id, 0))
        actual_empty = int(empty_result_counts_by_game.get(game_id, 0))
        if actual_terminal != expected_terminal:
            issues.append(make_issue("normalized_logic", "aggregate", "terminal_pa_count_mismatch", f"terminal plate_appearances expected {expected_terminal}, got {actual_terminal}", path=path))
        if actual_partial != expected_partial:
            issues.append(make_issue("normalized_logic", "aggregate", "partial_pa_count_mismatch", f"partial plate_appearances expected {expected_partial}, got {actual_partial}", path=path))
        if actual_empty != expected_partial:
            issues.append(make_issue("normalized_logic", "aggregate", "empty_result_text_mismatch", f"empty result_text plate_appearances expected {expected_partial}, got {actual_empty}", path=path))

        expected_batter_totals = (entry.get("expected_batter_totals") or entry.get("relay_batter_totals") or {})
        actual_batter_totals = batter_totals_by_game.get(game_id, {"home": Counter(), "away": Counter()})
        for side in ("home", "away"):
            for stat_name in ("pa", "ab", "hit", "bb", "so", "hbp"):
                expected_value = int(expected_batter_totals.get(side, {}).get(stat_name, 0) or 0)
                actual_value = int(actual_batter_totals[side].get(stat_name, 0))
                if expected_value != actual_value:
                    issues.append(make_issue("normalized_logic", "aggregate", f"batter_total_mismatch:{side}:{stat_name}", f"{side} {stat_name} expected {expected_value}, got {actual_value}", path=path))

        orphan_count, missing_tracking = pitch_link_counts.get(game_id, (0, 0))
        if orphan_count:
            issues.append(make_issue("normalized_logic", "normalized", "pitch_orphans", f"pitches missing pa/event/inning refs={orphan_count}", path=path))
        expected_pitch_tracking_gap = _expected_pitch_tracking_gap(entry)
        if missing_tracking != expected_pitch_tracking_gap:
            issues.append(
                make_issue(
                    "normalized_logic",
                    "normalized",
                    "pitch_tracking_gap_mismatch",
                    f"pitches without pitch_tracking expected {expected_pitch_tracking_gap}, got {missing_tracking}",
                    path=path,
                )
            )
        if baserunning_link_mismatches.get(game_id, 0):
            issues.append(make_issue("normalized_logic", "normalized", "baserunning_link_mismatch", f"baserunning_link_mismatch={baserunning_link_mismatches[game_id]}", path=path))
        if review_link_mismatches.get(game_id, 0):
            issues.append(make_issue("normalized_logic", "normalized", "review_link_mismatch", f"review_link_mismatch={review_link_mismatches[game_id]}", path=path))
        if substitution_link_mismatches.get(game_id, 0):
            issues.append(make_issue("normalized_logic", "normalized", "substitution_link_mismatch", f"substitution_link_mismatch={substitution_link_mismatches[game_id]}", path=path))

    remaining_issues: list[dict] = []
    for issue in issues:
        path = issue.get("path")
        if path and path in source_problem_paths:
            code = issue.get("code", "")
            if code == "inning_summary_mismatch" or code in {"terminal_pa_count_mismatch", "partial_pa_count_mismatch", "empty_result_text_mismatch"} or code.startswith("count_mismatch:plate_appearances") or code.startswith("batter_total_mismatch:"):
                source_issues.append(make_issue("source_json", issue["scope"], code, issue["message"], path=path))
                if code.startswith("count_mismatch:"):
                    parsed = parse_expected_actual(issue["message"])
                    if parsed:
                        expected_value, actual_value = parsed
                        source_table_diffs[code.split(":", 1)[1]] += actual_value - expected_value
                continue
        remaining_issues.append(issue)

    blocking_issues: list[dict] = []
    for issue in remaining_issues:
        code = issue.get("code", "")
        if code.startswith("table_count_mismatch:"):
            parsed = parse_expected_actual(issue["message"])
            if parsed:
                expected_value, actual_value = parsed
                table_name = code.split(":", 1)[1]
                if actual_value - expected_value == source_table_diffs.get(table_name, 0):
                    source_issues.append(make_issue("source_json", issue["scope"], code, issue["message"], path=issue.get("path")))
                    continue
        blocking_issues.append(issue)

    for table_name, counts in table_counts.items():
        if counts["expected"] != counts["actual"]:
            code = f"table_count_mismatch:{table_name}"
            message = f"{table_name} expected {counts['expected']}, got {counts['actual']}"
            if counts["actual"] - counts["expected"] == source_table_diffs.get(table_name, 0):
                source_issues.append(make_issue("source_json", "global", code, message))
            else:
                blocking_issues.append(make_issue("raw_ingest" if table_name.startswith("raw_") else "normalized_logic", "global", code, message))

    blocking_issue_types = dict(Counter(issue["type"] for issue in blocking_issues))
    source_issue_types = dict(Counter(issue["type"] for issue in source_issues))
    report = {
        "ok": not blocking_issues,
        "loaded_game_count": len(entries),
        "table_counts": table_counts,
        "blocking_issue_count": len(blocking_issues),
        "source_issue_count": len(source_issues),
        "blocking_issue_types": blocking_issue_types,
        "source_issue_types": source_issue_types,
        "blocking_issues": blocking_issues,
        "source_issues": source_issues,
    }
    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(report, report_path.with_suffix(".md"))
    print(f"bulk validate finished loaded_games={report['loaded_game_count']} blocking_issues={report['blocking_issue_count']} source_issues={report['source_issue_count']}")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
