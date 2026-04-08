from pathlib import Path

import dearpygui.dearpygui as dpg

from gui.jobs import JobRunner
from gui.layout_manager import LayoutManager, compute_shell_layout
from gui.shell_builder import build_shell_ui
from gui.state import AppState
from gui.tabs import build_default_tabs
from gui.tags import GLOBAL_TAGS
from gui.windows import AlertDetailWindow, DbDetailWindow, GlobalAlertWindow, GlobalStatusWindow


class AppShell:
    def __init__(self) -> None:
        self.root_dir = Path(__file__).resolve().parents[1]
        self.state = AppState.from_environment(self.root_dir)
        self.job_runner = JobRunner()
        self.layout_manager = LayoutManager()
        self.default_viewport_w = 1440
        self.default_viewport_h = 940
        self.viewport_title = "KBO 리플레이 검수"
        self.safe_viewport_title = "KBO Replay QA"
        self._localized_viewport_title_applied = False
        self.bottom_panel_h = 96
        self.bottom_db_ratio = 0.36
        self.db_detail_window_w = 980
        self.db_detail_window_h = 228
        self.alert_detail_window_w = 1040
        self.alert_detail_window_h = 336
        self.alert_error_detail_h = 104
        self.tabs = build_default_tabs(self.state, self.job_runner, self.layout_manager.mark_dirty)
        self.tab_by_key = {getattr(tab, "key", f"tab_{index}"): tab for index, tab in enumerate(self.tabs)}
        self.status_window = GlobalStatusWindow(height=self.bottom_panel_h)
        self.alert_window = GlobalAlertWindow(height=self.bottom_panel_h)
        self.db_detail_window = DbDetailWindow()
        self.alert_detail_window = AlertDetailWindow()

    @property
    def ingestion_tab(self):
        return self.tab_by_key["ingestion"]

    def on_tab_change(self, sender: int, app_data: int) -> None:
        label = dpg.get_item_label(app_data)
        if label:
            self.state.set_active_tab(label)

    def show_window(self, tag: str) -> None:
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=True)
            self.layout_manager.mark_dirty()

    def hide_window(self, tag: str) -> None:
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=False)
        if tag == GLOBAL_TAGS.alert_detail_window and dpg.does_item_exist(GLOBAL_TAGS.error_detail_group):
            dpg.configure_item(GLOBAL_TAGS.error_detail_group, show=False)
        self.layout_manager.mark_dirty()

    def build(self) -> None:
        build_shell_ui(self)

    def apply_localized_viewport_title(self) -> None:
        if self._localized_viewport_title_applied:
            return
        if hasattr(dpg, "set_viewport_title"):
            dpg.set_viewport_title(self.viewport_title)
        self._localized_viewport_title_applied = True

    def apply_layout(self) -> None:
        show_error_detail = dpg.does_item_exist(GLOBAL_TAGS.error_detail_group) and dpg.is_item_shown(GLOBAL_TAGS.error_detail_group)
        layout = compute_shell_layout(
            dpg.get_viewport_client_width(),
            dpg.get_viewport_client_height(),
            bottom_panel_height=self.bottom_panel_h,
            bottom_db_ratio=self.bottom_db_ratio,
            db_detail_window_width=self.db_detail_window_w,
            db_detail_window_height=self.db_detail_window_h,
            alert_detail_window_width=self.alert_detail_window_w,
            alert_detail_window_height=self.alert_detail_window_h,
            error_detail_extra_height=self.alert_error_detail_h,
            show_error_detail=show_error_detail,
        )
        dpg.configure_item(GLOBAL_TAGS.main_window, width=layout.main_window.width, height=layout.main_window.height, pos=(layout.main_window.x, layout.main_window.y))
        dpg.configure_item(GLOBAL_TAGS.db_window, width=layout.db_window.width, height=layout.db_window.height, pos=(layout.db_window.x, layout.db_window.y))
        dpg.configure_item(GLOBAL_TAGS.alert_window, width=layout.alert_window.width, height=layout.alert_window.height, pos=(layout.alert_window.x, layout.alert_window.y))
        if dpg.does_item_exist(GLOBAL_TAGS.db_summary_info_panel):
            dpg.configure_item(GLOBAL_TAGS.db_summary_info_panel, width=max(180, layout.db_window.width - 160), height=self.bottom_panel_h - 18)
        if dpg.does_item_exist(GLOBAL_TAGS.status_text):
            dpg.configure_item(GLOBAL_TAGS.status_text, wrap=max(140, layout.db_window.width - 220))
        if dpg.does_item_exist(GLOBAL_TAGS.db_summary_hint_text):
            dpg.configure_item(GLOBAL_TAGS.db_summary_hint_text, wrap=max(140, layout.db_window.width - 220))
        if dpg.does_item_exist(GLOBAL_TAGS.db_detail_window):
            dpg.configure_item(GLOBAL_TAGS.db_detail_window, width=layout.db_detail_window.width, height=layout.db_detail_window.height, pos=(layout.db_detail_window.x, layout.db_detail_window.y))
        if dpg.does_item_exist(GLOBAL_TAGS.alert_detail_window):
            dpg.configure_item(GLOBAL_TAGS.alert_detail_window, width=layout.alert_detail_window.width, height=layout.alert_detail_window.height, pos=(layout.alert_detail_window.x, layout.alert_detail_window.y))
        for tab in self.tabs:
            if hasattr(tab, "apply_responsive_layout"):
                tab.apply_responsive_layout(layout.tab_content_width, layout.tab_content_height)

    def run(self) -> None:
        self.build()
        while dpg.is_dearpygui_running():
            self.layout_manager.poll(self.apply_layout)
            self.job_runner.poll()
            dpg.render_dearpygui_frame()
            self.apply_localized_viewport_title()
        dpg.destroy_context()


def run() -> None:
    AppShell().run()
