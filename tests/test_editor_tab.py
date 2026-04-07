import json
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

dpg = pytest.importorskip("dearpygui.dearpygui")

from tabs.editor_tab import CorrectionEditorTab
from gui.state import AppState


def make_smoke_payload() -> dict:
    return {
        "schema_version": 2,
        "game_id": "20260406SMOKE",
        "game_source": {"provider": "naver", "source_game_id": "20260406SMOKE"},
        "collected_at": "2026-04-06T12:00:00Z",
        "lineup": {
            "game_info": {"gdate": 20260406, "gtime": "18:30", "hName": "Home", "aName": "Away"},
            "home_starter": [],
            "home_bullpen": [],
            "home_candidate": [],
            "away_starter": [],
            "away_bullpen": [],
            "away_candidate": [],
        },
        "relay": [[{"title": "1회초", "titleStyle": "0", "no": 0, "inn": 1, "homeOrAway": "0", "statusCode": 0, "textOptions": [], "ptsOptions": []}]],
        "record": {"batter": {"home": [], "away": [], "homeTotal": {}, "awayTotal": {}}, "pitcher": {"home": [], "away": []}},
    }


def test_editor_tab_smoke_load_edit_save(tmp_path: Path):
    json_path = tmp_path / "20260406SMOKE.json"
    json_path.write_text(json.dumps(make_smoke_payload(), ensure_ascii=False, indent=2), encoding="utf-8")

    state = AppState(config={})
    state.default_data_dir = str(tmp_path)
    tab = CorrectionEditorTab(state)

    dpg.create_context()
    try:
        with dpg.window():
            with dpg.tab_bar(tag="root_tab_bar"):
                tab.build(parent="root_tab_bar")

        tab.refresh_file_list()
        dpg.set_value(tab._t("file_list"), json_path.name)
        tab.load_selected_file()

        assert tab.session is not None

        dpg.set_value(tab._t("game_info_hName"), "Edited Home")
        tab.apply_game_info_editor()
        tab.save_current_file()

        saved = json.loads(json_path.read_text(encoding="utf-8"))
        assert saved["lineup"]["game_info"]["hName"] == "Edited Home"
        assert (json_path.parent / ".history" / json_path.stem).exists()
    finally:
        dpg.destroy_context()


def test_editor_tab_structured_missing_pa_action(tmp_path: Path):
    json_path = tmp_path / "20260406SMOKE.json"
    payload = make_smoke_payload()
    payload["lineup"]["home_starter"] = [{"playerCode": "HP", "playerName": "Home Pitcher", "position": "1", "positionName": "P"}]
    payload["lineup"]["away_starter"] = [
        {"playerCode": "AP", "playerName": "Away Pitcher", "position": "1", "positionName": "P"},
        {"playerCode": "A1", "playerName": "Dawson", "position": "2", "positionName": "BAT", "batorder": 1},
        {"playerCode": "A2", "playerName": "Yi", "position": "3", "positionName": "BAT", "batorder": 2},
    ]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "1번타자 Dawson",
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
        }
    ]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    state = AppState(config={})
    state.default_data_dir = str(tmp_path)
    tab = CorrectionEditorTab(state)

    dpg.create_context()
    try:
        with dpg.window():
            with dpg.tab_bar(tag="root_tab_bar"):
                tab.build(parent="root_tab_bar")

        tab.refresh_file_list()
        dpg.set_value(tab._t("file_list"), json_path.name)
        tab.load_selected_file()

        dpg.set_value(tab._t("pa_batter_id"), "A2")
        dpg.set_value(tab._t("pa_batter_name"), "Yi")
        dpg.set_value(tab._t("pa_pitcher_id"), "HP")
        dpg.set_value(tab._t("pa_result_type"), "single")
        dpg.set_value(tab._t("pa_detail"), "좌전")
        tab.insert_missing_plate_appearance()

        assert tab.session is not None
        assert len(tab.session.payload["relay"][0][0]["textOptions"]) >= 3
        assert any("안타" in event["text"] for event in tab.session.payload["relay"][0][0]["textOptions"])
    finally:
        dpg.destroy_context()


