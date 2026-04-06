from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from check_data import (
    build_batter_stats_from_relay,
    classify_pa_text,
    extract_lineup_players,
    extract_record_batters,
    extract_record_pitchers,
    get_final_scoreboard_from_relay,
    validate_game as validate_source_json,
)
from common_utils import to_int

from .ingest_raw import _parse_game_date, _to_bool_flag, _iter_relay_blocks
from .normalize_game import _is_batter_intro_text, classify_event


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_half(home_or_away: Any) -> str | None:
    txt = str(home_or_away).strip().upper()
    if txt in {"0", "TOP", "T", "AWAY"}:
        return "top"
    if txt in {"1", "BOTTOM", "B", "HOME"}:
        return "bottom"
    return None


def _player_id_from_row(row: dict[str, Any]) -> str | None:
    for key in ("playerCode", "pcode", "playerId"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _sum_player_stats(player_rows: dict[str, dict[str, int]]) -> dict[str, int]:
    totals = {"pa": 0, "ab": 0, "hit": 0, "bb": 0, "so": 0, "hbp": 0}
    for row in player_rows.values():
        for key in totals:
            totals[key] += int(row.get(key, 0) or 0)
    return totals


def _sum_pitcher_stats(pitcher_rows: dict[str, dict[str, int]]) -> dict[str, int]:
    totals = {"outs": 0, "r": 0, "er": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "ab": 0, "bf": 0, "pa": 0, "bbhp": 0}
    for row in pitcher_rows.values():
        for key in totals:
            totals[key] += int(row.get(key, 0) or 0)
    return totals


def _event_batter_id(event: dict[str, Any]) -> str | None:
    current_game_state = event.get("currentGameState") or {}
    batter_id = current_game_state.get("batter")
    if batter_id in (None, ""):
        return None
    return str(batter_id)


def _event_category(event: dict[str, Any]) -> str:
    pitch_id = event.get("ptsPitchId")
    return classify_event(
        event.get("text") or "",
        to_int(event.get("pitchNum"), None),
        event.get("pitchResult"),
        str(pitch_id) if pitch_id not in (None, "") else None,
        event.get("playerChange"),
        to_int(event.get("type"), None),
    )


def _event_starts_new_pa(event: dict[str, Any], category: str) -> bool:
    batter_id = _event_batter_id(event)
    if not batter_id:
        return False
    return category in {"pitch", "bat_result"} or _is_batter_intro_text(event.get("text") or "")


def _build_expected_pa_profile(raw_blocks: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    partial_count = 0
    terminal_count = 0
    current_pa: dict[str, Any] | None = None
    batter_totals = {"home": Counter(), "away": Counter()}
    last_terminal_signature: tuple[Any, ...] | None = None

    def finalize_current_pa() -> None:
        nonlocal partial_count, current_pa
        if current_pa and current_pa.get("has_action") and not current_pa.get("is_terminal"):
            partial_count += 1
        current_pa = None

    for _, block in raw_blocks:
        inning_no = int(block.get("inn") or 0)
        half = _normalize_half(block.get("homeOrAway"))
        in_key = (inning_no, half)
        offense_side = "away" if half == "top" else "home"
        if current_pa and current_pa.get("in_key") != in_key:
            finalize_current_pa()

        for event in block.get("textOptions") or []:
            category = _event_category(event)
            batter_id = _event_batter_id(event)
            event_starts_new_pa = _event_starts_new_pa(event, category)
            has_pa_action = category in {"pitch", "bat_result"}

            if event_starts_new_pa:
                if current_pa is None:
                    current_pa = {
                        "in_key": in_key,
                        "offense_side": offense_side,
                        "batter_id": batter_id,
                        "has_action": has_pa_action,
                        "is_terminal": False,
                    }
                elif current_pa.get("in_key") == in_key and current_pa.get("batter_id") == batter_id:
                    current_pa["has_action"] = current_pa.get("has_action") or has_pa_action
                elif current_pa.get("in_key") == in_key and not current_pa.get("has_action"):
                    current_pa["offense_side"] = offense_side
                    current_pa["batter_id"] = batter_id
                    current_pa["has_action"] = has_pa_action
                else:
                    finalize_current_pa()
                    current_pa = {
                        "in_key": in_key,
                        "offense_side": offense_side,
                        "batter_id": batter_id,
                        "has_action": has_pa_action,
                        "is_terminal": False,
                    }

                if category == "bat_result":
                    signature = (
                        in_key,
                        batter_id,
                        event.get("text") or "",
                        (event.get("currentGameState") or {}).get("out"),
                        (event.get("currentGameState") or {}).get("ball"),
                        (event.get("currentGameState") or {}).get("strike"),
                        (event.get("currentGameState") or {}).get("base1"),
                        (event.get("currentGameState") or {}).get("base2"),
                        (event.get("currentGameState") or {}).get("base3"),
                    )
                    if signature != last_terminal_signature:
                        terminal_count += 1
                        batter_totals[offense_side].update(classify_pa_text(event.get("text") or ""))
                        last_terminal_signature = signature
                    current_pa["is_terminal"] = True
                    current_pa = None

    finalize_current_pa()
    return {
        "terminal_plate_appearances": terminal_count,
        "partial_plate_appearances": partial_count,
        "batter_totals": {
            "home": dict(batter_totals["home"]),
            "away": dict(batter_totals["away"]),
        },
    }


def _build_inning_expectations(events_by_half: dict[tuple[int, str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    inning_expectations: list[dict[str, Any]] = []
    for (inning_no, half), rows in sorted(events_by_half.items()):
        first_state = rows[0]["currentGameState"]
        last_state = rows[-1]["currentGameState"]
        if half == "top":
            runs_scored = int(last_state.get("awayScore", 0) or 0) - int(first_state.get("awayScore", 0) or 0)
            hits_in_half = int(last_state.get("awayHit", 0) or 0) - int(first_state.get("awayHit", 0) or 0)
            walks_in_half = int(last_state.get("awayBallFour", 0) or 0) - int(first_state.get("awayBallFour", 0) or 0)
            errors_in_half = int(last_state.get("homeError", 0) or 0) - int(first_state.get("homeError", 0) or 0)
        else:
            runs_scored = int(last_state.get("homeScore", 0) or 0) - int(first_state.get("homeScore", 0) or 0)
            hits_in_half = int(last_state.get("homeHit", 0) or 0) - int(first_state.get("homeHit", 0) or 0)
            walks_in_half = int(last_state.get("homeBallFour", 0) or 0) - int(first_state.get("homeBallFour", 0) or 0)
            errors_in_half = int(last_state.get("awayError", 0) or 0) - int(first_state.get("awayError", 0) or 0)

        inning_expectations.append(
            {
                "inning_no": inning_no,
                "half": half,
                "runs_scored": runs_scored,
                "hits_in_half": hits_in_half,
                "walks_in_half": walks_in_half,
                "errors_in_half": errors_in_half,
                "event_count": len(rows),
            }
        )
    return inning_expectations


def build_source_profile(json_path: Path, *, project_root: Path | None = None) -> dict[str, Any]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    lineup = payload.get("lineup") or {}
    record = payload.get("record") or {}
    relay = payload.get("relay") or []
    game_info = lineup.get("game_info") or {}

    lineup_info = extract_lineup_players(lineup)
    record_batters = extract_record_batters(record.get("batter", {}))
    record_pitchers = extract_record_pitchers(record.get("pitcher", {}))
    relay_batters = build_batter_stats_from_relay(relay)
    source_validation = validate_source_json(payload)
    scoreboard = get_final_scoreboard_from_relay(relay) or {}

    raw_blocks = _iter_relay_blocks(relay)
    text_event_count = 0
    raw_pitch_track_count = 0
    pts_pitch_ids: set[str] = set()
    raw_pitch_track_ids: set[str] = set()
    category_counts = {"review": 0, "substitution": 0, "baserunning": 0, "bat_result": 0}
    relay_change_player_ids: set[str] = set()
    substitution_missing_player_id_count = 0
    events_by_half: dict[tuple[int, str], list[dict[str, Any]]] = {}

    for _, block in raw_blocks:
        inning_no = int(block.get("inn") or 0)
        half = _normalize_half(block.get("homeOrAway"))
        text_options = block.get("textOptions") or []
        pts_options = block.get("ptsOptions") or []
        text_event_count += len(text_options)
        raw_pitch_track_count += len(pts_options)
        for track in pts_options:
            pitch_id = track.get("pitchId")
            if pitch_id not in (None, ""):
                raw_pitch_track_ids.add(str(pitch_id))
        for event in text_options:
            pitch_id = event.get("ptsPitchId")
            if pitch_id not in (None, ""):
                pts_pitch_ids.add(str(pitch_id))
            category = _event_category(event)
            if category in category_counts:
                category_counts[category] += 1
            player_change = event.get("playerChange") or {}
            if category == "substitution":
                in_player_id = _player_id_from_row(player_change.get("inPlayer") or {})
                out_player_id = _player_id_from_row(player_change.get("outPlayer") or {})
                if not in_player_id or not out_player_id:
                    substitution_missing_player_id_count += 1
            for side_key in ("inPlayer", "outPlayer"):
                player_id = _player_id_from_row(player_change.get(side_key) or {})
                if player_id:
                    relay_change_player_ids.add(player_id)
            current_game_state = event.get("currentGameState") or {}
            if inning_no and half and current_game_state:
                events_by_half.setdefault((inning_no, half), []).append({"currentGameState": current_game_state})

    lineup_player_ids: list[str] = []
    lineup_row_count = 0
    for side in ("home", "away"):
        for group in ("starter", "bullpen", "candidate"):
            rows = lineup.get(f"{side}_{group}") or []
            lineup_row_count += len(rows)
            for row in rows:
                player_id = _player_id_from_row(row)
                if player_id:
                    lineup_player_ids.append(player_id)

    record_player_ids: set[str] = set()
    for side in ("home", "away"):
        for row in (record.get("batter") or {}).get(side, []) or []:
            player_id = _player_id_from_row(row)
            if player_id:
                record_player_ids.add(player_id)
        for row in (record.get("pitcher") or {}).get(side, []) or []:
            player_id = _player_id_from_row(row)
            if player_id:
                record_player_ids.add(player_id)

    roster_expected_count = lineup_row_count + len([player_id for player_id in sorted(record_player_ids) if player_id not in set(lineup_player_ids)])
    expected_player_ids = sorted(set(lineup_player_ids) | record_player_ids | relay_change_player_ids)

    record_batter_totals = {
        "home": {key: int(value or 0) for key, value in (record_batters.get("homeTotal") or {}).items() if key in {"ab", "hit", "rbi", "run", "sb"}},
        "away": {key: int(value or 0) for key, value in (record_batters.get("awayTotal") or {}).items() if key in {"ab", "hit", "rbi", "run", "sb"}},
    }
    relay_batter_totals = {
        "home": _sum_player_stats(relay_batters["home"]),
        "away": _sum_player_stats(relay_batters["away"]),
    }
    expected_pa_profile = _build_expected_pa_profile(raw_blocks)
    terminal_plate_appearance_count = int(expected_pa_profile["terminal_plate_appearances"])
    partial_plate_appearance_count = int(expected_pa_profile["partial_plate_appearances"])
    record_pitcher_totals = {
        "home": _sum_pitcher_stats(record_pitchers["home"]),
        "away": _sum_pitcher_stats(record_pitchers["away"]),
    }

    raw_game_date = game_info.get("gdate")
    game_date = _parse_game_date(raw_game_date)
    home_team_code = str(game_info.get("hCode") or game_info.get("homeTeamCode") or "")
    away_team_code = str(game_info.get("aCode") or game_info.get("awayTeamCode") or "")
    source_game_key = "_".join(
        [
            str(raw_game_date or ""),
            away_team_code,
            home_team_code,
            str(game_info.get("gameFlag") or game_info.get("gubun") or ""),
            str(game_info.get("round") or ""),
        ]
    )

    project_root = project_root or Path.cwd()
    relative_path = json_path.relative_to(project_root).as_posix() if json_path.is_absolute() and json_path.is_relative_to(project_root) else json_path.as_posix()

    return {
        "path": relative_path,
        "file_name": json_path.name,
        "season": json_path.parent.name,
        "source_file_hash": _file_hash(json_path),
        "source_game_key": source_game_key,
        "game_date": game_date.isoformat() if game_date else None,
        "game_time": game_info.get("gameTime") or game_info.get("gtime"),
        "home_team_code": home_team_code,
        "away_team_code": away_team_code,
        "home_team_name": game_info.get("hName") or game_info.get("homeTeamName"),
        "away_team_name": game_info.get("aName") or game_info.get("awayTeamName"),
        "stadium_name": game_info.get("stadium") or game_info.get("stadiumName"),
        "round_no": str(game_info.get("round") or "") or None,
        "game_flag": game_info.get("gameFlag") or game_info.get("gubun"),
        "is_postseason": _to_bool_flag(game_info.get("isPostSeason"), default=False),
        "cancel_flag": _to_bool_flag(game_info.get("cancelFlag"), default=False),
        "status_code": game_info.get("statusCode") or game_info.get("state"),
        "expected_counts": {
            "raw_games": 1,
            "raw_relay_blocks": len(raw_blocks),
            "raw_text_events": text_event_count,
            "raw_pitch_tracks": raw_pitch_track_count,
            "raw_plate_metrics": len(raw_blocks),
            "games": 1,
            "game_roster_entries": roster_expected_count,
            "innings": len(events_by_half),
            "plate_appearances": terminal_plate_appearance_count + partial_plate_appearance_count,
            "pa_events": text_event_count,
            "pitches": len(pts_pitch_ids),
            "pitch_tracking": len(pts_pitch_ids & raw_pitch_track_ids),
            "review_events": category_counts["review"],
            "substitution_events": category_counts["substitution"],
            "baserunning_events": category_counts["baserunning"],
            "batted_ball_results": category_counts["bat_result"],
        },
        "scoreboard": {key: int(value or 0) for key, value in scoreboard.items()},
        "inning_expectations": _build_inning_expectations(events_by_half),
        "expected_player_ids": expected_player_ids,
        "expected_roster_player_ids": sorted(set(lineup_player_ids) | record_player_ids),
        "record_batter_totals": record_batter_totals,
        "record_pitcher_totals": record_pitcher_totals,
        "relay_batter_totals": relay_batter_totals,
        "expected_batter_totals": expected_pa_profile["batter_totals"],
        "expected_terminal_plate_appearances": terminal_plate_appearance_count,
        "expected_partial_plate_appearances": partial_plate_appearance_count,
        "expected_null_counts": {
            "substitution_missing_player_id_count": substitution_missing_player_id_count,
        },
        "source_validation": source_validation,
    }
