from __future__ import annotations

from pathlib import Path

import dearpygui.dearpygui as dpg

from dpg_utils import bind_korean_font
from tabs import AppState, CollectionTab, IngestionTab, ReplayTab


class KBOIntegratedDPGApp:
    def __init__(self):
        root_dir = Path(__file__).resolve().parent
        self.state = AppState.from_environment(root_dir)

        self.collection_tab = CollectionTab(self.state)
        self.ingestion_tab = IngestionTab(self.state)
        self.replay_tab = ReplayTab(self.state)

        self.default_viewport_w = 1440
        self.default_viewport_h = 940
        self.bottom_panel_h = 96
        self.bottom_db_ratio = 0.36
        self.db_detail_window_w = 980
        self.db_detail_window_h = 228
        self.alert_detail_window_w = 1040
        self.alert_detail_window_h = 336
        self.alert_error_detail_h = 104

    def layout_windows(self):
        if not dpg.does_item_exist("main_window"):
            return
        vw = dpg.get_viewport_client_width()
        vh = dpg.get_viewport_client_height()
        margin = 10
        gap = 10

        panel_w = max(900, vw - margin * 2)
        db_w = max(360, min(int(panel_w * self.bottom_db_ratio), panel_w - 520))
        alert_w = max(420, panel_w - db_w - gap)
        bottom_y = vh - margin - self.bottom_panel_h
        main_h = max(220, bottom_y - gap - margin)
        tab_content_w = max(700, panel_w - 28)
        tab_content_h = max(260, main_h - 72)

        dpg.configure_item("main_window", width=panel_w, height=main_h, pos=(margin, margin))
        dpg.configure_item("global_db_window", width=db_w, height=self.bottom_panel_h, pos=(margin, bottom_y))
        dpg.configure_item("global_alert_window", width=alert_w, height=self.bottom_panel_h, pos=(margin + db_w + gap, bottom_y))
        if dpg.does_item_exist("db_summary_info_panel"):
            dpg.configure_item("db_summary_info_panel", width=max(180, db_w - 160), height=self.bottom_panel_h - 18)
        if dpg.does_item_exist("status_text"):
            dpg.configure_item("status_text", wrap=max(140, db_w - 220))
        if dpg.does_item_exist("db_summary_hint_text"):
            dpg.configure_item("db_summary_hint_text", wrap=max(140, db_w - 220))

        if dpg.does_item_exist("db_detail_window"):
            db_x = max(margin, int((vw - self.db_detail_window_w) / 2))
            db_y = max(margin, int((vh - self.db_detail_window_h) / 2))
            dpg.configure_item("db_detail_window", width=self.db_detail_window_w, height=self.db_detail_window_h, pos=(db_x, db_y))

        if dpg.does_item_exist("alert_detail_window"):
            alert_detail_h = self.alert_detail_window_h
            if dpg.does_item_exist("error_detail_group") and dpg.is_item_shown("error_detail_group"):
                alert_detail_h += self.alert_error_detail_h
            alert_x = max(margin, int((vw - self.alert_detail_window_w) / 2))
            alert_y = max(margin, int((vh - alert_detail_h) / 2))
            dpg.configure_item("alert_detail_window", width=self.alert_detail_window_w, height=alert_detail_h, pos=(alert_x, alert_y))

        self.collection_tab.apply_responsive_layout(tab_content_w, tab_content_h)
        self.ingestion_tab.apply_responsive_layout(tab_content_w, tab_content_h)
        self.replay_tab.apply_responsive_layout()

    def on_viewport_resize(self, sender=None, app_data=None):
        self.layout_windows()

    def on_tab_change(self, sender, app_data):
        if dpg.get_item_label(app_data):
            self.state.set_active_tab(dpg.get_item_label(app_data))

    def show_db_detail(self):
        if dpg.does_item_exist("db_detail_window"):
            dpg.configure_item("db_detail_window", show=True)
            self.layout_windows()

    def show_alert_detail(self, *, show_error_debug: bool = False):
        if dpg.does_item_exist("alert_detail_window"):
            dpg.configure_item("alert_detail_window", show=True)
        if show_error_debug and dpg.does_item_exist("error_detail_group"):
            dpg.configure_item("error_detail_group", show=True)
        self.layout_windows()

    def hide_detail_window(self, tag: str):
        if dpg.does_item_exist(tag):
            dpg.configure_item(tag, show=False)
        if tag == "alert_detail_window" and dpg.does_item_exist("error_detail_group"):
            dpg.configure_item("error_detail_group", show=False)

    def build(self):
        dpg.create_context()

        with dpg.window(
            tag="global_db_window",
            label="공통 DB 연결",
            width=self.default_viewport_w - 20,
            height=130,
            pos=(10, 10),
            no_resize=True,
            no_move=True,
        ):
            with dpg.group(horizontal=True):
                with dpg.child_window(tag="db_summary_info_panel", border=False, width=220, height=self.bottom_panel_h - 18, no_scrollbar=True):
                    with dpg.group(horizontal=True):
                        dpg.add_text("DB 상태")
                        dpg.add_text("미연결", tag="db_connection_summary_text", color=(255, 195, 90))
                    with dpg.group(horizontal=True):
                        dpg.add_text("최근 상태")
                        dpg.add_text("대기 중", tag="status_text", color=(180, 180, 180), wrap=180)
                    dpg.add_text("DSN/상세 로그는 상세 창에서 확인", tag="db_summary_hint_text", color=(160, 160, 160), wrap=180)
                with dpg.group():
                    dpg.add_button(label="DB 연결", callback=lambda: self.ingestion_tab.connect_db(), width=120)
                    dpg.add_button(label="상세 보기", callback=lambda: self.show_db_detail(), width=120)

        with dpg.window(
            tag="main_window",
            label="KBO DB Replay QA",
            width=self.default_viewport_w - 20,
            height=self.default_viewport_h - 420,
            pos=(10, 150),
            no_resize=True,
            no_move=True,
        ):
            with dpg.tab_bar(tag="main_tab_bar", callback=self.on_tab_change):
                self.collection_tab.build(parent="main_tab_bar")
                self.ingestion_tab.build(parent="main_tab_bar")
                self.replay_tab.build(parent="main_tab_bar")

        with dpg.window(
            tag="global_alert_window",
            label="전역 알림",
            width=self.default_viewport_w - 20,
            height=240,
            pos=(10, self.default_viewport_h - 250),
            no_resize=True,
            no_move=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_text("현재 탭: 데이터 수집", tag="global_status_current_tab")
                dpg.add_text("최근 작업: 대기 중", tag="global_status_recent_task")
                dpg.add_text("상태: 대기", tag="global_status_result", color=(180, 180, 180))
                dpg.add_button(label="상세 보기", callback=lambda: self.show_alert_detail())
            with dpg.group(horizontal=True):
                dpg.add_text("마지막 업데이트: -", tag="global_status_updated_at")
                dpg.add_spacer(width=16)
                dpg.add_text("최근 오류 없음", tag="recent_error_summary", color=(255, 150, 150))
                dpg.add_button(label="최근 오류 다시 보기 (F8)", callback=lambda: self.state.show_recent_error())

        with dpg.window(
            tag="db_detail_window",
            label="DB 연결 상세",
            show=False,
            no_resize=True,
            no_move=True,
            no_collapse=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_text("DSN")
                dpg.add_input_text(tag="dsn_input", width=720, default_value=self.state.default_dsn)
                dpg.add_button(label="DB 연결", callback=lambda: self.ingestion_tab.connect_db())
                dpg.add_button(label="닫기", callback=lambda: self.hide_detail_window("db_detail_window"))
            dpg.add_spacer(height=6)
            dpg.add_text("상세 상태 로그")
            dpg.add_input_text(tag="status_detail_text", multiline=True, readonly=True, width=-1, height=128)

        with dpg.window(
            tag="alert_detail_window",
            label="전역 알림 상세",
            show=False,
            no_resize=True,
            no_move=True,
            no_collapse=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_button(label="최근 오류 다시 보기 (F8)", callback=lambda: self.state.show_recent_error())
                dpg.add_button(label="오류 디버그 펼치기/접기", callback=lambda: self.state.toggle_error_detail())
                dpg.add_button(label="닫기", callback=lambda: self.hide_detail_window("alert_detail_window"))
            dpg.add_spacer(height=6)
            dpg.add_text("최근 오류 없음", tag="recent_error_detail_summary", color=(255, 150, 150))
            dpg.add_input_text(tag="global_notification_text", multiline=True, readonly=True, width=-1, height=180)
            with dpg.group(tag="error_detail_group", show=False):
                dpg.add_spacer(height=6)
                dpg.add_input_text(tag="global_error_debug_text", multiline=True, readonly=True, width=-1, height=90)

        with dpg.handler_registry():
            dpg.add_key_press_handler(key=dpg.mvKey_F8, callback=lambda: self.state.show_recent_error())

        dpg.create_viewport(title="KBO Replay QA (Graphics + Alerts)", width=self.default_viewport_w, height=self.default_viewport_h)
        dpg.setup_dearpygui()
        bind_korean_font(size=16)
        self.state.set_db_connection_indicator("미연결", "warn")
        dpg.set_viewport_resize_callback(self.on_viewport_resize)
        dpg.show_viewport()
        self.layout_windows()
        while dpg.is_dearpygui_running():
            self.layout_windows()
            self.collection_tab.message_pump()
            dpg.render_dearpygui_frame()

        dpg.destroy_context()


if __name__ == "__main__":
    app = KBOIntegratedDPGApp()
    app.build()
