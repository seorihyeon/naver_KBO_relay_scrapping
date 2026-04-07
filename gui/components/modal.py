from __future__ import annotations

from dataclasses import dataclass

import dearpygui.dearpygui as dpg


@dataclass
class ModalWindow:
    tag: str
    label: str
    width: int
    height: int

    def build_begin(self) -> None:
        dpg.window(tag=self.tag, label=self.label, modal=True, show=False, no_resize=True, width=self.width, height=self.height)

    def show(self) -> None:
        if dpg.does_item_exist(self.tag):
            dpg.configure_item(self.tag, show=True)

    def hide(self) -> None:
        if dpg.does_item_exist(self.tag):
            dpg.configure_item(self.tag, show=False)
