"""Approved synthetic orders for the real-browser Prep Queue walkthrough."""

from app.core.security import hash_password
from tests.integration import rows
from tests.integration.conftest import execute, fetch
from tests.integration.hr_fixture import SETUP

APP_NOW = "2026-11-10T10:06:00+01:00"
BUSINESS_DATE = APP_NOW[:10]
TIME_ZONE = "Europe/Stockholm"
WAREHOUSE_EMAIL = "wm@cfo.test"
CS_EMAIL = "cs@cfo.test"
DRIVER_EMAILS = ("driver-placeholder@cfo.test", "e3-driver-two@cfo.test")


def vehicle_code(trip_id: int) -> str:
    return f"E3-TRUCK-{trip_id}"


def seed_approved_order(dsn: str, trip_count: int, password: str) -> str:
    order_no = f"SE-E3-{trip_count}T"
    execute(
        dsn,
        *SETUP,
        "INSERT INTO ref.customer (market_id, external_ref, type, name) "
        "VALUES (1, 'E3-CLIENT', 'business', 'Synthetic client')",
        "INSERT INTO ref.product_global (code, name, category, base_unit, weight_kg, volume_m3, "
        "handling_group_id) SELECT 'E3-GOODS', 'Synthetic pallet', 'Demo', 'pcs', 5000, 20, id "
        "FROM ref.handling_group WHERE code='N6'",
        "INSERT INTO ops.customer_order (order_no, market_id, external_ref, customer_id, "
        "contact_name, delivery_address, delivery_lat, delivery_lon, date_mode, date_to, "
        "order_date, currency, submitted_at, status, approved_at, committed_date, "
        "promise_start, promise_end) "
        f"VALUES ('{order_no}', 1, 'E3-ORDER', 1, 'Demo recipient', 'Synthetic delivery site', 59, 18, "
        "'latest', '2026-11-10', '2026-11-04T09:00Z', 'SEK', '2026-11-04T09:00Z', 'APPROVED', "
        "'2026-11-04T10:00Z', '2026-11-10', '2026-11-10T10:00Z', '2026-11-10T13:00Z')",
        "INSERT INTO ops.order_line (order_id, line_no, local_sku, global_product_id, qty_sale, qty_base, "
        f"unit_price, line_total) SELECT 1, 1, 'E3-PALLET', id, {trip_count}, {trip_count}, "
        f"1, {trip_count} FROM ref.product_global WHERE code='E3-GOODS'",
        rows.run_sql(1, 1),
        rows.plan_sql(1, 1, 1, "approved"),
        "UPDATE ops.customer_order SET approved_plan_id=1 WHERE id=1",
        f"UPDATE plan.fulfilment_plan SET vehicle_count={trip_count}, "
        f"total_capacity_kg={9000 * trip_count}, total_capacity_m3={30 * trip_count}, "
        "workload=jsonb_build_object('planned_start_prep','2026-11-10T09:05:00Z'), "
        "goods_ready_at='2026-11-10T09:12Z', loading_start_at='2026-11-10T09:15Z', "
        "depart_at='2026-11-10T09:45Z', eta_at='2026-11-10T11:45Z', trip_end_at='2026-11-10T13:45Z' "
        "WHERE id=1",
    )
    if trip_count == 2:
        execute(
            dsn,
            "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, "
            "position_code, hire_date) "
            "VALUES (1, 'E3-D2', 'Synthetic', 'DriverTwo', 'DRIVER', '2025-01-01')",
            "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date) "
            "VALUES (11, 1, '2025-01-01')",
            "INSERT INTO hr.driver_staff (employee_id, home_warehouse_id, licence_class, licence_expires_on) "
            "VALUES (11, 1, 'CE', '2027-01-31')",
            "INSERT INTO ref.app_user (employee_id, email, password_hash, roles) "
            f"VALUES (11, '{DRIVER_EMAILS[1]}', 'pending-hash', '{{driver}}')",
        )
    for seq, driver_id in enumerate((5, 11)[:trip_count], start=1):
        code = vehicle_code(seq)
        execute(
            dsn,
            "INSERT INTO ref.vehicle (home_warehouse_id, code, plate, name, capacity_kg, capacity_m3, "
            f"required_licence) VALUES (1, '{code}', 'E3-PLATE-{seq}', '{code}', 9000, 30, 'C')",
            rows.plan_vehicle_sql(1, seq, seq, driver_id),
            "UPDATE plan.plan_vehicle SET load_kg=5000, load_m3=20, "
            "load_lines=jsonb_build_array(jsonb_build_object('line_no',1,'qty_base','1')), "
            "loading_start_at='2026-11-10T09:15Z', depart_at='2026-11-10T09:45Z', "
            "eta_at='2026-11-10T11:45Z', trip_end_at='2026-11-10T13:45Z' "
            f"WHERE id={seq}",
            "INSERT INTO ops.delivery_trip (plan_vehicle_id, warehouse_id, vehicle_id, driver_employee_id, "
            f"depart_planned_at) VALUES ({seq}, 1, {seq}, {driver_id}, '2026-11-10T09:45Z')",
            "INSERT INTO ops.trip_stop (trip_id, seq, order_id, eta_planned_at) "
            f"VALUES ({seq}, 1, 1, '2026-11-10T11:45Z')",
        )
    # CS must have a real Sweden-market employee scope. This synthetic fixture
    # mirrors test_orders_api's scoped employee binding and grants no new role.
    execute(
        dsn,
        "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, "
        "position_code, hire_date) VALUES "
        "(1, 'E3-CS', 'Synthetic', 'Service', 'CUSTOMER_SERVICE', '2025-01-01')",
        "UPDATE ref.app_user SET employee_id=(SELECT id FROM hr.employee "
        "WHERE employee_no='E3-CS') WHERE id=12",
        "INSERT INTO hr.cs_staff(employee_id) SELECT id FROM hr.employee WHERE employee_no='E3-CS'",
    )
    updated = fetch(
        dsn,
        "UPDATE ref.app_user SET password_hash=$1 WHERE email=ANY($2::text[]) RETURNING id",
        hash_password(password),
        [WAREHOUSE_EMAIL, CS_EMAIL, *DRIVER_EMAILS[:trip_count]],
    )
    assert len(updated) == 2 + trip_count
    return order_no
