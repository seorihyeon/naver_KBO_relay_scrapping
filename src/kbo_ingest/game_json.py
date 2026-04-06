from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2

GAME_INFO_FIELDS = (
    "gdate",
    "gtime",
    "hCode",
    "hName",
    "hPCode",
    "aCode",
    "aName",
    "aPCode",
    "round",
    "gameFlag",
    "stadium",
    "isPostSeason",
    "cancelFlag",
    "statusCode",
)

LINEUP_STARTER_FIELDS = (
    "playerCode",
    "playerName",
    "position",
    "positionName",
    "batorder",
    "backnum",
    "hitType",
    "batsThrows",
    "height",
    "weight",
)

LINEUP_BULLPEN_FIELDS = (
    "playerCode",
    "playerName",
    "pos",
    "hitType",
    "batsThrows",
)

LINEUP_CANDIDATE_FIELDS = (
    "playerCode",
    "playerName",
    "pos",
    "position",
    "hitType",
    "batsThrows",
)

CURRENT_GAME_STATE_FIELDS = (
    "homeScore",
    "awayScore",
    "homeHit",
    "awayHit",
    "homeBallFour",
    "awayBallFour",
    "homeError",
    "awayError",
    "pitcher",
    "batter",
    "strike",
    "ball",
    "out",
    "base1",
    "base2",
    "base3",
)

BATTER_RECORD_FIELDS = ("pcode",)

PLAYER_CHANGE_FIELDS = ("type", "outPlayerTurn")
PLAYER_CHANGE_PLAYER_FIELDS = (
    "playerId",
    "playerCode",
    "playerName",
    "name",
    "playerPos",
    "position",
)

RELAY_EVENT_FIELDS = (
    "seqno",
    "type",
    "text",
    "pitchNum",
    "pitchResult",
    "ptsPitchId",
    "speed",
    "stuff",
)

RELAY_BLOCK_FIELDS = (
    "title",
    "titleStyle",
    "no",
    "inn",
    "homeOrAway",
    "statusCode",
)

METRIC_OPTION_FIELDS = ("homeTeamWinRate", "awayTeamWinRate", "wpaByPlate")

PITCH_TRACK_FIELDS = (
    "pitchId",
    "inn",
    "ballcount",
    "crossPlateX",
    "crossPlateY",
    "topSz",
    "bottomSz",
    "vx0",
    "vy0",
    "vz0",
    "ax",
    "ay",
    "az",
    "x0",
    "y0",
    "z0",
    "stance",
)

BATTER_ROW_FIELDS = (
    "playerCode",
    "name",
    "batOrder",
    "ab",
    "hit",
    "bb",
    "kk",
    "hr",
    "rbi",
    "run",
    "sb",
)

BATTER_TOTAL_FIELDS = ("ab", "hit", "bb", "kk", "hr", "rbi", "run", "sb")

PITCHER_ROW_FIELDS = (
    "pcode",
    "name",
    "inn",
    "r",
    "er",
    "hit",
    "bb",
    "kk",
    "hr",
    "ab",
    "bf",
    "pa",
    "bbhp",
)


def _copy_selected_fields(row: dict[str, Any] | None, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    copied: dict[str, Any] = {}
    for field in fields:
        if field in row:
            copied[field] = copy.deepcopy(row[field])
    return copied


def _minimize_player_change(player_change: Any) -> dict[str, Any]:
    if not isinstance(player_change, dict):
        return {}
    minimized = _copy_selected_fields(player_change, PLAYER_CHANGE_FIELDS)
    for key in ("inPlayer", "outPlayer"):
        value = player_change.get(key)
        if isinstance(value, dict):
            minimized[key] = _copy_selected_fields(value, PLAYER_CHANGE_PLAYER_FIELDS)
    return minimized


def _minimize_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict):
        return {}
    minimized = _copy_selected_fields(event, RELAY_EVENT_FIELDS)
    current_game_state = _copy_selected_fields(event.get("currentGameState"), CURRENT_GAME_STATE_FIELDS)
    if current_game_state:
        minimized["currentGameState"] = current_game_state
    batter_record = _copy_selected_fields(event.get("batterRecord"), BATTER_RECORD_FIELDS)
    if batter_record:
        minimized["batterRecord"] = batter_record
    player_change = _minimize_player_change(event.get("playerChange"))
    if player_change:
        minimized["playerChange"] = player_change
    return minimized


