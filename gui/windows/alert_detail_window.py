from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.tags import GLOBAL_TAGS


@dataclass
class AlertDetailWindow:
    def build(
        self,
        *,
        on_show_recent_error: Callable[[], None],
        on_toggle_error_detail: Callable[[], None],
        on_close: Callable[[], None],
    ) -> None:
        with dpg.window(
            tag=GLOBAL_TAGS.alert_detail_window,
            label="알림 상세",
            show=False,
            no_resize=True,
            no_move=True,
            no_collapse=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_button(label="최근 오류 보기", callback=lambda: on_show_recent_error())
                dpg.add_button(label="디버그 전환", callback=lambda: on_toggle_error_detail())
                dpg.add_button(label="닫기", callback=lambda: on_close())
            dpg.add_spacer(height=6)
            dpg.add_text("최근 오류 없음", tag=GLOBAL_TAGS.recent_error_detail_summary, color=(255, 150, 150))
            dpg.add_input_text(tag=GLOBAL_TAGS.global_notification_text, multiline=True, readonly=True, width=-1, height=180)
            with dpg.group(tag=GLOBAL_TAGS.error_detail_group, show=False):
                dpg.add_spacer(height=6)
                dpg.add_input_text(tag=GLOBAL_TAGS.global_error_debug_text, multiline=True, readonly=True, width=-1, height=90)
