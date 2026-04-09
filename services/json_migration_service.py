"""최소 스키마 마이그레이션 유스케이스를 담당하는 서비스 모듈."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from src.kbo_ingest.game_validation import validate_game
from src.kbo_ingest.game_json import minimize_game_payload, pretty_game_json


def iter_json_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(path for path in target.rglob("*.json") if ".history" not in path.parts)


def history_root_for(path: Path) -> Path:
    return path.parent / ".history" / path.stem


def migrate_one_file(
    path: Path,
    *,
    write_in_place: bool,
    output_root: Path | None,
    relative_root: Path | None,
    validate: bool,
) -> dict[str, Any]:
    raw_text = path.read_text(encoding="utf-8")
    raw_payload = json.loads(raw_text)
    migrated = minimize_game_payload(raw_payload, file_path=path)
    migrated_text = pretty_game_json(migrated)

    before_result = validate_game(raw_payload) if validate else None
    after_result = validate_game(migrated) if validate else None
    changed = raw_text != migrated_text

    written_path: Path | None = None
    backup_path: Path | None = None
    patch_path: Path | None = None

    if write_in_place and changed:
        history_dir = history_root_for(path)
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = path.stem + "_migrate"
        backup_path = history_dir / f"{stamp}.bak"
        patch_path = history_dir / f"{stamp}.patch"
        backup_path.write_text(raw_text, encoding="utf-8")
        patch_text = "\n".join(
            difflib.unified_diff(
                raw_text.splitlines(),
                migrated_text.splitlines(),
                fromfile=f"{path.name} (before)",
                tofile=f"{path.name} (after)",
                lineterm="",
            )
        )
        patch_path.write_text(patch_text + ("\n" if patch_text else ""), encoding="utf-8")
        path.write_text(migrated_text, encoding="utf-8")
        written_path = path
    elif output_root is not None:
        try:
            relative = path.relative_to(relative_root) if relative_root is not None else Path(path.name)
        except ValueError:
            relative = Path(path.name)
        output_path = output_root / relative
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(migrated_text, encoding="utf-8")
        written_path = output_path

    return {
        "path": path.as_posix(),
        "changed": changed,
        "written_path": written_path.as_posix() if written_path else None,
        "backup_path": backup_path.as_posix() if backup_path else None,
        "patch_path": patch_path.as_posix() if patch_path else None,
        "before_ok": before_result["ok"] if before_result is not None else None,
        "after_ok": after_result["ok"] if after_result is not None else None,
        "after_issue_count": len(after_result["issues"]) if after_result is not None else None,
        "after_warning_count": len(after_result["warnings"]) if after_result is not None else None,
    }
