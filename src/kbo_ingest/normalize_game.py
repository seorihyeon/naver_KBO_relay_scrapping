from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - test env fallback
    psycopg = Any  # type: ignore[assignment]
try:
    from psycopg.types.json import Json
except ModuleNotFoundError:  # pragma: no cover - test env fallback
    def Json(value: Any) -> Any:  # type: ignore[misc]
        return value

from common_utils import first_non_empty, to_int


BASERUN_KEYWORDS = ("주자", "도루", "진루", "아웃", "홈인", "견제")
BAT_RESULT_KEYWORDS = ("안타", "홈런", "삼진", "뜬공", "땅볼", "볼넷", "사구", "병살")
PA_END_KEYWORDS = BAT_RESULT_KEYWORDS + ("아웃", "볼넷", "삼진", "사구")


def _extract_runner_name(text: str, base_no: int) -> str | None:
    if not text:
        return None
    m = re.search(rf"{base_no}루주자\s*([^ :]+)", text)
    if m:
        return m.group(1).strip()
    if base_no == 1:
        batter_runner = re.search(r"타자주자\s*([^ :]+)", text)
        if batter_runner:
            return batter_runner.group(1).strip()
    return None


def _batter_reached_base(text: str) -> int | None:
    if not text:
        return None
    if "홈런" in text:
        return None
    if "3루타" in text:
        return 3
    if "2루타" in text:
        return 2
    if any(k in text for k in ("1루타", "내야안타", "안타", "볼넷", "고의4구", "몸에 맞는 볼", "출루", "타자주자")):
        return 1
    return None


def _apply_baserunner_transition(
    text: str,
    runner_name_by_base: dict[int, str | None],
    runner_id_by_base: dict[int, str | None],
    name_to_player_id: dict[str, str],
) -> None:
    if not text:
        return
    move = re.search(r"([123])루주자\s*([^ :]+)\s*:.*([123])루까지 진루", text)
    if move:
        from_base = int(move.group(1))
        runner_name = move.group(2).strip()
        to_base = int(move.group(3))
        runner_id = runner_id_by_base.get(from_base) or name_to_player_id.get(runner_name)
        runner_name_by_base[from_base] = None
        runner_id_by_base[from_base] = None
        runner_name_by_base[to_base] = runner_name
        runner_id_by_base[to_base] = runner_id
        return

    home_in = re.search(r"([123])루주자\s*([^ :]+)\s*:.*홈인", text)
    if home_in:
        from_base = int(home_in.group(1))
        runner_name_by_base[from_base] = None
        runner_id_by_base[from_base] = None
        return

    out = re.search(r"([123])루주자\s*([^ :]+)\s*:.*아웃", text)
    if out:
        from_base = int(out.group(1))
        runner_name_by_base[from_base] = None
        runner_id_by_base[from_base] = None


def _infer_outs_recorded(text: str) -> int:
    txt = text or ""
    if "삼중살" in txt:
        return 3
    if "병살" in txt:
        return 2
    if "아웃" in txt:
        return 1
    return 0


@dataclass
class EventRec:
    raw_event_id: int
    raw_block_id: int
    inning_no: int | None
    half: str | None
    seqno: int
    type_code: int | None
    text: str
    batter_id: str | None
    pitcher_id: str | None
    outs: int | None
    balls: int | None
    strikes: int | None
    base1: bool
    base2: bool
    base3: bool
    home_score: int | None
    away_score: int | None
    pitch_num: int | None
    pitch_result: str | None
    pts_pitch_id: str | None
    speed_kph: float | None
    stuff_text: str | None
    category: str
    raw_payload: dict[str, Any]


def _normalize_half(home_or_away: Any) -> str | None:
    if home_or_away is None:
        return None
    txt = str(home_or_away).strip().upper()
    if txt in {"0", "TOP", "T", "AWAY"}:
        return "top"
    if txt in {"1", "BOTTOM", "B", "HOME"}:
        return "bottom"
    return None


def _to_bool(value: Any) -> bool:
    if value in (None, "", 0, "0", "false", False):
        return False
    return True


