from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

import psycopg

from gui.jobs import JobContext, JobResult
from gui.state import GameOption
from src.kbo_ingest.db import create_schema, reset_database
from src.kbo_ingest.manifest import build_manifest, load_manifest, resolve_stage_sizes, write_manifest
from src.kbo_ingest.pipeline import load_one_game
from src.kbo_ingest.runner import run_sampling_loop
from src.kbo_ingest.validation import validate_loaded_entries, validate_loaded_entries_parallel

class DatabaseService:
    def connect(self, dsn: str) -> psycopg.Connection:
        conn = psycopg.connect(dsn)
        conn.autocommit = True
        return conn

    def list_games(self, conn: psycopg.Connection, *, limit: int = 500, search: str | None = None, offset: int = 0) -> list[GameOption]:
        where_sql = ""
        params: list[Any] = []
        if search:
            where_sql = """
            WHERE CAST(g.game_id AS text) ILIKE %s
               OR COALESCE(at.team_name_short, '') ILIKE %s
               OR COALESCE(ht.team_name_short, '') ILIKE %s
            """
            like = f"%{search}%"
            params.extend([like, like, like])
        params.extend([limit, offset])
        query = f"""
        SELECT g.game_id,
               COALESCE(to_char(g.game_date,'YYYY-MM-DD'),'NO_DATE') || ' | ' ||
               COALESCE(at.team_name_short,'AWAY') || ' vs ' || COALESCE(ht.team_name_short,'HOME') ||
               ' | game_id=' || g.game_id::text AS label
        FROM games g
        LEFT JOIN teams at ON at.team_id = g.away_team_id
        LEFT JOIN teams ht ON ht.team_id = g.home_team_id
        {where_sql}
        ORDER BY g.game_date DESC NULLS LAST, g.game_id DESC
        LIMIT %s OFFSET %s
        """
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [GameOption(game_id=row[0], label=row[1]) for row in rows]


class IngestionService:
    def _load_paths(self, conn: psycopg.Connection, paths: list[Path], context: JobContext) -> None:
        total = max(1, len(paths))
        for index, path in enumerate(paths, start=1):
            context.check_cancelled()
            load_one_game(conn, path)
            if index % 10 == 0 or index == len(paths):
                context.set_progress(index / total, f"loaded {index}/{len(paths)}")

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
        context: JobContext,
    ) -> JobResult:
        manifest = build_manifest(data_dir, seasons=seasons, seed=seed, project_root=project_root)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_manifest(manifest, output_path)
        context.set_progress(1.0, "manifest created")
        return JobResult(
            summary="Manifest created",
            detail=f"games={manifest['total_games']}",
            artifacts={"manifest_path": str(output_path)},
            metrics={"total_games": manifest["total_games"]},
        )

    def create_schema_job(self, *, dsn: str, schema_path: Path, reset_first: bool, context: JobContext) -> JobResult:
        with psycopg.connect(dsn) as conn:
            if reset_first:
                context.log("info", "resetting database")
                reset_database(conn)
            context.log("info", "creating schema", schema_path=str(schema_path))
            create_schema(conn, schema_path)
        context.set_progress(1.0, "schema ready")
        return JobResult(summary="Schema ready", detail=str(schema_path))

    def ingest_manifest_job(
        self,
        *,
        dsn: str,
        manifest_path: Path,
        schema_path: Path,
        report_path: Path,
        reset_first: bool,
        validate_after_load: bool,
        context: JobContext,
    ) -> JobResult:
        entries = load_manifest(manifest_path)["entries"]
        load_started = time.perf_counter()
        with psycopg.connect(dsn) as conn:
            if reset_first:
                context.log("info", "resetting database")
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
        context.set_progress(1.0, "ingest finished")
        return JobResult(
            summary="Manifest ingested",
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
        context: JobContext,
    ) -> JobResult:
        entries = load_manifest(manifest_path)["entries"]
        context.log("info", "validating manifest", entries=len(entries), workers=workers)
        if workers > 1:
            report = validate_loaded_entries_parallel(dsn, entries, workers=workers)
        else:
            with psycopg.connect(dsn) as conn:
                report = validate_loaded_entries(conn, entries)
        self._write_report(report_path, report)
        context.set_progress(1.0, "validation finished")
        return JobResult(
            summary="Validation finished",
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
        context: JobContext,
    ) -> JobResult:
        manifest = load_manifest(manifest_path)
        stage_sizes = resolve_stage_sizes(len(manifest["entries"]), batch_sizes)
        report_dir.mkdir(parents=True, exist_ok=True)
        stage_reports: list[dict[str, Any]] = []
        total = max(1, len(stage_sizes))
        for index, stage_size in enumerate(stage_sizes, start=1):
            context.check_cancelled()
            context.log("info", "running sample stage", stage_size=stage_size)
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
        return JobResult(
            summary="Sample loop finished",
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
        context: JobContext,
    ) -> JobResult:
        files = sorted(data_dir.rglob("*.json"))
        with psycopg.connect(dsn) as conn:
            if reset_first:
                reset_database(conn)
            create_schema(conn, schema_path)
            self._load_paths(conn, files, context)
        return JobResult(summary="Directory ingested", detail=f"files={len(files)}")
