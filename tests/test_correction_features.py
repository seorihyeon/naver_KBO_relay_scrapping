import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.editor_core import GameEditorSession
from src.kbo_ingest.game_json import pretty_game_json


def make_valid_payload() -> dict:
    def starters(prefix: str, pitcher_code: str, names: list[tuple[str, str]]) -> list[dict]:
        rows = [{"playerCode": pitcher_code, "playerName": f"{prefix} Pitcher", "position": "1", "positionName": "P"}]
        positions = ["2", "3", "4", "5", "6", "7", "8", "9", "2"]
        for order, (player_code, player_name) in enumerate(names, start=1):
            rows.append(
                {
                    "playerCode": player_code,
                    "playerName": player_name,
                    "position": positions[order - 1],
                    "positionName": "BAT",
                    "batorder": order,
                }
            )
        return rows

    away_names = [
        ("A1", "\ub3c4\uc2a8"),
        ("A2", "\uc1a1\uc131\ubb38"),
        ("A3", "\uc774\uc720\ucc2c"),
        ("A4", "A4"),
        ("A5", "A5"),
        ("A6", "A6"),
        ("A7", "A7"),
        ("A8", "A8"),
        ("A9", "A9"),
    ]
    home_names = [(f"H{index}", f"H{index}") for index in range(1, 10)]

    return {
        "schema_version": 2,
        "game_id": "20260406CORRECT",
        "game_source": {"provider": "naver", "source_game_id": "20260406CORRECT"},
        "collected_at": "2026-04-06T12:00:00Z",
        "lineup": {
            "game_info": {
                "gdate": 20260406,
                "gtime": "18:30",
                "hCode": "HH",
                "hName": "Home",
                "hPCode": "HP",
                "aCode": "AW",
                "aName": "Away",
                "aPCode": "AP",
                "round": 1,
                "gameFlag": "0",
                "stadium": "Test",
                "isPostSeason": False,
                "cancelFlag": False,
                "statusCode": "1",
            },
            "home_starter": starters("H", "HP", home_names),
            "home_bullpen": [],
            "home_candidate": [],
            "away_starter": starters("A", "AP", away_names),
            "away_bullpen": [],
            "away_candidate": [],
        },
        "relay": [
            [
                {
                    "title": "1회초",
                    "titleStyle": "0",
                    "no": 0,
                    "inn": 1,
                    "homeOrAway": "0",
                    "statusCode": 0,
                    "textOptions": [
                        {
                            "seqno": 1,
                            "type": 0,
                            "text": "1번타자 도슨",
                            "currentGameState": {
                                "homeScore": 0,
                                "awayScore": 0,
                                "homeHit": 0,
                                "awayHit": 0,
                                "homeBallFour": 0,
                                "awayBallFour": 0,
                                "homeError": 0,
                                "awayError": 0,
                                "pitcher": "HP",
                                "batter": "A1",
                                "strike": 0,
                                "ball": 0,
                                "out": 0,
                                "base1": False,
                                "base2": False,
                                "base3": False,
                            },
                        },
                        {
                            "seqno": 2,
                            "type": 13,
                            "text": "도슨 : 삼진 아웃",
                            "currentGameState": {
                                "homeScore": 0,
                                "awayScore": 0,
                                "homeHit": 0,
                                "awayHit": 0,
                                "homeBallFour": 0,
                                "awayBallFour": 0,
                                "homeError": 0,
                                "awayError": 0,
                                "pitcher": "HP",
                                "batter": "A1",
                                "strike": 2,
                                "ball": 0,
                                "out": 1,
                                "base1": False,
                                "base2": False,
                                "base3": False,
                            },
                        },
                    ],
                    "ptsOptions": [],
                }
            ]
        ],
        "record": {
            "batter": {
                "home": [],
                "away": [
                    {"playerCode": "A1", "name": "\ub3c4\uc2a8", "batOrder": 1, "ab": 1, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "rbi": 0, "run": 0, "sb": 0}
                ],
                "homeTotal": {"ab": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "rbi": 0, "run": 0, "sb": 0},
                "awayTotal": {"ab": 1, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "rbi": 0, "run": 0, "sb": 0},
            },
            "pitcher": {
                "home": [{"pcode": "HP", "name": "Home Pitcher", "inn": "0.1", "r": 0, "er": 0, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "ab": 1, "bf": 1, "pa": 1, "bbhp": 0}],
                "away": [],
            },
        },
    }


def load_session(tmp_path: Path, payload: dict) -> GameEditorSession:
    path = tmp_path / "20260406CORRECT.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")
    return GameEditorSession.load(path)


