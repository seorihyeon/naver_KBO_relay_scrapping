import os, json, threading, datetime, queue, traceback, calendar
import dearpygui.dearpygui as dpg
from selenium.common.exceptions import TimeoutException
from kbo_naver_scrapper import Scrapper

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
    def run_scraper(self, start_date, end_date, save_dir, timeout, retry):
        self.stop_flag.clear()
        scr = None
        
        try:
            scr = Scrapper(wait = timeout, path = save_dir)
            self.log(f"[시작] KBO Naver Scrapper 작업 시작: {start_date} ~ {end_date} (timeout={timeout}, retry={retry})")

            cur = start_date
            total_days = (end_date - start_date).days + 1
            done_days = 0

            def day_complete():
                nonlocal done_days, cur
                done_days += 1
                self.msg_q.put(("progress", done_days / total_days))
                cur += datetime.timedelta(days = 1)

            while cur <= end_date and not self.stop_flag.is_set():
                self.log(f"{cur} 경기 정보 수집 시작...")

                urls = scr.get_game_urls(cur.year, cur.month, cur.day)

                if not urls:
                    self.log(f"{cur} 경기 없음/로딩 실패.")
                    day_complete()
                    continue

                for url in urls:
                    if self.stop_flag.is_set():
                        break
                    
                    ld = {}
                    for _ in range(int(retry)):
                        try:
                            ld, ind, rd = scr.get_game_data(url)
                            break
                        except Exception as ex:
                            self.log(f" 재시도 필요: {ex}")
                    
                    if not ld:
                        self.log(f"  경기 데이터 수집 실패: {url}")
                        continue

                    filename = url.split('/')[-1] + ".json"
                    with open(os.path.join(save_dir, filename), "w", encoding = "utf-8") as f:
                        json.dump({
                            "lineup": ld,
                            "inning_data": ind,
                            "record_data": rd
                        }, f, ensure_ascii = False, indent = 4)
                    self.log(f"  경기 데이터 저장 완료: {filename}")

                day_complete()

            if self.stop_flag.is_set():
                self.log("[중지] 작업이 중지되었습니다.")
            else:
                self.log("[완료] 모든 작업이 완료되었습니다.")
                self.msg_q.put(("progress", 1,0))

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

        period_items = ["start_date", "btn_cal_start", "btn_today_start",
                         "end_date", "btn_cal_end", "btn_today_end"]
        single_items = ["single_date", "btn_cal_single", "btn_today_single"]
        season_items = ["season_year"]

        all_items = set(period_items + single_items + season_items)
        for item in all_items:
            dpg.configure_item(item, enabled = False)

        if mode == "period":
            active = period_items
        elif mode == "single":
            active = single_items
        elif mode == "season":
            active = season_items
        else:
            active = []

        for item in active:
            dpg.configure_item(item, enabled = True)

    def start_scrape(self):
        if self.worker and self.worker.is_alive():
            self.log("이미 작업이 진행 중입니다.")
            return
        
        save_dir = dpg.get_value("save_dir")
        timeout = dpg.get_value("timeout")
        retry = dpg.get_value("retry")

        mode_key = dpg.get_value("mode")
        mode = self.modes.get(mode_key, "period")

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
                                       args = (sd, ed, save_dir, timeout, retry), daemon = True)
        self.worker.start()

    def stop_scrape(self):
        self.stop_flag.set()
        self.log("중지 요청됨. 현재 작업이 완료될 때까지 기다려주세요.")

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
                dpg.add_radio_button(items=list(self.modes.keys()), tag="mode", default_value="기간", callback=lambda s,a: self.update_mode_fields())

            with dpg.group(horizontal = True, parent = "main"):
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

            with dpg.group(horizontal=True, parent="main"):
                dpg.add_text("특정 날짜")
                dpg.add_input_text(tag="single_date", width=120, readonly=True, default_value=datetime.date.today().strftime("%Y-%m-%d"))
                dpg.add_button(label="V", width=30, tag="btn_cal_single", callback=lambda: self.open_calendar("single_date"))
                dpg.add_button(label="오늘", width=50, tag="btn_today_single", callback=lambda: self.set_today("single_date"))

            with dpg.group(horizontal=True, parent="main"):
                dpg.add_text("시즌 (2020~)")
                years = [str(y) for y in range(2020, datetime.date.today().year + 1)]
                dpg.add_combo(tag="season_year", width=120, items=years, default_value=years[-1])
            
            with dpg.group(horizontal = True, parent = "main"):
                dpg.add_text("저장 경로")
                dpg.add_input_text(tag = "save_dir", width = 460, default_value = 'games')

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
        self.disable_items = ["btn_start", "start_date", "end_date", "save_dir",
                            "timeout", "retry", "btn_cal_start", "btn_cal_end",
                            "btn_today_start", "btn_today_end", "single_date",
                            "btn_cal_single", "btn_today_single", "season_year", "mode"]

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
    print(os.path.exists("fonts/NanumGothic.ttf"))
    gui = kbo_naver_scrapper_gui()
    gui.run()