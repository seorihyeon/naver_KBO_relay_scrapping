from __future__ import annotations

import calendar
import datetime
import json
import os
import queue
import threading
import traceback

import dearpygui.dearpygui as dpg

import check_data
from web_interface import Scrapper
from .shared_state import AppState


class CollectionTab:
    def __init__(self, state: AppState):
        self.state = state
        self.msg_q = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker = None

        today = datetime.date.today()
        self.cal_year = today.year
        self.cal_month = today.month
        self.cal_target_input = None

        self.modes = {"기간": "period", "특정 날짜": "single", "시즌": "season"}

    def _t(self, name: str) -> str:
        return f"col_{name}"

    def log(self, msg):
        self.msg_q.put(msg)

    def _channel_from_message(self, message: str) -> str:
        txt = str(message)
        if "[오류]" in txt or "실패" in txt or "예외" in txt:
            return "error"
        if "[중지]" in txt or "없습니다" in txt or "유효하지" in txt:
            return "warn"
        return "info"

    def debug_log(self, debug_log_path, msg):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(debug_log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")

    def message_pump(self):
        try:
            while True:
                m = self.msg_q.get_nowait()
                if isinstance(m, tuple):
                    tag, val = m
                    if tag == "progress":
                        dpg.configure_item(self._t("progress_bar"), default_value=float(val))
                        self.state.set_status("info", "데이터 수집 진행", f"진행률: {int(float(val) * 100)}%", source="데이터 수집")
                    elif tag == "done":
                        for item in self.disable_items:
                            dpg.configure_item(item, enabled=True)
                        dpg.configure_item(self._t("btn_stop"), enabled=False)
                        dpg.configure_item(self._t("progress_bar"), overlay="완료")
                else:
                    prev = dpg.get_value(self._t("log"))
                    prev = (prev + "\n" if prev else "") + str(m)
                    dpg.set_value(self._t("log"), prev)
                    dpg.set_y_scroll(self._t("log_window"), 1.0)
                    channel = self._channel_from_message(str(m))
                    self.state.set_status(channel, "데이터 수집 이벤트", str(m), source="데이터 수집")
        except queue.Empty:
            pass

    def pick_day(self, sender, app_data, user_data):
        day = user_data
        if day is None:
            return
        dpg.set_value(self.cal_target_input, f"{self.cal_year:04d}-{self.cal_month:02d}-{day:02d}")
        dpg.configure_item(self._t("calendar_modal"), show=False)

    def render_calendar(self):
        y, m = self.cal_year, self.cal_month
        dpg.set_value(self._t("calendar_header"), f"{y}년 {m:02d}")
        dpg.delete_item(self._t("calendar_grid"), children_only=True)

        with dpg.group(horizontal=True, parent=self._t("calendar_grid")):
            for wd in ["월", "화", "수", "목", "금", "토", "일"]:
                dpg.add_button(label=wd, width=34, height=20, enabled=False)

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(y, m)
        today = datetime.date.today()
        same_month = y == today.year and m == today.month

        for week in weeks:
            with dpg.group(horizontal=True, parent=self._t("calendar_grid")):
                for day in week:
                    if day == 0:
                        dpg.add_button(label=" ", width=34, height=26, enabled=False)
                        continue
                    label = f"[{day:2d}]" if same_month and day == today.day else f"{day:2d}"
                    is_future = datetime.date(y, m, day) > today
                    dpg.add_button(label=label, width=34, height=26, enabled=not is_future, callback=self.pick_day, user_data=day)

    def open_calendar(self, target_input):
        self.cal_target_input = target_input
        try:
            base = datetime.datetime.strptime(dpg.get_value(target_input), "%Y-%m-%d").date()
        except Exception:
            base = datetime.date.today()
        self.cal_year, self.cal_month = base.year, base.month
        self.render_calendar()
        dpg.configure_item(self._t("calendar_modal"), show=True)

    def calendar_prev(self):
        self.cal_month -= 1
        if self.cal_month == 0:
            self.cal_month = 12
            self.cal_year -= 1
        self.render_calendar()

    def calendar_next(self):
        y, m = self.cal_year, self.cal_month
        m += 1
        if m == 13:
            y, m = y + 1, 1
        if datetime.date(y, m, 1) > datetime.date.today():
            return
        self.cal_year, self.cal_month = y, m
        self.render_calendar()

    def set_today(self, target_input):
        dpg.set_value(target_input, datetime.date.today().strftime("%Y-%m-%d"))

    def update_mode_fields(self):
        mode = self.modes.get(dpg.get_value(self._t("mode")), "period")
        show_map = {"period": [self._t("group_period")], "single": [self._t("group_single")], "season": [self._t("group_season")]}
        for group in [self._t("group_period"), self._t("group_single"), self._t("group_season")]:
            dpg.configure_item(group, show=False)
        for group in show_map.get(mode, []):
            dpg.configure_item(group, show=True)

    def run_scraper(self, mode, start_date, end_date, save_dir, timeout, retry, season_year=None):
        self.stop_flag.clear()
        scr = None
        debug_log_path = os.path.join(save_dir, f"scrape_debug_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        try:
            scr = Scrapper(wait=timeout, path=save_dir)
            self.log(f"[디버그] 로그 파일: {debug_log_path}")

            def fetch_and_save(url, prefix="", game_date=None):
                if self.stop_flag.is_set():
                    return False
                filename = url.split("/")[-1] + ".json"
                target_dir = os.path.join(save_dir, f"{game_date.year}") if game_date else save_dir
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, filename)
                if os.path.exists(target_path):
                    try:
                        with open(target_path, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                        if check_data.validate_game(existing).get("ok"):
                            self.log(f"{prefix}  기존 데이터 검증 통과: {filename} (스킵)")
                            return True
                    except Exception:
                        pass

                max_attempts = max(1, int(retry))
                ld = ind = rd = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        self.log(f"{prefix}    [{attempt}/{max_attempts}] 페이지 접속 및 데이터 수집 중...")
                        ld, ind, rd = scr.get_game_data(url)
                        if not (ld and ind and rd):
                            raise ValueError("lineup/relay/record 중 일부가 비어 있습니다.")
                        candidate_data = {"lineup": ld, "relay": ind, "record": rd}
                        validation = check_data.validate_game(candidate_data)
                        if validation.get("ok"):
                            with open(target_path, "w", encoding="utf-8") as f:
                                json.dump(candidate_data, f, ensure_ascii=False, indent=4)
                            self.log(f"{prefix}  검증 통과 및 저장 완료: {filename}")
                            return True
                    except Exception as ex:
                        self.debug_log(debug_log_path, f"{filename} | {type(ex).__name__}: {ex}\n{traceback.format_exc()}")
                self.log(f"{prefix}  {max_attempts}회 이상 실패로 건너뜀: {filename}")
                return False

            def make_process_day(day_complete, prefix=""):
                def _process(cur_date, urls):
                    if self.stop_flag.is_set():
                        return
                    self.log(f"{prefix}{cur_date} 경기 정보 수집 시작...")
                    if urls == -1:
                        self.log(f"{prefix}{cur_date} KBO 일정이 없습니다.")
                        day_complete()
                        return
                    if not urls:
                        self.log(f"{prefix}{cur_date} 경기 없음/로딩 실패.")
                        day_complete()
                        return
                    for url in urls:
                        if self.stop_flag.is_set():
                            break
                        fetch_and_save(url, prefix, cur_date)
                    if not self.stop_flag.is_set():
                        day_complete()

                return _process

            if mode == "season" and season_year is not None:
                monthly_active = []
                total_days = 0
                for month in range(1, 13):
                    active_days = scr.get_activated_dates_for_month(season_year, month)
                    filtered = [d for d in active_days if start_date <= datetime.date(season_year, month, d) <= end_date]
                    total_days += len(filtered)
                    monthly_active.append((month, filtered))
                if total_days == 0:
                    self.log("활성화된 일정이 없습니다.")
                    self.msg_q.put(("progress", 1.0))
                    return
                done_days = 0

                def day_complete():
                    nonlocal done_days
                    done_days += 1
                    self.msg_q.put(("progress", done_days / total_days))

                process_day = make_process_day(day_complete, prefix="[시즌] ")
                for month, days in monthly_active:
                    for day in days:
                        if self.stop_flag.is_set():
                            break
                        cur = datetime.date(season_year, month, day)
                        urls = scr.get_game_urls(season_year, month, day)
                        process_day(cur, urls)
            else:
                active_entries = list(scr.iter_active_date_urls(start_date, end_date))
                total_days = len(active_entries)
                if total_days == 0:
                    self.log("활성화된 일정이 없습니다.")
                    self.msg_q.put(("progress", 1.0))
                    return
                done_days = 0

                def day_complete():
                    nonlocal done_days
                    done_days += 1
                    self.msg_q.put(("progress", done_days / total_days))

                process_day = make_process_day(day_complete)
                for cur, urls in active_entries:
                    if self.stop_flag.is_set():
                        break
                    process_day(cur, urls)

            self.log("[중지] 작업이 중지되었습니다." if self.stop_flag.is_set() else "[완료] 모든 작업이 완료되었습니다.")
            if not self.stop_flag.is_set():
                self.msg_q.put(("progress", 1.0))
        except Exception as e:
            self.log("[오류]\n" + "".join(traceback.format_exception(type(e), e, e.__traceback__)))
            self.state.set_status("error", "데이터 수집 실패", "수집 중 예외가 발생했습니다.", debug_detail=traceback.format_exc(), source="데이터 수집")
        finally:
            if scr and getattr(scr, "driver", None):
                try:
                    scr.driver.quit()
                except Exception:
                    pass
            self.msg_q.put(("done", None))

    def start_scrape(self):
        if self.worker and self.worker.is_alive():
            self.log("이미 작업이 진행 중입니다.")
            return

        save_dir = dpg.get_value(self._t("save_dir"))
        timeout = dpg.get_value(self._t("timeout"))
        retry = dpg.get_value(self._t("retry"))
        mode = self.modes.get(dpg.get_value(self._t("mode")), "period")
        season_year = None

        try:
            if mode == "period":
                sd = datetime.datetime.strptime(dpg.get_value(self._t("start_date")), "%Y-%m-%d").date()
                ed = datetime.datetime.strptime(dpg.get_value(self._t("end_date")), "%Y-%m-%d").date()
                if ed < sd:
                    self.log("종료일은 시작일보다 이전일 수 없습니다.")
                    self.state.set_status("warn", "입력값 확인", "종료일은 시작일보다 이전일 수 없습니다.", source="데이터 수집")
                    return
            elif mode == "single":
                sd = ed = datetime.datetime.strptime(dpg.get_value(self._t("single_date")), "%Y-%m-%d").date()
            else:
                year = int(dpg.get_value(self._t("season_year")))
                if year < 2020:
                    self.log("시즌은 2020년부터 선택 가능합니다.")
                    self.state.set_status("warn", "입력값 확인", "시즌은 2020년부터 선택 가능합니다.", source="데이터 수집")
                    return
                sd = datetime.date(year, 1, 1)
                ed = datetime.date(year, 12, 31)
                season_year = year
        except ValueError:
            self.log("날짜 형식이 올바르지 않습니다.")
            self.state.set_status("warn", "입력값 확인", "날짜 형식이 올바르지 않습니다.", source="데이터 수집")
            return

        os.makedirs(save_dir, exist_ok=True)
        for item in self.disable_items:
            dpg.configure_item(item, enabled=False)
        dpg.configure_item(self._t("btn_stop"), enabled=True)
        dpg.configure_item(self._t("progress_bar"), overlay="진행 중...")

        self.stop_flag.clear()
        self.worker = threading.Thread(target=self.run_scraper, args=(mode, sd, ed, save_dir, timeout, retry, season_year), daemon=True)
        self.worker.start()
        self.state.set_status("info", "데이터 수집 시작", f"모드={mode}, 저장 경로={save_dir}", source="데이터 수집")

    def stop_scrape(self):
        self.stop_flag.set()
        self.log("중지 요청됨. 현재 작업이 완료될 때까지 기다려주세요.")
        self.state.set_status("warn", "데이터 수집 중지 요청", "현재 작업이 완료된 뒤 중지됩니다.", source="데이터 수집")

    def open_save_dir_dialog(self):
        dpg.configure_item(self._t("save_dir_dialog"), show=True)

    def select_save_dir(self, sender, app_data):
        selected_dir = app_data.get("file_path_name")
        if selected_dir:
            dpg.set_value(self._t("save_dir"), selected_dir)

    def build(self, parent):
        today = datetime.date.today().strftime("%Y-%m-%d")
        with dpg.tab(label="데이터 수집", parent=parent):
            dpg.add_text("KBO Naver Scrapper", bullet=True, color=(255, 0, 0), wrap=800)
            with dpg.group(horizontal=True):
                dpg.add_text("수집 모드")
                dpg.add_radio_button(items=list(self.modes.keys()), tag=self._t("mode"), default_value="기간", callback=lambda: self.update_mode_fields(), horizontal=True)

            with dpg.group(horizontal=True, tag=self._t("group_period")):
                dpg.add_text("시작일")
                dpg.add_input_text(tag=self._t("start_date"), width=120, readonly=True, default_value=today)
                dpg.add_button(label="V", width=30, tag=self._t("btn_cal_start"), callback=lambda: self.open_calendar(self._t("start_date")))
                dpg.add_button(label="오늘", width=50, tag=self._t("btn_today_start"), callback=lambda: self.set_today(self._t("start_date")))
                dpg.add_text("종료일")
                dpg.add_input_text(tag=self._t("end_date"), width=120, readonly=True, default_value=today)
                dpg.add_button(label="V", width=30, tag=self._t("btn_cal_end"), callback=lambda: self.open_calendar(self._t("end_date")))
                dpg.add_button(label="오늘", width=50, tag=self._t("btn_today_end"), callback=lambda: self.set_today(self._t("end_date")))

            with dpg.group(horizontal=True, tag=self._t("group_single")):
                dpg.add_text("특정 날짜")
                dpg.add_input_text(tag=self._t("single_date"), width=120, readonly=True, default_value=today)
                dpg.add_button(label="V", width=30, tag=self._t("btn_cal_single"), callback=lambda: self.open_calendar(self._t("single_date")))
                dpg.add_button(label="오늘", width=50, tag=self._t("btn_today_single"), callback=lambda: self.set_today(self._t("single_date")))

            with dpg.group(horizontal=True, tag=self._t("group_season")):
                dpg.add_text("시즌 (2020~)")
                years = [str(y) for y in range(2020, datetime.date.today().year + 1)]
                dpg.add_combo(tag=self._t("season_year"), width=120, items=years, default_value=years[-1])

            with dpg.group(horizontal=True):
                dpg.add_text("저장 경로")
                dpg.add_input_text(tag=self._t("save_dir"), width=400, default_value="games")
                dpg.add_button(label="폴더 선택", width=80, tag=self._t("btn_save_dir"), callback=lambda: self.open_save_dir_dialog())

            with dpg.group(horizontal=True):
                dpg.add_text("타임아웃(초)")
                dpg.add_input_int(tag=self._t("timeout"), width=80, default_value=8, min_value=2, max_value=60)
                dpg.add_text("최대 실패 횟수")
                dpg.add_input_int(tag=self._t("retry"), width=120, default_value=3, min_value=1, max_value=20)

            with dpg.group(horizontal=True):
                dpg.add_button(tag=self._t("btn_start"), label="시작", width=120, callback=lambda: self.start_scrape())
                dpg.add_button(tag=self._t("btn_stop"), label="중지", width=120, callback=lambda: self.stop_scrape(), enabled=False)

            dpg.add_progress_bar(tag=self._t("progress_bar"), width=-1, default_value=0.0, overlay="대기 중")
            dpg.add_text("로그")
            with dpg.child_window(tag=self._t("log_window"), autosize_x=True, height=250):
                dpg.add_input_text(tag=self._t("log"), multiline=True, readonly=True, width=-1, height=-1)

            with dpg.file_dialog(directory_selector=True, show=False, callback=self.select_save_dir, tag=self._t("save_dir_dialog"), width=640, height=480):
                dpg.add_file_extension(".*")

            with dpg.window(tag=self._t("calendar_modal"), label="날짜 선택", modal=True, show=False, no_move=False, no_resize=True, width=360, height=340):
                with dpg.group(horizontal=True):
                    dpg.add_button(label="<", width=30, callback=lambda: self.calendar_prev())
                    dpg.add_text("", tag=self._t("calendar_header"))
                    dpg.add_button(label=">", width=30, callback=lambda: self.calendar_next())
                dpg.add_separator()
                with dpg.child_window(tag=self._t("calendar_grid"), autosize_x=True, autosize_y=True):
                    pass
                dpg.add_separator()
                dpg.add_button(label="닫기", width=60, callback=lambda: dpg.configure_item(self._t("calendar_modal"), show=False))

        self.disable_items = [
            self._t("btn_start"), self._t("start_date"), self._t("end_date"), self._t("save_dir"),
            self._t("timeout"), self._t("retry"), self._t("btn_cal_start"), self._t("btn_cal_end"),
            self._t("btn_today_start"), self._t("btn_today_end"), self._t("single_date"),
            self._t("btn_cal_single"), self._t("btn_today_single"), self._t("season_year"), self._t("mode"),
            self._t("btn_save_dir"),
        ]
        self.update_mode_fields()
        self.render_calendar()
