import json
import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.kbo_ingest.correction_engine import rebuild_payload, rebuild_payload_with_record_sync
from src.kbo_ingest.editor_core import GameEditorSession
from src.kbo_ingest.game_json import pretty_game_json
from services.json_migration_service import migrate_one_file


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
                    "title": "1?뚯큹 Away 怨듦꺽",
                    "titleStyle": "0",
                    "no": 0,
                    "inn": 1,
                    "homeOrAway": "0",
                    "statusCode": 0,
                    "textOptions": [
                        {
                            "seqno": 1,
                            "type": 1,
                            "text": "1踰덊???Away Batter 1",
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
                            "text": "Away Batter 1 : ?쇱쭊 ?꾩썐",
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


def _rename_away_players_without_spaces(payload: dict) -> dict:
    for row in payload["lineup"]["away_starter"]:
        code = str(row.get("playerCode") or "")
        if code.startswith("A") and code[1:].isdigit():
            row["playerName"] = code
    for row in payload["record"]["batter"]["away"]:
        code = str(row.get("playerCode") or "")
        if code.startswith("A") and code[1:].isdigit():
            row["name"] = code
    return payload


def make_record_sync_payload() -> dict:
    def starters(prefix: str, team_label: str) -> list[dict]:
        rows = [{"playerCode": f"{prefix}P", "playerName": f"{team_label} ?ъ닔", "position": "1", "positionName": "P"}]
        positions = ["2", "3", "4", "5", "6", "7", "8", "9", "2"]
        for order, position in enumerate(positions, start=1):
            rows.append(
                {
                    "playerCode": f"{prefix}{order}",
                    "playerName": f"{team_label} ???{order}",
                    "position": position,
                    "positionName": "BAT",
                    "batorder": order,
                }
            )
        return rows

    def batter_rows(prefix: str, team_label: str) -> list[dict]:
        return [
            {
                "playerCode": f"{prefix}{order}",
                "name": f"{team_label} ???{order}",
                "batOrder": order,
                "ab": 0,
                "hit": 0,
                "bb": 0,
                "kk": 0,
                "hr": 0,
                "rbi": 0,
                "run": 0,
                "sb": 0,
            }
            for order in range(1, 10)
        ]

    return {
        "schema_version": 2,
        "game_id": "20260410SYNC",
        "game_source": {"provider": "naver", "source_game_id": "20260410SYNC"},
        "collected_at": "2026-04-10T12:00:00Z",
        "lineup": {
            "game_info": {
                "gdate": 20260410,
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
            "home_starter": starters("H", "Home"),
            "home_bullpen": [],
            "home_candidate": [],
            "away_starter": starters("A", "?먯젙"),
            "away_bullpen": [],
            "away_candidate": [],
        },
        "relay": [
            [
                {
                    "title": "1?뚯큹 ?먯젙 怨듦꺽",
                    "titleStyle": "0",
                    "no": 0,
                    "inn": 1,
                    "homeOrAway": "0",
                    "statusCode": 0,
                    "textOptions": [
                        {
                            "seqno": 1,
                            "type": 0,
                            "text": "1踰덊????먯젙???",
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
                            "text": "?먯젙??? : 醫뚯쟾 ?덊?",
                            "batterRecord": {"pcode": "A1"},
                            "currentGameState": {
                                "homeScore": 0,
                                "awayScore": 0,
                                "homeHit": 0,
                                "awayHit": 1,
                                "homeBallFour": 0,
                                "awayBallFour": 0,
                                "homeError": 0,
                                "awayError": 0,
                                "pitcher": "HP",
                                "batter": "A1",
                                "strike": 0,
                                "ball": 0,
                                "out": 0,
                                "base1": True,
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
                "home": batter_rows("H", "Home"),
                "away": batter_rows("A", "?먯젙"),
                "homeTotal": {"ab": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "rbi": 0, "run": 0, "sb": 0},
                "awayTotal": {"ab": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "rbi": 0, "run": 0, "sb": 0},
            },
            "pitcher": {
                "home": [{"pcode": "HP", "name": "???ъ닔", "inn": "0.0", "r": 0, "er": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "ab": 0, "bf": 0, "pa": 0, "bbhp": 0}],
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
            "text": "Away Batter 1 : ?쇱쭊 ?꾩썐",
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


def test_editor_session_allows_double_play_out_jump(tmp_path: Path):
    payload = make_editor_payload()
    payload["relay"][0][0]["textOptions"][1].update(
        {
            "text": "Away Batter 1 : 3猷⑥닔 蹂묒궡? ?꾩썐",
            "currentGameState": {
                **payload["relay"][0][0]["textOptions"][1]["currentGameState"],
                "out": 2,
                "strike": 0,
            },
        }
    )
    path = tmp_path / "20260406DOUBLEPLAY.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    findings = session.scan_relay_issues()

    assert "state_jump:out" not in {finding["code"] for finding in findings}


def test_editor_session_still_flags_unexpected_multi_out_jump(tmp_path: Path):
    payload = make_editor_payload()
    payload["relay"][0][0]["textOptions"][1].update(
        {
            "text": "Away Batter 1 : ?좉꺽???낅낵 ?꾩썐",
            "currentGameState": {
                **payload["relay"][0][0]["textOptions"][1]["currentGameState"],
                "out": 2,
                "strike": 0,
            },
        }
    )
    path = tmp_path / "20260406BADOUTJUMP.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    findings = session.scan_relay_issues()

    assert "state_jump:out" in {finding["code"] for finding in findings}


def test_editor_session_flags_missing_pitch_event_gap(tmp_path: Path):
    payload = make_editor_payload()
    intro_event = json.loads(json.dumps(payload["relay"][0][0]["textOptions"][0], ensure_ascii=False))
    base_state = intro_event["currentGameState"]
    payload["relay"][0][0]["textOptions"] = [
        intro_event,
        {
            "seqno": 2,
            "type": 1,
            "text": "Away Batter 1 : strike",
            "pitchNum": 1,
            "pitchResult": "S",
            "currentGameState": {
                **base_state,
                "strike": 1,
            },
            "batterRecord": {"pcode": "A1"},
        },
        {
            "seqno": 3,
            "type": 1,
            "text": "Away Batter 1 : foul",
            "pitchNum": 3,
            "pitchResult": "F",
            "currentGameState": {
                **base_state,
                "strike": 2,
            },
            "batterRecord": {"pcode": "A1"},
        },
    ]
    path = tmp_path / "20260411MISSINGPITCH.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    findings = session.scan_relay_issues()
    missing_pitch = [finding for finding in findings if finding["code"] == "missing_pitch_event"]

    assert missing_pitch
    assert missing_pitch[0]["severity"] == "error"
    assert missing_pitch[0]["location"] == {"tab": "relay", "group_index": 0, "block_index": 0, "event_index": 2}
    assert "1 -> 3" in missing_pitch[0]["message"]


def test_editor_session_validate_flags_pitch_after_terminal_as_merged_pa(tmp_path: Path):
    payload = make_editor_payload()
    for side in ("home", "away"):
        payload["lineup"][f"{side}_starter"][-1]["position"] = "9"
        payload["lineup"][f"{side}_starter"][-1]["positionName"] = "BAT"
    payload["relay"][0][0]["textOptions"].append(
        {
            "seqno": 3,
            "type": 1,
            "text": "Ball",
            "pitchNum": 4,
            "pitchResult": "B",
            "currentGameState": {
                **payload["relay"][0][0]["textOptions"][1]["currentGameState"],
                "ball": 1,
                "strike": 0,
            },
            "batterRecord": {"pcode": "A2"},
        }
    )
    path = tmp_path / "20260406MERGEDPA_PITCH.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    findings = session.validate()["findings"]
    merged = [finding for finding in findings if finding["code"] == "merged_pa_pitch_after_terminal"]

    assert merged
    assert merged[0]["severity"] == "error"
    assert merged[0]["location"] == {"tab": "relay", "group_index": 0, "block_index": 0, "event_index": 2}


def test_editor_session_validate_flags_multiple_terminal_results_as_merged_pa(tmp_path: Path):
    payload = make_editor_payload()
    for side in ("home", "away"):
        payload["lineup"][f"{side}_starter"][-1]["position"] = "9"
        payload["lineup"][f"{side}_starter"][-1]["positionName"] = "BAT"
    payload["relay"][0][0]["textOptions"].append(
        {
            "seqno": 3,
            "type": 13,
            "text": "Away Batter 2 : ?곗쟾 ?덊?",
            "currentGameState": {
                **payload["relay"][0][0]["textOptions"][1]["currentGameState"],
                "batter": "A2",
                "awayHit": 1,
                "base1": True,
                "out": 1,
            },
            "batterRecord": {"pcode": "A2"},
        }
    )
    path = tmp_path / "20260406MERGEDPA_RESULT.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    findings = session.validate()["findings"]
    merged = [finding for finding in findings if finding["code"] == "merged_pa_multiple_terminal"]

    assert merged
    assert merged[0]["severity"] == "error"
    assert merged[0]["location"] == {"tab": "relay", "group_index": 0, "block_index": 0, "event_index": 2}


def test_editor_session_validate_surfaces_partial_plate_appearance_location(tmp_path: Path):
    payload = make_record_sync_payload()
    payload["relay"][0][0]["textOptions"] = payload["relay"][0][0]["textOptions"][:1] + [
        {
            "seqno": 2,
            "type": 1,
            "text": "Strike",
            "pitchNum": 1,
            "pitchResult": "S",
            "currentGameState": {
                **payload["relay"][0][0]["textOptions"][0]["currentGameState"],
                "strike": 1,
            },
        },
        {
            "seqno": 3,
            "type": 1,
            "text": "In play",
            "pitchNum": 2,
            "pitchResult": "X",
            "batterRecord": {"pcode": "A1"},
            "currentGameState": {
                **payload["relay"][0][0]["textOptions"][0]["currentGameState"],
                "strike": 1,
            },
        },
    ]
    payload["record"]["batter"]["away"][0]["ab"] = 1
    payload["record"]["batter"]["awayTotal"]["ab"] = 1
    payload["record"]["pitcher"]["home"][0]["ab"] = 1
    payload["record"]["pitcher"]["home"][0]["pa"] = 1
    payload["record"]["pitcher"]["home"][0]["inn"] = "0.1"

    path = tmp_path / "20260410PARTIAL.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    findings = session.validate()["findings"]
    partial = [finding for finding in findings if finding["code"] == "partial_plate_appearance"]

    assert partial
    assert partial[0]["severity"] == "warning"
    assert partial[0]["location"] == {"tab": "relay", "group_index": 0, "block_index": 0, "event_index": 1}
    assert "record" in partial[0]["message"]


def test_editor_session_auto_rebuild_preserves_record_rows(tmp_path: Path):
    payload = make_editor_payload()
    payload["record"]["batter"]["away"][0]["kk"] = 99
    payload["record"]["batter"]["awayTotal"]["kk"] = 99
    payload["relay"][0][0]["textOptions"][1]["currentGameState"]["out"] = 0
    path = tmp_path / "20260406AUTOREBUILD.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    before_record = json.loads(json.dumps(session.payload["record"], ensure_ascii=False))

    preview = session.preview_auto_rebuild()
    assert preview["payload"]["relay"][0][0]["textOptions"][1]["currentGameState"]["out"] == 1
    assert preview["payload"]["record"] == before_record

    session.apply_auto_rebuild()

    assert session.payload["relay"][0][0]["textOptions"][1]["currentGameState"]["out"] == 1
    assert session.payload["record"] == before_record


def test_editor_session_insert_bat_result_preserves_record_rows(tmp_path: Path):
    payload = make_editor_payload()
    payload["record"]["batter"]["away"][0]["ab"] = 3
    payload["record"]["batter"]["awayTotal"]["ab"] = 3
    path = tmp_path / "20260406INSERTRESULT.json"
    path.write_text(pretty_game_json(payload), encoding="utf-8")

    session = GameEditorSession.load(path)
    before_record = json.loads(json.dumps(session.payload["record"], ensure_ascii=False))

    inserted = session.insert_event_template(
        group_index=0,
        block_index=0,
        insert_at=2,
        template_type="bat_result",
        spec={
            "batter_id": "A1",
            "batter_name": "Away Batter 1",
            "pitcher_id": "HP",
            "result_type": "single",
            "text": "Away Batter 1 : ?곗쟾 ?덊?",
        },
    )

    assert inserted == [2]
    assert session.payload["relay"][0][0]["textOptions"][2]["type"] == 13
    assert session.payload["record"] == before_record


def test_rebuild_payload_with_record_sync_recomputes_record_rows():
    payload = make_editor_payload()
    payload["record"]["batter"]["away"][0]["ab"] = 99
    payload["record"]["batter"]["away"][0]["kk"] = 99
    payload["record"]["batter"]["awayTotal"]["ab"] = 99
    payload["record"]["batter"]["awayTotal"]["kk"] = 99
    payload["record"]["pitcher"]["home"][0]["inn"] = "9.0"

    rebuilt, _report = rebuild_payload_with_record_sync(payload)

    assert rebuilt["record"]["batter"]["away"][0]["ab"] == 1
    assert rebuilt["record"]["batter"]["away"][0]["kk"] == 0
    assert rebuilt["record"]["batter"]["awayTotal"]["ab"] == 1
    assert rebuilt["record"]["batter"]["awayTotal"]["kk"] == 0
    assert rebuilt["record"]["pitcher"]["home"][0]["inn"] == "0.1"


def test_rebuild_payload_runner_out_event_clears_base():
    payload = _rename_away_players_without_spaces(make_editor_payload())
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "1번타자 A1",
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
            "text": "A1 : 우전 안타",
            "currentGameState": {"pitcher": "HP", "batter": "A1"},
        },
        {
            "seqno": 3,
            "type": 14,
            "text": "1루주자 A1 : 태그아웃 (1루수->2루수 태그아웃)",
            "currentGameState": {"pitcher": "HP", "batter": "A1"},
        },
        {
            "seqno": 4,
            "type": 0,
            "text": "2번타자 A2",
            "currentGameState": {"pitcher": "HP", "batter": "A2"},
        },
    ]

    rebuilt, _report = rebuild_payload(payload)
    runner_out_state = rebuilt["relay"][0][0]["textOptions"][2]["currentGameState"]
    next_intro_state = rebuilt["relay"][0][0]["textOptions"][3]["currentGameState"]

    assert runner_out_state["out"] == 1
    assert runner_out_state["base1"] is False
    assert next_intro_state["out"] == 1
    assert next_intro_state["base1"] is False


def test_rebuild_payload_explicit_home_in_does_not_double_score():
    payload = _rename_away_players_without_spaces(make_editor_payload())
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "1번타자 A1",
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
            "text": "A1 : 좌전 안타",
            "currentGameState": {"pitcher": "HP", "batter": "A1"},
        },
        {
            "seqno": 3,
            "type": 14,
            "text": "1루주자 A1 : 도루로 2루까지 진루",
            "currentGameState": {"pitcher": "HP", "batter": "A1"},
        },
        {
            "seqno": 4,
            "type": 0,
            "text": "2번타자 A2",
            "currentGameState": {"pitcher": "HP", "batter": "A2"},
        },
        {
            "seqno": 5,
            "type": 23,
            "text": "A2 : 좌중간 뒤 홈런",
            "currentGameState": {"pitcher": "HP", "batter": "A2"},
        },
        {
            "seqno": 6,
            "type": 24,
            "text": "2루주자 A1 : 홈인",
            "currentGameState": {"pitcher": "HP", "batter": "A2"},
        },
    ]

    rebuilt, _report = rebuild_payload(payload)
    homer_state = rebuilt["relay"][0][0]["textOptions"][4]["currentGameState"]
    home_in_state = rebuilt["relay"][0][0]["textOptions"][5]["currentGameState"]

    assert homer_state["awayScore"] == 2
    assert home_in_state["awayScore"] == 2
    assert home_in_state["base1"] is False
    assert home_in_state["base2"] is False
    assert home_in_state["base3"] is False


def test_rebuild_payload_runner_move_follows_runner_identity_after_default_advance():
    payload = _rename_away_players_without_spaces(make_editor_payload())
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "1번타자 A1",
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
            "text": "A1 : 좌전 안타",
            "currentGameState": {"pitcher": "HP", "batter": "A1"},
        },
        {
            "seqno": 3,
            "type": 0,
            "text": "2번타자 A2",
            "currentGameState": {"pitcher": "HP", "batter": "A2"},
        },
        {
            "seqno": 4,
            "type": 13,
            "text": "A2 : 좌전 안타",
            "currentGameState": {"pitcher": "HP", "batter": "A2"},
        },
        {
            "seqno": 5,
            "type": 24,
            "text": "1루주자 A1 : 3루까지 진루",
            "currentGameState": {"pitcher": "HP", "batter": "A2"},
        },
    ]

    rebuilt, _report = rebuild_payload(payload)
    advance_state = rebuilt["relay"][0][0]["textOptions"][4]["currentGameState"]

    assert advance_state["awayHit"] == 2
    assert advance_state["base1"] is True
    assert advance_state["base2"] is False
    assert advance_state["base3"] is True


def test_editor_session_sync_record_with_relay_clears_validate_game_mismatches(tmp_path: Path):
    path = tmp_path / "20260410SYNC.json"
    path.write_text(pretty_game_json(make_record_sync_payload()), encoding="utf-8")

    session = GameEditorSession.load(path)
    before_messages = [finding["message"] for finding in session.validate()["findings"] if finding["code"] == "validate_game"]

    assert before_messages

    result = session.sync_record_with_relay()
    after_validation = session.validate()
    after_messages = [finding["message"] for finding in after_validation["findings"] if finding["code"] == "validate_game"]

    assert result["sync_record"] is True
    assert result["changed_paths"]
    assert after_validation["ok"] is True
    assert not after_messages


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