def test_editor_tab_autofills_meaning_edit_from_selected_event(tmp_path: Path):
    json_path = tmp_path / "20260406AUTO.json"
    payload = make_smoke_payload()
    payload["lineup"]["home_starter"] = [{"playerCode": "HP", "playerName": "Home Pitcher", "position": "1", "positionName": "P"}]
    payload["lineup"]["away_starter"] = [
        {"playerCode": "A1", "playerName": "\uc774\uc720\ucc2c", "position": "8", "positionName": "CF", "batorder": 1},
        {"playerCode": "A2", "playerName": "\uc1a1\uc131\ubb38", "position": "6", "positionName": "SS", "batorder": 2},
    ]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 13,
            "text": "\uc774\uc720\ucc2c : \uc720\uaca9\uc218 \uc606 2\ub8e8\ud0c0",
            "pitchResult": "X",
            "pitchNum": 3,
            "ptsPitchId": "pitch-1",
            "batterRecord": {"pcode": "A1"},
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
                "strike": 1,
                "ball": 1,
                "out": 0,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        }
    ]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    state = AppState(config={})
    state.default_data_dir = str(tmp_path)
    tab = CorrectionEditorTab(state)

    dpg.create_context()
    try:
        with dpg.window():
            with dpg.tab_bar(tag="root_tab_bar"):
                tab.build(parent="root_tab_bar")

        tab.refresh_file_list()
        dpg.set_value(tab._t("file_list"), json_path.name)
        tab.load_selected_file()

        assert dpg.get_value(tab._t("meaning_batter_id")) == "A1"
        assert dpg.get_value(tab._t("meaning_batter_name")) == "\uc774\uc720\ucc2c"
        assert dpg.get_value(tab._t("meaning_pitcher_id")) == "HP"
        assert dpg.get_value(tab._t("meaning_text")) == "\uc774\uc720\ucc2c : \uc720\uaca9\uc218 \uc606 2\ub8e8\ud0c0"
        assert dpg.get_value(tab._t("meaning_result_type")) == "double"
        assert dpg.get_value(tab._t("split_first_batter_id")) == "A1"
        assert dpg.get_value(tab._t("split_second_batter_id")) == "A2"
    finally:
        dpg.destroy_context()


def test_editor_tab_editor_mode_and_context_summary(tmp_path: Path):
    json_path = tmp_path / "20260406MODE.json"
    payload = make_smoke_payload()
    payload["lineup"]["home_starter"] = [{"playerCode": "HP", "playerName": "Home Pitcher", "position": "1", "positionName": "P"}]
    payload["lineup"]["away_starter"] = [{"playerCode": "A1", "playerName": "Kim", "position": "8", "positionName": "CF", "batorder": 1}]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 13,
            "text": "Kim : single",
            "batterRecord": {"pcode": "A1"},
            "currentGameState": {
                "homeScore": 0,
                "awayScore": 1,
                "homeHit": 0,
                "awayHit": 1,
                "homeBallFour": 0,
                "awayBallFour": 0,
                "homeError": 0,
                "awayError": 0,
                "pitcher": "HP",
                "batter": "A1",
                "strike": 0,
                "ball": 1,
                "out": 0,
                "base1": True,
                "base2": False,
                "base3": False,
            },
        }
    ]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    state = AppState(config={})
    state.default_data_dir = str(tmp_path)
    tab = CorrectionEditorTab(state)

    dpg.create_context()
    try:
        with dpg.window():
            with dpg.tab_bar(tag="root_tab_bar"):
                tab.build(parent="root_tab_bar")

        tab.refresh_file_list()
        dpg.set_value(tab._t("file_list"), json_path.name)
        tab.load_selected_file()

        summary = dpg.get_value(tab._t("context_summary_text"))
        assert "Batter: Kim" in summary
        assert "Pitcher: Home Pitcher" in summary

        dpg.set_value(tab._t("editor_mode"), "Relay Raw")
        tab.apply_editor_mode()
        assert dpg.is_item_shown(tab._t("section_relay_event"))
        assert not dpg.is_item_shown(tab._t("section_meaning_edit"))
    finally:
        dpg.destroy_context()
