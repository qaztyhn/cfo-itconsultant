"""T18 real-PostgreSQL transfer API tests (US-ATP-02 AC1-3, US-ATP-03 AC1-3)."""

from uuid import uuid4

import pytest

from app.core.security import issue_token
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import ADMIN, DISPATCHER, SALES, SETUP, WAREHOUSE, ZZ_WAREHOUSE

pytestmark = pytest.mark.integration

SEED = (
    'UPDATE ref.market SET config=\'{"working_days":[1,2,3,4,5],"transfer_lead_days_default":1,'
    '"stale_stock_min":15,"routing":{"allow_fallback":false}}\' WHERE id=1',
    "INSERT INTO ref.customer (market_id, external_ref, type, name) "
    "VALUES (1,'SRC-C','business','Synthetic customer')",
    "INSERT INTO ref.product_global (code,name,category,base_unit,weight_kg,volume_m3,handling_group_id) "
    "VALUES ('G-T18','Synthetic goods','Goods','pcs',1,0.01,1)",
    "INSERT INTO ops.customer_order (order_no,market_id,external_ref,customer_id,contact_name,"
    "delivery_address,delivery_lat,delivery_lon,date_mode,date_to,order_date,currency,submitted_at,status) "
    "VALUES ('SE-T18',1,'POS-T18',1,'Demo contact','Demo location',59.0,18.0,'latest',"
    "'2026-11-10','2026-11-04T09:00:00Z','SEK','2026-11-04T09:00:00Z','NO_FEASIBLE_DATE')",
    "INSERT INTO ops.order_line (order_id,line_no,local_sku,global_product_id,qty_sale,qty_base,"
    "unit_price,line_total) VALUES (1,1,'SE-T18',1,60,60,1,60)",
    "INSERT INTO plan.planning_run (order_id,order_version,run_no,kind,input_snapshot,"
    "result,failed_check) VALUES (1,1,1,'initial','{}','infeasible','stock')",
    "INSERT INTO ops.stock_snapshot (warehouse_id,global_product_id,on_hand,wms_reserved,as_of) "
    "VALUES (1,1,50,0,'2026-11-04T09:00:00Z'),(3,1,20,0,'2026-11-04T09:00:00Z')",
    "INSERT INTO plan.route_matrix (warehouse_id,to_lat,to_lon,distance_km,duration_min,provider) "
    "VALUES (1,57.7,11.9,430.00,310,'ors')",
    "UPDATE ref.app_user SET roles='{warehouse}' WHERE id=7",
    "UPDATE hr.location_manager SET valid_to=NULL WHERE location_id=3 AND employee_id=7",
)


@pytest.fixture
def transfer_api(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP, *SEED)
    return api


def post(client: Api, path: str, actor: int, body: dict[str, object] | None = None, key: str | None = None):
    return client.client.post(
        "/api/v1" + path,
        headers={"Authorization": "Bearer " + issue_token(actor, {}), "Idempotency-Key": key or str(uuid4())},
        json=body,
    )


def selection(client: Api) -> dict[str, object]:
    response = client.get("/orders/1/transfer-suggestions", DISPATCHER)
    assert response.status_code == 200, response.text
    [candidate] = response.json()["items"]
    assert candidate["distance_km"] == "430.00"
    assert candidate["route_provenance"] == "ors"
    return {k: candidate[k] for k in ("from_warehouse_id", "to_warehouse_id", "lead_days", "lines")}


def approved(client: Api) -> int:
    response = post(client, "/orders/1/transfers", DISPATCHER, selection(client))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    return response.json()["id"]


def test_US_ATP_02_AC1_AC2_only_verified_shortage_and_ors_routes(transfer_api: Api) -> None:
    candidate = selection(transfer_api)
    assert candidate == {
        "from_warehouse_id": 1,
        "to_warehouse_id": 3,
        "lead_days": 1,
        "lines": [{"global_product_id": 1, "qty": "40.000"}],
    }
    execute(transfer_api.dsn, "DELETE FROM plan.route_matrix WHERE warehouse_id=1")
    assert transfer_api.get("/orders/1/transfer-suggestions", DISPATCHER).json() == {"items": []}
    assert_error(post(transfer_api, "/orders/1/transfers", DISPATCHER, candidate), 409, "PLAN_NOT_APPROVABLE")


def test_US_ATP_02_AC3_approve_audits_once_with_idempotent_replay(transfer_api: Api) -> None:
    body = selection(transfer_api)
    key = str(uuid4())
    first = post(transfer_api, "/orders/1/transfers", DISPATCHER, body, key)
    assert first.status_code == 200, first.text
    again = post(transfer_api, "/orders/1/transfers", DISPATCHER, body, key)
    assert again.status_code == 200 and again.json() == first.json()
    assert_error(
        post(transfer_api, "/orders/1/transfers", DISPATCHER, {**body, "lead_days": 2}, key),
        409,
        "IDEMPOTENCY_CONFLICT",
    )
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.stock_transfer")[0]["n"] == 1
    assert (
        fetch(
            transfer_api.dsn,
            "SELECT count(*) AS n FROM audit.decision_log " "WHERE action='TRANSFER_APPROVED'",
        )[0]["n"]
        == 1
    )
    assert first.json()["expected_arrival_date"] == "2026-11-05"


