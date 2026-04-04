import datetime
import json
import os
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# Selenium을 이용해 스크래핑을 수행하는 클래스
class Scrapper:
    def __init__(self, wait=10, path="games", headless=True):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless, args=["--no-sandbox"])
        self.context = self.browser.new_context(
            user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0')
        )
        self.page = self.context.new_page()
        self.driver = self.page
        self.DEFAULT_TIMEOUT = wait
        self.page.set_default_timeout(wait * 1000)

        try:
            if not os.path.exists('./' + path):
                os.makedirs('./' + path)
        except OSError as e:
            print(f"Error creating directory: {e}")
        self.path = './' + path + '/'

        self.page.goto("https://m.sports.naver.com/kbaseball/schedule/index")

    def close(self):
        try:
            self.context.close()
        finally:
            try:
                self.browser.close()
            finally:
                self.playwright.stop()

    def _to_locator(self, root, css=None):
        target = self.page if root is None else root
        if isinstance(target, str):
            target = self.page.locator(target)
        return target.locator(css) if css else target

    # 버튼 클릭
    def click(self, button):
        button.click(timeout=getattr(self, 'DEFAULT_TIMEOUT', 10) * 1000)

    # CSS_SELECTOR로 요소 찾기
    def find_element_css(self, parent, query):
        return self._to_locator(parent, query).first

    # backward compatibility
    def find_element_CSSS(self, parent, query):
        return self.find_element_css(parent, query)
    
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
        t_ms = (timeout or getattr(self, 'DEFAULT_TIMEOUT', 10)) * 1000
        locator = self._to_locator(root, css)
        state = "visible" if visible else "attached"
        locator.first.wait_for(state=state, timeout=t_ms)

        deadline = datetime.datetime.now() + datetime.timedelta(milliseconds=t_ms)
        while locator.count() < min_count:
            if datetime.datetime.now() >= deadline:
                raise PlaywrightTimeoutError(f"Timed out waiting for at least {min_count} elements: {css}")
            self.page.wait_for_timeout(100)

        if fresh:
            locator = self._to_locator(root, css)

        if min_count == 1:
            return locator.first
        return [locator.nth(i) for i in range(locator.count())]

    def wait_all_present(self, css, timeout = None):
        return self.wait_present(css, timeout=timeout, min_count=1, visible=False)
    
    def wait_clickable_css(self, css, timeout = None):
        return self.wait_present(css, timeout=timeout, min_count=1, visible=True)
    
    def wait_for_request(self, keyword, key_attr, timeout = None, retries = 3, refresh = True, clear_before = True, ready_css = None):
        t_ms = (timeout or getattr(self, 'DEFAULT_TIMEOUT', 10)) * 1000

        def _predicate(resp):
            url = resp.url or ""
            return keyword in url and resp.status >= 200

        attempt = 0
        while True:
            try:
                return self.page.wait_for_response(_predicate, timeout=t_ms)
            except PlaywrightTimeoutError:
                if attempt >= retries:
                    raise
                attempt += 1

                if refresh:
                    try:
                        self.page.reload()
                    except Exception:
                        pass

                if ready_css:
                    try:
                        self.wait_present(ready_css)
                    except Exception:
                        pass
                
    # 경기 페이지 내에서 탭 이동 버튼 찾기
    def find_tab_button(self, timeout = None, retry = 3):
        tab_css = 'ul[class^="GameTab_tab_list"]'
        self.wait_present(tab_css, visible=True)
        
        for _ in range(retry):
            try:
                tab_list = self.find_element_css(self.page, tab_css)
                tab_buttons = tab_list.locator('button')
        
                tab_button_dict = dict()
                
                for i in range(tab_buttons.count()):
                    btn = tab_buttons.nth(i)
                    text = self.find_element_css(btn, 'span[class^="GameTab_text"]').inner_text()
                    tab_button_dict[text.strip()] = btn
                
                if tab_button_dict:
                    return tab_button_dict
            except Exception:
                continue
        return {}

    # 중계 페이지 내에서 이닝 버튼 찾기
    def find_inning_button(self):
        main_section = self.find_element_css(self.page, 'div[class^="Home_main_section"]')
        game_panel = self.find_element_css(main_section, 'section[class^="Home_game_panel"]')
        tab_list = self.find_element_css(game_panel, 'div[class^="SetTab_tab_list"]')
        inning_buttons = tab_list.locator('button:enabled')
        return [inning_buttons.nth(i) for i in range(inning_buttons.count())]
    
    # 이닝 데이터 전처리
    def preprocess_inning_data(self, inning_data):
        processed_data = inning_data["result"]["textRelayData"]["textRelays"]
        processed_data.reverse()

        return processed_data
    
    # HTML request를 통해 이닝 데이터 취득
    def get_inning_data(self, relay_btn):
        self.click(relay_btn)
        self.wait_all_present('section[class^="Home_game_panel"] div[class^="SetTab_tab_list"] button')
        inning_buttons = self.find_inning_button()
        inning_data = []
        for btn in inning_buttons:
            with self.page.expect_response(lambda r: "inning" in (r.url or ""), timeout=self.DEFAULT_TIMEOUT * 1000) as resp_info:
                self.click(btn)
            resp = resp_info.value
            body = resp.text()
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
        with self.page.expect_response(lambda r: "preview" in (r.url or ""), timeout=self.DEFAULT_TIMEOUT * 1000) as resp_info:
            self.click(lineup_btn)
        body = resp_info.value.text()
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
        with self.page.expect_response(lambda r: "record" in (r.url or ""), timeout=self.DEFAULT_TIMEOUT * 1000) as resp_info:
            self.click(result_btn)
        body = resp_info.value.text()
        record_data = self.preprocess_record_data(json.loads(body)) if body else {}
        
        return record_data

    # 경기 중계 url을 받아 필요한 데이터를 긁어서 반환
    def get_game_data(self, game_url):
        self.page.goto(game_url)
        tab_buttons = self.find_tab_button()
        lineup_data = self.get_lineup_data(tab_buttons["라인업"])
        inning_data = self.get_inning_data(tab_buttons["중계"])
        record_data = self.get_record_data(tab_buttons["기록"])

        return lineup_data, inning_data, record_data
        
    # 활성화 된 날짜 목록 반환
    def get_activated_dates(self):
        self.wait_present('div[class^="CalendarDate_calendar_tab_wrap"]')

        css_tree = 'div[class^="Home_container"] div[class^="CalendarDate_schedule_date_area"] div[class^="CalendarDate_calendar_tab_wrap"]'
        date_tab = self.find_element_css(self.page, css_tree)
        date_buttons_em = date_tab.locator('button:not([disabled]) em')

        activated_dates = []
        for i in range(date_buttons_em.count()):
            em = date_buttons_em.nth(i)
            txt = em.inner_html()
            activated_dates.append(int(txt))

        return activated_dates

    def get_activated_dates_for_month(self, year, month, day = 1):
        """Load a month's schedule page and return enabled dates for that month.

        Parameters
        ----------
        year, month: int
            Target year/month to load.
        day: int, optional
            Day to use when constructing the schedule URL (default: 1).
        """
        self.page.goto(self.get_schedule_page_url(year, month, day))

        try:
            return self.get_activated_dates()
        except Exception:
            return []

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
        self.page.goto(self.get_schedule_page_url(year, month, date))
        try:
            self.wait_all_present('div[class^="ScheduleAllType_match_list_group"]')
        except PlaywrightTimeoutError:
            # 경기 없음 or 무한 로딩 -> 건너뜀
            return []
        main_section = self.find_element_css(self.page, 'div[class^="Home_container"]')
        match_group = main_section.locator('div[class^="ScheduleAllType_match_list_group"]')

        target_group = None
        for i in range(match_group.count()):
            grp = match_group.nth(i)
            a = self.find_element_css(grp, 'div[class^="ScheduleAllType_title_area"]')
            em = self.find_element_css(a, "em")
            if em.inner_text().strip() == "KBO리그":
                target_group = grp
                break
        
        if target_group is None:
            return -1

        match_urls = []    
        matches = target_group.locator('li[class^="MatchBox_match_item"]')
        for i in range(matches.count()):
            match = matches.nth(i)
            match_status = self.find_element_css(match, "em[class^=MatchBox_status]")
            if match_status.inner_text().strip() == "종료":
                match_urls.append(self.find_element_css(match, 'a[class^="MatchBox_link"]').get_attribute("href"))

        return match_urls
    
    # 다음 달로 이동
    def goto_next_month(self):
        self.wait_present('button[class^="CalendarDate_button_next"]')
        next_button = self.find_element_css(self.page, 'button[class^="CalendarDate_button_next"]')

        self.click(next_button)

        return 1

    def get_current_month(self):
        self.wait_present('time[class^="CalendarDate_current_date"]')
        current = self.find_element_css(self.page, 'time[class^="CalendarDate_current_date"]')

        month = current.get_attribute('datetime').split('-')[1]
        return int(month)

    def iter_active_date_urls(self, start_date, end_date):
        """
        일정 페이지의 활성화된 날짜를 이용해 (날짜, 경기 URL 리스트)를 순회한다.

        - start_date, end_date: datetime.date
        - 활성화되지 않은 날짜는 자동으로 건너뛴다.
        """
        if end_date < start_date:
            raise ValueError("종료일이 시작일보다 앞설 수 없습니다.")

        self.page.goto(self.get_schedule_page_url(start_date.year, start_date.month, start_date.day))
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
                self.page.goto(self.get_schedule_page_url(next_year, next_month, 1))

            cur_year, cur_month = next_year, next_month

    
