from __future__ import annotations

import copy
from dataclasses import dataclass, field
import re
from typing import Any

from common_utils import to_int

from .game_json import CURRENT_GAME_STATE_FIELDS
from .pa_scoring import score_relay_plate_appearances


JsonDict = dict[str, Any]

RESULT_TYPES = [
    "out",
    "single",
    "double",
    "triple",
    "home_run",
    "walk",
    "intentional_walk",
    "hit_by_pitch",
    "error",
    "fielders_choice",
    "sacrifice_bunt",
    "sacrifice_fly",
    "strikeout",
    "dropped_third",
    "double_play",
    "other",
]

EVENT_TEMPLATE_TYPES = ["pitch", "bat_result", "baserunning", "substitution", "review", "other"]
RUNNER_BASE_CHOICES = ["", "B", "1", "2", "3", "H", "OUT"]
DEFAULT_RESULT_TEXT = {
    "out": "\uc544\uc6c3",
    "single": "\uc548\ud0c0",
    "double": "2\ub8e8\ud0c0",
    "triple": "3\ub8e8\ud0c0",
    "home_run": "\ud648\ub7f0",
    "walk": "\ubcfc\ub137",
    "intentional_walk": "\uace0\uc7584\uad6c",
    "hit_by_pitch": "\ubab8\uc5d0 \ub9de\ub294 \ubcfc",
    "error": "\uc2e4\ucc45\uc73c\ub85c \ucd9c\ub8e8",
    "fielders_choice": "\uc57c\uc218\uc120\ud0dd",
    "sacrifice_bunt": "\ud76c\uc0dd\ubc88\ud2b8",
    "sacrifice_fly": "\ud76c\uc0dd\ud50c\ub77c\uc774",
    "strikeout": "\uc0bc\uc9c4 \uc544\uc6c3",
    "dropped_third": "\uc0bc\uc9c4 \ub0ab\uc544\uc6c3",
    "double_play": "\ubcd1\uc0b4\ud0c0",
    "other": "\uae30\ud0c0",
}
RESULT_TYPES_REQUIRING_BAT_RESULT = {
    "out",
    "single",
    "double",
    "triple",
    "home_run",
    "walk",
    "intentional_walk",
    "hit_by_pitch",
    "error",
    "fielders_choice",
    "sacrifice_bunt",
    "sacrifice_fly",
    "strikeout",
    "dropped_third",
    "double_play",
}
RUNNER_MOVE_RE = re.compile(r"(?:(?P<start>[123])\ub8e8\uc8fc\uc790|(?P<batter>\ud0c0\uc790\uc8fc\uc790))\s*(?P<name>[^ :]+)\s*:\s*(?P<action>.+)")
BATTER_INTRO_RE = re.compile(r"^(?:(?P<order>\d+)\ubc88\ud0c0\uc790|\ub300\ud0c0)\s+(?P<name>\S+)")


@dataclass(slots=True)
class PlayerInfo:
    player_id: str
    name: str = ""
    bat_order: int | None = None
    side: str | None = None


@dataclass(slots=True)
class RunnerMove:
    start: str
    end: str
    runner_id: str | None = None
    runner_name: str | None = None
    source: str = "explicit"


@dataclass(slots=True)
class EventRef:
    group_index: int
    block_index: int
    event_index: int


@dataclass(slots=True)
class PlateAppearanceSummary:
    group_index: int
    block_index: int
    start_index: int
    end_index: int
    batter_id: str | None
    batter_name: str | None
    pitcher_id: str | None
    result_type: str | None
    result_text: str
    is_terminal: bool


@dataclass(slots=True)
class RebuildEventDelta:
    ref: EventRef
    changed_fields: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RebuildReport:
    deltas: list[RebuildEventDelta]
    batter_runs: dict[str, dict[str, int]]
    batter_rbi: dict[str, dict[str, int]]
    pitcher_outs: dict[str, dict[str, int]]
    pitcher_runs: dict[str, dict[str, int]]
    batter_steals: dict[str, dict[str, int]]


def _default_state() -> JsonDict:
    return {
        "homeScore": 0,
        "awayScore": 0,
        "homeHit": 0,
        "awayHit": 0,
        "homeBallFour": 0,
        "awayBallFour": 0,
        "homeError": 0,
        "awayError": 0,
        "pitcher": None,
        "batter": None,
        "strike": 0,
        "ball": 0,
        "out": 0,
        "base1": False,
        "base2": False,
        "base3": False,
    }


def _copy_state(state: JsonDict) -> JsonDict:
    copied = {key: state.get(key) for key in CURRENT_GAME_STATE_FIELDS}
    for key in ("base1", "base2", "base3"):
        copied[key] = bool(copied.get(key))
    return copied


def _safe_int(value: Any, default: int = 0) -> int:
    parsed = to_int(value, default)
    return default if parsed is None else int(parsed)


def _normalize_player_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _normalize_half(home_or_away: Any) -> str:
    return "top" if str(home_or_away) == "0" else "bottom"


def _offense_side(home_or_away: Any) -> str:
    return "away" if str(home_or_away) == "0" else "home"


def _defense_side(home_or_away: Any) -> str:
    return "home" if str(home_or_away) == "0" else "away"


def _event_batter_id(event: JsonDict) -> str | None:
    return _normalize_player_id((event.get("currentGameState") or {}).get("batter") or (event.get("batterRecord") or {}).get("pcode"))


def _event_pitcher_id(event: JsonDict) -> str | None:
    return _normalize_player_id((event.get("currentGameState") or {}).get("pitcher"))


def _event_text(event: JsonDict) -> str:
    return str(event.get("text") or "")


def _is_batter_intro_text(text: str) -> bool:
    return bool(BATTER_INTRO_RE.match(text or ""))


def _event_category(event: JsonDict) -> str:
    text = _event_text(event)
    pitch_num = event.get("pitchNum")
    pitch_result = str(event.get("pitchResult") or "").strip()
    pts_pitch_id = str(event.get("ptsPitchId") or "").strip()
    player_change = event.get("playerChange") or {}
    type_code = _safe_int(event.get("type"), 0)
    if type_code in (13, 23):
        return "bat_result"
    if parse_result_type(text) in RESULT_TYPES_REQUIRING_BAT_RESULT:
        return "bat_result"
    if pitch_num not in (None, "") or pitch_result or pts_pitch_id:
        return "pitch"
    if player_change:
        return "substitution"
    if "\ube44\ub514\uc624\ud310\ub3c5" in text:
        return "review"
    if RUNNER_MOVE_RE.match(text.strip()):
        return "baserunning"
    if _is_batter_intro_text(text):
        return "intro"
    return "other"


def _event_starts_new_pa(event: JsonDict) -> bool:
    batter_id = _event_batter_id(event)
    if not batter_id:
        return False
    category = _event_category(event)
    return category in {"pitch", "bat_result", "intro"}


def _event_starts_new_pa_in_context(event: JsonDict, current_batter: str | None) -> bool:
    batter_id = _event_batter_id(event)
    if not batter_id:
        return False
    category = _event_category(event)
    if category == "intro":
        return True
    if category not in {"pitch", "bat_result"}:
        return False
    if current_batter is None:
        return True
    return batter_id != current_batter


def _is_terminal_event(event: JsonDict) -> bool:
    if _event_category(event) == "bat_result":
        return True
    result_type = parse_result_type(_event_text(event))
    return result_type in RESULT_TYPES_REQUIRING_BAT_RESULT


def _flatten_block_events(payload: JsonDict) -> list[tuple[EventRef, JsonDict, JsonDict]]:
    rows: list[tuple[EventRef, JsonDict, JsonDict]] = []
    for group_index, inning_group in enumerate(payload.get("relay") or []):
        for block_index, block in enumerate(inning_group or []):
            for event_index, event in enumerate(block.get("textOptions") or []):
                rows.append((EventRef(group_index, block_index, event_index), block, event))
    return rows


