from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.kbo_ingest.manifest import load_manifest
from src.kbo_ingest.validation import TABLE_NAMES, _aggregate_table_expectations, _fetch_global_actual_counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parallel chunk validator for the full KBO manifest")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--chunk-size", type=int, default=200)
    parser.add_argument("--max-procs", type=int, default=6)
    return parser


def launch_chunk(
    dsn: str,
    manifest_path: Path,
    offset: int,
    limit: int,
    chunk_report_path: Path,
) -> subprocess.Popen[str]:
    chunk_report_path.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            sys.executable,
            "postgres_loader.py",
            "validate",
            "--dsn",
            dsn,
            "--manifest",
            str(manifest_path),
            "--offset",
            str(offset),
            "--limit",
            str(limit),
            "--report-json",
            str(chunk_report_path),
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def main() -> int:
    args = build_parser().parse_args()
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    entries = manifest["entries"]
    total = len(entries)
    chunk_size = max(1, args.chunk_size)
    max_procs = max(1, args.max_procs)

    chunk_specs: list[tuple[int, int]] = []
    offset = 0
    while offset < total:
        limit = min(chunk_size, total - offset)
        chunk_specs.append((offset, limit))
        offset += limit

    report_path = Path(args.report_json)
    chunk_dir = report_path.parent / f"{report_path.stem}_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    running: list[tuple[tuple[int, int], Path, subprocess.Popen[str]]] = []
    completed_chunk_reports: list[Path] = []

    pending = list(chunk_specs)
    while pending or running:
        while pending and len(running) < max_procs:
            chunk_offset, chunk_limit = pending.pop(0)
            chunk_report_path = chunk_dir / f"chunk_{chunk_offset:04d}_{chunk_limit:04d}.json"
            proc = launch_chunk(args.dsn, manifest_path, chunk_offset, chunk_limit, chunk_report_path)
            running.append(((chunk_offset, chunk_limit), chunk_report_path, proc))

        still_running: list[tuple[tuple[int, int], Path, subprocess.Popen[str]]] = []
        for spec, chunk_report_path, proc in running:
            returncode = proc.poll()
            if returncode is None:
                still_running.append((spec, chunk_report_path, proc))
                continue
            stdout, stderr = proc.communicate()
            if stdout:
                print(stdout.strip())
            if stderr:
                print(stderr.strip(), file=sys.stderr)
            if returncode not in (0, 2):
                raise SystemExit(f"chunk validate failed offset={spec[0]} limit={spec[1]} returncode={returncode}")
            completed_chunk_reports.append(chunk_report_path)
        running = still_running

    chunk_reports = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(completed_chunk_reports)]

    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            expected_counts = _aggregate_table_expectations(entries)
            actual_counts = _fetch_global_actual_counts(cur)

    table_counts = {
        table_name: {
            "expected": expected_counts.get(table_name, 0),
            "actual": actual_counts.get(table_name, 0),
        }
        for table_name in TABLE_NAMES
    }

    blocking_issues = []
    source_issues = []
    for chunk_report in chunk_reports:
        blocking_issues.extend(chunk_report.get("blocking_issues", []))
        source_issues.extend(chunk_report.get("source_issues", []))

    for table_name, counts in table_counts.items():
        if counts["expected"] != counts["actual"]:
            blocking_issues.append(
                {
                    "type": "raw_ingest" if table_name.startswith("raw_") else "normalized_logic",
                    "scope": "global",
                    "code": f"table_count_mismatch:{table_name}",
                    "message": f"{table_name} expected {counts['expected']}, got {counts['actual']}",
                }
            )

    blocking_issue_types = dict(Counter(issue["type"] for issue in blocking_issues))
    source_issue_types = dict(Counter(issue["type"] for issue in source_issues))
    final_report = {
        "ok": not blocking_issues,
        "loaded_game_count": total,
        "table_counts": table_counts,
        "blocking_issue_count": len(blocking_issues),
        "source_issue_count": len(source_issues),
        "blocking_issue_types": blocking_issue_types,
        "source_issue_types": source_issue_types,
        "blocking_issues": blocking_issues,
        "source_issues": source_issues,
        "chunk_reports": [path.as_posix() for path in sorted(completed_chunk_reports)],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"parallel validate finished loaded_games={final_report['loaded_game_count']} "
        f"blocking_issues={final_report['blocking_issue_count']} source_issues={final_report['source_issue_count']}"
    )
    return 0 if final_report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
