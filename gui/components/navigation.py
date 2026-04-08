from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.tags import TagNamespace


@dataclass
class NavigatorPanel:
    namespace: TagNamespace
    title: str
    width: int = 220
    height: int = 92

    @property
    def panel_tag(self) -> str:
        return self.namespace("panel")

    @property
    def body_tag(self) -> str:
        return self.namespace("body")

    @property
    def text_tag(self) -> str:
        return self.namespace("text")

    @property
    def prev_tag(self) -> str:
        return self.namespace("prev")

    @property
    def next_tag(self) -> str:
        return self.namespace("next")

    def build(self, *, on_prev: Callable[[], None], on_next: Callable[[], None]) -> None:
        with dpg.child_window(tag=self.panel_tag, width=self.width, height=self.height, border=True, no_scrollbar=True):
            dpg.add_text(self.title)
            with dpg.child_window(tag=self.body_tag, width=-1, height=max(40, self.height - 50), border=False, no_scrollbar=True):
                dpg.add_text("-", tag=self.text_tag, wrap=max(140, self.width - 24))
            with dpg.group(horizontal=True):
                dpg.add_button(tag=self.prev_tag, label="이전", width=72, callback=lambda: on_prev())
                dpg.add_button(tag=self.next_tag, label="다음", width=72, callback=lambda: on_next())

    def set_summary(self, text: str) -> None:
        if dpg.does_item_exist(self.text_tag):
            dpg.set_value(self.text_tag, text)

    def set_enabled(self, *, prev_enabled: bool, next_enabled: bool) -> None:
        if dpg.does_item_exist(self.prev_tag):
            dpg.configure_item(self.prev_tag, enabled=prev_enabled)
        if dpg.does_item_exist(self.next_tag):
            dpg.configure_item(self.next_tag, enabled=next_enabled)

    def resize(self, *, width: int, height: int, body_height: int) -> None:
        self.width = width
        self.height = height
        if dpg.does_item_exist(self.panel_tag):
            dpg.configure_item(self.panel_tag, width=width, height=height)
        if dpg.does_item_exist(self.body_tag):
            dpg.configure_item(self.body_tag, width=max(140, width - 18), height=body_height)
        if dpg.does_item_exist(self.text_tag):
            dpg.configure_item(self.text_tag, wrap=max(140, width - 22))
