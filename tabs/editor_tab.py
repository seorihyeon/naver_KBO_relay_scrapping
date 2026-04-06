from __future__ import annotations

from pathlib import Path
from typing import Any

import dearpygui.dearpygui as dpg

from dpg_utils import prompt_native_text
from src.kbo_ingest.correction_engine import (
    EVENT_TEMPLATE_TYPES,
    RESULT_TYPES,
    RUNNER_BASE_CHOICES,
    build_player_index,
    parse_result_type,
    summarize_plate_appearances,
)
from src.kbo_ingest.editor_core import GameEditorSession
from src.kbo_ingest.game_json import CURRENT_GAME_STATE_FIELDS

from .shared_state import AppState


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


class CorrectionEditorTab:
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
        self._set_value_if_exists(self._t("file_count"), f"{len(labels)} files")

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
        updated = prompt_native_text(title=f"{label} input", initial_value=current_value, multiline=multiline)
        if updated is not None:
            self._set_value_if_exists(tag, updated)

    def _add_labeled_input_text(self, tag: str, label: str, *, multiline: bool = False, height: int = 0) -> None:
        dpg.add_text(label)
        show_helper = multiline or any(token in label.lower() for token in ("name", "detail", "text", "memo", "note"))
        if show_helper:
            with dpg.group(horizontal=True):
                kwargs: dict[str, Any] = {"tag": tag, "label": "", "width": -70}
                if multiline:
                    kwargs["multiline"] = True
                    kwargs["height"] = height or 90
                dpg.add_input_text(**kwargs)
                dpg.add_button(
                    label="IME",
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

    def _add_labeled_checkbox(self, tag: str, label: str, *, default_value: bool = False) -> None:
        dpg.add_text(label)
        dpg.add_checkbox(tag=tag, label="", default_value=default_value)

    def _add_runner_move_editor(self, prefix: str, *, count: int = 3, title_prefix: str = "runner") -> None:
        for index in range(1, count + 1):
            dpg.add_separator()
            dpg.add_text(f"{title_prefix} {index}")
            self._add_labeled_combo(self._t(f"{prefix}_runner_{index}_start"), "start", items=RUNNER_BASE_CHOICES, default_value="")
            self._add_labeled_combo(self._t(f"{prefix}_runner_{index}_end"), "end", items=RUNNER_BASE_CHOICES, default_value="")
            self._add_labeled_input_text(self._t(f"{prefix}_runner_{index}_id"), "runner_id")
            self._add_labeled_input_text(self._t(f"{prefix}_runner_{index}_name"), "runner_name")

    def _add_pa_pitch_editor(self, prefix: str, *, count: int = 5) -> None:
        for index in range(1, count + 1):
            dpg.add_separator()
            dpg.add_text(f"pitch {index}")
            self._add_labeled_input_text(self._t(f"{prefix}_pitch_{index}_result"), "result")
            self._add_labeled_input_text(self._t(f"{prefix}_pitch_{index}_num"), "pitch_num")
            self._add_labeled_input_text(self._t(f"{prefix}_pitch_{index}_id"), "pts_pitch_id")
            self._add_labeled_input_text(self._t(f"{prefix}_pitch_{index}_text"), "text")

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

        for prefix in ("add", "meaning"):
            self._set_value_if_exists(self._t(f"{prefix}_batter_id"), batter_id or "")
            self._set_value_if_exists(self._t(f"{prefix}_batter_name"), batter_name or "")
            self._set_value_if_exists(self._t(f"{prefix}_pitcher_id"), pitcher_id or "")
            self._set_value_if_exists(self._t(f"{prefix}_detail"), detail_text)
            self._set_value_if_exists(self._t(f"{prefix}_text"), event_text)
            self._set_value_if_exists(self._t(f"{prefix}_pitch_result"), pitch_result or "")
            self._set_value_if_exists(self._t(f"{prefix}_pitch_num"), "" if pitch_num in (None, "") else str(pitch_num))
            self._set_value_if_exists(self._t(f"{prefix}_pts_pitch_id"), pts_pitch_id or "")
            self._set_value_if_exists(self._t(f"{prefix}_result_type"), result_type)
            self._clear_runner_move_inputs(prefix)

        pa_insert_mode = str(dpg.get_value(self._t("pa_insert_mode")) or "before") if dpg.does_item_exist(self._t("pa_insert_mode")) else "before"
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
        self._set_value_if_exists(self._t("split_first_result_type"), "out")
        self._clear_runner_move_inputs("split_first")
        self._set_value_if_exists(self._t("split_second_batter_id"), split_second_batter_id or "")
        self._set_value_if_exists(self._t("split_second_batter_name"), split_second_batter_name or "")
        self._set_value_if_exists(self._t("split_second_detail"), detail_text)
        self._set_value_if_exists(self._t("split_second_text"), event_text)
        self._set_value_if_exists(self._t("split_second_result_type"), pa_summary.result_type if pa_summary and pa_summary.result_type else result_type)
        self._clear_runner_move_inputs("split_second")

        merge_batter_id = pa_summary.batter_id if pa_summary and pa_summary.batter_id else batter_id
        merge_batter_name = pa_summary.batter_name if pa_summary and pa_summary.batter_name else batter_name
        self._set_value_if_exists(self._t("merge_batter_id"), merge_batter_id or "")
        self._set_value_if_exists(self._t("merge_batter_name"), merge_batter_name or "")

    def refresh_context_summary(self) -> None:
        block = self._get_selected_block() or {}
        event = self._get_selected_event() or {}
        state = event.get("currentGameState") or {}
        inning = block.get("inn", "-")
        half = "Top" if str(block.get("homeOrAway", "0")) == "0" else "Bottom"
        batter_id = str(state.get("batter") or (event.get("batterRecord") or {}).get("pcode") or "").strip() or None
        pitcher_id = str(state.get("pitcher") or "").strip() or None
        batter_name = self._player_name_lookup(batter_id) or batter_id or "-"
        pitcher_name = self._player_name_lookup(pitcher_id) or pitcher_id or "-"
        balls = state.get("ball", 0)
        strikes = state.get("strike", 0)
        outs = state.get("out", 0)
        bases = f"{'1' if state.get('base1') else '-'}{'2' if state.get('base2') else '-'}{'3' if state.get('base3') else '-'}"
        score = f"{state.get('awayScore', 0)}:{state.get('homeScore', 0)}"
        event_ref = "-" if self.selected_event_ref is None else str(self.selected_event_ref[2])
        lines = [
            f"Inning: {inning} {half} | Event: {event_ref}",
            f"Batter: {batter_name}",
            f"Pitcher: {pitcher_name}",
            f"Count: B{balls}-S{strikes}-O{outs} | Bases: {bases} | Score A:H {score}",
            "",
            str(event.get("text") or "(no selected event)"),
        ]
        self._set_value_if_exists(self._t("context_summary_text"), "\n".join(lines))

    def apply_editor_mode(self) -> None:
        mode = str(dpg.get_value(self._t("editor_mode")) or "Quick Fix") if dpg.does_item_exist(self._t("editor_mode")) else "Quick Fix"
        sections = {
            "Quick Fix": [
                self._t("section_structured_add"),
                self._t("section_missing_pa"),
                self._t("section_meaning_edit"),
                self._t("section_pa_split_merge"),
            ],
            "Relay Raw": [
                self._t("section_relay_block"),
                self._t("section_relay_event"),
            ],
            "Roster/Game": [
                self._t("section_game_info"),
                self._t("section_lineup_row"),
            ],
            "Record": [
                self._t("record_totals_section"),
            ],
        }
        active_tags = set(sections.get(mode, sections["Quick Fix"]))
        for tag_list in sections.values():
            for tag in tag_list:
                self._toggle_group(tag, tag in active_tags)
        if mode == "Record":
            self._toggle_group(self._t("record_batter_editor_group"), self.selected_record_table == "batter")
            self._toggle_group(self._t("record_pitcher_editor_group"), self.selected_record_table == "pitcher")
        else:
            self._toggle_group(self._t("record_batter_editor_group"), False)
            self._toggle_group(self._t("record_pitcher_editor_group"), False)

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

        tags.extend(self._t(name) for name in ("add_template_type", "add_insert_mode", "add_result_type"))
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

    def refresh_all_views(self) -> None:
        self.auto_preview = None
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
            self._set_value_if_exists(self._t("loaded_file"), "No file loaded")
            self._set_value_if_exists(self._t("save_status"), "-")
            return
        self._set_value_if_exists(self._t("loaded_file"), self.session.path.as_posix())
        save_status = self.session.last_saved_at or "Not saved in this session"
        dirty = "modified" if self.session.has_unsaved_changes() else "clean"
        self._set_value_if_exists(self._t("save_status"), f"{save_status} | {dirty}")

    def refresh_selection_summary(self) -> None:
        parts = []
        if self.selected_game_info_key:
            parts.append(f"Game Info: {self.selected_game_info_key}")
        if self.selected_lineup_row is not None:
            parts.append(f"Lineup: {self.selected_lineup_section}[{self.selected_lineup_row}]")
        if self.selected_record_row is not None:
            parts.append(f"Record: {self.selected_record_table}.{self.selected_record_side}[{self.selected_record_row}]")
        if self.selected_block_ref is not None:
            parts.append(f"Relay block: {self.selected_block_ref[0]}:{self.selected_block_ref[1]}")
        if self.selected_event_ref is not None:
            parts.append(f"Relay event: {self.selected_event_ref[2]}")
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
                    dpg.add_text(self.selected_lineup_section)

    def select_lineup_row(self, row_index: int) -> None:
        self.selected_lineup_row = row_index
        self.populate_lineup_editor()
        self.refresh_lineup_table()
        self.refresh_selection_summary()

    def on_lineup_section_change(self) -> None:
        self.selected_lineup_section = dpg.get_value(self._t("lineup_section"))
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
        scope = dpg.get_value(self._t("record_scope"))
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
            self._set_value_if_exists(self._t("record_total_side"), total_side)
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
        side = str(dpg.get_value(self._t("record_total_side")) or "home")

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
            "inning": str(dpg.get_value(self._t("relay_inning_filter")) or "All"),
            "half": str(dpg.get_value(self._t("relay_half_filter")) or "All"),
            "type": str(dpg.get_value(self._t("relay_type_filter")) or "All"),
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
        inning_items = ["All"]
        type_items = ["All"]
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
        if filters["inning"] != "All" and str(block.get("inn", "")) != filters["inning"]:
            return False
        if filters["half"] != "All" and str(block.get("homeOrAway", "")) != ("0" if filters["half"] == "Top" else "1"):
            return False
        if filters["type"] != "All" and str(event.get("type", "")) != filters["type"]:
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
        self.refresh_selection_summary()

    def refresh_relay_event_table(self) -> None:
        self._clear_children(self._t("relay_events"))
        self._refresh_relay_filter_items()
        if not self.session or self.selected_block_ref is None:
            return
        block = self._get_selected_block()
        if not block:
            return
        view_mode = str(dpg.get_value(self._t("relay_view_mode")) or "Event") if dpg.does_item_exist(self._t("relay_view_mode")) else "Event"
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
            "result_type": str(dpg.get_value(self._t(f"{prefix}_result_type")) or "").strip() or None,
            "detail": self._input_text_value(self._t(f"{prefix}_detail")),
            "text": self._input_text_value(self._t(f"{prefix}_text")),
            "pitch_result": self._input_text_value(self._t(f"{prefix}_pitch_result")),
            "pitch_num": self._input_int_value(self._t(f"{prefix}_pitch_num")),
            "pts_pitch_id": self._input_text_value(self._t(f"{prefix}_pts_pitch_id")),
            "runner_moves": self._input_runner_moves(prefix),
        }

    def insert_structured_event(self) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        group_index, block_index = self.selected_block_ref
        template_type = str(dpg.get_value(self._t("add_template_type")) or "pitch")
        insert_mode = str(dpg.get_value(self._t("add_insert_mode")) or "after")
        if self.selected_event_ref is None:
            insert_at = 0
        elif insert_mode == "before":
            insert_at = self.selected_event_ref[2]
        else:
            insert_at = self.selected_event_ref[2] + 1
        inserted = session.insert_event_template(
            group_index=group_index,
            block_index=block_index,
            insert_at=insert_at,
            template_type=template_type,
            spec=self._semantic_spec_from_inputs("add"),
        )
        if inserted:
            self.selected_event_ref = (group_index, block_index, inserted[0])
        self.refresh_all_views()

    def insert_missing_plate_appearance(self) -> None:
        session = self._session_required()
        if session is None or self.selected_block_ref is None:
            return
        group_index, block_index = self.selected_block_ref
        insert_mode = str(dpg.get_value(self._t("pa_insert_mode")) or "before")
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

    def split_selected_plate_appearance(self) -> None:
        session = self._session_required()
        if session is None or self.selected_event_ref is None:
            return
        group_index, block_index, event_index = self.selected_event_ref
        spec = {
            "first_batter_id": self._input_text_value(self._t("split_first_batter_id")),
            "first_batter_name": self._input_text_value(self._t("split_first_batter_name")),
            "first_result_type": str(dpg.get_value(self._t("split_first_result_type")) or "").strip() or None,
            "first_detail": self._input_text_value(self._t("split_first_detail")),
            "first_text": self._input_text_value(self._t("split_first_text")),
            "first_runner_moves": self._input_runner_moves("split_first"),
            "second_batter_id": self._input_text_value(self._t("split_second_batter_id")),
            "second_batter_name": self._input_text_value(self._t("split_second_batter_name")),
            "second_result_type": str(dpg.get_value(self._t("split_second_result_type")) or "").strip() or None,
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
            merged_batter_id=self._input_text_value(self._t("merge_batter_id")),
            merged_batter_name=self._input_text_value(self._t("merge_batter_name")),
        )
        if next_index is not None:
            self.selected_event_ref = (group_index, block_index, next_index)
        self.refresh_all_views()

    def run_validation(self) -> None:
        session = self._session_required()
        if session is None:
            return
        previous_messages = {f"{item.get('code')}|{item.get('message')}" for item in (self.validation_result or {}).get("findings", [])}
        self.validation_result = session.validate()
        current_messages = {f"{item.get('code')}|{item.get('message')}" for item in (self.validation_result or {}).get("findings", [])}
        resolved = sorted(previous_messages - current_messages)
        added = sorted(current_messages - previous_messages)
        self.refresh_finding_table()
        self._set_value_if_exists(self._t("finding_summary"), f"errors={self.validation_result['error_count']} warnings={self.validation_result['warning_count']}")
        delta_lines = [f"resolved={len(resolved)}", f"new={len(added)}"]
        if resolved:
            delta_lines.extend(["", "Resolved:"])
            delta_lines.extend(resolved[:10])
        if added:
            delta_lines.extend(["", "New:"])
            delta_lines.extend(added[:10])
        self._set_value_if_exists(self._t("finding_delta"), "\n".join(delta_lines))
        self.state.set_status(
            "info" if self.validation_result["ok"] else "warn",
            "검증 실행 완료",
            f"errors={self.validation_result['error_count']} warnings={self.validation_result['warning_count']}",
            source="수정/보정",
        )

    def refresh_finding_table(self) -> None:
        self._clear_children(self._t("findings_table"))
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
            for label in ("#", "severity", "code", "message"):
                dpg.add_table_column(label=label)
            findings = (self.validation_result or {}).get("findings", [])
            for index, finding in enumerate(findings):
                with dpg.table_row():
                    dpg.add_selectable(
                        label=str(index),
                        default_value=index == self.selected_finding_index,
                        callback=lambda _s, _a, user_data: self.select_finding(user_data),
                        user_data=index,
                    )
                    dpg.add_text(str(finding.get("severity", "")))
                    dpg.add_text(str(finding.get("code", "")))
                    dpg.add_text(str(finding.get("message", "")))

    def select_finding(self, index: int) -> None:
        self.selected_finding_index = index
        findings = (self.validation_result or {}).get("findings", [])
        if not (0 <= index < len(findings)):
            return
        location = findings[index].get("location")
        if location:
            self.jump_to_location(location)
        self.refresh_finding_table()

    def jump_to_location(self, location: dict[str, Any]) -> None:
        tab = location.get("tab")
        if tab == "record":
            self.selected_record_table = location.get("table", "batter")
            self.selected_record_side = location.get("side", "home")
            self.selected_record_row = location.get("row_index")
            self._set_value_if_exists(self._t("record_scope"), f"{self.selected_record_table}:{self.selected_record_side}")
            dpg.set_value(self._t("detail_tabs"), self._t("record_tab"))
            self.refresh_record_table()
            self.populate_record_editor()
        elif tab == "relay":
            self.selected_block_ref = (location.get("group_index"), location.get("block_index"))
            if location.get("event_index") is not None:
                self.selected_event_ref = (*self.selected_block_ref, location.get("event_index"))
            dpg.set_value(self._t("detail_tabs"), self._t("relay_tab"))
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
            return
        if self.auto_preview is None:
            try:
                self.auto_preview = self.session.preview_auto_rebuild()
            except Exception:
                self.auto_preview = None
        if not self.auto_preview:
            self._set_value_if_exists(self._t("auto_preview_text"), "")
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
            lines.extend(["", "PA Preview:"])
            lines.extend(pa_lines)
        self._set_value_if_exists(self._t("auto_preview_text"), "\n".join(lines))

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
        file_w = max(220, min(320, int(content_w * 0.2)))
        detail_w = max(380, min(540, int(content_w * 0.32)))
        center_w = max(460, content_w - file_w - detail_w - 30)
        body_h = max(420, content_h - 60)
        relay_h = max(220, body_h - 110)

        for tag, width in ((self._t("file_panel"), file_w), (self._t("center_panel"), center_w), (self._t("detail_panel"), detail_w)):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, width=width, height=body_h)
        self._configure_detail_field_widths(detail_w)
        for tag in (self._t("game_info_table"), self._t("lineup_table"), self._t("record_table"), self._t("findings_table"), self._t("diff_text"), self._t("history_text"), self._t("auto_preview_text")):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, height=body_h - 90)
        if dpg.does_item_exist(self._t("relay_tree")):
            dpg.configure_item(self._t("relay_tree"), width=max(180, int(center_w * 0.32)), height=relay_h)
        if dpg.does_item_exist(self._t("relay_events")):
            dpg.configure_item(self._t("relay_events"), width=max(260, center_w - int(center_w * 0.32) - 20), height=relay_h)

    def build(self, parent: str) -> None:
        with dpg.tab(label="수정/보정", parent=parent):
            with dpg.group(horizontal=True):
                dpg.add_text("Root")
                dpg.add_input_text(tag=self._t("root_dir"), width=320, default_value=self.state.default_data_dir)
                dpg.add_text("Search")
                dpg.add_input_text(tag=self._t("search"), width=220, callback=lambda: self.refresh_file_list())
                dpg.add_button(label="목록 새로고침", callback=lambda: self.refresh_file_list())
                dpg.add_button(label="파일 열기", callback=lambda: self.load_selected_file())
                dpg.add_button(label="저장", callback=lambda: self.save_current_file())
                dpg.add_button(label="Undo", callback=lambda: self.undo())
                dpg.add_button(label="Redo", callback=lambda: self.redo())
                dpg.add_button(label="검증", callback=lambda: self.run_validation())
                dpg.add_button(label="세션 되돌리기", callback=lambda: self.revert_session())
                dpg.add_button(label="백업 복원", callback=lambda: self.restore_backup())

            with dpg.group(horizontal=True):
                dpg.add_text("Loaded")
                dpg.add_text("-", tag=self._t("loaded_file"))
            with dpg.group(horizontal=True):
                dpg.add_text("Save status")
                dpg.add_text("-", tag=self._t("save_status"))
                dpg.add_spacer(width=12)
                dpg.add_text("Selection")
                dpg.add_text("선택된 항목 없음", tag=self._t("selection_summary"))

            with dpg.group(horizontal=True):
                with dpg.child_window(tag=self._t("file_panel"), width=260, height=540, border=True):
                    dpg.add_text("Game Files")
                    dpg.add_text("0 files", tag=self._t("file_count"))
                    dpg.add_listbox(tag=self._t("file_list"), items=[], width=-1, num_items=24)

                with dpg.child_window(tag=self._t("center_panel"), width=840, height=540, border=True):
                    with dpg.tab_bar(tag=self._t("detail_tabs")):
                        with dpg.tab(tag=self._t("game_info_tab"), label="Game Info"):
                            dpg.add_button(label="Game Info 적용", callback=lambda: self.apply_game_info_editor())
                            with dpg.child_window(tag=self._t("game_info_table"), width=-1, height=440):
                                pass

                        with dpg.tab(tag=self._t("lineup_tab"), label="Lineup"):
                            with dpg.group(horizontal=True):
                                dpg.add_combo(
                                    tag=self._t("lineup_section"),
                                    items=["home_starter", "home_bullpen", "home_candidate", "away_starter", "away_bullpen", "away_candidate"],
                                    default_value=self.selected_lineup_section,
                                    callback=lambda: self.on_lineup_section_change(),
                                    width=180,
                                )
                                dpg.add_button(label="행 추가", callback=lambda: self.add_lineup_row())
                                dpg.add_button(label="행 삭제", callback=lambda: self.delete_lineup_row())
                                dpg.add_button(label="행 적용", callback=lambda: self.apply_lineup_editor())
                                dpg.add_button(label="선발 검증", callback=lambda: self.run_validation())
                            with dpg.child_window(tag=self._t("lineup_table"), width=-1, height=440):
                                pass

                        with dpg.tab(tag=self._t("relay_tab"), label="Relay"):
                            with dpg.group(horizontal=True):
                                dpg.add_combo(tag=self._t("relay_view_mode"), items=["Event", "PA"], default_value="Event", width=80, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_input_text(tag=self._t("relay_query"), hint="text / player / ptsPitchId", width=220, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_combo(tag=self._t("relay_inning_filter"), items=["All"], default_value="All", width=90, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_combo(tag=self._t("relay_half_filter"), items=["All", "Top", "Bottom"], default_value="All", width=90, callback=lambda: self.refresh_relay_event_table())
                                dpg.add_combo(tag=self._t("relay_type_filter"), items=["All"], default_value="All", width=90, callback=lambda: self.refresh_relay_event_table())
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

                        with dpg.tab(tag=self._t("record_tab"), label="Record"):
                            with dpg.group(horizontal=True):
                                dpg.add_combo(tag=self._t("record_scope"), items=["batter:home", "batter:away", "pitcher:home", "pitcher:away"], default_value="batter:home", width=180, callback=lambda: self.on_record_scope_change())
                                dpg.add_button(label="행 추가", callback=lambda: self.add_record_row())
                                dpg.add_button(label="행 삭제", callback=lambda: self.delete_record_row())
                                dpg.add_button(label="행 적용", callback=lambda: self.apply_record_editor())
                                dpg.add_button(label="타자 합계 재계산", callback=lambda: self.recalc_record_totals())
                            with dpg.child_window(tag=self._t("record_table"), width=-1, height=440):
                                pass

                        with dpg.tab(tag=self._t("validation_tab"), label="검증 결과"):
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="검증 실행", callback=lambda: self.run_validation())
                                dpg.add_text("-", tag=self._t("finding_summary"))
                            with dpg.child_window(tag=self._t("findings_table"), width=-1, height=440):
                                pass
                            dpg.add_input_text(tag=self._t("finding_delta"), multiline=True, readonly=True, width=-1, height=120)

                        with dpg.tab(tag=self._t("diff_tab"), label="Diff"):
                            dpg.add_input_text(tag=self._t("diff_text"), multiline=True, readonly=True, width=-1, height=440)

                        with dpg.tab(tag=self._t("history_tab"), label="History"):
                            dpg.add_input_text(tag=self._t("history_text"), multiline=True, readonly=True, width=-1, height=440)

                        with dpg.tab(tag=self._t("auto_preview_tab"), label="Auto Preview"):
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="미리보기 갱신", callback=lambda: self.refresh_auto_preview())
                                dpg.add_button(label="자동 재계산 적용", callback=lambda: self.apply_auto_rebuild())
                            dpg.add_input_text(tag=self._t("auto_preview_text"), multiline=True, readonly=True, width=-1, height=440)

                with dpg.child_window(tag=self._t("detail_panel"), width=480, height=540, border=True):
                    dpg.add_text("Selection Editor")
                    self._add_labeled_combo(
                        self._t("editor_mode"),
                        "editor_mode",
                        items=["Quick Fix", "Relay Raw", "Roster/Game", "Record"],
                        default_value="Quick Fix",
                        callback=lambda: self.apply_editor_mode(),
                    )
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Fill Selected", callback=lambda: self.populate_structured_editors())
                        dpg.add_button(label="Auto Rebuild", callback=lambda: self.apply_auto_rebuild())
                        dpg.add_button(label="Validate", callback=lambda: self.run_validation())
                        dpg.add_button(label="Save", callback=lambda: self.save_current_file())
                    dpg.add_input_text(tag=self._t("context_summary_text"), multiline=True, readonly=True, width=-1, height=92)
                    dpg.add_separator()
                    with dpg.collapsing_header(tag=self._t("section_game_info"), label="Game Info Editor", default_open=False):
                        for field in GAME_INFO_FIELDS:
                            if field in BOOLEAN_GAME_INFO_FIELDS:
                                self._add_labeled_checkbox(self._t(f"game_info_{field}"), field)
                            else:
                                self._add_labeled_input_text(self._t(f"game_info_{field}"), field)
                    dpg.add_separator()
                    with dpg.collapsing_header(tag=self._t("section_lineup_row"), label="Lineup Row Editor", default_open=False):
                        for field in LINEUP_FIELDS:
                            self._add_labeled_input_text(self._t(f"lineup_{field}"), field)
                    dpg.add_separator()
                    with dpg.collapsing_header(tag=self._t("section_relay_block"), label="Relay Block Editor", default_open=False):
                        for field in BLOCK_FIELDS:
                            self._add_labeled_input_text(self._t(f"block_{field}"), field)
                        for field in ("homeTeamWinRate", "awayTeamWinRate", "wpaByPlate"):
                            self._add_labeled_input_text(self._t(f"metric_{field}"), f"metric.{field}")
                        dpg.add_button(label="블록 적용", callback=lambda: self.apply_block_editor())
                    dpg.add_separator()
                    with dpg.collapsing_header(tag=self._t("section_relay_event"), label="Relay Event Editor", default_open=False):
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
                    dpg.add_separator()
                    with dpg.collapsing_header(tag=self._t("section_structured_add"), label="Structured Add", default_open=True):
                        self._add_labeled_combo(self._t("add_template_type"), "template_type", items=EVENT_TEMPLATE_TYPES, default_value="pitch")
                        self._add_labeled_combo(self._t("add_insert_mode"), "insert", items=["before", "after"], default_value="after")
                        for field in ("batter_id", "batter_name", "pitcher_id", "detail", "text", "pitch_result", "pitch_num", "pts_pitch_id"):
                            self._add_labeled_input_text(self._t(f"add_{field}"), field)
                        self._add_labeled_combo(self._t("add_result_type"), "result_type", items=RESULT_TYPES, default_value="out")
                        self._add_runner_move_editor("add", count=3)
                        dpg.add_button(label="이벤트 템플릿 추가", callback=lambda: self.insert_structured_event())
                    dpg.add_separator()
                    with dpg.collapsing_header(tag=self._t("section_missing_pa"), label="Missing PA", default_open=True):
                        self._add_labeled_combo(self._t("pa_insert_mode"), "insert", items=["before", "after"], default_value="before", callback=lambda: self.populate_structured_editors())
                        for field in ("batter_id", "batter_name", "pitcher_id", "detail", "result_text", "pitch_result", "pitch_num", "pts_pitch_id"):
                            self._add_labeled_input_text(self._t(f"pa_{field}"), field)
                        self._add_labeled_combo(self._t("pa_result_type"), "result_type", items=RESULT_TYPES, default_value="single")
                        self._add_pa_pitch_editor("pa", count=5)
                        self._add_runner_move_editor("pa", count=3)
                        dpg.add_button(label="누락 타석 삽입", callback=lambda: self.insert_missing_plate_appearance())
                    dpg.add_separator()
                    with dpg.collapsing_header(tag=self._t("section_meaning_edit"), label="Meaning Edit", default_open=True):
                        for field in ("batter_id", "batter_name", "pitcher_id", "detail", "text", "pitch_result", "pitch_num", "pts_pitch_id"):
                            self._add_labeled_input_text(self._t(f"meaning_{field}"), field)
                        self._add_labeled_combo(self._t("meaning_result_type"), "result_type", items=RESULT_TYPES, default_value="double")
                        self._add_labeled_checkbox(self._t("meaning_replace_runner_events"), "replace following runner events", default_value=True)
                        self._add_runner_move_editor("meaning", count=3)
                        dpg.add_button(label="결과 의미 수정", callback=lambda: self.apply_meaning_edit())
                    dpg.add_separator()
                    with dpg.collapsing_header(tag=self._t("section_pa_split_merge"), label="PA Split/Merge", default_open=False):
                        dpg.add_text("Split")
                        for field in ("first_batter_id", "first_batter_name", "first_detail", "first_text", "second_batter_id", "second_batter_name", "second_detail", "second_text"):
                            self._add_labeled_input_text(self._t(f"split_{field}"), field)
                        self._add_labeled_combo(self._t("split_first_result_type"), "first_result_type", items=RESULT_TYPES, default_value="strikeout")
                        self._add_labeled_combo(self._t("split_second_result_type"), "second_result_type", items=RESULT_TYPES, default_value="double")
                        self._add_runner_move_editor("split_first", count=3, title_prefix="split_first runner")
                        self._add_runner_move_editor("split_second", count=3, title_prefix="split_second runner")
                        dpg.add_button(label="타석 분리", callback=lambda: self.split_selected_plate_appearance())
                        dpg.add_separator()
                        dpg.add_text("Merge")
                        self._add_labeled_input_text(self._t("merge_batter_id"), "merged_batter_id")
                        self._add_labeled_input_text(self._t("merge_batter_name"), "merged_batter_name")
                        dpg.add_button(label="이전 타석과 병합", callback=lambda: self.merge_selected_plate_appearance())
                    dpg.add_separator()
                    with dpg.group(tag=self._t("record_batter_editor_group")):
                        dpg.add_text("Record Batter Row")
                        for field in RECORD_BATTER_FIELDS:
                            self._add_labeled_input_text(self._t(f"record_batter_{field}"), field)
                    with dpg.group(tag=self._t("record_pitcher_editor_group"), show=False):
                        dpg.add_text("Record Pitcher Row")
                        for field in RECORD_PITCHER_FIELDS:
                            self._add_labeled_input_text(self._t(f"record_pitcher_{field}"), field)
                    dpg.add_separator()
                    with dpg.group(tag=self._t("record_totals_section")):
                        dpg.add_text("Record Batter Totals")
                        self._add_labeled_combo(self._t("record_total_side"), "side", items=["home", "away"], default_value="home")
                        for field in RECORD_BATTER_TOTAL_FIELDS:
                            self._add_labeled_input_text(self._t(f"record_total_{field}"), f"total.{field}")
                        dpg.add_button(label="합계 수동 적용", callback=lambda: self.apply_record_total_editor())

        self.refresh_file_list()
        self.refresh_all_views()
        self._configure_detail_field_widths(480)
