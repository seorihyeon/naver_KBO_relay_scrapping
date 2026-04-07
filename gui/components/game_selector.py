from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.tags import TagNamespace
from gui.state import GameOption


@dataclass
class GameSelector:
    namespace: TagNamespace
    width: int = 760

    @property
    def combo_tag(self) -> str:
        return self.namespace("combo")

    def build(self, *, on_load: Callable[[], None], on_refresh: Callable[[], None] | None = None) -> None:
        with dpg.group(horizontal=True):
            dpg.add_text("Game")
            dpg.add_combo(tag=self.combo_tag, items=[], width=self.width)
            dpg.add_button(label="Load", width=80, callback=lambda: on_load())
            if on_refresh is not None:
                dpg.add_button(label="Refresh", width=80, callback=lambda: on_refresh())

    def set_games(self, games: list[GameOption]) -> None:
        labels = [game.label for game in games]
        if dpg.does_item_exist(self.combo_tag):
            dpg.configure_item(self.combo_tag, items=labels)
            if labels and not dpg.get_value(self.combo_tag):
                dpg.set_value(self.combo_tag, labels[0])

    def get_selected_label(self) -> str:
        return dpg.get_value(self.combo_tag)

    def set_width(self, width: int) -> None:
        self.width = width
        if dpg.does_item_exist(self.combo_tag):
            dpg.configure_item(self.combo_tag, width=width)
