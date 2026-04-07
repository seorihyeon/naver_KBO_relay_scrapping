from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.tags import TagNamespace


@dataclass
class FileSelector:
    namespace: TagNamespace
    label: str
    default_value: str
    button_label: str = "Browse"
    directory: bool = False
    width: int = 420

    @property
    def input_tag(self) -> str:
        return self.namespace("input")

    @property
    def dialog_tag(self) -> str:
        return self.namespace("dialog")

    def build(self, *, on_change: Callable[[], None] | None = None) -> None:
        with dpg.group(horizontal=True):
            dpg.add_text(self.label)
            dpg.add_input_text(tag=self.input_tag, width=self.width, default_value=self.default_value, callback=lambda: on_change() if on_change else None)
            dpg.add_button(label=self.button_label, callback=lambda: dpg.configure_item(self.dialog_tag, show=True))

        with dpg.file_dialog(
            directory_selector=self.directory,
            show=False,
            callback=self._select_path,
            tag=self.dialog_tag,
            width=640,
            height=480,
        ):
            dpg.add_file_extension(".*")

    def _select_path(self, sender: int, app_data: dict, user_data: object | None = None) -> None:
        selected_path = app_data.get("file_path_name")
        if selected_path and dpg.does_item_exist(self.input_tag):
            dpg.set_value(self.input_tag, selected_path)

    def get_value(self) -> str:
        return dpg.get_value(self.input_tag)

    def set_width(self, width: int) -> None:
        self.width = width
        if dpg.does_item_exist(self.input_tag):
            dpg.configure_item(self.input_tag, width=width)
