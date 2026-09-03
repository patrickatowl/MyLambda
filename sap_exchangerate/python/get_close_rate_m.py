import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

def download_bot_rates_csv():
    # 1. 取得當前年月 (格式：YYYY-MM，例如 2026-09)
    current_year_month = datetime.now().strftime("%Y-%m")
    
    # 2. 設定查詢網址 
    # 依據您提供的網站結構，收盤匯率查詢網址為 /cr/YYYY-MM
    base_url = "https://rate.bot.com.tw"
    query_url = f"{base_url}/cr/{current_year_month}"
    
    print(f"正在查詢 {current_year_month} 的匯率資料...")
    print(f"目標網址: {query_url}")
    
    try:
        # 取得網頁內容
        response = requests.get(query_url)
        response.raise_for_status() # 檢查 HTTP 請求是否成功
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 3. 解析網頁，尋找包含 CSV 的下載連結
        # 網頁中的下載按鈕文字通常包含 "CSV" 字眼
        csv_link_tag = soup.find("a", string=lambda text: text and "CSV" in text)
        
        if not csv_link_tag or not csv_link_tag.get("href"):
            # 如果網頁結構改變導致找不到按鈕，嘗試直接組合常見的臺灣銀行 CSV 下載路徑
            fallback_csv_url = f"{base_url}/cr/csv/{current_year_month}"
            print(f"網頁中未直接找到按鈕，嘗試預設下載路徑: {fallback_csv_url}")
            csv_url = fallback_csv_url
        else:
            csv_url = urljoin(base_url, csv_link_tag["href"])
            print(f"找到 CSV 下載連結: {csv_url}")
            
        # 4. 發送請求下載 CSV 檔案
        csv_response = requests.get(csv_url)
        csv_response.raise_for_status()
        
        # 5. 儲存檔案到本地端
        filename = f"bot_closing_rates_{current_year_month}.csv"
        with open(filename, "wb") as f:
            # 寫入二進位內容以避免編碼問題
            f.write(csv_response.content)
            
        print(f"✅ 下載成功！檔案已儲存為: {filename}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 發生網路請求錯誤: {e}")

if __name__ == "__main__":
    download_bot_rates_csv()