def build_player_index(payload: JsonDict) -> dict[str, PlayerInfo]:
    index: dict[str, PlayerInfo] = {}

    def consume_rows(rows: list[JsonDict], side: str) -> None:
        for row in rows:
            player_id = _normalize_player_id(row.get("playerCode") or row.get("pcode") or row.get("playerId"))
            if not player_id:
                continue
            entry = index.setdefault(player_id, PlayerInfo(player_id=player_id))
            entry.name = str(row.get("playerName") or row.get("name") or entry.name or "")
            if row.get("batorder") not in (None, ""):
                entry.bat_order = _safe_int(row.get("batorder"))
            elif row.get("batOrder") not in (None, ""):
                entry.bat_order = _safe_int(row.get("batOrder"))
            entry.side = side

    lineup = payload.get("lineup") or {}
    for side in ("home", "away"):
        consume_rows(lineup.get(f"{side}_starter") or [], side)
        consume_rows(lineup.get(f"{side}_bullpen") or [], side)
        consume_rows(lineup.get(f"{side}_candidate") or [], side)

    record = payload.get("record") or {}
    consume_rows((record.get("batter") or {}).get("home") or [], "home")
    consume_rows((record.get("batter") or {}).get("away") or [], "away")
    consume_rows((record.get("pitcher") or {}).get("home") or [], "home")
    consume_rows((record.get("pitcher") or {}).get("away") or [], "away")

    for _ref, _block, event in _flatten_block_events(payload):
        batter_id = _event_batter_id(event)
        if batter_id:
            index.setdefault(batter_id, PlayerInfo(player_id=batter_id))
        pitcher_id = _event_pitcher_id(event)
        if pitcher_id:
            index.setdefault(pitcher_id, PlayerInfo(player_id=pitcher_id))
        for side_key in ("inPlayer", "outPlayer"):
            player_row = (event.get("playerChange") or {}).get(side_key) or {}
            player_id = _normalize_player_id(player_row.get("playerId") or player_row.get("playerCode"))
            if player_id:
                entry = index.setdefault(player_id, PlayerInfo(player_id=player_id))
                entry.name = str(player_row.get("playerName") or player_row.get("name") or entry.name or "")
    return index


def _player_name(player_index: dict[str, PlayerInfo], player_id: str | None, fallback: str | None = None) -> str:
    if player_id and player_id in player_index and player_index[player_id].name:
        return player_index[player_id].name
    return str(fallback or player_id or "")


def _intro_text(player_index: dict[str, PlayerInfo], batter_id: str, batter_name: str | None = None) -> str:
    info = player_index.get(batter_id)
    order = info.bat_order if info else None
    name = _player_name(player_index, batter_id, batter_name)
    if order:
        return f"{order}\ubc88\ud0c0\uc790 {name}"
    return f"\ud0c0\uc790 {name}"


def _result_label(result_type: str, detail: str | None = None) -> str:
    detail_text = str(detail or "").strip()
    if detail_text:
        if result_type == "double" and "2\ub8e8\ud0c0" not in detail_text:
            return f"{detail_text} 2\ub8e8\ud0c0"
        if result_type == "triple" and "3\ub8e8\ud0c0" not in detail_text:
            return f"{detail_text} 3\ub8e8\ud0c0"
        if result_type == "single" and not any(keyword in detail_text for keyword in ("\uc548\ud0c0", "1\ub8e8\ud0c0")):
            return f"{detail_text} \uc548\ud0c0"
        return detail_text
    return DEFAULT_RESULT_TEXT.get(result_type, DEFAULT_RESULT_TEXT["other"])


def _pitch_label(pitch_result: str | None, text: str | None = None) -> str:
    if text:
        return text
    token = str(pitch_result or "").strip().upper()
    mapping = {
        "B": "\ubcfc",
        "I": "\ubcfc",
        "BALL": "\ubcfc",
        "S": "\uc2a4\ud2b8\ub77c\uc774\ud06c",
        "C": "\uc2a4\ud2b8\ub77c\uc774\ud06c",
        "SW": "\ud5db\uc2a4\uc719 \uc2a4\ud2b8\ub77c\uc774\ud06c",
        "F": "\ud30c\uc6b8",
        "FOUL": "\ud30c\uc6b8",
        "K": "\uc0bc\uc9c4",
        "X": "\ud0c0\uaca9",
        "INPLAY": "\ud0c0\uaca9",
    }
    return mapping.get(token, token or "\ud22c\uad6c")


def parse_result_type(text: str) -> str | None:
    txt = text or ""
    if "\ud648\ub7f0" in txt:
        return "home_run"
    if "3\ub8e8\ud0c0" in txt:
        return "triple"
    if "2\ub8e8\ud0c0" in txt:
        return "double"
    if "\uace0\uc7584\uad6c" in txt or "\uc790\ub3d9 \uace0\uc7584\uad6c" in txt:
        return "intentional_walk"
    if "\ubab8\uc5d0 \ub9de\ub294 \ubcfc" in txt:
        return "hit_by_pitch"
    if "\ubcfc\ub137" in txt:
        return "walk"
    if "\ud76c\uc0dd\ud50c\ub77c\uc774" in txt:
        return "sacrifice_fly"
    if "\ud76c\uc0dd\ubc88\ud2b8" in txt:
        return "sacrifice_bunt"
    if "\ubcd1\uc0b4" in txt:
        return "double_play"
    if "\uc57c\uc218\uc120\ud0dd" in txt:
        return "fielders_choice"
    if "\uc2e4\ucc45" in txt and "\ucd9c\ub8e8" in txt:
        return "error"
    if "\ub0ab\uc544\uc6c3" in txt:
        return "dropped_third"
    if "\uc0bc\uc9c4" in txt:
        return "strikeout"
    if "\uc548\ud0c0" in txt or "1\ub8e8\ud0c0" in txt:
        return "single"
    if "\uc544\uc6c3" in txt:
        return "out"
    return None


def build_event_template(
    payload: JsonDict,
    *,
    template_type: str,
    batter_id: str | None = None,
    batter_name: str | None = None,
    pitcher_id: str | None = None,
    result_type: str | None = None,
    detail: str | None = None,
    pitch_result: str | None = None,
    pitch_num: int | None = None,
    pts_pitch_id: str | None = None,
    text: str | None = None,
    player_change: JsonDict | None = None,
) -> JsonDict:
    player_index = build_player_index(payload)
    event: JsonDict = {
        "seqno": None,
        "type": 1,
        "text": "",
        "currentGameState": _default_state(),
    }
    if batter_id:
        event["currentGameState"]["batter"] = batter_id
        event["batterRecord"] = {"pcode": batter_id}
    if pitcher_id:
        event["currentGameState"]["pitcher"] = pitcher_id
    if template_type == "pitch":
        event["type"] = 1
        event["pitchNum"] = pitch_num
        if pitch_result:
            event["pitchResult"] = pitch_result
        if pts_pitch_id:
            event["ptsPitchId"] = pts_pitch_id
        label = _pitch_label(pitch_result, text)
        if batter_id:
            event["text"] = f"{_player_name(player_index, batter_id, batter_name)} : {label}"
        else:
            event["text"] = label
        return event
    if template_type == "bat_result":
        event["type"] = 13
        event["pitchNum"] = pitch_num
        if pitch_result:
            event["pitchResult"] = pitch_result
        if pts_pitch_id:
            event["ptsPitchId"] = pts_pitch_id
        label = text or _result_label(result_type or "other", detail)
        batter_label = _player_name(player_index, batter_id, batter_name)
        event["text"] = f"{batter_label} : {label}" if batter_label else label
        return event
    if template_type == "baserunning":
        event["type"] = 2
        event["text"] = text or "\uc8fc\ub8e8 \uc774\ubca4\ud2b8"
        return event
    if template_type == "substitution":
        event["type"] = 14
        event["text"] = text or "\uc120\uc218 \uad50\uccb4"
        if player_change:
            event["playerChange"] = copy.deepcopy(player_change)
        return event
    if template_type == "review":
        event["type"] = 98
        event["text"] = text or "\ube44\ub514\uc624\ud310\ub3c5"
        return event
    event["type"] = 99
    event["text"] = text or "\uae30\ud0c0 \uc774\ubca4\ud2b8"
    return event


