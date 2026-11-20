"""Historical T18 behavior under a test-only router (US-ATP-02/03).

The public Round 3 mount is tested separately in test_t31_api.py.
"""

import json
from uuid import uuid4

import pytest
from fastapi import FastAPI

from app.api.v1.transfers import router as historical_router
from app.core.security import issue_token
from app.deps import AuthUser, DbSession
from app.services import transfer_service
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
    app = api.client.app
    assert isinstance(app, FastAPI)
    app.include_router(historical_router, prefix="/api/v1")

    @app.get("/api/v1/orders/{order_id}/transfer-suggestions")
    async def historical_suggestions(order_id: int, user: AuthUser, db: DbSession) -> dict[str, object]:
        return await transfer_service.suggestions(db, user, order_id)

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


def audit_count(client: Api, action: str) -> int:
    rows = fetch(client.dsn, "SELECT count(*) AS n FROM audit.decision_log WHERE action=$1", action)
    return int(rows[0]["n"])


def audit_rows(client: Api, action: str) -> list[dict[str, object]]:
    def decode(row: dict[str, object]) -> dict[str, object]:
        for column in ("before", "after"):
            if isinstance(row[column], str):  # asyncpg returns raw JSON text without a codec
                row[column] = json.loads(row[column])  # type: ignore[arg-type]
        return row

    return [
        decode(dict(r))
        for r in fetch(
            client.dsn,
            "SELECT actor_user_id,actor_employee_id,actor_role,entity,entity_id,order_id,reason_text,"
            "ts,before,after FROM audit.decision_log WHERE action=$1 ORDER BY id",
            action,
        )
    ]


def status_of(client: Api) -> str:
    return str(fetch(client.dsn, "SELECT status FROM ops.stock_transfer ORDER BY id LIMIT 1")[0]["status"])


FAIL_AUDIT = (
    "CREATE FUNCTION audit.qa_reject() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
    "IF NEW.action = '{action}' THEN RAISE EXCEPTION 'qa: audit insert refused'; END IF; RETURN NEW; END $$",
    "CREATE TRIGGER qa_reject BEFORE INSERT ON audit.decision_log "
    "FOR EACH ROW EXECUTE FUNCTION audit.qa_reject()",
)
DROP_FAIL_AUDIT = ("DROP TRIGGER qa_reject ON audit.decision_log", "DROP FUNCTION audit.qa_reject()")


def test_D1_01_cancel_records_transfer_cancelled_once_in_the_same_transaction(transfer_api: Api) -> None:
    transfer_id = approved(transfer_api)
    key = str(uuid4())
    body = {"reason_text": "  Customer cancelled the transfer  "}
    first = post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, body, key)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "cancelled"
    assert status_of(transfer_api) == "cancelled"
    [row] = audit_rows(transfer_api, "TRANSFER_CANCELLED")
    assert (
        row["actor_role"] == "dispatcher" and row["actor_user_id"] == DISPATCHER and row["actor_employee_id"]
    )
    assert (row["entity"], row["entity_id"], row["order_id"]) == ("stock_transfer", str(transfer_id), 1)
    assert row["reason_text"] == "Customer cancelled the transfer" and row["ts"] is not None
    assert (row["before"]["status"], row["after"]["status"]) == ("approved", "cancelled")  # type: ignore[index]
    assert (
        audit_count(transfer_api, "TRANSFER_APPROVED") == 1
    )  # the original approval only: cancel never reuses it
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.inbound_shipment")[0]["n"] == 0
    again = post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, body, key)
    assert again.status_code == 200 and again.json() == first.json()  # idempotent replay
    assert audit_count(transfer_api, "TRANSFER_CANCELLED") == 1
    other = {"reason_text": "A different reason"}
    assert_error(
        post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, other, key),
        409,
        "IDEMPOTENCY_CONFLICT",
    )
    assert_error(
        post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, body), 409, "ILLEGAL_TRANSITION"
    )
    assert_error(
        post(transfer_api, f"/transfers/{transfer_id}/confirm-source", WAREHOUSE), 409, "ILLEGAL_TRANSITION"
    )
    assert (
        audit_count(transfer_api, "TRANSFER_CANCELLED") == 1
        and audit_count(transfer_api, "TRANSFER_CONFIRMED") == 0
    )
    assert transfer_api.get("/transfers", DISPATCHER, status="cancelled").json()["total"] == 1


@pytest.mark.parametrize("body", [{}, {"reason_text": ""}])
def test_D1_01_cancel_requires_a_reason_at_the_api(transfer_api: Api, body: dict[str, object]) -> None:
    transfer_id = approved(transfer_api)
    assert_error(
        post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, body), 422, "VALIDATION_ERROR"
    )
    assert status_of(transfer_api) == "approved" and audit_count(transfer_api, "TRANSFER_CANCELLED") == 0


def test_D1_01_blank_reason_is_refused_by_the_service(transfer_api: Api) -> None:
    transfer_id = approved(transfer_api)
    blank = {"reason_text": "   "}
    assert_error(
        post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, blank), 422, "REASON_REQUIRED"
    )
    assert status_of(transfer_api) == "approved" and audit_count(transfer_api, "TRANSFER_CANCELLED") == 0


