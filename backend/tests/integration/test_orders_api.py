"""API đọc đơn (06 v1.4 mục 5.1–5.4; US-ORD-02 AC1–AC3, US-ORD-06 AC1; BR-ORD-05).

Người dùng ở hr_fixture (hôm nay 2026-11-04, Stockholm). Thêm: nhân viên CS (id 11) gắn vào tài khoản CS
(12), khách SE (1) và ZZ (2), xe V-1 thuộc WH-2. Đơn (market SE trừ khi ghi chú), theo thứ tự đặt:
 2 PLANNED      01/11 08:00  kế hoạch proposed rank 1 từ WH-1 (kho của WAREHOUSE)
 1 SUBMITTED    01/11 09:00  cửa hàng ST-1, sales 6
 3 APPROVED     02/11        kế hoạch approved từ WH-2, chuyến của tài xế 5, rủi ro orange, alert EXCEPTION
 4 DELIVERED    03/11        cửa hàng ST-1, giao hôm nay
 5 BLOCKED      03/11 12:00  cửa hàng ST-1
 6 SUBMITTED    market ZZ
"""

import pytest

from tests.integration import rows
from tests.integration.api_harness import Api, api, assert_error  # noqa: F401  (fixture)
from tests.integration.conftest import execute
from tests.integration.hr_fixture import (
    ADMIN,
    CS,
    DISPATCHER,
    DRIVER,
    SALES,
    SETUP,
    SYSTEM_ADMIN,
    VIEWER,
    WAREHOUSE,
    ZZ_WAREHOUSE,
)

pytestmark = pytest.mark.integration


def _order(
    no: int,
    status: str,
    submitted: str,
    *,
    market: int = 1,
    customer: int = 1,
    store: str = "NULL",
    extra_cols: str = "",
    extra_vals: str = "",
) -> str:
    return (
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, contact_name, "
        "contact_phone, delivery_address, delivery_lat, delivery_lon, date_mode, date_to, order_date, "
        f"currency, submitted_at, status, origin_store_id, total_amount{extra_cols}) VALUES "
        f"('SE-{no:06d}', {market}, 'POS-{no}', {customer}, 'Contact {no}', '+46000{no}', "
        f"'Street {no}, Göteborg', 57.7, 11.9, 'latest', '2026-11-{10 + no}', '{submitted}', 'SEK', "
        f"'{submitted}', '{status}', {store}, {no}00{extra_vals})"
    )


SEED: tuple[str, ...] = (
    "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
    "VALUES (1, 'SE-011', 'Cara', 'Service', 'CUSTOMER_SERVICE', '2025-01-01')",
    "UPDATE ref.app_user SET employee_id = 11 WHERE id = 12",
    "INSERT INTO ref.customer (market_id, external_ref, type, name) VALUES "
    "(1, 'C-1', 'business', 'Nordbygg AB'), (2, 'C-2', 'business', 'Other Co')",
    "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3, "
    "required_licence) VALUES (3, 'V-1', 'TST001', 'Truck 1', 8000, 30, 'C')",
    "INSERT INTO ref.product_global (code, name, category, base_unit, weight_kg, volume_m3, "
    "handling_group_id, flags) VALUES ('G-1', 'Cement', 'Cement', 'bag', 25, 0.02, 3, '{FRAGILE}')",
    "INSERT INTO ref.product_se (local_sku, name, category, sale_unit, units_to_base, unit_price, "
    "global_product_id, mapping_status, mapped_by) VALUES "
    "('SE-CEM', 'Cement 25kg', 'Cement', 'pallet', 40, 950, 1, 'confirmed', 1)",
    _order(
        1, "SUBMITTED", "2026-11-01T09:00Z", store="2", extra_cols=", sales_employee_id", extra_vals=", 6"
    ),
    _order(2, "PLANNED", "2026-11-01T08:00Z"),
    _order(
        3,
        "APPROVED",
        "2026-11-02T08:00Z",
        extra_cols=", committed_date, promise_end",
        extra_vals=", '2026-11-13', '2026-11-13T12:00Z'",
    ),
    _order(
        4,
        "DELIVERED",
        "2026-11-03T08:00Z",
        store="2",
        extra_cols=", delivered_at",
        extra_vals=", '2026-11-04T08:00Z'",
    ),
    _order(
        5,
        "BLOCKED_UNMAPPED_SKU",
        "2026-11-03T12:00Z",
        store="2",
        extra_cols=", block_reason",
        extra_vals=", 'UNMAPPED_SKU: SE-X'",
    ),
    _order(6, "SUBMITTED", "2026-11-01T07:00Z", market=2, customer=2),
    "INSERT INTO ops.order_line (order_id, line_no, local_sku, global_product_id, qty_sale, qty_base, "
    "unit_price, line_total) VALUES (3, 1, 'SE-CEM', 1, 2, 80, 950, 1900), "
    "(1, 1, 'SE-CEM', 1, 1, 40, 950, 950)",
    rows.run_sql(2, 1),
    rows.plan_sql(1, 2, 1, "proposed"),  # kế hoạch 1, WH-1
    rows.run_sql(3, 1),
    rows.plan_sql(2, 3, 1, "approved"),  # kế hoạch 2
    "UPDATE plan.fulfilment_plan SET warehouse_id = 3 WHERE id = 2",
    "UPDATE ops.customer_order SET approved_plan_id = 2 WHERE id = 3",
    "INSERT INTO ops.delivery_trip (warehouse_id, vehicle_id, driver_employee_id, depart_planned_at) "
    "VALUES (3, 1, 5, '2026-11-13T07:00Z')",
    rows.stop_sql(1, 3),
    "INSERT INTO ops.eta_forecast (order_id, version, trigger, planned_eta, forecast_eta, "
    "commitment_deadline, reserve_total_min, slack_min, consumption_pct, risk_status, risk_color) VALUES "
    "(3, 1, 'approval', '2026-11-13T10:00Z', '2026-11-13T10:00Z', '2026-11-13T12:00Z', 120, 120, 10, "
    "'ON_TRACK', 'green'), (3, 2, 'gps', '2026-11-13T10:00Z', '2026-11-13T11:30Z', '2026-11-13T12:00Z', "
    "120, 30, 75, 'AT_RISK', 'orange')",
    "INSERT INTO ops.alert (order_id, market_id, level, type, message, target_roles, dedupe_key) VALUES "
    "(3, 1, 'warning', 'EXCEPTION', 'Shortage', '{dispatcher}', 'ex-3')",
)


