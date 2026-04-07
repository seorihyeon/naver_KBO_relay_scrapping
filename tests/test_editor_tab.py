import json
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

dpg = pytest.importorskip("dearpygui.dearpygui")

from gui.state import AppState
from tabs.editor_tab import (
    ACTION_LABELS,
    ADD_TEMPLATE_LABELS,
    EDITOR_MODES,
    INSERT_MODE_LABELS,
    PITCH_RESULT_LABELS,
    RESULT_TYPE_LABELS,
    CorrectionEditorTab,
)


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


def build_loaded_tab(tmp_path: Path, payload: dict, filename: str = "20260406SMOKE.json") -> tuple[CorrectionEditorTab, Path]:
    json_path = tmp_path / filename
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    state = AppState(config={})
    state.default_data_dir = str(tmp_path)
    tab = CorrectionEditorTab(state)

    with dpg.window():
        with dpg.tab_bar(tag="root_tab_bar"):
            tab.build(parent="root_tab_bar")

    tab.refresh_file_list()
    dpg.set_value(tab._t("file_list"), json_path.name)
    tab.load_selected_file()
    return tab, json_path


def make_intro_payload() -> dict:
    payload = make_smoke_payload()
    payload["lineup"]["home_starter"] = [{"playerCode": "HP", "playerName": "Home Pitcher", "position": "1", "positionName": "P"}]
    payload["lineup"]["away_starter"] = [
        {"playerCode": "A1", "playerName": "Kim", "position": "8", "positionName": "CF", "batorder": 1},
        {"playerCode": "A2", "playerName": "Lee", "position": "4", "positionName": "2B", "batorder": 2},
    ]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "1번타자 Kim",
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
    return payload


def make_terminal_pa_payload() -> dict:
    payload = make_intro_payload()
    payload["relay"][0][0]["textOptions"].append(
        {
            "seqno": 2,
            "type": 13,
            "text": "Kim : 좌전 안타",
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
        }
    )
    return payload


def make_pitch_then_result_payload() -> dict:
    payload = make_intro_payload()
    payload["relay"][0][0]["textOptions"].append(
        {
            "seqno": 2,
            "type": 1,
            "text": "Kim : 타격",
            "pitchNum": 1,
            "pitchResult": "X",
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
                "strike": 0,
                "ball": 0,
                "out": 0,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        }
    )
    return payload


def make_loaded_state_payload() -> dict:
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
    return payload


def test_editor_tab_basic_mode_primary_components_render(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_loaded_state_payload())

        assert tab.session is not None
        assert tab.validation_result is not None
        assert dpg.does_item_exist(tab._t("file_panel"))
        assert dpg.does_item_exist(tab._t("findings_table"))
        assert dpg.does_item_exist(tab._t("context_summary_text"))
        assert dpg.does_item_exist(tab._t("context_flow_text"))
        assert dpg.does_item_exist(tab._t("action_selector"))
        assert dpg.does_item_exist(tab._t("add_context_hint"))
        assert dpg.is_item_shown(tab._t("basic_mode_panel"))
        assert not dpg.is_item_shown(tab._t("advanced_mode_panel"))
    finally:
        dpg.destroy_context()


def test_editor_tab_finding_selection_jumps_to_location(tmp_path: Path):
    payload = make_smoke_payload()
    payload["lineup"]["away_starter"] = [{"playerCode": "A1", "playerName": "Kim", "position": "8", "positionName": "CF", "batorder": 1}]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 1,
            "text": "Kim : strike",
            "pitchNum": 1,
            "pitchResult": "S",
            "currentGameState": {
                "homeScore": 0,
                "awayScore": 0,
                "homeHit": 0,
                "awayHit": 0,
                "homeBallFour": 0,
                "awayBallFour": 0,
                "homeError": 0,
                "awayError": 0,
                "batter": "A1",
                "strike": 1,
                "ball": 0,
                "out": 0,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        }
    ]

    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, payload, filename="20260406FINDING.json")
        tab.run_validation()

        finding_index = next(index for index, finding in enumerate(tab.validation_result["findings"]) if finding["code"] == "missing_pitcher")
        tab.select_finding(finding_index)

        assert tab.selected_event_ref == (0, 0, 0)
        assert dpg.get_value(tab._t("action_selector")) == ACTION_LABELS["meaning"]
    finally:
        dpg.destroy_context()


