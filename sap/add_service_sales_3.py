"""
為既有的 SAP ByDesign 服務產品(Service Product)新增 Sales(銷售組織)資料，
並寫入該銷售組織對應公司的估價(Valuation)資料。

【修正說明】
1. 執行順序調整：1. 查詢 -> 2. 寫入/啟用 Valuation -> 3. 新增 Sales
   先啟用 Valuation 即可避免在新增 Sales 時出現財務流程未啟用的提示警示。
2. 階層式 ActionCode 配合：
   - 根節點 (ServiceProductValuationData)：固定使用 ActionCode.SAVE ('04')，作為父階資料建立與變更的通用指令[cite: 3]。
   - 子節點 (CostRate / FinancialProcessInformation)：
     根據步驟 1 查詢到的既有公司估價清單動態判定：
     * 若公司尚未建立 Valuation 資料：使用 ActionCode.CREATE ('01')[cite: 3]
     * 若公司已存在 Valuation 資料：使用 ActionCode.UPDATE ('02')[cite: 3]
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


class ActionCode:
    CREATE = "01"
    UPDATE = "02"
    DELETE = "03"
    SAVE = "04"
    REMOVE = "05"
    NO_ACTION = "06"


class LifeCycleStatusCode:
    IN_PREPARATION = "1"
    ACTIVE = "2"


SET_OF_BOOKS_ID = "7000"


def build_client(wsdl_path: str, login: str, password: str, label: str = "") -> Client:
    session = Session()
    session.auth = HTTPBasicAuth(login, password)
    transport = Transport(session=session)
    client = Client(wsdl=wsdl_path, transport=transport)
    print_client_endpoint(client, label)
    return client


def print_client_endpoint(client: Client, label: str):
    try:
        for service in client.wsdl.services.values():
            for port in service.ports.values():
                address = port.binding_options.get("address")
                print(f"[{label}] SOAP endpoint = {address}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. 查詢目前狀態：Query Service Products / FindByElements
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


def print_current_state(query_response):
    products = getattr(query_response, "ServiceProduct", None) or []
    if not products:
        print("[查詢] 找不到這個 service_id 的服務產品資料。")
        return

    product = products[0]
    print("[查詢] 目前已存在的 Sales(銷售組織)：")
    for sales in (getattr(product, "Sales", None) or []):
        print(
            f"  - SalesOrganisationID={sales.SalesOrganisationID}, "
            f"DistributionChannelCode={_v(sales.DistributionChannelCode)}, "
            f"LifeCycleStatusCode={sales.LifeCycleStatusCode}"
        )

    print("[查詢] 目前已存在的 Valuation(估價/公司)：")
    for valuation in (getattr(product, "Valuation", None) or []):
        print(f"  - CompanyID={valuation.CompanyID}, LifeCycleStatusCode={valuation.LifeCycleStatusCode}")


def _v(field):
    return getattr(field, "_value_1", field)


# ---------------------------------------------------------------------------
# 2. 寫入 Valuation(估價成本)：Manage Service Product Valuations / MaintainBundle
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
    is_update: bool = False,
):
    """
    寫入服務產品在指定公司下的估價成本。
    - 根節點固定使用 ActionCode.SAVE ('04')。
    - 子節點根據公司是否存在，動態傳入 ActionCode.CREATE ('01') 或 ActionCode.UPDATE ('02')。
    """
    start_date = start_date or datetime.date.today().strftime("%Y-%m-%d")

    # 根節點固定帶入 SAVE
    #action_code = ActionCode.SAVE
    # 內部子節點的 actionCode：不存在時用 CREATE ('01')，已存在時用 UPDATE ('02')
    sub_action_code = ActionCode.UPDATE if is_update else ActionCode.CREATE

    request = {
        "BasicMessageHeader": {"ID": uuid.uuid4().hex.upper()},
        "ServiceProductValuationData": {
            "actionCode": ActionCode.SAVE,
            "ServiceProductInternalID": service_id,
            "CompanyID": company_id,
            "AccountDeterminationGroupCode": account_determination_group,
            "CostRate": {
                "actionCode": sub_action_code,
                "SetOfBooksID": SET_OF_BOOKS_ID,
                "StartDate": start_date,
                "Amount": {"_value_1": cost, "currencyCode": currency},
                "Quantity": {"_value_1": 1, "unitCode": uom},
            },
            "FinancialProcessInformation": {
                "actionCode": sub_action_code,
                "LifeCycleStatusCode": LifeCycleStatusCode.ACTIVE,
            },
        },
    }
    return client.service.MaintainBundle(**request)


# ---------------------------------------------------------------------------
# 3. 新增 Sales：Manage Service Products / MaintainBundle_V1
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


def main():
    parser = argparse.ArgumentParser(description="查詢服務產品現況、寫入估價成本，並新增 Sales")
    parser.add_argument("--wsdl", required=True, help="Manage Service Products.wsdl 的路徑或 URL")
    parser.add_argument("--query-wsdl", help="Query Service Products.wsdl 的路徑或 URL")
    parser.add_argument("--valuation-wsdl", help="Manage Service Product Valuations.wsdl 的路徑或 URL")

    parser.add_argument("--service-id", help="要操作的 service_id (InternalID)")
    parser.add_argument("--sales-org", help="要新增的 SalesOrganisationID")
    parser.add_argument("--distribution-channel", default="01", help="DistributionChannelCode，預設 01")
    parser.add_argument("--sales-uom", default="EA", help="SalesMeasureUnitCode，預設 EA")
    parser.add_argument("--item-group", default="SEFL", help="ItemGroupCode，預設 SEFL")

    parser.add_argument("--company-id", help="估價對應的 CompanyID（例如 OB1000）")
    parser.add_argument("--account-determination-group", help="AccountDeterminationGroupCode（例如 Z006）")
    parser.add_argument("--cost", type=float, help="估價成本金額")
    parser.add_argument("--currency", default="TWD", help="幣別，預設 TWD")
    parser.add_argument("--start-date", help="估價生效日 (YYYY-MM-DD)，預設今天")

    parser.add_argument("--login", default=os.environ.get("BYD_login"), help="SAP ByD 帳號")
    parser.add_argument("--password", default=os.environ.get("BYD_password"), help="SAP ByD 密碼")
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

    print("=== 各服務的 SOAP endpoint ===")
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

    # ---- 1. 查詢現況 ----
    query_response = None
    if query_client is not None:
        try:
            query_response = query_service(query_client, service_id)
            print_current_state(query_response)
        except Exception as exc:
            sys.exit(f"查詢現況失敗：{exc}")
    else:
        print("[提示] 未提供 --query-wsdl，略過查詢現況步驟。")

    # ---- 判斷目標公司是否已經存在於估價資料中 ----
    is_company_valuation_exists = False
    if query_response is not None:
        products = getattr(query_response, "ServiceProduct", None) or []
        if products:
            existing_valuations = getattr(products[0], "Valuation", None) or []
            is_company_valuation_exists = any(
                getattr(val, "CompanyID", None) == args.company_id for val in existing_valuations
            )

    # ---- 2. 寫入/啟用 Valuation（先執行估價寫入，確保財務/評價資料已建立） ----
    if valuation_client is not None:
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
                is_update=is_company_valuation_exists,  # 自動傳入 True/False 判定
            )
        except Exception as exc:
            sys.exit(f"寫入估價失敗：{exc}")

        valuation_data = getattr(valuation_response, "ServiceProductValuationData", None)
        if not valuation_data or not getattr(
            valuation_data[0] if isinstance(valuation_data, list) else valuation_data, "ChangeStateID", None
        ):
            sys.exit(f"寫入估價失敗，SAP 回應異常：{valuation_response}")

        for item in (getattr(getattr(valuation_response, "Log", None), "Item", None) or []):
            print(f"[SAP 訊息][Severity={item.SeverityCode}] {item.Note}")
        print(
            f"[Valuation] service_id={service_id} 公司={args.company_id} "
            f"成本={args.cost} {args.currency} 寫入成功！"
        )
    else:
        print("[提示] 未提供 --valuation-wsdl / --company-id，略過寫入估價步驟。")

    # ---- 3. 新增 Sales（評價流程啟用後，再新增銷售組織） ----
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
        sys.exit(f"新增 Sales 失敗：{exc}")

    products = getattr(sales_response, "ServiceProduct", None) or []
    first_product = products[0] if products else None
    if not getattr(first_product, "UUID", None):
        sys.exit(f"新增 Sales 失敗，SAP 回應異常：{sales_response}")

    for item in (getattr(getattr(sales_response, "Log", None), "Item", None) or []):
        print(f"[SAP 訊息][Severity={item.SeverityCode}] {item.Note}")
    print(f"[Sales] service_id={service_id} 新增銷售組織={sales_org} 成功，UUID={first_product.UUID}")


if __name__ == "__main__":
    main()