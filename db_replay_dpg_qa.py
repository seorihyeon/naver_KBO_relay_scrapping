from __future__ import annotations

import dearpygui.dearpygui as dpg
import psycopg
import re
from pathlib import Path

from dpg_utils import bind_korean_font, create_or_replace_dynamic_texture, load_image_pixels

class ReplayDPGQA:
    def __init__(self):
        self.conn = None
        self.games = []  # [(game_id, label)]
        self.game_id = None

        self.events = []
        self.pitches = []
        self.pas = []
        self.innings = []

        self.event_idx = 0
        self.pitch_idx = 0
        self.pa_idx = 0
        self.inning_idx = 0

        self.pitch_row_tags = []
        self.warning_rows = []
        self.pitch_state_by_event = {}
        self.pa_state_by_id = {}
        self.derived_state_by_event = {}

        # ---- Layout constants ----
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
        self.pa_event_columns = None
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
        self.status_logs = []

    def set_status(self, summary, detail=None, append=False):
        if dpg.does_item_exist("status_text"):
            dpg.set_value("status_text", summary)

        if detail is None or not dpg.does_item_exist("status_detail_text"):
            return

        if append:
            self.status_logs.append(detail)
        else:
            self.status_logs = [detail]

        dpg.set_value("status_detail_text", "\n".join(self.status_logs))

    # ---------------- DB ----------------
    def connect_db(self):
        dsn = dpg.get_value("dsn_input").strip()
        self.set_status("DB 연결 중...", "DSN 확인 및 DB 연결을 시도합니다.")
        try:
            self.conn = psycopg.connect(dsn)
            self.conn.autocommit = True
            self.set_status("DB 연결 성공", "DB 연결 완료. 게임 목록을 불러옵니다.", append=True)
            self.load_games()
            self.set_status("DB 연결 및 게임 목록 로드 완료", "연결/초기 로딩 단계 완료.", append=True)
        except Exception as e:
            self.set_status("DB 연결 실패", "사용자 메시지: DSN/네트워크/DB 상태를 확인하세요.", append=False)
            self.set_status("DB 연결 실패", f"디버그 예외: {e}", append=True)

    def load_games(self):
        q = """
        SELECT g.game_id,
               COALESCE(to_char(g.game_date,'YYYY-MM-DD'),'NO_DATE') || ' | ' ||
               COALESCE(at.team_name_short,'AWAY') || ' vs ' || COALESCE(ht.team_name_short,'HOME') ||
               ' | game_id=' || g.game_id::text AS label
        FROM games g
        LEFT JOIN teams at ON at.team_id = g.away_team_id
        LEFT JOIN teams ht ON ht.team_id = g.home_team_id
        ORDER BY g.game_date DESC NULLS LAST, g.game_id DESC
        LIMIT 500
        """
        with self.conn.cursor() as cur:
            cur.execute(q)
            self.games = cur.fetchall()

        labels = [g[1] for g in self.games]
        dpg.configure_item("game_combo", items=labels)
        if labels:
            dpg.set_value("game_combo", labels[0])
            selected_game_id = self.games[0][0]
            self.set_status(
                f"게임 목록 로드 완료 ({len(labels)}건)",
                f"현재 선택 game_id={selected_game_id}",
                append=True
            )
        else:
            self.set_status("게임 목록 로드 완료 (0건)", "표시 가능한 게임이 없습니다.", append=True)

    def load_selected_game(self):
        if not self.conn:
            self.set_status("게임 로드 실패", "사용자 메시지: 먼저 DB 연결을 진행하세요.")
            return

        sel = dpg.get_value("game_combo")
        hit = [g for g in self.games if g[1] == sel]
        if not hit:
            self.set_status("게임 로드 실패", "사용자 메시지: 게임 선택 값이 유효하지 않습니다.")
            return

        self.game_id = hit[0][0]
        self.set_status(
            f"게임 로드 중... (game_id={self.game_id})",
            f"선택 게임 로드 시작: game_id={self.game_id}",
            append=False
        )
        try:
            self.events = self.fetch_events(self.game_id)
            self.set_status("게임 로드 중...", f"이벤트 로드 완료: {len(self.events)}건", append=True)

            self.pitches = self.fetch_pitches(self.game_id)
            self.pitch_state_by_event = {}
            for p in self.pitches:
                event_id = p[1]
                if event_id is None:
                    continue
                self.pitch_state_by_event[event_id] = {
                    "balls": self.safe_int(p[10]),
                    "strikes": self.safe_int(p[11]),
                }
            self.set_status("게임 로드 중...", f"투구 로드 완료: {len(self.pitches)}건", append=True)

            self.pas = self.fetch_pas(self.game_id)
            self.pa_state_by_id = {}
            for pa in self.pas:
                pa_id = pa[0]
                self.pa_state_by_id[pa_id] = {
                    "outs_before": self.safe_int(pa[6]),
                    "outs_after": self.safe_int(pa[7]),
                    "start_seqno": self.safe_int(pa[12]),
                    "end_seqno": self.safe_int(pa[13]),
                }
            self.set_status("게임 로드 중...", f"타석 로드 완료: {len(self.pas)}건", append=True)

            self.innings = self.fetch_innings(self.game_id)
            self.set_status("게임 로드 중...", f"이닝 로드 완료: {len(self.innings)}건", append=True)
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
            self.set_status(
                f"게임 로드 완료 (game_id={self.game_id})",
                "이벤트/투구/타석/이닝 데이터 로드 및 초기 렌더링이 완료되었습니다.",
                append=True
            )
        except Exception as e:
            self.set_status("게임 로드 실패", "사용자 메시지: 데이터를 불러오는 중 오류가 발생했습니다.", append=False)
            self.set_status("게임 로드 실패", f"디버그 예외: {e}", append=True)

    def get_pa_event_columns(self):
        if self.pa_event_columns is not None:
            return self.pa_event_columns

        q = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'pa_events'
        """
        with self.conn.cursor() as cur:
            cur.execute(q)
            self.pa_event_columns = {row[0] for row in cur.fetchall()}

        return self.pa_event_columns

    def fetch_events(self, game_id):
        cols = self.get_pa_event_columns()

        b1_name_expr = "e.base1_runner_name" if "base1_runner_name" in cols else "NULL"
        b2_name_expr = "e.base2_runner_name" if "base2_runner_name" in cols else "NULL"
        b3_name_expr = "e.base3_runner_name" if "base3_runner_name" in cols else "NULL"

        q = f"""
        SELECT e.event_id, e.event_seq_game, i.inning_no, i.half, e.pa_id, e.event_seq_in_pa,
               e.event_category, e.text, e.outs, e.balls, e.strikes,
               e.base1_occupied, e.base2_occupied, e.base3_occupied,
               e.home_score, e.away_score,
               {b1_name_expr} AS base1_runner_name,
               {b2_name_expr} AS base2_runner_name,
               {b3_name_expr} AS base3_runner_name
        FROM pa_events e
        LEFT JOIN innings i ON i.inning_id = e.inning_id
        WHERE e.game_id = %s
        ORDER BY e.event_seq_game
        """
        with self.conn.cursor() as cur:
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
        with self.conn.cursor() as cur:
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
        with self.conn.cursor() as cur:
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
        with self.conn.cursor() as cur:
            cur.execute(q, (game_id,))
            return cur.fetchall()

    # ---------------- Utility ----------------
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

    def extract_runner_name_from_text(self, text, base_no):
        if not text:
            return None

        direct = re.search(rf"{base_no}루주자\\s*([^ :]+)", text)
        if direct:
            return direct.group(1).strip()

        if base_no == 1:
            batter_on_base = re.search(r"^([^ :]+)\\s*:\\s*.*(볼넷|몸에 맞는 볼|고의4구|자동 고의4구|내야안타|안타)", text)
            if batter_on_base:
                return batter_on_base.group(1).strip()

        return None

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

            out_add = 0
            if "삼중살" in text:
                out_add = 3
            elif "병살" in text:
                out_add = 2
            elif "아웃" in text:
                # "송구아웃", "포스아웃" 등 보조 설명으로 "아웃"이 여러 번 들어가도
                # 기본적으로 1아웃 처리한다.
                out_add = 1

            if out_add > 0:
                outs = min(3, outs + out_add)
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
                elif base_no == 1:
                    batter_on_base = re.search(
                        r"^([^ :]+)\s*:\s*.*(볼넷|몸에 맞는 볼|고의4구|자동 고의4구|내야안타|안타)",
                        text,
                    )
                    if batter_on_base:
                        runner_names[1] = batter_on_base.group(1).strip()

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
        direct_outs = self.safe_int(ev[8])
        direct_balls = self.safe_int(ev[9])
        direct_strikes = self.safe_int(ev[10])
        direct_b1 = ev[11] if len(ev) > 11 else None
        direct_b2 = ev[12] if len(ev) > 12 else None
        direct_b3 = ev[13] if len(ev) > 13 else None
        direct_n1 = ev[16] if len(ev) > 16 else None
        direct_n2 = ev[17] if len(ev) > 17 else None
        direct_n3 = ev[18] if len(ev) > 18 else None
        if all(v is not None for v in [direct_outs, direct_balls, direct_strikes, direct_b1, direct_b2, direct_b3]):
            return {
                "outs": direct_outs,
                "balls": direct_balls,
                "strikes": direct_strikes,
                "home_score": self.safe_int(ev[14]) or 0,
                "away_score": self.safe_int(ev[15]) or 0,
                "b1_occ": bool(direct_b1),
                "b2_occ": bool(direct_b2),
                "b3_occ": bool(direct_b3),
                "b1_name": str(direct_n1).strip() if direct_n1 else None,
                "b2_name": str(direct_n2).strip() if direct_n2 else None,
                "b3_name": str(direct_n3).strip() if direct_n3 else None,
            }

        event_id = ev[0]
        if event_id in self.derived_state_by_event:
            derived_state = dict(self.derived_state_by_event[event_id])
            home_score = away_score = None
            for i in range(event_idx, -1, -1):
                prev_ev = self.events[i]
                if home_score is None:
                    home_score = self.safe_int(prev_ev[14])
                if away_score is None:
                    away_score = self.safe_int(prev_ev[15])
                if home_score is not None and away_score is not None:
                    break
            derived_state["home_score"] = home_score if home_score is not None else 0
            derived_state["away_score"] = away_score if away_score is not None else 0
            return derived_state

        outs = balls = strikes = home_score = away_score = None
        b1_occ = b2_occ = b3_occ = None
        b1_name = b2_name = b3_name = None

        for i in range(event_idx, -1, -1):
            ev = self.events[i]
            if outs is None:
                outs = self.safe_int(ev[8])
            if outs is None and ev[4] in self.pa_state_by_id:
                pa_state = self.pa_state_by_id[ev[4]]
                seq = self.safe_int(ev[1])
                pa_end = pa_state.get("end_seqno")
                if pa_end is not None and seq is not None and seq >= pa_end:
                    outs = pa_state.get("outs_after")
                else:
                    outs = pa_state.get("outs_before")
            if balls is None:
                balls = self.safe_int(ev[9])
            if strikes is None:
                strikes = self.safe_int(ev[10])
            if balls is None or strikes is None:
                pitch_state = self.pitch_state_by_event.get(ev[0])
                if pitch_state:
                    if balls is None:
                        balls = pitch_state.get("balls")
                    if strikes is None:
                        strikes = pitch_state.get("strikes")
            if home_score is None:
                home_score = self.safe_int(ev[14])
            if away_score is None:
                away_score = self.safe_int(ev[15])

            if b1_occ is None and len(ev) > 11 and ev[11] is not None:
                b1_occ = bool(ev[11])
            if b2_occ is None and len(ev) > 12 and ev[12] is not None:
                b2_occ = bool(ev[12])
            if b3_occ is None and len(ev) > 13 and ev[13] is not None:
                b3_occ = bool(ev[13])

            if b1_name is None and len(ev) > 16 and ev[16]:
                b1_name = str(ev[16]).strip()
            if b1_name is None:
                b1_name = self.extract_runner_name_from_text(ev[7], 1)
            if b2_name is None and len(ev) > 17 and ev[17]:
                b2_name = str(ev[17]).strip()
            if b2_name is None:
                b2_name = self.extract_runner_name_from_text(ev[7], 2)
            if b3_name is None and len(ev) > 18 and ev[18]:
                b3_name = str(ev[18]).strip()
            if b3_name is None:
                b3_name = self.extract_runner_name_from_text(ev[7], 3)

            if all(v is not None for v in [outs, balls, strikes, home_score, away_score, b1_occ, b2_occ, b3_occ]):
                break

        return {
            "outs": outs if outs is not None else 0,
            "balls": balls if balls is not None else 0,
            "strikes": strikes if strikes is not None else 0,
            "home_score": home_score if home_score is not None else 0,
            "away_score": away_score if away_score is not None else 0,
            "b1_occ": b1_occ if b1_occ is not None else False,
            "b2_occ": b2_occ if b2_occ is not None else False,
            "b3_occ": b3_occ if b3_occ is not None else False,
            "b1_name": b1_name,
            "b2_name": b2_name,
            "b3_name": b3_name,
        }

    def compute_overlay_positions(self, image_w, image_h):
        sx = image_w / self.BASE_IMAGE_W
        sy = image_h / self.BASE_IMAGE_H

        def scale_xy(xy):
            return (int(xy[0] * sx), int(xy[1] * sy))

        return {
            "bases": {k: scale_xy(v) for k, v in self.overlay_positions_base["bases"].items()},
            "outs": [scale_xy(v) for v in self.overlay_positions_base["outs"]],
            "balls": [scale_xy(v) for v in self.overlay_positions_base["balls"]],
            "strikes": [scale_xy(v) for v in self.overlay_positions_base["strikes"]],
            "score": {k: scale_xy(v) for k, v in self.overlay_positions_base["score"].items()},
        }

    def compute_layout(self):
        vw = dpg.get_viewport_client_width() or self.DEFAULT_VIEWPORT_W
        vh = dpg.get_viewport_client_height() or self.DEFAULT_VIEWPORT_H

        main_w = max(vw - 20, 700)
        main_h = max(vh - 20, 520)

        usable_w = max(main_w - 20, self.PANEL_MIN_WIDTH * 2)
        left_w = max(int(usable_w * self.LEFT_PANEL_RATIO), self.PANEL_MIN_WIDTH)
        right_w = max(usable_w - left_w - self.PANEL_GAP, self.PANEL_MIN_WIDTH)

        top_h = min(self.TOP_SECTION_HEIGHT, max(int(main_h * 0.45), 250))
        panel_h = max(main_h - top_h, 340)

        image_w = max(left_w - 40, 420)

        left_available = max(panel_h - self.LEFT_FIXED_HEIGHT, 260)
        relay_h = self.clamp(left_available * 0.34, 90, 180)
        image_h = self.clamp(min(left_available - relay_h, image_w / self.BASE_IMAGE_RATIO), 150, 320)

        right_available = max(panel_h - self.RIGHT_FIXED_HEIGHT, 220)
        pitch_h = self.clamp(right_available * 0.45, 120, 260)
        warning_h = self.clamp(right_available - pitch_h, 120, 320)

        return {
            "main_w": main_w,
            "main_h": main_h,
            "left_w": left_w,
            "right_w": right_w,
            "panel_h": panel_h,
            "image_w": image_w,
            "image_h": image_h,
            "relay_h": relay_h,
            "pitch_h": pitch_h,
            "warning_h": warning_h,
        }

    # ---------------- Anomaly ----------------
    def detect_anomalies(self):
        issues = []
        prev_ball = prev_strike = prev_home = prev_away = None
        prev_pa = None

        for i, e in enumerate(self.events):
            event_id, seq, inning_no, half, pa_id, seq_in_pa, cat, text, outs, balls, strikes, b1, b2, b3, hs, aws = e[:16]
            balls_i = self.safe_int(balls)
            strikes_i = self.safe_int(strikes)
            hs_i = self.safe_int(hs)
            aws_i = self.safe_int(aws)

            # 1) 점수 누락
            if hs_i is None or aws_i is None:
                issues.append((event_id, "점수 누락", f"event_seq={seq}, home/away score NULL"))

            # 타석 바뀌면 카운트 리셋 허용
            if prev_pa is not None and pa_id != prev_pa:
                prev_ball = prev_strike = None

            # 2) 카운트 역행
            if prev_ball is not None and balls_i is not None and balls_i < prev_ball:
                issues.append((event_id, "카운트 역행", f"볼 카운트 감소: {prev_ball} -> {balls_i} (seq={seq})"))
            if prev_strike is not None and strikes_i is not None and strikes_i < prev_strike:
                issues.append((event_id, "카운트 역행", f"스트라이크 카운트 감소: {prev_strike} -> {strikes_i} (seq={seq})"))

            # 3) 점수 역행
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

        idx = int(app_data)
        idx = max(0, min(len(self.events) - 1, idx))
        self.event_idx = idx
        self.render_event()

    def jump_to_event_index(self):
        if not self.events:
            return

        idx = self.safe_int(dpg.get_value("event_jump_input"))
        if idx is None:
            return

        idx = max(0, min(len(self.events) - 1, idx))
        self.event_idx = idx
        self.is_syncing_event_slider = True
        dpg.set_value("event_slider", idx)
        dpg.set_value("event_jump_input", idx)
        self.is_syncing_event_slider = False
        self.render_event()

    # ---------------- Render ----------------
    def render_event(self):
        if not self.events:
            dpg.set_value("relay_text", "이벤트 데이터 없음")
            return

        e = self.events[self.event_idx]
        state = self.get_resolved_game_state(self.event_idx)
        half_txt = "초" if e[3] == "top" else "말"
        base_txt = f"{'1' if state['b1_occ'] else '-'}{'2' if state['b2_occ'] else '-'}{'3' if state['b3_occ'] else '-'}"
        runner_1 = state["b1_name"] or "-"
        runner_2 = state["b2_name"] or "-"
        runner_3 = state["b3_name"] or "-"

        progress_header = (
            f"진행률 {self.event_idx + 1} / {len(self.events)} | "
            f"{e[2]}회{half_txt} | pa_id={e[4]}"
        )
        msg = (
            f"{progress_header}\n"
            f"[이벤트 #{self.event_idx + 1}] id={e[0]} / seq={e[1]} / seq_in_pa={e[5]}\n"
            f"이닝: {e[2]}회 {half_txt} | category={e[6]} | pa_id={e[4]}\n"
            f"카운트: {state['balls']}B-{state['strikes']}S | 아웃: {state['outs']} | 주자상태: {base_txt}\n"
            f"스코어: HOME {state['home_score']} : AWAY {state['away_score']}\n"
            f"주자: 1루({runner_1}), 2루({runner_2}), 3루({runner_3})\n"
            f"중계: {e[7] or '(텍스트 없음)'}"
        )
        self.set_status(f"이벤트 포커스 | game_id={self.game_id}")
        dpg.set_value("relay_text", msg)

        self.is_syncing_event_slider = True
        if dpg.does_item_exist("event_slider"):
            dpg.set_value("event_slider", self.event_idx)
        if dpg.does_item_exist("event_jump_input"):
            dpg.set_value("event_jump_input", self.event_idx)
        self.is_syncing_event_slider = False

        # 이벤트에 연관된 투구 하이라이트 갱신
        self.refresh_pitch_table(highlight_event_id=e[0])
        self.update_field_overlay(e, state)

    def update_field_overlay(self, event, state=None):
        if not dpg.does_item_exist(self.overlay_drawlist_tag):
            return

        dpg.delete_item(self.overlay_drawlist_tag, children_only=True)
        dpg.draw_image(
            self.tex_tag,
            pmin=(0, 0),
            pmax=(self.tex_w, self.tex_h),
            parent=self.overlay_drawlist_tag,
            tag=self.background_draw_tag,
        )

        if state is None:
            state = self.get_resolved_game_state(self.event_idx)
        event_outs = state["outs"]
        event_balls = state["balls"]
        event_strikes = state["strikes"]
        home_score = state["home_score"]
        away_score = state["away_score"]

        # 1/2/3루 점유
        base_map = {
            1: (state["b1_occ"], state["b1_name"]),
            2: (state["b2_occ"], state["b2_name"]),
            3: (state["b3_occ"], state["b3_name"]),
        }
        for base_no, center in self.overlay_positions["bases"].items():
            occupied, runner_name = base_map[base_no]
            fill = (255, 215, 0, 230) if occupied else (120, 120, 120, 120)
            dpg.draw_circle(center=center, radius=12, color=(255, 255, 255, 255),
                            fill=fill, thickness=2, parent=self.overlay_drawlist_tag)
            dpg.draw_text((center[0] - 4, center[1] - 8), str(base_no),
                          color=(0, 0, 0, 255), size=14, parent=self.overlay_drawlist_tag)
            if occupied:
                name_text = str(runner_name).strip() if runner_name else "주자"
                dpg.draw_text((center[0] + 14, center[1] - 24), name_text,
                              color=(255, 255, 255, 255), size=14, parent=self.overlay_drawlist_tag)

        # 아웃 카운트(0~2)
        outs_pos = self.overlay_positions["outs"]
        balls_pos = self.overlay_positions["balls"]
        strikes_pos = self.overlay_positions["strikes"]
        dpg.draw_text((outs_pos[0][0] - 28, outs_pos[0][1] - 12), "OUT", color=(255, 255, 255, 255), size=16, parent=self.overlay_drawlist_tag)
        for i, pos in enumerate(self.overlay_positions["outs"]):
            is_on = i < min(event_outs, 2)
            fill = (255, 80, 80, 235) if is_on else (70, 70, 70, 130)
            dpg.draw_circle(center=pos, radius=10, color=(255, 255, 255, 255),
                            fill=fill, thickness=2, parent=self.overlay_drawlist_tag)

        # 볼/스트라이크
        dpg.draw_text((balls_pos[0][0] - 20, balls_pos[0][1] - 10), "B", color=(255, 255, 255, 255), size=16, parent=self.overlay_drawlist_tag)
        for i, pos in enumerate(balls_pos):
            is_on = i < min(event_balls, 4)
            fill = (255, 210, 70, 235) if is_on else (70, 70, 70, 130)
            dpg.draw_circle(center=pos, radius=9, color=(255, 255, 255, 255),
                            fill=fill, thickness=2, parent=self.overlay_drawlist_tag)

        dpg.draw_text((strikes_pos[0][0] - 20, strikes_pos[0][1] - 10), "S", color=(255, 255, 255, 255), size=16, parent=self.overlay_drawlist_tag)
        for i, pos in enumerate(strikes_pos):
            is_on = i < min(event_strikes, 3)
            fill = (80, 170, 255, 235) if is_on else (70, 70, 70, 130)
            dpg.draw_circle(center=pos, radius=9, color=(255, 255, 255, 255),
                            fill=fill, thickness=2, parent=self.overlay_drawlist_tag)

        # 스코어
        score_pos = self.overlay_positions["score"]
        dpg.draw_text(score_pos["away_label"], "AWAY", color=(230, 230, 230, 255), size=18, parent=self.overlay_drawlist_tag)
        dpg.draw_text(score_pos["away_value"], str(away_score if away_score is not None else "-"),
                      color=(255, 255, 255, 255), size=24, parent=self.overlay_drawlist_tag)
        dpg.draw_text(score_pos["home_label"], "HOME", color=(230, 230, 230, 255), size=18, parent=self.overlay_drawlist_tag)
        dpg.draw_text(score_pos["home_value"], str(home_score if home_score is not None else "-"),
                      color=(255, 255, 255, 255), size=24, parent=self.overlay_drawlist_tag)

    def refresh_pitch_table(self, highlight_event_id=None):
        dpg.delete_item("pitch_table", children_only=True)

        # 헤더
        with dpg.table_row(parent="pitch_table"):
            for col in ["pitch_id", "event_id", "pa_id", "num", "result", "type", "speed", "count(before->after)"]:
                dpg.add_text(col)

        for p in self.pitches[:1000]:
            pitch_id, event_id, pa_id, inning_id, pitch_num, pitch_result, pitch_type_text, speed_kph, bb, sb, ba, sa, in_play, terminal = p
            is_hit = (highlight_event_id is not None and event_id == highlight_event_id)
            col = (255, 220, 50) if is_hit else (230, 230, 230)

            with dpg.table_row(parent="pitch_table"):
                dpg.add_text(str(pitch_id), color=col)
                dpg.add_text(str(event_id), color=col)
                dpg.add_text(str(pa_id), color=col)
                dpg.add_text(str(pitch_num), color=col)
                dpg.add_text(str(pitch_result), color=col)
                dpg.add_text(str(pitch_type_text), color=col)
                dpg.add_text(str(speed_kph), color=col)
                dpg.add_text(f"{bb}-{sb} -> {ba}-{sa}", color=col)

    # ---------------- Navigation ----------------
    def move(self, kind, delta):
        if not self.events:
            return

        if kind == "event":
            self.event_idx = max(0, min(len(self.events) - 1, self.event_idx + delta))
            self.render_event()
            return

        target_indices = []
        if kind == "pitch":
            seen_event_ids = set()
            for p in self.pitches:
                event_id = p[1]
                if event_id is None or event_id in seen_event_ids:
                    continue
                idx = self.find_event_index_by_event_id(event_id)
                if idx is not None:
                    target_indices.append(idx)
                    seen_event_ids.add(event_id)
        elif kind == "pa":
            seen_pa_ids = set()
            for ev_idx, ev in enumerate(self.events):
                pa_id = ev[4]
                if pa_id is None or pa_id in seen_pa_ids:
                    continue
                target_indices.append(ev_idx)
                seen_pa_ids.add(pa_id)
        elif kind == "inning":
            seen_innings = set()
            for ev_idx, ev in enumerate(self.events):
                key = (ev[2], ev[3])
                if key in seen_innings:
                    continue
                target_indices.append(ev_idx)
                seen_innings.add(key)

        if not target_indices:
            return

        current = self.event_idx
        if delta < 0:
            prev_candidates = [idx for idx in target_indices if idx < current]
            self.event_idx = prev_candidates[-1] if prev_candidates else target_indices[0]
        else:
            next_candidates = [idx for idx in target_indices if idx > current]
            self.event_idx = next_candidates[0] if next_candidates else target_indices[-1]

        self.render_event()

    # ---------------- Graphics ----------------
    def create_placeholder_texture(self, w=780, h=360):
        self.tex_w = w
        self.tex_h = h
        data = [0.08, 0.18, 0.10, 1.0] * (w * h)  # RGBA
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
            pixels, p = load_image_pixels(image_path, self.tex_w, self.tex_h, base_dir=Path(__file__).resolve().parent)

            # dynamic texture 갱신
            dpg.set_value(self.tex_tag, pixels)
            if dpg.does_item_exist(self.overlay_drawlist_tag):
                dpg.delete_item(self.overlay_drawlist_tag, children_only=True)
                dpg.draw_image(
                    self.tex_tag,
                    pmin=(0, 0),
                    pmax=(self.tex_w, self.tex_h),
                    parent=self.overlay_drawlist_tag,
                    tag=self.background_draw_tag,
                )
            dpg.set_value("status_text", f"배경 이미지 로드 성공: {p}")

        except Exception as e:
            dpg.set_value("status_text", f"배경 이미지 로드 실패: {e}")

    def resize_graphics_surface(self, width, height):
        box_w = max(int(width), 200)
        box_h = max(int(height), 120)

        ratio_from_box = box_w / max(box_h, 1)
        if ratio_from_box > self.BASE_IMAGE_RATIO:
            render_h = box_h
            render_w = int(render_h * self.BASE_IMAGE_RATIO)
        else:
            render_w = box_w
            render_h = int(render_w / self.BASE_IMAGE_RATIO)

        render_w = max(render_w, 200)
        render_h = max(render_h, 120)

        self.overlay_positions = self.compute_overlay_positions(render_w, render_h)
        self.create_placeholder_texture(render_w, render_h)

        if dpg.does_item_exist(self.overlay_drawlist_tag):
            dpg.configure_item(self.overlay_drawlist_tag, width=render_w, height=render_h)

        if self.current_image_path:
            self.load_stadium_texture(self.current_image_path)
        elif dpg.does_item_exist(self.overlay_drawlist_tag):
            dpg.delete_item(self.overlay_drawlist_tag, children_only=True)
            dpg.draw_image(
                self.tex_tag,
                pmin=(0, 0),
                pmax=(render_w, render_h),
                parent=self.overlay_drawlist_tag,
                tag=self.background_draw_tag,
            )

    def apply_responsive_layout(self):
        dims = self.compute_layout()
        if dpg.does_item_exist("main_window"):
            dpg.configure_item(
                "main_window",
                width=dims["main_w"],
                height=dims["main_h"],
            )

        if dpg.does_item_exist("left_panel"):
            dpg.configure_item("left_panel", width=dims["left_w"], height=dims["panel_h"])
        if dpg.does_item_exist("right_panel"):
            dpg.configure_item("right_panel", width=dims["right_w"], height=dims["panel_h"])

        self.resize_graphics_surface(dims["image_w"], dims["image_h"])

        if dpg.does_item_exist("event_slider"):
            dpg.configure_item("event_slider", width=max(dims["image_w"] - 20, 260))
        if dpg.does_item_exist("relay_text"):
            dpg.configure_item("relay_text", width=dims["image_w"], height=dims["relay_h"])

        if dpg.does_item_exist("pitch_table"):
            dpg.configure_item("pitch_table", height=dims["pitch_h"])
        if dpg.does_item_exist("warning_table"):
            dpg.configure_item("warning_table", height=dims["warning_h"])

        if self.events:
            self.update_field_overlay(self.events[self.event_idx], self.get_resolved_game_state(self.event_idx))

    def on_viewport_resize(self, sender=None, app_data=None):
        if dpg.does_item_exist("main_window"):
            self.apply_responsive_layout()

    # ---------------- UI ----------------
    def build(self):
        dpg.create_context()

        self.create_placeholder_texture(self.BASE_IMAGE_W, self.BASE_IMAGE_H)

        with dpg.window(tag="main_window", label="KBO DB Replay QA", width=self.DEFAULT_VIEWPORT_W - 40, height=self.DEFAULT_VIEWPORT_H - 60):
            with dpg.group(horizontal=True):
                dpg.add_text("DSN")
                dpg.add_input_text(tag="dsn_input", width=900, default_value="postgresql://HOST:PASSWORD@HOST:5432/DBNAME")
                dpg.add_button(label="DB 연결", callback=lambda: self.connect_db())

            with dpg.group(horizontal=True):
                dpg.add_combo(tag="game_combo", items=[], width=900)
                dpg.add_button(label="게임 로드", callback=lambda: self.load_selected_game())
                dpg.add_button(label="경고 재검사", callback=lambda: self.refresh_warning_panel())

            with dpg.group(horizontal=True):
                dpg.add_input_text(tag="img_path", width=700, default_value="assets/stadium.png")
                dpg.add_button(
                    label="배경 이미지 적용",
                    callback=lambda: self.load_stadium_texture(dpg.get_value("img_path"))
                )

            dpg.add_text("상태", tag="status_text")
            dpg.add_input_text(tag="status_detail_text", multiline=True, readonly=True, width=-1, height=90)
            dpg.add_text("자동 경고: 0건", tag="warning_count_text", color=(255, 100, 100))

            dpg.add_separator()
            with dpg.group(horizontal=True):
                # 좌측: 그래픽 + 문자중계
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
                        dpg.add_button(label="투구 ◀", callback=lambda: self.move("pitch", -1))
                        dpg.add_button(label="투구 ▶", callback=lambda: self.move("pitch", +1))
                        dpg.add_button(label="타석 ◀", callback=lambda: self.move("pa", -1))
                        dpg.add_button(label="타석 ▶", callback=lambda: self.move("pa", +1))
                        dpg.add_button(label="이닝 ◀", callback=lambda: self.move("inning", -1))
                        dpg.add_button(label="이닝 ▶", callback=lambda: self.move("inning", +1))

                    dpg.add_input_text(tag="relay_text", multiline=True, readonly=True, width=self.BASE_IMAGE_W, height=350)

                # 우측: 투구 하이라이트 + 경고패널
                with dpg.child_window(tag="right_panel", width=550, height=600, border=True):
                    dpg.add_text("연관 투구 자동 하이라이트 (현재 event_id 기준)")
                    dpg.add_text("※ 현재 이벤트(event_id)와 연결된 투구 행을 노란색으로 강조 표시합니다.", color=(170, 170, 170))
                    with dpg.table(header_row=False, tag="pitch_table",
                                   policy=dpg.mvTable_SizingStretchProp,
                                   row_background=True, borders_innerH=True, borders_outerH=True,
                                   borders_innerV=True, borders_outerV=True, height=320):
                        for _ in range(8):
                            dpg.add_table_column()

                    dpg.add_separator()
                    dpg.add_text("이상치 자동 경고 패널")
                    with dpg.table(header_row=False, tag="warning_table",
                                   policy=dpg.mvTable_SizingStretchProp,
                                   row_background=True, borders_innerH=True, borders_outerH=True,
                                   borders_innerV=True, borders_outerV=True, height=380):
                        for _ in range(3):
                            dpg.add_table_column()

        dpg.create_viewport(title="KBO Replay QA (Graphics + Alerts)", width=self.DEFAULT_VIEWPORT_W, height=self.DEFAULT_VIEWPORT_H)
        dpg.setup_dearpygui()
        bind_korean_font(size=16)
        dpg.set_viewport_resize_callback(self.on_viewport_resize)
        dpg.show_viewport()
        self.apply_responsive_layout()
        dpg.start_dearpygui()
        dpg.destroy_context()


if __name__ == "__main__":
    app = ReplayDPGQA()
    app.build()
