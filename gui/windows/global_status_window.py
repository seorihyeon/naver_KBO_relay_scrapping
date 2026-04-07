from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.tags import GLOBAL_TAGS


@dataclass
class GlobalStatusWindow:
    height: int = 96

    def build(self, *, on_connect_db: Callable[[], None], on_show_detail: Callable[[], None]) -> None:
        with dpg.window(
            tag=GLOBAL_TAGS.db_window,
            label="Global DB Status",
            width=720,
            height=self.height,
            pos=(10, 10),
            no_resize=True,
            no_move=True,
        ):
            with dpg.group(horizontal=True):
                with dpg.child_window(
                    tag=GLOBAL_TAGS.db_summary_info_panel,
                    border=False,
                    width=260,
                    height=self.height - 18,
                    no_scrollbar=True,
                ):
                    with dpg.group(horizontal=True):
                        dpg.add_text("DB")
                        dpg.add_text("Disconnected", tag=GLOBAL_TAGS.db_connection_summary_text, color=(255, 195, 90))
                    with dpg.group(horizontal=True):
                        dpg.add_text("Status")
                        dpg.add_text("Idle", tag=GLOBAL_TAGS.status_text, color=(180, 180, 180), wrap=180)
                    dpg.add_text(
                        "Use the detail window for DSN changes and low-level status logs.",
                        tag=GLOBAL_TAGS.db_summary_hint_text,
                        color=(160, 160, 160),
                        wrap=220,
                    )
                with dpg.group():
                    dpg.add_button(label="Connect DB", callback=lambda: on_connect_db(), width=120)
                    dpg.add_button(label="Details", callback=lambda: on_show_detail(), width=120)
