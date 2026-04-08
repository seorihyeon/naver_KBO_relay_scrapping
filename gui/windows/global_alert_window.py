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
            label="전체 알림",
            width=720,
            height=self.height,
            pos=(10, 10),
            no_resize=True,
            no_move=True,
        ):
            with dpg.group(horizontal=True):
                dpg.add_text("현재 탭: 수집", tag=GLOBAL_TAGS.global_status_current_tab)
                dpg.add_text("최근 작업: 없음", tag=GLOBAL_TAGS.global_status_recent_task)
                dpg.add_text("상태: 대기 중", tag=GLOBAL_TAGS.global_status_result, color=(180, 180, 180))
                dpg.add_button(label="상세", callback=lambda: on_show_detail())
            with dpg.group(horizontal=True):
                dpg.add_text("마지막 업데이트: -", tag=GLOBAL_TAGS.global_status_updated_at)
                dpg.add_spacer(width=16)
                dpg.add_text("최근 오류 없음", tag=GLOBAL_TAGS.recent_error_summary, color=(255, 150, 150))
                dpg.add_button(label="최근 오류 보기", callback=lambda: on_show_recent_error())