@pytest.fixture
def od(api: Api) -> Api:  # noqa: F811
    execute(api.dsn, *SETUP, *SEED)
    return api


def ids(response: object) -> list[int]:
    body = response.json()  # type: ignore[attr-defined]
    assert response.status_code == 200, body  # type: ignore[attr-defined]
    return [item["id"] for item in body["items"]]


# --- phạm vi (06 mục 5.2) ---------------------------------------------------------------------------------


def test_US_ORD_06_AC1_default_order_is_submission_order(od: Api) -> None:
    assert ids(od.get("/orders", DISPATCHER)) == [2, 1, 3, 4, 5]
    assert ids(od.get("/orders", SYSTEM_ADMIN)) == [6, 2, 1, 3, 4, 5]


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        (ADMIN, [2, 1, 3, 4, 5]),
        (CS, [2, 1, 3, 4, 5]),
        (WAREHOUSE, [2]),  # kế hoạch từ WH-1
        (SALES, [1, 4, 5]),  # cửa hàng gốc ST-1
        (DRIVER, [3]),  # chuyến của mình
        (ZZ_WAREHOUSE, []),
    ],
)
def test_US_ORD_02_AC1_scope_by_role(od: Api, user_id: int, expected: list[int]) -> None:
    assert ids(od.get("/orders", user_id)) == expected


def test_viewer_is_forbidden(od: Api) -> None:
    assert_error(od.get("/orders", VIEWER), 403, "FORBIDDEN")
    assert_error(od.get("/orders/1", VIEWER), 403, "FORBIDDEN")
    assert_error(od.get("/orders/counts", VIEWER), 403, "FORBIDDEN")
    assert_error(od.get("/orders", None), 401, "AUTH_INVALID")


@pytest.mark.parametrize(
    ("user_id", "order_id"), [(SALES, 2), (WAREHOUSE, 3), (DRIVER, 1), (ZZ_WAREHOUSE, 1), (DISPATCHER, 6)]
)
def test_US_ORD_02_AC2_out_of_scope_is_404(od: Api, user_id: int, order_id: int) -> None:
    assert_error(od.get(f"/orders/{order_id}", user_id), 404, "NOT_FOUND")


# --- trường theo vai trò (06 mục 5.3) ---------------------------------------------------------------------


