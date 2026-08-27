"""
讀取台灣銀行外幣收盤匯率 CSV 檔（如 ClosingRate@202605291601.csv），
解析所有幣別兌台幣（TWD）之匯率與生效日期，
並透過 SAP ByDesign SOAP Web Service (Manage Exchange Rate) 批次匯入系統。
"""

import argparse
import csv
import datetime
import os
import sys
import uuid
from typing import List, Tuple, Optional

from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.transports import Transport


def parse_taiwan_bank_csv(file_path: str) -> Tuple[Optional[str], List[Tuple[str, float]]]:
    """
    解析台灣銀行匯率 CSV 檔
    回傳: (parsed_date_str, [(currency_code, rate_value), ...])
    """
    rates = []
    effective_date = None

    with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue

            # 嘗試解析日期行 (例: "29 May, 2026" 或 "31 July, 2026")
            if len(row) >= 2 and any(
                month in row[0]
                for month in [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ]
            ):
                raw_date_str = ", ".join([x.strip() for x in row])
                try:
                    dt = datetime.datetime.strptime(raw_date_str, "%d %B, %Y")
                    effective_date = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

            # 解析幣別與匯率行 (例: "  USD", "31.3700")
            if len(row) == 2:
                curr = row[0].strip()
                rate_str = row[1].strip()
                # 排除標頭行，只取 3 碼 ISO 幣別代碼
                if curr != "Currency" and len(curr) == 3:
                    try:
                        rate = float(rate_str)
                        rates.append((curr, rate))
                    except ValueError:
                        pass

    return effective_date, rates


def import_exchange_rates_to_sap(
    client: Client,
    rates: List[Tuple[str, float]],
    target_currency: str = "TWD",
    effective_date: str = None,
    rate_type: str = "Z01",
):
    """
    依據 WSDL Signature 組裝 SOAP Request 並發送至 SAP ByDesign
    
    WSDL Signature:
    - actionCode: '04' (SAVE)
    - TypeCode: 匯率類型 (例如 'Z01' 或 '001')
    - SourceCurrencyCode: 來源幣別 (例如 'USD')
    - TargetCurrencyCode: 目標幣別 (例如 'TWD')
    - MidRate: 匯率金額
    - ValidFromDateTime: ISO UTC 時間格式 (例如 '2026-05-29T00:00:00Z')
    """
    effective_date = effective_date or datetime.date.today().strftime("%Y-%m-%d")
    valid_from_datetime = f"{effective_date}T00:00:00Z"

    # 建立批次 ExchangeRate 節點
    exchange_rate_items = []
    for source_curr, rate in rates:
        item = {
            "actionCode": "04",  # 04 = SAVE
            "TypeCode": rate_type,
            "SourceCurrencyCode": source_curr,
            "TargetCurrencyCode": target_currency,
            "MidRate": rate,
            "ValidFromDateTime": valid_from_datetime,
        }
        exchange_rate_items.append(item)

    request = {
        "BasicMessageHeader": {"ID": uuid.uuid4().hex.upper()},
        "ExchangeRate": exchange_rate_items,
    }

    return client.service.MaintainBundle(**request)


def main():
    parser = argparse.ArgumentParser(description="讀取台銀匯率 CSV 並批次寫入 SAP ByDesign")
    parser.add_argument("--wsdl", required=True, help="Manage Exchange Rate.wsdl 的路徑")
    parser.add_argument("--csv", required=True, help="匯率 CSV 檔案路徑")
    parser.add_argument("--date", help="指定生效日期 (YYYY-MM-DD)，若不指定則自動從 CSV 讀取")
    parser.add_argument("--target-currency", default="TWD", help="目標幣別，預設 TWD")
    parser.add_argument("--rate-type", default="Z01", help="匯率類型代碼，預設 Z01")

    parser.add_argument("--login", default=os.environ.get("BYD_login"), help="SAP ByD 帳號")
    parser.add_argument("--password", default=os.environ.get("BYD_password"), help="SAP ByD 密碼")
    args = parser.parse_args()

    if not args.login or not args.password:
        sys.exit("缺少帳密：請設定 --login/--password 參數，或環境變數 BYD_login / BYD_password")

    if not os.path.exists(args.csv):
        sys.exit(f"找不到 CSV 檔案：{args.csv}")

    # 1. 解析 CSV 檔案
    parsed_date, rates = parse_taiwan_bank_csv(args.csv)
    effective_date = args.date or parsed_date or datetime.date.today().strftime("%Y-%m-%d")

    if not rates:
        sys.exit("CSV 內未解析到任何有效的幣別匯率資料。")

    print(f"=== CSV 解析完成 ===")
    print(f"生效日期: {effective_date}")
    print(f"解析到 {len(rates)} 筆幣別匯率：")
    for curr, rate in rates:
        print(f"  - 1 {curr} = {rate} {args.target_currency}")
    print("=" * 30)

    # 2. 建立 SOAP Client
    session = Session()
    session.auth = HTTPBasicAuth(args.login, args.password)
    transport = Transport(session=session)
    client = Client(wsdl=args.wsdl, transport=transport)

    # 3. 發送 SOAP 批次寫入請求
    print("正在將匯率批次寫入 SAP ByDesign...")
    try:
        response = import_exchange_rates_to_sap(
            client=client,
            rates=rates,
            target_currency=args.target_currency,
            effective_date=effective_date,
            rate_type=args.rate_type,
        )
    except Exception as exc:
        sys.exit(f"呼叫 SOAP 服務失敗：{exc}")

    # 4. 檢查回傳結果
    logs = getattr(getattr(response, "Log", None), "Item", None) or []
    has_error = False
    for item in logs:
        severity = getattr(item, "SeverityCode", "")
        note = getattr(item, "Note", "")
        print(f"[SAP 訊息][Severity={severity}] {note}")
        if severity in ["3", "4"]:
            has_error = True

    if not has_error:
        print(f"成功將 {len(rates)} 筆外幣匯率寫入 SAP ByDesign (生效日期: {effective_date})！")
    else:
        print("寫入過程中部分資料有異常，請確認上述 Log 訊息。")


if __name__ == "__main__":
    main()