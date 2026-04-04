from __future__ import annotations

import re
from pathlib import Path

import dearpygui.dearpygui as dpg

from dpg_utils import create_or_replace_dynamic_texture, load_image_pixels
from .shared_state import AppState


class ReplayTab:
    def __init__(self, state: AppState):
        self.state = state
        self.events = []
        self.pitches = []
        self.pas = []
        self.innings = []

        self.event_idx = 0
        self.pitch_idx = 0
        self.pa_idx = 0
        self.inning_idx = 0

        self.pitch_state_by_event = {}
        self.pa_state_by_id = {}
        self.derived_state_by_event = {}
        self.player_name_by_id = {}
        self.pa_event_columns = None

        self.DEFAULT_VIEWPORT_W = 1440
        self.DEFAULT_VIEWPORT_H = 940
        self.LEFT_PANEL_RATIO = 0.60
        self.RIGHT_PANEL_RATIO = 0.40
        self.PANEL_MIN_WIDTH = 420
        self.TOP_SECTION_HEIGHT = 330
        self.PANEL_GAP = 20
        self.LEFT_FIXED_HEIGHT = 170
        self.RIGHT_FIXED_HEIGHT = 90
        self.BASE_IMAGE_W = 780
        self.BASE_IMAGE_H = 360
        self.BASE_IMAGE_RATIO = self.BASE_IMAGE_W / self.BASE_IMAGE_H

        self.tex_tag = "stadium_tex"
        self.overlay_drawlist_tag = "stadium_overlay_drawlist"
        self.background_draw_tag = "stadium_bg_image"
        self.is_syncing_event_slider = False
        self.current_image_path = "assets/stadium.png"
        self.overlay_positions_base = {
            "bases": {1: (390, 252), 2: (338, 210), 3: (286, 252)},
            "outs": [(42, 42), (72, 42), (102, 42)],
            "balls": [(44, 308), (74, 308), (104, 308), (134, 308)],
            "strikes": [(44, 334), (74, 334), (104, 334)],
            "score": {
                "away_label": (610, 25),
                "away_value": (690, 25),
                "home_label": (610, 55),
                "home_value": (690, 55),
            },
        }
        self.overlay_positions = self.overlay_positions_base.copy()

    def safe_int(self, x):
        try:
            return int(x) if x is not None else None
        except Exception:
            return None

    def clamp(self, value, min_value, max_value):
        return max(min_value, min(int(value), max_value))

    def current_event_id(self):
        if not self.events:
            return None
        return self.events[self.event_idx][0]

    def find_event_index_by_event_id(self, event_id):
        for idx, ev in enumerate(self.events):
            if ev[0] == event_id:
                return idx
        return None

    def load_selected_game(self):
        if not self.state.conn:
            self.state.set_status("게임 로드 실패", "사용자 메시지: 먼저 DB 연결을 진행하세요.")
            return

        sel = dpg.get_value("game_combo")
        hit = [g for g in self.state.games if g[1] == sel]
        if not hit:
            self.state.set_status("게임 로드 실패", "사용자 메시지: 게임 선택 값이 유효하지 않습니다.")
            return

        self.state.game_id = hit[0][0]
        self.state.set_status(
            f"게임 로드 중... (game_id={self.state.game_id})",
            f"선택 게임 로드 시작: game_id={self.state.game_id}",
            append=False,
        )
        try:
            with self.state.conn.cursor() as cur:
                cur.execute("SELECT player_id, player_name FROM players")
                self.player_name_by_id = {row[0]: row[1] for row in cur.fetchall() if row[0]}

            self.events = self.fetch_events(self.state.game_id)
            self.state.set_status("게임 로드 중...", f"이벤트 로드 완료: {len(self.events)}건", append=True)

            self.pitches = self.fetch_pitches(self.state.game_id)
            self.pitch_state_by_event = {}
            for p in self.pitches:
                event_id = p[1]
                if event_id is None:
                    continue
                self.pitch_state_by_event[event_id] = {
                    "balls": self.safe_int(p[10]),
                    "strikes": self.safe_int(p[11]),
                }
            self.state.set_status("게임 로드 중...", f"투구 로드 완료: {len(self.pitches)}건", append=True)

            self.pas = self.fetch_pas(self.state.game_id)
            self.pa_state_by_id = {}
            for pa in self.pas:
                pa_id = pa[0]
                self.pa_state_by_id[pa_id] = {
                    "outs_before": self.safe_int(pa[6]),
                    "outs_after": self.safe_int(pa[7]),
                    "start_seqno": self.safe_int(pa[12]),
                    "end_seqno": self.safe_int(pa[13]),
                }
            self.state.set_status("게임 로드 중...", f"타석 로드 완료: {len(self.pas)}건", append=True)

            self.innings = self.fetch_innings(self.state.game_id)
            self.state.set_status("게임 로드 중...", f"이닝 로드 완료: {len(self.innings)}건", append=True)
            self.derived_state_by_event = self.build_derived_state_map()

            self.event_idx = self.pitch_idx = self.pa_idx = self.inning_idx = 0

            event_max = max(0, len(self.events) - 1)
            dpg.configure_item("event_slider", min_value=0, max_value=event_max, enabled=bool(self.events))
            self.is_syncing_event_slider = True
            dpg.set_value("event_slider", 0)
            dpg.set_value("event_jump_input", 0)
            self.is_syncing_event_slider = False

            self.render_event()
            self.refresh_pitch_table(highlight_event_id=self.current_event_id())
            self.refresh_warning_panel()
            self.state.set_status(
                f"게임 로드 완료 (game_id={self.state.game_id})",
                "이벤트/투구/타석/이닝 데이터 로드 및 초기 렌더링이 완료되었습니다.",
                append=True,
            )
        except Exception as e:
            self.state.set_status("게임 로드 실패", "사용자 메시지: 데이터를 불러오는 중 오류가 발생했습니다.", append=False)
            self.state.set_status("게임 로드 실패", f"디버그 예외: {e}", append=True)

    def get_pa_event_columns(self):
        if self.pa_event_columns is not None:
            return self.pa_event_columns

        q = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'pa_events'
        """
        with self.state.conn.cursor() as cur:
            cur.execute(q)
            self.pa_event_columns = {row[0] for row in cur.fetchall()}

        return self.pa_event_columns

    def fetch_events(self, game_id):
        cols = self.get_pa_event_columns()
        b1_name_expr = "e.base1_runner_name" if "base1_runner_name" in cols else "NULL"
        b2_name_expr = "e.base2_runner_name" if "base2_runner_name" in cols else "NULL"
        b3_name_expr = "e.base3_runner_name" if "base3_runner_name" in cols else "NULL"
        b1_id_expr = "e.base1_runner_id" if "base1_runner_id" in cols else "NULL"
        b2_id_expr = "e.base2_runner_id" if "base2_runner_id" in cols else "NULL"
        b3_id_expr = "e.base3_runner_id" if "base3_runner_id" in cols else "NULL"

        q = f"""
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
            cur.execute(q, (game_id,))
            return cur.fetchall()

    def fetch_pitches(self, game_id):
        q = """
        SELECT pitch_id, event_id, pa_id, inning_id, pitch_num, pitch_result, pitch_type_text, speed_kph,
               balls_before, strikes_before, balls_after, strikes_after, is_in_play, is_terminal_pitch
        FROM pitches
        WHERE game_id = %s
        ORDER BY inning_id NULLS LAST, pa_id NULLS LAST, pitch_num NULLS LAST, pitch_id
        """
        with self.state.conn.cursor() as cur:
            cur.execute(q, (game_id,))
            return cur.fetchall()

    def fetch_pas(self, game_id):
        q = """
        SELECT pa.pa_id, pa.pa_seq_game, i.inning_no, i.half, pa.batter_id, pa.pitcher_id,
               pa.outs_before, pa.outs_after, pa.balls_final, pa.strikes_final,
               pa.result_text, pa.runs_scored_on_pa, pa.start_seqno, pa.end_seqno
        FROM plate_appearances pa
        LEFT JOIN innings i ON i.inning_id = pa.inning_id
        WHERE pa.game_id = %s
        ORDER BY pa.pa_seq_game
        """
        with self.state.conn.cursor() as cur:
            cur.execute(q, (game_id,))
            return cur.fetchall()

    def fetch_innings(self, game_id):
        q = """
        SELECT inning_id, inning_no, half, runs_scored, hits_in_half, errors_in_half, walks_in_half,
               start_event_seqno, end_event_seqno
        FROM innings
        WHERE game_id = %s
        ORDER BY inning_no, CASE WHEN half='top' THEN 0 ELSE 1 END
        """
        with self.state.conn.cursor() as cur:
            cur.execute(q, (game_id,))
            return cur.fetchall()

    def extract_runner_name_from_text(self, text, base_no):
        if not text:
            return None
        direct = re.search(rf"{base_no}루주자\\s*([^ :]+)", text)
        if direct:
            return direct.group(1).strip()
        return None

    def normalize_runner_name(self, name):
        if name is None:
            return None
        txt = str(name).strip()
        if txt in {"", "-", "주자", "-주자"}:
            return None
        txt = re.sub(r"^[123]루주자\\s*", "", txt).strip()
        if txt in {"", "-", "주자"}:
            return None
        return txt

    def resolve_runner_name(self, event, base_no, fallback_name=None):
        clean_name = self.normalize_runner_name(fallback_name)
        if clean_name:
            return clean_name
        id_index = {1: 19, 2: 20, 3: 21}.get(base_no)
        if id_index is None or len(event) <= id_index:
            return None
        runner_id = event[id_index]
        if not runner_id:
            return None
        return self.normalize_runner_name(self.player_name_by_id.get(runner_id))

    def build_derived_state_map(self):
        derived = {}
        balls, strikes, outs = 0, 0, 0
        runner_names = {1: None, 2: None, 3: None}
        for ev in self.events:
            event_id = ev[0]
            text = (ev[7] or "").strip()
            occ = {
                1: bool(ev[11]) if len(ev) > 11 and ev[11] is not None else False,
                2: bool(ev[12]) if len(ev) > 12 and ev[12] is not None else False,
                3: bool(ev[13]) if len(ev) > 13 and ev[13] is not None else False,
            }
            if "번타자" in text:
                balls, strikes = 0, 0
            if re.search(r"\d+구\s*볼", text) and "볼넷" not in text and "몸에 맞는 볼" not in text:
                balls = min(4, balls + 1)
            if "헛스윙" in text or ("스트라이크" in text and "자동 고의4구" not in text):
                strikes = min(3, strikes + 1)
            if "파울" in text and strikes < 2:
                strikes += 1
            if any(keyword in text for keyword in ["볼넷", "고의4구", "몸에 맞는 볼"]):
                balls, strikes = 0, 0
            if "아웃" in text:
                outs = min(3, outs + 1)
                balls, strikes = 0, 0
            if "공격" in text and ("회초" in text or "회말" in text):
                outs, balls, strikes = 0, 0, 0
                runner_names = {1: None, 2: None, 3: None}

            for base_no in [1, 2, 3]:
                if not occ[base_no]:
                    runner_names[base_no] = None
                    continue
                found_name = self.extract_runner_name_from_text(text, base_no)
                if found_name:
                    runner_names[base_no] = found_name

            derived[event_id] = {
                "outs": outs,
                "balls": balls,
                "strikes": strikes,
                "b1_occ": occ[1],
                "b2_occ": occ[2],
                "b3_occ": occ[3],
                "b1_name": runner_names[1],
                "b2_name": runner_names[2],
                "b3_name": runner_names[3],
            }
        return derived

    def get_resolved_game_state(self, event_idx):
        ev = self.events[event_idx]
        return {
            "outs": self.safe_int(ev[8]) if self.safe_int(ev[8]) is not None else 0,
            "balls": self.safe_int(ev[9]) if self.safe_int(ev[9]) is not None else 0,
            "strikes": self.safe_int(ev[10]) if self.safe_int(ev[10]) is not None else 0,
            "home_score": self.safe_int(ev[14]) if self.safe_int(ev[14]) is not None else 0,
            "away_score": self.safe_int(ev[15]) if self.safe_int(ev[15]) is not None else 0,
            "b1_occ": bool(ev[11]) if len(ev) > 11 and ev[11] is not None else False,
            "b2_occ": bool(ev[12]) if len(ev) > 12 and ev[12] is not None else False,
            "b3_occ": bool(ev[13]) if len(ev) > 13 and ev[13] is not None else False,
            "b1_name": self.normalize_runner_name(ev[16] if len(ev) > 16 else None),
            "b2_name": self.normalize_runner_name(ev[17] if len(ev) > 17 else None),
            "b3_name": self.normalize_runner_name(ev[18] if len(ev) > 18 else None),
        }

    def detect_anomalies(self):
        issues = []
        prev_ball = prev_strike = prev_home = prev_away = None
        prev_pa = None
        for e in self.events:
            event_id, seq, _, _, pa_id, _, _, _, _, balls, strikes, *_rest, hs, aws = e[:16]
            balls_i = self.safe_int(balls)
            strikes_i = self.safe_int(strikes)
            hs_i = self.safe_int(hs)
            aws_i = self.safe_int(aws)
            if hs_i is None or aws_i is None:
                issues.append((event_id, "점수 누락", f"event_seq={seq}, home/away score NULL"))
            if prev_pa is not None and pa_id != prev_pa:
                prev_ball = prev_strike = None
            if prev_ball is not None and balls_i is not None and balls_i < prev_ball:
                issues.append((event_id, "카운트 역행", f"볼 카운트 감소: {prev_ball} -> {balls_i} (seq={seq})"))
            if prev_strike is not None and strikes_i is not None and strikes_i < prev_strike:
                issues.append((event_id, "카운트 역행", f"스트라이크 카운트 감소: {prev_strike} -> {strikes_i} (seq={seq})"))
            if prev_home is not None and hs_i is not None and hs_i < prev_home:
                issues.append((event_id, "점수 역행", f"HOME 점수 감소: {prev_home} -> {hs_i} (seq={seq})"))
            if prev_away is not None and aws_i is not None and aws_i < prev_away:
                issues.append((event_id, "점수 역행", f"AWAY 점수 감소: {prev_away} -> {aws_i} (seq={seq})"))
            prev_pa = pa_id
            prev_ball = balls_i if balls_i is not None else prev_ball
            prev_strike = strikes_i if strikes_i is not None else prev_strike
            prev_home = hs_i if hs_i is not None else prev_home
            prev_away = aws_i if aws_i is not None else prev_away
        return issues

    def refresh_warning_panel(self):
        dpg.delete_item("warning_table", children_only=True)
        issues = self.detect_anomalies()
        with dpg.table_row(parent="warning_table"):
            dpg.add_text("event_id")
            dpg.add_text("유형")
            dpg.add_text("상세")
        for ev_id, typ, detail in issues[:500]:
            with dpg.table_row(parent="warning_table"):
                dpg.add_text(str(ev_id))
                dpg.add_text(typ, color=(255, 80, 80))
                dpg.add_text(detail)
        dpg.set_value("warning_count_text", f"자동 경고: {len(issues)}건")

    def on_event_slider_change(self, sender, app_data):
        if self.is_syncing_event_slider or not self.events:
            return
        self.event_idx = max(0, min(len(self.events) - 1, int(app_data)))
        self.render_event()

    def jump_to_event_index(self):
        if not self.events:
            return
        idx = self.safe_int(dpg.get_value("event_jump_input"))
        if idx is None:
            return
        self.event_idx = max(0, min(len(self.events) - 1, idx))
        self.is_syncing_event_slider = True
        dpg.set_value("event_slider", self.event_idx)
        dpg.set_value("event_jump_input", self.event_idx)
        self.is_syncing_event_slider = False
        self.render_event()

    def render_event(self):
        if not self.events:
            dpg.set_value("relay_text", "이벤트 데이터 없음")
            return
        e = self.events[self.event_idx]
        state = self.get_resolved_game_state(self.event_idx)
        half_txt = "초" if e[3] == "top" else "말"
        dpg.set_value(
            "relay_text",
            f"진행률 {self.event_idx + 1} / {len(self.events)}\n이닝: {e[2]}회{half_txt}\n중계: {e[7] or '(텍스트 없음)'}",
        )
        self.state.set_status(f"이벤트 포커스 | game_id={self.state.game_id}")
        self.is_syncing_event_slider = True
        dpg.set_value("event_slider", self.event_idx)
        dpg.set_value("event_jump_input", self.event_idx)
        self.is_syncing_event_slider = False
        self.refresh_pitch_table(highlight_event_id=e[0])
        self.update_field_overlay(e, state)

    def update_field_overlay(self, event, state=None):
        if not dpg.does_item_exist(self.overlay_drawlist_tag):
            return
        dpg.delete_item(self.overlay_drawlist_tag, children_only=True)
        dpg.draw_image(self.tex_tag, pmin=(0, 0), pmax=(self.tex_w, self.tex_h), parent=self.overlay_drawlist_tag, tag=self.background_draw_tag)
        if state is None:
            state = self.get_resolved_game_state(self.event_idx)
        dpg.draw_text((10, 10), f"B/S/O {state['balls']}/{state['strikes']}/{state['outs']}", color=(255, 255, 255, 255), size=18, parent=self.overlay_drawlist_tag)
        dpg.draw_text((10, 36), f"HOME {state['home_score']} - AWAY {state['away_score']}", color=(255, 255, 255, 255), size=18, parent=self.overlay_drawlist_tag)

    def refresh_pitch_table(self, highlight_event_id=None):
        dpg.delete_item("pitch_table", children_only=True)
        with dpg.table_row(parent="pitch_table"):
            for col in ["pitch_id", "event_id", "pa_id", "num", "result", "type", "speed", "count(before->after)"]:
                dpg.add_text(col)
        for p in self.pitches[:1000]:
            pitch_id, event_id, pa_id, _, pitch_num, pitch_result, pitch_type_text, speed_kph, bb, sb, ba, sa, *_ = p
            col = (255, 220, 50) if highlight_event_id is not None and event_id == highlight_event_id else (230, 230, 230)
            with dpg.table_row(parent="pitch_table"):
                dpg.add_text(str(pitch_id), color=col)
                dpg.add_text(str(event_id), color=col)
                dpg.add_text(str(pa_id), color=col)
                dpg.add_text(str(pitch_num), color=col)
                dpg.add_text(str(pitch_result), color=col)
                dpg.add_text(str(pitch_type_text), color=col)
                dpg.add_text(str(speed_kph), color=col)
                dpg.add_text(f"{bb}-{sb} -> {ba}-{sa}", color=col)

    def move(self, kind, delta):
        if not self.events:
            return
        if kind == "event":
            self.event_idx = max(0, min(len(self.events) - 1, self.event_idx + delta))
            self.render_event()

    def create_placeholder_texture(self, w=780, h=360):
        self.tex_w = w
        self.tex_h = h
        data = [0.08, 0.18, 0.10, 1.0] * (w * h)
        old_tex_tag = self.tex_tag
        self.tex_tag = create_or_replace_dynamic_texture(self.tex_tag, w, h, data)
        if old_tex_tag != self.tex_tag and dpg.does_item_exist(old_tex_tag):
            try:
                dpg.delete_item(old_tex_tag)
            except Exception:
                pass

    def load_stadium_texture(self, image_path="assets/stadium.png"):
        try:
            self.current_image_path = image_path
            pixels, p = load_image_pixels(image_path, self.tex_w, self.tex_h, base_dir=Path(__file__).resolve().parents[1])
            dpg.set_value(self.tex_tag, pixels)
            if dpg.does_item_exist(self.overlay_drawlist_tag):
                dpg.delete_item(self.overlay_drawlist_tag, children_only=True)
                dpg.draw_image(self.tex_tag, pmin=(0, 0), pmax=(self.tex_w, self.tex_h), parent=self.overlay_drawlist_tag, tag=self.background_draw_tag)
            self.state.set_status(f"배경 이미지 로드 성공: {p}")
        except Exception as e:
            self.state.set_status(f"배경 이미지 로드 실패: {e}")

    def apply_responsive_layout(self):
        if dpg.does_item_exist("event_slider"):
            dpg.configure_item("event_slider", width=max(self.BASE_IMAGE_W - 20, 260))

    def build(self, parent):
        self.create_placeholder_texture(self.BASE_IMAGE_W, self.BASE_IMAGE_H)
        with dpg.tab(label="Replay / 검증", parent=parent):
            with dpg.group(horizontal=True):
                dpg.add_combo(tag="game_combo", items=[], width=900)
                dpg.add_button(label="게임 로드", callback=lambda: self.load_selected_game())
                dpg.add_button(label="경고 재검사", callback=lambda: self.refresh_warning_panel())
            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="img_path", width=700, default_value=self.state.default_image_path)
                dpg.add_button(label="배경 이미지 적용", callback=lambda: self.load_stadium_texture(dpg.get_value("img_path")))

            dpg.add_text("자동 경고: 0건", tag="warning_count_text", color=(255, 100, 100))
            dpg.add_separator()
            with dpg.group(horizontal=True):
                with dpg.child_window(tag="left_panel", width=820, height=600, border=True):
                    dpg.add_text("그래픽 뷰 (야구장 배경 + 오버레이)")
                    dpg.add_drawlist(tag=self.overlay_drawlist_tag, width=self.BASE_IMAGE_W, height=self.BASE_IMAGE_H)
                    dpg.add_separator()
                    dpg.add_text("이벤트 인덱스")
                    dpg.add_slider_int(tag="event_slider", label="", width=self.BASE_IMAGE_W - 20, min_value=0, max_value=0, default_value=0, enabled=False, callback=self.on_event_slider_change)
                    with dpg.group(horizontal=True):
                        dpg.add_input_int(tag="event_jump_input", label="점프", width=160, default_value=0, min_value=0, min_clamped=True, step=1, step_fast=10)
                        dpg.add_button(label="이벤트 점프", callback=lambda: self.jump_to_event_index())
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="이벤트 ◀", callback=lambda: self.move("event", -1))
                        dpg.add_button(label="이벤트 ▶", callback=lambda: self.move("event", +1))
                    dpg.add_input_text(tag="relay_text", multiline=True, readonly=True, width=self.BASE_IMAGE_W, height=350)
                with dpg.child_window(tag="right_panel", width=550, height=600, border=True):
                    dpg.add_text("연관 투구 자동 하이라이트 (현재 event_id 기준)")
                    with dpg.table(header_row=False, tag="pitch_table", policy=dpg.mvTable_SizingStretchProp, row_background=True, borders_innerH=True, borders_outerH=True, borders_innerV=True, borders_outerV=True, height=320):
                        for _ in range(8):
                            dpg.add_table_column()
                    dpg.add_separator()
                    dpg.add_text("이상치 자동 경고 패널")
                    with dpg.table(header_row=False, tag="warning_table", policy=dpg.mvTable_SizingStretchProp, row_background=True, borders_innerH=True, borders_outerH=True, borders_innerV=True, borders_outerV=True, height=380):
                        for _ in range(3):
                            dpg.add_table_column()
