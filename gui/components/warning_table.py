from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import dearpygui.dearpygui as dpg

from gui.tags import TagNamespace


@dataclass
class WarningRow:
    code: str
    summary: str
    detail: str


@dataclass
class WarningTable:
    namespace: TagNamespace
    height: int = 120

    @property
    def table_tag(self) -> str:
        return self.namespace("table")

    def build(self) -> None:
        with dpg.table(
            header_row=True,
            tag=self.table_tag,
            policy=dpg.mvTable_SizingStretchProp,
            row_background=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            height=self.height,
        ):
            dpg.add_table_column(label="Code")
            dpg.add_table_column(label="Summary")
            dpg.add_table_column(label="Detail")

    def set_rows(self, rows: Iterable[WarningRow]) -> None:
        if not dpg.does_item_exist(self.table_tag):
            return
        dpg.delete_item(self.table_tag, children_only=True, slot=1)
        for row in rows:
            with dpg.table_row(parent=self.table_tag):
                dpg.add_text(row.code, color=(255, 100, 100))
                dpg.add_text(row.summary)
                dpg.add_text(row.detail)

    def set_height(self, height: int) -> None:
        self.height = height
        if dpg.does_item_exist(self.table_tag):
            dpg.configure_item(self.table_tag, height=height)
