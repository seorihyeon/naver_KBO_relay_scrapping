"""Service-layer orchestration for manifests, database setup, and ingestion workflows."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

import psycopg

from infrastructure.postgres_repository import GameCatalogRepository, PostgresConnectionFactory
from services.common import GameOption, ProgressReporter, ServiceResult
from src.kbo_ingest.db import create_schema, reset_database
from src.kbo_ingest.manifest import build_manifest, load_manifest, resolve_stage_sizes, write_manifest
from src.kbo_ingest.pipeline import load_one_game
from src.kbo_ingest.runner import run_sampling_loop
from src.kbo_ingest.validation import validate_loaded_entries, validate_loaded_entries_parallel


class DatabaseService:
    """Small service facade for GUI-driven DB connections and game lookup."""

    def __init__(self, *, connection_factory: PostgresConnectionFactory | None = None) -> None:
        self.connection_factory = connection_factory or PostgresConnectionFactory()

    def connect(self, dsn: str) -> psycopg.Connection:
        return self.connection_factory.connect(dsn)

    def list_games(
        self,
        conn: psycopg.Connection,
        *,
        limit: int = 500,
        search: str | None = None,
        offset: int = 0,
    ) -> list[GameOption]:
        return GameCatalogRepository(conn).list_games(limit=limit, search=search, offset=offset)


class IngestionService:
    """Coordinates manifest generation, schema setup, loading, and validation."""

    def _load_paths(self, conn: psycopg.Connection, paths: list[Path], context: ProgressReporter) -> None:
        total = max(1, len(paths))
        for index, path in enumerate(paths, start=1):
            context.check_cancelled()
            load_one_game(conn, path)
            if index % 10 == 0 or index == len(paths):
                context.set_progress(index / total, f"{index}/{len(paths)} files loaded")

    def _write_report(self, report_path: Path, report: dict[str, Any]) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_manifest_job(
        self,
        *,
        data_dir: Path,
        seasons: tuple[str, ...],
        output_path: Path,
        seed: int,
        project_root: Path,
        context: ProgressReporter,
    ) -> ServiceResult:
        manifest = build_manifest(data_dir, seasons=seasons, seed=seed, project_root=project_root)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_manifest(manifest, output_path)
        context.set_progress(1.0, "manifest written")
        return ServiceResult(
            summary="留ㅻ땲?섏뒪???앹꽦 ?꾨즺",
            detail=f"total_games={manifest['total_games']}",
            artifacts={"manifest_path": str(output_path)},
            metrics={"total_games": manifest["total_games"]},
        )

    def create_schema_job(self, *, dsn: str, schema_path: Path, reset_first: bool, context: ProgressReporter) -> ServiceResult:
        with psycopg.connect(dsn) as conn:
            if reset_first:
                context.log("info", "resetting database before schema creation")
                reset_database(conn)
            context.log("info", "creating schema", schema_path=str(schema_path))
            create_schema(conn, schema_path)
        context.set_progress(1.0, "schema ready")
        return ServiceResult(summary="?ㅽ궎留?以鍮??꾨즺", detail=str(schema_path))

    def ingest_manifest_job(
        self,
        *,
        dsn: str,
        manifest_path: Path,
        schema_path: Path,
        report_path: Path,
        reset_first: bool,
        validate_after_load: bool,
        context: ProgressReporter,
    ) -> ServiceResult:
        entries = load_manifest(manifest_path)["entries"]
        load_started = time.perf_counter()
        with psycopg.connect(dsn) as conn:
            if reset_first:
                context.log("info", "resetting database before manifest ingest")
                reset_database(conn)
            create_schema(conn, schema_path)
            self._load_paths(conn, [Path(entry["path"]) for entry in entries], context)
            conn.commit()
            validation_started = time.perf_counter()
            if validate_after_load:
                report = validate_loaded_entries(conn, entries)
            else:
                report = {
                    "ok": True,
                    "loaded_game_count": len(entries),
                    "blocking_issue_count": 0,
                    "source_issue_count": 0,
                    "blocking_issues": [],
                    "source_issues": [],
                    "table_counts": {},
                }
            report["load_seconds"] = time.perf_counter() - load_started
            report["validation_seconds"] = time.perf_counter() - validation_started if validate_after_load else 0.0
            report["report_json_path"] = report_path.as_posix()
            self._write_report(report_path, report)
        context.set_progress(1.0, "manifest ingest completed")
        return ServiceResult(
            summary="留ㅻ땲?섏뒪???곸옱 ?꾨즺",
            detail=f"loaded={report['loaded_game_count']} blocking={report['blocking_issue_count']}",
            artifacts={"report_path": str(report_path)},
            metrics={
                "loaded_game_count": report["loaded_game_count"],
                "blocking_issue_count": report["blocking_issue_count"],
                "source_issue_count": report["source_issue_count"],
            },
        )

    def validate_manifest_job(
        self,
        *,
        dsn: str,
        manifest_path: Path,
        report_path: Path,
        workers: int,
        context: ProgressReporter,
    ) -> ServiceResult:
        entries = load_manifest(manifest_path)["entries"]
        context.log("info", "validating manifest", entries=len(entries), workers=workers)
        if workers > 1:
            report = validate_loaded_entries_parallel(dsn, entries, workers=workers)
        else:
            with psycopg.connect(dsn) as conn:
                report = validate_loaded_entries(conn, entries)
        self._write_report(report_path, report)
        context.set_progress(1.0, "manifest validation completed")
        return ServiceResult(
            summary="寃利??꾨즺",
            detail=f"blocking={report['blocking_issue_count']} source={report['source_issue_count']}",
            artifacts={"report_path": str(report_path)},
            metrics={
                "loaded_game_count": report["loaded_game_count"],
                "blocking_issue_count": report["blocking_issue_count"],
                "source_issue_count": report["source_issue_count"],
            },
        )

    def sample_loop_job(
        self,
        *,
        dsn: str,
        manifest_path: Path,
        schema_path: Path,
        report_dir: Path,
        batch_sizes: list[int] | None,
        context: ProgressReporter,
    ) -> ServiceResult:
        manifest = load_manifest(manifest_path)
        stage_sizes = resolve_stage_sizes(len(manifest["entries"]), batch_sizes)
        report_dir.mkdir(parents=True, exist_ok=True)
        stage_reports: list[dict[str, Any]] = []
        total = max(1, len(stage_sizes))
        for index, stage_size in enumerate(stage_sizes, start=1):
            context.check_cancelled()
            context.log("info", "running sample-loop stage", stage_size=stage_size)
            summary = run_sampling_loop(
                dsn,
                {"seed": manifest["seed"], "total_games": manifest["total_games"], "entries": manifest["entries"][:stage_size]},
                schema_path=schema_path,
                report_dir=report_dir / f"stage_{stage_size:04d}",
                batch_sizes=[stage_size],
            )
            stage_reports.extend(summary["stage_reports"])
            context.set_progress(index / total, f"stage {index}/{len(stage_sizes)}")
            if not summary["completed_all_stages"]:
                break
        final_summary_path = report_dir / "sampling_summary.json"
        final_summary_path.write_text(
            json.dumps({"stage_reports": stage_reports}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return ServiceResult(
            summary="?섑뵆 猷⑦봽 ?꾨즺",
            detail=f"stages={len(stage_reports)}",
            artifacts={"summary_path": str(final_summary_path)},
            metrics={"stages": len(stage_reports)},
        )

    def legacy_directory_load_job(
        self,
        *,
        dsn: str,
        data_dir: Path,
        schema_path: Path,
        reset_first: bool,
        context: ProgressReporter,
    ) -> ServiceResult:
        files = sorted(data_dir.rglob("*.json"))
        with psycopg.connect(dsn) as conn:
            if reset_first:
                reset_database(conn)
            create_schema(conn, schema_path)
            self._load_paths(conn, files, context)
        return ServiceResult(summary="?붾젆?곕━ ?곸옱 ?꾨즺", detail=f"files={len(files)}")
