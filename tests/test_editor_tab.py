import json
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

dpg = pytest.importorskip("dearpygui.dearpygui")

from gui.state import AppState
from src.kbo_ingest.correction_engine import build_offense_entry_options
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


def make_basic_split_payload() -> dict:
    payload = make_smoke_payload()
    payload["lineup"]["home_starter"] = [
        {"playerCode": "HP", "playerName": "Home Pitcher", "position": "1", "positionName": "P"},
        {"playerCode": "H1", "playerName": "Home Batter", "position": "8", "positionName": "CF", "batorder": 1},
    ]
    payload["lineup"]["away_starter"] = [
        {"playerCode": "A1", "playerName": "허경민", "position": "5", "positionName": "3B", "batorder": 3},
        {"playerCode": "A2", "playerName": "양의지", "position": "2", "positionName": "C", "batorder": 4},
    ]
    payload["lineup"]["away_candidate"] = [
        {"playerCode": "A2", "playerName": "양의지", "position": "2", "positionName": "C", "batorder": 4},
        {"playerCode": "A3", "playerName": "이유찬", "position": "6", "positionName": "SS"},
    ]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "3번타자 허경민",
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
            "text": "허경민 : 유격수 땅볼 아웃",
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
                "out": 1,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        },
        {
            "seqno": 3,
            "type": 2,
            "text": "중계 정리",
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
                "out": 1,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        },
        {
            "seqno": 4,
            "type": 1,
            "text": "헛스윙 스트라이크",
            "pitchNum": 1,
            "pitchResult": "SW",
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
                "strike": 1,
                "ball": 0,
                "out": 1,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        },
        {
            "seqno": 5,
            "type": 1,
            "text": "파울",
            "pitchNum": 2,
            "pitchResult": "F",
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
                "strike": 2,
                "ball": 0,
                "out": 1,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        },
        {
            "seqno": 6,
            "type": 13,
            "text": "좌전 안타",
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
                "out": 1,
                "base1": True,
                "base2": False,
                "base3": False,
            },
        },
    ]
    return payload
def make_basic_split_failure_payload() -> dict:
    payload = make_intro_payload()
    payload["lineup"]["away_starter"] = [
        {"playerCode": "A1", "playerName": "허경민", "position": "5", "positionName": "3B", "batorder": 3},
        {"playerCode": "A2", "playerName": "양의지", "position": "2", "positionName": "C", "batorder": 4},
    ]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "3번타자 허경민",
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
            "type": 1,
            "text": "허경민 : 파울",
            "pitchNum": 1,
            "pitchResult": "F",
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
                "ball": 0,
                "out": 0,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        },
    ]
    return payload


def make_dual_block_split_payload() -> dict:
    payload = make_basic_split_payload()
    payload["relay"][0].append(
        {
            "title": "1회말",
            "titleStyle": "0",
            "no": 1,
            "inn": 1,
            "homeOrAway": "1",
            "statusCode": 0,
            "textOptions": [
                {
                    "seqno": 7,
                    "type": 0,
                    "text": "1번타자 Home Batter",
                    "currentGameState": {
                        "homeScore": 0,
                        "awayScore": 0,
                        "homeHit": 0,
                        "awayHit": 1,
                        "homeBallFour": 0,
                        "awayBallFour": 0,
                        "homeError": 0,
                        "awayError": 0,
                        "pitcher": "A1",
                        "batter": "H1",
                        "strike": 0,
                        "ball": 0,
                        "out": 1,
                        "base1": False,
                        "base2": False,
                        "base3": False,
                    },
                }
            ],
            "ptsOptions": [],
        }
    )
    return payload


def make_same_batter_split_payload() -> dict:
    payload = make_basic_split_payload()
    for index in (3, 4, 5):
        payload["relay"][0][0]["textOptions"][index].setdefault("currentGameState", {})["batter"] = "A2"
    payload["relay"][0][0]["textOptions"][5]["batterRecord"] = {"pcode": "A2"}
    payload["relay"][0][0]["textOptions"][5]["text"] = "양의지 : 좌전 안타"
    return payload


