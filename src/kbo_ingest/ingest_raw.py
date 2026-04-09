from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json

from .common_utils import first_non_empty, to_int
from .game_json import load_game_payload


def _to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool_flag(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)

    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "y", "yes"}:
        return True
    if normalized in {"0", "false", "f", "n", "no"}:
        return False
    return default


def _parse_game_date(value: Any) -> datetime.date | None:
    if value in (None, "", "-"):
        return None

    normalized = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iter_relay_blocks(relay: list[Any]) -> list[tuple[int, dict[str, Any]]]:
    blocks: list[tuple[int, dict[str, Any]]] = []
    block_index = 1
    for block_group in relay or []:
        for block in block_group or []:
            if isinstance(block, dict):
                blocks.append((block_index, block))
                block_index += 1
    return blocks


def _upsert_team(cur: psycopg.Cursor, team_code: str | None, team_name: str | None) -> int | None:
    if not team_code:
        return None
    cur.execute(
        """
        INSERT INTO teams (team_code, team_name_short, team_name_full)
        VALUES (%s, %s, %s)
        ON CONFLICT (team_code)
        DO UPDATE SET
            team_name_short = COALESCE(EXCLUDED.team_name_short, teams.team_name_short),
            team_name_full = COALESCE(EXCLUDED.team_name_full, teams.team_name_full)
        RETURNING team_id
        """,
        (team_code, team_name, team_name),
    )
    return cur.fetchone()[0]


def _upsert_player(cur: psycopg.Cursor, row: dict[str, Any]) -> None:
    player_id = str(first_non_empty(row.get("playerCode"), row.get("pcode"), row.get("playerId")) or "")
    if not player_id:
        return
    cur.execute(
        """
        INSERT INTO players (player_id, player_name, bats_throws_text, hit_type_text, height, weight)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (player_id)
        DO UPDATE SET
            player_name = COALESCE(EXCLUDED.player_name, players.player_name),
            bats_throws_text = COALESCE(EXCLUDED.bats_throws_text, players.bats_throws_text),
            hit_type_text = COALESCE(EXCLUDED.hit_type_text, players.hit_type_text),
            height = COALESCE(EXCLUDED.height, players.height),
            weight = COALESCE(EXCLUDED.weight, players.weight)
        """,
        (
            player_id,
            first_non_empty(row.get("playerName"), row.get("name")),
            first_non_empty(row.get("throwBat"), row.get("throws"), row.get("batsThrows")),
            first_non_empty(row.get("hitType"), row.get("bats")),
            to_int(row.get("height"), None),
            to_int(row.get("weight"), None),
        ),
    )


