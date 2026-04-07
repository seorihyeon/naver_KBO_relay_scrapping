from __future__ import annotations

from dataclasses import dataclass

import dearpygui.dearpygui as dpg

from .models import DerivedState, EventParticipants, EventRow, PitchContext


@dataclass
class FieldOverlayRenderer:
    drawlist_tag: str
    width: int
    height: int

    DEFENSE_ORDER = ["LF", "CF", "RF", "3B", "SS", "2B", "1B", "C", "P"]
    DEFENSE_POSITIONS = {
        "LF": (0.29, 0.21),
        "CF": (0.50, 0.12),
        "RF": (0.71, 0.21),
        "3B": (0.33, 0.58),
        "SS": (0.43, 0.45),
        "2B": (0.57, 0.45),
        "1B": (0.67, 0.58),
        "C": (0.50, 0.81),
        "P": (0.50, 0.60),
    }
    BASE_POSITIONS = {
        1: (0.61, 0.64),
        2: (0.50, 0.52),
        3: (0.39, 0.64),
    }
    RUNNER_LABEL_POSITIONS = {
        1: (0.66, 0.69),
        2: (0.56, 0.48),
        3: (0.34, 0.69),
    }

    def set_size(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def scale_px(self, value: float) -> float:
        return value * min(self.width / 1100.0, self.height / 420.0)

    def to_canvas(self, nx: float, ny: float) -> tuple[float, float]:
        return nx * self.width, ny * self.height

    def chip_size(self, text: str, font_size: int) -> tuple[int, int, int]:
        font_px = max(12, int(self.scale_px(font_size)))
        width = max(int(self.scale_px(56)), int(len(text) * font_px * 0.56) + int(self.scale_px(20)))
        height = int(font_px * 1.55)
        return width, height, font_px

    def draw_centered_chip(
        self,
        text: str,
        center_norm: tuple[float, float],
        *,
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int] = (255, 255, 255, 28),
        font_size: int = 14,
        text_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    ) -> None:
        if not text:
            return
        center_x, center_y = self.to_canvas(*center_norm)
        width, height, font_px = self.chip_size(text, font_size)
        x0 = center_x - width / 2
        y0 = center_y - height / 2
        dpg.draw_rectangle((x0, y0), (x0 + width, y0 + height), color=outline, fill=fill, rounding=self.scale_px(10), parent=self.drawlist_tag)
        dpg.draw_text((x0 + self.scale_px(10), y0 + self.scale_px(4)), text, color=text_color, size=font_px, parent=self.drawlist_tag)

    def draw_left_chip(
        self,
        text: str,
        origin_norm: tuple[float, float],
        *,
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int] = (255, 255, 255, 28),
        font_size: int = 14,
        text_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    ) -> None:
        if not text:
            return
        x0, y0 = self.to_canvas(*origin_norm)
        width, height, font_px = self.chip_size(text, font_size)
        dpg.draw_rectangle((x0, y0), (x0 + width, y0 + height), color=outline, fill=fill, rounding=self.scale_px(10), parent=self.drawlist_tag)
        dpg.draw_text((x0 + self.scale_px(10), y0 + self.scale_px(4)), text, color=text_color, size=font_px, parent=self.drawlist_tag)

    def draw_diamond(
        self,
        center_norm: tuple[float, float],
        radius_px: float,
        *,
        fill: tuple[int, int, int, int],
        outline: tuple[int, int, int, int] = (255, 255, 255, 60),
    ) -> None:
        cx, cy = self.to_canvas(*center_norm)
        radius = self.scale_px(radius_px)
        points = [(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)]
        dpg.draw_polygon(points, color=outline, fill=fill, parent=self.drawlist_tag)

    def draw_background(self) -> None:
        if not dpg.does_item_exist(self.drawlist_tag):
            return
        dpg.delete_item(self.drawlist_tag, children_only=True)
        dpg.draw_rectangle((0, 0), (self.width, self.height), fill=(38, 41, 43), color=(68, 72, 74), parent=self.drawlist_tag)
        home_norm = (0.50, 0.87)
        left_foul_norm = (0.10, 0.40)
        right_foul_norm = (0.90, 0.40)
        left_field_norm = (0.24, 0.12)
        center_field_norm = (0.50, 0.05)
        right_field_norm = (0.76, 0.12)

        field_boundary = [
            self.to_canvas(0.50, 0.99),
            self.to_canvas(0.06, 0.70),
            self.to_canvas(*left_foul_norm),
            self.to_canvas(*left_field_norm),
            self.to_canvas(*center_field_norm),
            self.to_canvas(*right_field_norm),
            self.to_canvas(*right_foul_norm),
            self.to_canvas(0.94, 0.70),
        ]
        dpg.draw_polygon(field_boundary, color=(116, 164, 118, 180), fill=(62, 134, 72, 255), parent=self.drawlist_tag)
        home = self.to_canvas(*home_norm)
        third = self.to_canvas(*self.BASE_POSITIONS[3])
        second = self.to_canvas(*self.BASE_POSITIONS[2])
        first = self.to_canvas(*self.BASE_POSITIONS[1])

        infield_dirt = [
            self.to_canvas(0.28, 0.73),
            self.to_canvas(0.34, 0.57),
            self.to_canvas(0.40, 0.44),
            self.to_canvas(0.50, 0.34),
            self.to_canvas(0.60, 0.44),
            self.to_canvas(0.66, 0.57),
            self.to_canvas(0.72, 0.73),
            self.to_canvas(0.50, 0.95),
        ]
        dpg.draw_polygon(infield_dirt, color=(177, 130, 82, 180), fill=(165, 110, 72, 255), parent=self.drawlist_tag)
        dpg.draw_polygon([home, third, second, first], color=(164, 198, 102, 60), fill=(146, 206, 84, 255), parent=self.drawlist_tag)
        dpg.draw_line(home, self.to_canvas(*left_foul_norm), color=(246, 240, 230, 255), thickness=self.scale_px(2), parent=self.drawlist_tag)
        dpg.draw_line(home, self.to_canvas(*right_foul_norm), color=(246, 240, 230, 255), thickness=self.scale_px(2), parent=self.drawlist_tag)
        dpg.draw_line(home, third, color=(233, 205, 172, 170), thickness=self.scale_px(2), parent=self.drawlist_tag)
        dpg.draw_line(third, second, color=(233, 205, 172, 170), thickness=self.scale_px(2), parent=self.drawlist_tag)
        dpg.draw_line(second, first, color=(233, 205, 172, 170), thickness=self.scale_px(2), parent=self.drawlist_tag)
        dpg.draw_line(first, home, color=(233, 205, 172, 170), thickness=self.scale_px(2), parent=self.drawlist_tag)
        dpg.draw_circle(self.to_canvas(0.50, 0.61), self.scale_px(26), color=(120, 74, 48, 210), fill=(120, 74, 48, 210), parent=self.drawlist_tag)
        dpg.draw_circle(self.to_canvas(0.50, 0.61), self.scale_px(9), color=(255, 255, 255, 160), fill=(255, 255, 255, 160), parent=self.drawlist_tag)
        plate_radius = self.scale_px(12)
        plate_x, plate_y = home
        plate_points = [
            (plate_x - plate_radius, plate_y),
            (plate_x + plate_radius, plate_y),
            (plate_x + plate_radius, plate_y + plate_radius * 0.8),
            (plate_x, plate_y + plate_radius * 1.5),
            (plate_x - plate_radius, plate_y + plate_radius * 0.8),
        ]
        dpg.draw_polygon(plate_points, color=(255, 255, 255, 220), fill=(255, 255, 255, 220), parent=self.drawlist_tag)
        for base_norm in self.BASE_POSITIONS.values():
            self.draw_diamond(base_norm, 10, fill=(252, 244, 232, 230))

    def render(
        self,
        *,
        event: EventRow,
        state: DerivedState,
        participants: EventParticipants,
        away_team_name: str,
        home_team_name: str,
        pitch_position: int,
        total_pitches: int,
        pa_position: int,
        total_pas: int,
        event_position: int,
        total_events: int,
    ) -> None:
        self.draw_background()
        self._draw_score_bug(event, state, participants, away_team_name, home_team_name, pitch_position, total_pitches, event_position, total_events)
        self._draw_players(participants, state)
        header_text = f"{event.inning_no or '-'} {'T' if event.half == 'top' else 'B'} | pitch {pitch_position}/{total_pitches} | pa {pa_position}/{total_pas}"
        self.draw_left_chip(header_text, (0.22, 0.04), fill=(28, 33, 35, 220), font_size=14)

    def _draw_score_bug(
        self,
        event: EventRow,
        state: DerivedState,
        participants: EventParticipants,
        away_team_name: str,
        home_team_name: str,
        pitch_position: int,
        total_pitches: int,
        event_position: int,
        total_events: int,
    ) -> None:
        box_x0, box_y0 = self.to_canvas(0.02, 0.04)
        box_x1, box_y1 = self.to_canvas(0.17, 0.60)
        dpg.draw_rectangle((box_x0, box_y0), (box_x1, box_y1), color=(255, 255, 255, 30), fill=(17, 51, 34, 220), rounding=self.scale_px(8), parent=self.drawlist_tag)
        row_h = self.scale_px(34)
        dpg.draw_rectangle((box_x0, box_y0), (box_x1, box_y0 + row_h), color=(0, 0, 0, 0), fill=(234, 129, 51, 240), parent=self.drawlist_tag)
        dpg.draw_rectangle((box_x0, box_y0 + row_h), (box_x1, box_y0 + row_h * 2), color=(0, 0, 0, 0), fill=(41, 55, 93, 240), parent=self.drawlist_tag)
        big_font = max(13, int(self.scale_px(16)))
        small_font = max(11, int(self.scale_px(12)))
        dpg.draw_text((box_x0 + self.scale_px(10), box_y0 + self.scale_px(6)), f"{away_team_name} {state.away_score}", color=(255, 255, 255, 255), size=big_font, parent=self.drawlist_tag)
        dpg.draw_text((box_x0 + self.scale_px(10), box_y0 + self.scale_px(40)), f"{home_team_name} {state.home_score}", color=(255, 255, 255, 255), size=big_font, parent=self.drawlist_tag)
        inning_label = f"{event.inning_no or '-'}{'T' if event.half == 'top' else 'B'}"
        dpg.draw_text((box_x0 + self.scale_px(12), box_y0 + self.scale_px(82)), inning_label, color=(255, 255, 255, 255), size=small_font, parent=self.drawlist_tag)
        dpg.draw_text((box_x0 + self.scale_px(12), box_y0 + self.scale_px(102)), f"event {event_position}/{total_events}", color=(204, 222, 212, 255), size=small_font, parent=self.drawlist_tag)
        for row_idx, (label, active_count, max_lights, fill_color) in enumerate(
            [
                ("B", min(max(state.balls, 0), 3), 3, (86, 194, 117, 255)),
                ("S", min(max(state.strikes, 0), 2), 2, (247, 203, 67, 255)),
                ("O", min(max(state.outs, 0), 2), 2, (238, 93, 93, 255)),
            ]
        ):
            y = box_y0 + self.scale_px(142 + row_idx * 24)
            dpg.draw_text((box_x0 + self.scale_px(10), y - self.scale_px(7)), label, color=(235, 235, 235, 255), size=small_font, parent=self.drawlist_tag)
            for light_idx in range(max_lights):
                cx = box_x0 + self.scale_px(34 + light_idx * 18)
                fill = fill_color if light_idx < active_count else (84, 110, 92, 180)
                dpg.draw_circle((cx, y), self.scale_px(5), color=(255, 255, 255, 22), fill=fill, parent=self.drawlist_tag)
        if state.count_status_label:
            self.draw_left_chip(state.count_status_label, (0.024, 0.405), fill=(77, 58, 28, 236), font_size=12)
        for base_no, origin in {1: (0.145, 0.295), 2: (0.128, 0.258), 3: (0.111, 0.295)}.items():
            occupied = {1: state.b1_occ, 2: state.b2_occ, 3: state.b3_occ}[base_no]
            fill = (255, 204, 82, 255) if occupied else (90, 110, 98, 180)
            self.draw_diamond(origin, 7, fill=fill)
        self.draw_left_chip(f"P {participants.pitcher_name}", (0.024, 0.47), fill=(23, 62, 44, 230), font_size=13)
        self.draw_left_chip(f"B {participants.batter_name}", (0.024, 0.535), fill=(86, 68, 38, 236), font_size=13)

    def _draw_players(self, participants: EventParticipants, state: DerivedState) -> None:
        for position in self.DEFENSE_ORDER:
            player_name = participants.lineup.get(position)
            if not player_name:
                continue
            self.draw_centered_chip(player_name, self.DEFENSE_POSITIONS[position], fill=(23, 57, 43, 226), font_size=13)
        if participants.batter_name and participants.batter_name != "-":
            if participants.batter_side == "L":
                batter_pos = (0.60, 0.89)
            elif participants.batter_side == "R":
                batter_pos = (0.40, 0.89)
            else:
                batter_pos = (0.50, 0.90)
            self.draw_centered_chip(f"B {participants.batter_name}", batter_pos, fill=(96, 72, 37, 236), font_size=13)
        for base_no, occupied, runner_name in (
            (1, state.b1_occ, state.b1_name),
            (2, state.b2_occ, state.b2_name),
            (3, state.b3_occ, state.b3_name),
        ):
            if not occupied:
                continue
            self.draw_centered_chip(runner_name or f"R{base_no}", self.RUNNER_LABEL_POSITIONS[base_no], fill=(149, 118, 43, 236), font_size=12)


