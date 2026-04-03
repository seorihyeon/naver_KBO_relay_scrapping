from __future__ import annotations

import dearpygui.dearpygui as dpg
import psycopg
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
            "bases": {1: (585, 250), 2: (500, 170), 3: (415, 250)},
            "outs": [(60, 60), (100, 60), (140, 60)],
            "balls": [(60, 320), (100, 320), (140, 320), (180, 320)],
            "strikes": [(60, 350), (100, 350), (140, 350)],
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
            self.set_status("게임 로드 중...", f"투구 로드 완료: {len(self.pitches)}건", append=True)

            self.pas = self.fetch_pas(self.game_id)
            self.set_status("게임 로드 중...", f"타석 로드 완료: {len(self.pas)}건", append=True)

            self.innings = self.fetch_innings(self.game_id)
            self.set_status("게임 로드 중...", f"이닝 로드 완료: {len(self.innings)}건", append=True)

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
            event_id, seq, inning_no, half, pa_id, seq_in_pa, cat, text, outs, balls, strikes, b1, b2, b3, hs, aws = e
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
        half_txt = "초" if e[3] == "top" else "말"
        base_txt = f"{'1' if e[11] else '-'}{'2' if e[12] else '-'}{'3' if e[13] else '-'}"
        runner_txt = f"1루:{e[16] or '-'} / 2루:{e[17] or '-'} / 3루:{e[18] or '-'}"

        progress_header = (
            f"진행률 {self.event_idx + 1} / {len(self.events)} | "
            f"{e[2]}회{half_txt} | pa_id={e[4]}"
        )
        msg = (
            f"{progress_header}\n"
            f"[이벤트 {self.event_idx+1}/{len(self.events)}]\n"
            f"event_id={e[0]}, seq={e[1]}, pa_id={e[4]}, seq_in_pa={e[5]}\n"
            f"{e[2]}회{half_txt} | category={e[6]}\n"
            f"count {e[9]}-{e[10]} | outs={e[8]} | base={base_txt}\n"
            f"HOME {e[14]} : AWAY {e[15]}\n"
            f"주자 {runner_txt}\n\n"
            f"{e[7] or '(텍스트 없음)'}"
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
        self.update_field_overlay(e)


    def update_field_overlay(self, event):
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

        event_outs = self.safe_int(event[8]) or 0
        event_balls = self.safe_int(event[9]) or 0
        event_strikes = self.safe_int(event[10]) or 0
        home_score = self.safe_int(event[14])
        away_score = self.safe_int(event[15])

        # 1/2/3루 점유
        base_map = {
            1: (bool(event[11]), event[16] if len(event) > 16 else None),
            2: (bool(event[12]), event[17] if len(event) > 17 else None),
            3: (bool(event[13]), event[18] if len(event) > 18 else None),
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
                dpg.draw_text((center[0] + 16, center[1] - 10), name_text,
                              color=(255, 255, 255, 255), size=14, parent=self.overlay_drawlist_tag)

        # 아웃 카운트(0~2)
        dpg.draw_text((20, 48), "OUT", color=(255, 255, 255, 255), size=16, parent=self.overlay_drawlist_tag)
        for i, pos in enumerate(self.overlay_positions["outs"]):
            is_on = i < min(event_outs, 2)
            fill = (255, 80, 80, 235) if is_on else (70, 70, 70, 130)
            dpg.draw_circle(center=pos, radius=10, color=(255, 255, 255, 255),
                            fill=fill, thickness=2, parent=self.overlay_drawlist_tag)

        # 볼/스트라이크
        dpg.draw_text((20, 308), "B", color=(255, 255, 255, 255), size=16, parent=self.overlay_drawlist_tag)
        for i, pos in enumerate(self.overlay_positions["balls"]):
            is_on = i < min(event_balls, 4)
            fill = (255, 210, 70, 235) if is_on else (70, 70, 70, 130)
            dpg.draw_circle(center=pos, radius=9, color=(255, 255, 255, 255),
                            fill=fill, thickness=2, parent=self.overlay_drawlist_tag)

        dpg.draw_text((20, 338), "S", color=(255, 255, 255, 255), size=16, parent=self.overlay_drawlist_tag)
        for i, pos in enumerate(self.overlay_positions["strikes"]):
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
        if kind == "event" and self.events:
            self.event_idx = max(0, min(len(self.events) - 1, self.event_idx + delta))
            self.render_event()
        elif kind == "pitch" and self.pitches:
            self.pitch_idx = max(0, min(len(self.pitches) - 1, self.pitch_idx + delta))
            p = self.pitches[self.pitch_idx]
            dpg.set_value("relay_text", f"[투구 {self.pitch_idx+1}/{len(self.pitches)}]\n{p}")
        elif kind == "pa" and self.pas:
            self.pa_idx = max(0, min(len(self.pas) - 1, self.pa_idx + delta))
            pa = self.pas[self.pa_idx]
            dpg.set_value("relay_text", f"[타석 {self.pa_idx+1}/{len(self.pas)}]\n{pa}")
        elif kind == "inning" and self.innings:
            self.inning_idx = max(0, min(len(self.innings) - 1, self.inning_idx + delta))
            inn = self.innings[self.inning_idx]
            dpg.set_value("relay_text", f"[이닝 {self.inning_idx+1}/{len(self.innings)}]\n{inn}")

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
            self.update_field_overlay(self.events[self.event_idx])

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
