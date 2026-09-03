import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from urllib.parse import urljoin

def download_bot_rates_csv():
    # 1. 動態計算前一個月的年月 (格式：YYYY-MM)
    today = datetime.now()
    first_day_this_month = today.replace(day=1)
    last_month_date = first_day_this_month - timedelta(days=1)
    target_year_month = last_month_date.strftime("%Y-%m")
    
    base_url = "https://rate.bot.com.tw"
    query_url = f"{base_url}/cr/{target_year_month}"
    
    print(f"正在查詢 {target_year_month} 的匯率資料...")
    print(f"目標網址: {query_url}")
    
    # 2. 建立 cloudscraper 實例 (它會自動處理常見的防護機制)
    scraper = cloudscraper.create_scraper(browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    })
    
    try:
        # 3. 使用 scraper 發送請求，取代原來的 requests
        response = scraper.get(query_url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 尋找包含 CSV 的下載連結
        csv_link_tag = soup.find("a", string=lambda text: text and "CSV" in text)
        
        if not csv_link_tag or not csv_link_tag.get("href"):
            csv_url = f"{base_url}/cr/csv/{target_year_month}"
            print(f"網頁中未直接找到按鈕，嘗試預設下載路徑: {csv_url}")
        else:
            csv_url = urljoin(base_url, csv_link_tag["href"])
            print(f"找到 CSV 下載連結: {csv_url}")
            
        # 4. 下載 CSV 檔案
        csv_response = scraper.get(csv_url)
        csv_response.raise_for_status()
        
        # 儲存檔案
        filename = f"bot_closing_rates_{target_year_month}.csv"
        with open(filename, "wb") as f:
            f.write(csv_response.content)
            
        print(f"✅ 下載成功！檔案已儲存為: {filename}")
        
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")

if __name__ == "__main__":
    download_bot_rates_csv()