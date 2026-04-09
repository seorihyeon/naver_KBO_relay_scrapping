from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from pathlib import Path
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.components import DatePicker, FileSelector, HorizontalToolbar, LogPanel, ProgressPanel, SummaryCard
from gui.jobs import JobEvent, JobHandle, JobResult, JobRunner, JobSnapshot
from gui.state import AppState
from gui.tags import TagNamespace
from services.collection_service import CollectionRequest, CollectionService, CollectionTarget


@dataclass
class CollectionViewModel:
    mode: str = "period"
    save_dir: str = "games"
    timeout_seconds: int = 8
    retry_count: int = 3
    headless: bool = True
    start_date: str = dt.date.today().strftime("%Y-%m-%d")
    end_date: str = dt.date.today().strftime("%Y-%m-%d")
    single_date: str = dt.date.today().strftime("%Y-%m-%d")
    season_year: str = str(dt.date.today().year)


class CollectionTab:
    key = "collection"
    label = "수집"

    def __init__(self, state: AppState, job_runner: JobRunner | None = None, request_layout: Callable[[], None] | None = None):
        self.state = state
        self.job_runner = job_runner or JobRunner()
        self.request_layout = request_layout or (lambda: None)
        self.namespace = TagNamespace("collection")
        self.view_model = CollectionViewModel(save_dir="games")
        self.service = CollectionService()
        self.date_picker = DatePicker(self.namespace.child("date_picker"))
        self.save_dir_selector = FileSelector(
            self.namespace.child("save_dir"),
            label="저장 경로",
            default_value=self.view_model.save_dir,
            directory=True,
            width=420,
        )
        self.progress_panel = ProgressPanel(self.namespace.child("progress"), default_message="수집 대기 중")
        self.log_panel = LogPanel(self.namespace.child("logs"), height=240, title="수집 작업 로그")
        self.summary_card = SummaryCard(self.namespace.child("summary"), title="마지막 실행 요약", default_text="아직 실행 기록이 없습니다")
        self.mode_toolbar = HorizontalToolbar(self._tag("mode_toolbar"))
        self.period_toolbar = HorizontalToolbar(self._tag("period_group"))
        self.single_toolbar = HorizontalToolbar(self._tag("single_group"))
        self.season_toolbar = HorizontalToolbar(self._tag("season_group"))
        self.options_toolbar = HorizontalToolbar(self._tag("options_toolbar"))
        self.action_toolbar = HorizontalToolbar(self._tag("action_toolbar"))
        self.current_job: JobHandle | None = None
        self.last_failed_targets: list[CollectionTarget] = []

    def _tag(self, name: str) -> str:
        return self.namespace(name)

    def build(self, parent: str) -> None:
        today = dt.date.today().strftime("%Y-%m-%d")
        self.view_model.start_date = today
        self.view_model.end_date = today
        self.view_model.single_date = today
        with dpg.tab(label=self.label, parent=parent, tag=self._tag("tab")):
            dpg.add_text("Naver KBO 경기 JSON을 수집하고 정상/이상/실패 결과를 구분해 저장합니다.")

            mode_row = self.mode_toolbar.build()
            dpg.add_text("수집 방식", parent=mode_row)
            dpg.add_radio_button(
                items=["기간", "단일 날짜", "시즌"],
                tag=self._tag("mode"),
                default_value="기간",
                horizontal=True,
                parent=mode_row,
                callback=lambda: self._apply_mode_from_ui(),
            )

            period_row = self.period_toolbar.build()
            dpg.add_text("시작일", parent=period_row)
            dpg.add_input_text(tag=self._tag("start_date"), width=120, readonly=True, default_value=today, parent=period_row)
            dpg.add_button(label="선택", width=48, parent=period_row, callback=lambda: self.date_picker.open(self._tag("start_date")))
            dpg.add_button(label="오늘", width=56, parent=period_row, callback=lambda: dpg.set_value(self._tag("start_date"), today))
            dpg.add_text("종료일", parent=period_row)
            dpg.add_input_text(tag=self._tag("end_date"), width=120, readonly=True, default_value=today, parent=period_row)
            dpg.add_button(label="선택", width=48, parent=period_row, callback=lambda: self.date_picker.open(self._tag("end_date")))
            dpg.add_button(label="오늘", width=56, parent=period_row, callback=lambda: dpg.set_value(self._tag("end_date"), today))

            single_row = self.single_toolbar.build()
            dpg.configure_item(self.single_toolbar.tag, show=False)
            dpg.add_text("날짜", parent=single_row)
            dpg.add_input_text(tag=self._tag("single_date"), width=120, readonly=True, default_value=today, parent=single_row)
            dpg.add_button(label="선택", width=48, parent=single_row, callback=lambda: self.date_picker.open(self._tag("single_date")))
            dpg.add_button(label="오늘", width=56, parent=single_row, callback=lambda: dpg.set_value(self._tag("single_date"), today))

            season_row = self.season_toolbar.build()
            dpg.configure_item(self.season_toolbar.tag, show=False)
            dpg.add_text("시즌 연도", parent=season_row)
            dpg.add_combo(
                tag=self._tag("season_year"),
                width=120,
                items=[str(year) for year in range(2020, dt.date.today().year + 1)],
                default_value=str(dt.date.today().year),
                parent=season_row,
            )

            self.save_dir_selector.build()

            options_row = self.options_toolbar.build()
            dpg.add_text("타임아웃", parent=options_row)
            dpg.add_input_int(tag=self._tag("timeout"), width=80, default_value=8, min_value=2, max_value=60, parent=options_row)
            dpg.add_text("재시도", parent=options_row)
            dpg.add_input_int(tag=self._tag("retry"), width=80, default_value=3, min_value=1, max_value=20, parent=options_row)
            dpg.add_checkbox(tag=self._tag("headless"), label="헤드리스 브라우저", default_value=True, parent=options_row)

            action_row = self.action_toolbar.build()
            dpg.add_button(tag=self._tag("start_button"), label="수집 시작", width=140, parent=action_row, callback=lambda: self.start_collection())
            dpg.add_button(tag=self._tag("cancel_button"), label="취소", width=100, parent=action_row, callback=lambda: self.cancel_collection(), enabled=False)
            dpg.add_button(tag=self._tag("retry_failed_button"), label="실패 재시도", width=120, parent=action_row, callback=lambda: self.retry_failed_collection(), enabled=False)

            self.progress_panel.build()
            self.summary_card.build()

            dpg.add_spacer(height=8)
            dpg.add_text("일자별 수집 결과")
            with dpg.table(
                header_row=True,
                tag=self._tag("result_table"),
                policy=dpg.mvTable_SizingStretchProp,
                row_background=True,
                borders_innerH=True,
                borders_outerH=True,
                borders_innerV=True,
                borders_outerV=True,
                height=140,
            ):
                for label in [
                    "날짜",
                    "경기 수",
                    "정상",
                    "이상",
                    "실패",
                    "재사용",
                    "이상 파일",
                    "이상 사유",
                    "실패 파일",
                    "실패 사유",
                ]:
                    dpg.add_table_column(label=label)

            self.log_panel.build()
        self.date_picker.build()

    def _apply_mode_from_ui(self) -> None:
        mode_value = dpg.get_value(self._tag("mode"))
        mode_map = {"기간": "period", "단일 날짜": "single", "시즌": "season"}
        self.view_model.mode = mode_map.get(mode_value, "period")
        dpg.configure_item(self.period_toolbar.tag, show=self.view_model.mode == "period")
        dpg.configure_item(self.single_toolbar.tag, show=self.view_model.mode == "single")
        dpg.configure_item(self.season_toolbar.tag, show=self.view_model.mode == "season")
        self.request_layout()

    def apply_responsive_layout(self, content_w: int, content_h: int) -> None:
        available_w = max(720, int(content_w) - 36)
        toolbar_width = max(220, available_w)
        for toolbar in (self.mode_toolbar, self.period_toolbar, self.single_toolbar, self.season_toolbar, self.options_toolbar, self.action_toolbar):
            toolbar.set_width(toolbar_width)
        if dpg.does_item_exist(self._tag("root_dir")):
            dpg.configure_item(self._tag("root_dir"), width=max(220, min(420, int(available_w * 0.3))))
        save_dir_w = max(220, min(520, available_w - 180))
        log_h = max(120, int(content_h) - 460)
        self.save_dir_selector.set_width(save_dir_w)
        self.log_panel.set_height(log_h)

    def _read_form(self) -> CollectionRequest:
        mode = self.view_model.mode
        if mode == "single":
            start_date = end_date = dt.datetime.strptime(dpg.get_value(self._tag("single_date")), "%Y-%m-%d").date()
            season_year = None
        elif mode == "season":
            season_year = int(dpg.get_value(self._tag("season_year")))
            start_date = dt.date(season_year, 1, 1)
            end_date = dt.date(season_year, 12, 31)
        else:
            start_date = dt.datetime.strptime(dpg.get_value(self._tag("start_date")), "%Y-%m-%d").date()
            end_date = dt.datetime.strptime(dpg.get_value(self._tag("end_date")), "%Y-%m-%d").date()
            season_year = None
        if end_date < start_date:
            raise ValueError("end date must be on or after start date")
        save_dir = Path(self.save_dir_selector.get_value() or "games")
        return CollectionRequest(
            mode=mode,
            save_dir=save_dir,
            timeout_seconds=int(dpg.get_value(self._tag("timeout"))),
            retry_count=int(dpg.get_value(self._tag("retry"))),
            headless=bool(dpg.get_value(self._tag("headless"))),
            start_date=start_date,
            end_date=end_date,
            season_year=season_year,
        )

    def start_collection(self) -> None:
        if self.current_job and (snapshot := self.job_runner.get_snapshot(self.current_job.job_id)) and not snapshot.is_terminal:
            self.state.set_status("warn", "수집 작업이 이미 실행 중입니다", "현재 작업이 끝난 뒤 다시 시도해 주세요.", source=self.label)
            return
        try:
            request = self._read_form()
        except ValueError as exc:
            self.state.set_status("warn", "수집 입력값이 올바르지 않습니다", str(exc), source=self.label)
            return

        self.log_panel.clear()
        self._set_controls_enabled(running=True)
        self.progress_panel.set_state(message="수집을 시작하는 중...", progress=0.0, overlay="0%")
        self.summary_card.set_text("수집 작업을 시작하는 중입니다")
        self.current_job = self.job_runner.start_job(
            name="KBO 수집",
            source=self.label,
            worker=lambda ctx: self.service.run(request, ctx),
            listener=self._handle_job_event,
        )
        self.state.set_status(
            "info",
            "수집 작업을 시작했습니다",
            f"수집 방식={self._mode_label(request.mode)} 저장 경로={request.save_dir}",
            source=self.label,
            append=False,
        )

    def retry_failed_collection(self) -> None:
        if not self.last_failed_targets:
            self.state.set_status("warn", "재시도할 실패 대상이 없습니다", source=self.label)
            return
        request = self._read_form()
        request = CollectionRequest(
            **{**request.__dict__, "targets": list(self.last_failed_targets)},
        )
        self.log_panel.clear()
        self._set_controls_enabled(running=True)
        self.current_job = self.job_runner.start_job(
            name="실패 재수집",
            source=self.label,
            worker=lambda ctx: self.service.run(request, ctx),
            listener=self._handle_job_event,
        )
        self.state.set_status("info", "실패 경기 재시도", f"targets={len(self.last_failed_targets)}", source=self.label, append=False)

    def cancel_collection(self) -> None:
        if self.current_job is None:
            return
        self.job_runner.cancel(self.current_job.job_id)
        self.state.set_status("warn", "수집 취소를 요청했습니다", source=self.label)

    def _handle_job_event(self, event: JobEvent, snapshot: JobSnapshot) -> None:
        if event.kind == "log":
            self.log_panel.append(event.payload)
            channel = "error" if event.payload.level == "error" else "info"
            self.state.set_status(channel, event.payload.message, source=self.label)
            return
        if event.kind == "progress":
            progress = float(event.payload.get("progress", 0.0))
            message = event.payload.get("message") or "수집 진행 중"
            self.progress_panel.set_state(message=message, progress=progress)
            self.state.set_status("info", "수집 진행 중", message, source=self.label)
            return
        if event.kind == "result":
            metrics = event.payload.metrics
            self.last_failed_targets = list(metrics.get("failed_targets", metrics.get("failed_target_items", [])))
            self.summary_card.set_text(self._build_summary_text(event.payload))
            self._render_day_logs(metrics.get("day_logs", []))
            if dpg.does_item_exist(self._tag("retry_failed_button")):
                dpg.configure_item(self._tag("retry_failed_button"), enabled=bool(self.last_failed_targets))
            return
        if event.kind == "completed":
            self._set_controls_enabled(running=False)
            self.progress_panel.set_state(message="수집이 완료되었습니다", progress=1.0, overlay="완료")
            self.state.set_status("info", "수집 완료", snapshot.latest_message, source=self.label, append=False)
            return
        if event.kind == "cancelled":
            self._set_controls_enabled(running=False)
            self.progress_panel.set_state(message="수집이 취소되었습니다", progress=snapshot.progress, overlay="취소")
            self.state.set_status("warn", "수집 취소", source=self.label, append=False)
            return
        if event.kind == "failed":
            self._set_controls_enabled(running=False)
            self.progress_panel.set_state(message="수집이 실패했습니다", progress=snapshot.progress, overlay="실패")
            self.summary_card.set_text(f"수집 실패\n{event.payload['message']}")
            self.state.set_status(
                "error",
                "수집 실패",
                event.payload["message"],
                debug_detail=event.payload["traceback"],
                source=self.label,
                append=False,
            )

    def _render_day_logs(self, day_logs: list[object]) -> None:
        table_tag = self._tag("result_table")
        if not dpg.does_item_exist(table_tag):
            return
        dpg.delete_item(table_tag, children_only=True, slot=1)
        for record in day_logs:
            with dpg.table_row(parent=table_tag):
                dpg.add_text(record.game_date)
                dpg.add_text(str(record.game_count))
                dpg.add_text(str(record.success_count), color=(120, 220, 140))
                dpg.add_text(str(record.anomaly_count), color=(255, 186, 92))
                dpg.add_text(str(record.failure_count), color=(255, 110, 110))
                dpg.add_text(str(record.skipped_count))
                dpg.add_text(", ".join(record.anomaly_files[:2]) or "-")
                dpg.add_text(" | ".join(record.anomaly_reasons[:1]) or "-")
                dpg.add_text(", ".join(record.failed_files[:2]) or "-")
                dpg.add_text(" | ".join(record.failed_reasons[:1]) or "-")

    def _build_summary_text(self, result: JobResult) -> str:
        metrics = result.metrics or {}
        artifacts = result.artifacts or {}
        detail = result.detail or (
            f"전체 {metrics.get('games', 0)}경기, 정상 {metrics.get('success_count', 0)}, "
            f"이상 {metrics.get('anomaly_count', 0)}, 실패 {metrics.get('failure_count', 0)}, "
            f"재사용 {metrics.get('skipped_count', 0)}"
        )
        failed_target_count = metrics.get("failed_target_count", len(metrics.get("failed_targets", [])))
        return (
            f"{result.summary}\n"
            f"{detail}\n"
            f"실패 재시도 대상: {failed_target_count}\n"
            f"이상 데이터: 수집은 되었지만 검증에서 문제나 경고가 확인된 경기\n"
            f"정상 저장 경로: {artifacts.get('save_dir', '-')}\n"
            f"이상 저장 경로: {artifacts.get('anomaly_dir', '-')}\n"
            f"디버그 로그: {self._display_path_if_exists(artifacts.get('debug_log_path'))}\n"
            f"이상 로그: {self._display_path_if_exists(artifacts.get('anomaly_log_path'))}\n"
            f"실패 로그: {self._display_path_if_exists(artifacts.get('failure_log_path'))}"
        )

    def _display_path_if_exists(self, path_text: str | None) -> str:
        if not path_text:
            return "-"
        return path_text if Path(path_text).exists() else "없음"

    def _mode_label(self, mode: str) -> str:
        return {"period": "기간", "single": "단일 날짜", "season": "시즌"}.get(mode, mode)

    def _set_controls_enabled(self, *, running: bool) -> None:
        disabled_tags = [
            self._tag("mode"),
            self._tag("start_date"),
            self._tag("end_date"),
            self._tag("single_date"),
            self._tag("season_year"),
            self._tag("timeout"),
            self._tag("retry"),
            self._tag("headless"),
            self._tag("start_button"),
        ]
        for tag in disabled_tags:
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=not running)
        if dpg.does_item_exist(self._tag("cancel_button")):
            dpg.configure_item(self._tag("cancel_button"), enabled=running)
