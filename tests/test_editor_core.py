import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from migrate_game_json import migrate_one_file
from src.kbo_ingest.editor_core import GameEditorSession
from src.kbo_ingest.game_json import pretty_game_json


def make_editor_payload() -> dict:
    def starters(prefix: str) -> list[dict]:
        rows = [{"playerCode": f"{prefix}P", "playerName": f"{prefix} Pitcher", "position": "1", "positionName": "P"}]
        for order in range(1, 10):
            rows.append(
                {
                    "playerCode": f"{prefix}{order}",
                    "playerName": f"{prefix} Batter {order}",
                    "position": str((order % 9) + 1),
                    "positionName": "BAT",
                    "batorder": order,
                }
            )
        return rows

    return {
        "schema_version": 2,
        "game_id": "20260406TEST",
        "game_source": {"provider": "naver", "source_game_id": "20260406TEST"},
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
            "home_starter": starters("H"),
            "home_bullpen": [],
            "home_candidate": [],
            "away_starter": starters("A"),
            "away_bullpen": [],
            "away_candidate": [],
        },
        "relay": [
            [
                {
                    "title": "1회초 Away 공격",
                    "titleStyle": "0",
                    "no": 0,
                    "inn": 1,
                    "homeOrAway": "0",
                    "statusCode": 0,
                    "textOptions": [
                        {
                            "seqno": 1,
                            "type": 1,
                            "text": "1번타자 Away Batter 1",
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
                            "text": "Away Batter 1 : 삼진 아웃",
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
                            "pitchNum": 3,
                            "pitchResult": "K",
                            "ptsPitchId": "pitch-1",
                        },
                    ],
                    "ptsOptions": [{"pitchId": "pitch-1", "inn": 1, "ballcount": "2-0", "crossPlateX": 0.1}],
                }
            ]
        ],
        "record": {
            "batter": {
                "home": [],
                "away": [{"playerCode": "A1", "name": "Away Batter 1", "batOrder": 1, "ab": 1, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "rbi": 0, "run": 0, "sb": 0}],
                "homeTotal": {"ab": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "rbi": 0, "run": 0, "sb": 0},
                "awayTotal": {"ab": 1, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "rbi": 0, "run": 0, "sb": 0},
            },
            "pitcher": {
                "home": [{"pcode": "HP", "name": "Home Pitcher", "inn": "1.0", "r": 0, "er": 0, "hit": 0, "bb": 0, "kk": 1, "hr": 0, "ab": 1, "bf": 1, "pa": 1, "bbhp": 0}],
                "away": [],
            },
        },
    }


def test_editor_session_save_creates_backup_and_history(tmp_path: Path):
    path = tmp_path / "20260406TEST.json"
    path.write_text(pretty_game_json(make_editor_payload()), encoding="utf-8")

    session = GameEditorSession.load(path)
    session.apply_change("rename_home", lambda payload: payload["lineup"]["game_info"].__setitem__("hName", "New Home"))
    log = session.save(actor="tester")

    history_dir = path.parent / ".history" / path.stem
    assert log["backup_path"] is not None
    assert history_dir.exists()
    assert list(history_dir.glob("*.bak"))
    assert list(history_dir.glob("*.patch"))
    assert (history_dir / "changes.jsonl").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["lineup"]["game_info"]["hName"] == "New Home"


def test_editor_session_undo_redo_and_revert(tmp_path: Path):
    path = tmp_path / "20260406TEST.json"
    path.write_text(pretty_game_json(make_editor_payload()), encoding="utf-8")

    session = GameEditorSession.load(path)
    session.apply_change("rename_home", lambda payload: payload["lineup"]["game_info"].__setitem__("hName", "Changed"))
    assert session.payload["lineup"]["game_info"]["hName"] == "Changed"

    assert session.undo() is True
    assert session.payload["lineup"]["game_info"]["hName"] == "Home"

    assert session.redo() is True
    assert session.payload["lineup"]["game_info"]["hName"] == "Changed"

    session.revert_to_loaded()
    assert session.payload["lineup"]["game_info"]["hName"] == "Home"


def test_editor_session_detects_duplicate_relay_issues(tmp_path: Path):
    payload = make_editor_payload()
    second_event = payload["relay"][0][0]["textOptions"][1]
    second_event["seqno"] = 5
    payload["relay"][0][0]["textOptions"].append(
        {
            "seqno": 5,
            "type": 13,
            "text": "Away Batter 1 : 삼진 아웃",
            "currentGameState": dict(second_event["currentGameState"]),
            "ptsPitchId": "pitch-1",
        }
    )
    path = tmp_path / "20260406TEST.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    findings = session.scan_relay_issues()
    codes = {finding["code"] for finding in findings}

    assert "duplicate_seqno" in codes
    assert "duplicate_pts_pitch_id" in codes
    assert "seq_gap" in codes


def test_migrate_one_file_writes_minimal_schema(tmp_path: Path):
    source_path = tmp_path / "20260406TEST.json"
    raw_payload = make_editor_payload()
    raw_payload["relay"][0][0]["textOptions"][0]["currentPlayersInfo"] = {"unused": True}
    source_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = migrate_one_file(source_path, write_in_place=True, output_root=None, relative_root=tmp_path, validate=True)
    migrated = json.loads(source_path.read_text(encoding="utf-8"))

    assert result["changed"] is True
    assert result["backup_path"] is not None
    assert migrated["schema_version"] == 2
    assert "currentPlayersInfo" not in migrated["relay"][0][0]["textOptions"][0]

