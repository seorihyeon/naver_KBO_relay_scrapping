from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
import difflib
import getpass
import json
from pathlib import Path
from typing import Any, Callable

import check_data

from .correction_engine import (
    insert_event_template as engine_insert_event_template,
    insert_missing_plate_appearance as engine_insert_missing_plate_appearance,
    merge_with_previous_plate_appearance as engine_merge_with_previous_plate_appearance,
    rebuild_payload,
    split_plate_appearance as engine_split_plate_appearance,
    summarize_plate_appearances,
    update_event_meaning as engine_update_event_meaning,
)
from .game_json import CURRENT_GAME_STATE_FIELDS, load_game_payload, pretty_game_json


JsonDict = dict[str, Any]
Mutator = Callable[[JsonDict], None]

BATTER_TOTAL_FIELDS = ("ab", "hit", "bb", "kk", "hr", "rbi", "run", "sb")
RELAY_STATE_KEYS = ("batter", "pitcher", "out", "ball", "strike", "base1", "base2", "base3")
SCORE_STATE_KEYS = (
    "homeScore",
    "awayScore",
    "homeHit",
    "awayHit",
    "homeBallFour",
    "awayBallFour",
    "homeError",
    "awayError",
)


@dataclass
class HistoryEntry:
    timestamp: str
    action: str
    changed_paths: list[str]


def _deepcopy_payload(payload: JsonDict) -> JsonDict:
    return copy.deepcopy(payload)


