"""
為既有的 SAP ByDesign 服務產品(Service Product)新增 Sales(銷售組織)資料，
並在新增前先查詢目前狀態、新增後一併寫入該銷售組織對應公司的估價(Valuation)資料。

注意用詞澄清：
    "Manage Material Valuations" 是「物料(Material)」的估價寫入服務。
    服務產品(Service Product)對應的估價寫入服務其實是另一個 WSDL：
        "Manage Service Product Valuations"（操作: MaintainBundle）
    本範例沿用 ERP_api 專案中 app/Services/ServiceValuationService.php::createSapServiceValuation()
    的參數結構，寫入的是「服務產品」的估價，而不是物料的。

流程分三步（對應 ERP_api 專案裡的三個既有 Service）：
    1. 查詢目前狀態  — Query Service Products / FindByElements
       (app/Services/ServiceService.php::querySapService)
       印出目前已有的 Sales、Valuation 節點，方便下手前先看現況。
    2. 新增 Sales    — Manage Service Products / MaintainBundle_V1
       (app/Services/ServiceService.php::createSapServiceBasic 的 Sales 節點寫法)
    3. 寫入 Valuation — Manage Service Product Valuations / MaintainBundle
       (app/Services/ServiceValuationService.php::createSapServiceValuation)

- 認證方式: SOAP 層 HTTP Basic Auth (帳密即 .env 的 BYD_login / BYD_password)

需要事先準備：
1. pip install zeep
2. 三份 WSDL 檔案（皆可從 ERP_api 後台 admin/wsdl 已上傳的檔案取得，或從 SAP ByD 匯出）：
   - "Query Service Products.wsdl"
   - "Manage Service Products.wsdl"
   - "Manage Service Product Valuations.wsdl"
3. 有效的 SAP ByDesign 帳號密碼 (BYD_login / BYD_password)。

用法範例（新增銷售組織 EP1201，並寫入 OB1000 公司的估價成本 100 TWD）：
    python add_service_sales.py \
        --wsdl "./Manage Service Products.wsdl" \
        --query-wsdl "./Query Service Products.wsdl" \
        --valuation-wsdl "./Manage Service Product Valuations.wsdl" \
        --service-id "E11GB0100004795" \
        --sales-org "EP1201" \
        --company-id "OB1000" \
        --account-determination-group "Z006" \
        --cost 100 --currency TWD

只想新增 Sales、不寫估價的話，把 --valuation-wsdl / --company-id 留空即可，
腳本會自動跳過第 3 步。
"""

import argparse
import datetime
import os
import sys
import uuid

from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.transports import Transport


# 對應 app/SapByDesign/Information/ActionCode.php
class ActionCode:
    CREATE = "01"
    UPDATE = "02"
    DELETE = "03"
    SAVE = "04"
    REMOVE = "05"
    NO_ACTION = "06"


# 對應 app/SapByDesign/Information/LifeCycleStatusCode.php
class LifeCycleStatusCode:
    IN_PREPARATION = "1"
    ACTIVE = "2"


# 對應 app/Models/Service.php 的 SET_OF_BOOKS_ID 常數
SET_OF_BOOKS_ID = "7000"


def build_client(wsdl_path: str, login: str, password: str, label: str = "") -> Client:
    """建立帶有 HTTP Basic Auth 的 SOAP client（等同 PHP 端 config/soap_options.php 的設定）。"""
    session = Session()
    session.auth = HTTPBasicAuth(login, password)
    transport = Transport(session=session)
    client = Client(wsdl=wsdl_path, transport=transport)
    print_client_endpoint(client, label)
    return client


