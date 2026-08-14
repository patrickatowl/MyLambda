"""
以 service_id 查詢 SAP ByDesign 服務產品(Service Product)資訊的 SOAP API 範例。

對應 ERP_api 專案中 app/Services/ServiceService.php::querySapService() 的邏輯：
- SAP ByD Web Service:  "Query Service Products"
- SOAP 操作 (Operation): FindByElements
- 認證方式: SOAP 層 HTTP Basic Auth (帳密即 .env 的 BYD_login / BYD_password)

需要事先準備：
1. pip install zeep
2. 該服務對應的 WSDL 檔案 (可從 SAP ByD 系統匯出，或使用 ERP_api 後台
   admin/wsdl 上傳的同一份 WSDL)。可以是本機路徑，也可以是 https:// URL。
3. 有效的 SAP ByDesign 帳號密碼 (BYD_login / BYD_password)。

用法範例：
    python query_service_by_id.py \
        --wsdl "./Query Service Products.wsdl" \
        --service-id "J00000000000000000000000000001"

也可以用環境變數提供帳密，不用寫在命令列上：
    set BYD_login=xxx
    set BYD_password=xxx
    python query_service_by_id.py --wsdl ... --service-id ...
"""

import argparse
import os
import sys

from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.transports import Transport


def build_client(wsdl_path: str, login: str, password: str) -> Client:
    """建立帶有 HTTP Basic Auth 的 SOAP client（等同 PHP 端 config/soap_options.php 的設定）。"""
    session = Session()
    session.auth = HTTPBasicAuth(login, password)
    transport = Transport(session=session)
    return Client(wsdl=wsdl_path, transport=transport)


def query_service_by_id(client: Client, service_id: str):
    """
    呼叫 SAP ByD 的 FindByElements 操作，依 service_id (InternalID) 查詢單筆服務產品。

    對應 PHP 端的參數結構：
        ServiceProductByElementsQuery_sync
          -> ServiceProductSelectionByElements
               -> SelectionByInternalID
                    - InclusionExclusionCode:      'I'   (Include)
                    - IntervalBoundaryTypeCode:     '1'  (單一值，非區間)
                    - LowerBoundaryInternalID:      service_id
          -> ProcessingConditions
               - QueryHitsMaximumNumberValue: '1'
               - QueryHitsUnlimitedIndicator: False
    """
    selection_by_elements = {
        "SelectionByInternalID": {
            "InclusionExclusionCode": "I",
            "IntervalBoundaryTypeCode": "1",
            "LowerBoundaryInternalID": service_id,
        }
    }
    processing_conditions = {
        "QueryHitsMaximumNumberValue": "1",
        "QueryHitsUnlimitedIndicator": False,
    }

    response = client.service.FindByElements(
        ServiceProductSelectionByElements=selection_by_elements,
        ProcessingConditions=processing_conditions,
    )
    return response


def main():
    parser = argparse.ArgumentParser(description="以 service_id 查詢 SAP ByDesign 服務產品資訊")
    parser.add_argument("--wsdl", required=True, help="Query Service Products.wsdl 的路徑或 URL")
    parser.add_argument("--service-id", required=False, help="要查詢的 service_id，未提供則互動輸入")
    parser.add_argument("--login", default=os.environ.get("BYD_login"), help="SAP ByD 帳號 (預設讀取環境變數 BYD_login)")
    parser.add_argument("--password", default=os.environ.get("BYD_password"), help="SAP ByD 密碼 (預設讀取環境變數 BYD_password)")
    args = parser.parse_args()

    if not args.login or not args.password:
        sys.exit("缺少帳密：請設定 --login/--password 參數，或環境變數 BYD_login / BYD_password")

    service_id = args.service_id or input("請輸入要查詢的 service_id：").strip()
    if not service_id:
        sys.exit("service_id 不可為空")

    client = build_client(args.wsdl, args.login, args.password)

    try:
        response = query_service_by_id(client, service_id)
    except Exception as exc:  # noqa: BLE001 - 範例程式，直接印出錯誤即可
        sys.exit(f"查詢失敗：{exc}")

    if not getattr(response, "ProcessingConditions", None):
        sys.exit(f"查無資料，或 SAP 回應格式異常：{response}")

    print(response)


if __name__ == "__main__":
    main()
