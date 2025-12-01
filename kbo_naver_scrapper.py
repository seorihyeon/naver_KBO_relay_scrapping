import datetime
import json
import time
import os
import re
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import JavascriptException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support.select import Select

# Selenium을 이용해 스크래핑을 수행하는 클래스
class Scrapper:
    def __init__(self, wait = 10, path = 'games'):
        edge_options = EdgeOptions()
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--headless=new")
        edge_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                                  'Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0')
        sw_options = {'exclude_hosts': ['mtalk.google.com', 'fcm.googleapis.com', 'clients.google.com', 'clients2.google.com']}
        self.driver = webdriver.Edge(options=edge_options, seleniumwire_options=sw_options)

        self.driver.implicitly_wait(wait)
        self.DEFAULT_TIMEOUT = wait

        try:
            if not os.path.exists('./' + path):
                os.makedirs('./' + path)
        except OSError as e:
            print(f"Error creating directory: {e}")
        self.path = './' + path + '/'

        self.driver.get("https://m.sports.naver.com/kbaseball/schedule/index")

    # 버튼 클릭
    def click(self, button):
        WebDriverWait(self.driver, getattr(self, 'DEFAULT_TIMEOUT', 10)).until(EC.element_to_be_clickable(button))
        ActionChains(self.driver).move_to_element(button).click(button).perform()

    # CSS_SELECTOR로 요소 찾기
    def find_element_CSSS(self, parent, query):
        return parent.find_element(By.CSS_SELECTOR, query)
    
    # 대기용 함수
    def wait_present(self, css, timeout = None, root = None, min_count = 1, visible = True, fresh = True):
        """
        css: 찾을 CSS 셀렉터(하나)
        root: 검색 범위 (None=driver, WebElement, 또는 CSS 문자열)
        min_count: 최소 몇 개 이상 나타나야 통과할지
        visible: 보이는 요소만 인정할지
        fresh: 통과 직후 한 번 더 재조회해서 최신 핸들을 반환할지
        반환: 요소 1개(min_count==1) 또는 요소 리스트
        """
        t = timeout or getattr(self, 'DEFAULT_TIMEOUT', 10)

        def _get_container():
            if root is None:
                return self.driver
            if isinstance(root, str):
                return self.driver.find_element(By.CSS_SELECTOR, root)
            return root # WebElement
        
        def _probe(_):
            try:
                container = _get_container()
                elems = container.find_elements(By.CSS_SELECTOR, css)
                if visible:
                    elems = [e for e in elems if e.is_displayed()]
                return elems if len(elems) >= min_count else False
            except StaleElementReferenceException:
                return False
            
        elems = WebDriverWait(self.driver, t).until(_probe)

        if fresh:
            try:
                container = _get_container()
                elems = container.find_elements(By.CSS_SELECTOR, css)
                if visible:
                    elems = [e for e in elems if e.is_displayed()]
            except Exception:
                pass
        
        return elems[0] if min_count == 1 else elems

    def wait_all_present(self, css, timeout = None):
        t = timeout or getattr(self, 'DEFAULT_TIMEOUT', 10)
        return WebDriverWait(self.driver, t).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, css)))
    
    def wait_clickable_css(self, css, timeout = None):
        t = timeout or getattr(self, 'DEFAULT_TIMEOUT', 10)
        return WebDriverWait(self.driver, t).until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
    
    def wait_for_request(self, keyword, key_attr, timeout = None, retries = 3, refresh = True, clear_before = True, ready_css = None):
        t = timeout or getattr(self, 'DEFAULT_TIMEOUT', 10)
        def _predicate(_):
            for req in reversed(self.driver.requests):
                try:
                    if getattr(req, "response", None) and (keyword in getattr(req, key_attr, "")):
                        return req
                except Exception:
                    continue
            return False
        
        attempt = 0
        while True:
            try:
                return WebDriverWait(self.driver,t).until(_predicate)
            except TimeoutException:
                if attempt >= retries:
                    raise
                attempt += 1

                if clear_before:
                    try:
                        del self.driver.requests
                    except Exception:
                        pass

                if refresh:
                    try:
                        self.driver.refresh()
                    except Exception:
                        pass

                if ready_css:
                    try:
                        self.wait_present(ready_css)
                    except Exception:
                        pass
                
    # 경기 페이지 내에서 탭 이동 버튼 찾기
    def find_tab_button(self, timeout = None, retry = 3):
        t = timeout or getattr(self, 'DEFAULT_TIMEOUT', 10)

        tab_css = 'ul[class^="GameTab_tab_list"]'
        self.wait_present(tab_css, visible=True)
        
        for _ in range(retry):
            try:
                tab_list = self.find_element_CSSS(self.driver, tab_css)
                tab_buttons = tab_list.find_elements(By.CSS_SELECTOR, 'button')
        
                tab_button_dict = dict()
                
                for btn in tab_buttons:
                    text = self.find_element_CSSS(btn, 'span[class^="GameTab_text"]').text
                    tab_button_dict[text] = btn
                
                if tab_button_dict:
                    return tab_button_dict
            except StaleElementReferenceException:
                raise
        return {}

    # 중계 페이지 내에서 이닝 버튼 찾기
    def find_inning_button(self):
        main_section = self.find_element_CSSS(self.driver, 'div[class^="Home_main_section"]')
        game_panel = self.find_element_CSSS(main_section, 'section[class^="Home_game_panel"]')
        tab_list = self.find_element_CSSS(game_panel, 'div[class^="SetTab_tab_list"]')
        inning_buttons = tab_list.find_elements(By.CSS_SELECTOR, 'button')

        inning_buttons[:] = [btn for btn in inning_buttons if btn.is_enabled()]

        return inning_buttons
    
    # 이닝 데이터 전처리
    def preprocess_inning_data(self, inning_data):
        processed_data = inning_data["result"]["textRelayData"]["textRelays"]

        return processed_data
    
    # HTML request를 통해 이닝 데이터 취득
    def get_inning_data(self, relay_btn):
        self.click(relay_btn)
        self.wait_all_present('section[class^="Home_game_panel"] div[class^="SetTab_tab_list"] button')
        inning_buttons = self.find_inning_button()
        inning_data = []
        for btn in inning_buttons:
            del self.driver.requests
            self.click(btn)
            req = self.wait_for_request('inning', 'querystring')
            body = req.response.body.decode('utf-8', 'ignore')
            inning_data.append(self.preprocess_inning_data(json.loads(body)) if body else [])
        return inning_data
    
    # 라인업 데이터 전처리
    def preprocess_lineup_data(self, lineup_data):
        preview_data = lineup_data["result"]["previewData"]
        away_lineup = preview_data["awayTeamLineUp"]
        home_lineup = preview_data["homeTeamLineUp"]

        processed_data = dict(game_info = preview_data["gameInfo"],
                              home_starter = home_lineup["fullLineUp"],
                              home_bullpen = home_lineup["pitcherBullpen"],
                              home_candidate = home_lineup["batterCandidate"],
                              away_starter = away_lineup["fullLineUp"],
                              away_bullpen = away_lineup["pitcherBullpen"],
                              away_candidate = away_lineup["batterCandidate"])
        
        return processed_data

    # HTML request를 통해 선수 라인업 데이터 취득
    def get_lineup_data(self, lineup_btn):
        del self.driver.requests
        self.click(lineup_btn)
        req = self.wait_for_request('preview', 'path')
        body = req.response.body.decode('utf-8', 'ignore')
        lineup_data = self.preprocess_lineup_data(json.loads(body)) if body else {}
        
        return lineup_data
    
    # 경기 기록 데이터 전처리
    def preprocess_record_data(self, record_data):
        record = record_data["result"]["recordData"]

        processed_data = dict(pitcher = record["pitchersBoxscore"],
                              batter = record["battersBoxscore"])
        
        return processed_data

    # HTML request를 통해 경기 기록 데이터 취득
    def get_record_data(self, result_btn):
        del self.driver.requests
        self.click(result_btn)
        req = self.wait_for_request('record', 'path')
        body = req.response.body.decode('utf-8', 'ignore')
        record_data = self.preprocess_record_data(json.loads(body)) if body else {}
        
        return record_data

    # 경기 중계 url을 받아 필요한 데이터를 긁어서 반환
    def get_game_data(self, game_url):
        self.driver.get(game_url)
        tab_buttons = self.find_tab_button()
        lineup_data = self.get_lineup_data(tab_buttons["라인업"])
        inning_data = self.get_inning_data(tab_buttons["중계"])
        record_data = self.get_record_data(tab_buttons["기록"])

        return lineup_data, inning_data, record_data
        
    # 경기/일정 페이지에서 달력 버튼 찾아 반환
    def find_calender_button(self):
        main_section = self.find_element_CSSS(self.driver, 'div[class^="Home_container"]')
        date_area = self.find_element_CSSS(main_section, 'div[class^="CalendarDate_schedule_date_area"]')
        calender = self.find_element_CSSS(date_area, 'div[class^="CalendarDate_calendar_wrap"]')
        calender_button = self.find_element_CSSS(calender, 'button')

        return calender_button
    
    # 달력 html 코드 획득
    def get_calender_html(self):
        main_section = self.find_element_CSSS(self.driver, 'div[class^="Home_container"]')
        date_area = self.find_element_CSSS(main_section, 'div[class^="CalendarDate_schedule_date_area"]')
        calender = self.find_element_CSSS(date_area, 'div[class^="CalendarDate_calendar_wrap"]')
        calender_layer = self.find_element_CSSS(calender, 'div[class^="Calendar_layer_content"]')

        return calender_layer
    
    # 달력에서 년도 선택
    def select_year(self, year):
        if not isinstance(year, int):
            raise ValueError('연도가 정수가 아닙니다.')
        calender_html = self.get_calender_html()
        try:
            self.wait_present('select[class^="Calendar_select"]', visible = True)
            select_year = Select(self.find_element_CSSS(calender_html, 'select[class^="Calendar_select"]'))
        except NoSuchElementException:
            raise ValueError('데이터가 제공되는 연도가 아닙니다.')
        select_year.select_by_value(str(year))

    # 연도의 첫 번째 달로 이동
    def goto_first_month(self):
        calender_html = self.get_calender_html()
        while True:
            current_month_element = self.find_element_CSSS(calender_html, 'div[class^="Calendar_current"]')
            prev_text = current_month_element.text
            self.click(self.find_element_CSSS(calender_html, 'button[class^="Calendar_button_prev"]'))
            WebDriverWait(self.driver, getattr(self, 'DEFAULT_TIMEOUT', 10)).until(
                lambda d: self.find_element_CSSS(self.get_calender_html(), 'div[class^="Calendar_current"]').text != prev_text
            )
            calender_html = self.get_calender_html()
            current_month_element = self.find_element_CSSS(calender_html, 'div[class^="Calendar_current"]')
            if int(current_month_element.text[:-1]) == 12:
                prev_text = current_month_element.text
                self.click(self.find_element_CSSS(calender_html, 'button[class^="Calendar_button_next"]'))
                break
        
        WebDriverWait(self.driver, getattr(self, 'DEFAULT_TIMEOUT', 10)).until(
                lambda d: self.find_element_CSSS(self.get_calender_html(), 'div[class^="Calendar_current"]').text != prev_text
            )
        current_month_element = self.find_element_CSSS(calender_html, 'div[class^="Calendar_current"]')
        return int(current_month_element.text[:-1])
    
    # 달의 첫번째 일자 버튼 클릭
    def click_first_date(self):
        calender_html = self.get_calender_html()
        date_buttons = calender_html.find_elements(By.CSS_SELECTOR, 'button[class^="Calendar_button_date"]')
        for btn in date_buttons:
            if btn.is_enabled():
                self.click(btn)
                break

    # 활성화 된 날짜 목록 반환
    def get_activated_dates(self):
        self.wait_present('div[class^="CalendarDate_calendar_tab_wrap"]')

        css_tree = 'div[class^="Home_container"] div[class^="CalendarDate_schedule_date_area"] div[class^="CalendarDate_calendar_tab_wrap"]'
        date_tab = self.find_element_CSSS(self.driver, css_tree)
        date_buttons_em = date_tab.find_elements(By.CSS_SELECTOR, 'button:not([disabled]) em')

        activated_dates = []
        for em in date_buttons_em:
            txt = em.get_attribute('innerHTML')
            activated_dates.append(int(txt))

        return activated_dates

    # 일자 지정하여 일정 주소 반환
    def get_schedule_page_url(self, year, month, date):
        base = "https://m.sports.naver.com/kbaseball/schedule/index?date="
        date = datetime.date(year, month, date).strftime("%Y-%m-%d")
        
        return base + date
    
    # 특정 일자에서 경기 페이지 주소 얻기
    def get_game_urls(self, year, month, date, soft_timeout = 8):
        """
        해당 (year, month, day)의 경기 URL 리스트를 반환.
        - 경기 목록이 뜨면 즉시 URL 반환
        - 로딩이 계속되면 [] 반환
        """
        self.driver.get(self.get_schedule_page_url(year,month,date))
        try:
            self.wait_all_present('div[class^="ScheduleAllType_match_list_group"]')
        except TimeoutException:
            # 경기 없음 or 무한 로딩 -> 건너뜀
            return []
        main_section = self.find_element_CSSS(self.driver, 'div[class^="Home_container"]')
        match_group = main_section.find_elements(By.CSS_SELECTOR, 'div[class^="ScheduleAllType_match_list_group"]')

        for grp in match_group:
            a = self.find_element_CSSS(grp, 'div[class^="ScheduleAllType_title_area"]')
            em = self.find_element_CSSS(a, 'em')
            if em.text == "KBO리그":
                target_group = grp
                break
            else:
                target_group = None
        
        if target_group is None:
            return -1

        match_urls = []    
        matches = target_group.find_elements(By.CSS_SELECTOR, 'li[class^="MatchBox_match_item"]')
        for match in matches:
            match_status = self.find_element_CSSS(match, 'em[class^=MatchBox_status]')
            if match_status.text == "종료":
                match_urls.append(self.find_element_CSSS(match, 'a[class^="MatchBox_link"]').get_attribute('href'))

        return match_urls
    
    # 다음 달로 이동
    def goto_next_month(self):
        self.wait_present('button[class^="CalendarDate_button_next"]')
        next_button = self.find_element_CSSS(self.driver, 'button[class^="CalendarDate_button_next"]')

        self.click(next_button)

        return 1

    def get_current_month(self):
        self.wait_present('time[class^="CalendarDate_current_date"]')
        current = self.find_element_CSSS(self.driver, 'time[class^="CalendarDate_current_date"]')

        month = current.get_attribute('datetime').split('-')[1]
        return int(month)

    # 특정 시즌 경기 데이터 긁어오기
    def get_game_data_season(self, year, retry = 3):
        self.click(self.find_calender_button())
        self.select_year(year)
        self.wait_present('button[class^="Calendar_button_date"]')
        current_month = self.goto_first_month()
        self.wait_present('button[class^="Calendar_button_date"]')
        self.click_first_date()

        while current_month < 13:
            activated_dates = self.get_activated_dates()
            for date in activated_dates:
                urls = self.get_game_urls(year, current_month, date)
                if isinstance(urls, list):
                    for url in urls:
                        ld = {}
                        for _ in range(retry):
                            try:
                                ld, ind, rd = self.get_game_data(url)
                            except TimeoutException:
                                pass
                            if ld:
                                break
                        if not ld:
                            raise
                        game_data = {"lineup": ld, "relay": ind, "record": rd}
                        filename = url.split('/')[-1] + '.json'
                        with open(self.path + filename, 'w', encoding = 'utf-8') as tgtfile:
                            json.dump(game_data, tgtfile, ensure_ascii= False, indent = 4)
            
            self.driver.get(self.get_schedule_page_url(year,current_month,activated_dates[-1]))
            for _ in range(retry):
                try:
                    check = self.goto_next_month()
                except TimeoutException:
                    check = 0
                    self.driver.refresh()
                if check:
                    break
            if not check:
                raise

            current_month += 1
            if self.get_current_month() != current_month:
                # 강제 이동
                self.driver.get(self.get_schedule_page_url(year,current_month,1))

    def get_game_data_range(self, start_date, end_date, retry = 3):
        """
        start_date, end_date: datetime.date 객체 또는 'YYYY-MM-DD'문자열
        """
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        if end_date < start_date:
            raise ValueError("종료일이 시작일보다 앞설 수 없습니다.")

        cur = start_date
        while cur <= end_date:
            year, month, day = cur.year, cur.month, cur.day
            # 해당 날짜의 경기 페이지에서 완료된 경기 링크 수집
            urls = self.get_game_urls(year, month, day)
            if not urls:
                cur += datetime.timedelta(days=1)
                continue
            if isinstance(urls, list):
                for url in urls:
                    # 네트워크 타임아웃/오류 대비 재시도
                    ld = {}
                    for _ in range(retry):
                        try:
                            ld, ind, rd = self.get_game_data(url)
                        except TimeoutException:
                            pass
                        if ld:
                            break
                    if not ld:
                        # 끝까지 실패하면 스킵
                        continue

                    game_data = {"lineup": ld, "relay": ind, "record": rd}
                    filename = url.split('/')[-1] + '.json'
                    with open(self.path + filename, 'w', encoding = 'utf-8') as tgtfile:
                        json.dump(game_data, tgtfile, ensure_ascii=False, indent = 4)

            cur += datetime.timedelta(days=1)

    def iter_active_date_urls(self, start_date, end_date):
        """
        일정 페이지의 활성화된 날짜를 이용해 (날짜, 경기 URL 리스트)를 순회한다.

        - start_date, end_date: datetime.date
        - 활성화되지 않은 날짜는 자동으로 건너뛴다.
        """
        if end_date < start_date:
            raise ValueError("종료일이 시작일보다 앞설 수 없습니다.")

        self.driver.get(self.get_schedule_page_url(start_date.year, start_date.month, start_date.day))
        cur_year, cur_month = start_date.year, start_date.month

        while True:
            activated_dates = self.get_activated_dates()
            for day in activated_dates:
                date_obj = datetime.date(cur_year, cur_month, day)
                if date_obj < start_date or date_obj > end_date:
                    continue

                urls = self.get_game_urls(cur_year, cur_month, day)
                yield date_obj, urls

            if cur_year == end_date.year and cur_month == end_date.month:
                break

            if cur_month == 12:
                next_year, next_month = cur_year + 1, 1
            else:
                next_year, next_month = cur_year, cur_month + 1

            try:
                moved = self.goto_next_month()
            except Exception:
                moved = 0

            if not moved or self.get_current_month() != next_month:
                self.driver.get(self.get_schedule_page_url(next_year, next_month, 1))

            cur_year, cur_month = next_year, next_month

if __name__ == "__main__":
    scrapper = Scrapper()

    try:
        scrapper.get_game_data_season(2024)
    finally:
        try:
            scrapper.driver.quit()
        except Exception:
            pass

    