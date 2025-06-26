from datetime import datetime
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

    # 경기 페이지 내에서 탭 이동 버튼 찾기
    def find_tab_button(self):
        main_section = self.driver.find_element(By.CSS_SELECTOR, 'div[class^="Home_main_section"]')
        game_panel = main_section.find_element(By.CSS_SELECTOR, 'section[class^="Home_game_panel"]')
        game_tab = game_panel.find_element(By.CSS_SELECTOR, 'ul[class^="GameTab_tab_list"]')
        tab_buttons = game_tab.find_elements(By.CSS_SELECTOR, 'button')

        return tab_buttons

    # 중계 페이지 내에서 이닝 버튼 찾기
    def find_inning_button(self):
        main_section = self.driver.find_element(By.CSS_SELECTOR, 'div[class^="Home_main_section"]')
        game_panel = main_section.find_element(By.CSS_SELECTOR, 'section[class^="Home_game_panel"]')
        tab_list = game_panel.find_element(By.CSS_SELECTOR, 'div[class^="SetTab_tab_list"]')
        inning_buttons = tab_list.find_elements(By.CSS_SELECTOR, 'button')

        inning_buttons[:] = [btn for btn in inning_buttons if btn.is_enabled()]

        return inning_buttons
    
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
                    print(request.querystring[-1])
                    body = request.response.body.decode('utf-8')
                    inning_data.append(json.loads(body))
        
        return inning_data
    
    # HTML request를 통해 선수 라인업 데이터 취득
    def get_lineup_data(self, lineup_btn):
        del self.driver.requests
        self.click(lineup_btn)
        time.sleep(1)
        for request in self.driver.requests:
            if 'preview' in request.path:
                body = request.response.body.decode('utf-8')
                lineup_data = json.loads(body)
        
        return lineup_data
    
    # HTML request를 통해 경기 결과 데이터 취득
    def get_result_data(self, result_btn):
        del self.driver.requests
        self.click(result_btn)
        time.sleep(1)
        for request in self.driver.requests:
            if 'record' in request.path:
                body = request.response.body.decode('utf-8')
                record_data = json.loads(body)
        
        return record_data

    # 경기 중계 url을 받아 필요한 데이터를 긁어서 반환
    def get_game_data(self, game_url):
        self.driver.get(game_url)
        tab_buttons = self.find_tab_button()
        lineup_data = self.get_lineup_data(tab_buttons[2])
        inning_data = self.get_inning_data(tab_buttons[3])
        result_data = self.get_result_data(tab_buttons[6])

        return lineup_data, inning_data, result_data
        
    # 경기/일정 페이지에서 달력 버튼 찾아 반환
    def find_calender_button(self):
        main_section = self.driver.find_element(By.CSS_SELECTOR, 'div[class^="Home_container"]')
        date_area = main_section.find_element(By.CSS_SELECTOR, 'div[class^="CalendarDate_schedule_date_area"]')
        calender = date_area.find_element(By.CSS_SELECTOR, 'div[class^="CalendarDate_calendar_wrap"]')
        calender_button = calender.find_element(By.CSS_SELECTOR, 'button')

        return calender_button
    
    # 달력 html 코드 획득
    def get_calender_html(self):
        main_section = self.driver.find_element(By.CSS_SELECTOR, 'div[class^="Home_container"]')
        date_area = main_section.find_element(By.CSS_SELECTOR, 'div[class^="CalendarDate_schedule_date_area"]')
        calender = date_area.find_element(By.CSS_SELECTOR, 'div[class^="CalendarDate_calendar_wrap"]')
        calender_layer = calender.find_element(By.CSS_SELECTOR, 'div[class^="Calendar_layer_content"]')

        return calender_layer
    
    # 달력에서 년도 선택
    def select_year(self, year):
        calender_html = self.get_calender_html()
        select_year = Select(calender_html.find_element(By.CSS_SELECTOR, 'select[class^="Calendar_select"]'))
        select_year.select_by_value(str(year))

    # 연도의 첫 번째 달로 이동
    def goto_first_month(self):
        calender_html = self.get_calender_html()
        while True:
            self.click(calender_html.find_element(By.CSS_SELECTOR, 'button[class^="Calendar_button_prev"]'))
            time.sleep(1)
            calender_html = self.get_calender_html()
            current_month = calender_html.find_element(By.CSS_SELECTOR, 'div[class^="Calendar_current"]')
            if int(current_month.text[:-1]) == 12:
                self.click(calender_html.find_element(By.CSS_SELECTOR, 'button[class^="Calendar_button_next"]'))
                break
    
    # 달의 첫번째 일자 버튼 클릭
    def click_first_date(self):
        calender_html = self.get_calender_html()
        date_buttons = calender_html.find_elements(By.CSS_SELECTOR, 'button[class^="Calendar_button_date"]')
        for btn in date_buttons:
            if btn.is_enabled():
                self.click(btn)
                break


if __name__ == "__main__":
    scrapper = Scrapper()
    scrapper.driver.get("https://m.sports.naver.com/kbaseball/schedule/index")
    time.sleep(1)
    scrapper.click(scrapper.find_calender_button())
    scrapper.select_year(2023)
    time.sleep(1)
    scrapper.goto_first_month()
    time.sleep(1)
    scrapper.click_first_date()
    
    #with open('lineup.json', 'w') as tgtfile:
    #    json.dump(ld, tgtfile, ensure_ascii= False, indent = 4)
    #with open('inning.json', 'w') as tgtfile:
    #    json.dump(ind, tgtfile, ensure_ascii= False, indent = 4)
    #with open('record.json', 'w') as tgtfile:
    #    json.dump(rd, tgtfile, ensure_ascii= False, indent = 4)

    os.system("pause")

    