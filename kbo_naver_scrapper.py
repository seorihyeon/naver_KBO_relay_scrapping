from datetime import datetime
import json
import time
import os
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import JavascriptException

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
        ActionChains(self.driver).move_to_element(relay_btn).click(relay_btn).perform()
        time.sleep(1)
        inning_buttons = self.find_inning_button()
        inning_data = []
        for btn in inning_buttons:
            del self.driver.requests
            ActionChains(self.driver).move_to_element(btn).click(btn).perform()
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
        ActionChains(self.driver).move_to_element(lineup_btn).click(lineup_btn).perform()
        time.sleep(1)
        for request in self.driver.requests:
            if 'preview' in request.path:
                body = request.response.body.decode('utf-8')
                lineup_data = json.loads(body)
        
        return lineup_data
    
    # HTML request를 통해 경기 결과 데이터 취득
    def get_result_data(self, result_btn):
        del self.driver.requests
        ActionChains(self.driver).move_to_element(result_btn).click(result_btn).perform()
        time.sleep(1)
        for request in self.driver.requests:
            if 'record' in request.path:
                body = request.response.body.decode('utf-8')
                record_data = json.loads(body)
        
        return record_data

    def get_game_data(self, game_url):
        self.driver.get(game_url)
        tab_buttons = self.find_tab_button()
        lineup_data = self.get_lineup_data(tab_buttons[2])
        inning_data = self.get_inning_data(tab_buttons[3])
        result_data = self.get_result_data(tab_buttons[6])

        return lineup_data, inning_data, result_data
        

if __name__ == "__main__":
    scrapper = Scrapper()
    game_url = "https://m.sports.naver.com/game/20250419NCHH02025"

    ld, ind, rd = scrapper.get_game_data(game_url)
    
    with open('lineup.json', 'w') as tgtfile:
        json.dump(ld, tgtfile, ensure_ascii= False, indent = 4)
    with open('inning.json', 'w') as tgtfile:
        json.dump(ind, tgtfile, ensure_ascii= False, indent = 4)
    with open('record.json', 'w') as tgtfile:
        json.dump(rd, tgtfile, ensure_ascii= False, indent = 4)

    os.system("pause")

    