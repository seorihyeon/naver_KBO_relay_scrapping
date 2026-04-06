from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

import check_data
from web_interface import Scrapper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recollect source-issue games and compare refreshed JSON against local files")
    parser.add_argument(
        "--input-report",
        default="reports/final_run/full_validate_report.json",
        help="Validation report JSON that contains source_issues",
    )
    parser.add_argument(
        "--source-root",
        default=".",
        help="Project root used to resolve game paths from the report",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/source_recollect/refetched_json",
        help="Directory where refreshed JSON files will be written",
    )
    parser.add_argument(
        "--report-json",
        default="reports/source_recollect/recollect_report.json",
        help="JSON summary report path",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run Playwright in headless mode",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Per-request timeout passed to Scrapper",
    )
    return parser.parse_args()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_json(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def build_game_url(game_path: Path) -> str:
    return f"https://m.sports.naver.com/kbaseball/game/{game_path.stem}"


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Source Issue Recollection Report",
        "",
        f"- Source-issue games: {report['game_count']}",
        f"- Recollection failures: {report['fetch_failure_count']}",
        f"- Same hash: {report['same_hash_count']}",
        f"- Different hash: {report['different_hash_count']}",
        f"- Same issues after recollection: {report['same_issue_set_count']}",
        f"- Changed issues after recollection: {report['changed_issue_set_count']}",
        "",
        "## Games",
        "",
        "| Path | Fetch | Hash | Issues |",
        "| --- | --- | --- | --- |",
    ]

    for game in report["games"]:
        if game["status"] == "fetch_failed":
            lines.append(f"| {game['path']} | failed | - | - |")
            continue
        hash_status = "same" if game["same_hash"] else "different"
        issue_status = "same" if game["same_issue_set"] else "changed"
        lines.append(f"| {game['path']} | ok | {hash_status} | {issue_status} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_report_path = Path(args.input_report)
    project_root = Path(args.source_root).resolve()
    output_dir = Path(args.output_dir)
    report_path = Path(args.report_json)

    report_data = json.loads(input_report_path.read_text(encoding="utf-8"))
    source_issue_paths = sorted({issue["path"] for issue in report_data.get("source_issues", []) if issue.get("path")})

    output_dir.mkdir(parents=True, exist_ok=True)

    games: list[dict[str, Any]] = []
    fetch_failure_count = 0
    same_hash_count = 0
    different_hash_count = 0
    same_issue_set_count = 0
    changed_issue_set_count = 0

    scr = Scrapper(wait=args.timeout, path=str(output_dir), headless=args.headless)
    try:
        for relative_path in source_issue_paths:
            game_path = (project_root / relative_path).resolve()
            game = {
                "path": relative_path,
                "game_id": game_path.stem,
                "game_url": build_game_url(game_path),
            }
            try:
                original = json.loads(game_path.read_text(encoding="utf-8"))
                lineup, relay, record = scr.get_game_data(game["game_url"])
                refreshed = {"lineup": lineup, "relay": relay, "record": record}

                refetch_path = output_dir / relative_path
                refetch_path.parent.mkdir(parents=True, exist_ok=True)
                refetch_path.write_text(json.dumps(refreshed, ensure_ascii=False, indent=2), encoding="utf-8")

                original_validation = check_data.validate_game(original)
                refreshed_validation = check_data.validate_game(refreshed)
                original_hash = digest_json(original)
                refreshed_hash = digest_json(refreshed)
                same_hash = original_hash == refreshed_hash
                same_issue_set = sorted(original_validation.get("issues", [])) == sorted(refreshed_validation.get("issues", []))

                game.update(
                    {
                        "status": "ok",
                        "refetch_path": refetch_path.as_posix(),
                        "same_hash": same_hash,
                        "same_issue_set": same_issue_set,
                        "original_hash": original_hash,
                        "refreshed_hash": refreshed_hash,
                        "original_issue_count": len(original_validation.get("issues", [])),
                        "refreshed_issue_count": len(refreshed_validation.get("issues", [])),
                        "original_issues": original_validation.get("issues", []),
                        "refreshed_issues": refreshed_validation.get("issues", []),
                    }
                )

                if same_hash:
                    same_hash_count += 1
                else:
                    different_hash_count += 1

                if same_issue_set:
                    same_issue_set_count += 1
                else:
                    changed_issue_set_count += 1
            except Exception as exc:
                fetch_failure_count += 1
                game.update(
                    {
                        "status": "fetch_failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            games.append(game)
    finally:
        scr.close()

    summary = {
        "game_count": len(source_issue_paths),
        "fetch_failure_count": fetch_failure_count,
        "same_hash_count": same_hash_count,
        "different_hash_count": different_hash_count,
        "same_issue_set_count": same_issue_set_count,
        "changed_issue_set_count": changed_issue_set_count,
        "games": games,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(summary, report_path.with_suffix(".md"))
    print(
        "recollect finished "
        f"games={summary['game_count']} "
        f"fetch_failures={summary['fetch_failure_count']} "
        f"same_hash={summary['same_hash_count']} "
        f"different_hash={summary['different_hash_count']} "
        f"same_issues={summary['same_issue_set_count']} "
        f"changed_issues={summary['changed_issue_set_count']}"
    )
    return 0 if fetch_failure_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