def classify_event(text: str, pitch_num: int | None, pitch_result: str | None, pts_pitch_id: str | None, player_change: Any) -> str:
    txt = text or ""
    if pitch_num is not None or pitch_result or pts_pitch_id:
        return "pitch"
    if player_change:
        return "substitution"
    if "비디오 판독" in txt:
        return "review"
    if any(k in txt for k in BASERUN_KEYWORDS):
        return "baserunning"
    if any(k in txt for k in BAT_RESULT_KEYWORDS):
        return "bat_result"
    if "회" in txt and ("초" in txt or "말" in txt):
        return "header"
    return "other"


def _bases_from_state(cgs: dict[str, Any]) -> tuple[bool, bool, bool]:
    return (
        _to_bool(first_non_empty(cgs.get("base1"), cgs.get("on1b"), cgs.get("runner1b"))),
        _to_bool(first_non_empty(cgs.get("base2"), cgs.get("on2b"), cgs.get("runner2b"))),
        _to_bool(first_non_empty(cgs.get("base3"), cgs.get("on3b"), cgs.get("runner3b"))),
    )


def _fetch_events(cur: psycopg.Cursor, raw_game_id: int) -> list[EventRec]:
    cur.execute(
        """
        SELECT
            rte.raw_event_id,
            rte.raw_block_id,
            rrb.inning_no,
            rrb.home_or_away,
            COALESCE(rte.seqno, rte.raw_event_id) AS seqno_fallback,
            rte.type_code,
            COALESCE(rte.text, '') AS text,
            rte.current_game_state_json,
            rte.pitch_num,
            rte.pitch_result,
            rte.pts_pitch_id,
            rte.speed_kph,
            rte.stuff_text,
            rte.player_change_json,
            rte.raw_event_json
        FROM raw_text_events rte
        JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rte.raw_block_id
        WHERE rrb.raw_game_id = %s
        ORDER BY seqno_fallback, rte.raw_event_id
        """,
        (raw_game_id,),
    )

    events: list[EventRec] = []
    for row in cur.fetchall():
        cgs = row[7] or {}
        b1, b2, b3 = _bases_from_state(cgs)
        txt = row[6]
        events.append(
            EventRec(
                raw_event_id=row[0],
                raw_block_id=row[1],
                inning_no=row[2],
                half=_normalize_half(row[3]),
                seqno=row[4],
                type_code=row[5],
                text=txt,
                batter_id=str(first_non_empty(cgs.get("batter"), (row[14] or {}).get("batterRecord", {}).get("pcode")) or "") or None,
                pitcher_id=str(first_non_empty(cgs.get("pitcher")) or "") or None,
                outs=to_int(first_non_empty(cgs.get("out"), cgs.get("outCount"), cgs.get("outs")), None),
                balls=to_int(first_non_empty(cgs.get("ball"), cgs.get("ballCount"), cgs.get("balls")), None),
                strikes=to_int(first_non_empty(cgs.get("strike"), cgs.get("strikeCount"), cgs.get("strikes")), None),
                base1=b1,
                base2=b2,
                base3=b3,
                home_score=to_int(first_non_empty(cgs.get("homeTeamScore"), cgs.get("homeScore")), None),
                away_score=to_int(first_non_empty(cgs.get("awayTeamScore"), cgs.get("awayScore")), None),
                pitch_num=row[8],
                pitch_result=row[9],
                pts_pitch_id=row[10],
                speed_kph=row[11],
                stuff_text=row[12],
                category=classify_event(txt, row[8], row[9], row[10], row[13]),
                raw_payload=row[14] or {},
            )
        )
    return events


def _is_pa_end(event: EventRec) -> bool:
    txt = event.text or ""
    return event.category == "bat_result" or any(k in txt for k in PA_END_KEYWORDS)


