from __future__ import annotations

from pathlib import Path
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.components import FileSelector, LogPanel, ProgressPanel, SummaryCard
from gui.ingestion_service import DatabaseService, IngestionService
from gui.jobs import JobEvent, JobHandle, JobRunner, JobSnapshot
from gui.tags import GLOBAL_TAGS, TagNamespace
from .shared_state import AppState


class IngestionTab:
    key = "ingestion"
    label = "Ingestion"

    def __init__(self, state: AppState, job_runner: JobRunner | None = None, request_layout: Callable[[], None] | None = None):
        self.state = state
        self.job_runner = job_runner or JobRunner()
        self.request_layout = request_layout or (lambda: None)
        self.namespace = TagNamespace("ingestion")
        self.db_service = DatabaseService()
        self.ingestion_service = IngestionService()
        self.data_dir_selector = FileSelector(
            self.namespace.child("data_dir"),
            label="Data dir",
            default_value=self.state.default_data_dir,
            directory=True,
            width=420,
        )
        self.manifest_selector = FileSelector(
            self.namespace.child("manifest"),
            label="Manifest",
            default_value="reports/gui_manifest.json",
            directory=False,
            width=420,
        )
        self.schema_selector = FileSelector(
            self.namespace.child("schema"),
            label="Schema",
            default_value=self.state.default_schema_path,
            directory=False,
            width=320,
        )
        self.report_dir_selector = FileSelector(
            self.namespace.child("report_dir"),
            label="Report dir",
            default_value="reports/gui",
            directory=True,
            width=360,
        )
        self.progress_panel = ProgressPanel(self.namespace.child("progress"), default_message="No ingestion job running")
        self.log_panel = LogPanel(self.namespace.child("logs"), height=240, title="Ingestion job log")
        self.summary_card = SummaryCard(self.namespace.child("summary"), title="Last ingestion result", default_text="No run yet")
        self.current_job: JobHandle | None = None

    def _tag(self, name: str) -> str:
        return self.namespace(name)

    def build(self, parent: str) -> None:
        with dpg.tab(label=self.label, parent=parent, tag=self._tag("tab")):
            dpg.add_text("Manage schema creation, manifest builds, ingestion, validation, and sample-loop jobs.")
            dpg.add_text("DB connection", color=(180, 180, 180))
            dpg.add_text("Disconnected", tag=self._tag("connection_status"), color=(255, 195, 90))
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag=self._tag("game_search"), width=240, hint="Search games")
                dpg.add_button(label="Refresh game list", callback=lambda: self.refresh_games())
            self.data_dir_selector.build()
            self.manifest_selector.build()
            with dpg.group(horizontal=True):
                self.schema_selector.build()
                self.report_dir_selector.build()
            with dpg.group(horizontal=True):
                dpg.add_button(tag=self._tag("manifest_button"), label="Build manifest", callback=lambda: self.start_manifest_job())
                dpg.add_button(tag=self._tag("schema_button"), label="Create schema", callback=lambda: self.start_schema_job(reset_first=False))
                dpg.add_button(tag=self._tag("reset_schema_button"), label="Reset + schema", callback=lambda: self.start_schema_job(reset_first=True))
            with dpg.group(horizontal=True):
                dpg.add_button(tag=self._tag("load_manifest_button"), label="Load manifest", callback=lambda: self.start_manifest_ingest_job())
                dpg.add_button(tag=self._tag("load_dir_button"), label="Load directory", callback=lambda: self.start_directory_ingest_job())
                dpg.add_button(tag=self._tag("validate_button"), label="Validate", callback=lambda: self.start_validate_job())
                dpg.add_button(tag=self._tag("sample_loop_button"), label="Sample loop", callback=lambda: self.start_sample_loop_job())
                dpg.add_button(tag=self._tag("cancel_button"), label="Cancel", enabled=False, callback=lambda: self.cancel_job())
            dpg.add_input_int(tag=self._tag("workers"), width=80, default_value=1, min_value=1, max_value=8)
            self.progress_panel.build()
            self.summary_card.build()
            dpg.add_text("Recent report path")
            dpg.add_text("-", tag=self._tag("report_path_text"), wrap=500)
            self.log_panel.build()

    def apply_responsive_layout(self, content_w: int, content_h: int) -> None:
        available_w = max(720, int(content_w) - 36)
        selector_w = max(240, min(520, available_w - 180))
        self.data_dir_selector.set_width(selector_w)
        self.manifest_selector.set_width(selector_w)
        self.schema_selector.set_width(max(220, min(360, int(available_w * 0.35))))
        self.report_dir_selector.set_width(max(220, min(360, int(available_w * 0.35))))
        self.log_panel.set_height(max(120, int(content_h) - 420))

    def connect_db(self) -> None:
        dsn = dpg.get_value(GLOBAL_TAGS.dsn_input).strip()
        self.state.set_db_connection_indicator("Connecting...", "info")
        try:
            if self.state.conn:
                try:
                    self.state.conn.close()
                except Exception:
                    pass
            self.state.conn = self.db_service.connect(dsn)
            self.state.set_db_connection_indicator("Connected", "info")
            if dpg.does_item_exist(self._tag("connection_status")):
                dpg.set_value(self._tag("connection_status"), "Connected")
                dpg.configure_item(self._tag("connection_status"), color=(120, 220, 140))
            self.state.set_status("info", "DB connected", "Game list refreshed.", source=self.label, append=False)
            self.refresh_games()
        except Exception as exc:
            self.state.conn = None
            self.state.set_db_connection_indicator("Connection failed", "error")
            if dpg.does_item_exist(self._tag("connection_status")):
                dpg.set_value(self._tag("connection_status"), "Connection failed")
                dpg.configure_item(self._tag("connection_status"), color=(255, 110, 110))
            self.state.set_status(
                "error",
                "DB connection failed",
                "Check the DSN and PostgreSQL status.",
                debug_detail=str(exc),
                source=self.label,
                append=False,
            )

    def refresh_games(self) -> None:
        if not self.state.conn:
            return
        search = dpg.get_value(self._tag("game_search")) if dpg.does_item_exist(self._tag("game_search")) else ""
        games = self.db_service.list_games(self.state.conn, limit=500, search=search or None, offset=0)
        self.state.set_games(games)
        self.summary_card.set_text(f"Connected\nloaded game options: {len(games)}")
        self.state.set_status("info", "Game list refreshed", f"count={len(games)}", source=self.label)

    def start_manifest_job(self) -> None:
        self._start_job(
            name="Build manifest",
            worker=lambda ctx: self.ingestion_service.build_manifest_job(
                data_dir=Path(self.data_dir_selector.get_value()).expanduser(),
                seasons=("2024", "2025"),
                output_path=Path(self.manifest_selector.get_value()).expanduser(),
                seed=20260404,
                project_root=Path.cwd(),
                context=ctx,
            ),
            source_detail=self.manifest_selector.get_value(),
        )

    def start_schema_job(self, *, reset_first: bool) -> None:
        if not dpg.get_value(GLOBAL_TAGS.dsn_input).strip():
            self.state.set_status("warn", "DSN is empty", source=self.label)
            return
        self._start_job(
            name="Schema job",
            worker=lambda ctx: self.ingestion_service.create_schema_job(
                dsn=dpg.get_value(GLOBAL_TAGS.dsn_input).strip(),
                schema_path=Path(self.schema_selector.get_value()).expanduser(),
                reset_first=reset_first,
                context=ctx,
            ),
            source_detail="schema",
        )

    def start_manifest_ingest_job(self) -> None:
        self._start_job(
            name="Ingest manifest",
            worker=lambda ctx: self.ingestion_service.ingest_manifest_job(
                dsn=dpg.get_value(GLOBAL_TAGS.dsn_input).strip(),
                manifest_path=Path(self.manifest_selector.get_value()).expanduser(),
                schema_path=Path(self.schema_selector.get_value()).expanduser(),
                report_path=Path(self.report_dir_selector.get_value()).expanduser() / "manifest_ingest_report.json",
                reset_first=False,
                validate_after_load=True,
                context=ctx,
            ),
            source_detail=self.manifest_selector.get_value(),
        )

    def start_validate_job(self) -> None:
        self._start_job(
            name="Validate manifest",
            worker=lambda ctx: self.ingestion_service.validate_manifest_job(
                dsn=dpg.get_value(GLOBAL_TAGS.dsn_input).strip(),
                manifest_path=Path(self.manifest_selector.get_value()).expanduser(),
                report_path=Path(self.report_dir_selector.get_value()).expanduser() / "manifest_validate_report.json",
                workers=int(dpg.get_value(self._tag("workers"))),
                context=ctx,
            ),
            source_detail=self.manifest_selector.get_value(),
        )

    def start_sample_loop_job(self) -> None:
        self._start_job(
            name="Sample loop",
            worker=lambda ctx: self.ingestion_service.sample_loop_job(
                dsn=dpg.get_value(GLOBAL_TAGS.dsn_input).strip(),
                manifest_path=Path(self.manifest_selector.get_value()).expanduser(),
                schema_path=Path(self.schema_selector.get_value()).expanduser(),
                report_dir=Path(self.report_dir_selector.get_value()).expanduser(),
                batch_sizes=None,
                context=ctx,
            ),
            source_detail=self.report_dir_selector.get_value(),
        )

    def start_directory_ingest_job(self) -> None:
        self._start_job(
            name="Ingest directory",
            worker=lambda ctx: self.ingestion_service.legacy_directory_load_job(
                dsn=dpg.get_value(GLOBAL_TAGS.dsn_input).strip(),
                data_dir=Path(self.data_dir_selector.get_value()).expanduser(),
                schema_path=Path(self.schema_selector.get_value()).expanduser(),
                reset_first=False,
                context=ctx,
            ),
            source_detail=self.data_dir_selector.get_value(),
        )

    def cancel_job(self) -> None:
        if self.current_job is None:
            return
        self.job_runner.cancel(self.current_job.job_id)
        self.state.set_status("warn", "Ingestion cancellation requested", source=self.label)

    def _start_job(self, *, name: str, worker, source_detail: str) -> None:
        if self.current_job and (snapshot := self.job_runner.get_snapshot(self.current_job.job_id)) and not snapshot.is_terminal:
            self.state.set_status("warn", "Another ingestion job is already running", source=self.label)
            return
        self.log_panel.clear()
        self._set_running_state(True)
        self.summary_card.set_text(f"{name}\n{source_detail}")
        self.progress_panel.set_state(message=f"{name} started", progress=0.0, overlay="0%")
        self.current_job = self.job_runner.start_job(
            name=name,
            source=self.label,
            worker=worker,
            listener=self._handle_job_event,
        )
        self.state.set_status("info", name, source_detail, source=self.label, append=False)

    def _handle_job_event(self, event: JobEvent, snapshot: JobSnapshot) -> None:
        if event.kind == "log":
            self.log_panel.append(event.payload)
            self.state.set_status("info", event.payload.message, source=self.label)
            return
        if event.kind == "progress":
            progress = float(event.payload.get("progress", 0.0))
            message = event.payload.get("message") or "Job running"
            self.progress_panel.set_state(message=message, progress=progress)
            self.state.set_status("info", snapshot.name, message, source=self.label)
            return
        if event.kind == "result":
            report_path = event.payload.artifacts.get("report_path") or event.payload.artifacts.get("summary_path") or event.payload.artifacts.get("manifest_path")
            self.summary_card.set_text(f"{event.payload.summary}\n{event.payload.detail or '-'}")
            if report_path and dpg.does_item_exist(self._tag("report_path_text")):
                dpg.set_value(self._tag("report_path_text"), report_path)
            if event.payload.summary in {"Manifest ingested", "Directory ingested"} and self.state.conn:
                self.refresh_games()
            return
        if event.kind == "completed":
            self._set_running_state(False)
            self.progress_panel.set_state(message="Job completed", progress=1.0, overlay="Done")
            self.state.set_status("info", f"{snapshot.name} completed", snapshot.latest_message, source=self.label, append=False)
            return
        if event.kind == "cancelled":
            self._set_running_state(False)
            self.progress_panel.set_state(message="Job cancelled", progress=snapshot.progress, overlay="Cancelled")
            self.state.set_status("warn", f"{snapshot.name} cancelled", source=self.label, append=False)
            return
        if event.kind == "failed":
            self._set_running_state(False)
            self.progress_panel.set_state(message="Job failed", progress=snapshot.progress, overlay="Failed")
            self.summary_card.set_text(f"{snapshot.name} failed\n{event.payload['message']}")
            self.state.set_status(
                "error",
                f"{snapshot.name} failed",
                event.payload["message"],
                debug_detail=event.payload["traceback"],
                source=self.label,
                append=False,
            )

    def _set_running_state(self, running: bool) -> None:
        for tag in (
            self._tag("manifest_button"),
            self._tag("schema_button"),
            self._tag("reset_schema_button"),
            self._tag("load_manifest_button"),
            self._tag("load_dir_button"),
            self._tag("validate_button"),
            self._tag("sample_loop_button"),
        ):
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=not running)
        if dpg.does_item_exist(self._tag("cancel_button")):
            dpg.configure_item(self._tag("cancel_button"), enabled=running)
