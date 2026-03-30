from __future__ import annotations

from pathlib import Path

import psycopg

from .ingest_raw import ingest_raw_game
from .normalize_game import normalize_game_from_raw


def load_one_game(conn: psycopg.Connection, json_path: Path) -> tuple[int, int]:
    raw_game_id, game_id = ingest_raw_game(conn, json_path)
    game_id = normalize_game_from_raw(conn, raw_game_id)
    return raw_game_id, game_id


def validate_game(conn: psycopg.Connection, game_id: int) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM innings WHERE game_id = %s", (game_id,))
        innings_cnt = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM plate_appearances WHERE game_id = %s", (game_id,))
        pa_cnt = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*)
            FROM pitch_tracking pt
            JOIN pitches p ON p.pitch_id = pt.pitch_id
            WHERE p.game_id = %s
            """,
            (game_id,),
        )
        joined_pitch_cnt = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*)
            FROM pa_events
            WHERE game_id = %s
              AND (home_score IS NULL OR away_score IS NULL)
            """,
            (game_id,),
        )
        score_null_cnt = cur.fetchone()[0]

    return {
        "innings_count": innings_cnt,
        "plate_appearances_count": pa_cnt,
        "pitch_tracking_joined_count": joined_pitch_cnt,
        "score_null_event_count": score_null_cnt,
    }
