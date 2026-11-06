"""Dữ liệu tối thiểu cho test ràng buộc (giả lập, không PII thật, không mật khẩu — 09 bất biến 25).

Không dùng thay seed demo của Dev 2 (`seed/generate_data.py`); chỉ đủ để chèn bản ghi phụ thuộc khóa ngoài.
"""

REF_HR = (
    "INSERT INTO ref.market (code, name, timezone, currency) VALUES ('ZZ', 'Test market', 'UTC', 'EUR')",
    "INSERT INTO hr.position (code, name, grp) VALUES ('TEST_POS', 'Test position', 'central')",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
    "VALUES (1, 'warehouse', 'WH-1', 'Warehouse 1', 59.3, 18.0, '15:00')",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon) "
    "VALUES (1, 'store', 'ST-1', 'Store 1', 59.4, 18.1)",
    "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
    "VALUES (1, 'E1', 'Test', 'One', 'TEST_POS', '2026-01-01')",
    "INSERT INTO ref.app_user (employee_id, email, password_hash, roles) "
    "VALUES (1, 'user1@cfo.test', 'not-a-real-hash', '{dispatcher}')",
    "INSERT INTO ref.customer (market_id, external_ref, type, name) "
    "VALUES (1, 'C-1', 'business', 'Test customer')",
    "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3, "
    "required_licence) VALUES (1, 'V-1', 'TST001', 'Truck 1', 8000, 30, 'C')",
    "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3, "
    "required_licence) VALUES (1, 'V-2', 'TST002', 'Truck 2', 8000, 30, 'C')",
    "INSERT INTO ref.handling_group (code, name, prep_unit, labour_hours_per_unit) "
    "VALUES ('T1', 'Test', 'line', 0.05)",
    "INSERT INTO ref.product_global (code, name, category, base_unit, weight_kg, volume_m3, "
    "handling_group_id) VALUES ('G-1', 'Test product', 'Test', 'pcs', 1, 0.01, 1)",
)


def order_sql(
    no: int,
    *,
    date_mode: str = "exact",
    date_from: str | None = "2026-11-10",
    date_to: str = "2026-11-10",
    window: tuple[str, str] | None = None,
) -> str:
    """INSERT một đơn (market 1, khách 1) với yêu cầu ngày tùy chỉnh."""
    df = f"'{date_from}'" if date_from else "NULL"
    ws, we = (f"'{window[0]}'", f"'{window[1]}'") if window else ("NULL", "NULL")
    return (
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, contact_name, "
        "delivery_address, delivery_lat, delivery_lon, date_mode, date_from, date_to, window_start, "
        "window_end, order_date, currency, submitted_at) VALUES "
        f"('ZZ-{no:06d}', 1, 'EXT-{no}', 1, 'Contact', 'Address', 59.0, 18.0, '{date_mode}', {df}, "
        f"'{date_to}', {ws}, {we}, '2026-11-04T09:00Z', 'EUR', '2026-11-04T09:00Z')"
    )


def trip_sql(vehicle_id: int) -> str:
    return (
        "INSERT INTO ops.delivery_trip (warehouse_id, vehicle_id, driver_employee_id, depart_planned_at) "
        f"VALUES (1, {vehicle_id}, 1, '2026-11-10T07:00Z')"
    )


def stop_sql(trip_id: int, order_id: int, seq: int = 1) -> str:
    return (
        "INSERT INTO ops.trip_stop (trip_id, seq, order_id, eta_planned_at) "
        f"VALUES ({trip_id}, {seq}, {order_id}, '2026-11-10T09:00Z')"
    )


def pod_sql(stop_id: int, order_id: int, result: str, failure_reason: str | None = None) -> str:
    fr = f"'{failure_reason}'" if failure_reason else "NULL"
    return (
        "INSERT INTO ops.proof_of_delivery (trip_stop_id, order_id, result, completed_at, failure_reason) "
        f"VALUES ({stop_id}, {order_id}, '{result}', '2026-11-10T09:30Z', {fr})"
    )


def event_sql(order_id: int, event_type: str, key: str) -> str:
    return (
        "INSERT INTO ops.milestone_event (order_id, event_type, occurred_at, actor_user_id, idempotency_key) "
        f"VALUES ({order_id}, '{event_type}', '2026-11-10T06:00Z', 1, '{key}')"
    )


def alert_sql(key: str) -> str:
    return (
        "INSERT INTO ops.alert (market_id, level, type, message, target_roles, dedupe_key) "
        f"VALUES (1, 'warning', 'RISK_ORANGE', 'Test', '{{dispatcher}}', '{key}')"
    )
