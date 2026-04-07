from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.tags import GLOBAL_TAGS


@dataclass
class DbDetailWindow:
    def build(self, *, default_dsn: str, on_connect_db: Callable[[], None], on_close: Callable[[], None]) -> None:
        with dpg.window(
            tag=GLOBAL_TAGS.db_detail_window,
            label="DB Details",
            show=False,
            no_resize=True,
            no_move=True,
            no_collapse=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_text("DSN")
                dpg.add_input_text(tag=GLOBAL_TAGS.dsn_input, width=720, default_value=default_dsn)
                dpg.add_button(label="Connect", callback=lambda: on_connect_db())
                dpg.add_button(label="Close", callback=lambda: on_close())
            dpg.add_spacer(height=6)
            dpg.add_text("Status log")
            dpg.add_input_text(tag=GLOBAL_TAGS.status_detail_text, multiline=True, readonly=True, width=-1, height=128)
