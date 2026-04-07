from __future__ import annotations

import importlib.metadata as importlib_metadata
from pathlib import Path

import dearpygui.dearpygui as dpg

from dpg_utils import bind_korean_font
from gui.jobs import JobRunner
from gui.layout_manager import LayoutManager, compute_shell_layout
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
        dpg.create_context()
        self.status_window.build(
            on_connect_db=self.ingestion_tab.connect_db,
            on_show_detail=lambda: self.show_window(GLOBAL_TAGS.db_detail_window),
        )
        with dpg.window(
            tag=GLOBAL_TAGS.main_window,
            label="KBO Replay QA",
            width=self.default_viewport_w - 20,
            height=self.default_viewport_h - 420,
            pos=(10, 150),
            no_resize=True,
            no_move=True,
        ):
            with dpg.tab_bar(tag=GLOBAL_TAGS.main_tab_bar, callback=self.on_tab_change):
                for tab in self.tabs:
                    tab.build(parent=GLOBAL_TAGS.main_tab_bar)
        self.alert_window.build(
            on_show_detail=lambda: self.show_window(GLOBAL_TAGS.alert_detail_window),
            on_show_recent_error=self.state.show_recent_error,
        )
        self.db_detail_window.build(
            default_dsn=self.state.default_dsn,
            on_connect_db=self.ingestion_tab.connect_db,
            on_close=lambda: self.hide_window(GLOBAL_TAGS.db_detail_window),
        )
        self.alert_detail_window.build(
            on_show_recent_error=self.state.show_recent_error,
            on_toggle_error_detail=self.state.toggle_error_detail,
            on_close=lambda: self.hide_window(GLOBAL_TAGS.alert_detail_window),
        )
        with dpg.handler_registry():
            dpg.add_key_press_handler(key=dpg.mvKey_F8, callback=lambda: self.state.show_recent_error())
        dpg.create_viewport(title="KBO Replay QA", width=self.default_viewport_w, height=self.default_viewport_h)
        dpg.setup_dearpygui()
        bind_korean_font(size=16)
        try:
            dpg_version = importlib_metadata.version("dearpygui")
        except Exception:
            dpg_version = "unknown"
        if dpg_version != "unknown" and dpg_version <= "2.1.0":
            self.state.set_status(
                "warn",
                "DearPyGui IME warning",
                f"Detected DearPyGui {dpg_version}. Windows Korean IME can be unstable in this version.",
                source="GUI",
            )
        self.state.set_db_connection_indicator("Disconnected", "warn")
        self.state.sync_presenter()
        dpg.set_viewport_resize_callback(self.layout_manager.on_viewport_resize)
        dpg.show_viewport()
        self.layout_manager.mark_dirty()

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
        dpg.destroy_context()


def run() -> None:
    AppShell().run()