def test_US_ATP_03_AC1_AC3_source_confirm_and_dest_receive_in_one_transaction(
    transfer_api: Api,
) -> None:
    transfer_id = approved(transfer_api)
    assert_error(post(transfer_api, f"/transfers/{transfer_id}/confirm-source", 7), 403, "FORBIDDEN")
    confirmed = post(transfer_api, f"/transfers/{transfer_id}/confirm-source", WAREHOUSE)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "source_confirmed"
    inbound = fetch(
        transfer_api.dsn, "SELECT source,confirmed,received,qty,eta_date FROM ops.inbound_shipment"
    )
    assert [(x["source"], x["confirmed"], x["received"], x["qty"]) for x in inbound] == [
        ("transfer", True, False, 40)
    ]
    assert_error(post(transfer_api, f"/transfers/{transfer_id}/receive", WAREHOUSE), 403, "FORBIDDEN")
    received = post(transfer_api, f"/transfers/{transfer_id}/receive", 7)
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "received"
    assert fetch(transfer_api.dsn, "SELECT received FROM ops.inbound_shipment")[0]["received"] is True
    assert (
        fetch(
            transfer_api.dsn,
            "SELECT count(*) AS n FROM audit.decision_log " "WHERE action='TRANSFER_CONFIRMED'",
        )[0]["n"]
        == 2
    )
    assert_error(
        post(
            transfer_api,
            f"/transfers/{transfer_id}/cancel",
            DISPATCHER,
            {"reason_text": "No longer required"},
        ),
        409,
        "ILLEGAL_TRANSITION",
    )


def test_US_ATP_03_AC2_RBAC_location_scope_and_market(transfer_api: Api) -> None:
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", SALES), 403, "FORBIDDEN")
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", ZZ_WAREHOUSE), 403, "FORBIDDEN")
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", ADMIN), 403, "FORBIDDEN")
    assert_error(post(transfer_api, "/orders/1/transfers", SALES, selection(transfer_api)), 403, "FORBIDDEN")
    transfer_id = approved(transfer_api)
    assert_error(transfer_api.get("/transfers", SALES), 403, "FORBIDDEN")
    assert_error(transfer_api.get("/transfers", ZZ_WAREHOUSE, warehouse_id=1), 404, "NOT_FOUND")
    assert transfer_api.get("/transfers", DISPATCHER).json()["total"] == 1
    assert transfer_api.get("/transfers", WAREHOUSE).json()["total"] == 1
    assert transfer_api.get("/transfers", 7).json()["total"] == 1
    assert transfer_api.get("/transfers", DISPATCHER, status="cancelled").json()["total"] == 0
    assert_error(transfer_api.get("/transfers", DISPATCHER, status="UNKNOWN"), 422, "VALIDATION_ERROR")
    assert_error(post(transfer_api, f"/transfers/{transfer_id}/receive", SALES), 403, "FORBIDDEN")


def test_US_ATP_02_AC3_cancel_with_reason_and_reject_invalid_transitions(
    transfer_api: Api,
) -> None:
    transfer_id = approved(transfer_api)
    assert_error(
        post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, {}), 422, "VALIDATION_ERROR"
    )
    key = str(uuid4())
    response = post(
        transfer_api,
        f"/transfers/{transfer_id}/cancel",
        DISPATCHER,
        {"reason_text": "Customer cancelled transfer"},
        key,
    )
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    same = post(
        transfer_api,
        f"/transfers/{transfer_id}/cancel",
        DISPATCHER,
        {"reason_text": "Customer cancelled transfer"},
        key,
    )
    assert same.json() == response.json()
    assert_error(
        post(transfer_api, f"/transfers/{transfer_id}/confirm-source", WAREHOUSE), 409, "ILLEGAL_TRANSITION"
    )
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.inbound_shipment")[0]["n"] == 0


def test_US_ATP_02_missing_stale_stock_and_no_eligible_order_fail_closed(transfer_api: Api) -> None:
    execute(transfer_api.dsn, "DELETE FROM ops.stock_snapshot WHERE warehouse_id=3")
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", DISPATCHER), 409, "PLAN_NOT_APPROVABLE")
    execute(transfer_api.dsn, "UPDATE ops.stock_snapshot SET as_of='2026-11-01T09:00Z' WHERE warehouse_id=1")
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", DISPATCHER), 409, "PLAN_NOT_APPROVABLE")
    execute(transfer_api.dsn, "UPDATE ops.customer_order SET status='PLANNED' WHERE id=1")
    assert transfer_api.get("/orders/1/transfer-suggestions", DISPATCHER).json() == {"items": []}
