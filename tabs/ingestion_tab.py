from __future__ import annotations

from pathlib import Path

import dearpygui.dearpygui as dpg
import psycopg

from src.kbo_ingest.pipeline import load_one_game

from .shared_state import AppState


class IngestionTab:
    def __init__(self, state: AppState):
        self.state = state

    def connect_db(self):
        dsn = dpg.get_value("dsn_input").strip()
        self.state.set_status("info", "DB 연결 중...", "DSN 확인 및 DB 연결을 시도합니다.", source="데이터 적재")
        try:
            self.state.conn = psycopg.connect(dsn)
            self.state.conn.autocommit = True
            self.state.set_status("info", "DB 연결 성공", "DB 연결 완료. 게임 목록을 불러옵니다.", source="데이터 적재", append=True)
            self.load_games()
            self.state.set_status("info", "DB 연결 및 게임 목록 로드 완료", "연결/초기 로딩 단계 완료.", source="데이터 적재", append=True)
        except Exception as e:
            self.state.set_status("error", "DB 연결 실패", "DSN/네트워크/DB 상태를 확인하세요.", debug_detail=str(e), source="데이터 적재", append=False)

    def create_schema(self):
        if not self.state.conn:
            self.state.set_status("warn", "스키마 생성 실패", "먼저 DB 연결을 진행하세요.", source="데이터 적재")
            return
        schema_path = Path(dpg.get_value("schema_path_input")).expanduser()
        if not schema_path.exists():
            self.state.set_status("warn", "스키마 생성 실패", f"스키마 파일을 찾을 수 없습니다: {schema_path}", source="데이터 적재")
            return
        try:
            with self.state.conn.cursor() as cur:
                cur.execute(schema_path.read_text(encoding="utf-8"))
            self.state.set_status("info", "스키마 생성 완료", f"스키마 반영: {schema_path}", source="데이터 적재", append=True)
        except Exception as e:
            self.state.set_status("error", "스키마 생성 실패", "스키마 적용 중 오류가 발생했습니다.", debug_detail=str(e), source="데이터 적재", append=True)

    def ingest_json_to_db(self):
        if not self.state.conn:
            self.state.set_status("warn", "적재 실패", "먼저 DB 연결을 진행하세요.", source="데이터 적재")
            return

        data_dir = Path(dpg.get_value("json_data_dir_input")).expanduser()
        if not data_dir.exists():
            self.state.set_status("warn", "적재 실패", f"데이터 디렉터리를 찾을 수 없습니다: {data_dir}", source="데이터 적재")
            return

        loaded = 0
        try:
            for json_path in sorted(data_dir.rglob("*.json")):
                load_one_game(self.state.conn, json_path)
                loaded += 1
            self.state.set_status("info", "적재 완료", f"JSON 적재 완료: {loaded}개 파일", source="데이터 적재", append=True)
            self.load_games()
        except Exception as e:
            self.state.set_status("error", "적재 실패", "적재 중 오류가 발생했습니다.", debug_detail=str(e), source="데이터 적재", append=True)

    def load_games(self):
        if not self.state.conn:
            return

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
        with self.state.conn.cursor() as cur:
            cur.execute(q)
            self.state.games = cur.fetchall()

        labels = [g[1] for g in self.state.games]
        if dpg.does_item_exist("game_combo"):
            dpg.configure_item("game_combo", items=labels)
            if labels:
                dpg.set_value("game_combo", labels[0])

        if labels:
            selected_game_id = self.state.games[0][0]
            self.state.set_status(
                "info",
                f"게임 목록 로드 완료 ({len(labels)}건)",
                f"현재 선택 game_id={selected_game_id}",
                source="데이터 적재",
                append=True,
            )
        else:
            self.state.set_status("warn", "게임 목록 로드 완료 (0건)", "표시 가능한 게임이 없습니다.", source="데이터 적재", append=True)

    def build(self, parent):
        with dpg.tab(label="데이터 적재", parent=parent):
            with dpg.group(horizontal=True):
                dpg.add_text("DSN")
                dpg.add_input_text(tag="dsn_input", width=900, default_value=self.state.default_dsn)
                dpg.add_button(label="DB 연결", callback=lambda: self.connect_db())

            with dpg.group(horizontal=True):
                dpg.add_text("JSON 경로")
                dpg.add_input_text(tag="json_data_dir_input", width=520, default_value=self.state.default_data_dir)
                dpg.add_text("스키마")
                dpg.add_input_text(tag="schema_path_input", width=260, default_value=self.state.default_schema_path)
                dpg.add_button(label="스키마 생성", callback=lambda: self.create_schema())
                dpg.add_button(label="JSON 적재", callback=lambda: self.ingest_json_to_db())

            dpg.add_text("상태", tag="status_text")
            dpg.add_input_text(tag="status_detail_text", multiline=True, readonly=True, width=-1, height=180)
