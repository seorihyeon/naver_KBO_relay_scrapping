"""PostgreSQL 적재용 워크플로를 묶은 서비스 모듈."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.kbo_ingest.db import create_schema, reset_database
from src.kbo_ingest.manifest import DEFAULT_SEASONS, build_manifest, load_manifest, write_manifest
from src.kbo_ingest.pipeline import load_one_game
from src.kbo_ingest.runner import load_and_validate_entries, run_sampling_loop
from src.kbo_ingest.validation import validate_loaded_entries, validate_loaded_entries_parallel

import psycopg


def _load_entries_from_manifest(manifest_path: Path, limit: int | None = None, offset: int = 0) -> list[dict]:
    manifest = load_manifest(manifest_path)
    entries = manifest["entries"]
    sliced = entries[offset:]
    return sliced[:limit] if limit else sliced


def _build_common_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--schema", default="sql/schema.sql")


def _parse_batch_sizes(raw_values: list[str] | None) -> list[int] | None:
    if not raw_values:
        return None
    result: list[int] = []
    for raw_value in raw_values:
        if raw_value.lower() == "all":
            continue
        result.append(int(raw_value))
    return result


def command_manifest(args: argparse.Namespace) -> int:
    manifest = build_manifest(
        Path(args.data_dir),
        seasons=tuple(args.seasons),
        seed=args.seed,
        project_root=Path.cwd(),
    )
    write_manifest(manifest, Path(args.output))
    print(f"manifest written: {args.output} total_games={manifest['total_games']}")
    return 0


def command_load(args: argparse.Namespace) -> int:
    entries = _load_entries_from_manifest(Path(args.manifest), args.limit, args.offset)
    report = load_and_validate_entries(
        args.dsn,
        entries,
        schema_path=Path(args.schema),
        report_json_path=Path(args.report_json),
        reset_db_first=args.reset_db,
        run_label=args.run_label,
        validate_after_load=not args.skip_validate,
    )
    print(
        f"load finished loaded_games={report['loaded_game_count']} blocking_issues={report['blocking_issue_count']} "
        f"source_issues={report['source_issue_count']}"
    )
    return 0 if report["ok"] else 2


def command_validate(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest))
    entries = manifest["entries"][args.offset :]
    if args.limit:
        entries = entries[: args.limit]
    if args.workers > 1:
        report = validate_loaded_entries_parallel(args.dsn, entries, workers=args.workers)
    else:
        with psycopg.connect(args.dsn) as conn:
            report = validate_loaded_entries(conn, entries)
    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(__import__("json").dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"validate finished loaded_games={report['loaded_game_count']} blocking_issues={report['blocking_issue_count']} "
        f"source_issues={report['source_issue_count']}"
    )
    return 0 if report["ok"] else 2


def command_sample_loop(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest))
    summary = run_sampling_loop(
        args.dsn,
        manifest,
        schema_path=Path(args.schema),
        report_dir=Path(args.report_dir),
        batch_sizes=_parse_batch_sizes(args.batch_sizes),
    )
    print(
        f"sampling loop finished stages={len(summary['stage_reports'])} "
        f"completed_all_stages={summary['completed_all_stages']}"
    )
    return 0 if summary["completed_all_stages"] else 2


def command_legacy(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    files = sorted(data_dir.rglob("*.json"))
    with psycopg.connect(args.dsn) as conn:
        if args.reset_db:
            reset_database(conn)
        if args.create_schema:
            create_schema(conn, Path(args.schema))
        total = 0
        for json_path in files:
            load_one_game(conn, json_path)
            total += 1
            print(f"[load] {total}/{len(files)} {json_path}")
    print(f"done. loaded games={total}")
    return 0


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KBO JSON -> PostgreSQL loader and QA runner")
    subparsers = parser.add_subparsers(dest="command")

    manifest_parser = subparsers.add_parser("manifest", help="build a shuffled manifest with source expectations")
    manifest_parser.add_argument("--data-dir", default="games")
    manifest_parser.add_argument("--seasons", nargs="+", default=list(DEFAULT_SEASONS))
    manifest_parser.add_argument("--seed", type=int, default=20260404)
    manifest_parser.add_argument("--output", required=True)
    manifest_parser.set_defaults(func=command_manifest)

    load_parser = subparsers.add_parser("load", help="reset/create DB, load a manifest slice, and validate it")
    _build_common_parser(load_parser)
    load_parser.add_argument("--manifest", required=True)
    load_parser.add_argument("--offset", type=int, default=0)
    load_parser.add_argument("--limit", type=int)
    load_parser.add_argument("--reset-db", action="store_true")
    load_parser.add_argument("--skip-validate", action="store_true")
    load_parser.add_argument("--report-json", required=True)
    load_parser.add_argument("--run-label", default="KBO Load Validation")
    load_parser.set_defaults(func=command_load)

    validate_parser = subparsers.add_parser("validate", help="validate loaded DB rows against a manifest slice")
    validate_parser.add_argument("--dsn", required=True)
    validate_parser.add_argument("--manifest", required=True)
    validate_parser.add_argument("--offset", type=int, default=0)
    validate_parser.add_argument("--limit", type=int)
    validate_parser.add_argument("--workers", type=int, default=1)
    validate_parser.add_argument("--report-json", required=True)
    validate_parser.set_defaults(func=command_validate)

    loop_parser = subparsers.add_parser("sample-loop", help="run cumulative non-replacement sampling stages")
    _build_common_parser(loop_parser)
    loop_parser.add_argument("--manifest", required=True)
    loop_parser.add_argument("--report-dir", required=True)
    loop_parser.add_argument("--batch-sizes", nargs="*")
    loop_parser.set_defaults(func=command_sample_loop)

    parser.add_argument("--dsn")
    parser.add_argument("--data-dir", default="games")
    parser.add_argument("--schema", default="sql/schema.sql")
    parser.add_argument("--create-schema", action="store_true")
    parser.add_argument("--reset-db", action="store_true")
    return parser


def main() -> int:
    parser = build_cli_parser()
    args = parser.parse_args()
    if hasattr(args, "func"):
        return args.func(args)
    if args.dsn:
        return command_legacy(args)
    parser.print_help()
    return 1