def build_runner_text(move: RunnerMove) -> str:
    name = move.runner_name or move.runner_id or "\uc8fc\uc790"
    prefix = "\ud0c0\uc790\uc8fc\uc790" if move.start == "B" else f"{move.start}\ub8e8\uc8fc\uc790"
    if move.end == "H":
        action = "\ud648\uc778"
    elif move.end == "OUT":
        action = "\uc544\uc6c3"
    else:
        action = f"{move.end}\ub8e8\uae4c\uc9c0 \uc9c4\ub8e8"
    return f"{prefix} {name} : {action}"


def build_runner_events(payload: JsonDict, runner_moves: list[RunnerMove], *, pitcher_id: str | None = None, batter_id: str | None = None) -> list[JsonDict]:
    events: list[JsonDict] = []
    for move in runner_moves:
        event = build_event_template(
            payload,
            template_type="baserunning",
            pitcher_id=pitcher_id,
            batter_id=batter_id,
            text=build_runner_text(move),
        )
        events.append(event)
    return events


def _empty_stat_bucket() -> dict[str, dict[str, int]]:
    return {"home": {}, "away": {}}


def _bump_stat(bucket: dict[str, dict[str, int]], side: str, player_id: str | None, amount: int = 1) -> None:
    if not player_id:
        return
    bucket.setdefault(side, {})
    bucket[side][player_id] = int(bucket[side].get(player_id, 0) or 0) + amount


def _first_pitcher_for_side(payload: JsonDict, side: str) -> str | None:
    starters = (payload.get("lineup") or {}).get(f"{side}_starter") or []
    for row in starters:
        if str(row.get("position") or "") == "1":
            return _normalize_player_id(row.get("playerCode"))
    game_info = (payload.get("lineup") or {}).get("game_info") or {}
    key = "hPCode" if side == "home" else "aPCode"
    return _normalize_player_id(game_info.get(key))


def _first_batter_for_side(payload: JsonDict, side: str) -> str | None:
    starters = (payload.get("lineup") or {}).get(f"{side}_starter") or []
    candidates: list[tuple[int, str]] = []
    for row in starters:
        if str(row.get("position") or "") == "1":
            continue
        player_id = _normalize_player_id(row.get("playerCode"))
        if not player_id:
            continue
        order = _safe_int(row.get("batorder"), 999)
        candidates.append((order, player_id))
    return sorted(candidates)[0][1] if candidates else None


def _seed_state_from_payload(payload: JsonDict) -> JsonDict:
    seed = _default_state()
    for _ref, _block, event in _flatten_block_events(payload):
        state = event.get("currentGameState") or {}
        for key in CURRENT_GAME_STATE_FIELDS:
            if state.get(key) not in (None, ""):
                if key in {"base1", "base2", "base3"}:
                    seed[key] = bool(state.get(key))
                else:
                    seed[key] = state.get(key)
        if any(state.get(key) not in (None, "") for key in CURRENT_GAME_STATE_FIELDS):
            break
    if not seed.get("pitcher"):
        seed["pitcher"] = _first_pitcher_for_side(payload, "home")
    if not seed.get("batter"):
        seed["batter"] = _first_batter_for_side(payload, "away")
    return seed


def _base_slots_empty() -> dict[str, dict[str, str | None]]:
    return {
        "1": {"id": None, "name": None},
        "2": {"id": None, "name": None},
        "3": {"id": None, "name": None},
    }


def _clear_counts(state: JsonDict) -> None:
    state["ball"] = 0
    state["strike"] = 0


def _clear_bases(state: JsonDict, base_slots: dict[str, dict[str, str | None]]) -> None:
    for base in ("1", "2", "3"):
        base_slots[base] = {"id": None, "name": None}
        state[f"base{base}"] = False


def _apply_base_flags(state: JsonDict, base_slots: dict[str, dict[str, str | None]]) -> None:
    state["base1"] = bool(base_slots["1"]["id"] or base_slots["1"]["name"])
    state["base2"] = bool(base_slots["2"]["id"] or base_slots["2"]["name"])
    state["base3"] = bool(base_slots["3"]["id"] or base_slots["3"]["name"])


def _runner_from_slot(base_slots: dict[str, dict[str, str | None]], base: str) -> dict[str, str | None]:
    return dict(base_slots.get(base, {"id": None, "name": None}))


def _set_runner_slot(base_slots: dict[str, dict[str, str | None]], base: str, runner_id: str | None, runner_name: str | None) -> None:
    base_slots[base] = {"id": runner_id, "name": runner_name}


def _score_run(
    state: JsonDict,
    offense_side: str,
    defense_side: str,
    runner_id: str | None,
    runner_name: str | None,
    batter_id: str | None,
    batter_runs: dict[str, dict[str, int]],
    batter_rbi: dict[str, dict[str, int]],
    pitcher_runs: dict[str, dict[str, int]],
    credit_rbi: bool,
) -> None:
    score_key = "awayScore" if offense_side == "away" else "homeScore"
    state[score_key] = _safe_int(state.get(score_key), 0) + 1
    _bump_stat(batter_runs, offense_side, runner_id, 1)
    if credit_rbi:
        _bump_stat(batter_rbi, offense_side, batter_id, 1)
    _bump_stat(pitcher_runs, defense_side, _normalize_player_id(state.get("pitcher")), 1)
    if not runner_id and runner_name:
        _bump_stat(batter_runs, offense_side, runner_name, 1)


def _runner_move_sort_key(move: RunnerMove) -> tuple[int, int]:
    start_order = {"3": 3, "2": 2, "1": 1, "B": 0}
    end_order = {"OUT": -1, "H": 4, "3": 3, "2": 2, "1": 1}
    return (start_order.get(move.start, 0), end_order.get(move.end, 0))


def _forced_walk_moves(base_slots: dict[str, dict[str, str | None]], batter_id: str | None, batter_name: str | None) -> list[RunnerMove]:
    moves: list[RunnerMove] = [RunnerMove(start="B", end="1", runner_id=batter_id, runner_name=batter_name, source="default")]
    if base_slots["1"]["id"] or base_slots["1"]["name"]:
        moves.append(RunnerMove(start="1", end="2", runner_id=base_slots["1"]["id"], runner_name=base_slots["1"]["name"], source="default"))
    if base_slots["1"]["id"] or base_slots["1"]["name"]:
        if base_slots["2"]["id"] or base_slots["2"]["name"]:
            moves.append(RunnerMove(start="2", end="3", runner_id=base_slots["2"]["id"], runner_name=base_slots["2"]["name"], source="default"))
    if (base_slots["1"]["id"] or base_slots["1"]["name"]) and (base_slots["2"]["id"] or base_slots["2"]["name"]) and (base_slots["3"]["id"] or base_slots["3"]["name"]):
        moves.append(RunnerMove(start="3", end="H", runner_id=base_slots["3"]["id"], runner_name=base_slots["3"]["name"], source="default"))
    return moves


def _hit_default_moves(result_type: str, base_slots: dict[str, dict[str, str | None]], batter_id: str | None, batter_name: str | None) -> list[RunnerMove]:
    if result_type == "single":
        defaults = [("3", "H"), ("2", "3"), ("1", "2"), ("B", "1")]
    elif result_type == "double":
        defaults = [("3", "H"), ("2", "H"), ("1", "3"), ("B", "2")]
    elif result_type == "triple":
        defaults = [("3", "H"), ("2", "H"), ("1", "H"), ("B", "3")]
    else:
        defaults = [("3", "H"), ("2", "H"), ("1", "H"), ("B", "H")]
    moves: list[RunnerMove] = []
    for start, end in defaults:
        if start == "B":
            moves.append(RunnerMove(start="B", end=end, runner_id=batter_id, runner_name=batter_name, source="default"))
            continue
        runner = base_slots[start]
        if runner["id"] or runner["name"]:
            moves.append(RunnerMove(start=start, end=end, runner_id=runner["id"], runner_name=runner["name"], source="default"))
    return moves