def print_client_endpoint(client: Client, label: str):
    """
    印出這份 WSDL 實際解析出來的 SOAP 服務位址(endpoint URL)。
    如果三份 WSDL 的呼叫全部失敗/成功不一致，先比對這裡印出的網址，
    通常就能看出是「打到不同租戶/主機」還是「同一主機但這個服務沒被授權」。
    """
    try:
        for service in client.wsdl.services.values():
            for port in service.ports.values():
                address = port.binding_options.get("address")
                print(f"[{label}] SOAP endpoint = {address}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. 查詢目前狀態：Query Service Products / FindByElements
#    對應 app/Services/ServiceService.php::querySapService()
# ---------------------------------------------------------------------------
def query_service(client: Client, service_id: str):
    request = {
        "ServiceProductSelectionByElements": {
            "SelectionByInternalID": {
                "InclusionExclusionCode": "I",
                "IntervalBoundaryTypeCode": "1",
                "LowerBoundaryInternalID": service_id,
            }
        },
        "ProcessingConditions": {
            "QueryHitsMaximumNumberValue": "1",
            "QueryHitsUnlimitedIndicator": False,
        },
    }
    return client.service.FindByElements(**request)


def get_current_state(query_response):
    """
    把查詢結果整理成 {'sales_orgs': set(...), 'valuation_companies': set(...)}，
    valuation_companies 是這個服務產品「已經啟用估價流程」的公司集合 —
    後面第 3 步寫入估價成本前，要用這個集合判斷目標公司是否需要先啟用。
    """
    products = getattr(query_response, "ServiceProduct", None) or []
    if not products:
        return None

    product = products[0]
    sales_list = getattr(product, "Sales", None) or []
    valuation_list = getattr(product, "Valuation", None) or []
    return {
        "product": product,
        "sales_orgs": {s.SalesOrganisationID for s in sales_list},
        "valuation_companies": {v.CompanyID for v in valuation_list},
        "sales_list": sales_list,
        "valuation_list": valuation_list,
    }


def print_current_state(state):
    """印出查詢結果中既有的 Sales / Valuation 節點，方便下手前先看現況。"""
    if state is None:
        print("[查詢] 找不到這個 service_id 的服務產品資料。")
        return

    print("[查詢] 目前已存在的 Sales(銷售組織)：")
    for sales in state["sales_list"]:
        print(
            f"  - SalesOrganisationID={sales.SalesOrganisationID}, "
            f"DistributionChannelCode={_v(sales.DistributionChannelCode)}, "
            f"LifeCycleStatusCode={sales.LifeCycleStatusCode}"
        )

    print("[查詢] 目前已存在的 Valuation(估價/公司)：")
    for valuation in state["valuation_list"]:
        print(f"  - CompanyID={valuation.CompanyID}, LifeCycleStatusCode={valuation.LifeCycleStatusCode}")


def _v(field):
    """WSDL 裡很多欄位其實是 {'_value_1': 實際值, 'listID': ...} 這種帶屬性的複雜型別，取出實際值方便印。"""
    return getattr(field, "_value_1", field)


# ---------------------------------------------------------------------------
# 2. 新增 Sales：Manage Service Products / MaintainBundle_V1
#    對應 app/Services/ServiceService.php::createSapServiceBasic() 的 Sales 節點
# ---------------------------------------------------------------------------
def add_service_sales(
    client: Client,
    service_id: str,
    sales_org: str,
    distribution_channel_code: str = "01",
    sales_uom: str = "EA",
    item_group_code: str = "SEFL",
    life_cycle_status_code: str = LifeCycleStatusCode.ACTIVE,
):
    """
    對既有 service_id 的服務產品新增一筆 Sales(銷售組織)資料。

        ServiceProductBundleMaintainRequest_sync_V1
          -> BasicMessageHeader.ID
          -> ServiceProduct
               - actionCode: NO_ACTION ('06')   # 服務產品本身不變更
               - InternalID: service_id
               -> Sales                          # 要新增的銷售組織節點
                    - actionCode: CREATE ('01')
                    - SalesOrganisationID / DistributionChannelCode /
                      LifeCycleStatusCode / SalesMeasureUnitCode / ItemGroupCode
    """
    request = {
        "BasicMessageHeader": {"ID": uuid.uuid4().hex.upper()},
        "ServiceProduct": {
            "actionCode": ActionCode.NO_ACTION,
            "InternalID": service_id,
            "Sales": {
                "actionCode": ActionCode.CREATE,
                "SalesOrganisationID": sales_org,
                "DistributionChannelCode": distribution_channel_code,
                "LifeCycleStatusCode": life_cycle_status_code,
                "SalesMeasureUnitCode": sales_uom,
                "ItemGroupCode": item_group_code,
            },
        },
    }
    return client.service.MaintainBundle_V1(**request)


# ---------------------------------------------------------------------------
# 3a. 啟用估價流程：Manage Service Products / MaintainBundle_V1
#     對應 app/Services/ServiceService.php::createSapServiceBasic() 建立服務產品當下，
#     自動幫本國公司加上的 Valuation 節點寫法。
#
#     寫入估價成本(CostRate)之前，SAP 要求該公司必須先在這個服務產品上「啟用估價流程」
#     (只帶 CompanyID + LifeCycleStatusCode，還沒有實際成本)，否則會出現：
#         "Given action code Create is not allowed"
#         "Update not possible; specified data for SERVPROD_VALU_DATA ... does not exist"
#     這裡是對「既有」服務產品、事後幫「另一家公司」補做這個啟用動作，
#     所以 ServiceProduct 根節點 actionCode = NO_ACTION，只有 Valuation 子節點 actionCode = CREATE。
# ---------------------------------------------------------------------------
def activate_service_valuation_company(
    client: Client,
    service_id: str,
    company_id: str,
    life_cycle_status_code: str = LifeCycleStatusCode.IN_PREPARATION,
):
    request = {
        "BasicMessageHeader": {"ID": uuid.uuid4().hex.upper()},
        "ServiceProduct": {
            "actionCode": ActionCode.NO_ACTION,
            "InternalID": service_id,
            "Valuation": {
                "actionCode": ActionCode.CREATE,
                "CompanyID": company_id,
                "LifeCycleStatusCode": life_cycle_status_code,
            },
        },
    }
    return client.service.MaintainBundle_V1(**request)


# ---------------------------------------------------------------------------
# 3b. 寫入 Valuation(估價成本)：Manage Service Product Valuations / MaintainBundle
#    對應 app/Services/ServiceValuationService.php::createSapServiceValuation()
# ---------------------------------------------------------------------------
def add_service_valuation(
    client: Client,
    service_id: str,
    company_id: str,
    account_determination_group: str,
    cost,
    currency: str = "TWD",
    uom: str = "EA",
    start_date: str = None,
):
    """
    寫入(建立/覆蓋)服務產品在指定公司下的估價成本。actionCode 用 SAVE，
    SAP 端會視該筆資料是否已存在自行判斷新增或更新（upsert），
    因此不需要像 Sales 一樣特別區分 CREATE / UPDATE。

        ServiceProductBundleMaintainRequest_sync_V1
          -> BasicMessageHeader.ID
          -> ServiceProductValuationData
               - actionCode: SAVE ('04')
               - ServiceProductInternalID / CompanyID / AccountDeterminationGroupCode
               -> CostRate
                    - actionCode: SAVE ('04')
                    - SetOfBooksID / StartDate
                    -> Amount(cost, currencyCode) / Quantity(1, unitCode)
               -> FinancialProcessInformation
                    - actionCode: UPDATE ('02')
                    - LifeCycleStatusCode: ACTIVE
    """
    start_date = start_date or datetime.date.today().strftime("%Y-%m-%d")

    request = {
        "BasicMessageHeader": {"ID": uuid.uuid4().hex.upper()},
        "ServiceProductValuationData": {
            "actionCode": ActionCode.SAVE,
            "ServiceProductInternalID": service_id,
            "CompanyID": company_id,
            "AccountDeterminationGroupCode": account_determination_group,
            "CostRate": {
                "actionCode": ActionCode.SAVE,
                "SetOfBooksID": SET_OF_BOOKS_ID,
                "StartDate": start_date,
                "Amount": {"_value_1": cost, "currencyCode": currency},
                "Quantity": {"_value_1": 1, "unitCode": uom},
            },
            "FinancialProcessInformation": {
                "actionCode": ActionCode.UPDATE,
                "LifeCycleStatusCode": LifeCycleStatusCode.ACTIVE,
            },
        },
    }
    return client.service.MaintainBundle(**request)


def main():
    parser = argparse.ArgumentParser(description="查詢服務產品現況、新增 Sales，並寫入對應公司的估價成本")
    parser.add_argument("--wsdl", required=True, help="Manage Service Products.wsdl 的路徑或 URL")
    parser.add_argument("--query-wsdl", help="Query Service Products.wsdl 的路徑或 URL（提供才會先查詢現況）")
    parser.add_argument("--valuation-wsdl", help="Manage Service Product Valuations.wsdl 的路徑或 URL（提供才會寫入估價）")

    parser.add_argument("--service-id", help="要操作的 service_id (InternalID)，未提供則互動輸入")
    parser.add_argument("--sales-org", help="要新增的 SalesOrganisationID，未提供則互動輸入")
    parser.add_argument("--distribution-channel", default="01", help="DistributionChannelCode，預設 01")
    parser.add_argument("--sales-uom", default="EA", help="SalesMeasureUnitCode，預設 EA")
    parser.add_argument("--item-group", default="SEFL", help="ItemGroupCode，預設 SEFL")

    parser.add_argument("--company-id", help="估價對應的 CompanyID（例如 OB1000）。與 --valuation-wsdl 一起提供才會寫入估價")
    parser.add_argument("--account-determination-group", help="AccountDeterminationGroupCode（例如 Z006）")
    parser.add_argument("--cost", type=float, help="估價成本金額")
    parser.add_argument("--currency", default="TWD", help="幣別，預設 TWD")
    parser.add_argument("--start-date", help="估價生效日 (YYYY-MM-DD)，預設今天")

    parser.add_argument("--login", default=os.environ.get("BYD_login"), help="SAP ByD 帳號 (預設讀取環境變數 BYD_login)")
    parser.add_argument("--password", default=os.environ.get("BYD_password"), help="SAP ByD 密碼 (預設讀取環境變數 BYD_password)")
    args = parser.parse_args()

    if not args.login or not args.password:
        sys.exit("缺少帳密：請設定 --login/--password 參數，或環境變數 BYD_login / BYD_password")

    service_id = args.service_id or input("請輸入要操作的 service_id：").strip()
    if not service_id:
        sys.exit("service_id 不可為空")

    sales_org = args.sales_org or input("請輸入要新增的 SalesOrganisationID：").strip()
    if not sales_org:
        sys.exit("sales_org 不可為空")

    want_valuation = bool(args.valuation_wsdl and args.company_id)
    if args.valuation_wsdl and not args.company_id:
        sys.exit("有提供 --valuation-wsdl 就必須一併提供 --company-id 才能寫入估價")
    if want_valuation and (args.cost is None or not args.account_determination_group):
        sys.exit("寫入估價需要 --cost 與 --account-determination-group")

    # ---- 先把所有需要的 client 都建好，把三個 endpoint 一次印出來 ----
    # 這樣不管哪一步先失敗，都能立刻比對三個 WSDL 是否指向同一個租戶/主機，
    # 不會因為中途 sys.exit() 而漏看還沒走到的 endpoint 資訊。
    print("=== 各服務的 SOAP endpoint（先比對主機是否一致）===")
    query_client = None
    if args.query_wsdl:
        query_client = build_client(args.query_wsdl, args.login, args.password, label="Query Service Products")

    manage_client = build_client(args.wsdl, args.login, args.password, label="Manage Service Products")

    valuation_client = None
    if want_valuation:
        valuation_client = build_client(
            args.valuation_wsdl, args.login, args.password, label="Manage Service Product Valuations"
        )
    print("=" * 40)

    # ---- 1. 查詢現況（選用） ----
    current_state = None
    if query_client is not None:
        try:
            query_response = query_service(query_client, service_id)
        except Exception as exc:
            sys.exit(f"查詢現況失敗：{exc}")
        current_state = get_current_state(query_response)
        print_current_state(current_state)
    else:
        print("[提示] 未提供 --query-wsdl，略過查詢現況步驟。")

    # ---- 2. 新增 Sales ----
    # 跟第 3 步的 Valuation 啟用一樣：查詢現況已經告訴我們這個 sales_org 存不存在，
    # 存在就直接跳過（SAP 對「已存在的組合又送一次 CREATE」一律回錯，重送沒有意義）；
    # 沒有查詢現況(--query-wsdl 沒給)時才照舊嘗試新增，失敗也只警告、不中斷，
    # 讓整支腳本可以放心重複執行(idempotent)，不會因為「已經做過」就整支中止。
    sales_org_already_exists = bool(current_state and sales_org in current_state["sales_orgs"])

    if sales_org_already_exists:
        print(f"[提示] 銷售組織 {sales_org} 已存在，略過新增 Sales 步驟。")
    else:
        try:
            sales_response = add_service_sales(
                manage_client,
                service_id=service_id,
                sales_org=sales_org,
                distribution_channel_code=args.distribution_channel,
                sales_uom=args.sales_uom,
                item_group_code=args.item_group,
            )
        except Exception as exc:
            print(f"[警告] 新增 Sales 失敗（可能已存在），仍嘗試繼續下一步：{exc}")
        else:
            # zeep 對於 schema 宣告可重複(maxOccurs>1)的節點一律回傳 list，
            # 即使實際上只有 1 筆，也不會像 PHP SoapClient 一樣自動拍平成單一物件，
            # 所以要先取第一筆再檢查 UUID。
            products = getattr(sales_response, "ServiceProduct", None) or []
            first_product = products[0] if products else None
            if getattr(first_product, "UUID", None):
                # Log 只是附加訊息，SeverityCode: 1=成功/資訊, 2=警告, 3=錯誤, 4=嚴重錯誤。
                # 有 UUID 就代表新增已成功，Log 內容(即使有)通常只是提醒事項，不代表失敗。
                for item in (getattr(getattr(sales_response, "Log", None), "Item", None) or []):
                    print(f"[SAP 訊息][Severity={item.SeverityCode}] {item.Note}")
                print(f"[Sales] service_id={service_id} 新增銷售組織={sales_org} 成功，UUID={first_product.UUID}")
            else:
                print(f"[警告] 新增 Sales 回應異常，仍嘗試繼續下一步：{sales_response}")

    # ---- 3. 寫入 Valuation（選用） ----
    if valuation_client is None:
        print("[提示] 未提供 --valuation-wsdl / --company-id，略過寫入估價步驟。")
        return

    # 判斷這家公司是否已在此服務產品上啟用過估價流程：
    #   - 有查詢現況(current_state 不是 None) → 用查詢結果精準判斷
    #   - 沒有查詢現況 → 保守起見，一律先嘗試啟用一次
    # 兩種情況都會走到「先啟用、失敗就當作已啟用過、不中斷、繼續寫入成本」的邏輯，
    # 因為 SAP 對「已啟用的公司又送一次 CREATE」通常也會報錯，不能直接把啟用失敗當硬錯誤。
    company_already_active = bool(current_state and args.company_id in current_state["valuation_companies"])

    if not company_already_active:
        print(f"[提示] {args.company_id} 尚未確認已啟用估價流程，先新增 Valuation 啟用節點...")
        try:
            activate_response = activate_service_valuation_company(manage_client, service_id, args.company_id)
            activated_products = getattr(activate_response, "ServiceProduct", None) or []
            activated_first = activated_products[0] if activated_products else None
            if getattr(activated_first, "UUID", None):
                print(f"[Valuation 啟用] 已為 {args.company_id} 新增估價啟用節點")
            else:
                print(f"[警告] 啟用估價流程回應異常，仍嘗試繼續寫入成本：{activate_response}")
        except Exception as exc:
            print(f"[警告] 啟用估價流程失敗（可能已啟用過），仍嘗試繼續寫入成本：{exc}")

    try:
        valuation_response = add_service_valuation(
            valuation_client,
            service_id=service_id,
            company_id=args.company_id,
            account_determination_group=args.account_determination_group,
            cost=args.cost,
            currency=args.currency,
            uom=args.sales_uom,
            start_date=args.start_date,
        )
    except Exception as exc:
        sys.exit(f"寫入估價失敗：{exc}")

    # 跟 ServiceProduct 一樣，ServiceProductValuationData 在 schema 裡也是可重複節點，
    # zeep 一律回傳 list（即使只有 1 筆），要先取第一筆再檢查 ChangeStateID。
    valuation_products = getattr(valuation_response, "ServiceProductValuationData", None) or []
    first_valuation = valuation_products[0] if valuation_products else None
    if not getattr(first_valuation, "ChangeStateID", None):
        sys.exit(f"寫入估價失敗，SAP 回應異常：{valuation_response}")

    for item in (getattr(getattr(valuation_response, "Log", None), "Item", None) or []):
        print(f"[SAP 訊息][Severity={item.SeverityCode}] {item.Note}")
    print(
        f"[Valuation] service_id={service_id} 公司={args.company_id} "
        f"成本={args.cost} {args.currency} 寫入成功，ChangeStateID={first_valuation.ChangeStateID}"
    )


if __name__ == "__main__":
    main()