def test_full_detail_for_dispatcher(od: Api) -> None:
    r = od.get("/orders/3", DISPATCHER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approved_plan_id"] == 2 and body["latest_run_id"] == 2 and body["external_ref"] == "POS-3"
    assert body["risk"]["color"] == "orange" and body["risk"]["slack_min"] == 30  # bản ETA mới nhất
    assert body["totals"] == {"weight_kg": 2000.0, "volume_m3": 1.6, "amount": "300.00", "currency": "SEK"}
    [line] = body["lines"]
    assert (line["name"], line["sale_unit"], line["global_code"], line["handling_group"], line["flags"]) == (
        "Cement 25kg",
        "pallet",
        "G-1",
        "N3",
        ["FRAGILE"],
    )
    assert body["committed"]["date"] == "2026-11-13" and body["date_request"]["window"] is None
    assert "gps" not in r.text.lower()


def test_store_tier_for_sales_and_cs(od: Api) -> None:
    body = od.get("/orders/1", SALES).json()
    assert "approved_plan_id" not in body and "latest_run_id" not in body
    assert body["totals"] == {"amount": "100.00", "currency": "SEK"}
    assert "handling_group" not in body["lines"][0] and "flags" not in body["lines"][0]
    assert body["sales"] == {"id": 6, "name": "Sam Sales"} and body["origin_store"]["id"] == 2
    cs = od.get("/orders/3", CS).json()
    assert cs["risk"] == {"status": "AT_RISK", "color": "orange", "forecast_eta": "2026-11-13T11:30:00Z"}


def test_driver_tier(od: Api) -> None:
    body = od.get("/orders/3", DRIVER).json()
    for hidden in ("external_ref", "origin_store", "sales", "block_reason", "approved_plan_id", "risk"):
        assert hidden not in body
    assert body["customer"] == {"name": "Nordbygg AB"}
    assert body["date_request"] == {"window": None}
    assert body["totals"] == {"weight_kg": 2000.0, "volume_m3": 1.6}
    assert body["lines"] == [
        {"line_no": 1, "name": "Cement 25kg", "qty_sale": "2.000", "sale_unit": "pallet"}
    ]
    item = od.get("/orders", DRIVER).json()["items"][0]
    assert "total_amount" not in item and "origin_store" not in item and "date_request" not in item


def test_list_item_shape(od: Api) -> None:
    items = {i["id"]: i for i in od.get("/orders", DISPATCHER).json()["items"]}
    assert items[3]["warehouse"] == {"id": 3, "code": "WH-2"} and items[3]["risk_color"] == "orange"
    assert items[2]["warehouse"] == {"id": 1, "code": "WH-1"}  # proposed rank 1
    assert items[1]["site"] == "Göteborg" and items[1]["origin_store"] == {"id": 2, "code": "ST-1"}
    assert items[1]["warehouse"] is None and items[1]["customer_name"] == "Nordbygg AB"
    assert "warehouse" not in od.get("/orders", SALES).json()["items"][0]


# --- lọc và sắp (06 mục 5, 5.4) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"blocked": "true"}, [5]),
        ({"status": "PLANNED,APPROVED"}, [2, 3]),
        ({"risk_color": "orange"}, [3]),
        ({"warehouse_id": 3}, [3]),
        ({"store_id": 2}, [1, 4, 5]),
        ({"q": "nordbygg"}, [2, 1, 3, 4, 5]),
        ({"q": "POS-4"}, [4]),
        ({"committed_date_from": "2026-11-13"}, [3]),
        ({"sort": "-date_to"}, [5, 4, 3, 2, 1]),
        ({"sort": "promise_end"}, [3, 2, 1, 4, 5]),  # NULL cuối, hòa theo thứ tự đặt
        ({"page_size": 2, "page": 2}, [3, 4]),
    ],
)
def test_US_ORD_02_AC3_filters_and_sorting(od: Api, params: dict[str, object], expected: list[int]) -> None:
    assert ids(od.get("/orders", DISPATCHER, **params)) == expected


@pytest.mark.parametrize(
    "params", [{"status": "NOPE"}, {"risk_color": "blue"}, {"date_mode": "x"}, {"sort": "score"}, {"page": 0}]
)
def test_invalid_filters(od: Api, params: dict[str, object]) -> None:
    assert_error(od.get("/orders", DISPATCHER, **params), 422, "VALIDATION_ERROR")


# --- số đếm (06 mục 5.4) ----------------------------------------------------------------------------------


def test_counts_for_dispatcher(od: Api) -> None:
    r = od.get("/orders/counts", DISPATCHER)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "all": 4,  # đơn 5 BLOCKED_UNMAPPED_SKU là legacy (ASM-005), không đếm
        "needs_plan": 1,
        "awaiting_approval": 1,
        "no_feasible_date": 0,
        "in_execution": 1,
        "replan_suggested": 0,
        "delivered_today": 1,
        "nav": {"order_queue": 2, "exceptions": 1, "tracking_risk": 1},
    }


def test_counts_follow_scope(od: Api) -> None:
    sales = od.get("/orders/counts", SALES).json()
    assert (sales["all"], sales["needs_plan"], sales["delivered_today"]) == (2, 1, 1)
    assert sales["nav"] == {"order_queue": 0, "exceptions": 0, "tracking_risk": 0}
    driver = od.get("/orders/counts", DRIVER).json()
    assert (driver["all"], driver["in_execution"], driver["nav"]["exceptions"]) == (1, 1, 1)
