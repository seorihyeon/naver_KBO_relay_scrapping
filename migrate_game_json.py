from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
from typing import Any

import check_data

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

    before_result = check_data.validate_game(raw_payload) if validate else None
    after_result = check_data.validate_game(migrated) if validate else None
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate KBO game JSON files to the minimal schema.")
    parser.add_argument("path", nargs="?", default="games", help="Target JSON file or directory")
    parser.add_argument("--in-place", action="store_true", help="Overwrite the source files after writing a backup/patch")
    parser.add_argument("--output-dir", type=Path, help="Write migrated files into a separate directory")
    parser.add_argument("--no-validate", action="store_true", help="Skip before/after source validation")
    args = parser.parse_args()

    target = Path(args.path)
    files = iter_json_files(target)
    if not files:
        print(f"No JSON files found under {target}")
        return 1

    results = [
        migrate_one_file(
            path,
            write_in_place=bool(args.in_place),
            output_root=args.output_dir,
            relative_root=target if target.is_dir() else target.parent,
            validate=not args.no_validate,
        )
        for path in files
    ]

    changed_count = sum(1 for item in results if item["changed"])
    failed_after = [item for item in results if item["after_ok"] is False]

    print(f"files={len(results)} changed={changed_count} after_failures={len(failed_after)}")
    for item in results[:20]:
        print(
            f"- {item['path']} | changed={item['changed']} | "
            f"written={item['written_path'] or '-'} | after_ok={item['after_ok']}"
        )

    return 0 if not failed_after else 2


if __name__ == "__main__":
    raise SystemExit(main())
