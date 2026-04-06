from __future__ import annotations

from pathlib import Path

import psycopg


SCHEMA_TABLES = [
    "teams",
    "players",
    "stadiums",
    "raw_games",
    "raw_relay_blocks",
    "raw_text_events",
    "raw_pitch_tracks",
    "raw_plate_metrics",
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


def create_schema(conn: psycopg.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def reset_database(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        for table_name in reversed(SCHEMA_TABLES):
            cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    conn.commit()