def _advance_all_one(base_slots: dict[str, dict[str, str | None]], batter_id: str | None, batter_name: str | None, *, score_runner_on_third: bool) -> list[RunnerMove]:
    moves: list[RunnerMove] = []
    if base_slots["3"]["id"] or base_slots["3"]["name"]:
        moves.append(
            RunnerMove(
                start="3",
                end="H" if score_runner_on_third else "3",
                runner_id=base_slots["3"]["id"],
                runner_name=base_slots["3"]["name"],
                source="default",
            )
        )
    if base_slots["2"]["id"] or base_slots["2"]["name"]:
        moves.append(RunnerMove(start="2", end="3", runner_id=base_slots["2"]["id"], runner_name=base_slots["2"]["name"], source="default"))
    if base_slots["1"]["id"] or base_slots["1"]["name"]:
        moves.append(RunnerMove(start="1", end="2", runner_id=base_slots["1"]["id"], runner_name=base_slots["1"]["name"], source="default"))
    if batter_id or batter_name:
        moves.append(RunnerMove(start="B", end="OUT", runner_id=batter_id, runner_name=batter_name, source="default"))
    return moves


def _double_play_moves(base_slots: dict[str, dict[str, str | None]], batter_id: str | None, batter_name: str | None) -> list[RunnerMove]:
    moves = [RunnerMove(start="B", end="OUT", runner_id=batter_id, runner_name=batter_name, source="default")]
    for base in ("1", "2", "3"):
        runner = base_slots[base]
        if runner["id"] or runner["name"]:
            moves.append(RunnerMove(start=base, end="OUT", runner_id=runner["id"], runner_name=runner["name"], source="default"))
            break
    return moves


def _fielders_choice_moves(base_slots: dict[str, dict[str, str | None]], batter_id: str | None, batter_name: str | None) -> list[RunnerMove]:
    moves = [RunnerMove(start="B", end="1", runner_id=batter_id, runner_name=batter_name, source="default")]
    for base in ("3", "2", "1"):
        runner = base_slots[base]
        if runner["id"] or runner["name"]:
            moves.append(RunnerMove(start=base, end="OUT", runner_id=runner["id"], runner_name=runner["name"], source="default"))
            break
    return moves


def _default_terminal_moves(result_type: str, base_slots: dict[str, dict[str, str | None]], batter_id: str | None, batter_name: str | None) -> list[RunnerMove]:
    if result_type in {"single", "double", "triple", "home_run"}:
        return _hit_default_moves(result_type, base_slots, batter_id, batter_name)
    if result_type in {"walk", "intentional_walk", "hit_by_pitch", "error"}:
        return _forced_walk_moves(base_slots, batter_id, batter_name)
    if result_type == "fielders_choice":
        return _fielders_choice_moves(base_slots, batter_id, batter_name)
    if result_type == "dropped_third":
        return _forced_walk_moves(base_slots, batter_id, batter_name)
    if result_type == "sacrifice_bunt":
        return _advance_all_one(base_slots, batter_id, batter_name, score_runner_on_third=False)
    if result_type == "sacrifice_fly":
        return _advance_all_one(base_slots, batter_id, batter_name, score_runner_on_third=True)
    if result_type == "double_play":
        return _double_play_moves(base_slots, batter_id, batter_name)
    if result_type in {"strikeout", "out", "other"}:
        return [RunnerMove(start="B", end="OUT", runner_id=batter_id, runner_name=batter_name, source="default")]
    return []


def _parse_runner_move(text: str, player_index: dict[str, PlayerInfo]) -> RunnerMove | None:
    match = RUNNER_MOVE_RE.match(text.strip())
    if not match:
        return None
    name = match.group("name").strip()
    action = match.group("action").strip()
    start = "B" if match.group("batter") else match.group("start")
    end = ""
    if "\ud648\uc778" in action:
        end = "H"
    elif "\uc544\uc6c3" in action:
        end = "OUT"
    else:
        end_match = re.search(r"([123])\ub8e8\uae4c\uc9c0 \uc9c4\ub8e8", action)
        if end_match:
            end = end_match.group(1)
    if not start or not end:
        return None
    runner_id = None
    for player_id, info in player_index.items():
        if info.name == name:
            runner_id = player_id
            break
    return RunnerMove(start=start, end=end, runner_id=runner_id, runner_name=name)


def _apply_runner_move(
    state: JsonDict,
    base_slots: dict[str, dict[str, str | None]],
    move: RunnerMove,
    *,
    offense_side: str,
    defense_side: str,
    batter_id: str | None,
    batter_name: str | None,
    batter_runs: dict[str, dict[str, int]],
    batter_rbi: dict[str, dict[str, int]],
    pitcher_outs: dict[str, dict[str, int]],
    pitcher_runs: dict[str, dict[str, int]],
    credit_rbi: bool,
) -> None:
    if move.start == "B":
        runner_id = move.runner_id or batter_id
        runner_name = move.runner_name or batter_name
    else:
        runner = _runner_from_slot(base_slots, move.start)
        runner_id = runner["id"] or move.runner_id
        runner_name = runner["name"] or move.runner_name
        _set_runner_slot(base_slots, move.start, None, None)

    if move.end in {"1", "2", "3"}:
        _set_runner_slot(base_slots, move.end, runner_id, runner_name)
    elif move.end == "H":
        _score_run(
            state,
            offense_side,
            defense_side,
            runner_id,
            runner_name,
            batter_id,
            batter_runs,
            batter_rbi,
            pitcher_runs,
            credit_rbi=credit_rbi,
        )
    elif move.end == "OUT":
        state["out"] = _safe_int(state.get("out"), 0) + 1
        _bump_stat(pitcher_outs, defense_side, _normalize_player_id(state.get("pitcher")), 1)
    _apply_base_flags(state, base_slots)


def _apply_pitch_result_to_count(state: JsonDict, pitch_result: str | None, text: str) -> None:
    token = str(pitch_result or "").strip().upper()
    if token in {"B", "BALL", "I"} or ("\ubcfc" in text and "\ubcfc\ub137" not in text):
        state["ball"] = min(_safe_int(state.get("ball"), 0) + 1, 4)
        return
    if token in {"S", "C", "SW", "K"} or "\uc2a4\ud2b8\ub77c\uc774\ud06c" in text or "\ud5db\uc2a4\uc719" in text:
        state["strike"] = min(_safe_int(state.get("strike"), 0) + 1, 3)
        return
    if token in {"F", "FOUL"} or "\ud30c\uc6b8" in text:
        state["strike"] = min(_safe_int(state.get("strike"), 0) + (0 if _safe_int(state.get("strike"), 0) >= 2 else 1), 2)


def _scoreboard_delta_for_result(result_type: str) -> tuple[int, int, int]:
    hit = 1 if result_type in {"single", "double", "triple", "home_run"} else 0
    walk = 1 if result_type in {"walk", "intentional_walk", "hit_by_pitch"} else 0
    error = 1 if result_type == "error" else 0
    return hit, walk, error


