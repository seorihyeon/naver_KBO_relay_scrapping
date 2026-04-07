from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

import dearpygui.dearpygui as dpg


@dataclass(frozen=True)
class Rect:
    width: int
    height: int
    x: int
    y: int


@dataclass(frozen=True)
class ShellLayout:
    main_window: Rect
    db_window: Rect
    alert_window: Rect
    db_detail_window: Rect
    alert_detail_window: Rect
    tab_content_width: int
    tab_content_height: int


def compute_shell_layout(
    viewport_width: int,
    viewport_height: int,
    *,
    bottom_panel_height: int,
    bottom_db_ratio: float,
    db_detail_window_width: int,
    db_detail_window_height: int,
    alert_detail_window_width: int,
    alert_detail_window_height: int,
    error_detail_extra_height: int,
    show_error_detail: bool,
) -> ShellLayout:
    margin = 10
    gap = 10
    panel_width = max(900, viewport_width - margin * 2)
    db_width = max(360, min(int(panel_width * bottom_db_ratio), panel_width - 520))
    alert_width = max(420, panel_width - db_width - gap)
    bottom_y = viewport_height - margin - bottom_panel_height
    main_height = max(220, bottom_y - gap - margin)
    tab_content_width = max(700, panel_width - 28)
    tab_content_height = max(260, main_height - 72)

    db_detail_x = max(margin, int((viewport_width - db_detail_window_width) / 2))
    db_detail_y = max(margin, int((viewport_height - db_detail_window_height) / 2))
    alert_detail_height = alert_detail_window_height + (error_detail_extra_height if show_error_detail else 0)
    alert_detail_x = max(margin, int((viewport_width - alert_detail_window_width) / 2))
    alert_detail_y = max(margin, int((viewport_height - alert_detail_height) / 2))

    return ShellLayout(
        main_window=Rect(panel_width, main_height, margin, margin),
        db_window=Rect(db_width, bottom_panel_height, margin, bottom_y),
        alert_window=Rect(alert_width, bottom_panel_height, margin + db_width + gap, bottom_y),
        db_detail_window=Rect(db_detail_window_width, db_detail_window_height, db_detail_x, db_detail_y),
        alert_detail_window=Rect(alert_detail_window_width, alert_detail_height, alert_detail_x, alert_detail_y),
        tab_content_width=tab_content_width,
        tab_content_height=tab_content_height,
    )


class LayoutManager:
    def __init__(self, *, debounce_ms: int = 60) -> None:
        self.debounce_ms = debounce_ms
        self._dirty = True
        self._requested_at = 0.0
        self._last_size: tuple[int, int] | None = None

    def mark_dirty(self) -> None:
        self._dirty = True
        self._requested_at = time.monotonic()

    def on_viewport_resize(self, sender: int | None = None, app_data: tuple[int, int] | None = None) -> None:
        self.mark_dirty()

    def poll(self, callback: Callable[[], None]) -> None:
        if not self._dirty:
            return
        current_size = (dpg.get_viewport_client_width(), dpg.get_viewport_client_height())
        now = time.monotonic()
        if self._last_size == current_size and (now - self._requested_at) * 1000 < self.debounce_ms:
            return
        callback()
        self._last_size = current_size
        self._dirty = False
