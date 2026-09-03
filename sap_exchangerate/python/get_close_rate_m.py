import os
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def download_csv_with_selenium():
    # 1. 取得前一個月的年月
    today = datetime.now()
    first_day_this_month = today.replace(day=1)
    last_month_date = first_day_this_month - timedelta(days=1)
    target_year_month = last_month_date.strftime("%Y-%m")
    
    query_url = f"https://rate.bot.com.tw/cr/{target_year_month}"
    
    # 2. 設定 Selenium 瀏覽器選項
    # 取得當前執行路徑，將下載資料夾設定在此
    current_dir = os.getcwd()
    
    chrome_options = Options()
    # 啟動無頭模式 (不顯示實體瀏覽器視窗，如果測試時想看畫面可以把這行註解掉)
    # chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options = Options()
    
    

    # 修改預設下載路徑，並禁止跳出下載確認視窗
    prefs = {
        "download.default_directory": current_dir,
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    print("啟動 Selenium 瀏覽器...")
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print(f"正在前往: {query_url}")
        driver.get(query_url)
        
        # 2. ⚠️ 改變定位策略：不抓文字，改抓網址中包含 'csv' 的按鈕
        wait = WebDriverWait(driver, 15)
        csv_button = wait.until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'csv')]"))
        )
        
        print("找到 CSV 按鈕，執行點擊...")
        # 為了避免被畫面上的其他元素擋住，使用 JavaScript 執行點擊
        driver.execute_script("arguments[0].click();", csv_button)
        
        # 4. 等待檔案下載完成 (給予 5 秒鐘的緩衝時間)
        print("等待檔案下載完成...")
        time.sleep(5)
        print(f"✅ 理論上下載已完成！請檢查目前資料夾 ({current_dir}) 中是否有新下載的 CSV 檔案。")
        
    except Exception as e:
        print(f"❌ 發生錯誤或找不到按鈕: {e}")
        
    finally:
        # 關閉瀏覽器，釋放資源
        driver.quit()

if __name__ == "__main__":
    download_csv_with_selenium()