def _apply_terminal_result(
    state: JsonDict,
    base_slots: dict[str, dict[str, str | None]],
    *,
    result_type: str,
    batter_id: str | None,
    batter_name: str | None,
    runner_moves: list[RunnerMove],
    offense_side: str,
    defense_side: str,
    batter_runs: dict[str, dict[str, int]],
    batter_rbi: dict[str, dict[str, int]],
    pitcher_outs: dict[str, dict[str, int]],
    pitcher_runs: dict[str, dict[str, int]],
) -> None:
    hit_delta, walk_delta, error_delta = _scoreboard_delta_for_result(result_type)
    hit_key = "awayHit" if offense_side == "away" else "homeHit"
    walk_key = "awayBallFour" if offense_side == "away" else "homeBallFour"
    error_key = "homeError" if defense_side == "home" else "awayError"
    state[hit_key] = _safe_int(state.get(hit_key), 0) + hit_delta
    state[walk_key] = _safe_int(state.get(walk_key), 0) + walk_delta
    state[error_key] = _safe_int(state.get(error_key), 0) + error_delta

    credit_rbi = result_type in {
        "single",
        "double",
        "triple",
        "home_run",
        "walk",
        "intentional_walk",
        "hit_by_pitch",
        "sacrifice_fly",
    }
    ordered_moves = sorted(runner_moves, key=_runner_move_sort_key, reverse=True)
    for move in ordered_moves:
        _apply_runner_move(
            state,
            base_slots,
            move,
            offense_side=offense_side,
            defense_side=defense_side,
            batter_id=batter_id,
            batter_name=batter_name,
            batter_runs=batter_runs,
            batter_rbi=batter_rbi,
            pitcher_outs=pitcher_outs,
            pitcher_runs=pitcher_runs,
            credit_rbi=credit_rbi and move.end == "H",
        )


def _capture_state_fields(event: JsonDict) -> JsonDict:
    state = event.get("currentGameState") or {}
    captured = {}
    for key in CURRENT_GAME_STATE_FIELDS:
        value = state.get(key)
        if key in {"base1", "base2", "base3"}:
            captured[key] = bool(value)
        else:
            captured[key] = value
    return captured


def _set_event_state(event: JsonDict, state: JsonDict) -> None:
    event["currentGameState"] = _copy_state(state)
    batter_id = _normalize_player_id(state.get("batter"))
    if batter_id and _event_category(event) in {"pitch", "bat_result"}:
        event["batterRecord"] = {"pcode": batter_id}


def rebuild_payload(payload: JsonDict, *, renumber_seq: bool = True, sync_record: bool = True) -> tuple[JsonDict, RebuildReport]:
    rebuilt = copy.deepcopy(payload)
    relay = rebuilt.get("relay") or []
    player_index = build_player_index(rebuilt)

    state = _seed_state_from_payload(rebuilt)
    base_slots = _base_slots_empty()
    batter_runs = _empty_stat_bucket()
    batter_rbi = _empty_stat_bucket()
    pitcher_outs = _empty_stat_bucket()
    pitcher_runs = _empty_stat_bucket()
    batter_steals = _empty_stat_bucket()
    deltas: list[RebuildEventDelta] = []
    previous_half_key: tuple[int | None, str | None] | None = None
    next_seq = 1
    pending_count_reset = False

    for group_index, inning_group in enumerate(relay):
        for block_index, block in enumerate(inning_group or []):
            inning_no = _safe_int(block.get("inn"), 0)
            half = _normalize_half(block.get("homeOrAway"))
            half_key = (inning_no, half)
            if previous_half_key is not None and half_key != previous_half_key:
                state["out"] = 0
                _clear_counts(state)
                _clear_bases(state, base_slots)
                state["pitcher"] = _first_pitcher_for_side(rebuilt, _defense_side(block.get("homeOrAway"))) or state.get("pitcher")
                state["batter"] = _first_batter_for_side(rebuilt, _offense_side(block.get("homeOrAway"))) or state.get("batter")
            previous_half_key = half_key
            offense_side = _offense_side(block.get("homeOrAway"))
            defense_side = _defense_side(block.get("homeOrAway"))

            for event_index, event in enumerate(block.get("textOptions") or []):
                category = _event_category(event)
                before = _capture_state_fields(event)
                text = _event_text(event)
                if renumber_seq:
                    event["seqno"] = next_seq
                    next_seq += 1

                explicit_batter = _event_batter_id(event)
                explicit_pitcher = _event_pitcher_id(event)
                if pending_count_reset and category in {"intro", "pitch", "bat_result"}:
                    _clear_counts(state)
                    pending_count_reset = False
                if explicit_pitcher:
                    state["pitcher"] = explicit_pitcher
                if category == "intro":
                    if explicit_batter:
                        state["batter"] = explicit_batter
                    _clear_counts(state)
                    _set_event_state(event, state)
                    after = _capture_state_fields(event)
                    if before != after:
                        changed = [key for key in CURRENT_GAME_STATE_FIELDS if before.get(key) != after.get(key)]
                        deltas.append(RebuildEventDelta(ref=EventRef(group_index, block_index, event_index), changed_fields=changed))
                    continue

                if explicit_batter:
                    state["batter"] = explicit_batter
                batter_id = _normalize_player_id(state.get("batter"))
                batter_name = _player_name(player_index, batter_id)

                if category == "substitution":
                    player_change = event.get("playerChange") or {}
                    in_player = player_change.get("inPlayer") or {}
                    in_player_id = _normalize_player_id(in_player.get("playerId") or in_player.get("playerCode"))
                    in_pos = str(in_player.get("playerPos") or in_player.get("position") or "")
                    if "투수" in in_pos or str(player_change.get("type") or "") == "pitcher":
                        state["pitcher"] = in_player_id or state.get("pitcher")
                    elif "타자" in in_pos or "대타" in in_pos or str(player_change.get("type") or "") == "batter":
                        state["batter"] = in_player_id or state.get("batter")
                    _set_event_state(event, state)
                elif category == "pitch":
                    _apply_pitch_result_to_count(state, event.get("pitchResult"), text)
                    _set_event_state(event, state)
                elif category == "bat_result":
                    result_type = parse_result_type(text) or "other"
                    default_moves = _default_terminal_moves(result_type, base_slots, batter_id, batter_name)
                    _apply_terminal_result(
                        state,
                        base_slots,
                        result_type=result_type,
                        batter_id=batter_id,
                        batter_name=batter_name,
                        runner_moves=default_moves,
                        offense_side=offense_side,
                        defense_side=defense_side,
                        batter_runs=batter_runs,
                        batter_rbi=batter_rbi,
                        pitcher_outs=pitcher_outs,
                        pitcher_runs=pitcher_runs,
                    )
                    _set_event_state(event, state)
                    pending_count_reset = True
                elif category == "baserunning":
                    move = _parse_runner_move(text, player_index)
                    if move:
                        if "도루" in text:
                            _bump_stat(batter_steals, offense_side, move.runner_id, 1)
                        _apply_runner_move(
                            state,
                            base_slots,
                            move,
                            offense_side=offense_side,
                            defense_side=defense_side,
                            batter_id=batter_id,
                            batter_name=batter_name,
                            batter_runs=batter_runs,
                            batter_rbi=batter_rbi,
                            pitcher_outs=pitcher_outs,
                            pitcher_runs=pitcher_runs,
                            credit_rbi=False,
                        )
                    _set_event_state(event, state)
                else:
                    _set_event_state(event, state)

                after = _capture_state_fields(event)
                if before != after:
                    changed = [key for key in CURRENT_GAME_STATE_FIELDS if before.get(key) != after.get(key)]
                    deltas.append(RebuildEventDelta(ref=EventRef(group_index, block_index, event_index), changed_fields=changed))

    if sync_record:
        _sync_record_tables(
            rebuilt,
            player_index=player_index,
            batter_runs=batter_runs,
            batter_rbi=batter_rbi,
            pitcher_outs=pitcher_outs,
            pitcher_runs=pitcher_runs,
            batter_steals=batter_steals,
        )

    return rebuilt, RebuildReport(
        deltas=deltas,
        batter_runs=batter_runs,
        batter_rbi=batter_rbi,
        pitcher_outs=pitcher_outs,
        pitcher_runs=pitcher_runs,
        batter_steals=batter_steals,
    )


def _outs_to_innings_text(outs: int) -> str:
    whole, remainder = divmod(int(outs or 0), 3)
    return str(whole) if remainder == 0 else f"{whole}.{remainder}"


