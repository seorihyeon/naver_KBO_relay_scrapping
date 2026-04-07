from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import dearpygui.dearpygui as dpg

from gui.components import GameSelector, NavigatorPanel, SummaryCard, WarningTable
from gui.components.warning_table import WarningRow
from gui.replay import (
    FieldOverlayRenderer,
    ReplayAnomalyDetector,
    ReplayNavigationModel,
    ReplayNavigationModelBuilder,
    ReplayRepository,
    ReplayStateBuilder,
    StrikeZoneRenderer,
)
from gui.replay.models import DerivedState, EventRow
from gui.replay.roster import build_roster_context
from gui.state import AppState
from gui.tags import TagNamespace


@dataclass
class ReplayLayout:
    content_w: int
    content_h: int
    stage_h: int
    bottom_h: int
    canvas_w: int
    canvas_h: int
    side_w: int
    left_event_h: int
    left_pa_h: int
    left_inning_h: int
    event_body_h: int
    inning_body_h: int
    right_pitch_h: int
    strike_h: int
    pitch_body_h: int
    pa_body_h: int
    warning_table_h: int


class ReplayTab:
    key = "replay"
    label = "Replay"

    PANEL_GAP = 8
    CONTROL_PANEL_HEIGHT = 46
    STAGE_MIN_HEIGHT = 336
    BOTTOM_INFO_MIN_HEIGHT = 140
    DETAIL_TEXT_HEIGHT = 64
    CANVAS_MIN_WIDTH = 460
    CANVAS_MIN_HEIGHT = 248

    def __init__(self, state: AppState, job_runner=None, request_layout: Callable[[], None] | None = None):
        self.state = state
        self.request_layout = request_layout or (lambda: None)
        self.namespace = TagNamespace("replay")
        self.game_selector = GameSelector(self.namespace.child("game_selector"), width=760)
        self.loaded_game_card = SummaryCard(self.namespace.child("loaded_game"), title="Loaded game", default_text="No game loaded")
        self.event_nav = NavigatorPanel(self.namespace.child("event_nav"), title="Event")
        self.pa_nav = NavigatorPanel(self.namespace.child("pa_nav"), title="PA")
        self.inning_nav = NavigatorPanel(self.namespace.child("inning_nav"), title="Inning")
        self.pitch_nav = NavigatorPanel(self.namespace.child("pitch_nav"), title="Pitch")
        self.warning_table = WarningTable(self.namespace.child("warnings"), height=120)
        self.repository: ReplayRepository | None = None
        self.state_builder: ReplayStateBuilder | None = None
        self.navigation: ReplayNavigationModel = ReplayNavigationModel()
        self.warning_detector = ReplayAnomalyDetector()
        self.warnings = []
        self.event_idx = 0
        self.pitch_idx = 0
        self.pa_idx = 0
        self.inning_idx = 0
        self.canvas_w = 1100
        self.canvas_h = 420
        self.strike_zone_w = 240
        self.strike_zone_h = 260
        self.field_renderer = FieldOverlayRenderer(self._tag("field_drawlist"), self.canvas_w, self.canvas_h)
        self.zone_renderer = StrikeZoneRenderer(self._tag("zone_drawlist"), self.strike_zone_w, self.strike_zone_h, self._tag("zone_meta"))
        self.state.subscribe("games_changed", self._on_games_changed)

    def _tag(self, name: str) -> str:
        return self.namespace(name)

    def build(self, parent: str) -> None:
        with dpg.tab(label=self.label, parent=parent, tag=self._tag("tab")):
            with dpg.child_window(tag=self._tag("control_panel"), border=True, width=-1, height=self.CONTROL_PANEL_HEIGHT, no_scrollbar=True):
                self.game_selector.build(on_load=lambda: self.load_selected_game())
                dpg.add_same_line()
                dpg.add_button(label="Refresh warnings", width=120, callback=lambda: self.refresh_warning_panel())

            dpg.add_spacer(height=self.PANEL_GAP)
            with dpg.child_window(tag=self._tag("stage_panel"), width=-1, height=400, border=True, no_scrollbar=True):
                with dpg.group(horizontal=True):
                    with dpg.child_window(tag=self._tag("left_column"), width=220, height=-1, border=False, no_scrollbar=True):
                        self.event_nav.build(on_prev=lambda: self.move_focus("event", -1), on_next=lambda: self.move_focus("event", 1))
                        dpg.add_spacer(height=self.PANEL_GAP)
                        self.pa_nav.build(on_prev=lambda: self.move_focus("pa", -1), on_next=lambda: self.move_focus("pa", 1))
                        dpg.add_spacer(height=self.PANEL_GAP)
                        self.inning_nav.build(on_prev=lambda: self.move_focus("inning", -1), on_next=lambda: self.move_focus("inning", 1))
                    with dpg.child_window(tag=self._tag("center_panel"), width=640, height=-1, border=False, no_scrollbar=True):
                        dpg.add_drawlist(tag=self._tag("field_drawlist"), width=self.canvas_w, height=self.canvas_h)
                    with dpg.child_window(tag=self._tag("right_column"), width=220, height=-1, border=False, no_scrollbar=True):
                        self.pitch_nav.build(on_prev=lambda: self.move_focus("pitch", -1), on_next=lambda: self.move_focus("pitch", 1))
                        dpg.add_spacer(height=self.PANEL_GAP)
                        with dpg.child_window(tag=self._tag("zone_panel"), width=220, height=-1, border=True, no_scrollbar=True):
                            dpg.add_drawlist(tag=self._tag("zone_drawlist"), width=self.strike_zone_w, height=self.strike_zone_h)
                            dpg.add_spacer(height=6)
                            dpg.add_text("No pitch selected", tag=self._tag("zone_meta"), wrap=188)
            dpg.add_spacer(height=self.PANEL_GAP)
            with dpg.child_window(tag=self._tag("inspector_panel"), width=-1, height=self.BOTTOM_INFO_MIN_HEIGHT, border=True, no_scrollbar=True):
                self.loaded_game_card.build()
                dpg.add_text("Focus detail")
                dpg.add_input_text(tag=self._tag("event_detail"), multiline=True, readonly=True, width=-1, height=self.DETAIL_TEXT_HEIGHT)
                dpg.add_text("Warnings: 0", tag=self._tag("warning_count"), color=(255, 100, 100))
                dpg.add_text("No anomaly detected", tag=self._tag("warning_hint"), wrap=360)
                self.warning_table.build()

        self.game_selector.set_games(self.state.games)
        self.render_empty_state()

    def _on_games_changed(self, games) -> None:
        self.game_selector.set_games(games)

    def apply_responsive_layout(self, content_w: int, content_h: int) -> None:
        if not dpg.does_item_exist(self._tag("control_panel")):
            return
        layout = self.compute_layout_metrics(content_w, content_h)
        dpg.configure_item(self._tag("control_panel"), width=layout.content_w, height=self.CONTROL_PANEL_HEIGHT)
        self.game_selector.set_width(max(260, layout.content_w - 280))
        dpg.configure_item(self._tag("stage_panel"), width=layout.content_w, height=layout.stage_h)
        dpg.configure_item(self._tag("left_column"), width=layout.side_w, height=-1)
        dpg.configure_item(self._tag("center_panel"), width=layout.canvas_w, height=-1)
        dpg.configure_item(self._tag("right_column"), width=layout.side_w, height=-1)
        self.event_nav.resize(width=layout.side_w, height=layout.left_event_h, body_height=layout.event_body_h)
        self.pa_nav.resize(width=layout.side_w, height=layout.left_pa_h, body_height=layout.pa_body_h)
        self.inning_nav.resize(width=layout.side_w, height=layout.left_inning_h, body_height=layout.inning_body_h)
        self.pitch_nav.resize(width=layout.side_w, height=layout.right_pitch_h, body_height=layout.pitch_body_h)
        dpg.configure_item(self._tag("zone_panel"), width=layout.side_w, height=-1)
        dpg.configure_item(self._tag("inspector_panel"), width=layout.content_w, height=layout.bottom_h)
        dpg.configure_item(self._tag("event_detail"), height=self.DETAIL_TEXT_HEIGHT)
        self.warning_table.set_height(layout.warning_table_h)

        self.canvas_w = layout.canvas_w
        self.canvas_h = layout.canvas_h
        self.strike_zone_w = max(160, layout.side_w - 24)
        self.strike_zone_h = max(96, layout.strike_h - 44)
        self.field_renderer.set_size(self.canvas_w, self.canvas_h)
        self.zone_renderer.set_size(self.strike_zone_w, self.strike_zone_h)
        dpg.configure_item(self._tag("field_drawlist"), width=self.canvas_w, height=self.canvas_h)
        dpg.configure_item(self._tag("zone_drawlist"), width=self.strike_zone_w, height=self.strike_zone_h)
        self.render_current_view()

    def compute_layout_metrics(self, content_w: int, content_h: int) -> ReplayLayout:
        available_h = max(500, content_h - self.CONTROL_PANEL_HEIGHT - self.PANEL_GAP * 2)
        stage_h = max(self.STAGE_MIN_HEIGHT, int(available_h * 0.8))
        bottom_h = available_h - stage_h
        if bottom_h < self.BOTTOM_INFO_MIN_HEIGHT:
            stage_h = max(self.STAGE_MIN_HEIGHT, available_h - self.BOTTOM_INFO_MIN_HEIGHT)
            bottom_h = available_h - stage_h
        stage_body_h = max(self.CANVAS_MIN_HEIGHT, stage_h - (self.PANEL_GAP + 8))
        side_w = max(214, min(274, int(content_w * 0.205)))
        canvas_w = content_w - side_w * 2 - self.PANEL_GAP * 2 - 24
        if canvas_w < self.CANVAS_MIN_WIDTH:
            reduce_each = int((self.CANVAS_MIN_WIDTH - canvas_w) / 2) + 8
            side_w = max(168, side_w - reduce_each)
            canvas_w = content_w - side_w * 2 - self.PANEL_GAP * 2 - 24
        canvas_w = max(self.CANVAS_MIN_WIDTH, canvas_w)
        canvas_h = stage_body_h
        left_available_h = stage_body_h - self.PANEL_GAP * 2
        left_event_h = max(86, int(left_available_h * 0.3))
        left_inning_h = max(76, int(left_available_h * 0.3))
        left_pa_h = left_available_h - left_event_h - left_inning_h
        if left_pa_h < 112:
            deficit = 112 - left_pa_h
            event_trim = min(max(0, left_event_h - 78), (deficit + 1) // 2)
            left_event_h -= event_trim
            deficit -= event_trim
            inning_trim = min(max(0, left_inning_h - 68), deficit)
            left_inning_h -= inning_trim
            left_pa_h = left_available_h - left_event_h - left_inning_h
        right_available_h = stage_body_h - self.PANEL_GAP
        right_pitch_h = max(80, int(right_available_h * 0.25))
        strike_h = right_available_h - right_pitch_h
        if strike_h < 196:
            right_pitch_h = max(72, right_available_h - 196)
            strike_h = right_available_h - right_pitch_h
        nav_body_reserved = 82
        return ReplayLayout(
            content_w=content_w,
            content_h=content_h,
            stage_h=stage_h,
            bottom_h=bottom_h,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            side_w=side_w,
            left_event_h=left_event_h,
            left_pa_h=left_pa_h,
            left_inning_h=left_inning_h,
            event_body_h=max(34, left_event_h - nav_body_reserved),
            inning_body_h=max(34, left_inning_h - nav_body_reserved),
            right_pitch_h=right_pitch_h,
            strike_h=strike_h,
            pitch_body_h=max(34, right_pitch_h - nav_body_reserved),
            pa_body_h=max(34, left_pa_h - nav_body_reserved),
            warning_table_h=max(60, bottom_h - self.DETAIL_TEXT_HEIGHT - 110),
        )

    def load_selected_game(self) -> None:
        if not self.state.conn:
            self.state.set_status("warn", "Replay load failed", "Connect to DB first.", source=self.label)
            return
        selected_label = self.game_selector.get_selected_label()
        match = [game for game in self.state.games if game.label == selected_label]
        if not match:
            self.state.set_status("warn", "Replay load failed", "Select a game first.", source=self.label)
            return
        selected_game = match[0]
        self.repository = ReplayRepository(self.state.conn)
        self.state.set_game_selection(selected_game.game_id)
        self.state.set_status("info", "Loading replay game", selected_game.label, source=self.label, append=False)
        try:
            dataset = self.repository.load_game(selected_game.game_id)
            roster_context = build_roster_context(dataset)
            self.state_builder = ReplayStateBuilder(self.state, dataset, roster_context)
            self.navigation = ReplayNavigationModelBuilder(self.state_builder).build()
            self.warnings = self.warning_detector.detect(dataset.events)
            self.event_idx = self.pitch_idx = self.pa_idx = self.inning_idx = 0
            self._update_loaded_game_summary()
            self.refresh_warning_panel()
            self.render_current_view()
            self.state.set_status(
                "info",
                f"Replay game loaded (game_id={selected_game.game_id})",
                f"events={len(dataset.events)} pitches={len(dataset.pitches)}",
                source=self.label,
                append=False,
            )
        except Exception as exc:
            self.state.set_status("error", "Replay load failed", str(exc), debug_detail=str(exc), source=self.label, append=False)

    def refresh_warning_panel(self) -> None:
        if self.state_builder is not None:
            self.warnings = self.warning_detector.detect(self.state_builder.dataset.events)
        rows = [WarningRow(code=warning.code, summary=f"event_id={warning.event_id}", detail=warning.detail) for warning in self.warnings[:500]]
        self.warning_table.set_rows(rows)
        if dpg.does_item_exist(self._tag("warning_count")):
            dpg.set_value(self._tag("warning_count"), f"Warnings: {len(self.warnings)}")
            dpg.configure_item(self._tag("warning_count"), color=(255, 100, 100) if self.warnings else (120, 220, 140))
        if dpg.does_item_exist(self._tag("warning_hint")):
            if self.warnings:
                first = self.warnings[0]
                dpg.set_value(self._tag("warning_hint"), f"First warning: event_id={first.event_id} | {first.code}\n{first.detail}")
            else:
                dpg.set_value(self._tag("warning_hint"), "No anomaly detected")

    def current_event(self) -> EventRow | None:
        if self.state_builder is None or not self.state_builder.events:
            return None
        return self.state_builder.events[self.event_idx]

    def current_pitch(self):
        if not self.navigation.pitch_items:
            return None
        return self.navigation.pitch_items[self.pitch_idx].pitch

    def current_pa(self):
        if not self.navigation.pa_items:
            return None
        return self.navigation.pa_items[self.pa_idx].pa

    def current_inning(self):
        if not self.navigation.inning_items:
            return None
        return self.navigation.inning_items[self.inning_idx].inning

    def move_focus(self, kind: str, delta: int) -> None:
        if self.state_builder is None or not self.state_builder.events:
            return
        if kind == "event":
            self.set_focus_event_index(self.event_idx + delta)
            return
        if kind == "pitch" and self.navigation.pitch_items:
            self.pitch_idx = max(0, min(self.pitch_idx + delta, len(self.navigation.pitch_items) - 1))
            self.set_focus_event_index(self.navigation.pitch_items[self.pitch_idx].event_idx)
            return
        if kind == "pa" and self.navigation.pa_items:
            self.pa_idx = max(0, min(self.pa_idx + delta, len(self.navigation.pa_items) - 1))
            self.set_focus_event_index(self.navigation.pa_items[self.pa_idx].event_idx)
            return
        if kind == "inning" and self.navigation.inning_items:
            self.inning_idx = max(0, min(self.inning_idx + delta, len(self.navigation.inning_items) - 1))
            self.set_focus_event_index(self.navigation.inning_items[self.inning_idx].event_idx)

    def set_focus_event_index(self, event_idx: int) -> None:
        if self.state_builder is None or not self.state_builder.events:
            return
        self.event_idx = max(0, min(event_idx, len(self.state_builder.events) - 1))
        self.sync_navigation_indices_from_event()
        self.render_current_view()

    def sync_navigation_indices_from_event(self) -> None:
        if self.state_builder is None or not self.state_builder.events:
            self.pitch_idx = self.pa_idx = self.inning_idx = 0
            return
        event = self.state_builder.events[self.event_idx]
        if self.navigation.pitch_items:
            self.pitch_idx = max(0, self._find_last_index(self.navigation.pitch_items, self.event_idx))
        if event.pa_id is not None and event.pa_id in self.navigation.pa_index_by_id:
            self.pa_idx = self.navigation.pa_index_by_id[event.pa_id]
        elif self.navigation.pa_items:
            self.pa_idx = max(0, self._find_last_index(self.navigation.pa_items, self.event_idx))
        inning_key = (event.inning_no, event.half)
        if inning_key in self.navigation.inning_index_by_key:
            self.inning_idx = self.navigation.inning_index_by_key[inning_key]
        elif self.navigation.inning_items:
            self.inning_idx = max(0, self._find_last_index(self.navigation.inning_items, self.event_idx))

    def _find_last_index(self, items, event_idx: int) -> int:
        match_idx = 0
        for idx, item in enumerate(items):
            if item.event_idx <= event_idx:
                match_idx = idx
            else:
                break
        return match_idx

    def render_current_view(self) -> None:
        if self.state_builder is None or not self.state_builder.events:
            self.render_empty_state()
            return
        event = self.state_builder.events[self.event_idx]
        pitch = self.current_pitch()
        state = self.state_builder.get_resolved_game_state(self.event_idx)
        participants = self.state_builder.get_event_participants(event, pitch=pitch)
        self._update_navigation_texts(event)
        self._update_focus_detail(event, state, participants)
        self.field_renderer.render(
            event=event,
            state=state,
            participants=participants,
            away_team_name=self.state_builder.dataset.context.away_team_name,
            home_team_name=self.state_builder.dataset.context.home_team_name,
            pitch_position=self.pitch_idx + 1 if self.navigation.pitch_items else 0,
            total_pitches=len(self.navigation.pitch_items),
            pa_position=self.pa_idx + 1 if self.navigation.pa_items else 0,
            total_pas=len(self.navigation.pa_items),
            event_position=self.event_idx + 1,
            total_events=len(self.state_builder.events),
        )
        self.zone_renderer.render(self.state_builder.current_pitch_tracking(pitch))

    def render_empty_state(self) -> None:
        self.loaded_game_card.set_text("Load a game to inspect replay data.")
        if dpg.does_item_exist(self._tag("event_detail")):
            dpg.set_value(self._tag("event_detail"), "Select a game and load it to inspect event detail.")
        self.event_nav.set_summary("No event data")
        self.pa_nav.set_summary("No plate appearance data")
        self.inning_nav.set_summary("No inning data")
        self.pitch_nav.set_summary("No pitch data")
        self.field_renderer.draw_background()
        self.zone_renderer.render(None)

    def _update_loaded_game_summary(self) -> None:
        if self.state_builder is None:
            self.loaded_game_card.set_text("No game loaded")
            return
        dataset = self.state_builder.dataset
        self.loaded_game_card.set_text(
            f"game_id={dataset.context.game_id}\n"
            f"{dataset.context.away_team_name} vs {dataset.context.home_team_name}\n"
            f"events={len(dataset.events)} pitches={len(dataset.pitches)} pas={len(dataset.plate_appearances)} innings={len(dataset.innings)}"
        )

    def _update_focus_detail(self, event: EventRow, state: DerivedState, participants) -> None:
        base_parts = []
        for base_no, occupied, runner_name in (
            (1, state.b1_occ, state.b1_name),
            (2, state.b2_occ, state.b2_name),
            (3, state.b3_occ, state.b3_name),
        ):
            base_parts.append(f"{base_no}B {runner_name or '-'}" if occupied else f"{base_no}B empty")
        detail = (
            f"fielding: {participants.fielding_team_name} | batting: {participants.batting_team_name}\n"
            f"event={event.event_category or '-'} | event_id={event.event_id} | seq={event.event_seq_game}\n"
            f"count={state.balls}-{state.strikes}, outs={state.outs}\n"
            f"bases: {' | '.join(base_parts)}\n"
            f"text: {event.text or '-'}"
        )
        if dpg.does_item_exist(self._tag("event_detail")):
            dpg.set_value(self._tag("event_detail"), detail)

    def _update_navigation_texts(self, event: EventRow) -> None:
        self.event_nav.set_summary(
            f"{event.event_category or '-'} {self.event_idx + 1}/{len(self.state_builder.events)}\n{(event.text or '(no text)')[:72]}"
        )
        self.event_nav.set_enabled(
            prev_enabled=self.event_idx > 0,
            next_enabled=self.event_idx < len(self.state_builder.events) - 1,
        )
        if self.navigation.pitch_items:
            pitch = self.navigation.pitch_items[self.pitch_idx].pitch
            self.pitch_nav.set_summary(
                f"pitch {self.pitch_idx + 1}/{len(self.navigation.pitch_items)}\n"
                f"num={pitch.pitch_num or '-'} | {pitch.pitch_type_text or '-'} | {pitch.speed_kph or '-'}km/h\n"
                f"{pitch.pitch_result or '-'}"
            )
            self.pitch_nav.set_enabled(
                prev_enabled=self.pitch_idx > 0,
                next_enabled=self.pitch_idx < len(self.navigation.pitch_items) - 1,
            )
        else:
            self.pitch_nav.set_summary("No pitch data")
            self.pitch_nav.set_enabled(prev_enabled=False, next_enabled=False)
        if self.navigation.pa_items:
            pa_item = self.navigation.pa_items[self.pa_idx]
            batter_name = self.state_builder.get_player_name(pa_item.pa.batter_id, f"pa_id={pa_item.pa.pa_id}")
            self.pa_nav.set_summary(
                f"pa {self.pa_idx + 1}/{len(self.navigation.pa_items)} | {self.state_builder.format_inning_label(pa_item.pa.inning_no, pa_item.pa.half)} | {batter_name}\n"
                f"{pa_item.display_result_text}"
            )
            self.pa_nav.set_enabled(prev_enabled=self.pa_idx > 0, next_enabled=self.pa_idx < len(self.navigation.pa_items) - 1)
        else:
            self.pa_nav.set_summary("No plate appearance data")
            self.pa_nav.set_enabled(prev_enabled=False, next_enabled=False)
        if self.navigation.inning_items:
            inning_item = self.navigation.inning_items[self.inning_idx]
            self.inning_nav.set_summary(
                f"{self.state_builder.format_inning_label(inning_item.inning.inning_no, inning_item.inning.half)} {self.inning_idx + 1}/{len(self.navigation.inning_items)}\n"
                f"runs={inning_item.runs_scored or 0}"
            )
            self.inning_nav.set_enabled(
                prev_enabled=self.inning_idx > 0,
                next_enabled=self.inning_idx < len(self.navigation.inning_items) - 1,
            )
        else:
            self.inning_nav.set_summary("No inning data")
            self.inning_nav.set_enabled(prev_enabled=False, next_enabled=False)
