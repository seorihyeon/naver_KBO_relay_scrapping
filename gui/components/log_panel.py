from __future__ import annotations

from dataclasses import dataclass, field

import dearpygui.dearpygui as dpg

from gui.jobs import JobLogEntry
from gui.tags import TagNamespace


@dataclass
class LogPanel:
    namespace: TagNamespace
    height: int = 240
    title: str = "로그"
    max_entries: int = 400
    _entries: list[JobLogEntry] = field(default_factory=list)

    @property
    def window_tag(self) -> str:
        return self.namespace("window")

    @property
    def text_tag(self) -> str:
        return self.namespace("text")

    def build(self) -> None:
        dpg.add_text(self.title)
        with dpg.child_window(tag=self.window_tag, autosize_x=True, height=self.height):
            dpg.add_input_text(tag=self.text_tag, multiline=True, readonly=True, width=-1, height=-1)

    def clear(self) -> None:
        self._entries = []
        if dpg.does_item_exist(self.text_tag):
            dpg.set_value(self.text_tag, "")

    def append(self, entry: JobLogEntry) -> None:
        self._entries.append(entry)
        self._entries = self._entries[-self.max_entries :]
        if dpg.does_item_exist(self.text_tag):
            dpg.set_value(self.text_tag, "\n".join(item.as_text() for item in self._entries))
            dpg.set_y_scroll(self.window_tag, -1.0)

    def set_height(self, height: int) -> None:
        self.height = height
        if dpg.does_item_exist(self.window_tag):
            dpg.configure_item(self.window_tag, height=height)
