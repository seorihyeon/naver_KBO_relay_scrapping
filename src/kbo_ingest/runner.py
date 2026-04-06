from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import psycopg

from .db import create_schema, reset_database
from .manifest import resolve_stage_sizes
from .pipeline import load_one_game
from .validation import validate_loaded_entries


def _write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_markdown_report(report: dict[str, Any], report_path: Path) -> None:
    lines = [
        f"# {report.get('run_label', 'KBO Load Validation Report')}",
        "",
        f"- Loaded games: {report.get('loaded_game_count', 0)}",
        f"- Blocking issues: {report.get('blocking_issue_count', 0)}",
        f"- Source issues: {report.get('source_issue_count', 0)}",
        f"- Load seconds: {report.get('load_seconds', 0):.2f}",
        f"- Validation seconds: {report.get('validation_seconds', 0):.2f}",
        "",
        "## Table Counts",
        "",
        "| Table | Expected | Actual |",
        "| --- | ---: | ---: |",
    ]
    for table_name, counts in report.get("table_counts", {}).items():
        lines.append(f"| {table_name} | {counts['expected']} | {counts['actual']} |")

    blocking_issues = report.get("blocking_issues", [])[:50]
    source_issues = report.get("source_issues", [])[:50]
    lines.extend(["", "## Blocking Issues", ""])
    if blocking_issues:
        for issue in blocking_issues:
            lines.append(f"- [{issue['type']}] {issue.get('path', issue['scope'])}: {issue['message']}")
    else:
        lines.append("- None")

    lines.extend(["", "## Source Issues", ""])
    if source_issues:
        for issue in source_issues:
            lines.append(f"- {issue.get('path', issue['scope'])}: {issue['message']}")
    else:
        lines.append("- None")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_and_validate_entries(
    dsn: str,
    entries: list[dict[str, Any]],
    *,
    schema_path: Path,
    report_json_path: Path,
    reset_db_first: bool = True,
    run_label: str = "KBO Load Validation",
    commit_every: int = 50,
    validate_after_load: bool = True,
) -> dict[str, Any]:
    load_started_at = time.perf_counter()
    with psycopg.connect(dsn) as conn:
        if reset_db_first:
            reset_database(conn)
        create_schema(conn, schema_path)

        for index, entry in enumerate(entries, start=1):
            load_one_game(conn, Path(entry["path"]))
            if commit_every and index % commit_every == 0:
                conn.commit()
            if index % 10 == 0 or index == len(entries):
                print(f"[load] {index}/{len(entries)} {entry['path']}")

        conn.commit()

        load_seconds = time.perf_counter() - load_started_at
        if validate_after_load:
            validation_started_at = time.perf_counter()
            report = validate_loaded_entries(conn, entries)
            validation_seconds = time.perf_counter() - validation_started_at
        else:
            report = {
                "ok": True,
                "loaded_game_count": len(entries),
                "table_counts": {},
                "blocking_issue_count": 0,
                "source_issue_count": 0,
                "blocking_issue_types": {},
                "source_issue_types": {},
                "blocking_issues": [],
                "source_issues": [],
            }
            validation_seconds = 0.0

    report.update(
        {
            "run_label": run_label,
            "load_seconds": load_seconds,
            "validation_seconds": validation_seconds,
            "report_json_path": report_json_path.as_posix(),
        }
    )
    _write_report(report, report_json_path)
    _write_markdown_report(report, report_json_path.with_suffix(".md"))
    return report


def run_sampling_loop(
    dsn: str,
    manifest: dict[str, Any],
    *,
    schema_path: Path,
    report_dir: Path,
    batch_sizes: list[int] | None = None,
) -> dict[str, Any]:
    entries = manifest["entries"]
    stage_sizes = resolve_stage_sizes(len(entries), batch_sizes)
    stage_reports: list[dict[str, Any]] = []

    for stage_size in stage_sizes:
        stage_entries = entries[:stage_size]
        report_path = report_dir / f"stage_{stage_size:04d}.json"
        report = load_and_validate_entries(
            dsn,
            stage_entries,
            schema_path=schema_path,
            report_json_path=report_path,
            reset_db_first=True,
            run_label=f"KBO Sampling Stage {stage_size}",
        )
        stage_reports.append(
            {
                "stage_size": stage_size,
                "ok": report["ok"],
                "blocking_issue_count": report["blocking_issue_count"],
                "source_issue_count": report["source_issue_count"],
                "report_json_path": report_path.as_posix(),
            }
        )
        if not report["ok"]:
            break

    summary = {
        "seed": manifest["seed"],
        "total_games": manifest["total_games"],
        "stage_reports": stage_reports,
        "completed_all_stages": bool(stage_reports) and stage_reports[-1]["stage_size"] == manifest["total_games"] and stage_reports[-1]["ok"],
    }
    _write_report(summary, report_dir / "sampling_summary.json")
    return summary
