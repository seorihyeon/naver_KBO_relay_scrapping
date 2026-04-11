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
    FINDING_TABLE_INNER_WIDTH,
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
        "relay": [[{"title": "1?뚯큹", "titleStyle": "0", "no": 0, "inn": 1, "homeOrAway": "0", "statusCode": 0, "textOptions": [], "ptsOptions": []}]],
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


def build_unloaded_tab(tmp_path: Path) -> CorrectionEditorTab:
    state = AppState(config={})
    state.default_data_dir = str(tmp_path)
    tab = CorrectionEditorTab(state)

    with dpg.window():
        with dpg.tab_bar(tag="root_tab_bar"):
            tab.build(parent="root_tab_bar")
    return tab


def collect_item_labels(root_item: int | str) -> set[str]:
    labels: set[str] = set()
    stack: list[int | str] = [root_item]
    seen: set[int | str] = set()

    while stack:
        item = stack.pop()
        if item in seen:
            continue
        seen.add(item)
        config = dpg.get_item_configuration(item)
        label = str(config.get("label") or "")
        if label:
            labels.add(label)
        children = dpg.get_item_children(item)
        child_groups = children.values() if isinstance(children, dict) else children
        for group in child_groups:
            stack.extend(group)

    return labels



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
            "text": "1踰덊???Kim",
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
            "text": "Kim : 醫뚯쟾 ?덊?",
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
            "text": "Kim : in play",
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