@dataclass
class StrikeZoneRenderer:
    drawlist_tag: str
    width: int
    height: int
    meta_text_tag: str

    def set_size(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def render(self, pitch_context: PitchContext | None) -> None:
        if not dpg.does_item_exist(self.drawlist_tag):
            return
        dpg.delete_item(self.drawlist_tag, children_only=True)
        dpg.draw_rectangle((0, 0), (self.width, self.height), fill=(31, 38, 42), color=(74, 88, 96), rounding=8, parent=self.drawlist_tag)
        if not pitch_context:
            dpg.draw_text((18, 18), "No pitch tracking", color=(220, 220, 220), size=16, parent=self.drawlist_tag)
            if dpg.does_item_exist(self.meta_text_tag):
                dpg.set_value(self.meta_text_tag, "No pitch selected")
            return
        zone_left = 46
        zone_right = self.width - 46
        zone_top_px = 34
        zone_bottom_px = self.height - 46
        dpg.draw_rectangle((zone_left, zone_top_px), (zone_right, zone_bottom_px), color=(114, 135, 144), fill=(24, 34, 40), parent=self.drawlist_tag)
        top_ft = pitch_context.zone_top
        bottom_ft = pitch_context.zone_bottom
        half_width_ft = pitch_context.zone_half_width
        if top_ft is None or bottom_ft is None or half_width_ft is None:
            dpg.draw_text((18, 18), "Missing strike-zone data", color=(220, 220, 220), size=16, parent=self.drawlist_tag)
            if dpg.does_item_exist(self.meta_text_tag):
                dpg.set_value(self.meta_text_tag, "Missing strike-zone data")
            return

        zone_height_ft = max(0.1, top_ft - bottom_ft)
        x_range = max(0.95, half_width_ft * 1.7)
        z_pad = max(0.55, zone_height_ft * 0.32)
        z_min = max(0.5, bottom_ft - z_pad)
        z_max = max(top_ft + z_pad, bottom_ft + 1.0)

        def scale_x(value: float) -> float:
            return zone_left + ((value + x_range) / (x_range * 2)) * (zone_right - zone_left)

        def scale_z(value: float) -> float:
            return zone_bottom_px - ((value - z_min) / (z_max - z_min)) * (zone_bottom_px - zone_top_px)

        strike_left = scale_x(-half_width_ft)
        strike_right = scale_x(half_width_ft)
        strike_top = scale_z(top_ft)
        strike_bottom = scale_z(bottom_ft)
        dpg.draw_rectangle((strike_left, strike_top), (strike_right, strike_bottom), color=(241, 236, 212), fill=(42, 80, 106, 120), thickness=2, parent=self.drawlist_tag)
        third_w = (strike_right - strike_left) / 3.0
        third_h = (strike_bottom - strike_top) / 3.0
        for idx in range(1, 3):
            dpg.draw_line((strike_left + third_w * idx, strike_top), (strike_left + third_w * idx, strike_bottom), color=(255, 255, 255, 40), parent=self.drawlist_tag)
            dpg.draw_line((strike_left, strike_top + third_h * idx), (strike_right, strike_top + third_h * idx), color=(255, 255, 255, 40), parent=self.drawlist_tag)
        is_in_zone = (
            pitch_context.plate_x is not None
            and pitch_context.plate_z is not None
            and abs(pitch_context.plate_x) <= half_width_ft
            and bottom_ft <= pitch_context.plate_z <= top_ft
        )
        if pitch_context.plate_x is not None and pitch_context.plate_z is not None:
            px = scale_x(max(-x_range, min(x_range, pitch_context.plate_x)))
            py = scale_z(max(z_min, min(z_max, pitch_context.plate_z)))
            pitch_color = (253, 223, 82) if is_in_zone else (255, 121, 76)
            dpg.draw_circle((px, py), 7, color=(18, 22, 24), fill=pitch_color, thickness=2, parent=self.drawlist_tag)
        dpg.draw_text((14, 10), "Strike Zone", color=(238, 238, 238), size=15, parent=self.drawlist_tag)
        stance_label = {"L": "Left", "R": "Right", "S": "Switch"}.get(pitch_context.stance, "Unknown stance")
        meta_text = f"Rule {pitch_context.rule_year} | {stance_label}"
        dpg.draw_text((14, self.height - 28), meta_text, color=(194, 206, 214), size=13, parent=self.drawlist_tag)
        if dpg.does_item_exist(self.meta_text_tag):
            dpg.set_value(self.meta_text_tag, meta_text)