def test_D1_01_cancel_rbac_and_unknown_transfer(transfer_api: Api) -> None:
    transfer_id = approved(transfer_api)
    body = {"reason_text": "No longer needed"}
    for actor in (SALES, WAREHOUSE, 7, ZZ_WAREHOUSE, ADMIN):  # only the dispatcher may cancel (06 section 7)
        assert_error(post(transfer_api, f"/transfers/{transfer_id}/cancel", actor, body), 403, "FORBIDDEN")
    assert_error(post(transfer_api, "/transfers/999/cancel", DISPATCHER, body), 404, "NOT_FOUND")
    assert status_of(transfer_api) == "approved" and audit_count(transfer_api, "TRANSFER_CANCELLED") == 0


def test_D1_01_cancel_rolls_back_when_the_audit_insert_fails(transfer_api: Api) -> None:
    transfer_id = approved(transfer_api)
    execute(transfer_api.dsn, FAIL_AUDIT[0].format(action="TRANSFER_CANCELLED"), FAIL_AUDIT[1])
    key = str(uuid4())
    body = {"reason_text": "Audit will fail"}
    with pytest.raises(Exception):  # noqa: B017, PT011 - the harness re-raises the server error
        post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, body, key)
    assert status_of(transfer_api) == "approved"  # never `cancelled` without its audit row
    execute(transfer_api.dsn, *DROP_FAIL_AUDIT)
    retry = post(transfer_api, f"/transfers/{transfer_id}/cancel", DISPATCHER, body, key)
    assert retry.status_code == 200, retry.text  # the failed attempt did not poison the idempotency key
    assert audit_count(transfer_api, "TRANSFER_CANCELLED") == 1


def test_US_ATP_02_missing_stale_stock_and_no_eligible_order_fail_closed(transfer_api: Api) -> None:
    execute(transfer_api.dsn, "DELETE FROM ops.stock_snapshot WHERE warehouse_id=3")
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", DISPATCHER), 409, "PLAN_NOT_APPROVABLE")
    execute(transfer_api.dsn, "UPDATE ops.stock_snapshot SET as_of='2026-11-01T09:00Z' WHERE warehouse_id=1")
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", DISPATCHER), 409, "PLAN_NOT_APPROVABLE")
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", DISPATCHER), 409, "PLAN_NOT_APPROVABLE")


def test_US_ATP_02_AC3_distinct_key_cannot_approve_same_shortage_twice(transfer_api: Api) -> None:
    body = selection(transfer_api)
    transfer_id = approved(transfer_api)
    assert transfer_id > 0
    assert_error(
        post(transfer_api, "/orders/1/transfers", DISPATCHER, body),
        409,
        "RESOURCE_CONFLICT",
    )
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.stock_transfer")[0]["n"] == 1


def test_US_ATP_02_nonshortage_order_has_no_transfer_suggestions(transfer_api: Api) -> None:
    """Create a separate initially-PLANNED order, never bypass the order transition trigger."""
    execute(
        transfer_api.dsn,
        "INSERT INTO ops.customer_order (order_no,market_id,external_ref,customer_id,"
        "contact_name,delivery_address,delivery_lat,delivery_lon,date_mode,date_to,"
        "order_date,currency,submitted_at,status) VALUES "
        "('SE-T18-PLANNED',1,'POS-T18-PLANNED',1,'Demo','Demo location',59.0,18.0,"
        "'latest','2026-11-10','2026-11-04T09:00:00Z','SEK',"
        "'2026-11-04T09:00:00Z','PLANNED')",
    )
    assert transfer_api.get("/orders/2/transfer-suggestions", DISPATCHER).json() == {"items": []}


def test_T18_mutations_require_valid_idempotency_header(transfer_api: Api) -> None:
    body = selection(transfer_api)
    for headers in ({}, {"Idempotency-Key": "not-a-uuid"}):
        response = transfer_api.client.post(
            "/api/v1/orders/1/transfers",
            headers={"Authorization": "Bearer " + issue_token(DISPATCHER, {}), **headers},
            json=body,
        )
        assert_error(response, 422, "VALIDATION_ERROR")
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.stock_transfer")[0]["n"] == 0


def test_T18_revoke_warehouse_approval_rights_immediately(transfer_api: Api) -> None:
    transfer_id = approved(transfer_api)
    execute(
        transfer_api.dsn,
        "UPDATE hr.location_manager SET can_approve=false " "WHERE location_id=1 AND employee_id=3",
    )
    assert_error(
        post(transfer_api, f"/transfers/{transfer_id}/confirm-source", WAREHOUSE),
        403,
        "FORBIDDEN",
    )
    assert fetch(transfer_api.dsn, "SELECT status FROM ops.stock_transfer")[0]["status"] == "approved"
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.inbound_shipment")[0]["n"] == 0


