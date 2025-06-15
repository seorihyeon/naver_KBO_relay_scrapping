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

    # 중계 페이지 내에서 이닝 버튼 찾기
    def find_inning_button(self):
        main_section = self.driver.find_element(By.CSS_SELECTOR, 'div[class^="Home_main_section"]')
        game_panel = main_section.find_element(By.CSS_SELECTOR, 'section[class^="Home_game_panel"]')
        tab_list = game_panel.find_element(By.CSS_SELECTOR, 'div[class^="SetTab_tab_list"]')
        inning_buttons = tab_list.find_elements(By.CSS_SELECTOR, 'button')

        inning_buttons[:] = [btn for btn in inning_buttons if btn.is_enabled()]

        return inning_buttons
    
    # HTML request를 통해 이닝 데이터 취득
    def get_inning_data(self):
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
        

if __name__ == "__main__":
    scrapper = Scrapper()
    scrapper.driver.get("https://m.sports.naver.com/game/20250419NCHH02025/relay")
    
    data = scrapper.get_inning_data()
    with open('test.json', 'w') as tgtfile:
        json.dump(data, tgtfile, ensure_ascii= False, indent = 4)

    os.system("pause")

    