def normalize_game_from_raw(conn: psycopg.Connection, raw_game_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base1_runner_id TEXT")
        cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base2_runner_id TEXT")
        cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base3_runner_id TEXT")
        cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base1_runner_name TEXT")
        cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base2_runner_name TEXT")
        cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base3_runner_name TEXT")

        cur.execute("SELECT game_id, home_team_id, away_team_id FROM games WHERE raw_game_id = %s", (raw_game_id,))
        game_row = cur.fetchone()
        if not game_row:
            raise ValueError(f"game not found for raw_game_id={raw_game_id}")
        game_id, home_team_id, away_team_id = game_row

        cur.execute("DELETE FROM substitution_events WHERE game_id = %s", (game_id,))
        cur.execute("DELETE FROM review_events WHERE game_id = %s", (game_id,))
        cur.execute("DELETE FROM baserunning_events WHERE game_id = %s", (game_id,))
        cur.execute("DELETE FROM batted_ball_results WHERE pa_id IN (SELECT pa_id FROM plate_appearances WHERE game_id = %s)", (game_id,))
        cur.execute("DELETE FROM pitch_tracking WHERE pitch_id IN (SELECT pitch_id FROM pitches WHERE game_id = %s)", (game_id,))
        cur.execute("DELETE FROM pitches WHERE game_id = %s", (game_id,))
        cur.execute("DELETE FROM pa_events WHERE game_id = %s", (game_id,))
        cur.execute("DELETE FROM plate_appearances WHERE game_id = %s", (game_id,))
        cur.execute("DELETE FROM innings WHERE game_id = %s", (game_id,))

        events = _fetch_events(cur, raw_game_id)
        cur.execute("SELECT player_id, player_name FROM players")
        player_name_by_id = {row[0]: row[1] for row in cur.fetchall() if row[0]}
        name_to_player_id = {}
        for player_id, player_name in player_name_by_id.items():
            if player_name and player_name not in name_to_player_id:
                name_to_player_id[player_name] = player_id

        inning_map: dict[tuple[int, str], int] = {}
        pa_counter = 0
        pa_in_half_counter: dict[tuple[int, str], int] = {}
        current_pa_id: int | None = None
        current_pa_key: tuple[int, str, str | None] | None = None
        current_pa_event_no = 0
        event_id_by_pitch_id: dict[str, int] = {}
        runner_name_by_base = {1: None, 2: None, 3: None}
        runner_id_by_base = {1: None, 2: None, 3: None}

        for event_seq_game, ev in enumerate(events, start = 1):
            inning_no = ev.inning_no or 0
            half = ev.half or "top"
            in_key = (inning_no, half)
            if in_key not in inning_map:
                batting_team_id = away_team_id if half == "top" else home_team_id
                fielding_team_id = home_team_id if half == "top" else away_team_id
                cur.execute(
                    """
                    INSERT INTO innings (
                        game_id, inning_no, half, batting_team_id, fielding_team_id,
                        start_event_seqno, end_event_seqno, runs_scored, hits_in_half, errors_in_half, walks_in_half
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0)
                    RETURNING inning_id
                    """,
                    (game_id, inning_no, half, batting_team_id, fielding_team_id, ev.seqno, ev.seqno),
                )
                inning_map[in_key] = cur.fetchone()[0]
                pa_in_half_counter[in_key] = 0
            inning_id = inning_map[in_key]

            pa_key = (inning_no, half, ev.batter_id)
            start_new_pa = current_pa_id is None or current_pa_key != pa_key
            if start_new_pa:
                pa_counter += 1
                pa_in_half_counter[in_key] += 1
                cur.execute(
                    """
                    INSERT INTO plate_appearances (
                        game_id, inning_id, pa_seq_game, pa_seq_in_half,
                        batter_id, pitcher_id, outs_before, balls_final, strikes_final,
                        bases_before, start_seqno, start_pitch_num, raw_block_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING pa_id
                    """,
                    (
                        game_id,
                        inning_id,
                        pa_counter,
                        pa_in_half_counter[in_key],
                        ev.batter_id,
                        ev.pitcher_id,
                        ev.outs,
                        ev.balls,
                        ev.strikes,
                        f"{int(ev.base1)}{int(ev.base2)}{int(ev.base3)}",
                        ev.seqno,
                        ev.pitch_num,
                        ev.raw_block_id,
                    ),
                )
                current_pa_id = cur.fetchone()[0]
                current_pa_key = pa_key
                current_pa_event_no = 0

            current_pa_event_no += 1
            _apply_baserunner_transition(ev.text, runner_name_by_base, runner_id_by_base, name_to_player_id)
            has_runner_transition = bool(re.search(r"[123]루주자\s*[^ :]+\s*:.*(까지 진루|홈인|아웃)", ev.text or ""))
            if not ev.base1:
                runner_name_by_base[1] = None
                runner_id_by_base[1] = None
            if not ev.base2:
                runner_name_by_base[2] = None
                runner_id_by_base[2] = None
            if not ev.base3:
                runner_name_by_base[3] = None
                runner_id_by_base[3] = None

            for base_no in (1, 2, 3):
                if has_runner_transition:
                    continue
                parsed_name = _extract_runner_name(ev.text, base_no)
                if parsed_name:
                    runner_name_by_base[base_no] = parsed_name
                    runner_id_by_base[base_no] = name_to_player_id.get(parsed_name)
            batter_reach_base = _batter_reached_base(ev.text)
            if batter_reach_base and ev.batter_id:
                batter_name = player_name_by_id.get(ev.batter_id)
                if batter_name:
                    runner_name_by_base[batter_reach_base] = batter_name
                runner_id_by_base[batter_reach_base] = ev.batter_id

            cur.execute(
                """
                INSERT INTO pa_events (
                    game_id, inning_id, pa_id, event_seq_game, event_seq_in_pa,
                    event_type_code, event_category, text, batter_id, pitcher_id,
                    outs, balls, strikes, base1_occupied, base2_occupied, base3_occupied,
                    home_score, away_score,
                    base1_runner_id, base2_runner_id, base3_runner_id,
                    base1_runner_name, base2_runner_name, base3_runner_name, raw_event_id, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING event_id
                """,
                (
                    game_id,
                    inning_id,
                    current_pa_id,
                    event_seq_game,
                    current_pa_event_no,
                    ev.type_code,
                    ev.category,
                    ev.text,
                    ev.batter_id,
                    ev.pitcher_id,
                    ev.outs,
                    ev.balls,
                    ev.strikes,
                    ev.base1,
                    ev.base2,
                    ev.base3,
                    ev.home_score,
                    ev.away_score,
                    runner_id_by_base[1],
                    runner_id_by_base[2],
                    runner_id_by_base[3],
                    runner_name_by_base[1],
                    runner_name_by_base[2],
                    runner_name_by_base[3],
                    ev.raw_event_id,
                    Json(ev.raw_payload),
                ),
            )
            pa_event_id = cur.fetchone()[0]

            if ev.pts_pitch_id:
                event_id_by_pitch_id[ev.pts_pitch_id] = pa_event_id
                cur.execute(
                    """
                    INSERT INTO pitches (
                        pitch_id, game_id, inning_id, pa_id, event_id,
                        pitch_num, pitch_result, pitch_type_text, speed_kph,
                        balls_before, strikes_before, balls_after, strikes_after,
                        is_in_play, is_terminal_pitch
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (pitch_id)
                    DO UPDATE SET
                        game_id = EXCLUDED.game_id,
                        inning_id = EXCLUDED.inning_id,
                        pa_id = EXCLUDED.pa_id,
                        event_id = EXCLUDED.event_id,
                        pitch_num = EXCLUDED.pitch_num,
                        pitch_result = EXCLUDED.pitch_result,
                        pitch_type_text = EXCLUDED.pitch_type_text,
                        speed_kph = EXCLUDED.speed_kph,
                        balls_before = EXCLUDED.balls_before,
                        strikes_before = EXCLUDED.strikes_before,
                        balls_after = EXCLUDED.balls_after,
                        strikes_after = EXCLUDED.strikes_after,
                        is_in_play = EXCLUDED.is_in_play,
                        is_terminal_pitch = EXCLUDED.is_terminal_pitch
                    """,
                    (
                        ev.pts_pitch_id,
                        game_id,
                        inning_id,
                        current_pa_id,
                        pa_event_id,
                        ev.pitch_num,
                        ev.pitch_result,
                        ev.stuff_text,
                        ev.speed_kph,
                        ev.balls,
                        ev.strikes,
                        ev.balls,
                        ev.strikes,
                        bool("인플레이" in (ev.pitch_result or "")),
                        _is_pa_end(ev),
                    ),
                )

            if ev.category == "baserunning":
                outs_recorded = _infer_outs_recorded(ev.text)
                cur.execute(
                    """
                    INSERT INTO baserunning_events (
                        game_id, inning_id, pa_id, event_id,
                        runner_player_id, runner_name_raw, event_subtype,
                        is_out, outs_recorded, caused_by_error, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        game_id,
                        inning_id,
                        current_pa_id,
                        pa_event_id,
                        ev.batter_id,
                        None,
                        "steal" if "도루" in ev.text else "advance",
                        bool(outs_recorded),
                        outs_recorded,
                        bool("실책" in ev.text),
                        ev.text,
                    ),
                )

            if ev.category == "review":
                cur.execute(
                    """
                    INSERT INTO review_events (
                        event_id, game_id, inning_id, pa_id,
                        subject_type, final_call, review_target_text, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (pa_event_id, game_id, inning_id, current_pa_id, "play", None, ev.text, ev.text),
                )

            if ev.category == "substitution":
                cur.execute(
                    """
                    INSERT INTO substitution_events (
                        event_id, game_id, inning_id, pa_id,
                        team_id, sub_type, in_player_id, out_player_id,
                        in_player_name, out_player_name, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (pa_event_id, game_id, inning_id, current_pa_id, None, "other", None, None, None, None, ev.text),
                )

            if ev.category == "bat_result":
                cur.execute(
                    """
                    INSERT INTO batted_ball_results (
                        pa_id, event_id, pitch_id, result_code, result_text,
                        hit_flag, out_flag, error_flag, sacrifice_flag
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        current_pa_id,
                        pa_event_id,
                        ev.pts_pitch_id,
                        ev.pitch_result,
                        ev.text,
                        bool("안타" in ev.text or "홈런" in ev.text),
                        bool("아웃" in ev.text),
                        bool("실책" in ev.text),
                        bool("희생" in ev.text),
                    ),
                )

            cur.execute(
                """
                UPDATE plate_appearances
                SET end_seqno = %s,
                    end_pitch_num = COALESCE(%s, end_pitch_num),
                    balls_final = %s,
                    strikes_final = %s,
                    outs_after = %s,
                    bases_after = %s,
                    result_text = CASE WHEN %s THEN %s ELSE result_text END,
                    is_terminal = COALESCE(is_terminal, %s)
                WHERE pa_id = %s
                """,
                (
                    ev.seqno,
                    ev.pitch_num,
                    ev.balls,
                    ev.strikes,
                    ev.outs,
                    f"{int(ev.base1)}{int(ev.base2)}{int(ev.base3)}",
                    _is_pa_end(ev),
                    ev.text,
                    _is_pa_end(ev),
                    current_pa_id,
                ),
            )

            cur.execute(
                """
                UPDATE innings
                SET end_event_seqno = GREATEST(COALESCE(end_event_seqno, %s), %s)
                WHERE inning_id = %s
                """,
                (ev.seqno, ev.seqno, inning_id),
            )

            if _is_pa_end(ev):
                current_pa_id = None
                current_pa_key = None
                current_pa_event_no = 0

        cur.execute(
            """
            SELECT rpt.pitch_id,
                   rpt.ballcount,
                   rpt.cross_plate_x,
                   rpt.cross_plate_y,
                   rpt.top_sz,
                   rpt.bottom_sz,
                   rpt.vx0,
                   rpt.vy0,
                   rpt.vz0,
                   rpt.ax,
                   rpt.ay,
                   rpt.az,
                   rpt.x0,
                   rpt.y0,
                   rpt.z0,
                   rpt.stance
            FROM raw_pitch_tracks rpt
            JOIN raw_relay_blocks rrb ON rrb.raw_block_id = rpt.raw_block_id
            WHERE rrb.raw_game_id = %s
            """,
            (raw_game_id,),
        )
        for tr in cur.fetchall():
            pitch_id = tr[0]
            if not pitch_id:
                continue
            if pitch_id not in event_id_by_pitch_id:
                continue
            cur.execute(
                """
                INSERT INTO pitch_tracking (
                    pitch_id, ballcount, cross_plate_x, cross_plate_y,
                    top_sz, bottom_sz, vx0, vy0, vz0, ax, ay, az, x0, y0, z0, stance
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pitch_id)
                DO UPDATE SET
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
                    stance = EXCLUDED.stance
                """,
                tr,
            )

    conn.commit()
    return game_id