def _minimize_block(block: Any) -> dict[str, Any]:
    if not isinstance(block, dict):
        return {"textOptions": [], "ptsOptions": []}
    minimized = _copy_selected_fields(block, RELAY_BLOCK_FIELDS)
    metric_option = _copy_selected_fields(block.get("metricOption"), METRIC_OPTION_FIELDS)
    if metric_option:
        minimized["metricOption"] = metric_option
    minimized["textOptions"] = [_minimize_event(event) for event in (block.get("textOptions") or [])]
    minimized["ptsOptions"] = [
        _copy_selected_fields(track, PITCH_TRACK_FIELDS)
        for track in (block.get("ptsOptions") or [])
        if isinstance(track, dict)
    ]
    return minimized


def _minimize_lineup_group(rows: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [_copy_selected_fields(row, fields) for row in rows if isinstance(row, dict)]


def _minimize_batter_table(table: Any) -> dict[str, Any]:
    if not isinstance(table, dict):
        return {"home": [], "away": [], "homeTotal": {}, "awayTotal": {}}
    return {
        "home": [_copy_selected_fields(row, BATTER_ROW_FIELDS) for row in (table.get("home") or []) if isinstance(row, dict)],
        "away": [_copy_selected_fields(row, BATTER_ROW_FIELDS) for row in (table.get("away") or []) if isinstance(row, dict)],
        "homeTotal": _copy_selected_fields(table.get("homeTotal"), BATTER_TOTAL_FIELDS),
        "awayTotal": _copy_selected_fields(table.get("awayTotal"), BATTER_TOTAL_FIELDS),
    }


def _minimize_pitcher_table(table: Any) -> dict[str, Any]:
    if not isinstance(table, dict):
        return {"home": [], "away": []}
    return {
        "home": [_copy_selected_fields(row, PITCHER_ROW_FIELDS) for row in (table.get("home") or []) if isinstance(row, dict)],
        "away": [_copy_selected_fields(row, PITCHER_ROW_FIELDS) for row in (table.get("away") or []) if isinstance(row, dict)],
    }


def _infer_game_id_from_path(path: Path | None) -> str | None:
    if path is None:
        return None
    stem = path.stem
    return stem or None


def _merge_game_source(existing: Any, *, inferred_game_id: str | None = None, game_url: str | None = None) -> dict[str, Any]:
    if isinstance(existing, dict):
        merged = copy.deepcopy(existing)
    else:
        merged = {}
    merged.setdefault("provider", "naver")
    if inferred_game_id and "source_game_id" not in merged:
        merged["source_game_id"] = inferred_game_id
    if game_url and "url" not in merged:
        merged["url"] = game_url
    return merged


def minimize_game_payload(
    payload: dict[str, Any],
    *,
    file_path: Path | None = None,
    game_id: str | None = None,
    game_url: str | None = None,
    collected_at: str | None = None,
) -> dict[str, Any]:
    inferred_game_id = str(
        payload.get("game_id")
        or game_id
        or (payload.get("game_source") or {}).get("source_game_id")
        or _infer_game_id_from_path(file_path)
        or ""
    ).strip() or None

    lineup = payload.get("lineup") or {}
    record = payload.get("record") or {}
    relay = payload.get("relay") or []

    minimized = {
        "schema_version": SCHEMA_VERSION,
        "game_id": inferred_game_id,
        "game_source": _merge_game_source(payload.get("game_source"), inferred_game_id=inferred_game_id, game_url=game_url),
        "collected_at": payload.get("collected_at") or collected_at,
        "lineup": {
            "game_info": _copy_selected_fields(lineup.get("game_info"), GAME_INFO_FIELDS),
            "home_starter": _minimize_lineup_group(lineup.get("home_starter"), LINEUP_STARTER_FIELDS),
            "home_bullpen": _minimize_lineup_group(lineup.get("home_bullpen"), LINEUP_BULLPEN_FIELDS),
            "home_candidate": _minimize_lineup_group(lineup.get("home_candidate"), LINEUP_CANDIDATE_FIELDS),
            "away_starter": _minimize_lineup_group(lineup.get("away_starter"), LINEUP_STARTER_FIELDS),
            "away_bullpen": _minimize_lineup_group(lineup.get("away_bullpen"), LINEUP_BULLPEN_FIELDS),
            "away_candidate": _minimize_lineup_group(lineup.get("away_candidate"), LINEUP_CANDIDATE_FIELDS),
        },
        "relay": [
            [_minimize_block(block) for block in (inning or []) if isinstance(block, dict)]
            for inning in relay
            if isinstance(inning, list)
        ],
        "record": {
            "batter": _minimize_batter_table(record.get("batter")),
            "pitcher": _minimize_pitcher_table(record.get("pitcher")),
        },
    }
    return minimized


def load_game_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return minimize_game_payload(payload, file_path=path)


def pretty_game_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

