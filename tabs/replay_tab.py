from __future__ import annotations

import math
import re

import dearpygui.dearpygui as dpg

from .shared_state import AppState


class ReplayTab:
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
    POSITION_ALIASES = {
        "1": "P",
        "투수": "P",
        "선발투수": "P",
        "2": "C",
        "포수": "C",
        "3": "1B",
        "1루수": "1B",
        "4": "2B",
        "2루수": "2B",
        "5": "3B",
        "3루수": "3B",
        "6": "SS",
        "유격수": "SS",
        "7": "LF",
        "좌익수": "LF",
        "8": "CF",
        "중견수": "CF",
        "9": "RF",
        "우익수": "RF",
        "0": "DH",
        "지명타자": "DH",
    }
    POSITION_PATTERN = r"(투수|포수|1루수|2루수|3루수|유격수|좌익수|중견수|우익수)"

    def __init__(self, state: AppState):
        self.state = state
        self.events = []
        self.pitches = []
        self.pas = []
        self.innings = []
        self.substitutions = []

        self.event_idx = 0
        self.pitch_idx = 0
        self.pa_idx = 0
        self.inning_idx = 0

        self.pitch_state_by_event = {}
        self.pa_state_by_id = {}
        self.pa_lookup_by_id = {}
        self.derived_state_by_event = {}
        self.player_name_by_id = {}
        self.player_height_by_id = {}
        self.player_batting_side_by_id = {}
        self.player_team_by_name = {}
        self.team_name_by_id = {}
        self.starting_defense_by_team = {}
        self.defense_snapshots_by_event = {}
        self.game_context = {}
        self.pa_event_columns = None

        self.event_index_by_id = {}
        self.event_index_by_seq = {}
        self.event_indices_by_pa_id = {}
        self.event_indices_by_inning_key = {}
        self.pitch_nav_items = []
        self.pa_nav_items = []
        self.inning_nav_items = []
        self.pa_index_by_id = {}
        self.inning_index_by_key = {}

        self.DEFAULT_VIEWPORT_W = 1440
        self.DEFAULT_VIEWPORT_H = 940
        self.PANEL_GAP = 8
        self.CONTROL_PANEL_HEIGHT = 46
        self.STAGE_MIN_HEIGHT = 336
        self.BOTTOM_INFO_MIN_HEIGHT = 100
        self.PITCH_SECTION_MIN_HEIGHT = 110
        self.NAV_PANEL_HEIGHT = 84
        self.NAV_TEXT_MIN_HEIGHT = 34
        self.NAV_BUTTON_HEIGHT = 28
        self.NAV_BUTTON_GAP = 8
        self.CANVAS_MIN_WIDTH = 460
        self.CANVAS_MIN_HEIGHT = 248
        self.DETAIL_TEXT_HEIGHT = 58
        self.RELAY_TEXT_MIN_HEIGHT = 96

        self.canvas_w = 1100
        self.canvas_h = 420
        self.strike_zone_w = 240
        self.strike_zone_h = 260
        self.stage_count_w = 88
        self.stage_count_h = 76

    def safe_int(self, value):
        try:
            return int(value) if value is not None else None
        except Exception:
            return None

    def clamp(self, value, min_value, max_value):
        return max(min_value, min(int(value), max_value))

    def set_text_value_if_exists(self, tag, value):
        if dpg.does_item_exist(tag):
            dpg.set_value(tag, value)

    def format_half(self, half):
        return "초" if half == "top" else "말"

    def format_inning_label(self, inning_no, half):
        if inning_no is None:
            return "이닝 정보 없음"
        return f"{inning_no}회{self.format_half(half)}"

    def get_player_name(self, player_id, fallback="-"):
        if player_id and player_id in self.player_name_by_id:
            return self.player_name_by_id[player_id]
        return fallback

    def get_team_name(self, team_id, fallback="-"):
        if team_id in self.team_name_by_id:
            return self.team_name_by_id[team_id]
        return fallback

    def parse_batting_side(self, raw_text):
        if not raw_text:
            return None
        text = str(raw_text)
        if "우타" in text:
            return "R"
        if "좌타" in text:
            return "L"
        if "양타" in text:
            return "S"
        return None

    def cm_to_ft(self, cm_value):
        if cm_value is None:
            return None
        return float(cm_value) / 30.48

    def get_game_year(self):
        game_date = self.game_context.get("game_date")
        return getattr(game_date, "year", None)

    def get_regulation_strike_zone(self, batter_id, fallback_top=None, fallback_bottom=None):
        height_cm = self.player_height_by_id.get(batter_id)
        year = self.get_game_year()
        rule = self.state.get_strike_zone_rule(year)
        if height_cm:
            top_ft = self.cm_to_ft(height_cm * rule["top_pct"])
            bottom_ft = self.cm_to_ft(height_cm * rule["bottom_pct"])
        else:
            top_ft = fallback_top
            bottom_ft = fallback_bottom
        half_width_ft = self.cm_to_ft(rule["width_cm"] / 2.0)
        return {
            "top_ft": top_ft,
            "bottom_ft": bottom_ft,
            "half_width_ft": half_width_ft,
            "height_cm": height_cm,
            "effective_year": rule["effective_year"],
            "width_cm": rule["width_cm"],
        }

    def solve_pitch_plate_height(self, pitch_item):
        cross_plate_y = pitch_item.get("cross_plate_y")
        y0 = pitch_item.get("y0")
        vy0 = pitch_item.get("vy0")
        ay = pitch_item.get("ay")
        z0 = pitch_item.get("z0")
        vz0 = pitch_item.get("vz0")
        az = pitch_item.get("az")
        if None in {cross_plate_y, y0, vy0, ay, z0, vz0, az}:
            return None

        a = 0.5 * ay
        b = vy0
        c = y0 - cross_plate_y
        t = None
        if abs(a) < 1e-9:
            if abs(b) < 1e-9:
                return None
            t = -c / b
        else:
            discriminant = b * b - 4 * a * c
            if discriminant < 0:
                return None
            root = math.sqrt(discriminant)
            candidates = [(-b - root) / (2 * a), (-b + root) / (2 * a)]
            positive_times = [candidate for candidate in candidates if candidate >= 0]
            if not positive_times:
                return None
            t = min(positive_times)

        if t is None or t < 0:
            return None
        return z0 + vz0 * t + 0.5 * az * t * t

    def current_pitch_tracking(self):
        pitch_item = self.current_pitch_item()
        if not pitch_item:
            return None

        pa_info = self.pa_lookup_by_id.get(pitch_item["pa_id"], {})
        regulation_zone = self.get_regulation_strike_zone(
            pa_info.get("batter_id"),
            fallback_top=pitch_item.get("tracking_top"),
            fallback_bottom=pitch_item.get("tracking_bottom"),
        )
        plate_z = self.solve_pitch_plate_height(pitch_item)
        return {
            "pitch": pitch_item,
            "plate_x": pitch_item.get("cross_plate_x"),
            "plate_z": plate_z,
            "zone_top": regulation_zone["top_ft"] or pitch_item.get("tracking_top"),
            "zone_bottom": regulation_zone["bottom_ft"] or pitch_item.get("tracking_bottom"),
            "zone_half_width": regulation_zone["half_width_ft"],
            "rule_year": regulation_zone["effective_year"],
            "batter_height_cm": regulation_zone["height_cm"],
            "width_cm": regulation_zone["width_cm"],
            "stance": pitch_item.get("stance"),
        }

    def resolve_batter_stance(self, batter_id, event=None):
        pitch_context = self.current_pitch_tracking()
        if pitch_context and pitch_context["pitch"] and pitch_context["pitch"].get("pa_id") == (event[4] if event else None):
            stance = pitch_context.get("stance")
            if stance in {"L", "R", "S"}:
                return stance
        return self.player_batting_side_by_id.get(batter_id)

    def canonical_position(self, value):
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        return self.POSITION_ALIASES.get(raw)

    def infer_batter_name_from_text(self, text):
        if not text:
            return None
        match = re.match(r"([^ :]+)\s*:", text.strip())
        if match:
            return match.group(1).strip()
        return None

    def clear_player_from_lineup(self, lineup, player_name):
        for position, name in list(lineup.items()):
            if name == player_name:
                del lineup[position]

    def get_available_content_size(self):
        width = self.DEFAULT_VIEWPORT_W - 70
        height = self.DEFAULT_VIEWPORT_H - 220
        if dpg.does_item_exist("main_window"):
            rect_w, rect_h = dpg.get_item_rect_size("main_window")
            if rect_w:
                width = rect_w - 34
            if rect_h:
                height = rect_h - 54
        return max(820, int(width)), max(640, int(height))

    def compute_layout_metrics(self, content_w, content_h):
        available_h = max(500, content_h - self.CONTROL_PANEL_HEIGHT - self.PANEL_GAP * 2)
        stage_h = max(self.STAGE_MIN_HEIGHT, int(available_h * 0.8))
        bottom_h = available_h - stage_h
        if bottom_h < self.BOTTOM_INFO_MIN_HEIGHT:
            stage_h = max(self.STAGE_MIN_HEIGHT, available_h - self.BOTTOM_INFO_MIN_HEIGHT)
            bottom_h = available_h - stage_h

        # Account for the child window's inner padding/border so the left/right
        # cards and center field fit fully inside the stage panel without clipping.
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

        nav_body_reserved = 60
        pitch_body_h = max(self.NAV_TEXT_MIN_HEIGHT, right_pitch_h - nav_body_reserved)
        pa_body_h = max(self.NAV_TEXT_MIN_HEIGHT, left_pa_h - nav_body_reserved)
        event_body_h = max(self.NAV_TEXT_MIN_HEIGHT, left_event_h - nav_body_reserved)
        inning_body_h = max(self.NAV_TEXT_MIN_HEIGHT, left_inning_h - nav_body_reserved)

        inspector_w = content_w

        return {
            "content_w": content_w,
            "content_h": content_h,
            "stage_h": stage_h,
            "bottom_h": bottom_h,
            "canvas_w": canvas_w,
            "canvas_h": canvas_h,
            "side_w": side_w,
            "stage_body_h": stage_body_h,
            "left_event_h": left_event_h,
            "left_pa_h": left_pa_h,
            "left_inning_h": left_inning_h,
            "event_body_h": event_body_h,
            "inning_body_h": inning_body_h,
            "right_pitch_h": right_pitch_h,
            "strike_h": strike_h,
            "pitch_body_h": pitch_body_h,
            "pa_body_h": pa_body_h,
            "inspector_w": max(260, inspector_w),
            "warning_table_h": max(52, bottom_h - self.DETAIL_TEXT_HEIGHT - 74),
        }

    def current_event_id(self):
        if not self.events:
            return None
        return self.events[self.event_idx][0]

    def current_pitch_item(self):
        if not self.pitch_nav_items:
            return None
        return self.pitch_nav_items[self.pitch_idx]

    def current_pa_item(self):
        if not self.pa_nav_items:
            return None
        return self.pa_nav_items[self.pa_idx]

    def current_inning_item(self):
        if not self.inning_nav_items:
            return None
        return self.inning_nav_items[self.inning_idx]

    def format_base_state(self, state):
        labels = []
        for base_no in (1, 2, 3):
            occupied = state.get(f"b{base_no}_occ")
            runner_name = state.get(f"b{base_no}_name")
            if occupied:
                labels.append(f"{base_no}루 {runner_name or '주자 미상'}")
            else:
                labels.append(f"{base_no}루 비움")
        return " | ".join(labels)

    def update_loaded_game_summary(self):
        selected_label = dpg.get_value("game_combo") if dpg.does_item_exist("game_combo") else ""
        if self.state.game_id is None:
            summary = "게임을 로드하면 이벤트, 투구, 타석, 이닝 개요가 여기에 표시됩니다."
        else:
            home_name = self.game_context.get("home_team_name", "HOME")
            away_name = self.game_context.get("away_team_name", "AWAY")
            summary = (
                f"{selected_label or f'game_id={self.state.game_id}'}\n"
                f"{away_name} vs {home_name}\n"
                f"이벤트 {len(self.events)}건 | 투구 {len(self.pitches)}건\n"
                f"타석 {len(self.pas)}건 | 이닝 {len(self.innings)}건"
            )
        self.set_text_value_if_exists("loaded_game_summary_text", summary)

    def get_fielding_team_id(self, event):
        home_team_id = self.game_context.get("home_team_id")
        away_team_id = self.game_context.get("away_team_id")
        if event[3] == "top":
            return home_team_id
        if event[3] == "bottom":
            return away_team_id
        return None

    def get_batting_team_id(self, event):
        home_team_id = self.game_context.get("home_team_id")
        away_team_id = self.game_context.get("away_team_id")
        if event[3] == "top":
            return away_team_id
        if event[3] == "bottom":
            return home_team_id
        return None

    def get_lineup_snapshot(self, event_id, team_id):
        snapshot = self.defense_snapshots_by_event.get(event_id, {})
        lineup = snapshot.get(team_id)
        if lineup is not None:
            return lineup
        return self.starting_defense_by_team.get(team_id, {})

    def get_event_participants(self, event):
        pa_id = event[4]
        pa_info = self.pa_lookup_by_id.get(pa_id, {})
        batter_id = pa_info.get("batter_id")
        batter_name = self.get_player_name(pa_info.get("batter_id")) if pa_info.get("batter_id") else "-"
        pitcher_name = self.get_player_name(pa_info.get("pitcher_id")) if pa_info.get("pitcher_id") else "-"
        if batter_name == "-":
            batter_name = self.infer_batter_name_from_text(event[7]) or "-"

        fielding_team_id = self.get_fielding_team_id(event)
        batting_team_id = self.get_batting_team_id(event)
        lineup = self.get_lineup_snapshot(event[0], fielding_team_id)
        if pitcher_name == "-" and lineup.get("P"):
            pitcher_name = lineup.get("P")

        return {
            "batter_name": batter_name,
            "pitcher_name": pitcher_name,
            "fielding_team_id": fielding_team_id,
            "fielding_team_name": self.get_team_name(fielding_team_id, "수비팀"),
            "batting_team_id": batting_team_id,
            "batting_team_name": self.get_team_name(batting_team_id, "공격팀"),
            "lineup": lineup,
            "batter_side": self.resolve_batter_stance(batter_id, event),
        }

    def update_current_focus_summary(self, event=None, state=None):
        if not self.events or event is None:
            self.set_text_value_if_exists("current_event_summary_text", "이벤트, 투구, 타석, 이닝 이동 버튼으로 현재 위치를 맞출 수 있습니다.")
            self.set_text_value_if_exists("relay_text", "게임을 먼저 로드해 주세요.")
            self.set_text_value_if_exists("event_detail_text", "검증 상세 정보가 여기에 표시됩니다.")
            return

        if state is None:
            state = self.get_resolved_game_state(self.event_idx)
        count_display = state.get("count_display") or self.get_count_display(event, state)

        participants = self.get_event_participants(event)
        detail = (
            f"수비팀: {participants['fielding_team_name']} | 공격팀: {participants['batting_team_name']}\n"
            f"이벤트: {event[6] or '-'} | event_id={event[0]} | seq={event[1]}\n"
            f"주자: {self.format_base_state(state)}"
        )
        if count_display["status_label"]:
            detail += f"\n판정 상태: {count_display['status_label']}"

        self.set_text_value_if_exists("event_detail_text", detail)

    def update_navigation_panel(self):
        if self.events:
            event = self.events[self.event_idx]
            event_text = (
                f"이벤트: {event[6] or '-'} {self.event_idx + 1}/{len(self.events)}\n"
                f"{(event[7] or '(텍스트 없음)')[:56]}"
            )
        else:
            event_text = "이벤트 데이터 없음"
        self.set_text_value_if_exists("event_nav_text", event_text)

        pitch_item = self.current_pitch_item()
        if pitch_item:
            pitch_text = (
                f"투구 {self.pitch_idx + 1} / {len(self.pitch_nav_items)}\n"
                f"{pitch_item['pitch_num'] or '-'}구 | {pitch_item['pitch_type']} | {pitch_item['speed_kph'] or '-'}km/h\n"
                f"{pitch_item['pitch_result']}"
            )
        else:
            pitch_text = "투구 데이터 없음"
        self.set_text_value_if_exists("pitch_nav_text", pitch_text)

        pa_item = self.current_pa_item()
        if pa_item:
            batter_name = self.get_player_name(pa_item["batter_id"], f"pa_id={pa_item['pa_id']}")
            pa_display_text = self.get_pa_display_text(pa_item, self.event_idx)
            pa_text = (
                f"타석 {self.pa_idx + 1}/{len(self.pa_nav_items)} | {self.format_inning_label(pa_item['inning_no'], pa_item['half'])} | {batter_name}\n"
                f"{pa_display_text}"
            )
        else:
            pa_text = "타석 데이터 없음"
        self.set_text_value_if_exists("pa_nav_text", pa_text)

        inning_item = self.current_inning_item()
        if inning_item:
            inning_text = (
                f"이닝 {self.format_inning_label(inning_item['inning_no'], inning_item['half'])} {self.inning_idx + 1}/{len(self.inning_nav_items)}"
            )
            if inning_item.get("runs_scored") is not None:
                inning_text += f"\n{inning_item['runs_scored']}득점"
        else:
            inning_text = "이닝 데이터 없음"
        self.set_text_value_if_exists("inning_nav_text", inning_text)

        button_states = {
            "event_prev_button": bool(self.events) and self.event_idx > 0,
            "event_next_button": bool(self.events) and self.event_idx < len(self.events) - 1,
            "pitch_prev_button": bool(self.pitch_nav_items) and self.pitch_idx > 0,
            "pitch_next_button": bool(self.pitch_nav_items) and self.pitch_idx < len(self.pitch_nav_items) - 1,
            "pa_prev_button": bool(self.pa_nav_items) and self.pa_idx > 0,
            "pa_next_button": bool(self.pa_nav_items) and self.pa_idx < len(self.pa_nav_items) - 1,
            "inning_prev_button": bool(self.inning_nav_items) and self.inning_idx > 0,
            "inning_next_button": bool(self.inning_nav_items) and self.inning_idx < len(self.inning_nav_items) - 1,
        }
        for tag, enabled in button_states.items():
            if dpg.does_item_exist(tag):
                dpg.configure_item(tag, enabled=enabled)

    def find_event_index_by_event_id(self, event_id):
        return self.event_index_by_id.get(event_id)

    def resolve_anchor_event_index(self, start_seqno=None, end_seqno=None, fallback_indices=None, prefer_last=False):
        for seqno in (end_seqno, start_seqno):
            if seqno is None:
                continue
            event_idx = self.event_index_by_seq.get(seqno)
            if event_idx is not None:
                return event_idx
        if fallback_indices:
            return fallback_indices[-1] if prefer_last else fallback_indices[0]
        return None

    def is_meaningful_pa_text(self, text):
        clean_text = (text or "").strip()
        if not clean_text or clean_text == "-":
            return False
        if re.match(r"^\d+번타자\s+", clean_text):
            return False
        return True

    def get_pa_display_text(self, pa_item, event_idx=None):
        if not pa_item:
            return "-"

        raw_result = (pa_item.get("result_text") or "").strip()
        if self.is_meaningful_pa_text(raw_result):
            return raw_result

        if event_idx is None:
            event_idx = self.event_idx
        current_event = self.events[event_idx] if self.events and 0 <= event_idx < len(self.events) else None
        pa_id = pa_item.get("pa_id")

        anchor_text = None
        pa_state = self.pa_state_by_id.get(pa_id, {})
        for seqno in (pa_state.get("end_seqno"), pa_state.get("start_seqno")):
            if seqno is None:
                continue
            anchor_idx = self.event_index_by_seq.get(seqno)
            if anchor_idx is None or anchor_idx > event_idx:
                continue
            candidate = (self.events[anchor_idx][7] or "").strip()
            if self.is_meaningful_pa_text(candidate):
                anchor_text = candidate
                break

        if current_event and current_event[4] == pa_id and current_event[6] == "baserunning" and anchor_text:
            return anchor_text

        for candidate_idx in reversed(self.event_indices_by_pa_id.get(pa_id, [])):
            if candidate_idx > event_idx:
                continue
            candidate = (self.events[candidate_idx][7] or "").strip()
            if self.is_meaningful_pa_text(candidate):
                return candidate

        if anchor_text:
            return anchor_text
        return "타석 진행 중"

    def compute_inning_runs_from_events(self, half, event_indices, fallback_runs=0):
        fallback_value = self.safe_int(fallback_runs)
        if not event_indices:
            return fallback_value if fallback_value is not None else 0

        start_idx = min(event_indices)
        end_idx = max(event_indices)

        prev_home = prev_away = 0
        if start_idx > 0:
            prev_state = self.get_resolved_game_state(start_idx - 1)
            prev_home = prev_state["home_score"]
            prev_away = prev_state["away_score"]

        end_state = self.get_resolved_game_state(end_idx)
        if half == "top":
            computed_runs = end_state["away_score"] - prev_away
        else:
            computed_runs = end_state["home_score"] - prev_home

        if computed_runs < 0:
            return fallback_value if fallback_value is not None else 0
        if fallback_value is not None and computed_runs == 0 and fallback_value > 0:
            return fallback_value
        return computed_runs

    def should_merge_pa_with_previous(self, pa_row, previous_display_item):
        if not pa_row or not previous_display_item:
            return False

        raw_result = (pa_row[10] or "").strip()
        if self.is_meaningful_pa_text(raw_result):
            return False

        if pa_row[4] != previous_display_item.get("batter_id") or pa_row[5] != previous_display_item.get("pitcher_id"):
            return False

        previous_end_seq = self.safe_int(previous_display_item.get("end_seqno"))
        current_start_seq = self.safe_int(pa_row[12])
        if previous_end_seq is not None and current_start_seq is not None and current_start_seq > previous_end_seq + 1:
            return False

        event_indices = self.event_indices_by_pa_id.get(pa_row[0], [])
        if not event_indices:
            return False

        categories = {self.events[idx][6] or "" for idx in event_indices}
        continuation_categories = {"baserunning", "other"}
        return bool(categories) and categories.issubset(continuation_categories)

    def build_navigation_models(self):
        self.event_index_by_id = {event[0]: idx for idx, event in enumerate(self.events)}
        self.event_index_by_seq = {event[1]: idx for idx, event in enumerate(self.events)}
        self.event_indices_by_pa_id = {}
        self.event_indices_by_inning_key = {}

        for idx, event in enumerate(self.events):
            pa_id = event[4]
            if pa_id is not None:
                self.event_indices_by_pa_id.setdefault(pa_id, []).append(idx)
            inning_key = (event[2], event[3])
            self.event_indices_by_inning_key.setdefault(inning_key, []).append(idx)

        self.pitch_nav_items = []
        for pitch in self.pitches:
            event_idx = self.find_event_index_by_event_id(pitch[1])
            if event_idx is None:
                continue
            self.pitch_nav_items.append(
                {
                    "event_idx": event_idx,
                    "event_id": pitch[1],
                    "pitch_id": pitch[0],
                    "pa_id": pitch[2],
                    "pitch_num": self.safe_int(pitch[4]),
                    "pitch_result": pitch[5] or "-",
                    "pitch_type": pitch[6] or "-",
                    "speed_kph": pitch[7],
                    "cross_plate_x": pitch[14],
                    "cross_plate_y": pitch[15],
                    "tracking_top": pitch[16],
                    "tracking_bottom": pitch[17],
                    "x0": pitch[18],
                    "y0": pitch[19],
                    "z0": pitch[20],
                    "vx0": pitch[21],
                    "vy0": pitch[22],
                    "vz0": pitch[23],
                    "ax": pitch[24],
                    "ay": pitch[25],
                    "az": pitch[26],
                    "stance": pitch[27],
                }
            )
        self.pitch_nav_items.sort(key=lambda item: (item["event_idx"], item["pitch_id"]))

        self.pa_nav_items = []
        self.pa_index_by_id = {}
        last_display_item = None
        for pa in self.pas:
            pa_id = pa[0]
            fallback_indices = self.event_indices_by_pa_id.get(pa_id, [])
            event_idx = fallback_indices[-1] if fallback_indices else self.resolve_anchor_event_index(
                start_seqno=self.safe_int(pa[12]),
                end_seqno=self.safe_int(pa[13]),
                fallback_indices=fallback_indices,
                prefer_last=True,
            )
            if event_idx is None:
                continue
            if self.should_merge_pa_with_previous(pa, last_display_item):
                display_index = len(self.pa_nav_items) - 1
                self.pa_index_by_id[pa_id] = display_index
                if pa_id in self.pa_lookup_by_id:
                    self.pa_lookup_by_id[pa_id]["display_pa_id"] = last_display_item["pa_id"]
                    self.pa_lookup_by_id[pa_id]["display_pa_seq_game"] = last_display_item["pa_seq_game"]
                continue

            item = {
                "event_idx": event_idx,
                "pa_id": pa_id,
                "pa_seq_game": pa[1],
                "inning_no": pa[2],
                "half": pa[3],
                "batter_id": pa[4],
                "pitcher_id": pa[5],
                "result_text": pa[10] or "-",
                "start_seqno": self.safe_int(pa[12]),
                "end_seqno": self.safe_int(pa[13]),
            }
            self.pa_index_by_id[pa_id] = len(self.pa_nav_items)
            self.pa_nav_items.append(item)
            last_display_item = item

        self.inning_nav_items = []
        self.inning_index_by_key = {}
        for inning in self.innings:
            inning_key = (inning[1], inning[2])
            fallback_indices = self.event_indices_by_inning_key.get(inning_key, [])
            event_idx = fallback_indices[0] if fallback_indices else self.resolve_anchor_event_index(
                start_seqno=self.safe_int(inning[9]),
                end_seqno=self.safe_int(inning[10]),
                fallback_indices=fallback_indices,
                prefer_last=False,
            )
            if event_idx is None:
                continue
            self.inning_index_by_key[inning_key] = len(self.inning_nav_items)
            self.inning_nav_items.append(
                {
                    "event_idx": event_idx,
                    "inning_id": inning[0],
                    "inning_no": inning[1],
                    "half": inning[2],
                    "runs_scored": self.compute_inning_runs_from_events(inning[2], fallback_indices, inning[5]),
                }
            )

    def find_pitch_index_for_event(self, event_idx):
        if not self.pitch_nav_items:
            return 0
        match_idx = 0
        for idx, item in enumerate(self.pitch_nav_items):
            if item["event_idx"] <= event_idx:
                match_idx = idx
            else:
                break
        return match_idx

    def find_last_nav_index_at_or_before(self, items, event_idx):
        if not items:
            return 0
        match_idx = 0
        for idx, item in enumerate(items):
            if item["event_idx"] <= event_idx:
                match_idx = idx
            else:
                break
        return match_idx

    def sync_navigation_indices_from_event(self):
        if not self.events:
            self.pitch_idx = self.pa_idx = self.inning_idx = 0
            return

        event = self.events[self.event_idx]
        self.pitch_idx = self.find_pitch_index_for_event(self.event_idx)

        pa_id = event[4]
        if pa_id in self.pa_index_by_id:
            self.pa_idx = self.pa_index_by_id[pa_id]
        else:
            self.pa_idx = self.find_last_nav_index_at_or_before(self.pa_nav_items, self.event_idx)

        inning_key = (event[2], event[3])
        if inning_key in self.inning_index_by_key:
            self.inning_idx = self.inning_index_by_key[inning_key]
        else:
            self.inning_idx = self.find_last_nav_index_at_or_before(self.inning_nav_items, self.event_idx)

    def set_focus_event_index(self, event_idx):
        if not self.events:
            return
        self.event_idx = self.clamp(event_idx, 0, len(self.events) - 1)
        self.sync_navigation_indices_from_event()
        self.render_event()

    def move_focus(self, kind, delta):
        if kind == "event":
            self.set_focus_event_index(self.event_idx + delta)
            return

        nav_map = {
            "pitch": ("pitch_idx", self.pitch_nav_items),
            "pa": ("pa_idx", self.pa_nav_items),
            "inning": ("inning_idx", self.inning_nav_items),
        }
        attr_name, items = nav_map[kind]
        if not items:
            return

        current_idx = getattr(self, attr_name)
        next_idx = self.clamp(current_idx + delta, 0, len(items) - 1)
        setattr(self, attr_name, next_idx)
        self.set_focus_event_index(items[next_idx]["event_idx"])

    def load_selected_game(self):
        if not self.state.conn:
            self.state.set_status("warn", "게임 로드 실패", "먼저 DB 연결을 진행해 주세요.", source="Replay")
            return

        selected_label = dpg.get_value("game_combo")
        match = [game for game in self.state.games if game[1] == selected_label]
        if not match:
            self.state.set_status("warn", "게임 로드 실패", "선택한 게임 정보가 유효하지 않습니다.", source="Replay")
            return

        self.state.game_id = match[0][0]
        self.state.set_status(
            "info",
            f"게임 로드 중... (game_id={self.state.game_id})",
            f"선택 게임 로드를 시작합니다: game_id={self.state.game_id}",
            source="Replay",
            append=False,
        )

        try:
            with self.state.conn.cursor() as cur:
                cur.execute("SELECT player_id, player_name, height, bats_throws_text, hit_type_text FROM players")
                self.player_name_by_id = {}
                self.player_height_by_id = {}
                self.player_batting_side_by_id = {}
                for player_id, player_name, height, bats_throws_text, hit_type_text in cur.fetchall():
                    if not player_id:
                        continue
                    self.player_name_by_id[player_id] = player_name
                    self.player_height_by_id[player_id] = self.safe_int(height)
                    batting_side = self.parse_batting_side(hit_type_text) or self.parse_batting_side(bats_throws_text)
                    if batting_side:
                        self.player_batting_side_by_id[player_id] = batting_side

            self.game_context = self.fetch_game_context(self.state.game_id)
            self.team_name_by_id = {
                self.game_context.get("home_team_id"): self.game_context.get("home_team_name", "HOME"),
                self.game_context.get("away_team_id"): self.game_context.get("away_team_name", "AWAY"),
            }

            roster_rows = self.fetch_roster_entries(self.state.game_id)
            self.build_roster_models(roster_rows)

            self.events = self.fetch_events(self.state.game_id)
            self.state.set_status("info", "게임 로드 중...", f"이벤트 로드 완료: {len(self.events)}건", source="Replay", append=True)

            self.pitches = self.fetch_pitches(self.state.game_id)
            self.pitch_state_by_event = {}
            for pitch in self.pitches:
                event_id = pitch[1]
                if event_id is None:
                    continue
                self.pitch_state_by_event[event_id] = {
                    "balls": self.safe_int(pitch[10]),
                    "strikes": self.safe_int(pitch[11]),
                }
            self.state.set_status("info", "게임 로드 중...", f"투구 로드 완료: {len(self.pitches)}건", source="Replay", append=True)

            self.pas = self.fetch_pas(self.state.game_id)
            self.pa_state_by_id = {}
            self.pa_lookup_by_id = {}
            for pa in self.pas:
                self.pa_state_by_id[pa[0]] = {
                    "outs_before": self.safe_int(pa[6]),
                    "outs_after": self.safe_int(pa[7]),
                    "start_seqno": self.safe_int(pa[12]),
                    "end_seqno": self.safe_int(pa[13]),
                }
                self.pa_lookup_by_id[pa[0]] = {
                    "pa_id": pa[0],
                    "pa_seq_game": pa[1],
                    "inning_no": pa[2],
                    "half": pa[3],
                    "batter_id": pa[4],
                    "pitcher_id": pa[5],
                    "result_text": pa[10] or "-",
                }
            self.state.set_status("info", "게임 로드 중...", f"타석 로드 완료: {len(self.pas)}건", source="Replay", append=True)

            self.innings = self.fetch_innings(self.state.game_id)
            self.state.set_status("info", "게임 로드 중...", f"이닝 로드 완료: {len(self.innings)}건", source="Replay", append=True)

            self.substitutions = self.fetch_substitutions(self.state.game_id)
            self.derived_state_by_event = self.build_derived_state_map()
            self.build_navigation_models()
            self.build_defensive_snapshots()
            self.update_loaded_game_summary()

            self.event_idx = self.pitch_idx = self.pa_idx = self.inning_idx = 0
            if self.events:
                self.set_focus_event_index(0)
            else:
                self.render_event()
            self.refresh_warning_panel()
            self.state.set_status(
                "info",
                f"게임 로드 완료 (game_id={self.state.game_id})",
                "이벤트 이동, 타석 이동, 그래픽 오버레이 초기화를 마쳤습니다.",
                source="Replay",
                append=True,
            )
        except Exception as exc:
            self.state.set_status(
                "error",
                "게임 로드 실패",
                "데이터를 불러오는 중 오류가 발생했습니다.",
                debug_detail=str(exc),
                source="Replay",
                append=False,
            )

    def get_pa_event_columns(self):
        if self.pa_event_columns is not None:
            return self.pa_event_columns

        query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'pa_events'
        """
        with self.state.conn.cursor() as cur:
            cur.execute(query)
            self.pa_event_columns = {row[0] for row in cur.fetchall()}
        return self.pa_event_columns

    def fetch_game_context(self, game_id):
        query = """
        SELECT g.game_id,
               g.game_date,
               g.home_team_id,
               g.away_team_id,
               ht.team_name_short,
               at.team_name_short
        FROM games g
        LEFT JOIN teams ht ON ht.team_id = g.home_team_id
        LEFT JOIN teams at ON at.team_id = g.away_team_id
        WHERE g.game_id = %s
        """
        with self.state.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            row = cur.fetchone()
        if not row:
            return {}
        return {
            "game_id": row[0],
            "game_date": row[1],
            "home_team_id": row[2],
            "away_team_id": row[3],
            "home_team_name": row[4] or "HOME",
            "away_team_name": row[5] or "AWAY",
        }

    def fetch_events(self, game_id):
        columns = self.get_pa_event_columns()
        b1_name_expr = "e.base1_runner_name" if "base1_runner_name" in columns else "NULL"
        b2_name_expr = "e.base2_runner_name" if "base2_runner_name" in columns else "NULL"
        b3_name_expr = "e.base3_runner_name" if "base3_runner_name" in columns else "NULL"
        b1_id_expr = "e.base1_runner_id" if "base1_runner_id" in columns else "NULL"
        b2_id_expr = "e.base2_runner_id" if "base2_runner_id" in columns else "NULL"
        b3_id_expr = "e.base3_runner_id" if "base3_runner_id" in columns else "NULL"

        query = f"""
        SELECT e.event_id, e.event_seq_game, i.inning_no, i.half, e.pa_id, e.event_seq_in_pa,
               e.event_category, e.text, e.outs, e.balls, e.strikes,
               e.base1_occupied, e.base2_occupied, e.base3_occupied,
               e.home_score, e.away_score,
               {b1_name_expr} AS base1_runner_name,
               {b2_name_expr} AS base2_runner_name,
               {b3_name_expr} AS base3_runner_name,
               {b1_id_expr} AS base1_runner_id,
               {b2_id_expr} AS base2_runner_id,
               {b3_id_expr} AS base3_runner_id
        FROM pa_events e
        LEFT JOIN innings i ON i.inning_id = e.inning_id
        WHERE e.game_id = %s
        ORDER BY e.event_seq_game
        """
        with self.state.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            return cur.fetchall()

    def fetch_pitches(self, game_id):
        query = """
        SELECT p.pitch_id, p.event_id, p.pa_id, p.inning_id, p.pitch_num, p.pitch_result, p.pitch_type_text, p.speed_kph,
               p.balls_before, p.strikes_before, p.balls_after, p.strikes_after, p.is_in_play, p.is_terminal_pitch,
               pt.cross_plate_x, pt.cross_plate_y, pt.top_sz, pt.bottom_sz,
               pt.x0, pt.y0, pt.z0, pt.vx0, pt.vy0, pt.vz0, pt.ax, pt.ay, pt.az, pt.stance
        FROM pitches p
        LEFT JOIN pitch_tracking pt ON pt.pitch_id = p.pitch_id
        WHERE p.game_id = %s
        ORDER BY p.inning_id NULLS LAST, p.pa_id NULLS LAST, p.pitch_num NULLS LAST, p.pitch_id
        """
        with self.state.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            return cur.fetchall()

    def fetch_pas(self, game_id):
        query = """
        SELECT pa.pa_id, pa.pa_seq_game, i.inning_no, i.half, pa.batter_id, pa.pitcher_id,
               pa.outs_before, pa.outs_after, pa.balls_final, pa.strikes_final,
               pa.result_text, pa.runs_scored_on_pa, pa.start_seqno, pa.end_seqno
        FROM plate_appearances pa
        LEFT JOIN innings i ON i.inning_id = pa.inning_id
        WHERE pa.game_id = %s
        ORDER BY pa.pa_seq_game
        """
        with self.state.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            return cur.fetchall()

    def fetch_innings(self, game_id):
        query = """
        SELECT inning_id, inning_no, half, batting_team_id, fielding_team_id,
               runs_scored, hits_in_half, errors_in_half, walks_in_half,
               start_event_seqno, end_event_seqno
        FROM innings
        WHERE game_id = %s
        ORDER BY inning_no, CASE WHEN half='top' THEN 0 ELSE 1 END
        """
        with self.state.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            return cur.fetchall()

    def fetch_roster_entries(self, game_id):
        query = """
        SELECT gre.team_id, gre.player_id, p.player_name, gre.roster_group,
               gre.is_starting_pitcher, gre.field_position_code, gre.field_position_name
        FROM game_roster_entries gre
        LEFT JOIN players p ON p.player_id = gre.player_id
        WHERE gre.game_id = %s
        ORDER BY gre.team_id, gre.is_starting_pitcher DESC, gre.roster_group, gre.game_roster_entry_id
        """
        with self.state.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            return cur.fetchall()

    def fetch_substitutions(self, game_id):
        query = """
        SELECT s.sub_event_id,
               s.event_id,
               e.event_seq_game,
               s.team_id,
               COALESCE(s.in_player_name, pin.player_name),
               COALESCE(s.out_player_name, pout.player_name),
               s.in_position,
               s.out_position,
               s.description
        FROM substitution_events s
        LEFT JOIN pa_events e ON e.event_id = s.event_id
        LEFT JOIN players pin ON pin.player_id = s.in_player_id
        LEFT JOIN players pout ON pout.player_id = s.out_player_id
        WHERE s.game_id = %s
        ORDER BY e.event_seq_game, s.sub_event_id
        """
        with self.state.conn.cursor() as cur:
            cur.execute(query, (game_id,))
            return cur.fetchall()

    def build_roster_models(self, roster_rows):
        self.player_team_by_name = {}
        self.starting_defense_by_team = {}
        for team_id, _player_id, player_name, roster_group, is_starting_pitcher, field_position_code, field_position_name in roster_rows:
            if not team_id or not player_name:
                continue
            self.player_team_by_name[player_name] = team_id
            lineup = self.starting_defense_by_team.setdefault(team_id, {})
            position = self.canonical_position(field_position_code) or self.canonical_position(field_position_name)
            if is_starting_pitcher:
                lineup["P"] = player_name
            elif roster_group == "starter" and position and position != "DH":
                lineup[position] = player_name

    def infer_substitution_target(self, sub_row):
        _sub_event_id, _event_id, _event_seq_game, team_id, in_name, out_name, in_position, out_position, description = sub_row
        if team_id:
            return team_id
        for name in (in_name, out_name):
            if name and name in self.player_team_by_name:
                return self.player_team_by_name[name]

        replacement = self.parse_substitution_update(description, in_name, out_name, in_position, out_position)
        if replacement and replacement[1] in self.player_team_by_name:
            return self.player_team_by_name[replacement[1]]
        return None

    def parse_substitution_update(self, description, in_name=None, out_name=None, in_position=None, out_position=None):
        position = self.canonical_position(in_position) or self.canonical_position(out_position)
        if position and in_name and position != "DH":
            return position, in_name

        if not description:
            return None

        change_match = re.search(
            rf"^(?:.+?)\s(?P<name>[^ :]+)\s*:\s*(?P<position>{self.POSITION_PATTERN})\(으\)로 수비위치 변경",
            description,
        )
        if change_match:
            return self.canonical_position(change_match.group("position")), change_match.group("name")

        replace_match = re.search(
            rf"^(?P<old_position>{self.POSITION_PATTERN})\s(?P<old_name>[^ :]+)\s*:\s*(?P<new_position>{self.POSITION_PATTERN})\s(?P<new_name>[^ ]+)\s+\(으\)로 교체",
            description,
        )
        if replace_match:
            return self.canonical_position(replace_match.group("new_position")), replace_match.group("new_name")

        pitcher_match = re.search(r"^투수\s(?P<old_name>[^ :]+)\s*:\s*투수\s(?P<new_name>[^ ]+)\s+\(으\)로 교체", description)
        if pitcher_match:
            return "P", pitcher_match.group("new_name")

        return None

    def build_defensive_snapshots(self):
        current_lineups = {team_id: lineup.copy() for team_id, lineup in self.starting_defense_by_team.items()}
        substitutions_by_event = {}
        for sub in self.substitutions:
            substitutions_by_event.setdefault(sub[1], []).append(sub)

        self.defense_snapshots_by_event = {}
        for event in self.events:
            event_id = event[0]
            for sub in substitutions_by_event.get(event_id, []):
                team_id = self.infer_substitution_target(sub)
                if team_id is None:
                    continue
                lineup = current_lineups.setdefault(team_id, {})
                parsed = self.parse_substitution_update(sub[8], sub[4], sub[5], sub[6], sub[7])
                if not parsed:
                    continue
                position, player_name = parsed
                if not position or position == "DH" or not player_name:
                    continue
                self.clear_player_from_lineup(lineup, player_name)
                lineup[position] = player_name

            self.defense_snapshots_by_event[event_id] = {
                team_id: lineup.copy() for team_id, lineup in current_lineups.items()
            }

    def extract_runner_name_from_text(self, text, base_no):
        if not text:
            return None
        direct = re.search(rf"{base_no}루주자\s*([^ :]+)", text)
        if direct:
            return direct.group(1).strip()
        return None

    def normalize_runner_name(self, name):
        if name is None:
            return None
        text = str(name).strip()
        if text in {"", "-", "주자", "-주자"}:
            return None
        text = re.sub(r"^[123]루주자\s*", "", text).strip()
        if text in {"", "-", "주자"}:
            return None
        return text

    def resolve_runner_name(self, event, base_no, fallback_name=None):
        clean_name = self.normalize_runner_name(fallback_name)
        if clean_name:
            return clean_name
        name_index = {1: 16, 2: 17, 3: 18}.get(base_no)
        id_index = {1: 19, 2: 20, 3: 21}.get(base_no)
        explicit_name = self.normalize_runner_name(event[name_index] if name_index is not None and len(event) > name_index else None)
        if explicit_name:
            return explicit_name
        runner_id = event[id_index] if id_index is not None and len(event) > id_index else None
        if not runner_id:
            return None
        return self.normalize_runner_name(self.player_name_by_id.get(runner_id))

    def find_runner_base(self, runner_names, runner_name):
        for base_no in (1, 2, 3):
            if runner_names.get(base_no) == runner_name:
                return base_no
        return None

    def get_event_runner_hint(self, event, base_no):
        explicit_name = self.normalize_runner_name(event[15 + base_no] if len(event) > 15 + base_no else None)
        runner_id = event[18 + base_no] if len(event) > 18 + base_no else None
        id_name = self.normalize_runner_name(self.player_name_by_id.get(runner_id)) if runner_id else None
        if explicit_name and id_name and explicit_name != id_name:
            return explicit_name
        return explicit_name or id_name

    def infer_batter_target_base(self, text):
        if not text:
            return None
        if "홈런" in text:
            return 4
        if "3루타" in text:
            return 3
        if "2루타" in text:
            return 2
        if any(keyword in text for keyword in ["1루타", "볼넷", "고의4구", "자동 고의4구", "몸에 맞는 볼", "실책으로 출루", "출루"]):
            return 1
        return None

    def parse_runner_movements(self, text):
        if not text:
            return []
        moves = []
        advance_pattern = re.compile(r"(?P<src>[123])루주자\s*(?P<name>[^ :]+)\s*:\s*(?P<dst>[123])루(?:까지)?\s*진루")
        home_pattern = re.compile(r"(?P<src>[123])루주자\s*(?P<name>[^ :]+)\s*:\s*홈인")
        out_pattern = re.compile(r"(?P<src>[123])루주자\s*(?P<name>[^ :]+)\s*:\s*아웃")

        for match in advance_pattern.finditer(text):
            moves.append({"src": int(match.group("src")), "name": match.group("name"), "dst": int(match.group("dst"))})
        for match in home_pattern.finditer(text):
            moves.append({"src": int(match.group("src")), "name": match.group("name"), "dst": "home"})
        for match in out_pattern.finditer(text):
            moves.append({"src": int(match.group("src")), "name": match.group("name"), "dst": "out"})
        return moves

    def apply_runner_movements(self, runner_names, text):
        for move in self.parse_runner_movements(text):
            runner_name = self.normalize_runner_name(move["name"])
            if not runner_name:
                continue
            current_base = self.find_runner_base(runner_names, runner_name)
            if move["dst"] in {1, 2, 3}:
                if current_base is not None and current_base != move["dst"]:
                    runner_names[current_base] = None
                runner_names[move["dst"]] = runner_name
            elif current_base is not None:
                runner_names[current_base] = None

    def assign_remaining_runners(self, previous_names, runner_names, occupied):
        assigned = {name for name in runner_names.values() if name}
        remaining_previous = []
        for prev_base in (3, 2, 1):
            runner_name = previous_names.get(prev_base)
            if runner_name and runner_name not in assigned:
                remaining_previous.append((prev_base, runner_name))

        for base_no in (1, 2, 3):
            if not occupied[base_no] or runner_names.get(base_no):
                continue
            same_base_name = previous_names.get(base_no)
            if same_base_name and same_base_name not in assigned:
                runner_names[base_no] = same_base_name
                assigned.add(same_base_name)

        available_bases = [base_no for base_no in (3, 2, 1) if occupied[base_no] and not runner_names.get(base_no)]
        for prev_base, runner_name in remaining_previous:
            if runner_name in assigned:
                continue
            higher_or_same = [base_no for base_no in available_bases if base_no >= prev_base]
            target_base = higher_or_same[0] if higher_or_same else (available_bases[0] if available_bases else None)
            if target_base is None:
                continue
            runner_names[target_base] = runner_name
            assigned.add(runner_name)
            available_bases.remove(target_base)

    def reconcile_runner_names(self, previous_names, event):
        text = (event[7] or "").strip()
        occupied = {
            1: bool(event[11]) if len(event) > 11 and event[11] is not None else False,
            2: bool(event[12]) if len(event) > 12 and event[12] is not None else False,
            3: bool(event[13]) if len(event) > 13 and event[13] is not None else False,
        }
        runner_names = previous_names.copy()

        for base_no in (1, 2, 3):
            if not occupied[base_no]:
                runner_names[base_no] = None

        self.apply_runner_movements(runner_names, text)

        pa_info = self.pa_lookup_by_id.get(event[4], {})
        batter_name = self.get_player_name(pa_info.get("batter_id")) if pa_info.get("batter_id") else self.infer_batter_name_from_text(text)
        batter_target = self.infer_batter_target_base(text)
        if batter_name and batter_target in {1, 2, 3}:
            existing_name = runner_names.get(batter_target)
            if existing_name and existing_name != batter_name:
                runner_names[batter_target] = batter_name
            else:
                runner_names[batter_target] = batter_name

        for base_no in (1, 2, 3):
            explicit_name = self.get_event_runner_hint(event, base_no)
            if occupied[base_no] and explicit_name:
                runner_names[base_no] = explicit_name

        self.assign_remaining_runners(previous_names, runner_names, occupied)

        for base_no in (1, 2, 3):
            if not occupied[base_no]:
                runner_names[base_no] = None

        return runner_names

    def build_derived_state_map(self):
        derived = {}
        balls, strikes, outs = 0, 0, 0
        runner_names = {1: None, 2: None, 3: None}
        for event in self.events:
            event_id = event[0]
            text = (event[7] or "").strip()
            occupied = {
                1: bool(event[11]) if len(event) > 11 and event[11] is not None else False,
                2: bool(event[12]) if len(event) > 12 and event[12] is not None else False,
                3: bool(event[13]) if len(event) > 13 and event[13] is not None else False,
            }

            if "번타자" in text:
                balls, strikes = 0, 0
            if re.search(r"\d+구\s*볼", text) and "볼넷" not in text and "몸에 맞는 볼" not in text:
                balls = min(4, balls + 1)
            if "스트라이크" in text and "자동 고의4구" not in text:
                strikes = min(3, strikes + 1)
            if "헛스윙" in text and strikes < 2:
                strikes += 1
            if "파울" in text and strikes < 2:
                strikes += 1
            if any(keyword in text for keyword in ["볼넷", "고의4구", "몸에 맞는 볼"]):
                balls, strikes = 0, 0
            if "아웃" in text:
                outs = min(3, outs + 1)
                balls, strikes = 0, 0
            if "공수교대" in text or "이닝 종료" in text:
                outs, balls, strikes = 0, 0, 0
                runner_names = {1: None, 2: None, 3: None}

            runner_names = self.reconcile_runner_names(runner_names, event)

            derived[event_id] = {
                "outs": outs,
                "balls": balls,
                "strikes": strikes,
                "b1_occ": occupied[1],
                "b2_occ": occupied[2],
                "b3_occ": occupied[3],
                "b1_name": runner_names[1],
                "b2_name": runner_names[2],
                "b3_name": runner_names[3],
            }
        return derived

    def get_count_display(self, event, state):
        text = (event[7] or "").strip()
        status_label = None
        if "삼진" in text:
            status_label = "삼진"
        elif "몸에 맞는 볼" in text:
            status_label = "사구"
        elif any(keyword in text for keyword in ["볼넷", "고의4구", "자동 고의4구"]):
            status_label = "볼넷"

        return {
            "balls": min(max(state["balls"], 0), 3),
            "strikes": min(max(state["strikes"], 0), 2),
            "outs": max(state["outs"], 0),
            "status_label": status_label,
        }

    def get_resolved_game_state(self, event_idx):
        event = self.events[event_idx]
        derived = self.derived_state_by_event.get(event[0], {})

        balls = self.safe_int(event[9])
        strikes = self.safe_int(event[10])
        outs = self.safe_int(event[8])
        home_score = self.safe_int(event[14])
        away_score = self.safe_int(event[15])

        state = {
            "outs": outs if outs is not None else derived.get("outs", 0),
            "balls": balls if balls is not None else derived.get("balls", 0),
            "strikes": strikes if strikes is not None else derived.get("strikes", 0),
            "home_score": home_score if home_score is not None else 0,
            "away_score": away_score if away_score is not None else 0,
            "b1_occ": bool(event[11]) if len(event) > 11 and event[11] is not None else derived.get("b1_occ", False),
            "b2_occ": bool(event[12]) if len(event) > 12 and event[12] is not None else derived.get("b2_occ", False),
            "b3_occ": bool(event[13]) if len(event) > 13 and event[13] is not None else derived.get("b3_occ", False),
            "b1_name": self.resolve_runner_name(event, 1, derived.get("b1_name")),
            "b2_name": self.resolve_runner_name(event, 2, derived.get("b2_name")),
            "b3_name": self.resolve_runner_name(event, 3, derived.get("b3_name")),
        }
        state["count_display"] = self.get_count_display(event, state)
        return state

    def detect_anomalies(self):
        issues = []
        prev_ball = prev_strike = prev_home = prev_away = None
        prev_pa = None
        for event in self.events:
            event_id, seq, _, _, pa_id, _, _, _, _, balls, strikes, *_rest, home_score, away_score = event[:16]
            balls_i = self.safe_int(balls)
            strikes_i = self.safe_int(strikes)
            home_i = self.safe_int(home_score)
            away_i = self.safe_int(away_score)

            if home_i is None or away_i is None:
                issues.append((event_id, "점수 누락", f"event_seq={seq}, home/away score NULL"))
            if prev_pa is not None and pa_id != prev_pa:
                prev_ball = prev_strike = None
            if prev_ball is not None and balls_i is not None and balls_i < prev_ball:
                issues.append((event_id, "카운트 역행", f"볼 카운트 감소: {prev_ball} -> {balls_i} (seq={seq})"))
            if prev_strike is not None and strikes_i is not None and strikes_i < prev_strike:
                issues.append((event_id, "카운트 역행", f"스트라이크 카운트 감소: {prev_strike} -> {strikes_i} (seq={seq})"))
            if prev_home is not None and home_i is not None and home_i < prev_home:
                issues.append((event_id, "점수 역행", f"HOME 점수 감소: {prev_home} -> {home_i} (seq={seq})"))
            if prev_away is not None and away_i is not None and away_i < prev_away:
                issues.append((event_id, "점수 역행", f"AWAY 점수 감소: {prev_away} -> {away_i} (seq={seq})"))

            prev_pa = pa_id
            prev_ball = balls_i if balls_i is not None else prev_ball
            prev_strike = strikes_i if strikes_i is not None else prev_strike
            prev_home = home_i if home_i is not None else prev_home
            prev_away = away_i if away_i is not None else prev_away
        return issues

    def refresh_warning_panel(self):
        if not dpg.does_item_exist("warning_table"):
            return
        dpg.delete_item("warning_table", children_only=True)
        issues = self.detect_anomalies()
        with dpg.table_row(parent="warning_table"):
            dpg.add_text("event_id")
            dpg.add_text("유형")
            dpg.add_text("상세")
        for event_id, issue_type, detail in issues[:500]:
            with dpg.table_row(parent="warning_table"):
                dpg.add_text(str(event_id))
                dpg.add_text(issue_type, color=(255, 90, 90))
                dpg.add_text(detail)
        self.set_text_value_if_exists("warning_count_text", f"자동 경고: {len(issues)}건")
        if dpg.does_item_exist("warning_count_text"):
            dpg.configure_item("warning_count_text", color=(255, 100, 100) if issues else (120, 220, 140))
        if issues:
            event_id, issue_type, detail = issues[0]
            self.set_text_value_if_exists("warning_hint_text", f"대표 경고: event_id={event_id} | {issue_type}\n{detail}")
        else:
            self.set_text_value_if_exists("warning_hint_text", "자동 검증 기준에서 즉시 확인할 이상치는 발견되지 않았습니다.")

    def render_event(self):
        if not self.events:
            self.set_text_value_if_exists("current_event_summary_text", "이벤트, 투구, 타석, 이닝 데이터가 없습니다.")
            self.set_text_value_if_exists("relay_text", "게임을 먼저 로드해 주세요.")
            self.set_text_value_if_exists("event_detail_text", "검증 상세 정보가 여기에 표시됩니다.")
            self.update_navigation_panel()
            self.draw_overlay_background()
            return

        event = self.events[self.event_idx]
        state = self.get_resolved_game_state(self.event_idx)
        pitch_item = self.current_pitch_item()
        self.update_navigation_panel()
        self.update_current_focus_summary(event, state)
        self.refresh_pitch_table(highlight_event_id=pitch_item["event_id"] if pitch_item else event[0])
        self.update_field_overlay(event, state)
        self.render_strike_zone_panel()

    def scale_px(self, value):
        return value * min(self.canvas_w / 1100.0, self.canvas_h / 420.0)

    def to_canvas(self, nx, ny):
        return nx * self.canvas_w, ny * self.canvas_h

    def chip_size(self, text, font_size):
        font_px = max(12, int(self.scale_px(font_size)))
        width = max(int(self.scale_px(56)), int(len(text) * font_px * 0.56) + int(self.scale_px(20)))
        height = int(font_px * 1.55)
        return width, height, font_px

    def draw_centered_chip(self, text, center_norm, *, fill, outline=(255, 255, 255, 28), font_size=14, text_color=(255, 255, 255, 255)):
        if not text:
            return
        center_x, center_y = self.to_canvas(*center_norm)
        width, height, font_px = self.chip_size(text, font_size)
        x0 = center_x - width / 2
        y0 = center_y - height / 2
        dpg.draw_rectangle((x0, y0), (x0 + width, y0 + height), color=outline, fill=fill, rounding=self.scale_px(10), parent="stadium_overlay_drawlist")
        dpg.draw_text((x0 + self.scale_px(10), y0 + self.scale_px(4)), text, color=text_color, size=font_px, parent="stadium_overlay_drawlist")

    def draw_left_chip(self, text, origin_norm, *, fill, outline=(255, 255, 255, 28), font_size=14, text_color=(255, 255, 255, 255)):
        if not text:
            return
        x0, y0 = self.to_canvas(*origin_norm)
        width, height, font_px = self.chip_size(text, font_size)
        dpg.draw_rectangle((x0, y0), (x0 + width, y0 + height), color=outline, fill=fill, rounding=self.scale_px(10), parent="stadium_overlay_drawlist")
        dpg.draw_text((x0 + self.scale_px(10), y0 + self.scale_px(4)), text, color=text_color, size=font_px, parent="stadium_overlay_drawlist")

    def draw_diamond(self, center_norm, radius_px, *, fill, outline=(255, 255, 255, 60)):
        cx, cy = self.to_canvas(*center_norm)
        radius = self.scale_px(radius_px)
        points = [
            (cx, cy - radius),
            (cx + radius, cy),
            (cx, cy + radius),
            (cx - radius, cy),
        ]
        dpg.draw_polygon(points, color=outline, fill=fill, parent="stadium_overlay_drawlist")

    def draw_overlay_background(self):
        if not dpg.does_item_exist("stadium_overlay_drawlist"):
            return
        dpg.delete_item("stadium_overlay_drawlist", children_only=True)

        dpg.draw_rectangle((0, 0), (self.canvas_w, self.canvas_h), fill=(38, 41, 43), color=(68, 72, 74), parent="stadium_overlay_drawlist")

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
        dpg.draw_polygon(field_boundary, color=(116, 164, 118, 180), fill=(62, 134, 72, 255), parent="stadium_overlay_drawlist")

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
        dpg.draw_polygon(infield_dirt, color=(177, 130, 82, 180), fill=(165, 110, 72, 255), parent="stadium_overlay_drawlist")

        dpg.draw_polygon([home, third, second, first], color=(164, 198, 102, 60), fill=(146, 206, 84, 255), parent="stadium_overlay_drawlist")

        dpg.draw_line(home, self.to_canvas(*left_foul_norm), color=(246, 240, 230, 255), thickness=self.scale_px(2), parent="stadium_overlay_drawlist")
        dpg.draw_line(home, self.to_canvas(*right_foul_norm), color=(246, 240, 230, 255), thickness=self.scale_px(2), parent="stadium_overlay_drawlist")
        dpg.draw_line(home, third, color=(233, 205, 172, 170), thickness=self.scale_px(2), parent="stadium_overlay_drawlist")
        dpg.draw_line(third, second, color=(233, 205, 172, 170), thickness=self.scale_px(2), parent="stadium_overlay_drawlist")
        dpg.draw_line(second, first, color=(233, 205, 172, 170), thickness=self.scale_px(2), parent="stadium_overlay_drawlist")
        dpg.draw_line(first, home, color=(233, 205, 172, 170), thickness=self.scale_px(2), parent="stadium_overlay_drawlist")

        dpg.draw_circle(self.to_canvas(0.50, 0.61), self.scale_px(26), color=(120, 74, 48, 210), fill=(120, 74, 48, 210), parent="stadium_overlay_drawlist")
        dpg.draw_circle(self.to_canvas(0.50, 0.61), self.scale_px(9), color=(255, 255, 255, 160), fill=(255, 255, 255, 160), parent="stadium_overlay_drawlist")

        plate_radius = self.scale_px(12)
        plate_x, plate_y = home
        plate_points = [
            (plate_x - plate_radius, plate_y),
            (plate_x + plate_radius, plate_y),
            (plate_x + plate_radius, plate_y + plate_radius * 0.8),
            (plate_x, plate_y + plate_radius * 1.5),
            (plate_x - plate_radius, plate_y + plate_radius * 0.8),
        ]
        dpg.draw_polygon(plate_points, color=(255, 255, 255, 220), fill=(255, 255, 255, 220), parent="stadium_overlay_drawlist")

        for base_norm in self.BASE_POSITIONS.values():
            self.draw_diamond(base_norm, 10, fill=(252, 244, 232, 230))

    def draw_score_bug(self, event, state, participants):
        box_x0, box_y0 = self.to_canvas(0.02, 0.04)
        box_x1, box_y1 = self.to_canvas(0.17, 0.60)
        dpg.draw_rectangle((box_x0, box_y0), (box_x1, box_y1), color=(255, 255, 255, 30), fill=(17, 51, 34, 220), rounding=self.scale_px(8), parent="stadium_overlay_drawlist")

        row_h = self.scale_px(34)
        dpg.draw_rectangle((box_x0, box_y0), (box_x1, box_y0 + row_h), color=(0, 0, 0, 0), fill=(234, 129, 51, 240), parent="stadium_overlay_drawlist")
        dpg.draw_rectangle((box_x0, box_y0 + row_h), (box_x1, box_y0 + row_h * 2), color=(0, 0, 0, 0), fill=(41, 55, 93, 240), parent="stadium_overlay_drawlist")

        big_font = max(13, int(self.scale_px(16)))
        small_font = max(11, int(self.scale_px(12)))
        away_name = self.game_context.get("away_team_name", "AWAY")
        home_name = self.game_context.get("home_team_name", "HOME")
        dpg.draw_text((box_x0 + self.scale_px(10), box_y0 + self.scale_px(6)), f"{away_name} {state['away_score']}", color=(255, 255, 255, 255), size=big_font, parent="stadium_overlay_drawlist")
        dpg.draw_text((box_x0 + self.scale_px(10), box_y0 + self.scale_px(40)), f"{home_name} {state['home_score']}", color=(255, 255, 255, 255), size=big_font, parent="stadium_overlay_drawlist")

        dpg.draw_text((box_x0 + self.scale_px(12), box_y0 + self.scale_px(82)), self.format_inning_label(event[2], event[3]), color=(255, 255, 255, 255), size=small_font, parent="stadium_overlay_drawlist")
        dpg.draw_text((box_x0 + self.scale_px(12), box_y0 + self.scale_px(102)), f"이벤트 {self.event_idx + 1}/{len(self.events)}", color=(204, 222, 212, 255), size=small_font, parent="stadium_overlay_drawlist")

        count_display = state.get("count_display") or self.get_count_display(event, state)
        count_specs = [
            ("B", count_display["balls"], 3, (86, 194, 117, 255)),
            ("S", count_display["strikes"], 2, (247, 203, 67, 255)),
            ("O", min(count_display["outs"], 2), 2, (238, 93, 93, 255)),
        ]
        for row_idx, (label, active_count, max_lights, fill_color) in enumerate(count_specs):
            y = box_y0 + self.scale_px(142 + row_idx * 24)
            dpg.draw_text((box_x0 + self.scale_px(10), y - self.scale_px(7)), label, color=(235, 235, 235, 255), size=small_font, parent="stadium_overlay_drawlist")
            for light_idx in range(max_lights):
                cx = box_x0 + self.scale_px(34 + light_idx * 18)
                fill = fill_color if light_idx < active_count else (84, 110, 92, 180)
                dpg.draw_circle((cx, y), self.scale_px(5), color=(255, 255, 255, 22), fill=fill, parent="stadium_overlay_drawlist")

        if count_display["status_label"]:
            self.draw_left_chip(count_display["status_label"], (0.024, 0.405), fill=(77, 58, 28, 236), font_size=12)

        for base_no, origin in {1: (0.145, 0.295), 2: (0.128, 0.258), 3: (0.111, 0.295)}.items():
            fill = (255, 204, 82, 255) if state.get(f"b{base_no}_occ") else (90, 110, 98, 180)
            self.draw_diamond(origin, 7, fill=fill)

        self.draw_left_chip(f"투수 {participants['pitcher_name']}", (0.024, 0.47), fill=(23, 62, 44, 230), font_size=13)
        self.draw_left_chip(f"타자 {participants['batter_name']}", (0.024, 0.535), fill=(86, 68, 38, 236), font_size=13)

    def draw_player_overlay(self, participants, state):
        lineup = participants["lineup"] or {}
        for position in self.DEFENSE_ORDER:
            player_name = lineup.get(position)
            if not player_name:
                continue
            self.draw_centered_chip(player_name, self.DEFENSE_POSITIONS[position], fill=(23, 57, 43, 226), font_size=13)

        batter_name = participants["batter_name"]
        if batter_name and batter_name != "-":
            batter_side = participants.get("batter_side")
            if batter_side == "L":
                batter_pos = (0.60, 0.89)
                batter_label = f"타자 {batter_name}"
            elif batter_side == "R":
                batter_pos = (0.40, 0.89)
                batter_label = f"타자 {batter_name}"
            else:
                batter_pos = (0.50, 0.90)
                batter_label = f"타자 {batter_name}"
            self.draw_centered_chip(batter_label, batter_pos, fill=(96, 72, 37, 236), font_size=13)

        for base_no in (1, 2, 3):
            if not state.get(f"b{base_no}_occ"):
                continue
            runner_name = state.get(f"b{base_no}_name") or f"{base_no}루 주자"
            self.draw_centered_chip(runner_name, self.RUNNER_LABEL_POSITIONS[base_no], fill=(149, 118, 43, 236), font_size=12)

    def update_field_overlay(self, event, state=None):
        if not dpg.does_item_exist("stadium_overlay_drawlist"):
            return
        self.draw_overlay_background()
        if state is None:
            state = self.get_resolved_game_state(self.event_idx)

        participants = self.get_event_participants(event)
        self.draw_score_bug(event, state, participants)
        self.draw_player_overlay(participants, state)

        header_text = (
            f"{self.format_inning_label(event[2], event[3])} | "
            f"투구 {self.pitch_idx + 1 if self.pitch_nav_items else 0}/{len(self.pitch_nav_items)} | "
            f"타석 {self.pa_idx + 1 if self.pa_nav_items else 0}/{len(self.pa_nav_items)}"
        )
        self.draw_left_chip(header_text, (0.22, 0.04), fill=(28, 33, 35, 220), font_size=14)

    def refresh_pitch_table(self, highlight_event_id=None):
        if not dpg.does_item_exist("pitch_table"):
            return
        dpg.delete_item("pitch_table", children_only=True)
        with dpg.table_row(parent="pitch_table"):
            for column in ["pitch_id", "event_id", "pa_id", "num", "result", "type", "speed", "count(before->after)"]:
                dpg.add_text(column)
        for pitch in self.pitches[:1000]:
            pitch_id, event_id, pa_id, _inning_id, pitch_num, pitch_result, pitch_type_text, speed_kph, balls_before, strikes_before, balls_after, strikes_after, *_ = pitch
            color = (255, 220, 50) if highlight_event_id is not None and event_id == highlight_event_id else (230, 230, 230)
            with dpg.table_row(parent="pitch_table"):
                dpg.add_text(str(pitch_id), color=color)
                dpg.add_text(str(event_id), color=color)
                dpg.add_text(str(pa_id), color=color)
                dpg.add_text(str(pitch_num), color=color)
                dpg.add_text(str(pitch_result), color=color)
                dpg.add_text(str(pitch_type_text), color=color)
                dpg.add_text(str(speed_kph), color=color)
                dpg.add_text(f"{balls_before}-{strikes_before} -> {balls_after}-{strikes_after}", color=color)

    def render_stage_count_panel(self):
        if not dpg.does_item_exist("stage_count_drawlist"):
            return
        dpg.delete_item("stage_count_drawlist", children_only=True)

        width = self.stage_count_w
        height = self.stage_count_h
        dpg.draw_rectangle((0, 0), (width, height), color=(65, 84, 92), fill=(25, 46, 56), rounding=6, parent="stage_count_drawlist")

        if not self.events:
            dpg.draw_text((12, 10), "B", color=(235, 235, 235), size=13, parent="stage_count_drawlist")
            return

        state = self.get_resolved_game_state(self.event_idx)
        event = self.events[self.event_idx]
        count_display = state.get("count_display") or self.get_count_display(event, state)
        count_specs = [
            ("B", count_display["balls"], 3, (86, 194, 117, 255)),
            ("S", count_display["strikes"], 2, (247, 203, 67, 255)),
            ("O", min(count_display["outs"], 2), 2, (238, 93, 93, 255)),
        ]
        row_y = [18, 38, 58]
        for idx, (label, active_count, total_lights, fill_color) in enumerate(count_specs):
            y = row_y[idx]
            dpg.draw_text((10, y - 7), label, color=(235, 235, 235), size=13, parent="stage_count_drawlist")
            for light_idx in range(total_lights):
                cx = 28 + light_idx * 16
                fill = fill_color if light_idx < active_count else (76, 95, 101, 180)
                dpg.draw_circle((cx, y), 4.5, color=(255, 255, 255, 24), fill=fill, parent="stage_count_drawlist")

    def render_strike_zone_panel(self):
        if not dpg.does_item_exist("strike_zone_drawlist"):
            return
        dpg.delete_item("strike_zone_drawlist", children_only=True)

        width = self.strike_zone_w
        height = self.strike_zone_h
        dpg.draw_rectangle((0, 0), (width, height), fill=(31, 38, 42), color=(74, 88, 96), rounding=8, parent="strike_zone_drawlist")

        pitch_context = self.current_pitch_tracking()
        if not pitch_context:
            dpg.draw_text((18, 18), "스트라이크존\n데이터 없음", color=(220, 220, 220), size=16, parent="strike_zone_drawlist")
            return

        zone_left = 46
        zone_right = width - 46
        zone_top_px = 34
        zone_bottom_px = height - 46
        dpg.draw_rectangle((zone_left, zone_top_px), (zone_right, zone_bottom_px), color=(114, 135, 144), fill=(24, 34, 40), parent="strike_zone_drawlist")

        top_ft = pitch_context["zone_top"]
        bottom_ft = pitch_context["zone_bottom"]
        half_width_ft = pitch_context["zone_half_width"]
        plate_x = pitch_context["plate_x"]
        plate_z = pitch_context["plate_z"]
        if top_ft is None or bottom_ft is None or half_width_ft is None:
            dpg.draw_text((18, 18), "존 계산 정보 부족", color=(220, 220, 220), size=16, parent="strike_zone_drawlist")
            return

        zone_height_ft = max(0.1, top_ft - bottom_ft)
        x_range = max(0.95, half_width_ft * 1.7)
        z_pad = max(0.55, zone_height_ft * 0.32)
        z_min = max(0.5, bottom_ft - z_pad)
        z_max = max(top_ft + z_pad, bottom_ft + 1.0)

        def scale_x(value):
            return zone_left + ((value + x_range) / (x_range * 2)) * (zone_right - zone_left)

        def scale_z(value):
            return zone_bottom_px - ((value - z_min) / (z_max - z_min)) * (zone_bottom_px - zone_top_px)

        strike_left = scale_x(-half_width_ft)
        strike_right = scale_x(half_width_ft)
        strike_top = scale_z(top_ft)
        strike_bottom = scale_z(bottom_ft)
        dpg.draw_rectangle(
            (strike_left, strike_top),
            (strike_right, strike_bottom),
            color=(241, 236, 212),
            fill=(42, 80, 106, 120),
            thickness=2,
            parent="strike_zone_drawlist",
        )

        third_w = (strike_right - strike_left) / 3.0
        third_h = (strike_bottom - strike_top) / 3.0
        for idx in range(1, 3):
            dpg.draw_line((strike_left + third_w * idx, strike_top), (strike_left + third_w * idx, strike_bottom), color=(255, 255, 255, 40), parent="strike_zone_drawlist")
            dpg.draw_line((strike_left, strike_top + third_h * idx), (strike_right, strike_top + third_h * idx), color=(255, 255, 255, 40), parent="strike_zone_drawlist")

        is_in_zone = (
            plate_x is not None
            and plate_z is not None
            and abs(plate_x) <= half_width_ft
            and bottom_ft <= plate_z <= top_ft
        )
        if plate_x is not None and plate_z is not None:
            px = scale_x(max(-x_range, min(x_range, plate_x)))
            py = scale_z(max(z_min, min(z_max, plate_z)))
            pitch_color = (253, 223, 82) if is_in_zone else (255, 121, 76)
            dpg.draw_circle((px, py), 7, color=(18, 22, 24), fill=pitch_color, thickness=2, parent="strike_zone_drawlist")

        dpg.draw_text((14, 10), "스트라이크존", color=(238, 238, 238), size=15, parent="strike_zone_drawlist")
        stance_label = {"L": "좌타", "R": "우타", "S": "양타"}.get(pitch_context.get("stance"), "타석 정보 없음")
        meta_text = f"규정 {pitch_context['rule_year']} | {stance_label}"
        dpg.draw_text((14, height - 28), meta_text, color=(194, 206, 214), size=13, parent="strike_zone_drawlist")
        if dpg.does_item_exist("strike_zone_meta_text"):
            dpg.set_value("strike_zone_meta_text", meta_text)

    def apply_responsive_layout(self):
        if not dpg.does_item_exist("replay_control_panel"):
            return

        content_w, content_h = self.get_available_content_size()
        layout = self.compute_layout_metrics(content_w, content_h)

        dpg.configure_item("replay_control_panel", width=layout["content_w"], height=self.CONTROL_PANEL_HEIGHT)
        dpg.configure_item("game_combo", width=max(260, layout["content_w"] - 260))
        dpg.configure_item("replay_stage_panel", width=layout["content_w"], height=layout["stage_h"])
        dpg.configure_item("replay_stage_left_column", width=layout["side_w"], height=-1)
        dpg.configure_item("replay_stage_center_panel", width=layout["canvas_w"], height=-1)
        dpg.configure_item("replay_stage_right_column", width=layout["side_w"], height=-1)
        dpg.configure_item("focus_nav_event_panel", width=layout["side_w"], height=layout["left_event_h"])
        dpg.configure_item("focus_nav_pa_panel", width=layout["side_w"], height=layout["left_pa_h"])
        dpg.configure_item("focus_nav_inning_panel", width=layout["side_w"], height=-1)
        dpg.configure_item("focus_nav_pitch_panel", width=layout["side_w"], height=layout["right_pitch_h"])
        dpg.configure_item("strike_zone_panel", width=layout["side_w"], height=-1)
        dpg.configure_item("event_nav_body", width=max(140, layout["side_w"] - 18), height=layout["event_body_h"])
        dpg.configure_item("inning_nav_body", width=max(140, layout["side_w"] - 18), height=layout["inning_body_h"])
        dpg.configure_item("pitch_nav_body", width=max(140, layout["side_w"] - 18), height=layout["pitch_body_h"])
        dpg.configure_item("pa_nav_body", width=max(140, layout["side_w"] - 18), height=layout["pa_body_h"])
        dpg.configure_item("event_nav_text", wrap=max(140, layout["side_w"] - 22))
        dpg.configure_item("inning_nav_text", wrap=max(140, layout["side_w"] - 22))
        dpg.configure_item("pitch_nav_text", wrap=max(140, layout["side_w"] - 22))
        dpg.configure_item("pa_nav_text", wrap=max(140, layout["side_w"] - 22))
        dpg.configure_item("strike_zone_meta_text", wrap=max(140, layout["side_w"] - 22))
        nav_button_w = max(76, min(92, int((layout["side_w"] - 30) / 2)))
        for tag in (
            "event_prev_button",
            "event_next_button",
            "inning_prev_button",
            "inning_next_button",
            "pitch_prev_button",
            "pitch_next_button",
            "pa_prev_button",
            "pa_next_button",
        ):
            dpg.configure_item(tag, width=nav_button_w, height=self.NAV_BUTTON_HEIGHT)

        dpg.configure_item("replay_bottom_info_group", horizontal=True)
        dpg.configure_item("replay_inspector_panel", width=layout["content_w"], height=layout["bottom_h"])
        dpg.configure_item("event_detail_text", height=self.DETAIL_TEXT_HEIGHT)
        dpg.configure_item("warning_hint_text", wrap=max(220, layout["content_w"] - 20))
        dpg.configure_item("warning_table", height=layout["warning_table_h"])

        canvas_changed = (self.canvas_w, self.canvas_h) != (layout["canvas_w"], layout["canvas_h"])
        self.canvas_w = layout["canvas_w"]
        self.canvas_h = layout["canvas_h"]
        self.strike_zone_w = max(160, layout["side_w"] - 24)
        self.strike_zone_h = max(96, layout["strike_h"] - 44)
        dpg.configure_item("stadium_overlay_drawlist", width=self.canvas_w, height=self.canvas_h)
        dpg.configure_item("strike_zone_drawlist", width=self.strike_zone_w, height=self.strike_zone_h)
        if canvas_changed:
            if self.events:
                self.update_field_overlay(self.events[self.event_idx], self.get_resolved_game_state(self.event_idx))
            else:
                self.draw_overlay_background()
        self.render_strike_zone_panel()

    def build(self, parent):
        with dpg.tab(label="Replay / 검증", parent=parent):
            with dpg.child_window(tag="replay_control_panel", border=True, width=-1, height=self.CONTROL_PANEL_HEIGHT, no_scrollbar=True):
                with dpg.group(horizontal=True):
                    dpg.add_text("게임")
                    dpg.add_combo(tag="game_combo", items=[], width=760)
                    dpg.add_button(label="로드", width=72, callback=lambda: self.load_selected_game())
                    dpg.add_button(label="경고 재검사", width=92, callback=lambda: self.refresh_warning_panel())

            dpg.add_spacer(height=self.PANEL_GAP)
            with dpg.child_window(tag="replay_stage_panel", width=-1, height=400, border=True, no_scrollbar=True):
                with dpg.group(horizontal=True, tag="replay_stage_layout_group"):
                    with dpg.child_window(tag="replay_stage_left_column", width=220, height=-1, border=False, no_scrollbar=True):
                        with dpg.child_window(tag="focus_nav_event_panel", width=220, height=92, border=True, no_scrollbar=True):
                            with dpg.child_window(tag="event_nav_body", width=-1, height=48, border=False, no_scrollbar=True):
                                dpg.add_text("이벤트 데이터 없음", tag="event_nav_text", wrap=188)
                            dpg.add_spacer(height=4)
                            with dpg.group(horizontal=True):
                                dpg.add_button(tag="event_prev_button", label="이전", width=72, callback=lambda: self.move_focus("event", -1))
                                dpg.add_button(tag="event_next_button", label="다음", width=72, callback=lambda: self.move_focus("event", +1))
                        dpg.add_spacer(height=self.PANEL_GAP)
                        with dpg.child_window(tag="focus_nav_pa_panel", width=220, height=96, border=True, no_scrollbar=True):
                            with dpg.child_window(tag="pa_nav_body", width=-1, height=52, border=False, no_scrollbar=True):
                                dpg.add_text("타석 데이터 없음", tag="pa_nav_text", wrap=188)
                            dpg.add_spacer(height=4)
                            with dpg.group(horizontal=True):
                                dpg.add_button(tag="pa_prev_button", label="이전", width=72, callback=lambda: self.move_focus("pa", -1))
                                dpg.add_button(tag="pa_next_button", label="다음", width=72, callback=lambda: self.move_focus("pa", +1))
                        dpg.add_spacer(height=self.PANEL_GAP)
                        with dpg.child_window(tag="focus_nav_inning_panel", width=220, height=-1, border=True, no_scrollbar=True):
                            with dpg.child_window(tag="inning_nav_body", width=-1, height=40, border=False, no_scrollbar=True):
                                dpg.add_text("이닝 데이터 없음", tag="inning_nav_text", wrap=188)
                            dpg.add_spacer(height=4)
                            with dpg.group(horizontal=True):
                                dpg.add_button(tag="inning_prev_button", label="이전", width=72, callback=lambda: self.move_focus("inning", -1))
                                dpg.add_button(tag="inning_next_button", label="다음", width=72, callback=lambda: self.move_focus("inning", +1))

                    with dpg.child_window(tag="replay_stage_center_panel", width=640, height=-1, border=False, no_scrollbar=True):
                        dpg.add_drawlist(tag="stadium_overlay_drawlist", width=self.canvas_w, height=self.canvas_h)

                    with dpg.child_window(tag="replay_stage_right_column", width=220, height=-1, border=False, no_scrollbar=True):
                        with dpg.child_window(tag="focus_nav_pitch_panel", width=220, height=84, border=True, no_scrollbar=True):
                            with dpg.child_window(tag="pitch_nav_body", width=-1, height=40, border=False, no_scrollbar=True):
                                dpg.add_text("투구 데이터 없음", tag="pitch_nav_text", wrap=188)
                            dpg.add_spacer(height=4)
                            with dpg.group(horizontal=True):
                                dpg.add_button(tag="pitch_prev_button", label="이전", width=72, callback=lambda: self.move_focus("pitch", -1))
                                dpg.add_button(tag="pitch_next_button", label="다음", width=72, callback=lambda: self.move_focus("pitch", +1))
                        dpg.add_spacer(height=self.PANEL_GAP)
                        with dpg.child_window(tag="strike_zone_panel", width=220, height=-1, border=True, no_scrollbar=True):
                            dpg.add_drawlist(tag="strike_zone_drawlist", width=self.strike_zone_w, height=self.strike_zone_h)
                            dpg.add_spacer(height=6)
                            dpg.add_text("스트라이크존 정보 없음", tag="strike_zone_meta_text", wrap=188)

            dpg.add_spacer(height=self.PANEL_GAP)
            with dpg.group(tag="replay_bottom_info_group", horizontal=True):
                with dpg.child_window(tag="replay_inspector_panel", width=420, height=self.BOTTOM_INFO_MIN_HEIGHT, border=True, no_scrollbar=True):
                    dpg.add_text("검증 인스펙터")
                    dpg.add_text("자동 경고: 0건", tag="warning_count_text", color=(255, 100, 100))
                    dpg.add_input_text(tag="event_detail_text", multiline=True, readonly=True, width=-1, height=self.DETAIL_TEXT_HEIGHT)
                    dpg.add_text("자동 검증 기준에서 즉시 확인할 이상치는 발견되지 않았습니다.", tag="warning_hint_text", wrap=360)
                    dpg.add_separator()
                    with dpg.table(
                        header_row=False,
                        tag="warning_table",
                        policy=dpg.mvTable_SizingStretchProp,
                        row_background=True,
                        borders_innerH=True,
                        borders_outerH=True,
                        borders_innerV=True,
                        borders_outerV=True,
                        height=84,
                    ):
                        for _ in range(3):
                            dpg.add_table_column()

        self.update_loaded_game_summary()
        self.update_current_focus_summary()
        self.update_navigation_panel()
        self.draw_overlay_background()
        self.render_strike_zone_panel()