def _iter_record_player_rows(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for side in ("home", "away"):
        for row in (record.get("batter") or {}).get(side, []) or []:
            if first_non_empty(row.get("playerCode"), row.get("pcode"), row.get("playerId")):
                rows.append((side, row))
        for row in (record.get("pitcher") or {}).get(side, []) or []:
            if first_non_empty(row.get("playerCode"), row.get("pcode"), row.get("playerId")):
                rows.append((side, row))
    return rows


def _delete_existing_normalized_rows(cur: psycopg.Cursor, game_id: int) -> None:
    cur.execute("DELETE FROM substitution_events WHERE game_id = %s", (game_id,))
    cur.execute("DELETE FROM review_events WHERE game_id = %s", (game_id,))
    cur.execute("DELETE FROM baserunning_events WHERE game_id = %s", (game_id,))
    cur.execute(
        "DELETE FROM batted_ball_results WHERE pa_id IN (SELECT pa_id FROM plate_appearances WHERE game_id = %s)",
        (game_id,),
    )
    cur.execute("DELETE FROM pitch_tracking WHERE pitch_id IN (SELECT pitch_id FROM pitches WHERE game_id = %s)", (game_id,))
    cur.execute("DELETE FROM pitches WHERE game_id = %s", (game_id,))
    cur.execute("DELETE FROM pa_events WHERE game_id = %s", (game_id,))
    cur.execute("DELETE FROM plate_appearances WHERE game_id = %s", (game_id,))
    cur.execute("DELETE FROM innings WHERE game_id = %s", (game_id,))


def ingest_raw_game(conn: psycopg.Connection, json_path: Path) -> tuple[int, int]:
    payload = load_game_payload(json_path)
    file_hash = _file_hash(json_path)
    lineup = payload.get("lineup") or {}
    record = payload.get("record") or {}
    game_info = lineup.get("game_info") or {}
    raw_game_date = first_non_empty(game_info.get("gdate"), game_info.get("gameDate"), game_info.get("date"))
    game_date = _parse_game_date(raw_game_date)
    is_postseason = _to_bool_flag(
        first_non_empty(game_info.get("isPostSeason"), game_info.get("postSeason"), game_info.get("postseason")),
        default=False,
    )
    cancel_flag = _to_bool_flag(first_non_empty(game_info.get("cancelFlag"), game_info.get("cancel")), default=False)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_games (source_file_name, source_file_hash, raw_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (source_file_hash)
            DO UPDATE SET source_file_name = EXCLUDED.source_file_name,
                          raw_json = EXCLUDED.raw_json,
                          ingested_at = NOW()
            RETURNING raw_game_id
            """,
            (str(json_path), file_hash, Json(payload)),
        )
        raw_game_id = cur.fetchone()[0]

        home_code = first_non_empty(game_info.get("hCode"), game_info.get("homeTeamCode"))
        away_code = first_non_empty(game_info.get("aCode"), game_info.get("awayTeamCode"))
        home_name = first_non_empty(game_info.get("hName"), game_info.get("homeTeamName"))
        away_name = first_non_empty(game_info.get("aName"), game_info.get("awayTeamName"))

        home_team_id = _upsert_team(cur, str(home_code) if home_code else None, home_name)
        away_team_id = _upsert_team(cur, str(away_code) if away_code else None, away_name)

        stadium_name = first_non_empty(game_info.get("stadium"), game_info.get("stadiumName"))
        stadium_id = None
        if stadium_name:
            cur.execute(
                """
                INSERT INTO stadiums (stadium_name)
                VALUES (%s)
                ON CONFLICT (stadium_name) DO UPDATE SET stadium_name = EXCLUDED.stadium_name
                RETURNING stadium_id
                """,
                (stadium_name,),
            )
            stadium_id = cur.fetchone()[0]

        source_game_key = "_".join(
            [
                str(raw_game_date or ""),
                str(away_code or ""),
                str(home_code or ""),
                str(first_non_empty(game_info.get("gameFlag"), "")),
                str(first_non_empty(game_info.get("round"), "")),
            ]
        )

        cur.execute(
            """
            INSERT INTO games (
                raw_game_id, source_game_key, game_date, game_time,
                stadium_id, home_team_id, away_team_id,
                round_no, game_flag, is_postseason, cancel_flag, status_code, source_file_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (raw_game_id)
            DO UPDATE SET source_game_key = EXCLUDED.source_game_key,
                          game_date = EXCLUDED.game_date,
                          game_time = EXCLUDED.game_time,
                          stadium_id = EXCLUDED.stadium_id,
                          home_team_id = EXCLUDED.home_team_id,
                          away_team_id = EXCLUDED.away_team_id,
                          round_no = EXCLUDED.round_no,
                          game_flag = EXCLUDED.game_flag,
                          is_postseason = EXCLUDED.is_postseason,
                          cancel_flag = EXCLUDED.cancel_flag,
                          status_code = EXCLUDED.status_code,
                          source_file_name = EXCLUDED.source_file_name
            RETURNING game_id
            """,
            (
                raw_game_id,
                source_game_key,
                game_date,
                first_non_empty(game_info.get("gameTime"), game_info.get("gtime")),
                stadium_id,
                home_team_id,
                away_team_id,
                str(first_non_empty(game_info.get("round"), "")) or None,
                first_non_empty(game_info.get("gameFlag"), game_info.get("gubun")),
                is_postseason,
                cancel_flag,
                first_non_empty(game_info.get("statusCode"), game_info.get("state")),
                str(json_path),
            ),
        )
        game_id = cur.fetchone()[0]

        _delete_existing_normalized_rows(cur, game_id)
        cur.execute("DELETE FROM game_roster_entries WHERE game_id = %s", (game_id,))
        roster_player_ids: set[str] = set()

        for side, team_id in (("home", home_team_id), ("away", away_team_id)):
            for group in ("starter", "bullpen", "candidate"):
                rows = lineup.get(f"{side}_{group}") or []
                for row in rows:
                    _upsert_player(cur, row)
                    pid = str(first_non_empty(row.get("playerCode"), row.get("pcode"), row.get("playerId")) or "") or None
                    if pid:
                        roster_player_ids.add(pid)
                    cur.execute(
                        """
                        INSERT INTO game_roster_entries (
                            game_id, team_id, player_id, roster_group, is_starting_pitcher,
                            batting_order_slot, field_position_code, field_position_name, back_number
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            game_id,
                            team_id,
                            pid,
                            group,
                            bool(str(row.get("position")) == "1" and group == "starter"),
                            to_int(first_non_empty(row.get("batOrder"), row.get("bo")), None),
                            str(row.get("position")) if row.get("position") is not None else None,
                            first_non_empty(row.get("positionName"), row.get("positionText")),
                            first_non_empty(row.get("backNo"), row.get("backnum")),
                        ),
                    )

        team_id_by_side = {"home": home_team_id, "away": away_team_id}
        for side, row in _iter_record_player_rows(record):
            _upsert_player(cur, row)
            pid = str(first_non_empty(row.get("playerCode"), row.get("pcode"), row.get("playerId")) or "") or None
            if not pid or pid in roster_player_ids:
                continue
            roster_player_ids.add(pid)
            cur.execute(
                """
                INSERT INTO game_roster_entries (
                    game_id, team_id, player_id, roster_group, is_starting_pitcher,
                    batting_order_slot, field_position_code, field_position_name, back_number
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    game_id,
                    team_id_by_side.get(side),
                    pid,
                    "record_only",
                    False,
                    to_int(first_non_empty(row.get("batOrder"), row.get("bo")), None),
                    None,
                    None,
                    None,
                ),
            )

        cur.execute("DELETE FROM raw_relay_blocks WHERE raw_game_id = %s", (raw_game_id,))

        block_id_map: dict[int, int] = {}
        for block_index, block in _iter_relay_blocks(payload.get("relay") or []):
            cur.execute(
                """
                INSERT INTO raw_relay_blocks (
                    raw_game_id, block_index, title, title_style, block_no,
                    inning_no, home_or_away, status_code, raw_block_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING raw_block_id
                """,
                (
                    raw_game_id,
                    block_index,
                    block.get("title"),
                    str(block.get("titleStyle")) if block.get("titleStyle") is not None else None,
                    to_int(block.get("no"), None),
                    to_int(block.get("inn"), None),
                    str(block.get("homeOrAway")) if block.get("homeOrAway") is not None else None,
                    str(block.get("statusCode")) if block.get("statusCode") is not None else None,
                    Json(block),
                ),
            )
            raw_block_id = cur.fetchone()[0]
            block_id_map[block_index] = raw_block_id

            metric = block.get("metricOption") or {}
            cur.execute(
                """
                INSERT INTO raw_plate_metrics (raw_block_id, home_team_win_rate, away_team_win_rate, wpa_by_plate)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (raw_block_id)
                DO UPDATE SET
                    home_team_win_rate = EXCLUDED.home_team_win_rate,
                    away_team_win_rate = EXCLUDED.away_team_win_rate,
                    wpa_by_plate = EXCLUDED.wpa_by_plate
                """,
                (
                    raw_block_id,
                    _to_float(metric.get("homeTeamWinRate")),
                    _to_float(metric.get("awayTeamWinRate")),
                    _to_float(metric.get("wpaByPlate")),
                ),
            )

            for event_idx, ev in enumerate(block.get("textOptions") or [], start=1):
                cur.execute(
                    """
                    INSERT INTO raw_text_events (
                        raw_block_id, event_index_in_block, seqno, type_code, text,
                        current_game_state_json, batter_record_json, current_players_info_json,
                        player_change_json, pitch_num, pitch_result, pts_pitch_id,
                        speed_kph, stuff_text, raw_event_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        raw_block_id,
                        event_idx,
                        to_int(ev.get("seqno"), None),
                        to_int(ev.get("type"), None),
                        ev.get("text"),
                        Json(ev.get("currentGameState")),
                        Json(ev.get("batterRecord")) if ev.get("batterRecord") is not None else None,
                        Json(ev.get("currentPlayersInfo")) if ev.get("currentPlayersInfo") is not None else None,
                        Json(ev.get("playerChange")) if ev.get("playerChange") is not None else None,
                        to_int(ev.get("pitchNum"), None),
                        ev.get("pitchResult"),
                        str(ev.get("ptsPitchId")) if ev.get("ptsPitchId") is not None else None,
                        _to_float(ev.get("speed")),
                        ev.get("stuff"),
                        Json(ev),
                    ),
                )

            for track_index, track in enumerate(block.get("ptsOptions") or [], start=1):
                cur.execute(
                    """
                    INSERT INTO raw_pitch_tracks (
                        raw_block_id, track_index_in_block, pitch_id, inn, ballcount,
                        cross_plate_x, cross_plate_y, top_sz, bottom_sz,
                        vx0, vy0, vz0, ax, ay, az, x0, y0, z0, stance,
                        raw_track_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (raw_block_id, track_index_in_block)
                    DO UPDATE SET
                        pitch_id = EXCLUDED.pitch_id,
                        inn = EXCLUDED.inn,
                        ballcount = EXCLUDED.ballcount,
                        cross_plate_x = EXCLUDED.cross_plate_x,
                        cross_plate_y = EXCLUDED.cross_plate_y,
                        top_sz = EXCLUDED.top_sz,
                        bottom_sz = EXCLUDED.bottom_sz,
                        vx0 = EXCLUDED.vx0,
                        vy0 = EXCLUDED.vy0,
                        vz0 = EXCLUDED.vz0,
                        ax = EXCLUDED.ax,
                        ay = EXCLUDED.ay,
                        az = EXCLUDED.az,
                        x0 = EXCLUDED.x0,
                        y0 = EXCLUDED.y0,
                        z0 = EXCLUDED.z0,
                        stance = EXCLUDED.stance,
                        raw_track_json = EXCLUDED.raw_track_json
                    """,
                    (
                        raw_block_id,
                        track_index,
                        str(track.get("pitchId")) if track.get("pitchId") is not None else None,
                        to_int(track.get("inn"), None),
                        track.get("ballcount"),
                        _to_float(track.get("crossPlateX")),
                        _to_float(track.get("crossPlateY")),
                        _to_float(track.get("topSz")),
                        _to_float(track.get("bottomSz")),
                        _to_float(track.get("vx0")),
                        _to_float(track.get("vy0")),
                        _to_float(track.get("vz0")),
                        _to_float(track.get("ax")),
                        _to_float(track.get("ay")),
                        _to_float(track.get("az")),
                        _to_float(track.get("x0")),
                        _to_float(track.get("y0")),
                        _to_float(track.get("z0")),
                        track.get("stance"),
                        Json(track),
                    ),
                )

    return raw_game_id, game_id
