import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urljoin

# 準備一個常見的瀏覽器 User-Agent
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def download_bot_rates_csv_previous_month():
    # 1. 動態計算前一個月的年月 (格式：YYYY-MM)
    today = datetime.now()
    # 取得本月的 1 號
    first_day_this_month = today.replace(day=1)
    # 減去 1 天，日期就會自動倒退到「上個月的最後一天」
    last_month_date = first_day_this_month - timedelta(days=1)
    target_year_month = last_month_date.strftime("%Y-%m")
    
    # 2. 設定查詢網址 
    base_url = "https://rate.bot.com.tw"
    query_url = f"{base_url}/cr/{target_year_month}"
    
    print(f"正在查詢 {target_year_month} 的匯率資料...")
    print(f"目標網址: {query_url}")
    
    try:
        # 取得網頁內容
        # 加上 headers 進行請求
        response = requests.get(query_url, headers=headers)
        response.raise_for_status() # 檢查 HTTP 請求是否成功

        
    
    
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 3. 解析網頁，尋找包含 CSV 的下載連結
        csv_link_tag = soup.find("a", string=lambda text: text and "CSV" in text)
        
        if not csv_link_tag or not csv_link_tag.get("href"):
            fallback_csv_url = f"{base_url}/cr/csv/{target_year_month}"
            print(f"網頁中未直接找到按鈕，嘗試預設下載路徑: {fallback_csv_url}")
            csv_url = fallback_csv_url
        else:
            csv_url = urljoin(base_url, csv_link_tag["href"])
            print(f"找到 CSV 下載連結: {csv_url}")
            
        # 4. 發送請求下載 CSV 檔案
        csv_response = requests.get(csv_url, headers=headers)
        csv_response.raise_for_status()
        
        # 5. 儲存檔案到本地端
        filename = f"bot_closing_rates_{target_year_month}.csv"
        with open(filename, "wb") as f:
            f.write(csv_response.content)
            
        print(f"✅ 下載成功！檔案已儲存為: {filename}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 發生網路請求錯誤: {e}")

if __name__ == "__main__":
    download_bot_rates_csv_previous_month()