def make_explicit_intro_split_payload() -> dict:
    payload = make_same_batter_split_payload()
    payload["relay"][0][0]["textOptions"].insert(
        3,
        {
            "seqno": 4,
            "type": 0,
            "text": "4번타자 양의지",
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
                "batter": "A2",
                "strike": 0,
                "ball": 0,
                "out": 1,
                "base1": False,
                "base2": False,
                "base3": False,
            },
        },
    )
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


def test_build_offense_entry_options_orders_starters_then_candidates():
    options = build_offense_entry_options(make_basic_split_payload(), group_index=0, block_index=0)

    assert [option["player_id"] for option in options] == ["A1", "A2", "A3"]
    assert options[0]["label"].startswith("3번 허경민")
    assert options[1]["label"].startswith("4번 양의지")
    assert options[2]["label"].startswith("후보 이유찬")


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


def test_editor_tab_basic_split_success_reassigns_segment_and_inserts_intro(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_basic_split_payload(), filename="20260406SPLIT.json")

        tab.select_event((0, 0, 3))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["split_merge"])
        tab.refresh_action_sections()
        dpg.set_value(tab._t("split_basic_batter"), "4번 양의지 (A2)")
        tab.preview_split_from_selected_event()

        preview_text = dpg.get_value(tab._t("split_basic_preview_text"))
        assert "이전 종료 이벤트: 있음" in preview_text
        assert "새 블록 생성: 예" in preview_text
        assert "새 블록 제목: 4번타자 양의지" in preview_text
        assert "intro 자동 삽입: 예" in preview_text

        tab.split_selected_plate_appearance_basic()

        relay_group = tab.session.payload["relay"][0]
        assert len(relay_group) == 2
        assert relay_group[1]["title"] == "4번타자 양의지"
        assert relay_group[0]["textOptions"][-1]["text"] == "중계 정리"
        events = relay_group[1]["textOptions"]
        assert events[0]["text"] == "4번타자 양의지"
        assert events[1]["batterRecord"]["pcode"] == "A2"
        assert events[1]["currentGameState"]["batter"] == "A2"
        assert events[1]["text"].startswith("양의지 :")
        assert events[3]["text"].startswith("양의지 :")
        assert tab.selected_event_ref == (0, 1, 0)
    finally:
        dpg.destroy_context()


def test_editor_tab_basic_split_fails_without_prior_terminal(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_basic_split_failure_payload(), filename="20260406SPLITFAIL.json")

        tab.select_event((0, 0, 1))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["split_merge"])
        tab.refresh_action_sections()
        dpg.set_value(tab._t("split_basic_batter"), "4번 양의지 (A2)")
        tab.preview_split_from_selected_event()

        assert "기본 모드에서" in dpg.get_value(tab._t("split_basic_status_text"))
        before_count = len(tab.session.payload["relay"][0][0]["textOptions"])
        tab.split_selected_plate_appearance_basic()
        after_count = len(tab.session.payload["relay"][0][0]["textOptions"])

        assert before_count == after_count
        assert tab.selected_event_ref == (0, 0, 1)
    finally:
        dpg.destroy_context()


def test_editor_tab_split_entry_options_follow_selected_block(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_dual_block_split_payload(), filename="20260406SPLITBLOCK.json")

        away_items = dpg.get_item_configuration(tab._t("split_basic_batter"))["items"]
        assert any("허경민" in item for item in away_items)
        assert all("Home Batter" not in item for item in away_items)

        tab.select_event((0, 1, 0))

        home_items = dpg.get_item_configuration(tab._t("split_basic_batter"))["items"]
        assert any("Home Batter" in item for item in home_items)
        assert all("허경민" not in item for item in home_items)
    finally:
        dpg.destroy_context()