def make_record_sync_validation_payload() -> dict:
    payload = make_terminal_pa_payload()
    positions = ["2", "3", "4", "5", "6", "7", "8", "9", "2"]
    payload["lineup"]["home_starter"] = [{"playerCode": "HP", "playerName": "Home Pitcher", "position": "1", "positionName": "P"}]
    payload["lineup"]["away_starter"] = [{"playerCode": "AP", "playerName": "?먯젙?ъ닔", "position": "1", "positionName": "P"}]
    for order, position in enumerate(positions, start=1):
        payload["lineup"]["home_starter"].append(
            {"playerCode": f"H{order}", "playerName": f"Home Batter {order}", "position": position, "positionName": "BAT", "batorder": order}
        )
        payload["lineup"]["away_starter"].append(
            {"playerCode": f"A{order}", "playerName": f"Away Batter {order}", "position": position, "positionName": "BAT", "batorder": order}
        )

    payload["relay"][0][0]["title"] = "1?뚯큹 ?먯젙 怨듦꺽"
    payload["relay"][0][0]["textOptions"][0]["text"] = "1踰덊????먯젙???"
    payload["relay"][0][0]["textOptions"][1]["text"] = "?먯젙??? : 醫뚯쟾 ?덊?"
    payload["relay"][0][0]["textOptions"][1]["currentGameState"]["pitcher"] = "HP"

    def batter_rows(prefix: str, team_label: str) -> list[dict]:
        return [
            {
                "playerCode": f"{prefix}{order}",
                "name": f"{team_label} Batter {order}",
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

    payload["record"]["batter"] = {
        "home": batter_rows("H", "Home"),
        "away": batter_rows("A", "?먯젙"),
        "homeTotal": {"ab": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "rbi": 0, "run": 0, "sb": 0},
        "awayTotal": {"ab": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "rbi": 0, "run": 0, "sb": 0},
    }
    payload["record"]["pitcher"] = {
        "home": [{"pcode": "HP", "name": "Home Pitcher", "inn": "0.0", "r": 0, "er": 0, "hit": 0, "bb": 0, "kk": 0, "hr": 0, "ab": 0, "bf": 0, "pa": 0, "bbhp": 0}],
        "away": [],
    }
    return payload


def make_basic_split_payload() -> dict:
    payload = make_smoke_payload()
    payload["lineup"]["home_starter"] = [
        {"playerCode": "HP", "playerName": "Home Pitcher", "position": "1", "positionName": "P"},
        {"playerCode": "H1", "playerName": "Home Batter", "position": "8", "positionName": "CF", "batorder": 1},
    ]
    payload["lineup"]["away_starter"] = [
        {"playerCode": "A1", "playerName": "Kim", "position": "5", "positionName": "3B", "batorder": 3},
        {"playerCode": "A2", "playerName": "?묒쓽吏", "position": "2", "positionName": "C", "batorder": 4},
    ]
    payload["lineup"]["away_candidate"] = [
        {"playerCode": "A2", "playerName": "?묒쓽吏", "position": "2", "positionName": "C", "batorder": 4},
        {"playerCode": "A3", "playerName": "Choi", "position": "6", "positionName": "SS"},
    ]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "3번타자 Kim",
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
            "text": "?덇꼍誘?: ?좉꺽???낅낵 ?꾩썐",
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
            "text": "以묎퀎 ?뺣━",
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
            "text": "swinging strike",
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
            "text": "?뚯슱",
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
            "text": "醫뚯쟾 ?덊?",
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
        {"playerCode": "A1", "playerName": "Kim", "position": "5", "positionName": "3B", "batorder": 3},
        {"playerCode": "A2", "playerName": "?묒쓽吏", "position": "2", "positionName": "C", "batorder": 4},
    ]
    payload["relay"][0][0]["textOptions"] = [
        {
            "seqno": 1,
            "type": 0,
            "text": "3번타자 Kim",
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
            "text": "?덇꼍誘?: ?뚯슱",
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
            "title": "1?뚮쭚",
            "titleStyle": "0",
            "no": 1,
            "inn": 1,
            "homeOrAway": "1",
            "statusCode": 0,
            "textOptions": [
                {
                    "seqno": 7,
                    "type": 0,
                    "text": "1踰덊???Home Batter",
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
    payload["relay"][0][0]["textOptions"][5]["text"] = "?묒쓽吏 : 醫뚯쟾 ?덊?"
    return payload


def make_explicit_intro_split_payload() -> dict:
    payload = make_same_batter_split_payload()
    payload["relay"][0][0]["textOptions"].insert(
        3,
        {
            "seqno": 4,
            "type": 0,
            "text": "4踰덊????묒쓽吏",
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
        assert dpg.does_item_exist(tab._t("findings_panel"))
        assert dpg.does_item_exist(tab._t("findings_table"))
        assert dpg.does_item_exist(tab._t("context_summary_text"))
        assert dpg.does_item_exist(tab._t("context_flow_text"))
        assert dpg.does_item_exist(tab._t("action_selector"))
        assert dpg.does_item_exist(tab._t("add_context_hint"))
        assert dpg.is_item_shown(tab._t("basic_mode_panel"))
        assert not dpg.is_item_shown(tab._t("advanced_mode_panel"))
        assert dpg.is_item_shown(tab._t("game_info_tab"))
        assert dpg.is_item_shown(tab._t("lineup_tab"))
        assert dpg.is_item_shown(tab._t("record_tab"))
        assert dpg.get_item_configuration(tab._t("file_panel"))["height"] < dpg.get_item_configuration(tab._t("findings_panel"))["height"]
        assert dpg.get_item_configuration(tab._t("relay_events"))["horizontal_scrollbar"] is True
        assert dpg.get_item_configuration(tab._t("findings_table"))["horizontal_scrollbar"] is True
        assert dpg.get_item_configuration(tab._t("action_selector"))["items"] == [
            ACTION_LABELS["add"],
            ACTION_LABELS["meaning"],
            ACTION_LABELS["split_merge"],
            ACTION_LABELS["preview"],
        ]
        assert not dpg.does_item_exist(tab._t("section_missing_pa"))

        relay_labels = collect_item_labels(tab._t("relay_tab"))
        for label in ():
            assert label not in relay_labels

        tab._set_tab_value(tab._t("detail_tabs"), tab._t("lineup_tab"))
        selected_before = dpg.get_value(tab._t("detail_tabs"))
        tab.apply_editor_mode()
        assert dpg.get_value(tab._t("detail_tabs")) == selected_before
    finally:
        dpg.destroy_context()


def test_editor_tab_root_dir_dialog_selection_refreshes_file_list(tmp_path: Path):
    dpg.create_context()
    try:
        target_dir = tmp_path / "season"
        target_dir.mkdir()
        json_path = target_dir / "20260406ROOT.json"
        json_path.write_text(json.dumps(make_smoke_payload(), ensure_ascii=False, indent=2), encoding="utf-8")

        tab = build_unloaded_tab(tmp_path)
        tab.on_root_dir_dialog_selected(None, {"file_path_name": str(target_dir)})

        assert dpg.get_value(tab._t("root_dir")) == str(target_dir)
        assert dpg.get_item_configuration(tab._t("file_list"))["items"] == [json_path.name]
        assert tab.state.default_data_dir == str(target_dir)
    finally:
        dpg.destroy_context()


def test_editor_tab_file_list_double_click_loads_selected_file(tmp_path: Path):
    dpg.create_context()
    try:
        json_path = tmp_path / "20260406DOUBLE.json"
        json_path.write_text(json.dumps(make_loaded_state_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        tab = build_unloaded_tab(tmp_path)

        tab.refresh_file_list()
        dpg.set_value(tab._t("file_list"), json_path.name)
        tab.on_file_list_double_click()

        assert tab.session is not None
        assert tab.session.path == json_path
        assert dpg.get_value(tab._t("loaded_file")) == json_path.as_posix()
    finally:
        dpg.destroy_context()


def test_editor_tab_findings_table_uses_fixed_description_width(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_loaded_state_payload(), filename="20260406FINDINGS.json")

        table_config = dpg.get_item_configuration(tab._t("findings_table_inner"))
        columns = dpg.get_item_children(tab._t("findings_table_inner"), 0)
        description_column = columns[4]
        config = dpg.get_item_configuration(description_column)

        assert table_config["scrollX"] is True
        assert table_config["inner_width"] == FINDING_TABLE_INNER_WIDTH
        assert config["width_fixed"] is True
        assert config["init_width_or_weight"] == 720
    finally:
        dpg.destroy_context()


def test_editor_tab_findings_selection_preserves_scroll_and_all_cells_are_clickable(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_loaded_state_payload(), filename="20260406FINDINGSCROLL.json")
        tab.validation_result = {
            "ok": False,
            "error_count": 60,
            "warning_count": 0,
            "findings": [
                {
                    "severity": "error",
                    "code": "validate_game",
                    "message": f"validation issue message {index} " * 8,
                    "location": {"tab": "relay", "group_index": 0, "block_index": 0, "event_index": 0},
                }
                for index in range(60)
            ],
        }
        tab.refresh_finding_table()

        dpg.set_x_scroll(tab._t("findings_table"), 120)
        dpg.set_y_scroll(tab._t("findings_table"), 180)
        dpg.set_x_scroll(tab._t("findings_table_inner"), 90)
        dpg.set_y_scroll(tab._t("findings_table_inner"), 150)
        before_x = dpg.get_x_scroll(tab._t("findings_table"))
        before_y = dpg.get_y_scroll(tab._t("findings_table"))
        before_inner_x = dpg.get_x_scroll(tab._t("findings_table_inner"))
        before_inner_y = dpg.get_y_scroll(tab._t("findings_table_inner"))

        rows = dpg.get_item_children(tab._t("findings_table_inner"), 1)
        first_row_children = dpg.get_item_children(rows[0], 1)
        assert len(first_row_children) == 9
        assert dpg.does_item_exist(tab._t("finding_cell_handler_severity_0"))
        assert dpg.does_item_exist(tab._t("finding_cell_handler_code_0"))
        assert dpg.does_item_exist(tab._t("finding_cell_handler_location_0"))
        assert dpg.does_item_exist(tab._t("finding_cell_handler_message_0"))

        tab.select_finding(40)

        after_x = dpg.get_x_scroll(tab._t("findings_table"))
        after_y = dpg.get_y_scroll(tab._t("findings_table"))
        after_inner_x = dpg.get_x_scroll(tab._t("findings_table_inner"))
        after_inner_y = dpg.get_y_scroll(tab._t("findings_table_inner"))
        assert after_x == before_x
        assert after_y == before_y
        assert after_inner_x == before_inner_x
        assert after_inner_y == before_inner_y
        assert tab.selected_event_ref == (0, 0, 0)
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
        detail_text = dpg.get_value(tab._t("finding_detail_text"))
        assert "missing_pitcher" in detail_text
        assert "missing currentGameState.pitcher" in detail_text
        assert dpg.get_value(tab._t("validation_hint_text")) == detail_text
    finally:
        dpg.destroy_context()


def test_build_offense_entry_options_orders_starters_then_candidates():
    options = build_offense_entry_options(make_basic_split_payload(), group_index=0, block_index=0)

    assert [option["player_id"] for option in options] == ["A1", "A2", "A3"]
    assert options[0]["label"]
    assert options[1]["label"]
    assert options[2]["label"]


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
        dpg.set_value(tab._t("split_basic_batter"), "4踰??묒쓽吏 (A2)")
        tab.preview_split_from_selected_event()

        preview_text = dpg.get_value(tab._t("split_basic_preview_text"))
        assert "?댁쟾 醫낅즺 ?대깽?? ?덉쓬" in preview_text
        assert preview_text
        assert "??釉붾줉 ?쒕ぉ: 4踰덊????묒쓽吏" in preview_text
        assert preview_text

        tab.split_selected_plate_appearance_basic()

        relay_group = tab.session.payload["relay"][0]
        assert len(relay_group) == 2
        assert relay_group[1]["title"] == "4踰덊????묒쓽吏"
        assert relay_group[0]["textOptions"][-1]["text"] == "以묎퀎 ?뺣━"
        events = relay_group[1]["textOptions"]
        assert events[0]["text"] == "4踰덊????묒쓽吏"
        assert events[1]["batterRecord"]["pcode"] == "A2"
        assert events[1]["currentGameState"]["batter"] == "A2"
        assert events[1]["text"]
        assert events[2]["text"] == "?뚯슱"
        assert events[3]["text"].startswith("?묒쓽吏 :")
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
        dpg.set_value(tab._t("split_basic_batter"), "4踰??묒쓽吏 (A2)")
        tab.preview_split_from_selected_event()

        assert "湲곕낯 紐⑤뱶?먯꽌" in dpg.get_value(tab._t("split_basic_status_text"))
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
        assert away_items
        assert all("Home Batter" not in item for item in away_items)

        tab.select_event((0, 1, 0))

        home_items = dpg.get_item_configuration(tab._t("split_basic_batter"))["items"]
        assert any("Home Batter" in item for item in home_items)
        assert home_items
    finally:
        dpg.destroy_context()


def test_editor_tab_split_repairs_inferred_start_when_selected_segment_already_has_new_batter(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_same_batter_split_payload(), filename="20260406SPLITKEEP.json")

        tab.select_event((0, 0, 3))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["split_merge"])
        tab.refresh_action_sections()
        dpg.set_value(tab._t("split_basic_batter"), "4踰??묒쓽吏 (A2)")
        tab.refresh_basic_split_card(preview=True)

        assert dpg.get_value(tab._t("split_basic_batter")) == "4踰??묒쓽吏 (A2)"
        assert "??由대젅??釉붾줉?쇰줈 遺꾨━?????덉뒿?덈떎" in dpg.get_value(tab._t("split_basic_status_text"))
        assert dpg.get_value(tab._t("split_basic_preview_text"))
        assert dpg.get_value(tab._t("split_basic_preview_text"))

        tab.split_selected_plate_appearance_basic()

        relay_group = tab.session.payload["relay"][0]
        assert len(relay_group) == 2
        assert relay_group[1]["title"] == "4踰덊????묒쓽吏"
        events = relay_group[1]["textOptions"]
        assert events[0]["text"] == "4踰덊????묒쓽吏"
        assert events[1]["currentGameState"]["batter"] == "A2"
        assert events[1]["text"]
    finally:
        dpg.destroy_context()


def test_editor_tab_split_moves_existing_intro_into_new_block_without_duplication(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_explicit_intro_split_payload(), filename="20260406SPLITINTRO.json")

        tab.select_event((0, 0, 3))
        dpg.set_value(tab._t("action_selector"), ACTION_LABELS["split_merge"])
        tab.refresh_action_sections()
        dpg.set_value(tab._t("split_basic_batter"), "4踰??묒쓽吏 (A2)")
        tab.preview_split_from_selected_event()

        preview_text = dpg.get_value(tab._t("split_basic_preview_text"))
        assert preview_text
        assert preview_text

        tab.split_selected_plate_appearance_basic()

        relay_group = tab.session.payload["relay"][0]
        assert len(relay_group) == 2
        assert relay_group[1]["title"] == "4踰덊????묒쓽吏"
        events = relay_group[1]["textOptions"]
        assert events[0]["text"] == "4踰덊????묒쓽吏"
        assert len([event for event in events if event["text"] == "4踰덊????묒쓽吏"]) == 1
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
        assert inserted["text"]
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
        assert dpg.get_value(tab._t("add_pitch_num")) == ""
        dpg.set_value(tab._t("add_result_type"), RESULT_TYPE_LABELS["single"])
        dpg.set_value(tab._t("add_text"), "single to left")
        tab.insert_structured_event()

        events = tab.session.payload["relay"][0][0]["textOptions"]
        inserted = events[2]

        assert len(events) == 3
        assert inserted["type"] == 13
        assert "single to left" in inserted["text"]
        assert inserted["batterRecord"]["pcode"] == "A1"
        assert "pitchNum" not in inserted
        assert "pitchResult" not in inserted
        assert "ptsPitchId" not in inserted
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
        dpg.set_value(tab._t("split_basic_batter"), "4踰??묒쓽吏 (A2)")
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
        dpg.set_value(tab._t("split_basic_batter"), "4踰??묒쓽吏 (A2)")
        tab.split_selected_plate_appearance_basic()

        assert len(tab.session.payload["relay"][0]) == 2
        assert tab.selected_event_ref == (0, 1, 0)

        tab.merge_selected_plate_appearance()

        assert len(tab.session.payload["relay"][0]) == 1
        assert tab.selected_event_ref is not None
        assert tab.selected_event_ref[:2] == (0, 0)
    finally:
        dpg.destroy_context()


def test_editor_tab_record_sync_clears_validation_mismatch(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_record_sync_validation_payload(), filename="20260410RECORDSYNC.json")

        tab.run_validation()
        before_messages = [finding["message"] for finding in tab.validation_result["findings"] if finding["code"] == "validate_game"]
        assert before_messages

        tab.sync_record_with_relay()

        after_messages = [finding["message"] for finding in tab.validation_result["findings"] if finding["code"] == "validate_game"]
        assert tab.validation_result["ok"] is True
        assert not after_messages
        assert tab.session.payload["record"]["pitcher"]["home"][0]["pa"] == 1
    finally:
        dpg.destroy_context()


def test_editor_tab_mode_switch_and_context_summary(tmp_path: Path):
    dpg.create_context()
    try:
        tab, _json_path = build_loaded_tab(tmp_path, make_loaded_state_payload(), filename="20260406MODE.json")

        summary = dpg.get_value(tab._t("context_summary_text"))
        assert "????ъ닔: Kim vs Home Pitcher" in summary
        assert "?꾩옱 ??? ?대깽??0-0 | 寃곌낵 Kim : single" in summary

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


