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
        self.db_window_expanded_h = 130
        self.alert_window_expanded_h = 240
        self.collapsed_h = 28

    def layout_windows(self):
        if not dpg.does_item_exist("main_window"):
            return
        vw = dpg.get_viewport_client_width()
        vh = dpg.get_viewport_client_height()
        margin = 10
        gap = 10

        def _window_height(tag: str, expanded_h: int) -> int:
            if not dpg.does_item_exist(tag):
                return expanded_h
            cfg = dpg.get_item_configuration(tag)
            state = dpg.get_item_state(tag)
            rect_h = (state.get("rect_size") or (0, expanded_h))[1]
            collapsed = bool(cfg.get("collapsed")) or rect_h <= (self.collapsed_h + 6)
            return self.collapsed_h if collapsed else expanded_h

        db_h = _window_height("global_db_window", self.db_window_expanded_h)
        alert_h = _window_height("global_alert_window", self.alert_window_expanded_h)

        top_y = margin
        main_y = top_y + db_h + gap
        alert_y = vh - margin - alert_h
        main_h = max(220, alert_y - gap - main_y)
        panel_w = max(700, vw - margin * 2)

        dpg.configure_item("global_db_window", width=panel_w, height=db_h, pos=(margin, top_y))
        dpg.configure_item("main_window", width=panel_w, height=main_h, pos=(margin, main_y))
        dpg.configure_item("global_alert_window", width=panel_w, height=alert_h, pos=(margin, alert_y))
        self.replay_tab.apply_responsive_layout()

    def on_viewport_resize(self, sender=None, app_data=None):
        self.layout_windows()

    def on_tab_change(self, sender, app_data):
        if dpg.get_item_label(app_data):
            self.state.set_active_tab(dpg.get_item_label(app_data))

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
                dpg.add_text("DSN")
                dpg.add_input_text(tag="dsn_input", width=900, default_value=self.state.default_dsn)
                dpg.add_button(label="DB 연결", callback=lambda: self.ingestion_tab.connect_db())
            dpg.add_text("DB 상태", tag="status_text")
            dpg.add_input_text(tag="status_detail_text", multiline=True, readonly=True, width=-1, height=40)

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
            dpg.add_input_text(tag="global_notification_text", multiline=True, readonly=True, width=-1, height=120)
            with dpg.group(horizontal=True):
                dpg.add_button(label="최근 오류 다시 보기 (F8)", callback=lambda: self.state.show_recent_error())
                dpg.add_button(label="오류 디버그 펼치기/접기", callback=lambda: self.state.toggle_error_detail())
            dpg.add_text("최근 오류 없음", tag="recent_error_summary", color=(255, 150, 150))
            with dpg.group(tag="error_detail_group", show=False):
                dpg.add_input_text(tag="global_error_debug_text", multiline=True, readonly=True, width=-1, height=90)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("현재 탭: 데이터 수집", tag="global_status_current_tab")
                dpg.add_text("최근 작업: 대기 중", tag="global_status_recent_task")
                dpg.add_text("상태: 대기", tag="global_status_result", color=(180, 180, 180))
                dpg.add_text("마지막 업데이트: -", tag="global_status_updated_at")

        with dpg.handler_registry():
            dpg.add_key_press_handler(key=dpg.mvKey_F8, callback=lambda: self.state.show_recent_error())

        dpg.create_viewport(title="KBO Replay QA (Graphics + Alerts)", width=self.default_viewport_w, height=self.default_viewport_h)
        dpg.setup_dearpygui()
        bind_korean_font(size=16)
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
