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

    def on_viewport_resize(self, sender=None, app_data=None):
        if dpg.does_item_exist("main_window"):
            self.replay_tab.apply_responsive_layout()

    def on_tab_change(self, sender, app_data):
        if dpg.get_item_label(app_data):
            self.state.set_active_tab(dpg.get_item_label(app_data))

    def build(self):
        dpg.create_context()

        with dpg.window(tag="main_window", label="KBO DB Replay QA", width=self.default_viewport_w - 40, height=self.default_viewport_h - 60):
            with dpg.tab_bar(tag="main_tab_bar", callback=self.on_tab_change):
                self.collection_tab.build(parent="main_tab_bar")
                self.ingestion_tab.build(parent="main_tab_bar")
                self.replay_tab.build(parent="main_tab_bar")
            dpg.add_separator()
            dpg.add_text("전역 알림 패널")
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
        self.replay_tab.apply_responsive_layout()
        while dpg.is_dearpygui_running():
            self.collection_tab.message_pump()
            dpg.render_dearpygui_frame()

        dpg.destroy_context()


if __name__ == "__main__":
    app = KBOIntegratedDPGApp()
    app.build()
