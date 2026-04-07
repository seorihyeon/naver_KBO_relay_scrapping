from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.tags import GLOBAL_TAGS


@dataclass
class GlobalAlertWindow:
    height: int = 96

    def build(self, *, on_show_detail: Callable[[], None], on_show_recent_error: Callable[[], None]) -> None:
        with dpg.window(
            tag=GLOBAL_TAGS.alert_window,
            label="Global Alerts",
            width=720,
            height=self.height,
            pos=(10, 10),
            no_resize=True,
            no_move=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_text("Current tab: Collection", tag=GLOBAL_TAGS.global_status_current_tab)
                dpg.add_text("Recent task: None", tag=GLOBAL_TAGS.global_status_recent_task)
                dpg.add_text("Status: Idle", tag=GLOBAL_TAGS.global_status_result, color=(180, 180, 180))
                dpg.add_button(label="Details", callback=lambda: on_show_detail())
            with dpg.group(horizontal=True):
                dpg.add_text("Last update: -", tag=GLOBAL_TAGS.global_status_updated_at)
                dpg.add_spacer(width=16)
                dpg.add_text("No recent error", tag=GLOBAL_TAGS.recent_error_summary, color=(255, 150, 150))
                dpg.add_button(label="Show Recent Error", callback=lambda: on_show_recent_error())
