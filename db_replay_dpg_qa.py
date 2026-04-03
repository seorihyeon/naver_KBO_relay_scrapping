from __future__ import annotations

import dearpygui.dearpygui as dpg
import psycopg
from PIL import Image


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

        self.tex_tag = "stadium_tex"

    # ---------------- DB ----------------
    def connect_db(self):
        dsn = dpg.get_value("dsn_input").strip()
        try:
            self.conn = psycopg.connect(dsn)
            self.conn.autocommit = True
            self.load_games()
            dpg.set_value("status_text", "DB 연결 성공")
        except Exception as e:
            dpg.set_value("status_text", f"DB 연결 실패: {e}")

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

    def load_selected_game(self):
        if not self.conn:
            dpg.set_value("status_text", "먼저 DB 연결하세요.")
            return

        sel = dpg.get_value("game_combo")
        hit = [g for g in self.games if g[1] == sel]
        if not hit:
            dpg.set_value("status_text", "게임 선택이 올바르지 않습니다.")
            return

        self.game_id = hit[0][0]
        self.events = self.fetch_events(self.game_id)
        self.pitches = self.fetch_pitches(self.game_id)
        self.pas = self.fetch_pas(self.game_id)
        self.innings = self.fetch_innings(self.game_id)

        self.event_idx = self.pitch_idx = self.pa_idx = self.inning_idx = 0
        self.render_event()
        self.refresh_pitch_table(highlight_event_id=self.current_event_id())
        self.refresh_warning_panel()

    def fetch_events(self, game_id):
        q = """
        SELECT e.event_id, e.event_seq_game, i.inning_no, i.half, e.pa_id, e.event_seq_in_pa,
               e.event_category, e.text, e.outs, e.balls, e.strikes,
               e.base1_occupied, e.base2_occupied, e.base3_occupied,
               e.home_score, e.away_score
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

    def current_event_id(self):
        if not self.events:
            return None
        return self.events[self.event_idx][0]

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

    # ---------------- Render ----------------
    def render_event(self):
        if not self.events:
            dpg.set_value("relay_text", "이벤트 데이터 없음")
            return

        e = self.events[self.event_idx]
        half_txt = "초" if e[3] == "top" else "말"
        base_txt = f"{'1' if e[11] else '-'}{'2' if e[12] else '-'}{'3' if e[13] else '-'}"

        msg = (
            f"[이벤트 {self.event_idx+1}/{len(self.events)}]\n"
            f"event_id={e[0]}, seq={e[1]}, pa_id={e[4]}, seq_in_pa={e[5]}\n"
            f"{e[2]}회{half_txt} | category={e[6]}\n"
            f"count {e[9]}-{e[10]} | outs={e[8]} | base={base_txt}\n"
            f"HOME {e[14]} : AWAY {e[15]}\n\n"
            f"{e[7] or '(텍스트 없음)'}"
        )
        dpg.set_value("status_text", f"이벤트 포커스 | game_id={self.game_id}")
        dpg.set_value("relay_text", msg)

        # 이벤트에 연관된 투구 하이라이트 갱신
        self.refresh_pitch_table(highlight_event_id=e[0])

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
    def load_stadium_texture(self, image_path="assets/stadium.png"):
        try:
            image = Image.open(image_path).convert("RGBA")
            width, height = image.size
            data = []
            for r, g, b, a in image.getdata():
                data.extend([r / 255.0, g / 255.0, b / 255.0, a / 255.0])

            with dpg.texture_registry(show=False):
                if dpg.does_item_exist(self.tex_tag):
                    dpg.delete_item(self.tex_tag)
                dpg.add_static_texture(width, height, data, tag=self.tex_tag)

            dpg.configure_item("stadium_image", texture_tag=self.tex_tag)
            dpg.set_value("status_text", f"배경 이미지 로드 성공: {image_path}")
        except Exception as e:
            dpg.set_value("status_text", f"배경 이미지 로드 실패: {e}")

    # ---------------- UI ----------------
    def build(self):
        dpg.create_context()

        with dpg.window(label="KBO DB Replay QA", width=1400, height=900):
            with dpg.group(horizontal=True):
                dpg.add_text("DSN")
                dpg.add_input_text(tag="dsn_input", width=900, default_value="postgresql://USER:PASSWORD@HOST:5432/DBNAME")
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
            dpg.add_text("자동 경고: 0건", tag="warning_count_text", color=(255, 100, 100))

            dpg.add_separator()
            with dpg.group(horizontal=True):
                # 좌측: 그래픽 + 문자중계
                with dpg.child_window(width=820, height=780, border=True):
                    dpg.add_text("그래픽 뷰 (야구장 배경 + 오버레이)")
                    dpg.add_image("0", tag="stadium_image", width=780, height=360)  # texture_tag는 로드 후 갱신

                    dpg.add_separator()
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="이벤트 ◀", callback=lambda: self.move("event", -1))
                        dpg.add_button(label="이벤트 ▶", callback=lambda: self.move("event", +1))
                        dpg.add_button(label="투구 ◀", callback=lambda: self.move("pitch", -1))
                        dpg.add_button(label="투구 ▶", callback=lambda: self.move("pitch", +1))
                        dpg.add_button(label="타석 ◀", callback=lambda: self.move("pa", -1))
                        dpg.add_button(label="타석 ▶", callback=lambda: self.move("pa", +1))
                        dpg.add_button(label="이닝 ◀", callback=lambda: self.move("inning", -1))
                        dpg.add_button(label="이닝 ▶", callback=lambda: self.move("inning", +1))

                    dpg.add_input_text(tag="relay_text", multiline=True, readonly=True, width=780, height=350)

                # 우측: 투구 하이라이트 + 경고패널
                with dpg.child_window(width=550, height=780, border=True):
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

        dpg.create_viewport(title="KBO Replay QA (Graphics + Alerts)", width=1440, height=940)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()


if __name__ == "__main__":
    app = ReplayDPGQA()
    app.build()