def _row_int(row: JsonDict, key: str) -> int:
    return _safe_int(row.get(key), 0)


def _lineup_bat_order(payload: JsonDict, side: str, player_id: str) -> int | None:
    for row in (payload.get("lineup") or {}).get(f"{side}_starter") or []:
        if _normalize_player_id(row.get("playerCode")) == player_id:
            return to_int(row.get("batorder"), None)
    return None


def _sync_record_tables(
    payload: JsonDict,
    *,
    player_index: dict[str, PlayerInfo],
    batter_runs: dict[str, dict[str, int]],
    batter_rbi: dict[str, dict[str, int]],
    pitcher_outs: dict[str, dict[str, int]],
    pitcher_runs: dict[str, dict[str, int]],
    batter_steals: dict[str, dict[str, int]],
) -> None:
    record = payload.setdefault("record", {})
    batter_record = record.setdefault("batter", {"home": [], "away": [], "homeTotal": {}, "awayTotal": {}})
    pitcher_record = record.setdefault("pitcher", {"home": [], "away": []})
    scoring = score_relay_plate_appearances(payload.get("relay") or [])

    for side in ("home", "away"):
        existing_rows = {
            _normalize_player_id(row.get("playerCode")): row
            for row in batter_record.get(side, []) or []
            if _normalize_player_id(row.get("playerCode"))
        }
        player_ids = list(existing_rows.keys())
        for player_id in scoring.batter_totals_by_side[side].keys():
            if player_id not in player_ids:
                player_ids.append(player_id)
        ordered_rows: list[JsonDict] = []
        for player_id in player_ids:
            existing = copy.deepcopy(existing_rows.get(player_id) or {})
            summary = scoring.batter_totals_by_side[side].get(player_id, {})
            row = {
                "playerCode": player_id,
                "name": existing.get("name") or _player_name(player_index, player_id),
                "batOrder": existing.get("batOrder") if existing.get("batOrder") not in (None, "") else _lineup_bat_order(payload, side, player_id),
                "ab": int(summary.get("ab", 0) or 0),
                "hit": int(summary.get("hit", 0) or 0),
                "bb": int(summary.get("bb", 0) or 0),
                "kk": int(summary.get("so", 0) or 0),
                "hr": int(summary.get("hr", 0) or 0),
                "rbi": int(batter_rbi.get(side, {}).get(player_id, 0) or 0),
                "run": int(batter_runs.get(side, {}).get(player_id, 0) or 0),
                "sb": int(batter_steals.get(side, {}).get(player_id, 0) or 0),
            }
            ordered_rows.append(row)
        ordered_rows.sort(key=lambda row: (_safe_int(row.get("batOrder"), 999), str(row.get("name") or row.get("playerCode") or "")))
        batter_record[side] = ordered_rows
        batter_record[f"{side}Total"] = {
            "ab": sum(_row_int(row, "ab") for row in ordered_rows),
            "hit": sum(_row_int(row, "hit") for row in ordered_rows),
            "bb": sum(_row_int(row, "bb") for row in ordered_rows),
            "kk": sum(_row_int(row, "kk") for row in ordered_rows),
            "hr": sum(_row_int(row, "hr") for row in ordered_rows),
            "rbi": sum(_row_int(row, "rbi") for row in ordered_rows),
            "run": sum(_row_int(row, "run") for row in ordered_rows),
            "sb": sum(_row_int(row, "sb") for row in ordered_rows),
        }

    for side in ("home", "away"):
        existing_rows = {
            _normalize_player_id(row.get("pcode")): row
            for row in pitcher_record.get(side, []) or []
            if _normalize_player_id(row.get("pcode"))
        }
        player_ids = list(existing_rows.keys())
        for player_id in scoring.pitcher_totals_by_side[side].keys():
            if player_id not in player_ids:
                player_ids.append(player_id)
        rows: list[JsonDict] = []
        for player_id in player_ids:
            existing = copy.deepcopy(existing_rows.get(player_id) or {})
            summary = scoring.pitcher_totals_by_side[side].get(player_id, {})
            outs = int(pitcher_outs.get(side, {}).get(player_id, 0) or 0)
            runs = int(pitcher_runs.get(side, {}).get(player_id, 0) or 0)
            rows.append(
                {
                    "pcode": player_id,
                    "name": existing.get("name") or _player_name(player_index, player_id),
                    "inn": _outs_to_innings_text(outs),
                    "r": runs,
                    "er": runs,
                    "hit": int(summary.get("hit", 0) or 0),
                    "bb": int(summary.get("bb", 0) or 0),
                    "kk": int(summary.get("so", 0) or 0),
                    "hr": int(summary.get("hr", 0) or 0),
                    "ab": int(summary.get("ab", 0) or 0),
                    "bf": int(summary.get("bf", 0) or 0),
                    "pa": int(summary.get("pa", 0) or 0),
                    "bbhp": int(summary.get("bbhp", 0) or 0),
                }
            )
        pitcher_record[side] = [row for row in rows if any(row.get(key) not in (None, "", 0, "0") for key in ("inn", "r", "hit", "bb", "kk", "hr", "ab", "bf", "pa", "bbhp")) or row.get("pcode")]


def summarize_plate_appearances(payload: JsonDict, *, group_index: int | None = None, block_index: int | None = None) -> list[PlateAppearanceSummary]:
    rows: list[PlateAppearanceSummary] = []
    player_index = build_player_index(payload)
    for current_group, inning_group in enumerate(payload.get("relay") or []):
        if group_index is not None and current_group != group_index:
            continue
        for current_block, block in enumerate(inning_group or []):
            if block_index is not None and current_block != block_index:
                continue
            start_index: int | None = None
            start_batter: str | None = None
            start_pitcher: str | None = None
            current_batter: str | None = None
            for event_index, event in enumerate(block.get("textOptions") or []):
                if start_index is None and _event_starts_new_pa(event):
                    start_index = event_index
                    start_batter = _event_batter_id(event)
                    start_pitcher = _event_pitcher_id(event)
                    current_batter = start_batter
                elif start_index is not None and _event_starts_new_pa_in_context(event, current_batter):
                    batter_id = current_batter or start_batter
                    rows.append(
                        PlateAppearanceSummary(
                            group_index=current_group,
                            block_index=current_block,
                            start_index=start_index,
                            end_index=event_index - 1,
                            batter_id=batter_id,
                            batter_name=_player_name(player_index, batter_id),
                            pitcher_id=start_pitcher,
                            result_type=None,
                            result_text="",
                            is_terminal=False,
                        )
                    )
                    start_index = event_index
                    start_batter = _event_batter_id(event)
                    start_pitcher = _event_pitcher_id(event)
                    current_batter = start_batter
                if start_index is None:
                    continue
                if _event_batter_id(event):
                    current_batter = _event_batter_id(event)
                if _is_terminal_event(event):
                    batter_id = _event_batter_id(event) or start_batter
                    rows.append(
                        PlateAppearanceSummary(
                            group_index=current_group,
                            block_index=current_block,
                            start_index=start_index,
                            end_index=event_index,
                            batter_id=batter_id,
                            batter_name=_player_name(player_index, batter_id),
                            pitcher_id=_event_pitcher_id(event) or start_pitcher,
                            result_type=parse_result_type(_event_text(event)),
                            result_text=_event_text(event),
                            is_terminal=True,
                        )
                    )
                    start_index = None
                    start_batter = None
                    start_pitcher = None
                    current_batter = None
            if start_index is not None:
                batter_id = start_batter
                rows.append(
                    PlateAppearanceSummary(
                        group_index=current_group,
                        block_index=current_block,
                        start_index=start_index,
                        end_index=len(block.get("textOptions") or []) - 1,
                        batter_id=batter_id,
                        batter_name=_player_name(player_index, batter_id),
                        pitcher_id=start_pitcher,
                        result_type=None,
                        result_text="",
                        is_terminal=False,
                    )
                )
    return rows