def test_editor_tab_split_repairs_inferred_start_when_selected_segment_already_has_new_batter(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_same_batter_split_payload(), filename="20260406SPLITKEEP.json")

        tab.select_event((0, 0, 3))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["split_merge"])
        tab.refresh_action_sections()
        dpg.set_value(tab._t("split_basic_batter"), "4번 양의지 (A2)")
        tab.refresh_basic_split_card(preview=True)

        assert dpg.get_value(tab._t("split_basic_batter")) == "4번 양의지 (A2)"
        assert "새 릴레이 블록으로 분리할 수 있습니다" in dpg.get_value(tab._t("split_basic_status_text"))
        assert "새 블록 생성: 예" in dpg.get_value(tab._t("split_basic_preview_text"))
        assert "intro 자동 삽입: 예" in dpg.get_value(tab._t("split_basic_preview_text"))

        tab.split_selected_plate_appearance_basic()

        relay_group = tab.session.payload["relay"][0]
        assert len(relay_group) == 2
        assert relay_group[1]["title"] == "4번타자 양의지"
        events = relay_group[1]["textOptions"]
        assert events[0]["text"] == "4번타자 양의지"
        assert events[1]["currentGameState"]["batter"] == "A2"
        assert events[1]["text"].startswith("양의지 :")
    finally:
        dpg.destroy_context()


def test_editor_tab_split_moves_existing_intro_into_new_block_without_duplication(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_explicit_intro_split_payload(), filename="20260406SPLITINTRO.json")

        tab.select_event((0, 0, 3))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["split_merge"])
        tab.refresh_action_sections()
        dpg.set_value(tab._t("split_basic_batter"), "4번 양의지 (A2)")
        tab.preview_split_from_selected_event()

        preview_text = dpg.get_value(tab._t("split_basic_preview_text"))
        assert "새 블록 생성: 예" in preview_text
        assert "intro 자동 삽입: 아니오" in preview_text

        tab.split_selected_plate_appearance_basic()

        relay_group = tab.session.payload["relay"][0]
        assert len(relay_group) == 2
        assert relay_group[1]["title"] == "4번타자 양의지"
        events = relay_group[1]["textOptions"]
        assert events[0]["text"] == "4번타자 양의지"
        assert len([event for event in events if event["text"] == "4번타자 양의지"]) == 1
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


def test_editor_tab_basic_split_keeps_save_and_validation_flow(tmp_path: Path):
    dpg.create_context()
    try:
        tab, json_path = build_loaded_tab(tmp_path, make_basic_split_payload(), filename="20260406SPLITSAVE.json")

        tab.select_event((0, 0, 3))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["split_merge"])
        tab.refresh_action_sections()
        dpg.set_value(tab._t("split_basic_batter"), "4번 양의지 (A2)")
        tab.split_selected_plate_appearance_basic()
        tab.save_current_file()

        assert tab.validation_result is not None
        assert dpg.get_value(tab._t("basic_auto_preview_text"))
        assert (json_path.parent / ".history" / json_path.stem).exists()
        assert len(tab.session.payload["relay"][0]) == 2
    finally:
        dpg.destroy_context()


def test_editor_tab_basic_split_can_merge_back_from_new_block(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_basic_split_payload(), filename="20260406SPLITMERGE.json")

        tab.select_event((0, 0, 3))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["split_merge"])
        tab.refresh_action_sections()
        dpg.set_value(tab._t("split_basic_batter"), "4번 양의지 (A2)")
        tab.split_selected_plate_appearance_basic()

        assert len(tab.session.payload["relay"][0]) == 2
        assert tab.selected_event_ref == (0, 1, 0)

        tab.merge_selected_plate_appearance()

        assert len(tab.session.payload["relay"][0]) == 1
        assert tab.selected_event_ref is not None
        assert tab.selected_event_ref[:2] == (0, 0)
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
        assert dpg.does_item_exist(tab._t("section_pa_split_merge_advanced"))

        dpg.set_value(tab._t("editor_mode"), EDITOR_MODES[0])
        tab.apply_editor_mode()
        assert dpg.is_item_shown(tab._t("basic_mode_panel"))
        assert dpg.does_item_exist(tab._t("split_basic_summary_text"))
    finally:
        dpg.destroy_context()