def test_T18_2_lead_time_default_is_explicit_and_provenance_is_stored(transfer_api: Api) -> None:
    transfer_id = approved(transfer_api)
    suggestion = fetch(transfer_api.dsn, f"SELECT suggestion FROM ops.stock_transfer WHERE id={transfer_id}")[
        0
    ]["suggestion"]
    suggestion = json.loads(suggestion) if isinstance(suggestion, str) else suggestion
    assert suggestion["lead_time_provenance"] == {
        "source": "market_config_default",
        "key": "transfer_lead_days_default",
        "market_id": 1,
        "lead_days": 1,
    }


def test_T18_2_missing_market_lead_default_fails_closed(transfer_api: Api) -> None:
    execute(
        transfer_api.dsn,
        'UPDATE ref.market SET config=\'{"working_days":[1,2,3,4,5],"stale_stock_min":15,'
        '"routing":{"allow_fallback":false}}\' WHERE id=1',
    )
    assert_error(transfer_api.get("/orders/1/transfer-suggestions", DISPATCHER), 409, "PLAN_NOT_APPROVABLE")


def test_T18_concurrent_approvals_with_distinct_keys_create_one_transfer(transfer_api: Api) -> None:
    from concurrent.futures import ThreadPoolExecutor

    body = selection(transfer_api)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: post(transfer_api, "/orders/1/transfers", DISPATCHER, body), range(2))
        )
    assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.stock_transfer")[0]["n"] == 1
    assert audit_count(transfer_api, "TRANSFER_APPROVED") == 1


def test_Q3_cfo_physical_confirmation_and_receipt_are_disabled_and_write_nothing(transfer_api: Api) -> None:
    """DEC-INT-TRANSFER-BOUNDARY: CFO requests transfers; WMS alone executes physical outbound/inbound."""
    transfer_id = approved(transfer_api)
    for path, actor in (("confirm-source", WAREHOUSE), ("receive", 7)):
        assert_error(post(transfer_api, f"/transfers/{transfer_id}/{path}", actor), 409, "ILLEGAL_TRANSITION")
    assert fetch(transfer_api.dsn, "SELECT status FROM ops.stock_transfer")[0]["status"] == "approved"
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.inbound_shipment")[0]["n"] == 0
    assert audit_count(transfer_api, "TRANSFER_CONFIRMED") == 0
    assert audit_count(transfer_api, "TRANSFER_RECEIVED") == 0


def test_Q3_disabled_physical_actions_keep_scope_and_rbac(transfer_api: Api) -> None:
    transfer_id = approved(transfer_api)
    assert_error(post(transfer_api, f"/transfers/{transfer_id}/confirm-source", 7), 404, "NOT_FOUND")
    assert_error(post(transfer_api, f"/transfers/{transfer_id}/receive", WAREHOUSE), 404, "NOT_FOUND")
    assert_error(post(transfer_api, f"/transfers/{transfer_id}/confirm-source", DISPATCHER), 403, "FORBIDDEN")
    assert_error(post(transfer_api, "/transfers/999/receive", 7), 404, "NOT_FOUND")


def test_Q3_a_snapshot_replacement_never_changes_a_requested_transfer_or_adds_inbound(
    transfer_api: Api,
) -> None:
    transfer_id = approved(transfer_api)
    execute(
        transfer_api.dsn,
        "UPDATE ops.stock_snapshot SET on_hand=60, as_of='2026-11-04T09:30:00Z' WHERE warehouse_id=3",
    )
    assert fetch(transfer_api.dsn, "SELECT status FROM ops.stock_transfer")[0]["status"] == "approved"
    assert fetch(transfer_api.dsn, "SELECT count(*) AS n FROM ops.inbound_shipment")[0]["n"] == 0
    assert transfer_id == 1


def test_T18_1_transfer_sourced_inbound_is_never_counted_as_available(transfer_api: Api) -> None:
    from app.services.planning_context import confirmed_inbound
    from tests.integration.test_planning_context_stock import _run

    transfer_id = approved(transfer_api)
    execute(
        transfer_api.dsn,
        "INSERT INTO ops.inbound_shipment (inbound_ref,warehouse_id,global_product_id,qty,eta_date,confirmed,"
        "received,source,transfer_id) VALUES "
        f"('TR-1',3,1,40,'2026-11-12',true,false,'transfer',{transfer_id}), "
        "('ERP-1',3,1,5,'2026-11-12',true,false,'erp',NULL)",
    )
    inbound = _run(transfer_api.dsn, lambda s: confirmed_inbound(s, [3], [1]))
    assert [(i.inbound_ref, i.qty) for i in inbound[3]] == [("ERP-1", 5)]


def test_T18_3_cancel_is_blocked_at_and_after_source_confirmed(transfer_api: Api) -> None:
    transfer_id = approved(transfer_api)
    for status in ("source_confirmed", "received"):
        execute(transfer_api.dsn, f"UPDATE ops.stock_transfer SET status='{status}' WHERE id={transfer_id}")
        assert_error(
            post(
                transfer_api,
                f"/transfers/{transfer_id}/cancel",
                DISPATCHER,
                {"reason_text": "No longer needed"},
            ),
            409,
            "ILLEGAL_TRANSITION",
        )
        assert fetch(transfer_api.dsn, "SELECT status FROM ops.stock_transfer")[0]["status"] == status
    assert audit_count(transfer_api, "TRANSFER_CANCELLED") == 0