def _normalize_runner_moves(runner_moves: list[dict[str, Any]] | None) -> list[RunnerMove]:
    moves: list[RunnerMove] = []
    for item in runner_moves or []:
        start = str(item.get("start") or "").strip().upper()
        end = str(item.get("end") or "").strip().upper()
        if start not in {"B", "1", "2", "3"} or end not in {"1", "2", "3", "H", "OUT"}:
            continue
        moves.append(
            RunnerMove(
                start=start,
                end=end,
                runner_id=_normalize_player_id(item.get("runner_id")),
                runner_name=str(item.get("runner_name") or "").strip() or None,
            )
        )
    return moves


def _block_events(payload: JsonDict, group_index: int, block_index: int) -> list[JsonDict]:
    return ((payload.get("relay") or [])[group_index][block_index].setdefault("textOptions", []))


def insert_event_template(
    payload: JsonDict,
    *,
    group_index: int,
    block_index: int,
    insert_at: int,
    template_type: str,
    spec: dict[str, Any],
) -> list[int]:
    events = _block_events(payload, group_index, block_index)
    event = build_event_template(
        payload,
        template_type=template_type,
        batter_id=_normalize_player_id(spec.get("batter_id")),
        batter_name=str(spec.get("batter_name") or "").strip() or None,
        pitcher_id=_normalize_player_id(spec.get("pitcher_id")),
        result_type=str(spec.get("result_type") or "").strip() or None,
        detail=str(spec.get("detail") or "").strip() or None,
        pitch_result=str(spec.get("pitch_result") or "").strip() or None,
        pitch_num=to_int(spec.get("pitch_num"), None),
        pts_pitch_id=str(spec.get("pts_pitch_id") or "").strip() or None,
        text=str(spec.get("text") or "").strip() or None,
        player_change=copy.deepcopy(spec.get("player_change") or {}),
    )
    insert_at = max(0, min(insert_at, len(events)))
    events.insert(insert_at, event)
    inserted = [insert_at]
    if template_type == "bat_result":
        runner_events = build_runner_events(
            payload,
            _normalize_runner_moves(spec.get("runner_moves")),
            pitcher_id=_normalize_player_id(spec.get("pitcher_id")),
            batter_id=_normalize_player_id(spec.get("batter_id")),
        )
        for offset, runner_event in enumerate(runner_events, start=1):
            events.insert(insert_at + offset, runner_event)
            inserted.append(insert_at + offset)
    return inserted


def insert_missing_plate_appearance(
    payload: JsonDict,
    *,
    group_index: int,
    block_index: int,
    insert_at: int,
    spec: dict[str, Any],
) -> list[int]:
    player_index = build_player_index(payload)
    batter_id = _normalize_player_id(spec.get("batter_id"))
    pitcher_id = _normalize_player_id(spec.get("pitcher_id"))
    batter_name = str(spec.get("batter_name") or "").strip() or _player_name(player_index, batter_id)
    events = _block_events(payload, group_index, block_index)
    insert_at = max(0, min(insert_at, len(events)))
    created: list[JsonDict] = []
    if batter_id:
        created.append(
            {
                "seqno": None,
                "type": 0,
                "text": _intro_text(player_index, batter_id, batter_name),
                "currentGameState": {**_default_state(), "batter": batter_id, "pitcher": pitcher_id},
            }
        )
    pitch_specs = spec.get("pitch_list") or []
    for pitch_item in pitch_specs:
        created.append(
            build_event_template(
                payload,
                template_type="pitch",
                batter_id=batter_id,
                batter_name=batter_name,
                pitcher_id=pitcher_id,
                pitch_result=str(pitch_item.get("pitch_result") or pitch_item.get("pitchResult") or "").strip() or None,
                pitch_num=to_int(pitch_item.get("pitch_num") or pitch_item.get("pitchNum"), None),
                pts_pitch_id=str(pitch_item.get("pts_pitch_id") or pitch_item.get("ptsPitchId") or "").strip() or None,
                text=str(pitch_item.get("text") or "").strip() or None,
            )
        )
    created.append(
        build_event_template(
            payload,
            template_type="bat_result",
            batter_id=batter_id,
            batter_name=batter_name,
            pitcher_id=pitcher_id,
            result_type=str(spec.get("result_type") or "").strip() or "other",
            detail=str(spec.get("detail") or "").strip() or None,
            pitch_result=str(spec.get("pitch_result") or "").strip() or None,
            pitch_num=to_int(spec.get("pitch_num"), None),
            pts_pitch_id=str(spec.get("pts_pitch_id") or "").strip() or None,
            text=str(spec.get("result_text") or "").strip() or None,
        )
    )
    created.extend(build_runner_events(payload, _normalize_runner_moves(spec.get("runner_moves")), pitcher_id=pitcher_id, batter_id=batter_id))
    for offset, event in enumerate(created):
        events.insert(insert_at + offset, event)
    return list(range(insert_at, insert_at + len(created)))


def update_event_meaning(
    payload: JsonDict,
    *,
    group_index: int,
    block_index: int,
    event_index: int,
    spec: dict[str, Any],
) -> list[int]:
    events = _block_events(payload, group_index, block_index)
    if not (0 <= event_index < len(events)):
        return []
    event = events[event_index]
    batter_id = _normalize_player_id(spec.get("batter_id")) or _event_batter_id(event)
    pitcher_id = _normalize_player_id(spec.get("pitcher_id")) or _event_pitcher_id(event)
    if batter_id:
        event.setdefault("currentGameState", {})["batter"] = batter_id
        event["batterRecord"] = {"pcode": batter_id}
    if pitcher_id:
        event.setdefault("currentGameState", {})["pitcher"] = pitcher_id
    result_type = str(spec.get("result_type") or "").strip()
    if result_type:
        for key in ("pitchNum", "pitchResult", "ptsPitchId"):
            event.pop(key, None)
        updated = build_event_template(
            payload,
            template_type="bat_result" if result_type in RESULT_TYPES_REQUIRING_BAT_RESULT else str(spec.get("template_type") or "other"),
            batter_id=batter_id,
            batter_name=str(spec.get("batter_name") or "").strip() or None,
            pitcher_id=pitcher_id,
            result_type=result_type,
            detail=str(spec.get("detail") or "").strip() or None,
            pitch_result=str(spec.get("pitch_result") or "").strip() or None,
            pitch_num=to_int(spec.get("pitch_num"), None),
            pts_pitch_id=str(spec.get("pts_pitch_id") or "").strip() or None,
            text=str(spec.get("text") or "").strip() or None,
        )
        for key, value in updated.items():
            event[key] = value
    else:
        if spec.get("text") not in (None, ""):
            event["text"] = str(spec.get("text"))
        if spec.get("pitch_result") not in (None, ""):
            event["pitchResult"] = str(spec.get("pitch_result"))
        if spec.get("pitch_num") not in (None, ""):
            event["pitchNum"] = to_int(spec.get("pitch_num"), None)
        if spec.get("pts_pitch_id") not in (None, ""):
            event["ptsPitchId"] = str(spec.get("pts_pitch_id"))
    if spec.get("replace_runner_events"):
        next_index = event_index + 1
        while next_index < len(events) and _event_category(events[next_index]) == "baserunning":
            events.pop(next_index)
    runner_events = build_runner_events(payload, _normalize_runner_moves(spec.get("runner_moves")), pitcher_id=pitcher_id, batter_id=batter_id)
    for offset, runner_event in enumerate(runner_events, start=1):
        events.insert(event_index + offset, runner_event)
    return [event_index] + list(range(event_index + 1, event_index + 1 + len(runner_events)))


