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


BASERUN_KEYWORDS = ("도루", "진루", "홈인", "견제", "태그아웃", "포스아웃", "주루사", "협살")
BAT_RESULT_KEYWORDS = (
    "1루타",
    "2루타",
    "3루타",
    "내야안타",
    "번트안타",
    "안타",
    "홈런",
    "삼진",
    "뜬공",
    "플라이 아웃",
    "파울플라이 아웃",
    "땅볼",
    "직선타",
    "라인드라이브",
    "볼넷",
    "고의4구",
    "자동 고의4구",
    "사구",
    "몸에 맞는 볼",
    "병살",
    "희생플라이",
    "희생번트",
    "낫아웃",
    "낫 아웃",
    "야수선택",
    "타격방해",
    "실책",
    "출루",
)
PA_END_KEYWORDS = BAT_RESULT_KEYWORDS + ("아웃",)
BAT_RESULT_TYPE_CODES = {13, 23}

RUNNER_EVENT_PREFIX_RE = re.compile(r"^(?:[123]루주자|타자주자)\s+")
PICKOFF_ATTEMPT_RE = re.compile(r"^[123]루\s+견제 시도")
_PA_RUNNER_COLUMNS_READY_BY_CONN: set[int] = set()


def _extract_event_subject_name(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"(?:(?:[123]\ub8e8\uc8fc\uc790|타자주자)\s*)?([^ :]+)\s*:", text)
    if match:
        return match.group(1).strip()
    return None


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


