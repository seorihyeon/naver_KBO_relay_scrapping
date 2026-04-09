from __future__ import annotations

from pathlib import Path
from typing import Any

import dearpygui.dearpygui as dpg

from gui.dpg_utils import prompt_native_text
from gui.components import HorizontalToolbar
from gui.state import AppState
from src.kbo_ingest.correction_engine import (
    RESULT_TYPES,
    RUNNER_BASE_CHOICES,
    build_player_index,
    parse_result_type,
    summarize_plate_appearances,
)
from src.kbo_ingest.editor_core import GameEditorSession
from src.kbo_ingest.game_json import CURRENT_GAME_STATE_FIELDS


GAME_INFO_FIELDS = [
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
]

LINEUP_FIELDS = [
    "playerCode",
    "playerName",
    "position",
    "positionName",
    "batorder",
    "backnum",
    "pos",
    "hitType",
    "batsThrows",
    "height",
    "weight",
]

RECORD_BATTER_FIELDS = ["playerCode", "name", "batOrder", "ab", "hit", "bb", "kk", "hr", "rbi", "run", "sb"]
RECORD_BATTER_TOTAL_FIELDS = ["ab", "hit", "bb", "kk", "hr", "rbi", "run", "sb"]
RECORD_PITCHER_FIELDS = ["pcode", "name", "inn", "r", "er", "hit", "bb", "kk", "hr", "ab", "bf", "pa", "bbhp"]
EVENT_FIELDS = ["seqno", "type", "text", "pitchNum", "pitchResult", "ptsPitchId", "speed", "stuff"]
BLOCK_FIELDS = ["title", "titleStyle", "no", "inn", "homeOrAway", "statusCode"]
PLAYER_CHANGE_PLAYER_FIELDS = ["playerId", "playerCode", "playerName", "playerPos", "position"]
OPTIONAL_EVENT_FIELDS = {"pitchNum", "pitchResult", "ptsPitchId", "speed", "stuff"}
INTEGER_EVENT_FIELDS = {"seqno", "type", "pitchNum", "speed"}
INTEGER_BLOCK_FIELDS = {"no", "inn"}
INTEGER_GAME_INFO_FIELDS = {"round"}
BOOLEAN_GAME_INFO_FIELDS = {"isPostSeason", "cancelFlag"}
INTEGER_RECORD_BATTER_FIELDS = {"batOrder", "ab", "hit", "bb", "kk", "hr", "rbi", "run", "sb"}
INTEGER_STATE_FIELDS = {
    "homeScore",
    "awayScore",
    "homeHit",
    "awayHit",
    "homeBallFour",
    "awayBallFour",
    "homeError",
    "awayError",
    "strike",
    "ball",
    "out",
}
BASE_STATE_FIELDS = {"base1", "base2", "base3"}
EDITOR_MODES = ["기본 모드", "고급 모드"]
ACTION_TABS = {
    "add": "action_add_tab",
    "missing_pa": "action_missing_pa_tab",
    "meaning": "action_meaning_tab",
    "split_merge": "action_split_merge_tab",
    "preview": "action_preview_tab",
}
ACTION_LABELS = {
    "add": "이벤트 추가",
    "missing_pa": "누락 타석 복구",
    "meaning": "결과 의미 수정",
    "split_merge": "타석 분리 / 병합",
    "preview": "자동 재계산 미리보기",
}
ADD_TEMPLATE_LABELS = {
    "pitch": "투구",
    "bat_result": "타격 결과",
    "baserunning": "주루",
    "substitution": "선수 교체",
    "review": "비디오 판독",
    "other": "기타 raw 이벤트",
}
ADD_TEMPLATE_LABELS_REVERSE = {label: key for key, label in ADD_TEMPLATE_LABELS.items()}
BASIC_ADD_TEMPLATE_TYPES = ["pitch", "bat_result", "baserunning", "substitution"]
INSERT_MODE_LABELS = {
    "before": "선택 이벤트 앞",
    "after": "선택 이벤트 뒤",
}
INSERT_MODE_LABELS_REVERSE = {label: key for key, label in INSERT_MODE_LABELS.items()}
PITCH_RESULT_LABELS = {
    "": "선택 안 함",
    "B": "볼",
    "S": "스트라이크",
    "F": "파울",
    "SW": "헛스윙 스트라이크",
    "X": "타격",
    "K": "삼진",
}
PITCH_RESULT_LABELS_REVERSE = {label: key for key, label in PITCH_RESULT_LABELS.items()}
RESULT_TYPE_LABELS = {
    "out": "아웃",
    "single": "안타",
    "double": "2루타",
    "triple": "3루타",
    "home_run": "홈런",
    "walk": "볼넷",
    "intentional_walk": "고의4구",
    "hit_by_pitch": "몸에 맞는 볼",
    "error": "실책 출루",
    "fielders_choice": "야수선택",
    "sacrifice_bunt": "희생번트",
    "sacrifice_fly": "희생플라이",
    "strikeout": "삼진",
    "dropped_third": "낫아웃",
    "double_play": "병살",
    "other": "기타",
}
RESULT_TYPE_LABELS_REVERSE = {label: key for key, label in RESULT_TYPE_LABELS.items()}
FINDING_TYPE_GROUPS = {
    "전체": None,
    "누락/점프": ("missing_", "state_jump", "seq_gap"),
    "중복": ("duplicate_",),
    "재계산 차이": ("auto_rebuild_drift",),
    "검증 이슈": ("validate_game", "validate_game_warning"),
}
LINEUP_SECTIONS = ["home_starter", "home_bullpen", "home_candidate", "away_starter", "away_bullpen", "away_candidate"]
RECORD_SCOPE_ITEMS = ["batter:home", "batter:away", "pitcher:home", "pitcher:away"]
LINEUP_SECTION_LABELS = {
    "home_starter": "홈 선발",
    "home_bullpen": "홈 불펜",
    "home_candidate": "홈 교체 후보",
    "away_starter": "원정 선발",
    "away_bullpen": "원정 불펜",
    "away_candidate": "원정 교체 후보",
}
LINEUP_SECTION_LABELS_REVERSE = {label: key for key, label in LINEUP_SECTION_LABELS.items()}
RECORD_SCOPE_LABELS = {
    "batter:home": "타자(홈)",
    "batter:away": "타자(원정)",
    "pitcher:home": "투수(홈)",
    "pitcher:away": "투수(원정)",
}
RECORD_SCOPE_LABELS_REVERSE = {label: key for key, label in RECORD_SCOPE_LABELS.items()}
SIDE_LABELS = {"home": "홈", "away": "원정"}
SIDE_LABELS_REVERSE = {label: key for key, label in SIDE_LABELS.items()}
RELAY_VIEW_MODE_LABELS = {"Event": "이벤트", "PA": "타석"}
RELAY_VIEW_MODE_LABELS_REVERSE = {label: key for key, label in RELAY_VIEW_MODE_LABELS.items()}
RELAY_HALF_FILTER_LABELS = {"All": "전체", "Top": "초", "Bottom": "말"}
RELAY_HALF_FILTER_LABELS_REVERSE = {label: key for key, label in RELAY_HALF_FILTER_LABELS.items()}
RELAY_ALL_FILTER_LABEL = "전체"


