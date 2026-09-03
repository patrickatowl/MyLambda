import os
import time
import glob
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ----------------- 設定區 -----------------
SENDER_EMAIL = "patrick.violin@gmail.com"      # 替換成你用來寄信的 Gmail
SENDER_PASSWORD = "muzc fhed fbyg zdwz" # 替換成剛申請的 16 位應用程式密碼
RECEIVER_EMAIL = "maggie168.hsieh@gmail.com"
# ------------------------------------------

def send_email_with_attachment(file_path, target_month):
    print("準備發送 Email...")
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"自動報表：臺灣銀行 {target_month} 歷史收盤匯率"

    # 信件內文
    body = f"Maggie 您好，\n\n附件為 {target_month} 的臺灣銀行收盤匯率 CSV 檔案，請查收。\n\n本信件為系統自動發送。"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    # 讀取並附加 CSV 檔案
    with open(file_path, "rb") as f:
        part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
    part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
    msg.attach(part)

    # 透過 Gmail SMTP 伺服器寄信
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ 郵件已成功發送至 {RECEIVER_EMAIL}！")
    except Exception as e:
        print(f"❌ 郵件發送失敗: {e}")

def download_and_send_csv():
    # 1. 計算前一個月的年月
    today = datetime.now()
    first_day_this_month = today.replace(day=1)
    last_month_date = first_day_this_month - timedelta(days=1)
    target_year_month = last_month_date.strftime("%Y-%m")
    
    query_url = f"https://rate.bot.com.tw/cr/{target_year_month}"
    current_dir = os.getcwd()
    
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    prefs = {
        "download.default_directory": current_dir,
        "download.prompt_for_download": False,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    print("啟動 Selenium 瀏覽器...")
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        driver.get(query_url)
        wait = WebDriverWait(driver, 15)
        csv_button = wait.until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'csv')]"))
        )
        
        print("找到 CSV 按鈕，執行點擊...")
        driver.execute_script("arguments[0].click();", csv_button)
        
        print("等待檔案下載完成 (5秒)...")
        time.sleep(5)
        
        # 2. 尋找資料夾中最新下載的 CSV 檔案 (排除掉我們自己命名的舊檔案，如果有的話)
        list_of_files = glob.glob(os.path.join(current_dir, '*.csv'))
        if not list_of_files:
            print("❌ 找不到下載的 CSV 檔案！")
            return
            
        # 找出剛剛才載好的那個檔案
        latest_file = max(list_of_files, key=os.path.getctime)
        
        # 3. 處理重新命名與檔案重複邏輯
        base_filename = f"bot_closing_rates_{target_year_month}.csv"
        target_filepath = os.path.join(current_dir, base_filename)
        
        # 檢查該檔名是否已存在
        if os.path.exists(target_filepath):
            # 檔案存在，加入時間戳記以產生新檔名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"bot_closing_rates_{target_year_month}_{timestamp}.csv"
            target_filepath = os.path.join(current_dir, base_filename)
            print(f"⚠️ 檔案已存在，為避免覆蓋，新檔案將命名為: {base_filename}")
        else:
            print(f"將檔案重新命名為標準格式: {base_filename}")
            
        # 執行重新命名
        os.rename(latest_file, target_filepath)
        print(f"✅ 檔案已成功改名為: {target_filepath}")
        
        # 4. 呼叫寄信功能 (傳入改名後的新檔案路徑)
        send_email_with_attachment(target_filepath, target_year_month)
        
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    download_and_send_csv()