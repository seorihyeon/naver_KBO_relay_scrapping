import datetime
import json
import time
import os
import re
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import JavascriptException
from selenium.webdriver.support.select import Select

# Selenium을 이용해 스크래핑을 수행하는 클래스
class Scrapper:
    def __init__(self, wait = 10, path = './games/'):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--no-sandbox") # 샌드박스 기능 비활성화
        #chrome_options.add_argument("--headless") # GUI 기능 비활성화
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36') # User-agent 위조
        self.driver = webdriver.Chrome(options = chrome_options)
        self.driver.implicitly_wait(wait)
        self.path = path

    # 버튼 클릭
    def click(self, button):
        ActionChains(self.driver).move_to_element(button).click(button).perform()

    # CSS_SELECTOR로 요소 찾기
    def find_element_CSSS(self, parent, query):
        return parent.find_element(By.CSS_SELECTOR, query)
    
    # 경기 페이지 내에서 탭 이동 버튼 찾기
    def find_tab_button(self):
        main_section = self.find_element_CSSS(self.driver, 'div[class^="Home_main_section"]')
        game_panel = self.find_element_CSSS(main_section, 'section[class^="Home_game_panel"]')
        game_tab = self.find_element_CSSS(game_panel, 'ul[class^="GameTab_tab_list"]')
        tab_buttons = game_tab.find_elements(By.CSS_SELECTOR, 'button')
        
        tab_button_dict = dict()
        
        for btn in tab_buttons:
            text = self.find_element_CSSS(btn, 'span[class^="GameTab_text"]').text
            tab_button_dict[text] = btn

        return tab_button_dict

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
        time.sleep(1)
        inning_buttons = self.find_inning_button()
        inning_data = []
        for btn in inning_buttons:
            del self.driver.requests
            self.click(btn)
            time.sleep(1)
            for request in self.driver.requests:
                if 'inning' in request.querystring:
                    body = request.response.body.decode('utf-8')
                    break

            inning_data.append(self.preprocess_inning_data(json.loads(body)))
        
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
        time.sleep(1)
        for request in self.driver.requests:
            if 'preview' in request.path:
                body = request.response.body.decode('utf-8')
                lineup_data = json.loads(body)
                break
        
        lineup_data = self.preprocess_lineup_data(lineup_data)
        
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
        time.sleep(1)
        for request in self.driver.requests:
            if 'record' in request.path:
                body = request.response.body.decode('utf-8')
                record_data = json.loads(body)
                break
        
        record_data = self.preprocess_record_data(record_data)
        
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
        calender_html = self.get_calender_html()
        select_year = Select(self.find_element_CSSS(calender_html, 'select[class^="Calendar_select"]'))
        select_year.select_by_value(str(year))

    # 연도의 첫 번째 달로 이동
    def goto_first_month(self):
        calender_html = self.get_calender_html()
        while True:
            self.click(self.find_element_CSSS(calender_html, 'button[class^="Calendar_button_prev"]'))
            time.sleep(1)
            calender_html = self.get_calender_html()
            current_month = self.find_element_CSSS(calender_html, 'div[class^="Calendar_current"]')
            if int(current_month.text[:-1]) == 12:
                self.click(self.find_element_CSSS(calender_html, 'button[class^="Calendar_button_next"]'))
                break
    
    # 달의 첫번째 일자 버튼 클릭
    def click_first_date(self):
        calender_html = self.get_calender_html()
        date_buttons = calender_html.find_elements(By.CSS_SELECTOR, 'button[class^="Calendar_button_date"]')
        for btn in date_buttons:
            if btn.is_enabled():
                self.click(btn)
                break

    # 활성화 된 날짜 목록 반환
    def get_activated_date(self):
        main_section = self.find_element_CSSS(self.driver, 'div[class^="Home_container"]')
        date_area = self.find_element_CSSS(main_section, 'div[class^="CalendarDate_schedule_date_area"]')
        date_tab = self.find_element_CSSS(date_area, 'div[class^=CalendarDate_calendar_tab_wrap]')
        date_buttons = date_tab.find_elements(By.CSS_SELECTOR, 'button')

        activated_dates = []
        for btn in date_buttons:
            if btn.is_enabled():
                btn_date = self.find_element_CSSS(btn, 'em')
                activated_dates.append(int(btn_date.get_attribute('innerHTML')))

        return activated_dates

    # 일자 지정하여 일정 주소 반환
    def get_schedule_page_url(self, year, month, date):
        base = "https://m.sports.naver.com/kbaseball/schedule/index?date="
        date = datetime.date(year, month, date).strftime("%Y-%m-%d")
        
        return base + date
    
    # 특정 일자에서 경기 페이지 주소 얻기
    def get_game_urls(self, year, month, date):
        self.driver.get(self.get_schedule_page_url(year,month,date))
        time.sleep(1)

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


if __name__ == "__main__":
    scrapper = Scrapper()
    urls = scrapper.get_game_urls(2025, 6, 24)
    ld, ind, rd = scrapper.get_game_data(urls[0])
    
    with open('lineup.json', 'w') as tgtfile:
        json.dump(ld, tgtfile, ensure_ascii= False, indent = 4)
    with open('inning.json', 'w') as tgtfile:
        json.dump(ind, tgtfile, ensure_ascii= False, indent = 4)
    with open('record.json', 'w') as tgtfile:
        json.dump(rd, tgtfile, ensure_ascii= False, indent = 4)

    