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
            label="전체 DB 상태",
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
                        dpg.add_text("연결 안 됨", tag=GLOBAL_TAGS.db_connection_summary_text, color=(255, 195, 90))
                    with dpg.group(horizontal=True):
                        dpg.add_text("상태")
                        dpg.add_text("대기 중", tag=GLOBAL_TAGS.status_text, color=(180, 180, 180), wrap=180)
                    dpg.add_text(
                        "상세 창에서 DSN 변경과 세부 상태 로그를 확인할 수 있습니다.",
                        tag=GLOBAL_TAGS.db_summary_hint_text,
                        color=(160, 160, 160),
                        wrap=220,
                    )
                with dpg.group():
                    dpg.add_button(label="DB 연결", callback=lambda: on_connect_db(), width=120)
                    dpg.add_button(label="상세", callback=lambda: on_show_detail(), width=120)
