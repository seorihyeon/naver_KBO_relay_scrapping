from __future__ import annotations

from dataclasses import dataclass

import dearpygui.dearpygui as dpg


@dataclass
class HorizontalToolbar:
    tag: str
    height: int = 42
    border: bool = False

    @property
    def body_tag(self) -> str:
        return f"{self.tag}__body"

    def build(self, *, parent: str | None = None) -> str:
        kwargs = {
            "tag": self.tag,
            "width": -1,
            "height": self.height,
            "border": self.border,
            "horizontal_scrollbar": True,
        }
        if parent is not None:
            kwargs["parent"] = parent
        with dpg.child_window(**kwargs):
            with dpg.group(tag=self.body_tag, horizontal=True):
                pass
        return self.body_tag

    def set_width(self, width: int) -> None:
        if dpg.does_item_exist(self.tag):
            dpg.configure_item(self.tag, width=width)