def test_editor_tab_selection_updates_action_defaults(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_terminal_pa_payload(), filename="20260406ACTION.json")

        dpg.set_value(tab._t("add_insert_mode"), INSERT_MODE_LABELS["after"])
        tab.refresh_add_action_form()
        assert dpg.get_value(tab._t("add_batter_id")) == "A1"

        tab.select_event((0, 0, 1))

        assert dpg.get_value(tab._t("action_selector")) == ACTION_LABELS["meaning"]
        assert dpg.get_value(tab._t("add_batter_id")) == "A2"
        assert "Lee (A2)" in dpg.get_value(tab._t("add_context_hint"))
    finally:
        dpg.destroy_context()


def test_editor_tab_add_pitch_with_blank_pts_pitch_id(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_intro_payload(), filename="20260406PITCHADD.json")

        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["add"])
        dpg.set_value(tab._t("add_insert_mode"), INSERT_MODE_LABELS["after"])
        dpg.set_value(tab._t("add_template_type"), ADD_TEMPLATE_LABELS["pitch"])
        tab.refresh_add_action_form()
        dpg.set_value(tab._t("add_pitch_result_display"), PITCH_RESULT_LABELS["X"])
        dpg.set_value(tab._t("add_pts_pitch_id"), "")
        tab.insert_structured_event()

        events = tab.session.payload["relay"][0][0]["textOptions"]
        inserted = events[1]

        assert len(events) == 2
        assert inserted["type"] == 1
        assert inserted["pitchResult"] == "X"
        assert inserted.get("ptsPitchId") in (None, "")
        assert inserted["batterRecord"]["pcode"] == "A1"
        assert inserted["currentGameState"]["batter"] == "A1"
        assert inserted["pitchNum"] == 1
        assert dpg.get_value(tab._t("basic_auto_preview_text"))
    finally:
        dpg.destroy_context()


def test_editor_tab_add_bat_result_flow(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_pitch_then_result_payload(), filename="20260406BATRESULT.json")

        tab.select_event((0, 0, 1))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["add"])
        dpg.set_value(tab._t("add_insert_mode"), INSERT_MODE_LABELS["after"])
        dpg.set_value(tab._t("add_template_type"), ADD_TEMPLATE_LABELS["bat_result"])
        tab.refresh_add_action_form()
        dpg.set_value(tab._t("add_result_type"), RESULT_TYPE_LABELS["single"])
        dpg.set_value(tab._t("add_text"), "좌전 안타")
        tab.insert_structured_event()

        events = tab.session.payload["relay"][0][0]["textOptions"]
        inserted = events[2]

        assert len(events) == 3
        assert inserted["type"] == 13
        assert "좌전 안타" in inserted["text"]
        assert inserted["batterRecord"]["pcode"] == "A1"
        assert inserted["pitchNum"] == 1
        assert inserted["currentGameState"]["batter"] == "A1"
    finally:
        dpg.destroy_context()


def test_editor_tab_structured_missing_pa_action_keeps_save_and_validation_flow(tmp_path: Path):
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

    dpg.create_context()
    try:
        tab, json_path = build_loaded_tab(tmp_path, payload)

        dpg.set_value(tab._t("pa_batter_id"), "A2")
        dpg.set_value(tab._t("pa_batter_name"), "Yi")
        dpg.set_value(tab._t("pa_pitcher_id"), "HP")
        dpg.set_value(tab._t("pa_result_type"), RESULT_TYPE_LABELS["single"])
        dpg.set_value(tab._t("pa_detail"), "좌전")
        tab.insert_missing_plate_appearance()
        tab.save_current_file()

        assert tab.validation_result is not None
        assert len(tab.session.payload["relay"][0][0]["textOptions"]) >= 3
        assert any("안타" in event["text"] for event in tab.session.payload["relay"][0][0]["textOptions"])
        assert dpg.get_value(tab._t("basic_auto_preview_text"))
        assert (json_path.parent / ".history" / json_path.stem).exists()
    finally:
        dpg.destroy_context()


def test_editor_tab_mode_switch_and_context_summary(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_loaded_state_payload(), filename="20260406MODE.json")

        summary = dpg.get_value(tab._t("context_summary_text"))
        assert "타자/투수: Kim vs Home Pitcher" in summary
        assert "현재 타석: 이벤트 0-0 | 결과 Kim : single" in summary

        dpg.set_value(tab._t("editor_mode"), EDITOR_MODES[1])
        tab.apply_editor_mode()
        assert dpg.is_item_shown(tab._t("advanced_mode_panel"))
        assert not dpg.is_item_shown(tab._t("basic_mode_panel"))

        dpg.set_value(tab._t("editor_mode"), EDITOR_MODES[0])
        tab.apply_editor_mode()
        assert dpg.is_item_shown(tab._t("basic_mode_panel"))
    finally:
        dpg.destroy_context()
