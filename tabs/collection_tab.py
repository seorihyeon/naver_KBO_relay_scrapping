from __future__ import annotations

import subprocess
from pathlib import Path

import dearpygui.dearpygui as dpg

from .shared_state import AppState


class CollectionTab:
    def __init__(self, state: AppState):
        self.state = state

    def launch_collection_gui(self):
        script_path = Path(__file__).resolve().parents[1] / "graphic_interface.py"
        if not script_path.exists():
            self.state.set_status("수집 GUI 실행 실패", f"파일 없음: {script_path}")
            return
        try:
            subprocess.Popen(["python", str(script_path)])
            self.state.set_status("수집 GUI 실행", "별도 창에서 수집 GUI를 실행했습니다.", append=True)
        except Exception as e:
            self.state.set_status("수집 GUI 실행 실패", str(e), append=True)

    def build(self, parent):
        with dpg.tab(label="데이터 수집", parent=parent):
            dpg.add_text("Naver 수집 GUI를 실행하여 JSON 데이터를 생성합니다.")
            dpg.add_button(label="수집 GUI 실행", callback=lambda: self.launch_collection_gui())
            dpg.add_spacer(height=8)
            dpg.add_text("수집 결과(JSON)는 '데이터 적재' 탭에서 DB로 적재하세요.", color=(170, 170, 170))