def _find_pa_bounds_in_block(events: list[JsonDict], selected_index: int) -> tuple[int, int]:
    current_start: int | None = None
    current_batter: str | None = None
    for index, event in enumerate(events):
        if current_start is None and _event_starts_new_pa(event):
            current_start = index
            current_batter = _event_batter_id(event)
        elif current_start is not None and _event_starts_new_pa_in_context(event, current_batter):
            if current_start <= selected_index <= index - 1:
                return current_start, index - 1
            current_start = index
            current_batter = _event_batter_id(event)
        if current_start is not None and _event_batter_id(event):
            current_batter = _event_batter_id(event)
        if current_start is None:
            continue
        if _is_terminal_event(event):
            if current_start <= selected_index <= index:
                return current_start, index
            current_start = None
            current_batter = None
    if current_start is not None:
        return current_start, len(events) - 1
    return selected_index, selected_index


def _assign_batter_to_segment(events: list[JsonDict], start: int, end: int, batter_id: str | None, batter_name: str | None, player_index: dict[str, PlayerInfo]) -> None:
    if not batter_id:
        return
    for index in range(start, end + 1):
        event = events[index]
        category = _event_category(event)
        event.setdefault("currentGameState", {})["batter"] = batter_id
        if category in {"pitch", "bat_result"}:
            event["batterRecord"] = {"pcode": batter_id}
        if category == "intro":
            event["text"] = _intro_text(player_index, batter_id, batter_name)


def split_plate_appearance(
    payload: JsonDict,
    *,
    group_index: int,
    block_index: int,
    split_at: int,
    spec: dict[str, Any],
) -> int | None:
    events = _block_events(payload, group_index, block_index)
    if not (0 < split_at < len(events)):
        return None
    pa_start, pa_end = _find_pa_bounds_in_block(events, split_at)
    if split_at <= pa_start or split_at > pa_end:
        return None
    player_index = build_player_index(payload)
    first_batter = _normalize_player_id(spec.get("first_batter_id")) or _event_batter_id(events[pa_start])
    second_batter = _normalize_player_id(spec.get("second_batter_id")) or _event_batter_id(events[split_at])
    first_name = str(spec.get("first_batter_name") or "").strip() or _player_name(player_index, first_batter)
    second_name = str(spec.get("second_batter_name") or "").strip() or _player_name(player_index, second_batter)
    first_terminal_index = None
    for index in range(pa_start, split_at):
        if _is_terminal_event(events[index]):
            first_terminal_index = index
            break
    inserted_terminal = False
    if first_terminal_index is None and spec.get("first_result_type"):
        terminal_event = build_event_template(
            payload,
            template_type="bat_result",
            batter_id=first_batter,
            batter_name=first_name,
            pitcher_id=_event_pitcher_id(events[pa_start]),
            result_type=str(spec.get("first_result_type")),
            detail=str(spec.get("first_detail") or "").strip() or None,
            text=str(spec.get("first_text") or "").strip() or None,
        )
        events.insert(split_at, terminal_event)
        split_at += 1
        pa_end += 1
        first_terminal_index = split_at - 1
        inserted_terminal = True
    elif first_terminal_index is not None and spec.get("first_result_type"):
        update_event_meaning(
            payload,
            group_index=group_index,
            block_index=block_index,
            event_index=first_terminal_index,
            spec={
                "batter_id": first_batter,
                "batter_name": first_name,
                "pitcher_id": _event_pitcher_id(events[first_terminal_index]),
                "result_type": spec.get("first_result_type"),
                "detail": spec.get("first_detail"),
                "text": spec.get("first_text"),
                "replace_runner_events": True,
                "runner_moves": spec.get("first_runner_moves"),
            },
        )
    if not _is_batter_intro_text(_event_text(events[split_at])):
        intro_event = {
            "seqno": None,
            "type": 0,
            "text": _intro_text(player_index, second_batter or "", second_name),
            "currentGameState": {**_default_state(), "batter": second_batter, "pitcher": _event_pitcher_id(events[split_at])},
        }
        events.insert(split_at, intro_event)
        pa_end += 1
    second_terminal_index = None
    for index in range(split_at, pa_end + 1):
        if _is_terminal_event(events[index]):
            second_terminal_index = index
            break
    if second_terminal_index is None and spec.get("second_result_type"):
        second_terminal = build_event_template(
            payload,
            template_type="bat_result",
            batter_id=second_batter,
            batter_name=second_name,
            pitcher_id=_event_pitcher_id(events[split_at]),
            result_type=str(spec.get("second_result_type")),
            detail=str(spec.get("second_detail") or "").strip() or None,
            text=str(spec.get("second_text") or "").strip() or None,
        )
        events.insert(pa_end + 1, second_terminal)
        second_terminal_index = pa_end + 1
    elif second_terminal_index is not None and spec.get("second_result_type"):
        update_event_meaning(
            payload,
            group_index=group_index,
            block_index=block_index,
            event_index=second_terminal_index,
            spec={
                "batter_id": second_batter,
                "batter_name": second_name,
                "pitcher_id": _event_pitcher_id(events[second_terminal_index]),
                "result_type": spec.get("second_result_type"),
                "detail": spec.get("second_detail"),
                "text": spec.get("second_text"),
                "replace_runner_events": True,
                "runner_moves": spec.get("second_runner_moves"),
            },
        )
    first_segment_end = first_terminal_index if first_terminal_index is not None else split_at - 1
    _assign_batter_to_segment(events, pa_start, first_segment_end, first_batter, first_name, player_index)
    second_segment_start = split_at
    second_segment_end = second_terminal_index if second_terminal_index is not None else pa_end
    _assign_batter_to_segment(events, second_segment_start, second_segment_end, second_batter, second_name, player_index)
    return split_at if inserted_terminal else second_segment_start


def merge_with_previous_plate_appearance(
    payload: JsonDict,
    *,
    group_index: int,
    block_index: int,
    selected_index: int,
    merged_batter_id: str | None = None,
    merged_batter_name: str | None = None,
) -> int | None:
    events = _block_events(payload, group_index, block_index)
    pa_list = summarize_plate_appearances(payload, group_index=group_index, block_index=block_index)
    current_pa_index = None
    for pa_index, pa in enumerate(pa_list):
        if pa.start_index <= selected_index <= pa.end_index:
            current_pa_index = pa_index
            break
    if current_pa_index is None or current_pa_index == 0:
        return None
    prev_pa = pa_list[current_pa_index - 1]
    curr_pa = pa_list[current_pa_index]
    if prev_pa.end_index < len(events):
        events.pop(prev_pa.end_index)
        if curr_pa.start_index > prev_pa.end_index:
            curr_pa = PlateAppearanceSummary(
                group_index=curr_pa.group_index,
                block_index=curr_pa.block_index,
                start_index=max(prev_pa.end_index, curr_pa.start_index - 1),
                end_index=curr_pa.end_index - 1,
                batter_id=curr_pa.batter_id,
                batter_name=curr_pa.batter_name,
                pitcher_id=curr_pa.pitcher_id,
                result_type=curr_pa.result_type,
                result_text=curr_pa.result_text,
                is_terminal=curr_pa.is_terminal,
            )
    if curr_pa.start_index < len(events) and _is_batter_intro_text(_event_text(events[curr_pa.start_index])):
        events.pop(curr_pa.start_index)
        curr_pa = PlateAppearanceSummary(
            group_index=curr_pa.group_index,
            block_index=curr_pa.block_index,
            start_index=curr_pa.start_index,
            end_index=curr_pa.end_index - 1,
            batter_id=curr_pa.batter_id,
            batter_name=curr_pa.batter_name,
            pitcher_id=curr_pa.pitcher_id,
            result_type=curr_pa.result_type,
            result_text=curr_pa.result_text,
            is_terminal=curr_pa.is_terminal,
        )
    player_index = build_player_index(payload)
    batter_id = merged_batter_id or prev_pa.batter_id
    batter_name = merged_batter_name or prev_pa.batter_name
    _assign_batter_to_segment(events, prev_pa.start_index, curr_pa.end_index, batter_id, batter_name, player_index)
    return prev_pa.start_index
