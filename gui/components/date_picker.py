from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

import dearpygui.dearpygui as dpg

from gui.tags import TagNamespace


@dataclass
class DatePicker:
    namespace: TagNamespace
    width: int = 360
    height: int = 340

    def __post_init__(self) -> None:
        today = dt.date.today()
        self.year = today.year
        self.month = today.month
        self.target_tag: str | None = None

    @property
    def modal_tag(self) -> str:
        return self.namespace("modal")

    @property
    def header_tag(self) -> str:
        return self.namespace("header")

    @property
    def grid_tag(self) -> str:
        return self.namespace("grid")

    def build(self) -> None:
        with dpg.window(tag=self.modal_tag, label="Pick date", modal=True, show=False, width=self.width, height=self.height):
            with dpg.group(horizontal=True):
                dpg.add_button(label="<", width=30, callback=lambda: self.prev_month())
                dpg.add_text("", tag=self.header_tag)
                dpg.add_button(label=">", width=30, callback=lambda: self.next_month())
            dpg.add_separator()
            with dpg.child_window(tag=self.grid_tag, autosize_x=True, autosize_y=True):
                pass
            dpg.add_separator()
            dpg.add_button(label="Close", width=60, callback=lambda: dpg.configure_item(self.modal_tag, show=False))
        self.render()

    def open(self, target_tag: str) -> None:
        self.target_tag = target_tag
        try:
            base = dt.datetime.strptime(dpg.get_value(target_tag), "%Y-%m-%d").date()
        except Exception:
            base = dt.date.today()
        self.year = base.year
        self.month = base.month
        self.render()
        dpg.configure_item(self.modal_tag, show=True)

    def render(self) -> None:
        if not dpg.does_item_exist(self.header_tag):
            return
        dpg.set_value(self.header_tag, f"{self.year:04d}-{self.month:02d}")
        dpg.delete_item(self.grid_tag, children_only=True)
        with dpg.group(horizontal=True, parent=self.grid_tag):
            for day_name in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]:
                dpg.add_button(label=day_name, width=34, height=20, enabled=False)
        cal = calendar.Calendar(firstweekday=0)
        today = dt.date.today()
        same_month = today.year == self.year and today.month == self.month
        for week in cal.monthdayscalendar(self.year, self.month):
            with dpg.group(horizontal=True, parent=self.grid_tag):
                for day in week:
                    if day == 0:
                        dpg.add_button(label=" ", width=34, height=26, enabled=False)
                        continue
                    is_future = dt.date(self.year, self.month, day) > today
                    label = f"[{day:2d}]" if same_month and day == today.day else f"{day:2d}"
                    dpg.add_button(label=label, width=34, height=26, enabled=not is_future, user_data=day, callback=self.pick_day)

    def prev_month(self) -> None:
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        self.render()

    def next_month(self) -> None:
        year, month = self.year, self.month + 1
        if month == 13:
            year += 1
            month = 1
        if dt.date(year, month, 1) > dt.date.today():
            return
        self.year = year
        self.month = month
        self.render()

    def pick_day(self, sender: int, app_data: object, user_data: int) -> None:
        if self.target_tag is None:
            return
        dpg.set_value(self.target_tag, f"{self.year:04d}-{self.month:02d}-{user_data:02d}")
        dpg.configure_item(self.modal_tag, show=False)