def test_insert_missing_plate_appearance_rebuilds_state_but_preserves_record(tmp_path: Path):
    session = load_session(tmp_path, make_valid_payload())
    before_record = json.loads(json.dumps(session.payload["record"], ensure_ascii=False))

    inserted = session.insert_missing_plate_appearance(
        group_index=0,
        block_index=0,
        insert_at=2,
        spec={
            "batter_id": "A3",
            "batter_name": "\uc774\uc720\ucc2c",
            "pitcher_id": "HP",
            "result_type": "single",
            "detail": "\uc88c\uc804",
        },
    )

    assert inserted == [2, 3]
    result_event = session.payload["relay"][0][0]["textOptions"][3]
    assert result_event["text"].endswith("\uc88c\uc804 \uc548\ud0c0")
    assert result_event["currentGameState"]["awayHit"] == 1
    assert result_event["currentGameState"]["base1"] is True
    assert session.payload["record"] == before_record
    validation = session.validate()
    assert validation["error_count"] > 0
    assert any("relay에만 있는 타자" in finding["message"] for finding in validation["findings"])


def test_update_event_meaning_out_to_double_rebuilds_state_but_preserves_record(tmp_path: Path):
    session = load_session(tmp_path, make_valid_payload())
    before_record = json.loads(json.dumps(session.payload["record"], ensure_ascii=False))

    changed = session.update_event_meaning(
        group_index=0,
        block_index=0,
        event_index=1,
        spec={
            "result_type": "double",
            "detail": "\uc720\uaca9\uc218 \uc606",
            "batter_id": "A1",
            "batter_name": "\ub3c4\uc2a8",
            "pitcher_id": "HP",
            "replace_runner_events": True,
        },
    )

    assert changed == [1]
    result_event = session.payload["relay"][0][0]["textOptions"][1]
    assert "2\ub8e8\ud0c0" in result_event["text"]
    assert result_event["currentGameState"]["awayHit"] == 1
    assert result_event["currentGameState"]["base2"] is True
    assert session.payload["record"] == before_record
    validation = session.validate()
    assert validation["error_count"] > 0
    assert any("타자 A1" in finding["message"] and "불일치" in finding["message"] for finding in validation["findings"])


def test_split_plate_appearance_reassigns_results_but_preserves_record(tmp_path: Path):
    payload = make_valid_payload()
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "1번타자 도슨",
            "currentGameState": {
                "homeScore": 0,
                "awayScore": 0,
                "homeHit": 0,
                "awayHit": 0,
                "homeBallFour": 0,
                "awayBallFour": 0,
                "homeError": 0,
                "awayError": 0,
                "pitcher": "HP",
                "batter": "A1",
                "strike": 0,
                "ball": 0,
                "out": 0,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        },
        {"seqno": 2, "type": 1, "text": "도슨 : 스트라이크", "pitchResult": "S", "pitchNum": 1, "currentGameState": {"pitcher": "HP", "batter": "A1"}},
        {"seqno": 3, "type": 13, "text": "송성문 : 유격수 옆 2루타", "currentGameState": {"pitcher": "HP", "batter": "A1"}},
    ]
    payload["record"]["batter"]["away"] = [
        {"playerCode": "A1", "name": "\ub3c4\uc2a8", "batOrder": 1, "ab": 1, "hit": 1, "bb": 0, "kk": 0, "hr": 0, "rbi": 0, "run": 0, "sb": 0}
    ]
    payload["record"]["batter"]["awayTotal"] = {"ab": 1, "hit": 1, "bb": 0, "kk": 0, "hr": 0, "rbi": 0, "run": 0, "sb": 0}
    payload["record"]["pitcher"]["home"] = [
        {"pcode": "HP", "name": "Home Pitcher", "inn": "0.0", "r": 0, "er": 0, "hit": 1, "bb": 0, "kk": 0, "hr": 0, "ab": 1, "bf": 1, "pa": 1, "bbhp": 0}
    ]
    session = load_session(tmp_path, payload)
    before_record = json.loads(json.dumps(session.payload["record"], ensure_ascii=False))

    next_index = session.split_plate_appearance(
        group_index=0,
        block_index=0,
        split_at=2,
        spec={
            "first_batter_id": "A1",
            "first_batter_name": "\ub3c4\uc2a8",
            "first_result_type": "strikeout",
            "second_batter_id": "A2",
            "second_batter_name": "\uc1a1\uc131\ubb38",
            "second_result_type": "double",
            "second_detail": "\uc720\uaca9\uc218 \uc606",
        },
    )

    assert next_index == 3
    texts = [event["text"] for event in session.payload["relay"][0][0]["textOptions"]]
    assert texts[2].endswith("\uc0bc\uc9c4 \uc544\uc6c3")
    assert texts[3].startswith("2\ubc88\ud0c0\uc790")
    assert "2\ub8e8\ud0c0" in texts[4]
    assert session.payload["record"] == before_record
    validation = session.validate()
    assert validation["error_count"] > 0
    assert any("relay에만 있는 타자" in finding["message"] or ("타자 A1" in finding["message"] and "불일치" in finding["message"]) for finding in validation["findings"])
