import os, json, threading, datetime, queue, traceback, calendar
import dearpygui.dearpygui as dpg
from selenium.common.exceptions import TimeoutException
from web_interface import Scrapper
import check_data

class kbo_naver_scrapper_gui:
    def __init__(self):
        # 공통 상태
        self.msg_q = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker = None

        # 달력 상태
        today = datetime.date.today()
        self.cal_year = today.year
        self.cal_month = today.month
        self.cal_target_input = None

        # 모드 상태
        self.modes = {
            "기간": "period",
            "특정 날짜": "single",
            "시즌": "season"
        }
    
    # 로그/메시지 업데이트
    def log(self, msg):
        self.msg_q.put(msg)

    def message_pump(self):
        try:
            while True:
                m = self.msg_q.get_nowait()

                if isinstance(m, tuple):
                    tag, val = m
                    if tag == "progress":
                        dpg.configure_item("progress_bar", default_value = float(val))
                    elif tag == "done":
                        for item in self.disable_items:
                            dpg.configure_item(item, enabled = True)
                        dpg.configure_item("btn_stop", enabled = False)
                        dpg.configure_item("progress_bar", overlay = "완료")
                else:
                    prev = dpg.get_value("log")
                    prev = (prev + "\n" if prev else "") + str(m)
                    dpg.set_value("log", prev)
                    dpg.set_y_scroll("log_window", 1.0)

        except queue.Empty:
            pass

    # 달력 기능
    def pick_day(self, sender, app_data, user_data):
        day = user_data
        if day is None:
            return
        
        y, m = self.cal_year, self.cal_month
        dpg.set_value(self.cal_target_input, f"{y:04d}-{m:02d}-{day:02d}")
        dpg.configure_item("calendar_modal", show = False)
    
    def render_calendar(self):
        y, m = self.cal_year, self.cal_month

        dpg.set_value("calendar_header", f"{y}년 {m:02d}")
        dpg.delete_item("calendar_grid", children_only = True)

        with dpg.group(horizontal = True, parent = "calendar_grid"):
            for wd in ["월", "화", "수", "목", "금", "토", "일"]:
                dpg.add_button(label = wd, width = 34, height = 20, enabled = False)
        
        cal = calendar.Calendar(firstweekday = 0)
        weeks = cal.monthdayscalendar(y, m)

        today = datetime.date.today()
        same_month = (y == today.year and m == today.month)

        for week in weeks:
            with dpg.group(horizontal = True, parent = "calendar_grid"):
                for day in week:
                    if day == 0:
                        dpg.add_button(label = " ", width = 34, height = 26, enabled = False)
                    else:
                        label = f"{day:2d}"
                        if same_month and day == today.day:
                            label = f"[{day:2d}]"
                        
                        is_future = datetime.date(y, m, day) > today
                        enabled = not is_future

                        dpg.add_button(label = label, width = 34, height = 26, enabled=enabled,
                                       callback = self.pick_day, user_data = day)

    def open_calendar(self, target_input):
        self.cal_target_input = target_input

        # 현재 입력된 날짜로 달력 초기화
        try:
            base = datetime.datetime.strptime(dpg.get_value(target_input), "%Y-%m-%d").date()
        except Exception:
            base = datetime.date.today()
        
        self.cal_year, self.cal_month = base.year, base.month

        self.render_calendar()
        dpg.configure_item("calendar_modal", show = True)

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
        
        # 현재 이후 달로 이동 막기
        first_of_next = datetime.date(y, m, 1)
        if first_of_next > datetime.date.today():
            return

        self.cal_year, self.cal_month = y, m
        self.render_calendar()

    def set_today(self, target_input):
        today = datetime.date.today().strftime("%Y-%m-%d")
        dpg.set_value(target_input, today)

    # 스크래핑 작업
    def run_scraper(self, mode, start_date, end_date, save_dir, timeout, retry, season_year=None):
        self.stop_flag.clear()
        scr = None

        try:
            scr = Scrapper(wait = timeout, path = save_dir)

            def fetch_and_save(url, prefix="", game_date=None):
                if self.stop_flag.is_set():
                    return False

                filename = url.split('/')[-1] + ".json"
                target_dir = save_dir
                if game_date is not None:
                    target_dir = os.path.join(save_dir, f"{game_date.year}")

                os.makedirs(target_dir, exist_ok=True)

                # 이미 저장된 파일이 있으면 무결성 체크 후 통과 시 스킵
                target_path = os.path.join(target_dir, filename)
                if os.path.exists(target_path):
                    try:
                        with open(target_path, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                        valid = check_data.validate_game_full(existing)
                        if valid.get("ok"):
                            self.log(f"{prefix}  기존 데이터 검증 통과: {filename} (스킵)")
                            return True
                        issues = valid.get("issues") or []
                        warnings = valid.get("warnings") or []
                        details = []
                        if issues:
                            details.append("이슈: " + "; ".join(issues))
                        if warnings:
                            details.append("경고: " + "; ".join(warnings))
                        detail_msg = " | ".join(details) if details else "세부 정보 없음"
                        self.log(
                            f"{prefix}  기존 데이터 이상 발견 → 재수집 진행: {filename} (상세: {detail_msg})"
                        )
                    except Exception as ex:
                        self.log(f"{prefix}  기존 데이터 로드/검증 실패({ex}) → 재수집 진행: {filename}")

                ld = {}
                for _ in range(int(retry)):
                    try:
                        ld, ind, rd = scr.get_game_data(url)
                        if ld:
                            break
                    except Exception as ex:
                        self.log(f"{prefix} 재시도 필요: {ex}")

                if not ld:
                    self.log(f"{prefix}  경기 데이터 수집 실패: {url}")
                    return False

                with open(target_path, "w", encoding = "utf-8") as f:
                    json.dump({
                        "lineup": ld,
                        "relay": ind,
                        "record": rd
                    }, f, ensure_ascii = False, indent = 4)
                self.log(f"{prefix}  경기 데이터 저장 완료: {filename}")
                return True

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

                self.log(f"[시작] 시즌 전체 수집: {season_year} (timeout={timeout}, retry={retry})")
                monthly_active = []
                total_days = 0

                for month in range(1, 13):
                    self.log(f"[시즌] {month}월 활성화 날짜 탐색 중...")
                    active_days = scr.get_activated_dates_for_month(season_year, month)

                    filtered = [d for d in active_days
                                if start_date <= datetime.date(season_year, month, d) <= end_date]
                    self.log(f"[시즌] {month}월 활성화 날짜 {len(filtered)}건 발견.")

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
                    if self.stop_flag.is_set():
                        break

                    for day in days:
                        if self.stop_flag.is_set():
                            break

                        cur = datetime.date(season_year, month, day)
                        urls = scr.get_game_urls(season_year, month, day)
                        process_day(cur, urls)
            else:
                self.log(f"[시작] KBO Naver Scrapper 작업 시작: {start_date} ~ {end_date} (timeout={timeout}, retry={retry})")

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

            if self.stop_flag.is_set():
                self.log("[중지] 작업이 중지되었습니다.")
            else:
                self.log("[완료] 모든 작업이 완료되었습니다.")
                self.msg_q.put(("progress", 1.0))

        except Exception as e:
            self.log("[오류]\n" + "".join(traceback.format_exception(type(e), e, e.__traceback__)))


        finally:
            if scr and getattr(scr, "driver", None):
                try:
                    scr.driver.quit()
                except Exception:
                    pass

            self.msg_q.put(("done", None))

    # UI 이벤트
    def update_mode_fields(self):
        mode_key = dpg.get_value("mode")
        mode = self.modes.get(mode_key, "period")

        show_map = {
            "period": ["group_period"],
            "single": ["group_single"],
            "season": ["group_season"],
        }

        for group in ["group_period", "group_single", "group_season"]:
            dpg.configure_item(group, show = False)

        for group in show_map.get(mode, []):
            dpg.configure_item(group, show = True)

    def start_scrape(self):
        if self.worker and self.worker.is_alive():
            self.log("이미 작업이 진행 중입니다.")
            return
        
        save_dir = dpg.get_value("save_dir")
        timeout = dpg.get_value("timeout")
        retry = dpg.get_value("retry")

        mode_key = dpg.get_value("mode")
        mode = self.modes.get(mode_key, "period")
        season_year = None

        try:
            if mode == "period":
                sd = datetime.datetime.strptime(dpg.get_value("start_date"), "%Y-%m-%d").date()
                ed = datetime.datetime.strptime(dpg.get_value("end_date"), "%Y-%m-%d").date()
                if ed < sd:
                    self.log("종료일은 시작일보다 이전일 수 없습니다.")
                    return
            elif mode == "single":
                target = datetime.datetime.strptime(dpg.get_value("single_date"), "%Y-%m-%d").date()
                sd = ed = target
            elif mode == "season":
                year = int(dpg.get_value("season_year"))
                if year < 2020:
                    self.log("시즌은 2020년부터 선택 가능합니다.")
                    return
                sd = datetime.date(year, 1, 1)
                ed = datetime.date(year, 12, 31)
                season_year = year
            else:
                self.log("알 수 없는 수집 모드입니다.")
                return
        except ValueError:
            self.log("날짜 형식이 올바르지 않습니다.")
            return

        os.makedirs(save_dir, exist_ok = True)

        for item in self.disable_items:
            dpg.configure_item(item, enabled = False)
        dpg.configure_item("btn_stop", enabled = True)

        dpg.configure_item("progress_bar", overlay = "진행 중...")

        self.stop_flag.clear()
        self.worker = threading.Thread(target = self.run_scraper,
                                       args = (mode, sd, ed, save_dir, timeout, retry, season_year), daemon = True)
        self.worker.start()

    def stop_scrape(self):
        self.stop_flag.set()
        self.log("중지 요청됨. 현재 작업이 완료될 때까지 기다려주세요.")

    def open_save_dir_dialog(self):
        dpg.configure_item("save_dir_dialog", show = True)

    def select_save_dir(self, sender, app_data):
        selected_dir = app_data.get("file_path_name")
        if selected_dir:
            dpg.set_value("save_dir", selected_dir)

    # UI 구성
    def build_ui(self):
        dpg.create_context()
        dpg.create_viewport(title = "KBO Naver Scrapper", width = 900, height = 600)

        with dpg.font_registry():
            with dpg.font("fonts/NanumGothic.ttf", 16) as default_font:
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Korean)
            

        with dpg.window(tag="main", label = "KBO Naver Scrapper", width = 900, height = 600):
            dpg.bind_font(default_font)
            dpg.add_text("KBO Naver Scrapper", bullet = True, color = (255, 0, 0), wrap = 800, parent="main")
            dpg.add_spacer(height=10, parent="main")

            with dpg.group(horizontal=True, parent="main"):
                dpg.add_text("수집 모드")
                dpg.add_radio_button(items=list(self.modes.keys()), tag="mode", default_value="기간",
                                     callback=lambda s, a: self.update_mode_fields(), horizontal=True)

            with dpg.group(horizontal = True, parent = "main", tag="group_period"):
                dpg.add_text("시작일")
                dpg.add_input_text(tag = "start_date", width = 120,
                                   readonly = True, default_value = datetime.date.today().strftime("%Y-%m-%d"))
                dpg.add_button(label = "V", width = 30,
                               tag = "btn_cal_start", callback = lambda: self.open_calendar("start_date"))
                dpg.add_button(label = "오늘", width = 50,
                               tag = "btn_today_start", callback = lambda: self.set_today("start_date"))
                
                dpg.add_spacer(width = 10)

                dpg.add_text("종료일")
                dpg.add_input_text(tag = "end_date", width = 120,
                                   readonly = True, default_value = datetime.date.today().strftime("%Y-%m-%d"))
                dpg.add_button(label = "V", width = 30,
                               tag = "btn_cal_end", callback = lambda: self.open_calendar("end_date"))
                dpg.add_button(label = "오늘", width = 50,
                               tag = "btn_today_end", callback = lambda: self.set_today("end_date"))

            with dpg.group(horizontal=True, parent="main", tag="group_single"):
                dpg.add_text("특정 날짜")
                dpg.add_input_text(tag="single_date", width=120, readonly=True, default_value=datetime.date.today().strftime("%Y-%m-%d"))
                dpg.add_button(label="V", width=30, tag="btn_cal_single", callback=lambda: self.open_calendar("single_date"))
                dpg.add_button(label="오늘", width=50, tag="btn_today_single", callback=lambda: self.set_today("single_date"))

            with dpg.group(horizontal=True, parent="main", tag="group_season"):
                dpg.add_text("시즌 (2020~)")
                years = [str(y) for y in range(2020, datetime.date.today().year + 1)]
                dpg.add_combo(tag="season_year", width=120, items=years, default_value=years[-1])
            
            with dpg.group(horizontal = True, parent = "main"):
                dpg.add_text("저장 경로")
                dpg.add_input_text(tag = "save_dir", width = 400, default_value = 'games')
                dpg.add_button(label = "폴더 선택", width = 80,
                               tag = "btn_save_dir", callback = lambda: self.open_save_dir_dialog())

            with dpg.group(horizontal=True):
                dpg.add_text("타임아웃(초)")
                dpg.add_input_int(tag="timeout", width=80, default_value=8, min_value=2, max_value=60)
                dpg.add_text("재시도")
                dpg.add_input_int(tag="retry", width=80, default_value=3, min_value=1, max_value=10)

            with dpg.group(horizontal = True, parent = "main"):
                dpg.add_button(tag = "btn_start", label = "시작", width = 120, callback = lambda s, a: self.start_scrape())
                dpg.add_button(tag = "btn_stop", label = "중지", width = 120, callback = lambda s, a: self.stop_scrape())

            dpg.add_progress_bar(tag = "progress_bar", width = -1, default_value = 0.0, overlay = "대기 중", parent = "main")

            dpg.add_text("로그")
            with dpg.child_window(tag = "log_window", autosize_x = True, height = 320):
                dpg.add_input_text(tag = "log", multiline = True, readonly = True, width = -1, height = -1)
            
        # 비활성화 대상 일괄 지정
        self.disable_items = [
            "btn_start", "start_date", "end_date", "save_dir",
            "timeout", "retry", "btn_cal_start", "btn_cal_end",
            "btn_today_start", "btn_today_end", "single_date",
            "btn_cal_single", "btn_today_single", "season_year", "mode",
            "btn_save_dir"
        ]

        with dpg.file_dialog(directory_selector = True, show = False, callback = self.select_save_dir,
                             tag = "save_dir_dialog", width = 640, height = 480):
            dpg.add_file_extension(".*")

        # 달력 UI 구성
        with dpg.window(tag = "calendar_modal",
                        label = "날짜 선택", modal = True, show = False,
                        no_move = False, no_resize = True,
                        width = 360, height = 340):
            with dpg.group(horizontal = True):
                dpg.add_button(label = "<", width = 30, callback = lambda s,a: self.calendar_prev())
                dpg.add_spacer(width = 6)
                dpg.add_text("", tag = "calendar_header")
                dpg.add_spacer(width = 6)
                dpg.add_button(label = ">", width = 30, callback = lambda s,a: self.calendar_next())
                
            dpg.add_separator()
            with dpg.child_window(tag = "calendar_grid", autosize_x = True, autosize_y = True):
                pass

            dpg.add_separator()
            dpg.add_button(label = "닫기", width = 60, callback = lambda: dpg.configure_item("calendar_modal", show = False))
        
        # 초기 렌더
        self.update_mode_fields()
        self.render_calendar()

        # UI 실행
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main", True)
        # 렌더 루프
        while dpg.is_dearpygui_running():
            dpg.render_dearpygui_frame()
            self.message_pump()

        dpg.destroy_context()

    def run(self):
        self.build_ui()

if __name__ == "__main__":
    gui = kbo_naver_scrapper_gui()
    gui.run()
