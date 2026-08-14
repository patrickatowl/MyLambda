"""
以 service_id 為現有的 SAP ByDesign 服務產品(Service Product)新增一筆 Sales(銷售組織)資料。

對應 ERP_api 專案中 app/Services/ServiceService.php::createSapServiceBasic() 的
Sales 節點寫法，但這裡假設 ServiceProduct 本身已存在(不重新建立整個產品)，
只針對既有產品「新增」一筆 Sales 子節點，因此：
    - ServiceProduct 根節點 actionCode = NO_ACTION ('06')  # 對象本身不變更
    - Sales 子節點     actionCode = CREATE     ('01')       # 新增這筆銷售組織資料

- SAP ByD Web Service:  "Manage Service Products"
- SOAP 操作 (Operation): MaintainBundle_V1
- 認證方式: SOAP 層 HTTP Basic Auth (帳密即 .env 的 BYD_login / BYD_password)
"""

import argparse
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


def build_client(wsdl_path: str, login: str, password: str) -> Client:
    """建立帶有 HTTP Basic Auth 的 SOAP client（等同 PHP 端 config/soap_options.php 的設定）。"""
    session = Session()
    session.auth = HTTPBasicAuth(login, password)
    transport = Transport(session=session)
    return Client(wsdl=wsdl_path, transport=transport)


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

    對應 PHP 端的參數結構：
        ServiceProductBundleMaintainRequest_sync_V1
          -> BasicMessageHeader.ID              # 任意不重複的訊息 ID
          -> ServiceProduct
               - actionCode:    NO_ACTION ('06')  # 服務產品本身不變更
               - InternalID:    service_id        # 指定要操作的既有服務產品
               -> Sales                            # 要新增的銷售組織節點
                    - actionCode:            CREATE ('01')
                    - SalesOrganisationID:   sales_org
                    - DistributionChannelCode: distribution_channel_code
                    - LifeCycleStatusCode:   life_cycle_status_code
                    - SalesMeasureUnitCode:  sales_uom
                    - ItemGroupCode:         item_group_code
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

    response = client.service.MaintainBundle_V1(**request)
    return response


def main():
    parser = argparse.ArgumentParser(description="為既有的 SAP ByDesign 服務產品新增一筆 Sales(銷售組織)資料")
    parser.add_argument("--wsdl", required=True, help="Manage Service Products.wsdl 的路徑或 URL")
    parser.add_argument("--service-id", required=False, help="要新增 Sales 的 service_id (InternalID)，未提供則互動輸入")
    parser.add_argument("--sales-org", required=False, help="要新增的 SalesOrganisationID，未提供則互動輸入")
    parser.add_argument("--distribution-channel", default="01", help="DistributionChannelCode，預設 01")
    parser.add_argument("--sales-uom", default="EA", help="SalesMeasureUnitCode，預設 EA")
    parser.add_argument("--item-group", default="SEFL", help="ItemGroupCode，預設 SEFL")
    parser.add_argument("--login", default=os.environ.get("BYD_login"), help="SAP ByD 帳號 (預設讀取環境變數 BYD_login)")
    parser.add_argument("--password", default=os.environ.get("BYD_password"), help="SAP ByD 密碼 (預設讀取環境變數 BYD_password)")
    args = parser.parse_args()

    if not args.login or not args.password:
        sys.exit("缺少帳密：請設定 --login/--password 參數，或環境變數 BYD_login / BYD_password")

    service_id = args.service_id or input("請輸入要新增 Sales 的 service_id：").strip()
    if not service_id:
        sys.exit("service_id 不可為空")

    sales_org = args.sales_org or input("請輸入要新增的 SalesOrganisationID：").strip()
    if not sales_org:
        sys.exit("sales_org 不可為空")

    client = build_client(args.wsdl, args.login, args.password)

    try:
        response = add_service_sales(
            client,
            service_id=service_id,
            sales_org=sales_org,
            distribution_channel_code=args.distribution_channel,
            sales_uom=args.sales_uom,
            item_group_code=args.item_group,
        )
    except Exception as exc:
        sys.exit(f"新增失敗：{exc}")

    if not getattr(getattr(response, "ServiceProduct", None), "UUID", None):
        sys.exit(f"新增失敗，SAP 回應異常：{response}")

    print(f"service_id={service_id} 新增 Sales(銷售組織={sales_org}) 成功")
    print(response)


if __name__ == "__main__":
    main()