class CorrectionEditorTab:
    key = "editor"
    label = "수정/보정"

    def __init__(self, state: AppState):
        self.state = state
        self.session: GameEditorSession | None = None
        self.validation_result: dict[str, Any] | None = None
        self.file_map: dict[str, Path] = {}
        self.selected_lineup_section = "home_starter"
        self.selected_lineup_row: int | None = None
        self.selected_record_table = "batter"
        self.selected_record_side = "home"
        self.selected_record_row: int | None = None
        self.selected_block_ref: tuple[int, int] | None = None
        self.selected_event_ref: tuple[int, int, int] | None = None
        self.selected_finding_index: int | None = None
        self.selected_game_info_key: str | None = None
        self.auto_preview: dict[str, Any] | None = None
        self.split_preview: dict[str, Any] | None = None
        self._split_entry_options: list[dict[str, Any]] = []
        self._last_validation_signatures: set[str] = set()
        self.header_toolbar = HorizontalToolbar(self._t("header_toolbar"))
        self.loaded_toolbar = HorizontalToolbar(self._t("loaded_toolbar"))
        self.status_toolbar = HorizontalToolbar(self._t("status_toolbar"))

    def _t(self, name: str) -> str:
        return f"editor_{name}"

    def _session_required(self) -> GameEditorSession | None:
        if self.session is None:
            self.state.set_status("warn", "편집 파일 없음", "먼저 JSON 파일을 선택해서 열어 주세요.", source="수정/보정")
            return None
        return self.session

    def _set_value_if_exists(self, tag: str, value: Any) -> None:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, value)

    def _toggle_group(self, tag: str, show: bool) -> None:
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=show)

    def _clear_children(self, tag: str) -> None:
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag, children_only=True)

    def _set_tab_value(self, tag: str, value: str) -> None:
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, value)

    def _half_label(self, home_or_away: Any) -> str:
        return "초" if str(home_or_away) == "0" else "말"

    def _block_label(self, block: dict[str, Any] | None) -> str:
        if not block:
            return "-"
        return f"{block.get('inn', '?')}회{self._half_label(block.get('homeOrAway'))}"

    def _selected_mode(self) -> str:
        if dpg.does_item_exist(self._t("editor_mode")):
            return str(dpg.get_value(self._t("editor_mode")) or EDITOR_MODES[0])
        return EDITOR_MODES[0]

    def _lineup_section_label(self, section: str) -> str:
        return LINEUP_SECTION_LABELS.get(section, section)

    def _record_scope_label(self, table: str, side: str) -> str:
        return RECORD_SCOPE_LABELS.get(f"{table}:{side}", f"{table}:{side}")

    def _action_tab_tag(self, action_key: str) -> str:
        return self._t(ACTION_TABS[action_key])

    def _set_active_action(self, action_key: str) -> None:
        if dpg.does_item_exist(self._t("action_selector")):
            dpg.set_value(self._t("action_selector"), ACTION_LABELS[action_key])
        tab_tag = ACTION_TABS.get(action_key)
        if tab_tag:
            self._set_tab_value(self._t("action_tabs"), self._t(tab_tag))
        self.refresh_action_sections()

    def _current_action_key(self) -> str:
        if dpg.does_item_exist(self._t("action_selector")):
            selected_label = str(dpg.get_value(self._t("action_selector")) or "")
            for action_key, label in ACTION_LABELS.items():
                if selected_label == label:
                    return action_key
        if not dpg.does_item_exist(self._t("action_tabs")):
            return "meaning"
        current = str(dpg.get_value(self._t("action_tabs")) or "")
        for action_key, tab_name in ACTION_TABS.items():
            if current == self._t(tab_name):
                return action_key
        return "meaning"

    def refresh_action_sections(self) -> None:
        active = self._current_action_key()
        section_map = {
            "add": self._t("section_structured_add"),
            "missing_pa": self._t("section_missing_pa"),
            "meaning": self._t("section_meaning_edit"),
            "split_merge": self._t("section_pa_split_merge"),
        }
        for action_key, tag in section_map.items():
            self._toggle_group(tag, action_key == active)
        self._toggle_group(self._t("basic_preview_panel"), active == "preview")

    def _recommended_action(self, finding: dict[str, Any] | None = None) -> str:
        code = str((finding or {}).get("code") or "")
        if code.startswith("missing_") or code.startswith("state_jump"):
            return "meaning"
        if code.startswith("duplicate_") or code == "seq_gap" or code == "auto_rebuild_drift":
            return "preview"
        if code.startswith("validate_game"):
            location = (finding or {}).get("location") or {}
            if location.get("tab") == "relay":
                return "meaning"
            return "preview"
        pa_summary = self._selected_pa_summary()
        if pa_summary and not pa_summary.is_terminal:
            return "missing_pa"
        event = self._get_selected_event() or {}
        if parse_result_type(str(event.get("text") or "")):
            return "meaning"
        if self.selected_event_ref is not None:
            return "add"
        return "preview"

    def _finding_signature(self, finding: dict[str, Any]) -> str:
        return f"{finding.get('severity')}|{finding.get('code')}|{finding.get('message')}"

    def _relative_label(self, path: Path, root: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()

    def _scan_game_files(self) -> list[Path]:
        root = Path(dpg.get_value(self._t("root_dir"))).expanduser()
        if not root.exists():
            return []
        return sorted(
            path
            for path in root.rglob("*.json")
            if ".history" not in path.parts
        )

    def refresh_file_list(self) -> None:
        root = Path(dpg.get_value(self._t("root_dir"))).expanduser()
        query = str(dpg.get_value(self._t("search")) or "").strip().lower()
        files = self._scan_game_files()
        self.file_map.clear()
        labels: list[str] = []
        for path in files:
            label = self._relative_label(path, root)
            if query and query not in label.lower():
                continue
            labels.append(label)
            self.file_map[label] = path
        if dpg.does_item_exist(self._t("file_list")):
            dpg.configure_item(self._t("file_list"), items=labels)
            if labels:
                current = dpg.get_value(self._t("file_list"))
                dpg.set_value(self._t("file_list"), current if current in labels else labels[0])
        self._set_value_if_exists(self._t("file_count"), f"{len(labels)}개 파일")

    def load_selected_file(self) -> None:
        label = dpg.get_value(self._t("file_list"))
        path = self.file_map.get(label)
        if path is None:
            self.state.set_status("warn", "파일 선택 필요", "좌측 목록에서 JSON 파일을 선택해 주세요.", source="수정/보정")
            return
        try:
            self.session = GameEditorSession.load(path)
            self.validation_result = None
            self.auto_preview = None
            self.selected_lineup_section = "home_starter"
            self.selected_lineup_row = 0 if self.session.get_lineup_rows(self.selected_lineup_section) else None
            self.selected_record_table = "batter"
            self.selected_record_side = "home"
            self.selected_record_row = 0 if self.session.get_record_rows(self.selected_record_table, self.selected_record_side) else None
            self._set_value_if_exists(self._t("lineup_section"), self._lineup_section_label(self.selected_lineup_section))
            self._set_value_if_exists(self._t("record_scope"), self._record_scope_label(self.selected_record_table, self.selected_record_side))
            self._set_value_if_exists(self._t("record_total_side"), SIDE_LABELS["home"])
            self.selected_block_ref = None
            self.selected_event_ref = None
            self.selected_game_info_key = GAME_INFO_FIELDS[0]
            for group_index, block_index, _block in self._iter_blocks():
                self.selected_block_ref = (group_index, block_index)
                break
            if self.selected_block_ref:
                block = self._get_selected_block()
                if block and (block.get("textOptions") or []):
                    self.selected_event_ref = (*self.selected_block_ref, 0)
            self.refresh_all_views()
            self.state.set_status("info", "파일 로드 완료", f"{path.as_posix()} 를 편집 세션에 열었습니다.", source="수정/보정")
        except Exception as exc:
            self.state.set_status("error", "파일 로드 실패", "JSON 파일을 여는 중 오류가 발생했습니다.", debug_detail=str(exc), source="수정/보정")

    def _iter_blocks(self):
        if not self.session:
            return []
        return [
            (group_index, block_index, block)
            for group_index, inning_group in enumerate((self.session.payload.get("relay") or []))
            for block_index, block in enumerate(inning_group or [])
        ]

    def _get_selected_block(self) -> dict[str, Any] | None:
        if not self.session or self.selected_block_ref is None:
            return None
        group_index, block_index = self.selected_block_ref
        relay = self.session.payload.get("relay") or []
        if 0 <= group_index < len(relay) and 0 <= block_index < len(relay[group_index]):
            return relay[group_index][block_index]
        return None

    def _get_selected_event(self) -> dict[str, Any] | None:
        if not self.session or self.selected_event_ref is None:
            return None
        group_index, block_index, event_index = self.selected_event_ref
        relay = self.session.payload.get("relay") or []
        if not (0 <= group_index < len(relay) and 0 <= block_index < len(relay[group_index])):
            return None
        events = relay[group_index][block_index].get("textOptions") or []
        if 0 <= event_index < len(events):
            return events[event_index]
        return None

    def _get_lineup_rows(self) -> list[dict[str, Any]]:
        return self.session.get_lineup_rows(self.selected_lineup_section) if self.session else []

    def _get_record_rows(self) -> list[dict[str, Any]]:
        return self.session.get_record_rows(self.selected_record_table, self.selected_record_side) if self.session else []

    def _input_text_value(self, tag: str) -> str | None:
        value = str(dpg.get_value(tag) or "").strip()
        return value or None

    def _input_int_value(self, tag: str) -> int | None:
        value = self._input_text_value(tag)
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _input_runner_moves(self, prefix: str) -> list[dict[str, Any]]:
        moves: list[dict[str, Any]] = []
        for index in range(1, 4):
            start = str(dpg.get_value(self._t(f"{prefix}_runner_{index}_start")) or "").strip().upper()
            end = str(dpg.get_value(self._t(f"{prefix}_runner_{index}_end")) or "").strip().upper()
            if start not in {"B", "1", "2", "3"} or end not in {"1", "2", "3", "H", "OUT"}:
                continue
            moves.append(
                {
                    "start": start,
                    "end": end,
                    "runner_id": self._input_text_value(self._t(f"{prefix}_runner_{index}_id")),
                    "runner_name": self._input_text_value(self._t(f"{prefix}_runner_{index}_name")),
                }
            )
        return moves

    def _set_or_delete(self, mapping: dict[str, Any], key: str, value: Any) -> None:
        if value in (None, "", {}):
            mapping.pop(key, None)
        else:
            mapping[key] = value

    def _open_native_text_dialog(self, tag: str, label: str, multiline: bool = False) -> None:
        current_value = str(dpg.get_value(tag) or "")
        updated = prompt_native_text(title=f"{label} 입력", initial_value=current_value, multiline=multiline)
        if updated is not None:
            self._set_value_if_exists(tag, updated)

    def _add_labeled_input_text(self, tag: str, label: str, *, multiline: bool = False, height: int = 0) -> None:
        dpg.add_text(label)
        show_helper = multiline or any(token in label.lower() for token in ("name", "detail", "text", "memo", "note")) or any(
            token in label for token in ("이름", "설명", "텍스트", "문구", "메모")
        )
        if show_helper:
            with dpg.group(horizontal=True):
                kwargs: dict[str, Any] = {"tag": tag, "label": "", "width": -70}
                if multiline:
                    kwargs["multiline"] = True
                    kwargs["height"] = height or 90
                dpg.add_input_text(**kwargs)
                dpg.add_button(
                    label="입력",
                    width=56,
                    callback=lambda _s, _a, user_data: self._open_native_text_dialog(*user_data),
                    user_data=(tag, label, multiline),
                )
        else:
            kwargs = {"tag": tag, "label": "", "width": -1}
            if multiline:
                kwargs["multiline"] = True
                kwargs["height"] = height or 90
            dpg.add_input_text(**kwargs)

    def _add_labeled_combo(self, tag: str, label: str, *, items: list[str], default_value: str, width: int = -1, callback: Any = None) -> None:
        dpg.add_text(label)
        kwargs: dict[str, Any] = {"tag": tag, "label": "", "items": items, "default_value": default_value, "width": width}
        if callback is not None:
            kwargs["callback"] = callback
        dpg.add_combo(**kwargs)

    def _add_labeled_checkbox(self, tag: str, label: str, *, default_value: bool = False, callback: Any = None) -> None:
        dpg.add_text(label)
        kwargs: dict[str, Any] = {"tag": tag, "label": "", "default_value": default_value}
        if callback is not None:
            kwargs["callback"] = callback
        dpg.add_checkbox(**kwargs)

    def _add_runner_move_editor(self, prefix: str, *, count: int = 3, title_prefix: str = "주자") -> None:
        for index in range(1, count + 1):
            dpg.add_separator()
            dpg.add_text(f"{title_prefix} {index}")
            self._add_labeled_combo(self._t(f"{prefix}_runner_{index}_start"), "출발 위치", items=RUNNER_BASE_CHOICES, default_value="")
            self._add_labeled_combo(self._t(f"{prefix}_runner_{index}_end"), "도착 위치", items=RUNNER_BASE_CHOICES, default_value="")
            self._add_labeled_input_text(self._t(f"{prefix}_runner_{index}_id"), "주자 id (선택)")
            self._add_labeled_input_text(self._t(f"{prefix}_runner_{index}_name"), "주자 이름 (선택)")

    def _add_pa_pitch_editor(self, prefix: str, *, count: int = 5) -> None:
        for index in range(1, count + 1):
            dpg.add_separator()
            dpg.add_text(f"투구 {index}")
            self._add_labeled_input_text(self._t(f"{prefix}_pitch_{index}_result"), "투구 결과")
            self._add_labeled_input_text(self._t(f"{prefix}_pitch_{index}_num"), "투구 번호")
            self._add_labeled_input_text(self._t(f"{prefix}_pitch_{index}_id"), "원본 pitch id")
            self._add_labeled_input_text(self._t(f"{prefix}_pitch_{index}_text"), "문구")

    def _mapped_choice_value(self, raw_value: Any, *, reverse_map: dict[str, str], default: str) -> str:
        value = str(raw_value or "").strip()
        if value in reverse_map.values():
            return value
        return reverse_map.get(value, default)

    def _set_mapped_choice(self, tag: str, value: str | None, *, label_map: dict[str, str], default: str) -> None:
        normalized = str(value or "").strip()
        display = label_map.get(normalized, label_map[default])
        self._set_value_if_exists(tag, display)

    def _event_batter_id(self, event: dict[str, Any] | None) -> str | None:
        if not event:
            return None
        state = event.get("currentGameState") or {}
        batter_id = str(state.get("batter") or (event.get("batterRecord") or {}).get("pcode") or "").strip()
        return batter_id or None

    def _event_pitcher_id(self, event: dict[str, Any] | None) -> str | None:
        if not event:
            return None
        state = event.get("currentGameState") or {}
        pitcher_id = str(state.get("pitcher") or "").strip()
        return pitcher_id or None

    def _coerce_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _player_name_lookup(self, player_id: str | None) -> str:
        if not self.session or not player_id:
            return ""
        info = build_player_index(self.session.payload).get(str(player_id))
        return str(info.name or "") if info else ""

    def _selected_offense_side(self) -> str:
        block = self._get_selected_block() or {}
        return "away" if str(block.get("homeOrAway", "0")) == "0" else "home"

    def _ordered_batter_ids(self, side: str) -> list[str]:
        if not self.session:
            return []
        lineup = self.session.payload.get("lineup") or {}
        order_rows: list[tuple[int, str]] = []
        seen: set[str] = set()
        for section in (f"{side}_starter", f"{side}_candidate"):
            for row in lineup.get(section) or []:
                player_id = str(row.get("playerCode") or "").strip()
                if not player_id or player_id in seen:
                    continue
                batorder = row.get("batorder")
                if batorder in (None, ""):
                    continue
                try:
                    order_value = int(batorder)
                except (TypeError, ValueError):
                    continue
                seen.add(player_id)
                order_rows.append((order_value, player_id))
        return [player_id for _order, player_id in sorted(order_rows)]

    def _adjacent_batter(self, current_batter_id: str | None, *, side: str, offset: int) -> tuple[str | None, str | None]:
        ordered = self._ordered_batter_ids(side)
        if not ordered:
            return None, None
        if current_batter_id in ordered:
            index = ordered.index(current_batter_id)
            target_index = (index + offset) % len(ordered)
        else:
            target_index = 0 if offset >= 0 else len(ordered) - 1
        player_id = ordered[target_index]
        return player_id, self._player_name_lookup(player_id) or None

    def _selected_pa_summary(self):
        if not self.session or self.selected_event_ref is None:
            return None
        group_index, block_index, event_index = self.selected_event_ref
        for pa in summarize_plate_appearances(self.session.payload, group_index=group_index, block_index=block_index):
            if pa.start_index <= event_index <= pa.end_index:
                return pa
        return None

    def _selected_insert_mode(self, prefix: str) -> str:
        tag = self._t(f"{prefix}_insert_mode")
        if not dpg.does_item_exist(tag):
            return "after"
        raw_value = dpg.get_value(tag)
        return self._mapped_choice_value(raw_value, reverse_map=INSERT_MODE_LABELS_REVERSE, default="after")

    def _selected_add_template_type(self) -> str:
        tag = self._t("add_template_type")
        if not dpg.does_item_exist(tag):
            return "pitch"
        raw_value = dpg.get_value(tag)
        return self._mapped_choice_value(raw_value, reverse_map=ADD_TEMPLATE_LABELS_REVERSE, default="pitch")

    def _selected_pitch_result(self) -> str | None:
        tag = self._t("add_pitch_result_display")
        if not dpg.does_item_exist(tag):
            return None
        pitch_result = self._mapped_choice_value(dpg.get_value(tag), reverse_map=PITCH_RESULT_LABELS_REVERSE, default="")
        return pitch_result or None

    def _selected_result_type(self, prefix: str) -> str | None:
        tag = self._t(f"{prefix}_result_type")
        if not dpg.does_item_exist(tag):
            return None
        result_type = self._mapped_choice_value(dpg.get_value(tag), reverse_map=RESULT_TYPE_LABELS_REVERSE, default="other")
        return result_type or None

    def _selected_split_entry(self) -> dict[str, Any] | None:
        tag = self._t("split_basic_batter")
        if not dpg.does_item_exist(tag):
            return None
        selected_label = str(dpg.get_value(tag) or "").strip()
        for option in self._split_entry_options:
            if option.get("label") == selected_label:
                return option
        return None

    def _recommended_split_entry(self, current_batter_id: str | None) -> dict[str, Any] | None:
        if not self._split_entry_options:
            return None
        event_batter_id = self._event_batter_id(self._get_selected_event())
        if event_batter_id and event_batter_id != current_batter_id:
            for option in self._split_entry_options:
                if option.get("player_id") == event_batter_id:
                    return option
        next_batter_id, _next_name = self._adjacent_batter(current_batter_id, side=self._selected_offense_side(), offset=1)
        if next_batter_id:
            for option in self._split_entry_options:
                if option.get("player_id") == next_batter_id:
                    return option
        for option in self._split_entry_options:
            if option.get("player_id") != current_batter_id:
                return option
        return self._split_entry_options[0]

    def refresh_basic_split_card(self, *, preview: bool = True) -> None:
        self.split_preview = None
        if not dpg.does_item_exist(self._t("split_basic_summary_text")):
            return
        if not self.session or self.selected_event_ref is None or self.selected_block_ref is None:
            self._split_entry_options = []
            if dpg.does_item_exist(self._t("split_basic_batter")):
                dpg.configure_item(self._t("split_basic_batter"), items=[])
                dpg.set_value(self._t("split_basic_batter"), "")
            self._set_value_if_exists(self._t("split_basic_summary_text"), "선택한 이벤트가 없어서 타석 분리 대상을 계산할 수 없습니다.")
            self._set_value_if_exists(self._t("split_basic_status_text"), "중앙 이벤트 목록에서 새 타석이 시작되어야 하는 이벤트를 먼저 선택해 주세요.")
            self._set_value_if_exists(self._t("split_basic_preview_text"), "")
            return

        group_index, block_index, event_index = self.selected_event_ref
        block = self._get_selected_block() or {}
        selected_event = self._get_selected_event() or {}
        current_pa = self._selected_pa_summary()
        current_batter_id = current_pa.batter_id if current_pa else self._event_batter_id(selected_event)
        current_batter_name = current_pa.batter_name if current_pa else self._player_name_lookup(current_batter_id)

        self._split_entry_options = self.session.get_offense_entry_options(group_index=group_index, block_index=block_index)
        split_labels = [str(option.get("label") or "") for option in self._split_entry_options]
        if dpg.does_item_exist(self._t("split_basic_batter")):
            dpg.configure_item(self._t("split_basic_batter"), items=split_labels)
        current_entry = self._selected_split_entry()
        if current_entry is None:
            current_entry = self._recommended_split_entry(current_batter_id)
            self._set_value_if_exists(self._t("split_basic_batter"), str((current_entry or {}).get("label") or ""))
        selected_entry = self._selected_split_entry()

        summary_lines = [
            f"현재 블록: {self._block_label(block)} / 선택 이벤트 [{event_index}] {selected_event.get('text') or '(문구 없음)'}",
            f"현재 추정 타석: {current_batter_name or current_batter_id or '-'}"
            + (f" (이벤트 {current_pa.start_index}-{current_pa.end_index})" if current_pa else " (자동 인식 불가)"),
            f"새 타석 시작 위치: 선택 이벤트부터 새 블록",
        ]
        if selected_entry:
            summary_lines.append(f"새 타자 후보: {selected_entry.get('label')}")
        else:
            summary_lines.append("새 타자 후보: 공격 팀 엔트리에서 선택 필요")
        self._set_value_if_exists(self._t("split_basic_summary_text"), "\n".join(summary_lines))

        if not preview or selected_entry is None:
            self._set_value_if_exists(self._t("split_basic_status_text"), "공격 팀 엔트리에서 새 타자를 선택하면 분리 가능 여부를 확인합니다.")
            self._set_value_if_exists(self._t("split_basic_preview_text"), "")
            return

        preview_result = self.session.preview_split_plate_appearance_from_event(
            group_index=group_index,
            block_index=block_index,
            selected_index=event_index,
            new_batter_id=str(selected_entry.get("player_id") or ""),
            new_batter_name=str(selected_entry.get("name") or "") or None,
            auto_insert_intro=bool(dpg.get_value(self._t("split_basic_auto_intro"))) if dpg.does_item_exist(self._t("split_basic_auto_intro")) else True,
        )
        self.split_preview = preview_result
        self._set_value_if_exists(self._t("split_basic_status_text"), str(preview_result.get("message") or "-"))
        preview_lines = [
            f"새 타자: {selected_entry.get('label')}",
            f"이전 종료 이벤트: {'있음' if preview_result.get('prior_terminal_index') is not None else '없음'}",
            f"새 블록 생성: {'예' if preview_result.get('new_block_created') else '아니오'}",
            f"intro 자동 삽입: {'예' if preview_result.get('intro_inserted') else '아니오'}",
        ]
        if preview_result.get("ok"):
            preview_lines.extend(
                [
                    f"새 블록 제목: {preview_result.get('new_block_title') or '-'}",
                    f"분리 대상 범위: [{event_index}] ~ [{preview_result.get('segment_end')}]",
                    f"예상 변경 이벤트 수: {preview_result.get('changed_event_count', 0)}",
                    f"재계산 변경 예정 이벤트 수: {preview_result.get('rebuild_delta_count', 0)}",
                ]
            )
        else:
            preview_lines.append("안내: 기본 모드에서 분리할 수 없는 경우 고급 모드의 상세 분리를 사용해 주세요.")
        self._set_value_if_exists(self._t("split_basic_preview_text"), "\n".join(preview_lines))

    def _candidate_insert_index(self, insert_mode: str) -> int:
        block = self._get_selected_block() or {}
        events = block.get("textOptions") or []
        if self.selected_event_ref is None:
            return len(events) if insert_mode == "after" else 0
        event_index = self.selected_event_ref[2]
        return event_index if insert_mode == "before" else event_index + 1

    def _build_insert_context(self, *, insert_mode: str) -> dict[str, Any]:
        block = self._get_selected_block() or {}
        event = self._get_selected_event() or {}
        events = block.get("textOptions") or []
        pa_summary = self._selected_pa_summary()
        insert_at = max(0, min(self._candidate_insert_index(insert_mode), len(events)))
        state = event.get("currentGameState") or {}
        batter_id = self._event_batter_id(event)
        pitcher_id = self._event_pitcher_id(event)
        batter_name = self._player_name_lookup(batter_id) or None
        pitcher_name = self._player_name_lookup(pitcher_id) or None
        offense_side = self._selected_offense_side()
        prev_batter_id, prev_batter_name = self._adjacent_batter(batter_id, side=offense_side, offset=-1)
        next_batter_id, next_batter_name = self._adjacent_batter(batter_id, side=offense_side, offset=1)
        selected_index = self.selected_event_ref[2] if self.selected_event_ref is not None else None
        same_plate_appearance = True

        if pa_summary and selected_index is not None:
            if insert_mode == "after" and pa_summary.is_terminal and selected_index >= pa_summary.end_index and next_batter_id:
                batter_id, batter_name = next_batter_id, next_batter_name
                same_plate_appearance = False
            elif insert_mode == "before" and selected_index <= pa_summary.start_index and prev_batter_id:
                batter_id, batter_name = prev_batter_id, prev_batter_name
                same_plate_appearance = False

        prev_seqno: int | None = None
        for index in range(insert_at - 1, -1, -1):
            prev_seqno = self._coerce_int(events[index].get("seqno"))
            if prev_seqno is not None:
                break

        latest_pitch_num: int | None = None
        if same_plate_appearance and pa_summary:
            search_start = pa_summary.start_index
            for index in range(insert_at - 1, search_start - 1, -1):
                latest_pitch_num = self._coerce_int(events[index].get("pitchNum"))
                if latest_pitch_num is not None:
                    break

        pitch_num_candidate = (latest_pitch_num + 1) if latest_pitch_num is not None else 1
        result_pitch_num = latest_pitch_num
        bases = ", ".join(base for base, occupied in (("1루", state.get("base1")), ("2루", state.get("base2")), ("3루", state.get("base3"))) if occupied) or "주자 없음"
        game_info = ((self.session.payload.get("lineup") or {}).get("game_info") or {}) if self.session else {}
        offense_team_name = game_info.get("aName") if offense_side == "away" else game_info.get("hName")
        defense_team_name = game_info.get("hName") if offense_side == "away" else game_info.get("aName")
        offense_team = str(offense_team_name or "").strip() or offense_side
        defense_team = str(defense_team_name or "").strip() or ("home" if offense_side == "away" else "away")

        return {
            "block": block,
            "insert_mode": insert_mode,
            "insert_at": insert_at,
            "inning_label": self._block_label(block),
            "offense_side": offense_side,
            "offense_team": offense_team,
            "defense_team": defense_team,
            "batter_id": batter_id,
            "batter_name": batter_name,
            "pitcher_id": pitcher_id,
            "pitcher_name": pitcher_name,
            "prev_batter_id": prev_batter_id,
            "prev_batter_name": prev_batter_name,
            "next_batter_id": next_batter_id,
            "next_batter_name": next_batter_name,
            "pa_summary": pa_summary,
            "same_plate_appearance": same_plate_appearance,
            "seqno_candidate": 1 if prev_seqno is None else prev_seqno + 1,
            "pitch_num_candidate": pitch_num_candidate,
            "result_pitch_num_candidate": result_pitch_num,
            "ball": state.get("ball", 0),
            "strike": state.get("strike", 0),
            "out": state.get("out", 0),
            "bases": bases,
            "selected_text": str(event.get("text") or "(문구 없음)"),
        }

    def _extract_event_detail(self, text: str, batter_name: str | None = None) -> str:
        detail = str(text or "").strip()
        if " : " in detail:
            detail = detail.split(" : ", 1)[1].strip()
        elif ":" in detail:
            detail = detail.split(":", 1)[1].strip()
        if batter_name and detail.startswith(batter_name):
            detail = detail[len(batter_name):].strip(" :")
        return detail

    def _clear_runner_move_inputs(self, prefix: str, *, count: int = 3) -> None:
        for index in range(1, count + 1):
            self._set_value_if_exists(self._t(f"{prefix}_runner_{index}_start"), "")
            self._set_value_if_exists(self._t(f"{prefix}_runner_{index}_end"), "")
            self._set_value_if_exists(self._t(f"{prefix}_runner_{index}_id"), "")
            self._set_value_if_exists(self._t(f"{prefix}_runner_{index}_name"), "")

    def _clear_pa_pitch_inputs(self, prefix: str, *, count: int = 5) -> None:
        for index in range(1, count + 1):
            self._set_value_if_exists(self._t(f"{prefix}_pitch_{index}_result"), "")
            self._set_value_if_exists(self._t(f"{prefix}_pitch_{index}_num"), "")
            self._set_value_if_exists(self._t(f"{prefix}_pitch_{index}_id"), "")
            self._set_value_if_exists(self._t(f"{prefix}_pitch_{index}_text"), "")

    def _populate_add_action_defaults(
        self,
        *,
        batter_id: str | None,
        batter_name: str | None,
        pitcher_id: str | None,
        pitch_result: str | None,
        result_type: str,
    ) -> None:
        template_type = self._selected_add_template_type()
        if template_type not in ADD_TEMPLATE_LABELS:
            template_type = "pitch"
        if self._selected_mode() == EDITOR_MODES[0] and template_type not in BASIC_ADD_TEMPLATE_TYPES:
            template_type = "pitch"
        insert_mode = self._selected_insert_mode("add")
        context = self._build_insert_context(insert_mode=insert_mode)
        default_pitch_result = pitch_result or ("X" if result_type != "other" else "")

        self._set_mapped_choice(self._t("add_template_type"), template_type, label_map=ADD_TEMPLATE_LABELS, default="pitch")
        self._set_mapped_choice(self._t("add_insert_mode"), insert_mode, label_map=INSERT_MODE_LABELS, default="after")
        self._set_value_if_exists(self._t("add_batter_id"), context["batter_id"] or batter_id or "")
        self._set_value_if_exists(self._t("add_batter_name"), context["batter_name"] or batter_name or "")
        self._set_value_if_exists(self._t("add_pitcher_id"), context["pitcher_id"] or pitcher_id or "")
        self._set_value_if_exists(self._t("add_pitch_num"), "")
        self._set_value_if_exists(self._t("add_pts_pitch_id"), "")
        self._set_value_if_exists(self._t("add_detail"), "")
        self._set_value_if_exists(self._t("add_text"), "")
        self._set_value_if_exists(self._t("add_pitch_result"), default_pitch_result)
        self._set_mapped_choice(self._t("add_pitch_result_display"), default_pitch_result, label_map=PITCH_RESULT_LABELS, default="")
        self._set_mapped_choice(self._t("add_result_type"), result_type or "out", label_map=RESULT_TYPE_LABELS, default="out")
        self._clear_runner_move_inputs("add")
        self.refresh_add_action_form()

    def refresh_add_action_form(self) -> None:
        template_type = self._selected_add_template_type()
        if self._selected_mode() == EDITOR_MODES[0] and template_type not in BASIC_ADD_TEMPLATE_TYPES:
            template_type = "pitch"
            self._set_mapped_choice(self._t("add_template_type"), template_type, label_map=ADD_TEMPLATE_LABELS, default="pitch")
        insert_mode = self._selected_insert_mode("add")
        context = self._build_insert_context(insert_mode=insert_mode)
        pitch_result = self._selected_pitch_result()
        self._set_value_if_exists(self._t("add_pitch_result"), pitch_result or "")
        default_pitch_num = context["pitch_num_candidate"] if template_type == "pitch" else context["result_pitch_num_candidate"]
        self._set_value_if_exists(self._t("add_pitch_num"), "" if default_pitch_num is None else str(default_pitch_num))
        self._set_value_if_exists(self._t("add_batter_id"), context["batter_id"] or "")
        self._set_value_if_exists(self._t("add_batter_name"), context["batter_name"] or "")
        self._set_value_if_exists(self._t("add_pitcher_id"), context["pitcher_id"] or "")

        self._toggle_group(self._t("add_pitch_fields"), template_type == "pitch")
        self._toggle_group(self._t("add_bat_result_fields"), template_type == "bat_result")
        self._toggle_group(self._t("add_runner_move_section"), template_type in {"bat_result", "baserunning"})

        text_label = "표시 문구 / 메모 (선택)"
        help_text = "투구 결과와 선택적 pitch id만 입력하면 나머지 문맥은 현재 경기 흐름에서 자동으로 채웁니다."
        if template_type == "bat_result":
            text_label = "결과 문구 (선택)"
            help_text = "결과 유형과 필요한 문구만 입력하면 타자/투수/타석 연결은 현재 문맥으로 자동 보정합니다."
        elif template_type == "baserunning":
            text_label = "주루 설명"
            help_text = "필요한 주자 이동만 보완하면 현재 이닝과 상태 연결은 자동 재계산으로 이어집니다."
        elif template_type == "substitution":
            text_label = "교체 설명"
            help_text = "기본 모드에서는 교체 설명만 추가합니다. 세부 교체 필드는 고급 모드에서 직접 확인할 수 있습니다."
        self._set_value_if_exists(self._t("add_text_label"), text_label)
        self._set_value_if_exists(self._t("add_action_help_text"), help_text)

        lines = [
            f"삽입 위치: {context['inning_label']} / {INSERT_MODE_LABELS[insert_mode]} / index {context['insert_at']}",
            f"자동 채움: 타자 {context['batter_name'] or '-'} ({context['batter_id'] or '-'}) / 투수 {context['pitcher_name'] or '-'} ({context['pitcher_id'] or '-'})",
            f"현재 상태: B{context['ball']} S{context['strike']} O{context['out']} / {context['bases']} / {context['offense_team']} 공격",
        ]
        if template_type == "pitch":
            lines.append(f"투구 번호 후보: {context['pitch_num_candidate']} / seqno 후보: {context['seqno_candidate']}")
        elif template_type == "bat_result":
            result_pitch_num = context["result_pitch_num_candidate"]
            lines.append(f"연결 투구 번호: {'-' if result_pitch_num is None else result_pitch_num} / seqno 후보: {context['seqno_candidate']}")
        else:
            lines.append(f"seqno 후보: {context['seqno_candidate']} / 기준 이벤트: {context['selected_text']}")
        if not context["same_plate_appearance"]:
            lines.append("선택 위치가 타석 경계에 있어 인접 타순을 기준으로 기본값을 잡았습니다.")
        self._set_value_if_exists(self._t("add_context_hint"), "\n".join(lines))

    def populate_structured_editors(self) -> None:
        event = self._get_selected_event() or {}
        state = event.get("currentGameState") or {}
        batter_id = str(state.get("batter") or (event.get("batterRecord") or {}).get("pcode") or "").strip() or None
        pitcher_id = str(state.get("pitcher") or "").strip() or None
        batter_name = self._player_name_lookup(batter_id) or None
        event_text = str(event.get("text") or "")
        pitch_result = str(event.get("pitchResult") or "").strip() or None
        pts_pitch_id = str(event.get("ptsPitchId") or "").strip() or None
        pitch_num = event.get("pitchNum")
        detail_text = self._extract_event_detail(event_text, batter_name)
        result_type = parse_result_type(event_text) or "other"
        offense_side = self._selected_offense_side()
        prev_batter_id, prev_batter_name = self._adjacent_batter(batter_id, side=offense_side, offset=-1)
        next_batter_id, next_batter_name = self._adjacent_batter(batter_id, side=offense_side, offset=1)
        pa_summary = self._selected_pa_summary()

        self._populate_add_action_defaults(
            batter_id=batter_id,
            batter_name=batter_name,
            pitcher_id=pitcher_id,
            pitch_result=pitch_result,
            result_type=result_type,
        )

        self._set_value_if_exists(self._t("meaning_batter_id"), batter_id or "")
        self._set_value_if_exists(self._t("meaning_batter_name"), batter_name or "")
        self._set_value_if_exists(self._t("meaning_pitcher_id"), pitcher_id or "")
        self._set_value_if_exists(self._t("meaning_detail"), detail_text)
        self._set_value_if_exists(self._t("meaning_text"), event_text)
        self._set_value_if_exists(self._t("meaning_pitch_result"), pitch_result or "")
        self._set_value_if_exists(self._t("meaning_pitch_num"), "" if pitch_num in (None, "") else str(pitch_num))
        self._set_value_if_exists(self._t("meaning_pts_pitch_id"), pts_pitch_id or "")
        self._set_mapped_choice(self._t("meaning_result_type"), result_type, label_map=RESULT_TYPE_LABELS, default="out")
        self._clear_runner_move_inputs("meaning")

        pa_insert_mode = self._selected_insert_mode("pa") if dpg.does_item_exist(self._t("pa_insert_mode")) else "before"
        default_pa_batter_id = prev_batter_id if pa_insert_mode == "before" else next_batter_id
        default_pa_batter_name = prev_batter_name if pa_insert_mode == "before" else next_batter_name
        if not default_pa_batter_id:
            default_pa_batter_id, default_pa_batter_name = batter_id, batter_name
        self._set_value_if_exists(self._t("pa_batter_id"), default_pa_batter_id or "")
        self._set_value_if_exists(self._t("pa_batter_name"), default_pa_batter_name or "")
        self._set_value_if_exists(self._t("pa_pitcher_id"), pitcher_id or "")
        self._set_value_if_exists(self._t("pa_detail"), "")
        self._set_value_if_exists(self._t("pa_result_text"), "")
        self._set_value_if_exists(self._t("pa_pitch_result"), "")
        self._set_value_if_exists(self._t("pa_pitch_num"), "")
        self._set_value_if_exists(self._t("pa_pts_pitch_id"), "")
        self._set_mapped_choice(self._t("pa_result_type"), "single", label_map=RESULT_TYPE_LABELS, default="single")
        self._clear_pa_pitch_inputs("pa")
        self._clear_runner_move_inputs("pa")

        split_first_batter_id = pa_summary.batter_id if pa_summary else batter_id
        split_first_batter_name = pa_summary.batter_name if pa_summary else batter_name
        split_second_batter_id = next_batter_id or batter_id
        split_second_batter_name = next_batter_name or batter_name
        self._set_value_if_exists(self._t("split_first_batter_id"), split_first_batter_id or "")
        self._set_value_if_exists(self._t("split_first_batter_name"), split_first_batter_name or "")
        self._set_value_if_exists(self._t("split_first_detail"), "")
        self._set_value_if_exists(self._t("split_first_text"), "")
        self._set_mapped_choice(self._t("split_first_result_type"), "out", label_map=RESULT_TYPE_LABELS, default="out")
        self._clear_runner_move_inputs("split_first")
        self._set_value_if_exists(self._t("split_second_batter_id"), split_second_batter_id or "")
        self._set_value_if_exists(self._t("split_second_batter_name"), split_second_batter_name or "")
        self._set_value_if_exists(self._t("split_second_detail"), detail_text)
        self._set_value_if_exists(self._t("split_second_text"), event_text)
        self._set_mapped_choice(
            self._t("split_second_result_type"),
            pa_summary.result_type if pa_summary and pa_summary.result_type else result_type,
            label_map=RESULT_TYPE_LABELS,
            default="out",
        )
        self._clear_runner_move_inputs("split_second")

        merge_batter_id = pa_summary.batter_id if pa_summary and pa_summary.batter_id else batter_id
        merge_batter_name = pa_summary.batter_name if pa_summary and pa_summary.batter_name else batter_name
        self._set_value_if_exists(self._t("merge_batter_id"), merge_batter_id or "")
        self._set_value_if_exists(self._t("merge_batter_name"), merge_batter_name or "")
        self.refresh_basic_split_card()

    def refresh_context_summary(self) -> None:
        block = self._get_selected_block() or {}
        event = self._get_selected_event() or {}
        event_ref = self.selected_event_ref
        if not block or event_ref is None:
            self._set_value_if_exists(
                self._t("context_summary_text"),
                "선택한 이벤트가 없습니다.\n\n좌측 문제 목록이나 중앙 경기 흐름에서 이벤트를 고르면 여기서 상황과 추천 액션을 확인할 수 있습니다.",
            )
            self._set_value_if_exists(self._t("context_flow_text"), "선택 이벤트 앞/현재/뒤 문맥이 여기에 표시됩니다.")
            self._set_value_if_exists(self._t("action_recommendation_text"), f"추천 작업: {ACTION_LABELS[self._recommended_action()]}")
            return

        _group_index, block_index, event_index = event_ref
        state = event.get("currentGameState") or {}
        batter_id = str(state.get("batter") or (event.get("batterRecord") or {}).get("pcode") or "").strip() or None
        pitcher_id = str(state.get("pitcher") or "").strip() or None
        batter_name = self._player_name_lookup(batter_id) or batter_id or "-"
        pitcher_name = self._player_name_lookup(pitcher_id) or pitcher_id or "-"
        pa_summary = self._selected_pa_summary()
        bases = ", ".join(base for base, occupied in (("1루", state.get("base1")), ("2루", state.get("base2")), ("3루", state.get("base3"))) if occupied) or "주자 없음"
        lines = [
            "현재 선택",
            f"- 위치: {self._block_label(block)} / 블록 {block_index} / 이벤트 {event_index}",
            f"- 타자/투수: {batter_name} vs {pitcher_name}",
            f"- 카운트: 볼 {state.get('ball', 0)} / 스트라이크 {state.get('strike', 0)} / 아웃 {state.get('out', 0)}",
            f"- 주자/점수: {bases} | 원정 {state.get('awayScore', 0)} : 홈 {state.get('homeScore', 0)}",
        ]
        if pa_summary:
            lines.append(
                f"- 현재 타석: 이벤트 {pa_summary.start_index}-{pa_summary.end_index}"
                f" | 결과 {pa_summary.result_text or '진행 중'}"
            )
        lines.extend(["", "선택 이벤트 문구", str(event.get("text") or "(문구 없음)")])
        self._set_value_if_exists(self._t("context_summary_text"), "\n".join(lines))

        block_events = block.get("textOptions") or []
        flow_lines = []
        if pa_summary:
            flow_lines.extend(
                [
                    "현재 타석 요약",
                    f"- 범위: 이벤트 {pa_summary.start_index}-{pa_summary.end_index}",
                    f"- 타자: {pa_summary.batter_name or pa_summary.batter_id or '-'}",
                    f"- 투수: {self._player_name_lookup(pa_summary.pitcher_id) or pa_summary.pitcher_id or '-'}",
                    f"- 결과: {pa_summary.result_text or '진행 중'}",
                    "",
                ]
            )
        flow_lines.append("주변 이벤트")
        for offset, label in ((-1, "선택 이벤트 앞"), (0, "현재 선택"), (1, "선택 이벤트 뒤")):
            target_index = event_index + offset
            if 0 <= target_index < len(block_events):
                target_event = block_events[target_index]
                target_state = target_event.get("currentGameState") or {}
                flow_lines.append(
                    f"- {label}: [{target_index}] {target_event.get('text') or '(문구 없음)'} "
                    f"| B{target_state.get('ball', 0)} S{target_state.get('strike', 0)} O{target_state.get('out', 0)}"
                )
            else:
                flow_lines.append(f"- {label}: 없음")
        self._set_value_if_exists(self._t("context_flow_text"), "\n".join(flow_lines))

        finding = None
        findings = (self.validation_result or {}).get("findings", [])
        if self.selected_finding_index is not None and 0 <= self.selected_finding_index < len(findings):
            finding = findings[self.selected_finding_index]
        self._set_value_if_exists(self._t("action_recommendation_text"), f"추천 작업: {ACTION_LABELS[self._recommended_action(finding)]}")

    def apply_editor_mode(self) -> None:
        mode = self._selected_mode()
        basic_mode = mode == EDITOR_MODES[0]
        self._toggle_group(self._t("basic_mode_panel"), basic_mode)
        self._toggle_group(self._t("advanced_mode_panel"), not basic_mode)
        for tag in (
            self._t("game_info_tab"),
            self._t("lineup_tab"),
            self._t("record_tab"),
            self._t("validation_tab"),
            self._t("diff_tab"),
            self._t("history_tab"),
            self._t("auto_preview_tab"),
        ):
            self._toggle_group(tag, not basic_mode)
        self._toggle_group(self._t("relay_tab"), True)
        self._set_value_if_exists(
            self._t("mode_help_text"),
            "문제 목록 -> 경기 흐름 -> 구조화 액션 순서로 수정합니다."
            if basic_mode
            else "원본 이벤트, 게임 정보, 기록을 직접 확인하거나 고급 편집합니다.",
        )
        if basic_mode:
            finding = None
            findings = (self.validation_result or {}).get("findings", [])
            if self.selected_finding_index is not None and 0 <= self.selected_finding_index < len(findings):
                finding = findings[self.selected_finding_index]
            self._set_active_action(self._recommended_action(finding))
            self.refresh_action_sections()
            self._set_tab_value(self._t("detail_tabs"), self._t("relay_tab"))
        else:
            self._toggle_group(self._t("record_batter_editor_group"), self.selected_record_table == "batter")
            self._toggle_group(self._t("record_pitcher_editor_group"), self.selected_record_table == "pitcher")

    def _detail_field_tags(self) -> list[str]:
        tags: list[str] = []
        tags.extend(self._t(f"game_info_{field}") for field in GAME_INFO_FIELDS if field not in BOOLEAN_GAME_INFO_FIELDS)
        tags.extend(self._t(f"lineup_{field}") for field in LINEUP_FIELDS)
        tags.extend(self._t(f"block_{field}") for field in BLOCK_FIELDS)
        tags.extend(self._t(f"metric_{field}") for field in ("homeTeamWinRate", "awayTeamWinRate", "wpaByPlate"))
        tags.extend(self._t(f"event_{field}") for field in EVENT_FIELDS)
        tags.append(self._t("event_batterRecord_pcode"))
        tags.extend(self._t(f"state_{field}") for field in CURRENT_GAME_STATE_FIELDS if field not in BASE_STATE_FIELDS)
        tags.extend(self._t(name) for name in ("change_type", "change_outPlayerTurn"))
        for side in ("inPlayer", "outPlayer"):
            tags.extend(self._t(f"{side}_{field}") for field in PLAYER_CHANGE_PLAYER_FIELDS)

        tags.extend(self._t(name) for name in ("add_template_type", "add_insert_mode", "add_result_type", "add_pitch_result_display", "add_context_hint"))
        tags.extend(self._t(f"add_{field}") for field in ("batter_id", "batter_name", "pitcher_id", "detail", "text", "pitch_result", "pitch_num", "pts_pitch_id"))
        for index in range(1, 4):
            tags.extend(
                self._t(name)
                for name in (
                    f"add_runner_{index}_start",
                    f"add_runner_{index}_end",
                    f"add_runner_{index}_id",
                    f"add_runner_{index}_name",
                )
            )

        tags.extend(self._t(name) for name in ("pa_insert_mode", "pa_result_type"))
        tags.extend(self._t(f"pa_{field}") for field in ("batter_id", "batter_name", "pitcher_id", "detail", "result_text", "pitch_result", "pitch_num", "pts_pitch_id"))
        for index in range(1, 6):
            tags.extend(
                self._t(name)
                for name in (
                    f"pa_pitch_{index}_result",
                    f"pa_pitch_{index}_num",
                    f"pa_pitch_{index}_id",
                    f"pa_pitch_{index}_text",
                )
            )
        for index in range(1, 4):
            tags.extend(
                self._t(name)
                for name in (
                    f"pa_runner_{index}_start",
                    f"pa_runner_{index}_end",
                    f"pa_runner_{index}_id",
                    f"pa_runner_{index}_name",
                )
            )

        tags.extend(self._t("meaning_result_type") for _ in range(1))
        tags.extend(self._t(f"meaning_{field}") for field in ("batter_id", "batter_name", "pitcher_id", "detail", "text", "pitch_result", "pitch_num", "pts_pitch_id"))
        for index in range(1, 4):
            tags.extend(
                self._t(name)
                for name in (
                    f"meaning_runner_{index}_start",
                    f"meaning_runner_{index}_end",
                    f"meaning_runner_{index}_id",
                    f"meaning_runner_{index}_name",
                )
            )

        tags.extend(self._t(name) for name in ("split_basic_batter", "split_basic_summary_text", "split_basic_preview_text"))
        tags.extend(self._t(name) for name in ("split_first_result_type", "split_second_result_type", "merge_batter_id", "merge_batter_name"))
        tags.extend(self._t(f"split_{field}") for field in ("first_batter_id", "first_batter_name", "first_detail", "first_text", "second_batter_id", "second_batter_name", "second_detail", "second_text"))
        for prefix in ("split_first", "split_second"):
            for index in range(1, 4):
                tags.extend(
                    self._t(name)
                    for name in (
                        f"{prefix}_runner_{index}_start",
                        f"{prefix}_runner_{index}_end",
                        f"{prefix}_runner_{index}_id",
                        f"{prefix}_runner_{index}_name",
                    )
                )

        tags.extend(self._t(f"record_batter_{field}") for field in RECORD_BATTER_FIELDS)
        tags.extend(self._t(f"record_pitcher_{field}") for field in RECORD_PITCHER_FIELDS)
        tags.append(self._t("record_total_side"))
        tags.extend(self._t(f"record_total_{field}") for field in RECORD_BATTER_TOTAL_FIELDS)
        return tags

    def _configure_detail_field_widths(self, detail_w: int) -> None:
        field_w = max(220, detail_w - 28)
        for tag in self._detail_field_tags():
            if dpg.does_item_exist(tag):
                try:
                    dpg.configure_item(tag, width=field_w)
                except SystemError:
                    continue

    def _update_validation_delta_text(self, previous: set[str], current: set[str]) -> None:
        resolved = sorted(previous - current)
        added = sorted(current - previous)
        lines = [f"해결됨 {len(resolved)}건", f"새로 감지됨 {len(added)}건"]
        if resolved:
            lines.extend(["", "해결된 항목"])
            lines.extend(resolved[:10])
        if added:
            lines.extend(["", "새 항목"])
            lines.extend(added[:10])
        self._set_value_if_exists(self._t("finding_delta"), "\n".join(lines))

    def _refresh_validation_snapshot(self) -> None:
        if not self.session:
            self.validation_result = None
            self.selected_finding_index = None
            self._last_validation_signatures = set()
            self._set_value_if_exists(self._t("finding_summary"), "검증 결과 없음")
            self._set_value_if_exists(self._t("finding_delta"), "")
            return
        previous = self._last_validation_signatures
        self.validation_result = self.session.validate()
        current = {self._finding_signature(item) for item in self.validation_result.get("findings", [])}
        self._last_validation_signatures = current
        if self.selected_finding_index is not None and self.selected_finding_index >= len(self.validation_result.get("findings", [])):
            self.selected_finding_index = 0 if self.validation_result.get("findings") else None
        self._set_value_if_exists(
            self._t("finding_summary"),
            f"오류 {self.validation_result['error_count']}건 / 경고 {self.validation_result['warning_count']}건",
        )
        self._update_validation_delta_text(previous, current)

    def refresh_all_views(self) -> None:
        self.auto_preview = None
        self.split_preview = None
        self._refresh_validation_snapshot()
        self.refresh_header()
        self.refresh_game_info_table()
        self.refresh_lineup_table()
        self.refresh_record_table()
        self.refresh_relay_tree()
        self.refresh_relay_event_table()
        self.refresh_diff_text()
        self.refresh_history_text()
        self.refresh_auto_preview_text()
        self.refresh_finding_table()
        self.populate_game_info_editor()
        self.populate_lineup_editor()
        self.populate_record_editor()
        self.populate_block_editor()
        self.populate_event_editor()
        self.populate_structured_editors()
        self.refresh_context_summary()
        self.apply_editor_mode()
        self.refresh_selection_summary()

    def refresh_header(self) -> None:
        if not self.session:
            self._set_value_if_exists(self._t("loaded_file"), "불러온 파일 없음")
            self._set_value_if_exists(self._t("save_status"), "-")
            return
        self._set_value_if_exists(self._t("loaded_file"), self.session.path.as_posix())
        save_status = self.session.last_saved_at or "이번 세션에서 아직 저장하지 않음"
        dirty = "수정됨" if self.session.has_unsaved_changes() else "저장됨"
        self._set_value_if_exists(self._t("save_status"), f"{save_status} | {dirty}")

    def refresh_selection_summary(self) -> None:
        parts = []
        if self.selected_game_info_key:
            parts.append(f"게임 정보 {self.selected_game_info_key}")
        if self.selected_lineup_row is not None:
            parts.append(f"라인업 {self.selected_lineup_section}[{self.selected_lineup_row}]")
        if self.selected_record_row is not None:
            parts.append(f"기록 {self.selected_record_table}.{self.selected_record_side}[{self.selected_record_row}]")
        if self.selected_block_ref is not None:
            parts.append(f"중계 블록 {self.selected_block_ref[0]}:{self.selected_block_ref[1]}")
        if self.selected_event_ref is not None:
            parts.append(f"이벤트 {self.selected_event_ref[2]}")
        self._set_value_if_exists(self._t("selection_summary"), " | ".join(parts) if parts else "선택된 항목 없음")

    def refresh_game_info_table(self) -> None:
        self._clear_children(self._t("game_info_table"))
        with dpg.table(
            tag=self._t("game_info_table_inner"),
            parent=self._t("game_info_table"),
            header_row=True,
            row_background=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            policy=dpg.mvTable_SizingStretchProp,
        ):
            dpg.add_table_column(label="Field")
            dpg.add_table_column(label="Value")
            if not self.session:
                return
            game_info = ((self.session.payload.get("lineup") or {}).get("game_info") or {})
            for field in GAME_INFO_FIELDS:
                with dpg.table_row():
                    dpg.add_selectable(
                        label=field,
                        default_value=field == self.selected_game_info_key,
                        callback=lambda _s, _a, user_data: self.select_game_info_field(user_data),
                        user_data=field,
                    )
                    dpg.add_text(str(game_info.get(field, "")))

    def select_game_info_field(self, field: str) -> None:
        self.selected_game_info_key = field
        self.populate_game_info_editor()
        self.refresh_game_info_table()
        self.refresh_selection_summary()

    def populate_game_info_editor(self) -> None:
        if not self.session:
            for field in GAME_INFO_FIELDS:
                self._set_value_if_exists(self._t(f"game_info_{field}"), False if field in BOOLEAN_GAME_INFO_FIELDS else "")
            return
        game_info = ((self.session.payload.get("lineup") or {}).get("game_info") or {})
        for field in GAME_INFO_FIELDS:
            value = game_info.get(field)
            if field in BOOLEAN_GAME_INFO_FIELDS:
                self._set_value_if_exists(self._t(f"game_info_{field}"), bool(value))
            else:
                self._set_value_if_exists(self._t(f"game_info_{field}"), "" if value is None else str(value))

    def apply_game_info_editor(self) -> None:
        session = self._session_required()
        if session is None:
            return

        def mutator(payload: dict[str, Any]) -> None:
            game_info = ((payload.get("lineup") or {}).setdefault("game_info", {}))
            for field in GAME_INFO_FIELDS:
                if field in BOOLEAN_GAME_INFO_FIELDS:
                    self._set_or_delete(game_info, field, bool(dpg.get_value(self._t(f"game_info_{field}"))))
                elif field in INTEGER_GAME_INFO_FIELDS:
                    self._set_or_delete(game_info, field, self._input_int_value(self._t(f"game_info_{field}")))
                else:
                    self._set_or_delete(game_info, field, self._input_text_value(self._t(f"game_info_{field}")))

        session.apply_change("apply_game_info", mutator)
        self.refresh_all_views()

    def refresh_lineup_table(self) -> None:
        self._clear_children(self._t("lineup_table"))
        rows = self._get_lineup_rows()
        with dpg.table(
            tag=self._t("lineup_table_inner"),
            parent=self._t("lineup_table"),
            header_row=True,
            row_background=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            policy=dpg.mvTable_SizingStretchProp,
        ):
            for label in ("#", "playerCode", "playerName", "position", "batorder", "group"):
                dpg.add_table_column(label=label)
            for row_index, row in enumerate(rows):
                with dpg.table_row():
                    dpg.add_selectable(
                        label=str(row_index),
                        default_value=row_index == self.selected_lineup_row,
                        callback=lambda _s, _a, user_data: self.select_lineup_row(user_data),
                        user_data=row_index,
                    )
                    dpg.add_text(str(row.get("playerCode", "")))
                    dpg.add_text(str(row.get("playerName", "")))
                    dpg.add_text(str(row.get("position", row.get("pos", ""))))
                    dpg.add_text(str(row.get("batorder", "")))
                    dpg.add_text(self._lineup_section_label(self.selected_lineup_section))

    def select_lineup_row(self, row_index: int) -> None:
        self.selected_lineup_row = row_index
        self.populate_lineup_editor()
        self.refresh_lineup_table()
        self.refresh_selection_summary()

    def on_lineup_section_change(self) -> None:
        selected_label = str(dpg.get_value(self._t("lineup_section")) or "")
        self.selected_lineup_section = LINEUP_SECTION_LABELS_REVERSE.get(selected_label, selected_label)
        rows = self._get_lineup_rows()
        self.selected_lineup_row = 0 if rows else None
        self.refresh_lineup_table()
        self.populate_lineup_editor()
        self.refresh_selection_summary()

    def populate_lineup_editor(self) -> None:
        row = None
        rows = self._get_lineup_rows()
        if self.selected_lineup_row is not None and 0 <= self.selected_lineup_row < len(rows):
            row = rows[self.selected_lineup_row]
        row = row or {}
        for field in LINEUP_FIELDS:
            self._set_value_if_exists(self._t(f"lineup_{field}"), "" if row.get(field) is None else str(row.get(field)))

    def apply_lineup_editor(self) -> None:
        session = self._session_required()
        if session is None or self.selected_lineup_row is None:
            return

        def mutator(payload: dict[str, Any]) -> None:
            rows = ((payload.get("lineup") or {}).setdefault(self.selected_lineup_section, []))
            if not (0 <= self.selected_lineup_row < len(rows)):
                return
            row = rows[self.selected_lineup_row]
            for field in LINEUP_FIELDS:
                if field in {"batorder", "height", "weight"}:
                    self._set_or_delete(row, field, self._input_int_value(self._t(f"lineup_{field}")))
                else:
                    self._set_or_delete(row, field, self._input_text_value(self._t(f"lineup_{field}")))

        session.apply_change("apply_lineup_row", mutator)
        self.refresh_all_views()

    def add_lineup_row(self) -> None:
        session = self._session_required()
        if session is None:
            return
        session.add_lineup_row(self.selected_lineup_section)
        rows = self._get_lineup_rows()
        self.selected_lineup_row = len(rows) - 1 if rows else None
        self.refresh_all_views()

    def delete_lineup_row(self) -> None:
        session = self._session_required()
        if session is None or self.selected_lineup_row is None:
            return
        session.delete_lineup_row(self.selected_lineup_section, self.selected_lineup_row)
        rows = self._get_lineup_rows()
        self.selected_lineup_row = min(self.selected_lineup_row, len(rows) - 1) if rows else None
        self.refresh_all_views()

    def refresh_record_table(self) -> None:
        self._clear_children(self._t("record_table"))
        rows = self._get_record_rows()
        columns = RECORD_BATTER_FIELDS if self.selected_record_table == "batter" else RECORD_PITCHER_FIELDS
        with dpg.table(
            tag=self._t("record_table_inner"),
            parent=self._t("record_table"),
            header_row=True,
            row_background=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            policy=dpg.mvTable_SizingStretchProp,
        ):
            dpg.add_table_column(label="#")
            for column in columns:
                dpg.add_table_column(label=column)
            for row_index, row in enumerate(rows):
                with dpg.table_row():
                    dpg.add_selectable(
                        label=str(row_index),
                        default_value=row_index == self.selected_record_row,
                        callback=lambda _s, _a, user_data: self.select_record_row(user_data),
                        user_data=row_index,
                    )
                    for column in columns:
                        dpg.add_text(str(row.get(column, "")))

    def on_record_scope_change(self) -> None:
        scope_label = str(dpg.get_value(self._t("record_scope")) or "")
        scope = RECORD_SCOPE_LABELS_REVERSE.get(scope_label, scope_label)
        table, side = scope.split(":")
        self.selected_record_table = table
        self.selected_record_side = side
        rows = self._get_record_rows()
        self.selected_record_row = 0 if rows else None
        self.refresh_record_table()
        self.populate_record_editor()
        self.refresh_selection_summary()

    def select_record_row(self, row_index: int) -> None:
        self.selected_record_row = row_index
        self.populate_record_editor()
        self.refresh_record_table()
        self.refresh_selection_summary()

    def populate_record_editor(self) -> None:
        row = None
        rows = self._get_record_rows()
        if self.selected_record_row is not None and 0 <= self.selected_record_row < len(rows):
            row = rows[self.selected_record_row]
        row = row or {}
        for field in RECORD_BATTER_FIELDS:
            self._set_value_if_exists(self._t(f"record_batter_{field}"), "" if row.get(field) is None else str(row.get(field)))
        for field in RECORD_PITCHER_FIELDS:
            self._set_value_if_exists(self._t(f"record_pitcher_{field}"), "" if row.get(field) is None else str(row.get(field)))
        self._toggle_group(self._t("record_batter_editor_group"), self.selected_record_table == "batter")
        self._toggle_group(self._t("record_pitcher_editor_group"), self.selected_record_table == "pitcher")
        if self.session:
            batter = ((self.session.payload.get("record") or {}).get("batter") or {})
            total_side = self.selected_record_side
            total_row = batter.get(f"{total_side}Total") or {}
            self._set_value_if_exists(self._t("record_total_side"), SIDE_LABELS.get(total_side, total_side))
            for field in RECORD_BATTER_TOTAL_FIELDS:
                self._set_value_if_exists(self._t(f"record_total_{field}"), "" if total_row.get(field) is None else str(total_row.get(field)))

    def apply_record_editor(self) -> None:
        session = self._session_required()
        if session is None or self.selected_record_row is None:
            return
        table = self.selected_record_table
        side = self.selected_record_side
        columns = RECORD_BATTER_FIELDS if table == "batter" else RECORD_PITCHER_FIELDS

        def mutator(payload: dict[str, Any]) -> None:
            rows = (((payload.get("record") or {}).get(table) or {}).setdefault(side, []))
            if not (0 <= self.selected_record_row < len(rows)):
                return
            row = rows[self.selected_record_row]
            for field in columns:
                tag_prefix = "record_batter" if table == "batter" else "record_pitcher"
                if table == "batter" and field in INTEGER_RECORD_BATTER_FIELDS:
                    self._set_or_delete(row, field, self._input_int_value(self._t(f"{tag_prefix}_{field}")))
                elif table == "pitcher" and field not in {"name", "inn", "pcode"}:
                    self._set_or_delete(row, field, self._input_int_value(self._t(f"{tag_prefix}_{field}")))
                else:
                    self._set_or_delete(row, field, self._input_text_value(self._t(f"{tag_prefix}_{field}")))

        session.apply_change(f"apply_record_row:{table}:{side}", mutator)
        self.refresh_all_views()

    def apply_record_total_editor(self) -> None:
        session = self._session_required()
        if session is None:
            return
        side_label = str(dpg.get_value(self._t("record_total_side")) or SIDE_LABELS["home"])
        side = SIDE_LABELS_REVERSE.get(side_label, side_label)

        def mutator(payload: dict[str, Any]) -> None:
            batter = ((payload.get("record") or {}).setdefault("batter", {}))
            total_row = batter.setdefault(f"{side}Total", {})
            for field in RECORD_BATTER_TOTAL_FIELDS:
                self._set_or_delete(total_row, field, self._input_int_value(self._t(f"record_total_{field}")))

        session.apply_change(f"apply_record_total:{side}", mutator)
        self.refresh_all_views()

    def add_record_row(self) -> None:
        session = self._session_required()
        if session is None:
            return
        session.add_record_row(self.selected_record_table, self.selected_record_side)
        rows = self._get_record_rows()
        self.selected_record_row = len(rows) - 1 if rows else None
        self.refresh_all_views()

    def delete_record_row(self) -> None:
        session = self._session_required()
        if session is None or self.selected_record_row is None:
            return
        session.delete_record_row(self.selected_record_table, self.selected_record_side, self.selected_record_row)
        rows = self._get_record_rows()
        self.selected_record_row = min(self.selected_record_row, len(rows) - 1) if rows else None
        self.refresh_all_views()

    def recalc_record_totals(self) -> None:
        session = self._session_required()
        if session is None:
            return
        session.recalculate_batter_totals()
        self.refresh_all_views()

    def _relay_filters(self) -> dict[str, Any]:
        return {
            "query": str(dpg.get_value(self._t("relay_query")) or "").strip().lower(),
            "inning": str(dpg.get_value(self._t("relay_inning_filter")) or RELAY_ALL_FILTER_LABEL),
            "half": str(dpg.get_value(self._t("relay_half_filter")) or RELAY_ALL_FILTER_LABEL),
            "type": str(dpg.get_value(self._t("relay_type_filter")) or RELAY_ALL_FILTER_LABEL),
            "errors_only": bool(dpg.get_value(self._t("relay_errors_only"))),
            "duplicates_only": bool(dpg.get_value(self._t("relay_duplicates_only"))),
            "missing_only": bool(dpg.get_value(self._t("relay_missing_only"))),
        }

    def _relay_issue_codes_by_location(self) -> dict[tuple[int, int, int], set[str]]:
        issue_codes: dict[tuple[int, int, int], set[str]] = {}
        if not self.session:
            return issue_codes
        for finding in self.session.scan_relay_issues():
            location = finding.get("location") or {}
            ref = (location.get("group_index"), location.get("block_index"), location.get("event_index"))
            if None in ref:
                continue
            issue_codes.setdefault(ref, set()).add(str(finding.get("code")))
        return issue_codes

    def _refresh_relay_filter_items(self) -> None:
        if not self.session:
            return
        inning_items = [RELAY_ALL_FILTER_LABEL]
        type_items = [RELAY_ALL_FILTER_LABEL]
        innings_seen = set()
        types_seen = set()
        for _group_index, _block_index, block in self._iter_blocks():
            innings_seen.add(str(block.get("inn", "")))
            for event in block.get("textOptions") or []:
                types_seen.add(str(event.get("type", "")))
        inning_items.extend(sorted(item for item in innings_seen if item))
        type_items.extend(sorted(item for item in types_seen if item))
        dpg.configure_item(self._t("relay_inning_filter"), items=inning_items)
        dpg.configure_item(self._t("relay_type_filter"), items=type_items)

    def _event_passes_filter(self, block: dict[str, Any], event: dict[str, Any], filters: dict[str, Any], issue_codes: set[str]) -> bool:
        query = filters["query"]
        if query:
            text_match = query in str(event.get("text", "")).lower()
            batter_match = query in str((event.get("currentGameState") or {}).get("batter", "")).lower()
            pitcher_match = query in str((event.get("currentGameState") or {}).get("pitcher", "")).lower()
            pitch_match = query in str(event.get("ptsPitchId", "")).lower()
            if not any((text_match, batter_match, pitcher_match, pitch_match)):
                return False
        if filters["inning"] != RELAY_ALL_FILTER_LABEL and str(block.get("inn", "")) != filters["inning"]:
            return False
        if filters["half"] != RELAY_ALL_FILTER_LABEL and str(block.get("homeOrAway", "")) != ("0" if filters["half"] == RELAY_HALF_FILTER_LABELS["Top"] else "1"):
            return False
        if filters["type"] != RELAY_ALL_FILTER_LABEL and str(event.get("type", "")) != filters["type"]:
            return False
        if filters["errors_only"] and not any(code.startswith("missing_") for code in issue_codes):
            return False
        if filters["duplicates_only"] and not any(code.startswith("duplicate_") for code in issue_codes):
            return False
        if filters["missing_only"] and not (any(code.startswith("state_jump") for code in issue_codes) or any(code.startswith("missing_") for code in issue_codes) or "seq_gap" in issue_codes):
            return False
        return True

    def refresh_relay_tree(self) -> None:
        self._clear_children(self._t("relay_tree"))
        if not self.session:
            return
        relay = self.session.payload.get("relay") or []
        for group_index, inning_group in enumerate(relay):
            if not inning_group:
                continue
            first_block = inning_group[0]
            tree_label = f"{first_block.get('inn', '?')}회 {'초' if str(first_block.get('homeOrAway')) == '0' else '말'}"
            with dpg.tree_node(label=tree_label, default_open=True, parent=self._t("relay_tree")):
                for block_index, block in enumerate(inning_group):
                    label = f"[{block_index}] {block.get('title', '(no title)')} | {len(block.get('textOptions') or [])} events"
                    dpg.add_selectable(
                        label=label,
                        default_value=self.selected_block_ref == (group_index, block_index),
                        callback=lambda _s, _a, user_data: self.select_block(user_data),
                        user_data=(group_index, block_index),
                    )

    def select_block(self, ref: tuple[int, int]) -> None:
        self.selected_block_ref = ref
        block = self._get_selected_block()
        if block and (block.get("textOptions") or []):
            current_event_index = self.selected_event_ref[2] if self.selected_event_ref and self.selected_event_ref[:2] == ref else 0
            current_event_index = min(current_event_index, len(block.get("textOptions") or []) - 1)
            self.selected_event_ref = (*ref, current_event_index)
        else:
            self.selected_event_ref = None
        self.refresh_relay_tree()
        self.refresh_relay_event_table()
        self.populate_block_editor()
        self.populate_event_editor()
        self.populate_structured_editors()
        self.refresh_context_summary()
        self.apply_editor_mode()
        self.refresh_selection_summary()

    def select_event(self, ref: tuple[int, int, int]) -> None:
        self.selected_block_ref = ref[:2]
        self.selected_event_ref = ref
        self.refresh_relay_tree()
        self.refresh_relay_event_table()
        self.populate_block_editor()
        self.populate_event_editor()
        self.populate_structured_editors()
        self.refresh_context_summary()
        self.apply_editor_mode()
        self.refresh_selection_summary()

    def select_relative_event(self, delta: int) -> None:
        if self.selected_event_ref is None:
            return
        block = self._get_selected_block() or {}
        events = block.get("textOptions") or []
        if not events:
            return
        group_index, block_index, event_index = self.selected_event_ref
        next_index = max(0, min(len(events) - 1, event_index + delta))
        self.select_event((group_index, block_index, next_index))

    def refresh_relay_event_table(self) -> None:
        self._clear_children(self._t("relay_events"))
        self._refresh_relay_filter_items()
        if not self.session or self.selected_block_ref is None:
            return
        block = self._get_selected_block()
        if not block:
            return
        view_mode_label = str(dpg.get_value(self._t("relay_view_mode")) or RELAY_VIEW_MODE_LABELS["Event"]) if dpg.does_item_exist(self._t("relay_view_mode")) else RELAY_VIEW_MODE_LABELS["Event"]
        view_mode = RELAY_VIEW_MODE_LABELS_REVERSE.get(view_mode_label, view_mode_label)
        if view_mode == "PA":
            pa_rows = self.session.preview_auto_rebuild().get("plate_appearances", [])
            target_rows = [
                row
                for row in pa_rows
                if row.group_index == self.selected_block_ref[0] and row.block_index == self.selected_block_ref[1]
            ]
            with dpg.table(
                tag=self._t("relay_events_inner"),
                parent=self._t("relay_events"),
                header_row=True,
                row_background=True,
                borders_innerH=True,
                borders_outerH=True,
                borders_innerV=True,
                borders_outerV=True,
                policy=dpg.mvTable_SizingStretchProp,
            ):
                for label in ("start", "end", "batter", "pitcher", "result", "terminal"):
                    dpg.add_table_column(label=label)
                for pa in target_rows:
                    with dpg.table_row():
                        dpg.add_selectable(
                            label=str(pa.start_index),
                            default_value=self.selected_event_ref == (*self.selected_block_ref, pa.end_index),
                            callback=lambda _s, _a, user_data: self.select_event(user_data),
                            user_data=(*self.selected_block_ref, pa.end_index),
                        )
                        dpg.add_text(str(pa.end_index))
                        dpg.add_text(str(pa.batter_name or pa.batter_id or ""))
                        dpg.add_text(str(pa.pitcher_id or ""))
                        dpg.add_text(str(pa.result_text or ""))
                        dpg.add_text("Y" if pa.is_terminal else "N")
            return
        filters = self._relay_filters()
        issue_codes = self._relay_issue_codes_by_location()
        with dpg.table(
            tag=self._t("relay_events_inner"),
            parent=self._t("relay_events"),
            header_row=True,
            row_background=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            policy=dpg.mvTable_SizingStretchProp,
        ):
            for label in ("#", "seqno", "type", "pitch", "ptsPitchId", "flags", "text"):
                dpg.add_table_column(label=label)
            for event_index, event in enumerate(block.get("textOptions") or []):
                ref = (*self.selected_block_ref, event_index)
                location_codes = issue_codes.get(ref, set())
                if not self._event_passes_filter(block, event, filters, location_codes):
                    continue
                with dpg.table_row():
                    dpg.add_selectable(
                        label=str(event_index),
                        default_value=self.selected_event_ref == ref,
                        callback=lambda _s, _a, user_data: self.select_event(user_data),
                        user_data=ref,
                    )
                    dpg.add_text(str(event.get("seqno", "")))
                    dpg.add_text(str(event.get("type", "")))
                    dpg.add_text(str(event.get("pitchNum", "")))
                    dpg.add_text(str(event.get("ptsPitchId", "")))
                    dpg.add_text(", ".join(sorted(location_codes)))
                    dpg.add_text(str(event.get("text", "")))

    def populate_block_editor(self) -> None:
        block = self._get_selected_block() or {}
        for field in BLOCK_FIELDS:
            self._set_value_if_exists(self._t(f"block_{field}"), "" if block.get(field) is None else str(block.get(field)))
        metric_option = block.get("metricOption") or {}
        for field in ("homeTeamWinRate", "awayTeamWinRate", "wpaByPlate"):
            self._set_value_if_exists(self._t(f"metric_{field}"), "" if metric_option.get(field) is None else str(metric_option.get(field)))

    def apply_block_editor(self) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        group_index, block_index = self.selected_block_ref

        def mutator(payload: dict[str, Any]) -> None:
            block = (payload.get("relay") or [])[group_index][block_index]
            for field in BLOCK_FIELDS:
                if field in INTEGER_BLOCK_FIELDS:
                    self._set_or_delete(block, field, self._input_int_value(self._t(f"block_{field}")))
                else:
                    self._set_or_delete(block, field, self._input_text_value(self._t(f"block_{field}")))
            metric_option = block.setdefault("metricOption", {})
            for field in ("homeTeamWinRate", "awayTeamWinRate", "wpaByPlate"):
                self._set_or_delete(metric_option, field, self._input_text_value(self._t(f"metric_{field}")))
            if not metric_option:
                block.pop("metricOption", None)

        session.apply_change("apply_block_editor", mutator)
        self.refresh_all_views()

    def populate_event_editor(self) -> None:
        event = self._get_selected_event() or {}
        for field in EVENT_FIELDS:
            self._set_value_if_exists(self._t(f"event_{field}"), "" if event.get(field) is None else str(event.get(field)))
        batter_record = event.get("batterRecord") or {}
        self._set_value_if_exists(self._t("event_batterRecord_pcode"), "" if batter_record.get("pcode") is None else str(batter_record.get("pcode")))
        state = event.get("currentGameState") or {}
        for field in CURRENT_GAME_STATE_FIELDS:
            if field in BASE_STATE_FIELDS:
                self._set_value_if_exists(self._t(f"state_{field}"), bool(state.get(field)))
            else:
                self._set_value_if_exists(self._t(f"state_{field}"), "" if state.get(field) is None else str(state.get(field)))
        player_change = event.get("playerChange") or {}
        self._set_value_if_exists(self._t("change_type"), "" if player_change.get("type") is None else str(player_change.get("type")))
        self._set_value_if_exists(self._t("change_outPlayerTurn"), "" if player_change.get("outPlayerTurn") is None else str(player_change.get("outPlayerTurn")))
        for side in ("inPlayer", "outPlayer"):
            player_row = player_change.get(side) or {}
            for field in PLAYER_CHANGE_PLAYER_FIELDS:
                self._set_value_if_exists(self._t(f"{side}_{field}"), "" if player_row.get(field) is None else str(player_row.get(field)))

    def apply_event_editor(self) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        group_index, block_index, event_index = self.selected_event_ref

        def mutator(payload: dict[str, Any]) -> None:
            event = ((payload.get("relay") or [])[group_index][block_index].setdefault("textOptions", []))[event_index]
            for field in EVENT_FIELDS:
                value = self._input_int_value(self._t(f"event_{field}")) if field in INTEGER_EVENT_FIELDS else self._input_text_value(self._t(f"event_{field}"))
                if field in OPTIONAL_EVENT_FIELDS:
                    self._set_or_delete(event, field, value)
                else:
                    event[field] = value

            batter_record = event.setdefault("batterRecord", {})
            self._set_or_delete(batter_record, "pcode", self._input_text_value(self._t("event_batterRecord_pcode")))
            if not batter_record:
                event.pop("batterRecord", None)

            state = event.setdefault("currentGameState", {})
            for field in CURRENT_GAME_STATE_FIELDS:
                if field in BASE_STATE_FIELDS:
                    self._set_or_delete(state, field, bool(dpg.get_value(self._t(f"state_{field}"))))
                elif field in INTEGER_STATE_FIELDS:
                    self._set_or_delete(state, field, self._input_int_value(self._t(f"state_{field}")))
                else:
                    self._set_or_delete(state, field, self._input_text_value(self._t(f"state_{field}")))

            player_change = event.setdefault("playerChange", {})
            self._set_or_delete(player_change, "type", self._input_text_value(self._t("change_type")))
            self._set_or_delete(player_change, "outPlayerTurn", self._input_text_value(self._t("change_outPlayerTurn")))
            for side in ("inPlayer", "outPlayer"):
                player_row = player_change.setdefault(side, {})
                for field in PLAYER_CHANGE_PLAYER_FIELDS:
                    self._set_or_delete(player_row, field, self._input_text_value(self._t(f"{side}_{field}")))
                if not player_row:
                    player_change.pop(side, None)
            if not player_change:
                event.pop("playerChange", None)

        session.apply_change("apply_event_editor", mutator)
        self.refresh_all_views()

    def add_block(self) -> None:
        session = self._session_required()
        if session is None:
            return
        if self.selected_block_ref is None:
            session.add_relay_block()
        else:
            group_index, block_index = self.selected_block_ref
            session.add_relay_block(group_index=group_index, block_index=block_index + 1)
        self.selected_block_ref = next(((g, b) for g, b, _block in self._iter_blocks()), None)
        self.selected_event_ref = None
        self.refresh_all_views()

    def delete_block(self) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        session.delete_relay_block(*self.selected_block_ref)
        self.selected_block_ref = next(((g, b) for g, b, _block in self._iter_blocks()), None)
        self.selected_event_ref = None
        self.refresh_all_views()

    def move_block(self, delta: int) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        next_ref = session.move_relay_block(*self.selected_block_ref, delta=delta)
        if next_ref is not None:
            self.selected_block_ref = next_ref
        self.refresh_all_views()

    def add_event(self) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        group_index, block_index = self.selected_block_ref
        insert_at = None if self.selected_event_ref is None else self.selected_event_ref[2] + 1
        event_index = session.add_relay_event(group_index, block_index, event_index=insert_at)
        self.selected_event_ref = (group_index, block_index, event_index)
        self.refresh_all_views()

    def delete_event(self) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        group_index, block_index, event_index = self.selected_event_ref
        session.delete_relay_event(group_index, block_index, event_index)
        block = self._get_selected_block()
        events = block.get("textOptions") if block else []
        if events:
            self.selected_event_ref = (group_index, block_index, min(event_index, len(events) - 1))
        else:
            self.selected_event_ref = None
        self.refresh_all_views()

    def duplicate_event(self) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        group_index, block_index, event_index = self.selected_event_ref
        new_index = session.duplicate_relay_event(group_index, block_index, event_index)
        self.selected_event_ref = (group_index, block_index, new_index)
        self.refresh_all_views()

    def move_event(self, delta: int) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        group_index, block_index, event_index = self.selected_event_ref
        new_index = session.move_relay_event(group_index, block_index, event_index, delta)
        self.selected_event_ref = (group_index, block_index, new_index)
        self.refresh_all_views()

    def renumber_seqno(self) -> None:
        session = self._session_required()
        if session is None:
            return
        session.renumber_seqno()
        self.refresh_all_views()

    def fill_missing_state(self) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        session.fill_missing_current_game_state(*self.selected_block_ref)
        self.refresh_all_views()

    def _semantic_spec_from_inputs(self, prefix: str) -> dict[str, Any]:
        return {
            "batter_id": self._input_text_value(self._t(f"{prefix}_batter_id")),
            "batter_name": self._input_text_value(self._t(f"{prefix}_batter_name")),
            "pitcher_id": self._input_text_value(self._t(f"{prefix}_pitcher_id")),
            "result_type": self._selected_result_type(prefix),
            "detail": self._input_text_value(self._t(f"{prefix}_detail")),
            "text": self._input_text_value(self._t(f"{prefix}_text")),
            "pitch_result": self._input_text_value(self._t(f"{prefix}_pitch_result")),
            "pitch_num": self._input_int_value(self._t(f"{prefix}_pitch_num")),
            "pts_pitch_id": self._input_text_value(self._t(f"{prefix}_pts_pitch_id")),
            "runner_moves": self._input_runner_moves(prefix),
        }

    def _structured_add_spec_from_inputs(self) -> tuple[str, dict[str, Any]]:
        template_type = self._selected_add_template_type()
        context = self._build_insert_context(insert_mode=self._selected_insert_mode("add"))
        spec: dict[str, Any] = {
            "batter_id": self._input_text_value(self._t("add_batter_id")) or context["batter_id"],
            "batter_name": self._input_text_value(self._t("add_batter_name")) or context["batter_name"],
            "pitcher_id": self._input_text_value(self._t("add_pitcher_id")) or context["pitcher_id"],
            "text": self._input_text_value(self._t("add_text")),
        }
        if template_type == "pitch":
            spec["pitch_result"] = self._selected_pitch_result()
            spec["pitch_num"] = context["pitch_num_candidate"]
            spec["pts_pitch_id"] = self._input_text_value(self._t("add_pts_pitch_id"))
        elif template_type == "bat_result":
            spec["result_type"] = self._selected_result_type("add")
            spec["detail"] = self._input_text_value(self._t("add_detail"))
            spec["pitch_num"] = context["result_pitch_num_candidate"]
            spec["runner_moves"] = self._input_runner_moves("add")
        elif template_type == "baserunning":
            spec["runner_moves"] = self._input_runner_moves("add")
        elif template_type == "substitution":
            spec["text"] = self._input_text_value(self._t("add_text")) or "선수 교체"
        return template_type, spec

    def insert_structured_event(self) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        group_index, block_index = self.selected_block_ref
        template_type, spec = self._structured_add_spec_from_inputs()
        insert_mode = self._selected_insert_mode("add")
        insert_at = self._candidate_insert_index(insert_mode)
        inserted = session.insert_event_template(
            group_index=group_index,
            block_index=block_index,
            insert_at=insert_at,
            template_type=template_type,
            spec=spec,
        )
        if inserted:
            self.selected_event_ref = (group_index, block_index, inserted[0])
        self.refresh_all_views()

    def insert_missing_plate_appearance(self) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        group_index, block_index = self.selected_block_ref
        insert_mode = self._selected_insert_mode("pa")
        if self.selected_event_ref is None:
            insert_at = 0
        elif insert_mode == "after":
            insert_at = self.selected_event_ref[2] + 1
        else:
            insert_at = self.selected_event_ref[2]
        pitch_list: list[dict[str, Any]] = []
        for index in range(1, 6):
            pitch_result = self._input_text_value(self._t(f"pa_pitch_{index}_result"))
            pitch_text = self._input_text_value(self._t(f"pa_pitch_{index}_text"))
            pitch_num = self._input_int_value(self._t(f"pa_pitch_{index}_num"))
            pitch_id = self._input_text_value(self._t(f"pa_pitch_{index}_id"))
            if not any((pitch_result, pitch_text, pitch_num, pitch_id)):
                continue
            pitch_list.append(
                {
                    "pitch_result": pitch_result,
                    "text": pitch_text,
                    "pitch_num": pitch_num,
                    "pts_pitch_id": pitch_id,
                }
            )
        spec = self._semantic_spec_from_inputs("pa")
        spec["pitch_list"] = pitch_list
        inserted = session.insert_missing_plate_appearance(
            group_index=group_index,
            block_index=block_index,
            insert_at=insert_at,
            spec=spec,
        )
        if inserted:
            self.selected_event_ref = (group_index, block_index, inserted[0])
        self.refresh_all_views()

    def apply_meaning_edit(self) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        group_index, block_index, event_index = self.selected_event_ref
        spec = self._semantic_spec_from_inputs("meaning")
        spec["replace_runner_events"] = bool(dpg.get_value(self._t("meaning_replace_runner_events")))
        changed = session.update_event_meaning(
            group_index=group_index,
            block_index=block_index,
            event_index=event_index,
            spec=spec,
        )
        if changed:
            self.selected_event_ref = (group_index, block_index, changed[0])
        self.refresh_all_views()

    def preview_split_from_selected_event(self) -> None:
        self.refresh_basic_split_card(preview=True)
        if self.split_preview:
            self.state.set_status(
                "info" if self.split_preview.get("ok") else "warn",
                "타석 분리 미리보기",
                str(self.split_preview.get("message") or "-"),
                source="수정/보정",
            )

    def split_selected_plate_appearance_basic(self) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        selected_entry = self._selected_split_entry()
        if selected_entry is None:
            self.state.set_status("warn", "타석 분리 불가", "공격 팀 엔트리에서 새 타자를 먼저 선택해 주세요.", source="수정/보정")
            return
        group_index, block_index, event_index = self.selected_event_ref
        result = session.split_plate_appearance_from_event(
            group_index=group_index,
            block_index=block_index,
            selected_index=event_index,
            new_batter_id=str(selected_entry.get("player_id") or ""),
            new_batter_name=str(selected_entry.get("name") or "") or None,
            auto_insert_intro=bool(dpg.get_value(self._t("split_basic_auto_intro"))) if dpg.does_item_exist(self._t("split_basic_auto_intro")) else True,
        )
        if not result.get("ok"):
            self.split_preview = result
            self.refresh_basic_split_card(preview=True)
            self.state.set_status("warn", "타석 분리 불가", str(result.get("message") or "-"), source="수정/보정")
            return
        target_block_index = int(result.get("target_block_index") or block_index)
        start_index = int(result.get("target_start_index") or result.get("start_index") or 0)
        self.selected_block_ref = (group_index, target_block_index)
        self.selected_event_ref = (group_index, target_block_index, start_index)
        self.refresh_all_views()
        self._set_active_action("split_merge")
        self.state.set_status("info", "타석 분리 완료", str(result.get("message") or "선택 이벤트부터 새 타석으로 분리했습니다."), source="수정/보정")

    def split_selected_plate_appearance_advanced(self) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        group_index, block_index, event_index = self.selected_event_ref
        spec = {
            "first_batter_id": self._input_text_value(self._t("split_first_batter_id")),
            "first_batter_name": self._input_text_value(self._t("split_first_batter_name")),
            "first_result_type": self._selected_result_type("split_first"),
            "first_detail": self._input_text_value(self._t("split_first_detail")),
            "first_text": self._input_text_value(self._t("split_first_text")),
            "first_runner_moves": self._input_runner_moves("split_first"),
            "second_batter_id": self._input_text_value(self._t("split_second_batter_id")),
            "second_batter_name": self._input_text_value(self._t("split_second_batter_name")),
            "second_result_type": self._selected_result_type("split_second"),
            "second_detail": self._input_text_value(self._t("split_second_detail")),
            "second_text": self._input_text_value(self._t("split_second_text")),
            "second_runner_moves": self._input_runner_moves("split_second"),
        }
        next_index = session.split_plate_appearance(
            group_index=group_index,
            block_index=block_index,
            split_at=event_index,
            spec=spec,
        )
        if next_index is not None:
            self.selected_event_ref = (group_index, block_index, next_index)
        self.refresh_all_views()

    def merge_selected_plate_appearance(self) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        group_index, block_index, event_index = self.selected_event_ref
        next_index = session.merge_with_previous_plate_appearance(
            group_index=group_index,
            block_index=block_index,
            selected_index=event_index,
            merged_batter_id=self._input_text_value(self._t("merge_batter_id")) if dpg.does_item_exist(self._t("merge_batter_id")) else None,
            merged_batter_name=self._input_text_value(self._t("merge_batter_name")) if dpg.does_item_exist(self._t("merge_batter_name")) else None,
        )
        if next_index is not None:
            next_block_index, next_event_index = next_index
            self.selected_block_ref = (group_index, next_block_index)
            self.selected_event_ref = (group_index, next_block_index, next_event_index)
        self.refresh_all_views()

    def run_validation(self) -> None:
        session = self._session_required()
        if session is None:
            return
        self._refresh_validation_snapshot()
        self.refresh_finding_table()
        self.refresh_context_summary()
        self.apply_editor_mode()
        self.state.set_status(
            "info" if self.validation_result["ok"] else "warn",
            "검증 실행 완료",
            f"errors={self.validation_result['error_count']} warnings={self.validation_result['warning_count']}",
            source="수정/보정",
        )

    def _finding_location_text(self, finding: dict[str, Any]) -> str:
        location = finding.get("location") or {}
        tab = location.get("tab")
        if tab == "relay":
            relay = (self.session.payload.get("relay") or []) if self.session else []
            group_index = location.get("group_index")
            block_index = location.get("block_index")
            event_index = location.get("event_index")
            if group_index is None or block_index is None:
                return "중계"
            try:
                block = relay[group_index][block_index]
            except Exception:
                return "중계"
            suffix = f" / 이벤트 {event_index}" if event_index is not None else ""
            return f"{self._block_label(block)}{suffix}"
        if tab == "record":
            return f"기록 {location.get('table', '-')}.{location.get('side', '-')}"
        return "-"

    def _refresh_finding_filter_items(self) -> None:
        if not self.validation_result:
            return
        inning_items = {"전체"}
        for finding in self.validation_result.get("findings", []):
            location = finding.get("location") or {}
            if location.get("tab") != "relay" or not self.session:
                continue
            try:
                block = self.session.payload["relay"][location["group_index"]][location["block_index"]]
            except Exception:
                continue
            inning_items.add(str(block.get("inn", "")))
        if dpg.does_item_exist(self._t("finding_inning_filter")):
            dpg.configure_item(self._t("finding_inning_filter"), items=sorted(inning_items, key=lambda item: (item != "전체", item)))
        if dpg.does_item_exist(self._t("finding_half_filter")):
            dpg.configure_item(self._t("finding_half_filter"), items=["전체", "초", "말"])

    def _finding_matches_filters(self, finding: dict[str, Any]) -> bool:
        query = str(dpg.get_value(self._t("finding_query")) or "").strip().lower() if dpg.does_item_exist(self._t("finding_query")) else ""
        type_group = str(dpg.get_value(self._t("finding_type_filter")) or "전체") if dpg.does_item_exist(self._t("finding_type_filter")) else "전체"
        inning_filter = str(dpg.get_value(self._t("finding_inning_filter")) or "전체") if dpg.does_item_exist(self._t("finding_inning_filter")) else "전체"
        half_filter = str(dpg.get_value(self._t("finding_half_filter")) or "전체") if dpg.does_item_exist(self._t("finding_half_filter")) else "전체"
        code = str(finding.get("code") or "")
        location_text = self._finding_location_text(finding)
        if query and query not in " ".join((code, str(finding.get("message") or ""), location_text)).lower():
            return False
        code_prefixes = FINDING_TYPE_GROUPS.get(type_group)
        if code_prefixes and not any(code.startswith(prefix) for prefix in code_prefixes):
            return False
        if inning_filter != "전체" and inning_filter not in location_text:
            return False
        if half_filter != "전체" and half_filter not in location_text:
            return False
        return True

    def refresh_finding_table(self) -> None:
        self._clear_children(self._t("findings_table"))
        self._refresh_finding_filter_items()
        with dpg.table(
            tag=self._t("findings_table_inner"),
            parent=self._t("findings_table"),
            header_row=True,
            row_background=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            policy=dpg.mvTable_SizingStretchProp,
        ):
            for label in ("#", "심각도", "유형", "위치", "설명"):
                dpg.add_table_column(label=label)
            findings = (self.validation_result or {}).get("findings", [])
            for index, finding in enumerate(findings):
                if not self._finding_matches_filters(finding):
                    continue
                with dpg.table_row():
                    dpg.add_selectable(
                        label=str(index),
                        default_value=index == self.selected_finding_index,
                        callback=lambda _s, _a, user_data: self.select_finding(user_data),
                        user_data=index,
                    )
                    dpg.add_text("오류" if str(finding.get("severity", "")) == "error" else "경고")
                    dpg.add_text(str(finding.get("code", "")))
                    dpg.add_text(self._finding_location_text(finding))
                    dpg.add_text(str(finding.get("message", "")))

    def select_finding(self, index: int) -> None:
        self.selected_finding_index = index
        findings = (self.validation_result or {}).get("findings", [])
        if not (0 <= index < len(findings)):
            return
        finding = findings[index]
        location = finding.get("location")
        if location:
            self.jump_to_location(location)
        self._set_active_action(self._recommended_action(finding))
        self.refresh_context_summary()
        self.apply_editor_mode()
        self.refresh_finding_table()

    def jump_to_location(self, location: dict[str, Any]) -> None:
        tab = location.get("tab")
        if tab == "record":
            self.selected_record_table = location.get("table", "batter")
            self.selected_record_side = location.get("side", "home")
            self.selected_record_row = location.get("row_index")
            self._set_value_if_exists(self._t("record_scope"), self._record_scope_label(self.selected_record_table, self.selected_record_side))
            self._set_value_if_exists(self._t("editor_mode"), EDITOR_MODES[1])
            self._set_tab_value(self._t("detail_tabs"), self._t("record_tab"))
            self.refresh_record_table()
            self.populate_record_editor()
        elif tab == "relay":
            self.selected_block_ref = (location.get("group_index"), location.get("block_index"))
            if location.get("event_index") is not None:
                self.selected_event_ref = (*self.selected_block_ref, location.get("event_index"))
            self._set_tab_value(self._t("detail_tabs"), self._t("relay_tab"))
            self.refresh_relay_tree()
            self.refresh_relay_event_table()
            self.populate_block_editor()
            self.populate_event_editor()
            self.populate_structured_editors()
        self.refresh_context_summary()
        self.refresh_selection_summary()

    def refresh_diff_text(self) -> None:
        diff_text = self.session.build_diff() if self.session else ""
        self._set_value_if_exists(self._t("diff_text"), diff_text or "(no diff)")

    def refresh_history_text(self) -> None:
        if not self.session:
            self._set_value_if_exists(self._t("history_text"), "")
            return
        lines = []
        for entry in self.session.history_entries[-50:]:
            changed = ", ".join(entry.changed_paths[:6])
            if len(entry.changed_paths) > 6:
                changed += ", ..."
            lines.append(f"[{entry.timestamp}] {entry.action} | {changed}")
        backups = self.session.list_backups()
        if backups:
            lines.append("")
            lines.append("Backups:")
            lines.extend(backup.as_posix() for backup in backups[-10:])
        self._set_value_if_exists(self._t("history_text"), "\n".join(lines))

    def refresh_auto_preview_text(self) -> None:
        if not self.session:
            self._set_value_if_exists(self._t("auto_preview_text"), "")
            self._set_value_if_exists(self._t("basic_auto_preview_text"), "")
            return
        if self.auto_preview is None:
            try:
                self.auto_preview = self.session.preview_auto_rebuild()
            except Exception:
                self.auto_preview = None
        if not self.auto_preview:
            self._set_value_if_exists(self._t("auto_preview_text"), "")
            self._set_value_if_exists(self._t("basic_auto_preview_text"), "")
            return
        pa_lines = []
        for pa in self.auto_preview.get("plate_appearances", [])[:20]:
            result_text = pa.result_text or "(partial)"
            pa_lines.append(
                f"{pa.group_index}:{pa.block_index} {pa.start_index}-{pa.end_index} "
                f"{pa.batter_name or pa.batter_id or '-'} -> {result_text}"
            )
        changed_paths = self.auto_preview.get("changed_paths", [])
        lines = [
            f"changed_paths={len(changed_paths)}",
            "",
            self.auto_preview.get("diff") or "(no auto rebuild diff)",
        ]
        if pa_lines:
            lines.extend(["", "타석 미리보기:"])
            lines.extend(pa_lines)
        preview_text = "\n".join(lines)
        self._set_value_if_exists(self._t("auto_preview_text"), preview_text)
        self._set_value_if_exists(self._t("basic_auto_preview_text"), preview_text)

    def refresh_auto_preview(self) -> None:
        session = self._session_required()
        if session is None:
            return
        self.auto_preview = session.preview_auto_rebuild()
        self.refresh_auto_preview_text()

    def apply_auto_rebuild(self) -> None:
        session = self._session_required()
        if session is None:
            return
        session.apply_auto_rebuild()
        self.auto_preview = None
        self.refresh_all_views()

    def save_current_file(self) -> None:
        session = self._session_required()
        if session is None:
            return
        try:
            result = session.save(action="save")
            self.refresh_all_views()
            self.state.set_status("info", "저장 완료", f"backup={result.get('backup_path') or 'new file'}", source="수정/보정")
        except Exception as exc:
            self.state.set_status("error", "저장 실패", "백업 생성 또는 저장 중 오류가 발생했습니다.", debug_detail=str(exc), source="수정/보정")

    def undo(self) -> None:
        session = self._session_required()
        if session and session.undo():
            self.refresh_all_views()

    def redo(self) -> None:
        session = self._session_required()
        if session and session.redo():
            self.refresh_all_views()

    def revert_session(self) -> None:
        session = self._session_required()
        if session is None:
            return
        session.revert_to_loaded()
        self.refresh_all_views()

    def restore_backup(self) -> None:
        session = self._session_required()
        if session is None:
            return
        restored = session.restore_latest_backup()
        self.refresh_all_views()
        if restored:
            self.state.set_status("info", "백업 복원 완료", restored.as_posix(), source="수정/보정")
        else:
            self.state.set_status("warn", "백업 없음", "복원할 백업 파일이 아직 없습니다.", source="수정/보정")

    def apply_responsive_layout(self, content_w: int, content_h: int) -> None:
        available_w = max(700, int(content_w) - 36)
        file_w = max(250, min(360, int(available_w * 0.24)))
        detail_w = max(400, min(560, int(available_w * 0.32)))
        center_w = max(500, available_w - file_w - detail_w - 30)
        body_h = max(460, int(content_h) - 120)
        relay_h = max(220, body_h - 260)

        self.header_toolbar.set_width(available_w)
        self.loaded_toolbar.set_width(available_w)
        self.status_toolbar.set_width(available_w)
        if dpg.does_item_exist(self._t("root_dir")):
            dpg.configure_item(self._t("root_dir"), width=max(220, min(420, int(available_w * 0.3))))
        if dpg.does_item_exist(self._t("search")):
            dpg.configure_item(self._t("search"), width=max(160, min(280, int(available_w * 0.2))))

        for tag, width in ((self._t("file_panel"), file_w), (self._t("center_panel"), center_w), (self._t("detail_panel"), detail_w)):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, width=width, height=body_h)

        self._configure_detail_field_widths(detail_w)
        for tag in (
            self._t("game_info_table"),
            self._t("lineup_table"),
            self._t("record_table"),
            self._t("findings_table"),
            self._t("diff_text"),
            self._t("history_text"),
            self._t("auto_preview_text"),
            self._t("basic_auto_preview_text"),
        ):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, height=body_h - 90)
        if dpg.does_item_exist(self._t("context_summary_text")):
            dpg.configure_item(self._t("context_summary_text"), height=120)
        if dpg.does_item_exist(self._t("context_flow_text")):
            dpg.configure_item(self._t("context_flow_text"), height=110)
        if dpg.does_item_exist(self._t("relay_tree")):
            dpg.configure_item(self._t("relay_tree"), width=max(180, int(center_w * 0.32)), height=relay_h)
        if dpg.does_item_exist(self._t("relay_events")):
            dpg.configure_item(self._t("relay_events"), width=max(260, center_w - int(center_w * 0.32) - 20), height=relay_h)

    def build(self, parent: str) -> None:
        with dpg.tab(label="수정/보정", parent=parent):
            header_row = self.header_toolbar.build()
            dpg.add_text("루트 경로", parent=header_row)
            dpg.add_input_text(tag=self._t("root_dir"), width=320, default_value=self.state.default_data_dir, parent=header_row)
            dpg.add_text("검색", parent=header_row)
            dpg.add_input_text(tag=self._t("search"), width=220, parent=header_row, callback=lambda: self.refresh_file_list())
            with dpg.group(horizontal=True, parent=header_row):
                dpg.add_button(label="목록 새로고침", callback=lambda: self.refresh_file_list())
                dpg.add_button(label="파일 열기", callback=lambda: self.load_selected_file())
                dpg.add_button(label="저장", callback=lambda: self.save_current_file())
                dpg.add_button(label="실행 취소", callback=lambda: self.undo())
                dpg.add_button(label="다시 실행", callback=lambda: self.redo())
                dpg.add_button(label="검증", callback=lambda: self.run_validation())
                dpg.add_button(label="세션 되돌리기", callback=lambda: self.revert_session())
                dpg.add_button(label="백업 복원", callback=lambda: self.restore_backup())

            loaded_row = self.loaded_toolbar.build()
            with dpg.group(horizontal=True, parent=loaded_row):
                dpg.add_text("불러온 파일")
                dpg.add_text("-", tag=self._t("loaded_file"))
            status_row = self.status_toolbar.build()
            with dpg.group(horizontal=True, parent=status_row):
                dpg.add_text("저장 상태")
                dpg.add_text("-", tag=self._t("save_status"))
                dpg.add_spacer(width=12)
                dpg.add_text("선택")
                dpg.add_text("선택된 항목 없음", tag=self._t("selection_summary"))

            with dpg.group(horizontal=True, tag=self._t("workspace")):
                with dpg.child_window(tag=self._t("file_panel"), width=260, height=540, border=True):
                    dpg.add_text("경기 파일")
                    dpg.add_text("0 files", tag=self._t("file_count"))
                    dpg.add_listbox(tag=self._t("file_list"), items=[], width=-1, num_items=24)
                    dpg.add_separator()
                    dpg.add_text("문제 목록")
                    dpg.add_text("-", tag=self._t("finding_summary"))
                    with dpg.group(horizontal=True):
                        dpg.add_combo(
                            tag=self._t("finding_type_filter"),
                            items=list(FINDING_TYPE_GROUPS),
                            default_value="전체",
                            width=110,
                            callback=lambda: self.refresh_finding_table(),
                        )
                        dpg.add_combo(
                            tag=self._t("finding_inning_filter"),
                            items=["전체"],
                            default_value="전체",
                            width=70,
                            callback=lambda: self.refresh_finding_table(),
                        )
                        dpg.add_combo(
                            tag=self._t("finding_half_filter"),
                            items=["전체", "초", "말"],
                            default_value="전체",
                            width=70,
                            callback=lambda: self.refresh_finding_table(),
                        )
                    dpg.add_input_text(
                        tag=self._t("finding_query"),
                        hint="문제 유형 / 문구 검색",
                        width=-1,
                        callback=lambda: self.refresh_finding_table(),
                    )
                    with dpg.child_window(tag=self._t("findings_table"), width=-1, height=220, border=True):
                        pass
                    with dpg.collapsing_header(label="검증 변화", default_open=False):
                        dpg.add_input_text(tag=self._t("finding_delta"), multiline=True, readonly=True, width=-1, height=110)

                with dpg.child_window(tag=self._t("center_panel"), width=840, height=540, border=True):
                    with dpg.tab_bar(tag=self._t("detail_tabs")):
                        with dpg.tab(tag=self._t("game_info_tab"), label="경기 정보"):
                            dpg.add_button(label="경기 정보 적용", callback=lambda: self.apply_game_info_editor())
                            with dpg.child_window(tag=self._t("game_info_table"), width=-1, height=440):
                                pass

                        with dpg.tab(tag=self._t("lineup_tab"), label="라인업"):
                            with dpg.group(horizontal=True):
                                dpg.add_combo(
                                    tag=self._t("lineup_section"),
                                    items=[LINEUP_SECTION_LABELS[key] for key in LINEUP_SECTIONS],
                                    default_value=LINEUP_SECTION_LABELS[self.selected_lineup_section],
                                    callback=lambda: self.on_lineup_section_change(),
                                    width=180,
                                )
                                dpg.add_button(label="행 추가", callback=lambda: self.add_lineup_row())
                                dpg.add_button(label="행 삭제", callback=lambda: self.delete_lineup_row())
                                dpg.add_button(label="행 적용", callback=lambda: self.apply_lineup_editor())
                                dpg.add_button(label="선발 검증", callback=lambda: self.run_validation())
                            with dpg.child_window(tag=self._t("lineup_table"), width=-1, height=440):
                                pass

                        with dpg.tab(tag=self._t("relay_tab"), label="중계"):
                            dpg.add_text("경기 흐름 / 선택 맥락")
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="이전 이벤트", callback=lambda: self.select_relative_event(-1))
                                dpg.add_button(label="다음 이벤트", callback=lambda: self.select_relative_event(1))
                            dpg.add_input_text(tag=self._t("context_summary_text"), multiline=True, readonly=True, width=-1, height=120)
                            dpg.add_input_text(tag=self._t("context_flow_text"), multiline=True, readonly=True, width=-1, height=110)
                            with dpg.group(horizontal=True):
                                dpg.add_combo(tag=self._t("relay_view_mode"), items=list(RELAY_VIEW_MODE_LABELS.values()), default_value=RELAY_VIEW_MODE_LABELS["Event"], width=80, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_input_text(tag=self._t("relay_query"), hint="문구 / 선수 / ptsPitchId", width=220, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_combo(tag=self._t("relay_inning_filter"), items=[RELAY_ALL_FILTER_LABEL], default_value=RELAY_ALL_FILTER_LABEL, width=90, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_combo(tag=self._t("relay_half_filter"), items=list(RELAY_HALF_FILTER_LABELS.values()), default_value=RELAY_HALF_FILTER_LABELS["All"], width=90, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_combo(tag=self._t("relay_type_filter"), items=[RELAY_ALL_FILTER_LABEL], default_value=RELAY_ALL_FILTER_LABEL, width=90, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_checkbox(tag=self._t("relay_errors_only"), label="오류만", callback=lambda: self.refresh_relay_event_table())
                                dpg.add_checkbox(tag=self._t("relay_duplicates_only"), label="중복만", callback=lambda: self.refresh_relay_event_table())
                                dpg.add_checkbox(tag=self._t("relay_missing_only"), label="누락 의심만", callback=lambda: self.refresh_relay_event_table())
                            with dpg.group(horizontal=True):
                                with dpg.child_window(tag=self._t("relay_tree"), width=260, height=360, border=True):
                                    pass
                                with dpg.child_window(tag=self._t("relay_events"), width=-1, height=360, border=True):
                                    pass
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="블록 추가", callback=lambda: self.add_block())
                                dpg.add_button(label="블록 삭제", callback=lambda: self.delete_block())
                                dpg.add_button(label="블록 위로", callback=lambda: self.move_block(-1))
                                dpg.add_button(label="블록 아래로", callback=lambda: self.move_block(+1))
                                dpg.add_button(label="이벤트 추가", callback=lambda: self.add_event())
                                dpg.add_button(label="이벤트 복제", callback=lambda: self.duplicate_event())
                                dpg.add_button(label="이벤트 삭제", callback=lambda: self.delete_event())
                                dpg.add_button(label="이벤트 위로", callback=lambda: self.move_event(-1))
                                dpg.add_button(label="이벤트 아래로", callback=lambda: self.move_event(+1))
                                dpg.add_button(label="seq 재정렬", callback=lambda: self.renumber_seqno())
                                dpg.add_button(label="빈 state 채우기", callback=lambda: self.fill_missing_state())
                                dpg.add_button(label="미리보기", callback=lambda: self.refresh_auto_preview())
                                dpg.add_button(label="자동 재계산", callback=lambda: self.apply_auto_rebuild())

                        with dpg.tab(tag=self._t("record_tab"), label="기록"):
                            with dpg.group(horizontal=True):
                                dpg.add_combo(tag=self._t("record_scope"), items=[RECORD_SCOPE_LABELS[item] for item in RECORD_SCOPE_ITEMS], default_value=RECORD_SCOPE_LABELS["batter:home"], width=180, callback=lambda: self.on_record_scope_change())
                                dpg.add_button(label="행 추가", callback=lambda: self.add_record_row())
                                dpg.add_button(label="행 삭제", callback=lambda: self.delete_record_row())
                                dpg.add_button(label="행 적용", callback=lambda: self.apply_record_editor())
                                dpg.add_button(label="타자 합계 재계산", callback=lambda: self.recalc_record_totals())
                            with dpg.child_window(tag=self._t("record_table"), width=-1, height=440):
                                pass

                        with dpg.tab(tag=self._t("validation_tab"), label="검증 결과"):
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="검증 실행", callback=lambda: self.run_validation())
                                dpg.add_text("문제 목록은 좌측 패널에서 확인하세요.")
                            with dpg.child_window(tag=self._t("validation_placeholder"), width=-1, height=120):
                                pass
                            dpg.add_input_text(tag=self._t("validation_hint_text"), multiline=True, readonly=True, width=-1, height=120, default_value="좌측 패널의 문제 목록이 기본 진입점입니다.\n고급 모드에서는 이 탭에서 검증을 다시 실행할 수 있습니다.")

                        with dpg.tab(tag=self._t("diff_tab"), label="차이점"):
                            dpg.add_input_text(tag=self._t("diff_text"), multiline=True, readonly=True, width=-1, height=440)

                        with dpg.tab(tag=self._t("history_tab"), label="변경 이력"):
                            dpg.add_input_text(tag=self._t("history_text"), multiline=True, readonly=True, width=-1, height=440)

                        with dpg.tab(tag=self._t("auto_preview_tab"), label="자동 재계산 미리보기"):
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="미리보기 갱신", callback=lambda: self.refresh_auto_preview())
                                dpg.add_button(label="자동 재계산 적용", callback=lambda: self.apply_auto_rebuild())
                            dpg.add_input_text(tag=self._t("auto_preview_text"), multiline=True, readonly=True, width=-1, height=440)

                with dpg.child_window(tag=self._t("detail_panel"), width=480, height=540, border=True):
                    dpg.add_text("액션 패널")
                    with dpg.group(horizontal=True):
                        dpg.add_text("작업 모드")
                        dpg.add_combo(
                            tag=self._t("editor_mode"),
                            items=EDITOR_MODES,
                            default_value=EDITOR_MODES[0],
                            width=140,
                            callback=lambda: self.apply_editor_mode(),
                        )
                    dpg.add_text("-", tag=self._t("mode_help_text"))
                    dpg.add_text("-", tag=self._t("action_recommendation_text"))
                    with dpg.group(tag=self._t("basic_mode_panel")):
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="선택 기반 입력", callback=lambda: self.populate_structured_editors())
                            dpg.add_button(label="검증 갱신", callback=lambda: self.run_validation())
                            dpg.add_button(label="저장", callback=lambda: self.save_current_file())
                        dpg.add_combo(
                            tag=self._t("action_selector"),
                            items=[ACTION_LABELS[key] for key in ("add", "missing_pa", "meaning", "split_merge", "preview")],
                            default_value=ACTION_LABELS["meaning"],
                            width=-1,
                            callback=lambda: self.refresh_action_sections(),
                        )
                    with dpg.group(tag=self._t("advanced_mode_panel"), show=False):
                        dpg.add_text("고급 편집 섹션")
                    dpg.add_separator(parent=self._t("advanced_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_game_info"), label="경기 정보 편집기", default_open=False, parent=self._t("advanced_mode_panel")):
                        for field in GAME_INFO_FIELDS:
                            if field in BOOLEAN_GAME_INFO_FIELDS:
                                self._add_labeled_checkbox(self._t(f"game_info_{field}"), field)
                            else:
                                self._add_labeled_input_text(self._t(f"game_info_{field}"), field)
                    dpg.add_separator(parent=self._t("advanced_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_lineup_row"), label="라인업 행 편집기", default_open=False, parent=self._t("advanced_mode_panel")):
                        for field in LINEUP_FIELDS:
                            self._add_labeled_input_text(self._t(f"lineup_{field}"), field)
                    dpg.add_separator(parent=self._t("advanced_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_relay_block"), label="중계 블록 편집기", default_open=False, parent=self._t("advanced_mode_panel")):
                        for field in BLOCK_FIELDS:
                            self._add_labeled_input_text(self._t(f"block_{field}"), field)
                        for field in ("homeTeamWinRate", "awayTeamWinRate", "wpaByPlate"):
                            self._add_labeled_input_text(self._t(f"metric_{field}"), f"metric.{field}")
                        dpg.add_button(label="블록 적용", callback=lambda: self.apply_block_editor())
                    dpg.add_separator(parent=self._t("advanced_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_relay_event"), label="중계 이벤트 편집기", default_open=False, parent=self._t("advanced_mode_panel")):
                        for field in EVENT_FIELDS:
                            if field == "text":
                                self._add_labeled_input_text(self._t(f"event_{field}"), field, multiline=True, height=90)
                            else:
                                self._add_labeled_input_text(self._t(f"event_{field}"), field)
                        self._add_labeled_input_text(self._t("event_batterRecord_pcode"), "batterRecord.pcode")
                        dpg.add_text("currentGameState")
                        for field in CURRENT_GAME_STATE_FIELDS:
                            if field in BASE_STATE_FIELDS:
                                self._add_labeled_checkbox(self._t(f"state_{field}"), field)
                            else:
                                self._add_labeled_input_text(self._t(f"state_{field}"), field)
                        dpg.add_text("playerChange")
                        self._add_labeled_input_text(self._t("change_type"), "type")
                        self._add_labeled_input_text(self._t("change_outPlayerTurn"), "outPlayerTurn")
                        for side in ("inPlayer", "outPlayer"):
                            dpg.add_text(side)
                            for field in PLAYER_CHANGE_PLAYER_FIELDS:
                                self._add_labeled_input_text(self._t(f"{side}_{field}"), f"{side}.{field}")
                        dpg.add_button(label="이벤트 적용", callback=lambda: self.apply_event_editor())
                    dpg.add_separator(parent=self._t("advanced_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_pa_split_merge_advanced"), label="타석 분리 / 병합", default_open=False, parent=self._t("advanced_mode_panel")):
                        dpg.add_text("고급 분리")
                        for field in ("first_batter_id", "first_batter_name", "first_detail", "first_text", "second_batter_id", "second_batter_name", "second_detail", "second_text"):
                            self._add_labeled_input_text(self._t(f"split_{field}"), field)
                        self._add_labeled_combo(
                            self._t("split_first_result_type"),
                            "first_result_type",
                            items=[RESULT_TYPE_LABELS[key] for key in RESULT_TYPES],
                            default_value=RESULT_TYPE_LABELS["strikeout"],
                        )
                        self._add_labeled_combo(
                            self._t("split_second_result_type"),
                            "second_result_type",
                            items=[RESULT_TYPE_LABELS[key] for key in RESULT_TYPES],
                            default_value=RESULT_TYPE_LABELS["double"],
                        )
                        self._add_runner_move_editor("split_first", count=3, title_prefix="첫 번째 타석 주자")
                        self._add_runner_move_editor("split_second", count=3, title_prefix="두 번째 타석 주자")
                        dpg.add_button(label="고급 타석 분리 적용", callback=lambda: self.split_selected_plate_appearance_advanced())
                        dpg.add_separator()
                        dpg.add_text("병합")
                        self._add_labeled_input_text(self._t("merge_batter_id"), "merged_batter_id")
                        self._add_labeled_input_text(self._t("merge_batter_name"), "merged_batter_name")
                        dpg.add_button(label="이전 타석과 병합", callback=lambda: self.merge_selected_plate_appearance())
                    dpg.add_separator(parent=self._t("basic_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_structured_add"), label="이벤트 추가", default_open=True, parent=self._t("basic_mode_panel")):
                        self._add_labeled_combo(
                            self._t("add_insert_mode"),
                            "삽입 위치",
                            items=list(INSERT_MODE_LABELS.values()),
                            default_value=INSERT_MODE_LABELS["after"],
                            callback=lambda: self.refresh_add_action_form(),
                        )
                        self._add_labeled_combo(
                            self._t("add_template_type"),
                            "이벤트 종류",
                            items=[ADD_TEMPLATE_LABELS[key] for key in BASIC_ADD_TEMPLATE_TYPES],
                            default_value=ADD_TEMPLATE_LABELS["pitch"],
                            callback=lambda: self.refresh_add_action_form(),
                        )
                        dpg.add_text("-", tag=self._t("add_action_help_text"), wrap=0)
                        dpg.add_input_text(tag=self._t("add_context_hint"), multiline=True, readonly=True, width=-1, height=110)
                        with dpg.group(tag=self._t("add_internal_defaults"), show=False):
                            for field in ("batter_id", "batter_name", "pitcher_id", "pitch_result", "pitch_num"):
                                dpg.add_input_text(tag=self._t(f"add_{field}"))
                        with dpg.group(tag=self._t("add_pitch_fields")):
                            self._add_labeled_combo(
                                self._t("add_pitch_result_display"),
                                "투구 결과",
                                items=list(PITCH_RESULT_LABELS.values()),
                                default_value=PITCH_RESULT_LABELS[""],
                                callback=lambda: self.refresh_add_action_form(),
                            )
                            self._add_labeled_input_text(self._t("add_pts_pitch_id"), "원본 pitch id (선택)")
                        with dpg.group(tag=self._t("add_bat_result_fields"), show=False):
                            self._add_labeled_combo(
                                self._t("add_result_type"),
                                "결과 유형",
                                items=[RESULT_TYPE_LABELS[key] for key in RESULT_TYPES],
                                default_value=RESULT_TYPE_LABELS["out"],
                            )
                            self._add_labeled_input_text(self._t("add_detail"), "결과 설명 (선택)")
                        dpg.add_text("표시 문구 / 메모 (선택)", tag=self._t("add_text_label"))
                        with dpg.group(horizontal=True):
                            dpg.add_input_text(tag=self._t("add_text"), multiline=True, width=-70, height=90)
                            dpg.add_button(
                                label="입력",
                                width=56,
                                callback=lambda: self._open_native_text_dialog(self._t("add_text"), "이벤트 문구", True),
                            )
                        with dpg.group(tag=self._t("add_runner_move_section"), show=False):
                            dpg.add_text("주자 이동 (필요 시)")
                            self._add_runner_move_editor("add", count=3, title_prefix="주자")
                        dpg.add_button(label="이 이벤트 추가", callback=lambda: self.insert_structured_event())
                    dpg.add_separator(parent=self._t("basic_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_missing_pa"), label="누락 타석 복구", default_open=True, parent=self._t("basic_mode_panel")):
                        self._add_labeled_combo(
                            self._t("pa_insert_mode"),
                            "삽입 위치",
                            items=list(INSERT_MODE_LABELS.values()),
                            default_value=INSERT_MODE_LABELS["before"],
                            callback=lambda: self.populate_structured_editors(),
                        )
                        for field in ("batter_id", "batter_name", "pitcher_id", "detail", "result_text", "pitch_result", "pitch_num", "pts_pitch_id"):
                            self._add_labeled_input_text(self._t(f"pa_{field}"), field)
                        self._add_labeled_combo(
                            self._t("pa_result_type"),
                            "결과 유형",
                            items=[RESULT_TYPE_LABELS[key] for key in RESULT_TYPES],
                            default_value=RESULT_TYPE_LABELS["single"],
                        )
                        self._add_pa_pitch_editor("pa", count=5)
                        self._add_runner_move_editor("pa", count=3)
                        dpg.add_button(label="누락 타석 삽입", callback=lambda: self.insert_missing_plate_appearance())
                    dpg.add_separator(parent=self._t("basic_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_meaning_edit"), label="결과 의미 수정", default_open=True, parent=self._t("basic_mode_panel")):
                        for field in ("batter_id", "batter_name", "pitcher_id", "detail", "text", "pitch_result", "pitch_num", "pts_pitch_id"):
                            self._add_labeled_input_text(self._t(f"meaning_{field}"), field)
                        self._add_labeled_combo(
                            self._t("meaning_result_type"),
                            "결과 유형",
                            items=[RESULT_TYPE_LABELS[key] for key in RESULT_TYPES],
                            default_value=RESULT_TYPE_LABELS["double"],
                        )
                        self._add_labeled_checkbox(self._t("meaning_replace_runner_events"), "뒤따르는 주자 이벤트 다시 구성", default_value=True)
                        self._add_runner_move_editor("meaning", count=3)
                        dpg.add_button(label="결과 의미 수정", callback=lambda: self.apply_meaning_edit())
                    dpg.add_separator(parent=self._t("basic_mode_panel"))
                    with dpg.collapsing_header(tag=self._t("section_pa_split_merge"), label="타석 분리 / 병합", default_open=False, parent=self._t("basic_mode_panel")):
                        dpg.add_text("타석 분리")
                        dpg.add_input_text(tag=self._t("split_basic_summary_text"), multiline=True, readonly=True, width=-1, height=95)
                        self._add_labeled_combo(
                            self._t("split_basic_batter"),
                            "새 타자 선택",
                            items=[],
                            default_value="",
                            callback=lambda: self.refresh_basic_split_card(preview=True),
                        )
                        self._add_labeled_checkbox(
                            self._t("split_basic_auto_intro"),
                            "새 타석 intro 이벤트 자동 삽입",
                            default_value=True,
                            callback=lambda: self.refresh_basic_split_card(preview=True),
                        )
                        dpg.add_text("이전 타석 종료 이벤트가 앞쪽에 없으면 기본 모드 분리는 차단됩니다.", wrap=0)
                        dpg.add_text("-", tag=self._t("split_basic_status_text"), wrap=0)
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="분리 미리보기", callback=lambda: self.preview_split_from_selected_event())
                            dpg.add_button(label="선택 이벤트부터 분리", callback=lambda: self.split_selected_plate_appearance_basic())
                        dpg.add_input_text(tag=self._t("split_basic_preview_text"), multiline=True, readonly=True, width=-1, height=120)
                        dpg.add_separator()
                        dpg.add_text("타석 병합")
                        dpg.add_text("현재 선택 타석을 이전 타석과 병합합니다. 세부 타자 지정은 고급 모드에서만 제공합니다.", wrap=0)
                        dpg.add_button(label="이전 타석과 병합", callback=lambda: self.merge_selected_plate_appearance())
                    dpg.add_separator(parent=self._t("basic_mode_panel"))
                    with dpg.group(tag=self._t("basic_preview_panel"), parent=self._t("basic_mode_panel")):
                        dpg.add_text("자동 재계산 미리보기")
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="미리보기 갱신", callback=lambda: self.refresh_auto_preview())
                            dpg.add_button(label="자동 재계산 적용", callback=lambda: self.apply_auto_rebuild())
                            dpg.add_button(label="실행 취소", callback=lambda: self.undo())
                            dpg.add_button(label="다시 실행", callback=lambda: self.redo())
                        dpg.add_input_text(tag=self._t("basic_auto_preview_text"), multiline=True, readonly=True, width=-1, height=180)
                    dpg.add_separator(parent=self._t("advanced_mode_panel"))
                    with dpg.group(tag=self._t("record_batter_editor_group"), parent=self._t("advanced_mode_panel")):
                        dpg.add_text("타자 기록 행")
                        for field in RECORD_BATTER_FIELDS:
                            self._add_labeled_input_text(self._t(f"record_batter_{field}"), field)
                    with dpg.group(tag=self._t("record_pitcher_editor_group"), show=False, parent=self._t("advanced_mode_panel")):
                        dpg.add_text("투수 기록 행")
                        for field in RECORD_PITCHER_FIELDS:
                            self._add_labeled_input_text(self._t(f"record_pitcher_{field}"), field)
                    dpg.add_separator(parent=self._t("advanced_mode_panel"))
                    with dpg.group(tag=self._t("record_totals_section"), parent=self._t("advanced_mode_panel")):
                        dpg.add_text("타자 기록 합계")
                        self._add_labeled_combo(self._t("record_total_side"), "구분", items=list(SIDE_LABELS.values()), default_value=SIDE_LABELS["home"])
                        for field in RECORD_BATTER_TOTAL_FIELDS:
                            self._add_labeled_input_text(self._t(f"record_total_{field}"), f"total.{field}")
                        dpg.add_button(label="합계 수동 적용", callback=lambda: self.apply_record_total_editor())

        self.refresh_file_list()
        self.refresh_all_views()
        self._configure_detail_field_widths(480)
