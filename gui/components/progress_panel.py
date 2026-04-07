from __future__ import annotations

from dataclasses import dataclass

import dearpygui.dearpygui as dpg

from gui.tags import TagNamespace


@dataclass
class ProgressPanel:
    namespace: TagNamespace
    default_message: str = "Idle"

    @property
    def text_tag(self) -> str:
        return self.namespace("message")

    @property
    def bar_tag(self) -> str:
        return self.namespace("bar")

    def build(self) -> None:
        dpg.add_text(self.default_message, tag=self.text_tag)
        dpg.add_progress_bar(tag=self.bar_tag, width=-1, default_value=0.0, overlay="0%")

    def set_state(self, *, message: str, progress: float, overlay: str | None = None) -> None:
        if dpg.does_item_exist(self.text_tag):
            dpg.set_value(self.text_tag, message)
        if dpg.does_item_exist(self.bar_tag):
            dpg.configure_item(self.bar_tag, default_value=max(0.0, min(1.0, progress)), overlay=overlay or f"{int(progress * 100)}%")
