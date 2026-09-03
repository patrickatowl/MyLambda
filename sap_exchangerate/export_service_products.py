"""
使用 SAP Business ByDesign SOAP API (Query Service Products)
匯出所有服務產品 (Service Product) 清單並存成 CSV 檔案。
"""

import argparse
import csv
import os
import sys
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.transports import Transport

# 預設的 Endpoint URL
DEFAULT_WSDL_URL = "https://my343714.sapbydesign.com/sap/bc/srt/scs/sap/queryserviceproductin?wsdl"


def fetch_all_service_products(client: Client, page_size: int = 100):
    """
    分頁查詢所有 Service Products
    """
    all_products = []
    start_index = 0
    more_hits_exist = True

    while more_hits_exist:
        print(f"正在讀取資料... (目前起始位址: {start_index})")
        
        request_data = {
            "ServiceProductSelectionByElements": {
                # 留空代表選擇全部產品
            },
            "ProcessingConditions": {
                "QueryHitsMaximumNumberValue": page_size,
                "QueryHitsUnlimitedIndicator": False,
                "LastReturnedObjectID": None if start_index == 0 else last_object_id,
            },
        }

        # 呼叫 SOAP 服務 (FindByElements)
        response = client.service.FindByElements(**request_data)

        # 取得回傳的 ServiceProduct 清單
        products = getattr(response, "ServiceProduct", []) or []
        if not products:
            break

        all_products.extend(products)

        # 檢查分頁條件
        processing_conditions = getattr(response, "ProcessingConditions", None)
        if processing_conditions:
            more_hits_exist = getattr(processing_conditions, "MoreHitsAvailableIndicator", False)
            last_object_id = getattr(processing_conditions, "LastReturnedObjectID", None)
            start_index += len(products)
        else:
            more_hits_exist = False

        print(f"已成功取得 {len(all_products)} 筆服務產品資料。")

    return all_products


def export_to_csv(products, output_file: str):
    """
    將 Service Product 列表解析並寫入 CSV 檔案
    """
    headers = [
        "InternalID",
        "UUID",
        "Description",
        "BaseMeasureUnitCode",
        "LifeCycleStatusCode",
        "ProductCategoryID",
    ]

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for prod in products:
            internal_id = getattr(prod, "InternalID", "")
            uuid_val = getattr(prod, "UUID", "")
            
            # Description 處理 (多語言陣列)
            desc_list = getattr(prod, "Description", []) or []
            description = desc_list[0]._value_1 if desc_list else ""

            base_uom = getattr(prod, "BaseMeasureUnitCode", "")
            status_code = getattr(prod, "LifeCycleStatusCode", "")
            category_id = getattr(prod, "ProductCategoryInternalID", "")

            writer.writerow([
                internal_id,
                uuid_val,
                description,
                base_uom,
                status_code,
                category_id,
            ])

    print(f"\n匯出完成！檔案已儲存至: {os.path.abspath(output_file)}")


def main():
    parser = argparse.ArgumentParser(description="匯出 SAP ByDesign 服務產品 (Service Product) 清單")
    parser.add_argument("--wsdl", default=DEFAULT_WSDL_URL, help="WSDL 路徑或網址")
    parser.add_argument("--output", default="service_products.csv", help="輸出的 CSV 檔案路徑")
    parser.add_argument("--login", default=os.environ.get("BYD_login"), help="SAP 帳號 (預設讀取環境變數 BYD_login)")
    parser.add_argument("--password", default=os.environ.get("BYD_password"), help="SAP 密碼 (預設讀取環境變數 BYD_password)")
    args = parser.parse_args()

    if not args.login or not args.password:
        sys.exit("缺少帳密：請透過 --login / --password 指定，或設定環境變數 BYD_login 及 BYD_password")

    # 1. 初始化 SOAP Client
    session = Session()
    session.auth = HTTPBasicAuth(args.login, args.password)
    transport = Transport(session=session)
    client = Client(wsdl=args.wsdl, transport=transport)

    # 2. 查詢資料
    try:
        products = fetch_all_service_products(client)
    except Exception as exc:
        sys.exit(f"查詢 Service Product 失敗: {exc}")

    # 3. 寫入 CSV
    if products:
        export_to_csv(products, args.output)
    else:
        print("未查詢到任何服務產品資料。")


if __name__ == "__main__":
    main()