def _is_batter_intro_text(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    return bool(re.match(r"^\d+\ubc88\ud0c0\uc790\s+\S+", stripped) or re.match(r"^\ub300\ud0c0\s+\S+", stripped))


def _is_neutral_baserunning_text(text: str) -> bool:
    if not text:
        return False
    return "\uacac\uc81c \uc2dc\ub3c4" in text and not any(
        keyword in text
        for keyword in (
            "\uc544\uc6c3",
            "\uc138\uc774\ud504",
            "\uc9c4\ub8e8",
            "\ud648\uc778",
            "\ub3c4\ub8e8",
            "\uc2e4\ucc45",
        )
    )


def _event_description(text: str) -> str:
    if ":" not in text:
        return ""
    return text.split(":", maxsplit=1)[1].strip()


def _is_baserunning_text(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if RUNNER_EVENT_PREFIX_RE.match(stripped):
        return True
    if PICKOFF_ATTEMPT_RE.match(stripped):
        return True
    desc = _event_description(stripped)
    return bool(desc) and any(keyword in desc for keyword in BASERUN_KEYWORDS)


def _is_bat_result_text(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if RUNNER_EVENT_PREFIX_RE.match(stripped) or PICKOFF_ATTEMPT_RE.match(stripped):
        return False
    desc = _event_description(stripped)
    if not desc:
        return False
    return any(keyword in desc for keyword in BAT_RESULT_KEYWORDS)


def _ensure_pa_event_runner_columns(conn: psycopg.Connection, cur: psycopg.Cursor) -> None:
    conn_key = id(conn)
    if conn_key in _PA_RUNNER_COLUMNS_READY_BY_CONN:
        return
    cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base1_runner_id TEXT")
    cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base2_runner_id TEXT")
    cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base3_runner_id TEXT")
    cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base1_runner_name TEXT")
    cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base2_runner_name TEXT")
    cur.execute("ALTER TABLE pa_events ADD COLUMN IF NOT EXISTS base3_runner_name TEXT")
    _PA_RUNNER_COLUMNS_READY_BY_CONN.add(conn_key)


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
    home_hits: int | None
    away_hits: int | None
    home_errors: int | None
    away_errors: int | None
    home_ball_four: int | None
    away_ball_four: int | None
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


def classify_event(
    text: str,
    pitch_num: int | None,
    pitch_result: str | None,
    pts_pitch_id: str | None,
    player_change: Any,
    type_code: int | None = None,
) -> str:
    txt = text or ""
    if pitch_num is not None or pitch_result or pts_pitch_id:
        return "pitch"
    if type_code in BAT_RESULT_TYPE_CODES:
        return "bat_result"
    if player_change:
        return "substitution"
    if "비디오 판독" in txt:
        return "review"
    if "회" in txt and ("초" in txt or "말" in txt):
        return "header"
    if _is_bat_result_text(txt):
        return "bat_result"
    if _is_baserunning_text(txt):
        return "baserunning"
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
                home_hits=to_int(first_non_empty(cgs.get("homeHit"), cgs.get("homeHits")), None),
                away_hits=to_int(first_non_empty(cgs.get("awayHit"), cgs.get("awayHits")), None),
                home_errors=to_int(first_non_empty(cgs.get("homeError"), cgs.get("homeErrors")), None),
                away_errors=to_int(first_non_empty(cgs.get("awayError"), cgs.get("awayErrors")), None),
                home_ball_four=to_int(first_non_empty(cgs.get("homeBallFour"), cgs.get("homeWalks")), None),
                away_ball_four=to_int(first_non_empty(cgs.get("awayBallFour"), cgs.get("awayWalks")), None),
                pitch_num=row[8],
                pitch_result=row[9],
                pts_pitch_id=row[10],
                speed_kph=row[11],
                stuff_text=row[12],
                category=classify_event(txt, row[8], row[9], row[10], row[13], row[5]),
                raw_payload=row[14] or {},
            )
        )
    return events


def _is_pa_end(event: EventRec) -> bool:
    txt = event.text or ""
    if event.category in {"baserunning", "review", "substitution", "header"}:
        return False
    return event.category == "bat_result" or _is_bat_result_text(txt)


def _event_has_pa_action(event: EventRec) -> bool:
    if event.category in {"pitch", "bat_result"}:
        return True
    if event.category == "baserunning":
        return not _is_neutral_baserunning_text(event.text or "")
    if event.category in {"header", "review", "substitution"}:
        return False

    txt = event.text or ""
    if _is_batter_intro_text(txt):
        return False
    if event.pitch_num is not None or event.pitch_result or event.pts_pitch_id:
        return True
    return bool(
        re.search(r"\d+\uad6c", txt)
        or "\ud53c\uce58\ud074\ub77d" in txt
        or "\ubab8\uc5d0 \ub9de\ub294 \ubcfc" in txt
        or "\ubcf4\ub110" in txt
    )


def _event_starts_new_pa(event: EventRec) -> bool:
    if not event.batter_id:
        return False
    return _event_has_pa_action(event) or _is_batter_intro_text(event.text or "")


def _resolve_baserunning_subject(
    event: EventRec,
    player_name_by_id: dict[str, str],
    name_to_player_id: dict[str, str],
) -> tuple[str | None, str | None]:
    runner_name = _extract_event_subject_name(event.text or "")
    if runner_name:
        runner_id = name_to_player_id.get(runner_name)
        if runner_id:
            return runner_id, runner_name
        batter_name = player_name_by_id.get(event.batter_id or "")
        if batter_name and batter_name == runner_name:
            return event.batter_id, runner_name
        return None, runner_name

    batter_name = player_name_by_id.get(event.batter_id or "")
    if batter_name:
        return event.batter_id, batter_name
    return event.batter_id, None


def _score_state(event: EventRec) -> dict[str, int | None]:
    return {
        "home_score": event.home_score,
        "away_score": event.away_score,
        "home_hits": event.home_hits,
        "away_hits": event.away_hits,
        "home_errors": event.home_errors,
        "away_errors": event.away_errors,
        "home_ball_four": event.home_ball_four,
        "away_ball_four": event.away_ball_four,
    }


def _state_delta(end_value: int | None, start_value: int | None) -> int | None:
    if end_value is None or start_value is None:
        return None
    return end_value - start_value


def _normalized_pitch_id(game_id: int, source_pitch_id: str | None) -> str | None:
    if not source_pitch_id:
        return None
    return f"{game_id}:{source_pitch_id}"


def _scoreboard_walk_count_from_text(text: str | None) -> int:
    txt = text or ""
    if any(keyword in txt for keyword in ("몸에 맞는 볼", "볼넷", "고의4구", "자동 고의4구")):
        return 1
    return 0


def _walk_count_from_text(text: str | None) -> int:
    txt = text or ""
    if "몸에 맞는 볼" in txt:
        return 0
    if any(keyword in txt for keyword in ("볼넷", "고의4구", "자동 고의4구")):
        return 1
    return 0


def _parse_baserunning_bases(event: EventRec) -> tuple[str | None, str | None, str | None]:
    text = event.text or ""
    transition = re.search(r"([123])루주자\s*[^ :]+\s*:.*([123])루까지 진루", text)
    if transition:
        return transition.group(1), transition.group(2), None

    home_in = re.search(r"([123])루주자\s*[^ :]+\s*:.*홈인", text)
    if home_in:
        return home_in.group(1), "H", None

    runner_out = re.search(r"([123])루주자\s*[^ :]+\s*:.*아웃", text)
    if runner_out:
        return runner_out.group(1), "OUT", None

    if "타자주자" in text:
        reached_base = _batter_reached_base(text)
        if reached_base:
            return "B", str(reached_base), None
        if "아웃" in text:
            return "B", "OUT", None

    if event.batter_id and "아웃" in text and ":" in text:
        return "B", "OUT", None
    return None, None, None


def _parse_review_details(text: str) -> dict[str, Any]:
    match = re.search(
        r"(?P<start>\d{1,2}:\d{2})\s*~\s*(?P<end>\d{1,2}:\d{2})(?:\s*\((?P<minutes>\d+)분간\))?\s*(?P<team>.+?)요청 비디오 판독:\s*(?P<target>.+?)\s*관련\s*(?P<original>[^→]+)→(?P<final>.+)$",
        text or "",
    )
    if not match:
        return {}

    minutes_text = match.group("minutes")
    duration_seconds = int(minutes_text) * 60 if minutes_text else None
    if duration_seconds is None:
        try:
            start_h, start_m = map(int, match.group("start").split(":"))
            end_h, end_m = map(int, match.group("end").split(":"))
            duration_seconds = max(0, ((end_h * 60 + end_m) - (start_h * 60 + start_m)) * 60)
        except ValueError:
            duration_seconds = None

    return {
        "request_team_name": match.group("team").strip(),
        "review_target_text": match.group("target").strip(),
        "original_call": match.group("original").strip(),
        "final_call": match.group("final").strip(),
        "started_at_text": match.group("start"),
        "ended_at_text": match.group("end"),
        "duration_seconds": duration_seconds,
    }


def _parse_substitution_details(raw_payload: dict[str, Any]) -> dict[str, Any]:
    player_change = raw_payload.get("playerChange") or {}
    in_player = player_change.get("inPlayer") or {}
    out_player = player_change.get("outPlayer") or {}
    return {
        "sub_type": player_change.get("type") or "other",
        "in_player_id": str(first_non_empty(in_player.get("playerId"), in_player.get("playerCode")) or "") or None,
        "out_player_id": str(first_non_empty(out_player.get("playerId"), out_player.get("playerCode")) or "") or None,
        "in_player_name": first_non_empty(in_player.get("playerName"), in_player.get("name")),
        "out_player_name": first_non_empty(out_player.get("playerName"), out_player.get("name")),
        "in_position": first_non_empty(in_player.get("playerPos"), in_player.get("position")),
        "out_position": first_non_empty(out_player.get("playerPos"), out_player.get("position")),
        "out_player_turn": out_player.get("outPlayerTurn"),
    }


def normalize_game_from_raw(conn: psycopg.Connection, raw_game_id: int) -> int:
    with conn.cursor() as cur:
        _ensure_pa_event_runner_columns(conn, cur)

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
        cur.execute(
            """
            SELECT DISTINCT p.player_id, p.player_name
            FROM players p
            JOIN game_roster_entries gre ON gre.player_id = p.player_id
            WHERE gre.game_id = %s
            """,
            (game_id,),
        )
        player_name_by_id = {row[0]: row[1] for row in cur.fetchall() if row[0]}
        name_to_player_id = {}
        for player_id, player_name in player_name_by_id.items():
            if player_name and player_name not in name_to_player_id:
                name_to_player_id[player_name] = player_id
        cur.execute(
            """
            SELECT gre.player_id, gre.team_id, gre.batting_order_slot
            FROM game_roster_entries gre
            WHERE gre.game_id = %s
              AND gre.player_id IS NOT NULL
            """,
            (game_id,),
        )
        team_id_by_player_id: dict[str, int] = {}
        batting_order_by_player_id: dict[str, int] = {}
        for player_id, team_id, batting_order_slot in cur.fetchall():
            if not player_id:
                continue
            if player_id not in team_id_by_player_id and team_id is not None:
                team_id_by_player_id[player_id] = team_id
            if player_id not in batting_order_by_player_id and batting_order_slot is not None:
                batting_order_by_player_id[player_id] = batting_order_slot

        cur.execute(
            """
            SELECT team_id, team_name_short, team_name_full
            FROM teams
            WHERE team_id IN (%s, %s)
            """,
            (home_team_id, away_team_id),
        )
        team_id_by_name: dict[str, int] = {}
        for team_id, team_name_short, team_name_full in cur.fetchall():
            for team_name in (team_name_short, team_name_full):
                if team_name and team_name not in team_id_by_name:
                    team_id_by_name[team_name] = team_id

        cur.execute(
            """
            SELECT raw_block_id, home_team_win_rate, away_team_win_rate, wpa_by_plate
            FROM raw_plate_metrics rpm
            WHERE EXISTS (
                SELECT 1
                FROM raw_relay_blocks rrb
                WHERE rrb.raw_game_id = %s
                  AND rrb.raw_block_id = rpm.raw_block_id
            )
            """,
            (raw_game_id,),
        )
        metric_by_block_id = {
            row[0]: {
                "home_win_rate_after": row[1],
                "away_win_rate_after": row[2],
                "wpa_by_plate": row[3],
            }
            for row in cur.fetchall()
        }

        inning_map: dict[tuple[int, str], int] = {}
        pa_counter = 0
        pa_in_half_counter: dict[tuple[int, str], int] = {}
        current_pa_id: int | None = None
        current_pa_key: tuple[int, str, str | None] | None = None
        current_pa_event_no = 0
        current_pa_has_action = False
        normalized_pitch_id_by_source: dict[str, str] = {}
        last_event_by_pa: dict[int, int] = {}
        event_seq_in_pa_by_pa: dict[int, int] = {}
        last_action_pa_id_by_half: dict[tuple[int, str], int] = {}
        runner_name_by_base = {1: None, 2: None, 3: None}
        runner_id_by_base = {1: None, 2: None, 3: None}
        pa_start_state: dict[int, dict[str, int | None]] = {}
        pa_end_state: dict[int, dict[str, int | None]] = {}
        pa_raw_block_id_by_id: dict[int, int | None] = {}
        pa_inning_id_by_id: dict[int, int] = {}
        pa_batter_id_by_id: dict[int, str | None] = {}
        pa_has_batter_action_by_id: dict[int, bool] = {}
        inning_start_state: dict[int, dict[str, int | None]] = {}
        inning_end_state: dict[int, dict[str, int | None]] = {}
        inning_half_by_id: dict[int, str] = {}

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
            inning_half_by_id[inning_id] = half
            if inning_id not in inning_start_state:
                inning_start_state[inning_id] = _score_state(ev)
            inning_end_state[inning_id] = _score_state(ev)

            pa_key = (inning_no, half, ev.batter_id)
            event_starts_new_pa = _event_starts_new_pa(ev)
            event_pa_id: int | None = None
            event_seq_in_pa: int | None = None
            if current_pa_id is not None and current_pa_key == pa_key:
                current_pa_event_no += 1
                event_pa_id = current_pa_id
                event_seq_in_pa = current_pa_event_no
            elif (
                current_pa_id is not None
                and not current_pa_has_action
                and current_pa_key is not None
                and current_pa_key[:2] == in_key
                and ev.category in {"baserunning", "review"}
                and ev.batter_id
                and current_pa_key[2] != ev.batter_id
            ):
                prior_action_pa_id = last_action_pa_id_by_half.get(in_key)
                if prior_action_pa_id is not None and prior_action_pa_id != current_pa_id:
                    event_pa_id = prior_action_pa_id
                    event_seq_in_pa_by_pa[event_pa_id] = event_seq_in_pa_by_pa.get(event_pa_id, 0) + 1
                    event_seq_in_pa = event_seq_in_pa_by_pa[event_pa_id]
            elif (
                current_pa_id is not None
                and not current_pa_has_action
                and current_pa_key is not None
                and current_pa_key[:2] == in_key
                and event_starts_new_pa
                and ev.batter_id
                and current_pa_key[2] != ev.batter_id
            ):
                cur.execute(
                    """
                    UPDATE plate_appearances
                    SET batter_id = %s,
                        pitcher_id = %s
                    WHERE pa_id = %s
                    """,
                    (ev.batter_id, ev.pitcher_id, current_pa_id),
                )
                current_pa_key = pa_key
                current_pa_event_no += 1
                event_pa_id = current_pa_id
                event_seq_in_pa = current_pa_event_no
            elif event_starts_new_pa:
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
                current_pa_event_no = 1
                current_pa_has_action = False
                event_pa_id = current_pa_id
                event_seq_in_pa = current_pa_event_no
                event_seq_in_pa_by_pa[current_pa_id] = current_pa_event_no
                pa_start_state[current_pa_id] = _score_state(ev)
                pa_raw_block_id_by_id[current_pa_id] = ev.raw_block_id
                pa_has_batter_action_by_id[current_pa_id] = False

            if event_pa_id is not None and event_pa_id not in pa_start_state:
                pa_start_state[event_pa_id] = _score_state(ev)
                pa_raw_block_id_by_id.setdefault(event_pa_id, ev.raw_block_id)
            if event_pa_id is not None:
                pa_end_state[event_pa_id] = _score_state(ev)
                pa_inning_id_by_id[event_pa_id] = inning_id
                pa_batter_id_by_id[event_pa_id] = ev.batter_id

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
                    home_score, away_score, home_hits, away_hits, home_errors, away_errors,
                    base1_runner_id, base2_runner_id, base3_runner_id,
                    base1_runner_name, base2_runner_name, base3_runner_name, raw_event_id, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING event_id
                """,
                (
                    game_id,
                    inning_id,
                    event_pa_id,
                    event_seq_game,
                    event_seq_in_pa,
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
                    ev.home_hits,
                    ev.away_hits,
                    ev.home_errors,
                    ev.away_errors,
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
            prev_pa_event_id = last_event_by_pa.get(event_pa_id) if event_pa_id is not None else None
            if False and (
                event_pa_id is not None
                and ev.category == "baserunning"
                and prev_pa_event_id
                and prev_pa_event_id != pa_event_id
                and any(k in (ev.text or "") for k in ("진루", "홈인", "아웃"))
            ):
                # 같은 PA 내 연결 이벤트(타구 결과 + 주루 후속)는 결과 상태를 이전 이벤트에도 반영
                cur.execute(
                    """
                    SELECT base1_runner_id, base2_runner_id, base3_runner_id,
                           base1_runner_name, base2_runner_name, base3_runner_name
                    FROM pa_events
                    WHERE event_id = %s
                    """,
                    (prev_pa_event_id,),
                )
                prev_runner = cur.fetchone() or (None, None, None, None, None, None)
                merged_id_1 = runner_id_by_base[1] if runner_id_by_base[1] else (prev_runner[0] if ev.base1 else None)
                merged_id_2 = runner_id_by_base[2] if runner_id_by_base[2] else (prev_runner[1] if ev.base2 else None)
                merged_id_3 = runner_id_by_base[3] if runner_id_by_base[3] else (prev_runner[2] if ev.base3 else None)
                merged_name_1 = runner_name_by_base[1] if runner_name_by_base[1] else (prev_runner[3] if ev.base1 else None)
                merged_name_2 = runner_name_by_base[2] if runner_name_by_base[2] else (prev_runner[4] if ev.base2 else None)
                merged_name_3 = runner_name_by_base[3] if runner_name_by_base[3] else (prev_runner[5] if ev.base3 else None)

                cur.execute(
                    """
                    UPDATE pa_events
                    SET base1_occupied = %s,
                        base2_occupied = %s,
                        base3_occupied = %s,
                        base1_runner_id = %s,
                        base2_runner_id = %s,
                        base3_runner_id = %s,
                        base1_runner_name = %s,
                        base2_runner_name = %s,
                        base3_runner_name = %s
                    WHERE event_id = %s
                    """,
                    (
                        ev.base1,
                        ev.base2,
                        ev.base3,
                        merged_id_1,
                        merged_id_2,
                        merged_id_3,
                        merged_name_1,
                        merged_name_2,
                        merged_name_3,
                        prev_pa_event_id,
                    ),
                )

            if event_pa_id is not None:
                last_event_by_pa[event_pa_id] = pa_event_id

            if event_pa_id is not None and _event_has_pa_action(ev):
                last_action_pa_id_by_half[in_key] = event_pa_id

            if ev.pts_pitch_id:
                normalized_pitch_id = _normalized_pitch_id(game_id, ev.pts_pitch_id)
                if normalized_pitch_id is None:
                    continue
                normalized_pitch_id_by_source[ev.pts_pitch_id] = normalized_pitch_id
                cur.execute(
                    """
                    INSERT INTO pitches (
                        pitch_id, source_pitch_id, game_id, inning_id, pa_id, event_id,
                        pitch_num, pitch_result, pitch_type_text, speed_kph,
                        balls_before, strikes_before, balls_after, strikes_after,
                        is_in_play, is_terminal_pitch
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (pitch_id)
                    DO UPDATE SET
                        source_pitch_id = EXCLUDED.source_pitch_id,
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
                        normalized_pitch_id,
                        ev.pts_pitch_id,
                        game_id,
                        inning_id,
                        event_pa_id,
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
                runner_player_id, runner_name_raw = _resolve_baserunning_subject(ev, player_name_by_id, name_to_player_id)
                start_base, end_base, related_fielder_sequence = _parse_baserunning_bases(ev)
                cur.execute(
                    """
                    INSERT INTO baserunning_events (
                        game_id, inning_id, pa_id, event_id,
                        runner_player_id, runner_name_raw, start_base, end_base, related_fielder_sequence, event_subtype,
                        is_out, outs_recorded, caused_by_error, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        game_id,
                        inning_id,
                        event_pa_id,
                        pa_event_id,
                        runner_player_id,
                        runner_name_raw,
                        start_base,
                        end_base,
                        related_fielder_sequence,
                        "steal" if "도루" in ev.text else "advance",
                        bool(outs_recorded),
                        outs_recorded,
                        bool("실책" in ev.text),
                        ev.text,
                    ),
                )

            if ev.category == "review":
                review_details = _parse_review_details(ev.text)
                cur.execute(
                    """
                    INSERT INTO review_events (
                        event_id, game_id, inning_id, pa_id,
                        request_team_id, subject_type, original_call, final_call,
                        review_target_text, started_at_text, ended_at_text, duration_seconds, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        pa_event_id,
                        game_id,
                        inning_id,
                        event_pa_id,
                        team_id_by_name.get(review_details.get("request_team_name", "")),
                        "play",
                        review_details.get("original_call"),
                        review_details.get("final_call"),
                        review_details.get("review_target_text", ev.text),
                        review_details.get("started_at_text"),
                        review_details.get("ended_at_text"),
                        review_details.get("duration_seconds"),
                        ev.text,
                    ),
                )

            if ev.category == "substitution":
                substitution_details = _parse_substitution_details(ev.raw_payload)
                team_id = (
                    team_id_by_player_id.get(substitution_details.get("out_player_id") or "")
                    or team_id_by_player_id.get(substitution_details.get("in_player_id") or "")
                )
                if substitution_details.get("in_player_id") and team_id:
                    team_id_by_player_id[substitution_details["in_player_id"]] = team_id
                cur.execute(
                    """
                    INSERT INTO substitution_events (
                        event_id, game_id, inning_id, pa_id,
                        team_id, sub_type, in_player_id, out_player_id,
                        in_player_name, out_player_name, in_position, out_position, out_player_turn, description
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        pa_event_id,
                        game_id,
                        inning_id,
                        event_pa_id,
                        team_id,
                        substitution_details.get("sub_type", "other"),
                        substitution_details.get("in_player_id"),
                        substitution_details.get("out_player_id"),
                        substitution_details.get("in_player_name"),
                        substitution_details.get("out_player_name"),
                        substitution_details.get("in_position"),
                        substitution_details.get("out_position"),
                        substitution_details.get("out_player_turn"),
                        ev.text,
                    ),
                )

            if ev.category == "bat_result" and event_pa_id is not None:
                cur.execute(
                    """
                    INSERT INTO batted_ball_results (
                        pa_id, event_id, pitch_id, result_code, result_text,
                        hit_flag, out_flag, error_flag, sacrifice_flag
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event_pa_id,
                        pa_event_id,
                        _normalized_pitch_id(game_id, ev.pts_pitch_id),
                        ev.pitch_result,
                        ev.text,
                        bool("안타" in ev.text or "홈런" in ev.text),
                        bool("아웃" in ev.text),
                        bool("실책" in ev.text),
                        bool("희생" in ev.text),
                    ),
                )

            if event_pa_id is not None:
                cur.execute(
                    """
                    UPDATE plate_appearances
                    SET end_seqno = %s,
                        end_pitch_num = COALESCE(%s, end_pitch_num),
                        balls_final = %s,
                        strikes_final = %s,
                        outs_after = %s,
                        bases_after = %s,
                        result_code = CASE WHEN %s THEN COALESCE(%s, result_code) ELSE result_code END,
                        result_text = CASE WHEN %s THEN %s ELSE result_text END,
                        is_terminal = CASE WHEN %s THEN TRUE ELSE COALESCE(is_terminal, FALSE) END
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
                        ev.pitch_result,
                        _is_pa_end(ev),
                        ev.text,
                        _is_pa_end(ev),
                        event_pa_id,
                    ),
                )

            if event_pa_id == current_pa_id and _event_has_pa_action(ev):
                current_pa_has_action = True
            if event_pa_id == current_pa_id and ev.category in {"pitch", "bat_result"}:
                pa_has_batter_action_by_id[event_pa_id] = True

            cur.execute(
                """
                UPDATE innings
                SET end_event_seqno = GREATEST(COALESCE(end_event_seqno, %s), %s)
                WHERE inning_id = %s
                """,
                (ev.seqno, ev.seqno, inning_id),
            )

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
            source_pitch_id = tr[0]
            if not source_pitch_id:
                continue
            normalized_pitch_id = normalized_pitch_id_by_source.get(source_pitch_id)
            if not normalized_pitch_id:
                continue
            cur.execute(
                """
                INSERT INTO pitch_tracking (
                    pitch_id, source_pitch_id, ballcount, cross_plate_x, cross_plate_y,
                    top_sz, bottom_sz, vx0, vy0, vz0, ax, ay, az, x0, y0, z0, stance
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pitch_id)
                DO UPDATE SET
                    source_pitch_id = EXCLUDED.source_pitch_id,
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
                (
                    normalized_pitch_id,
                    source_pitch_id,
                    tr[1],
                    tr[2],
                    tr[3],
                    tr[4],
                    tr[5],
                    tr[6],
                    tr[7],
                    tr[8],
                    tr[9],
                    tr[10],
                    tr[11],
                    tr[12],
                    tr[13],
                    tr[14],
                    tr[15],
                ),
            )

        pa_ids_without_action = [pa_id for pa_id, has_action in pa_has_batter_action_by_id.items() if not has_action]
        if pa_ids_without_action:
            cur.execute(
                "UPDATE pa_events SET pa_id = NULL, event_seq_in_pa = NULL WHERE pa_id = ANY(%s)",
                (pa_ids_without_action,),
            )
            cur.execute("UPDATE pitches SET pa_id = NULL WHERE pa_id = ANY(%s)", (pa_ids_without_action,))
            cur.execute("UPDATE baserunning_events SET pa_id = NULL WHERE pa_id = ANY(%s)", (pa_ids_without_action,))
            cur.execute("UPDATE review_events SET pa_id = NULL WHERE pa_id = ANY(%s)", (pa_ids_without_action,))
            cur.execute("UPDATE substitution_events SET pa_id = NULL WHERE pa_id = ANY(%s)", (pa_ids_without_action,))
            cur.execute("UPDATE batted_ball_results SET pa_id = NULL WHERE pa_id = ANY(%s)", (pa_ids_without_action,))
            cur.execute("DELETE FROM plate_appearances WHERE pa_id = ANY(%s)", (pa_ids_without_action,))
            for pa_id in pa_ids_without_action:
                pa_start_state.pop(pa_id, None)
                pa_end_state.pop(pa_id, None)
                pa_raw_block_id_by_id.pop(pa_id, None)
                pa_inning_id_by_id.pop(pa_id, None)
                pa_batter_id_by_id.pop(pa_id, None)

        cur.execute("UPDATE plate_appearances SET pa_seq_game = -pa_seq_game WHERE game_id = %s", (game_id,))
        cur.execute(
            """
            WITH ranked AS (
                SELECT
                    pa.pa_id,
                    ROW_NUMBER() OVER (ORDER BY pa.start_seqno, pa.pa_id) AS new_pa_seq_game,
                    ROW_NUMBER() OVER (PARTITION BY pa.inning_id ORDER BY pa.start_seqno, pa.pa_id) AS new_pa_seq_in_half
                FROM plate_appearances pa
                WHERE pa.game_id = %s
            )
            UPDATE plate_appearances pa
            SET pa_seq_game = ranked.new_pa_seq_game,
                pa_seq_in_half = ranked.new_pa_seq_in_half
            FROM ranked
            WHERE pa.pa_id = ranked.pa_id
            """,
            (game_id,),
        )

        for pa_id, start_state in pa_start_state.items():
            end_state = pa_end_state.get(pa_id, start_state)
            raw_block_id = pa_raw_block_id_by_id.get(pa_id)
            metric_row = metric_by_block_id.get(raw_block_id or -1, {})
            runs_scored = None
            if all(
                value is not None
                for value in (
                    start_state.get("home_score"),
                    start_state.get("away_score"),
                    end_state.get("home_score"),
                    end_state.get("away_score"),
                )
            ):
                runs_scored = (end_state["home_score"] - start_state["home_score"]) + (end_state["away_score"] - start_state["away_score"])
            cur.execute(
                """
                UPDATE plate_appearances
                SET batting_order_slot = COALESCE(%s, batting_order_slot),
                    runs_scored_on_pa = COALESCE(%s, runs_scored_on_pa),
                    wpa_by_plate = COALESCE(%s, wpa_by_plate),
                    home_win_rate_after = COALESCE(%s, home_win_rate_after),
                    away_win_rate_after = COALESCE(%s, away_win_rate_after)
                WHERE pa_id = %s
                """,
                (
                    batting_order_by_player_id.get(pa_batter_id_by_id.get(pa_id) or ""),
                    runs_scored,
                    metric_row.get("wpa_by_plate"),
                    metric_row.get("home_win_rate_after"),
                    metric_row.get("away_win_rate_after"),
                    pa_id,
                ),
            )

        for inning_id, start_state in inning_start_state.items():
            end_state = inning_end_state.get(inning_id, start_state)
            half = inning_half_by_id.get(inning_id, "top")
            if half == "top":
                runs_scored = _state_delta(end_state.get("away_score"), start_state.get("away_score"))
                hits_in_half = _state_delta(end_state.get("away_hits"), start_state.get("away_hits"))
                errors_in_half = _state_delta(end_state.get("home_errors"), start_state.get("home_errors"))
                walks_in_half = _state_delta(end_state.get("away_ball_four"), start_state.get("away_ball_four"))
            else:
                runs_scored = _state_delta(end_state.get("home_score"), start_state.get("home_score"))
                hits_in_half = _state_delta(end_state.get("home_hits"), start_state.get("home_hits"))
                errors_in_half = _state_delta(end_state.get("away_errors"), start_state.get("away_errors"))
                walks_in_half = _state_delta(end_state.get("home_ball_four"), start_state.get("home_ball_four"))
            cur.execute(
                """
                UPDATE innings
                SET runs_scored = COALESCE(%s, runs_scored),
                    hits_in_half = COALESCE(%s, hits_in_half),
                    errors_in_half = COALESCE(%s, errors_in_half),
                    walks_in_half = COALESCE(%s, walks_in_half)
                WHERE inning_id = %s
                """,
                (
                    runs_scored,
                    hits_in_half,
                    errors_in_half,
                    walks_in_half,
                    inning_id,
                ),
            )

    return game_id
