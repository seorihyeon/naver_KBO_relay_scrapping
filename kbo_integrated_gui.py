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

    def build(self):
        dpg.create_context()

        with dpg.window(tag="main_window", label="KBO DB Replay QA", width=self.default_viewport_w - 40, height=self.default_viewport_h - 60):
            with dpg.tab_bar(tag="main_tab_bar"):
                self.collection_tab.build(parent="main_tab_bar")
                self.ingestion_tab.build(parent="main_tab_bar")
                self.replay_tab.build(parent="main_tab_bar")

        dpg.create_viewport(title="KBO Replay QA (Graphics + Alerts)", width=self.default_viewport_w, height=self.default_viewport_h)
        dpg.setup_dearpygui()
        bind_korean_font(size=16)
        dpg.set_viewport_resize_callback(self.on_viewport_resize)
        dpg.show_viewport()
        self.replay_tab.apply_responsive_layout()
        dpg.start_dearpygui()
        dpg.destroy_context()


if __name__ == "__main__":
    app = KBOIntegratedDPGApp()
    app.build()
