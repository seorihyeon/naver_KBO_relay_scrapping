from __future__ import annotations

from dataclasses import dataclass

import dearpygui.dearpygui as dpg

from gui.tags import TagNamespace


@dataclass
class SummaryCard:
    namespace: TagNamespace
    title: str
    default_text: str = "-"

    @property
    def text_tag(self) -> str:
        return self.namespace("text")

    def build(self) -> None:
        dpg.add_text(self.title)
        dpg.add_text(self.default_text, tag=self.text_tag, wrap=380)

    def set_text(self, text: str) -> None:
        if dpg.does_item_exist(self.text_tag):
            dpg.set_value(self.text_tag, text)