def _json_path(prefix: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{prefix}[{key}]"
    if not prefix:
        return key
    return f"{prefix}.{key}"


def _collect_changed_paths(before: Any, after: Any, *, prefix: str = "") -> list[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        changed: list[str] = []
        for key in sorted(set(before) | set(after)):
            if key not in before or key not in after:
                changed.append(_json_path(prefix, key))
                continue
            changed.extend(_collect_changed_paths(before[key], after[key], prefix=_json_path(prefix, key)))
        return changed
    if isinstance(before, list) and isinstance(after, list):
        changed: list[str] = []
        max_len = max(len(before), len(after))
        for index in range(max_len):
            if index >= len(before) or index >= len(after):
                changed.append(_json_path(prefix, index))
                continue
            changed.extend(_collect_changed_paths(before[index], after[index], prefix=_json_path(prefix, index)))
        return changed
    if before != after:
        return [prefix or "$"]
    return []


def _history_root_for(path: Path) -> Path:
    return path.parent / ".history" / path.stem


def _timestamp_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _timestamp_file() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _relay_block_label(block: JsonDict) -> str:
    inning_no = block.get("inn") or "?"
    half = "초" if str(block.get("homeOrAway")) == "0" else "말"
    return f"{inning_no}회{half}"


def _event_signature(event: JsonDict) -> tuple[Any, ...]:
    state = event.get("currentGameState") or {}
    return (
        event.get("text"),
        state.get("batter"),
        state.get("pitcher"),
        state.get("out"),
        state.get("ball"),
        state.get("strike"),
        state.get("base1"),
        state.get("base2"),
        state.get("base3"),
        state.get("homeScore"),
        state.get("awayScore"),
    )


def _normalize_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _current_state_value(event: JsonDict, key: str) -> Any:
    return (event.get("currentGameState") or {}).get(key)


def _iter_block_refs(payload: JsonDict):
    relay = payload.get("relay") or []
    for group_index, inning_group in enumerate(relay):
        for block_index, block in enumerate(inning_group or []):
            if isinstance(block, dict):
                yield group_index, block_index, block


def _iter_event_refs(payload: JsonDict):
    for group_index, block_index, block in _iter_block_refs(payload):
        for event_index, event in enumerate(block.get("textOptions") or []):
            if isinstance(event, dict):
                yield group_index, block_index, event_index, event


class GameEditorSession:
    def __init__(self, path: Path, payload: JsonDict):
        self.path = path
        self.original_payload = _deepcopy_payload(payload)
        self.disk_payload = _deepcopy_payload(payload)
        self.payload = _deepcopy_payload(payload)
        self.undo_stack: list[tuple[str, JsonDict]] = []
        self.redo_stack: list[tuple[str, JsonDict]] = []
        self.history_entries: list[HistoryEntry] = []
        self.last_saved_at: str | None = None

    @classmethod
    def load(cls, path: Path) -> "GameEditorSession":
        return cls(path=path, payload=load_game_payload(path))

    def _record_snapshot(self, action: str) -> None:
        self.undo_stack.append((action, _deepcopy_payload(self.payload)))
        self.redo_stack.clear()

    def apply_change(self, action: str, mutator: Mutator) -> None:
        before = _deepcopy_payload(self.payload)
        self._record_snapshot(action)
        mutator(self.payload)
        changed_paths = _collect_changed_paths(before, self.payload)
        self.history_entries.append(HistoryEntry(timestamp=_timestamp_now(), action=action, changed_paths=changed_paths))

    def has_unsaved_changes(self) -> bool:
        return self.disk_payload != self.payload

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        action, snapshot = self.undo_stack.pop()
        self.redo_stack.append((action, _deepcopy_payload(self.payload)))
        self.payload = snapshot
        self.history_entries.append(HistoryEntry(timestamp=_timestamp_now(), action=f"undo:{action}", changed_paths=[]))
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        action, snapshot = self.redo_stack.pop()
        self.undo_stack.append((action, _deepcopy_payload(self.payload)))
        self.payload = snapshot
        self.history_entries.append(HistoryEntry(timestamp=_timestamp_now(), action=f"redo:{action}", changed_paths=[]))
        return True

    def revert_to_loaded(self) -> None:
        self.apply_change("revert_to_loaded", lambda payload: payload.clear() or payload.update(_deepcopy_payload(self.original_payload)))

    def build_diff(self) -> str:
        before = pretty_game_json(self.disk_payload).splitlines()
        after = pretty_game_json(self.payload).splitlines()
        return "\n".join(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"{self.path.name} (saved)",
                tofile=f"{self.path.name} (working)",
                lineterm="",
            )
        )

    def _history_dir(self) -> Path:
        return _history_root_for(self.path)

    def list_backups(self) -> list[Path]:
        history_dir = self._history_dir()
        if not history_dir.exists():
            return []
        return sorted(history_dir.glob("*.bak"))

    def restore_latest_backup(self) -> Path | None:
        backups = self.list_backups()
        if not backups:
            return None
        latest = backups[-1]
        self.path.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
        restored = load_game_payload(self.path)
        self.original_payload = _deepcopy_payload(restored)
        self.disk_payload = _deepcopy_payload(restored)
        self.payload = _deepcopy_payload(restored)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.history_entries.append(HistoryEntry(timestamp=_timestamp_now(), action="restore_backup", changed_paths=[]))
        return latest

    def save(self, *, actor: str | None = None, action: str = "save") -> dict[str, Any]:
        history_dir = self._history_dir()
        history_dir.mkdir(parents=True, exist_ok=True)

        before_text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        after_text = pretty_game_json(self.payload)
        changed_paths = _collect_changed_paths(self.disk_payload, self.payload)
        stamp = _timestamp_file()
        actor_name = actor or getpass.getuser()

        if before_text:
            backup_path = history_dir / f"{stamp}.bak"
            backup_path.write_text(before_text, encoding="utf-8")
        else:
            backup_path = None

        patch_path = history_dir / f"{stamp}.patch"
        patch_text = "\n".join(
            difflib.unified_diff(
                before_text.splitlines(),
                after_text.splitlines(),
                fromfile=f"{self.path.name} (before)",
                tofile=f"{self.path.name} (after)",
                lineterm="",
            )
        )
        patch_path.write_text(patch_text + ("\n" if patch_text else ""), encoding="utf-8")

        self.path.write_text(after_text, encoding="utf-8")

        log_entry = {
            "timestamp": _timestamp_now(),
            "actor": actor_name,
            "action": action,
            "path": self.path.as_posix(),
            "backup_path": backup_path.as_posix() if backup_path else None,
            "patch_path": patch_path.as_posix(),
            "changed_paths": changed_paths,
        }
        history_log = history_dir / "changes.jsonl"
        with history_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        self.disk_payload = _deepcopy_payload(self.payload)
        self.last_saved_at = log_entry["timestamp"]
        self.history_entries.append(HistoryEntry(timestamp=log_entry["timestamp"], action=action, changed_paths=changed_paths))
        return log_entry

    def renumber_seqno(self, *, start: int = 1) -> None:
        def mutator(payload: JsonDict) -> None:
            next_seq = start
            for _, _, _, event in _iter_event_refs(payload):
                event["seqno"] = next_seq
                next_seq += 1

        self.apply_change("renumber_seqno", mutator)

    def recalculate_batter_totals(self) -> None:
        def mutator(payload: JsonDict) -> None:
            batter = (payload.get("record") or {}).get("batter") or {}
            for side in ("home", "away"):
                totals = {field: 0 for field in BATTER_TOTAL_FIELDS}
                for row in batter.get(side) or []:
                    for field in BATTER_TOTAL_FIELDS:
                        totals[field] += _normalize_int(row.get(field)) or 0
                batter[f"{side}Total"] = totals

        self.apply_change("recalculate_batter_totals", mutator)

    def fill_missing_current_game_state(self, group_index: int, block_index: int) -> None:
        def mutator(payload: JsonDict) -> None:
            relay = payload.get("relay") or []
            block = relay[group_index][block_index]
            carry: dict[str, Any] = {}
            for event in block.get("textOptions") or []:
                state = event.setdefault("currentGameState", {})
                for key in CURRENT_GAME_STATE_FIELDS:
                    value = state.get(key)
                    if value in (None, "") and key in carry:
                        state[key] = carry[key]
                    elif value not in (None, ""):
                        carry[key] = value

        self.apply_change("fill_missing_current_game_state", mutator)

    def get_lineup_rows(self, section: str) -> list[JsonDict]:
        return (self.payload.get("lineup") or {}).setdefault(section, [])

    def add_lineup_row(self, section: str, row: JsonDict | None = None, index: int | None = None) -> None:
        template = row or {"playerCode": "", "playerName": "", "position": "", "positionName": ""}

        def mutator(payload: JsonDict) -> None:
            rows = (payload.get("lineup") or {}).setdefault(section, [])
            insert_at = len(rows) if index is None else max(0, min(index, len(rows)))
            rows.insert(insert_at, _deepcopy_payload(template))

        self.apply_change(f"add_lineup_row:{section}", mutator)

    def delete_lineup_row(self, section: str, row_index: int) -> None:
        def mutator(payload: JsonDict) -> None:
            rows = (payload.get("lineup") or {}).setdefault(section, [])
            if 0 <= row_index < len(rows):
                rows.pop(row_index)

        self.apply_change(f"delete_lineup_row:{section}", mutator)

    def get_record_rows(self, table: str, side: str) -> list[JsonDict]:
        return (((self.payload.get("record") or {}).get(table) or {}).setdefault(side, []))

    def add_record_row(self, table: str, side: str, row: JsonDict | None = None, index: int | None = None) -> None:
        template = row or ({"playerCode": "", "name": ""} if table == "batter" else {"pcode": "", "name": ""})

        def mutator(payload: JsonDict) -> None:
            rows = (((payload.get("record") or {}).get(table) or {}).setdefault(side, []))
            insert_at = len(rows) if index is None else max(0, min(index, len(rows)))
            rows.insert(insert_at, _deepcopy_payload(template))

        self.apply_change(f"add_record_row:{table}:{side}", mutator)

    def delete_record_row(self, table: str, side: str, row_index: int) -> None:
        def mutator(payload: JsonDict) -> None:
            rows = (((payload.get("record") or {}).get(table) or {}).setdefault(side, []))
            if 0 <= row_index < len(rows):
                rows.pop(row_index)

        self.apply_change(f"delete_record_row:{table}:{side}", mutator)

    def add_relay_block(self, group_index: int | None = None, block_index: int | None = None, block: JsonDict | None = None) -> None:
        template = block or {
            "title": "새 블록",
            "titleStyle": "0",
            "no": 0,
            "inn": 1,
            "homeOrAway": "0",
            "statusCode": 0,
            "textOptions": [],
            "ptsOptions": [],
        }

        def mutator(payload: JsonDict) -> None:
            relay = payload.setdefault("relay", [])
            if group_index is None:
                relay.append([_deepcopy_payload(template)])
                return
            while len(relay) <= group_index:
                relay.append([])
            target_group = relay[group_index]
            insert_at = len(target_group) if block_index is None else max(0, min(block_index, len(target_group)))
            target_group.insert(insert_at, _deepcopy_payload(template))

        self.apply_change("add_relay_block", mutator)

    def delete_relay_block(self, group_index: int, block_index: int) -> None:
        def mutator(payload: JsonDict) -> None:
            relay = payload.get("relay") or []
            if 0 <= group_index < len(relay) and 0 <= block_index < len(relay[group_index]):
                relay[group_index].pop(block_index)
                if not relay[group_index]:
                    relay.pop(group_index)

        self.apply_change("delete_relay_block", mutator)

    def move_relay_block(self, group_index: int, block_index: int, delta: int) -> tuple[int, int] | None:
        next_ref: list[tuple[int, int] | None] = [None]

        def mutator(payload: JsonDict) -> None:
            relay = payload.get("relay") or []
            if not (0 <= group_index < len(relay) and 0 <= block_index < len(relay[group_index])):
                return
            group = relay[group_index]
            new_index = max(0, min(len(group) - 1, block_index + delta))
            if new_index == block_index:
                next_ref[0] = (group_index, block_index)
                return
            group.insert(new_index, group.pop(block_index))
            next_ref[0] = (group_index, new_index)

        self.apply_change("move_relay_block", mutator)
        return next_ref[0]

    def add_relay_event(self, group_index: int, block_index: int, event_index: int | None = None, event: JsonDict | None = None) -> int:
        template = event or {
            "seqno": None,
            "type": 1,
            "text": "",
            "currentGameState": {key: None for key in CURRENT_GAME_STATE_FIELDS},
        }
        inserted_index = [0]

        def mutator(payload: JsonDict) -> None:
            block = (payload.get("relay") or [])[group_index][block_index]
            events = block.setdefault("textOptions", [])
            insert_at = len(events) if event_index is None else max(0, min(event_index, len(events)))
            events.insert(insert_at, _deepcopy_payload(template))
            inserted_index[0] = insert_at

        self.apply_change("add_relay_event", mutator)
        return inserted_index[0]

    def delete_relay_event(self, group_index: int, block_index: int, event_index: int) -> None:
        def mutator(payload: JsonDict) -> None:
            block = (payload.get("relay") or [])[group_index][block_index]
            events = block.setdefault("textOptions", [])
            if 0 <= event_index < len(events):
                events.pop(event_index)

        self.apply_change("delete_relay_event", mutator)

    def duplicate_relay_event(self, group_index: int, block_index: int, event_index: int) -> int:
        inserted_index = [event_index + 1]

        def mutator(payload: JsonDict) -> None:
            block = (payload.get("relay") or [])[group_index][block_index]
            events = block.setdefault("textOptions", [])
            if not (0 <= event_index < len(events)):
                return
            clone = _deepcopy_payload(events[event_index])
            events.insert(event_index + 1, clone)
            inserted_index[0] = event_index + 1

        self.apply_change("duplicate_relay_event", mutator)
        return inserted_index[0]

    def move_relay_event(self, group_index: int, block_index: int, event_index: int, delta: int) -> int:
        next_index = [event_index]

        def mutator(payload: JsonDict) -> None:
            block = (payload.get("relay") or [])[group_index][block_index]
            events = block.setdefault("textOptions", [])
            if not (0 <= event_index < len(events)):
                return
            new_index = max(0, min(len(events) - 1, event_index + delta))
            if new_index == event_index:
                next_index[0] = event_index
                return
            events.insert(new_index, events.pop(event_index))
            next_index[0] = new_index

        self.apply_change("move_relay_event", mutator)
        return next_index[0]

    def preview_auto_rebuild(self) -> dict[str, Any]:
        rebuilt, report = rebuild_payload(self.payload)
        before = pretty_game_json(self.payload).splitlines()
        after = pretty_game_json(rebuilt).splitlines()
        diff = "\n".join(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"{self.path.name} (working)",
                tofile=f"{self.path.name} (auto_rebuild)",
                lineterm="",
            )
        )
        return {
            "payload": rebuilt,
            "report": report,
            "changed_paths": _collect_changed_paths(self.payload, rebuilt),
            "diff": diff,
            "plate_appearances": summarize_plate_appearances(rebuilt),
        }

    def apply_auto_rebuild(self) -> dict[str, Any]:
        preview = {}

        def mutator(payload: JsonDict) -> None:
            rebuilt, report = rebuild_payload(payload)
            preview["report"] = report
            payload.clear()
            payload.update(rebuilt)

        self.apply_change("auto_rebuild", mutator)
        return preview

    def insert_event_template(
        self,
        *,
        group_index: int,
        block_index: int,
        insert_at: int,
        template_type: str,
        spec: dict[str, Any],
    ) -> list[int]:
        inserted: list[int] = []

        def mutator(payload: JsonDict) -> None:
            inserted[:] = engine_insert_event_template(
                payload,
                group_index=group_index,
                block_index=block_index,
                insert_at=insert_at,
                template_type=template_type,
                spec=spec,
            )
            rebuilt, _report = rebuild_payload(payload)
            payload.clear()
            payload.update(rebuilt)

        self.apply_change(f"insert_event_template:{template_type}", mutator)
        return inserted

    def insert_missing_plate_appearance(
        self,
        *,
        group_index: int,
        block_index: int,
        insert_at: int,
        spec: dict[str, Any],
    ) -> list[int]:
        inserted: list[int] = []

        def mutator(payload: JsonDict) -> None:
            inserted[:] = engine_insert_missing_plate_appearance(
                payload,
                group_index=group_index,
                block_index=block_index,
                insert_at=insert_at,
                spec=spec,
            )
            rebuilt, _report = rebuild_payload(payload)
            payload.clear()
            payload.update(rebuilt)

        self.apply_change("insert_missing_plate_appearance", mutator)
        return inserted

    def update_event_meaning(
        self,
        *,
        group_index: int,
        block_index: int,
        event_index: int,
        spec: dict[str, Any],
    ) -> list[int]:
        changed: list[int] = []

        def mutator(payload: JsonDict) -> None:
            changed[:] = engine_update_event_meaning(
                payload,
                group_index=group_index,
                block_index=block_index,
                event_index=event_index,
                spec=spec,
            )
            rebuilt, _report = rebuild_payload(payload)
            payload.clear()
            payload.update(rebuilt)

        self.apply_change("update_event_meaning", mutator)
        return changed

    def split_plate_appearance(
        self,
        *,
        group_index: int,
        block_index: int,
        split_at: int,
        spec: dict[str, Any],
    ) -> int | None:
        next_index: list[int | None] = [None]

        def mutator(payload: JsonDict) -> None:
            next_index[0] = engine_split_plate_appearance(
                payload,
                group_index=group_index,
                block_index=block_index,
                split_at=split_at,
                spec=spec,
            )
            rebuilt, _report = rebuild_payload(payload)
            payload.clear()
            payload.update(rebuilt)

        self.apply_change("split_plate_appearance", mutator)
        return next_index[0]

    def merge_with_previous_plate_appearance(
        self,
        *,
        group_index: int,
        block_index: int,
        selected_index: int,
        merged_batter_id: str | None = None,
        merged_batter_name: str | None = None,
    ) -> int | None:
        next_index: list[int | None] = [None]

        def mutator(payload: JsonDict) -> None:
            next_index[0] = engine_merge_with_previous_plate_appearance(
                payload,
                group_index=group_index,
                block_index=block_index,
                selected_index=selected_index,
                merged_batter_id=merged_batter_id,
                merged_batter_name=merged_batter_name,
            )
            rebuilt, _report = rebuild_payload(payload)
            payload.clear()
            payload.update(rebuilt)

        self.apply_change("merge_plate_appearance", mutator)
        return next_index[0]

    def _row_location_by_player(self, table: str, side: str, player_id: str) -> dict[str, Any] | None:
        rows = self.get_record_rows(table, side)
        key_name = "playerCode" if table == "batter" else "pcode"
        for row_index, row in enumerate(rows):
            if str(row.get(key_name) or "") == player_id:
                return {"tab": "record", "table": table, "side": side, "row_index": row_index}
        return None

    def _guess_validation_location(self, message: str) -> dict[str, Any] | None:
        for side in ("home", "away"):
            side_tag = f"[{side}]"
            if side_tag not in message:
                continue
            codes = [token.strip("[]',") for token in message.replace(":", " ").split() if token.strip("[]',").isdigit()]
            for code in codes:
                location = self._row_location_by_player("batter", side, code)
                if location:
                    return location
                location = self._row_location_by_player("pitcher", side, code)
                if location:
                    return location
        return None

    def scan_relay_issues(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        seq_map: dict[int, list[tuple[int, int, int]]] = {}
        pitch_map: dict[str, list[tuple[int, int, int]]] = {}
        previous_event: tuple[int, int, int, JsonDict] | None = None

        for group_index, block_index, event_index, event in _iter_event_refs(self.payload):
            seqno = _normalize_int(event.get("seqno"))
            if seqno is not None:
                seq_map.setdefault(seqno, []).append((group_index, block_index, event_index))

            pts_pitch_id = str(event.get("ptsPitchId") or "").strip()
            if pts_pitch_id:
                pitch_map.setdefault(pts_pitch_id, []).append((group_index, block_index, event_index))

            if previous_event is not None:
                prev_group, prev_block, prev_event_index, prev_event = previous_event
                prev_seq = _normalize_int(prev_event.get("seqno"))
                if prev_seq is not None and seqno is not None and seqno > prev_seq + 1:
                    findings.append(
                        {
                            "severity": "warning",
                            "code": "seq_gap",
                            "message": f"seqno gap: {prev_seq} -> {seqno} between {_relay_block_label((self.payload['relay'][prev_group])[prev_block])} and {_relay_block_label((self.payload['relay'][group_index])[block_index])}",
                            "location": {"tab": "relay", "group_index": group_index, "block_index": block_index, "event_index": event_index},
                        }
                    )

                same_signature = _event_signature(prev_event) == _event_signature(event)
                if same_signature:
                    findings.append(
                        {
                            "severity": "warning",
                            "code": "duplicate_signature",
                            "message": "Consecutive relay events have identical text/state signatures.",
                            "location": {"tab": "relay", "group_index": group_index, "block_index": block_index, "event_index": event_index},
                        }
                    )

                if _current_state_value(prev_event, "batter") == _current_state_value(event, "batter"):
                    for key in ("ball", "strike", "out"):
                        prev_value = _normalize_int(_current_state_value(prev_event, key))
                        current_value = _normalize_int(_current_state_value(event, key))
                        if prev_value is None or current_value is None:
                            continue
                        if current_value - prev_value > 1:
                            findings.append(
                                {
                                    "severity": "warning",
                                    "code": f"state_jump:{key}",
                                    "message": f"{key} jumped from {prev_value} to {current_value}.",
                                    "location": {"tab": "relay", "group_index": group_index, "block_index": block_index, "event_index": event_index},
                                }
                            )

            state = event.get("currentGameState") or {}
            if (event.get("pitchNum") is not None or event.get("pitchResult") or event.get("ptsPitchId")) and not state.get("pitcher"):
                findings.append(
                    {
                        "severity": "error",
                        "code": "missing_pitcher",
                        "message": "Pitch-like event is missing currentGameState.pitcher.",
                        "location": {"tab": "relay", "group_index": group_index, "block_index": block_index, "event_index": event_index},
                    }
                )
            if (event.get("pitchNum") is not None or event.get("type") in (13, 23)) and not (state.get("batter") or (event.get("batterRecord") or {}).get("pcode")):
                findings.append(
                    {
                        "severity": "error",
                        "code": "missing_batter",
                        "message": "Action event is missing batter identity.",
                        "location": {"tab": "relay", "group_index": group_index, "block_index": block_index, "event_index": event_index},
                    }
                )
            previous_event = (group_index, block_index, event_index, event)

        for seqno, refs in seq_map.items():
            if len(refs) < 2:
                continue
            for group_index, block_index, event_index in refs:
                findings.append(
                    {
                        "severity": "warning",
                        "code": "duplicate_seqno",
                        "message": f"Duplicate seqno detected: {seqno}",
                        "location": {"tab": "relay", "group_index": group_index, "block_index": block_index, "event_index": event_index},
                    }
                )

        for pts_pitch_id, refs in pitch_map.items():
            if len(refs) < 2:
                continue
            for group_index, block_index, event_index in refs:
                findings.append(
                    {
                        "severity": "warning",
                        "code": "duplicate_pts_pitch_id",
                        "message": f"Duplicate ptsPitchId detected: {pts_pitch_id}",
                        "location": {"tab": "relay", "group_index": group_index, "block_index": block_index, "event_index": event_index},
                    }
                )

        return findings

    def scan_auto_rebuild_drift(self) -> list[dict[str, Any]]:
        rebuilt, _report = rebuild_payload(self.payload)
        findings: list[dict[str, Any]] = []
        current_events = list(_iter_event_refs(self.payload))
        rebuilt_events = list(_iter_event_refs(rebuilt))
        for current_row, rebuilt_row in zip(current_events, rebuilt_events):
            group_index, block_index, event_index, event = current_row
            _g2, _b2, _e2, rebuilt_event = rebuilt_row
            changed_fields: list[str] = []
            current_state = event.get("currentGameState") or {}
            rebuilt_state = rebuilt_event.get("currentGameState") or {}
            for key in CURRENT_GAME_STATE_FIELDS:
                current_value = bool(current_state.get(key)) if key in {"base1", "base2", "base3"} else current_state.get(key)
                rebuilt_value = bool(rebuilt_state.get(key)) if key in {"base1", "base2", "base3"} else rebuilt_state.get(key)
                if current_value != rebuilt_value:
                    changed_fields.append(f"currentGameState.{key}")
            if _normalize_int(event.get("seqno")) != _normalize_int(rebuilt_event.get("seqno")):
                changed_fields.append("seqno")
            if changed_fields:
                findings.append(
                    {
                        "severity": "warning",
                        "code": "auto_rebuild_drift",
                        "message": f"Auto rebuild would update: {', '.join(changed_fields[:8])}",
                        "location": {"tab": "relay", "group_index": group_index, "block_index": block_index, "event_index": event_index},
                    }
                )
        return findings

    def validate(self) -> dict[str, Any]:
        base = check_data.validate_game(self.payload)
        relay_findings = self.scan_relay_issues()
        rebuild_findings = self.scan_auto_rebuild_drift()
        findings = [
            {
                "severity": "error",
                "code": "validate_game",
                "message": message,
                "location": self._guess_validation_location(message),
            }
            for message in base.get("issues", [])
        ]
        findings.extend(
            {
                "severity": "warning",
                "code": "validate_game_warning",
                "message": message,
                "location": self._guess_validation_location(message),
            }
            for message in base.get("warnings", [])
        )
        findings.extend(relay_findings)
        findings.extend(rebuild_findings)
        error_count = sum(1 for item in findings if item["severity"] == "error")
        warning_count = sum(1 for item in findings if item["severity"] != "error")
        return {
            "ok": error_count == 0,
            "error_count": error_count,
            "warning_count": warning_count,
            "findings": findings,
            "raw_result": base,
        }
