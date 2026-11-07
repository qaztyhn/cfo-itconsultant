"""Đóng kế hoạch cũ trong cùng transaction với đổi trạng thái (05 mục 6; 09 bất biến 21; US-ORD-04/05).

Đơn 1 (đối tượng): run 1, kế hoạch 1 approved + kế hoạch 3 proposed, giữ chỗ hàng/giờ công/xe committed,
một giữ chỗ hàng đã consumed, chuyến 1 với điểm dừng pending. Đơn 2: kế hoạch 2, giữ chỗ và chuyến riêng —
không bị đụng tới.
"""

from collections.abc import Iterator

import pytest

from app.core.errors import DomainError
from app.domain.enums import OrderStatus as S
from app.domain.transitions import transition
from tests.integration import rows
from tests.integration.conftest import execute, fetch
from tests.integration.order_rows import db as base_db  # noqa: F401  (fixture)
from tests.integration.order_rows import error_of, order_sql, run

pytestmark = pytest.mark.integration


def _order_with_plan(order_id: int, status: str, run_id: int, plan_id: int, vehicle: int) -> list[str]:
    return [
        *order_sql(order_id, status, ()),
        rows.run_sql(order_id, 1),
        rows.plan_sql(run_id, order_id, 1, "approved"),
        rows.plan_vehicle_sql(plan_id, 1, vehicle),
        f"UPDATE ops.customer_order SET approved_plan_id = {plan_id}, committed_date = '2026-11-10', "
        "promise_start = '2026-11-10T08:00Z', promise_end = '2026-11-10T12:00Z' "
        f"WHERE id = {order_id}",
        "INSERT INTO plan.stock_reservation (run_id, order_id, warehouse_id, global_product_id, qty, status) "
        f"VALUES ({run_id}, {order_id}, 1, 1, 5, 'committed')",
        "INSERT INTO plan.prep_reservation (run_id, order_id, warehouse_id, work_date, hours, status) "
        f"VALUES ({run_id}, {order_id}, 1, '2026-11-10', 1.5, 'committed')",
        (
            rows.vehicle_res_sql(run_id, plan_id, plan_id, order_id, vehicle, 1, status="committed")
            if order_id == 1
            else rows.vehicle_res_sql(
                run_id,
                plan_id,
                plan_id,
                order_id,
                vehicle,
                2,
                "[2026-11-11 06:30+00, 2026-11-11 11:00+00)",
                "committed",
            )
        ),
        rows.trip_sql(vehicle),
        rows.stop_sql(order_id, order_id),
    ]


@pytest.fixture
def db(base_db: str) -> Iterator[str]:  # noqa: F811
    execute(
        base_db,
        *_order_with_plan(1, "APPROVED", 1, 1, 1),
        *_order_with_plan(2, "APPROVED", 2, 2, 2),
        rows.plan_sql(1, 1, 2, "proposed"),  # kế hoạch 3: phương án 2 của đơn 1
        "INSERT INTO plan.stock_reservation (run_id, order_id, warehouse_id, global_product_id, qty, status) "
        "VALUES (1, 1, 1, 1, 2, 'consumed')",
    )
    yield base_db


def plan_statuses(dsn: str) -> dict[int, str]:
    return {r["id"]: r["s"] for r in fetch(dsn, "SELECT id, status::text AS s FROM plan.fulfilment_plan")}


def reservation_statuses(dsn: str, order_id: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for table in ("stock_reservation", "prep_reservation", "vehicle_reservation"):
        sql = f"SELECT status::text AS s FROM plan.{table} WHERE order_id = $1 ORDER BY id"
        out[table] = [r["s"] for r in fetch(dsn, sql, order_id)]
    return out


def trip_state(dsn: str, order_id: int) -> tuple[str, str]:
    row = fetch(
        dsn,
        "SELECT s.status AS stop, t.status::text AS trip FROM ops.trip_stop s "
        "JOIN ops.delivery_trip t ON t.id = s.trip_id WHERE s.order_id = $1",
        order_id,
    )[0]
    return row["stop"], row["trip"]


def order_plan_fields(dsn: str, order_id: int) -> tuple[object, ...]:
    row = fetch(
        dsn,
        "SELECT status::text AS s, approved_plan_id, committed_date, promise_start, promise_end "
        "FROM ops.customer_order WHERE id = $1",
        order_id,
    )[0]
    return tuple(row.values())


def test_US_ORD_05_replan_closes_old_plan_in_same_transaction(db: str) -> None:
    result = run(db, lambda s: transition(s, 1, S.SUBMITTED, "dispatcher", "Customer moved the date"))
    assert result.from_status == S.APPROVED and result.closed is not None
    closed = result.closed
    assert closed.superseded_plan_ids == (1, 3)
    assert closed.released == {"stock": 1, "prep": 1, "vehicle": 1}
    assert closed.cancelled_trip_ids == (1,)
    assert closed.before == {
        "approved_plan_id": 1,
        "committed_date": "2026-11-10",
        "promise_start": "2026-11-10T08:00:00+00:00",
        "promise_end": "2026-11-10T12:00:00+00:00",
        "superseded_plan_ids": [1, 3],
    }
    assert plan_statuses(db) == {1: "superseded", 2: "approved", 3: "superseded"}
    assert reservation_statuses(db, 1) == {
        "stock_reservation": ["released", "consumed"],  # consumed giữ nguyên
        "prep_reservation": ["released"],
        "vehicle_reservation": ["released"],
    }
    assert trip_state(db, 1) == ("cancelled", "cancelled")
    assert order_plan_fields(db, 1) == ("SUBMITTED", None, None, None, None)


def test_other_orders_are_untouched(db: str) -> None:
    run(db, lambda s: transition(s, 1, S.SUBMITTED, "dispatcher", "Customer moved the date"))
    assert reservation_statuses(db, 2) == {
        "stock_reservation": ["committed"],
        "prep_reservation": ["committed"],
        "vehicle_reservation": ["committed"],
    }
    assert trip_state(db, 2) == ("pending", "planned")
    assert order_plan_fields(db, 2)[:2] == ("APPROVED", 2)


def test_new_plan_can_be_approved_after_closing(db: str) -> None:
    """ux_one_approved_plan không chặn kế hoạch mới sau khi kế hoạch cũ bị superseded."""
    run(db, lambda s: transition(s, 1, S.SUBMITTED, "dispatcher", "Customer moved the date"))
    execute(db, rows.run_sql(1, 2), rows.plan_sql(3, 1, 1, "approved"))
    assert sorted(plan_statuses(db).values()).count("approved") == 2  # đơn 1 mới + đơn 2


def test_US_ORD_04_cancel_loaded_order_cancels_loading_trip(db: str) -> None:
    execute(
        db,
        "UPDATE ops.customer_order SET status = 'PREPARING' WHERE id = 1",
        "UPDATE ops.customer_order SET status = 'GOODS_READY' WHERE id = 1",
        "UPDATE ops.customer_order SET status = 'LOADED' WHERE id = 1",
        "UPDATE ops.delivery_trip SET status = 'loading' WHERE id = 1",
    )
    run(db, lambda s: transition(s, 1, S.CANCELLED, "dispatcher", "Customer withdrew"))
    assert trip_state(db, 1) == ("cancelled", "cancelled")
    assert order_plan_fields(db, 1) == ("CANCELLED", None, None, None, None)


def test_failed_delivery_requeue_keeps_completed_trip_and_failed_stop(db: str) -> None:
    execute(
        db,
        "UPDATE ops.customer_order SET status = 'PREPARING' WHERE id = 1",
        "UPDATE ops.customer_order SET status = 'GOODS_READY' WHERE id = 1",
        "UPDATE ops.customer_order SET status = 'LOADED' WHERE id = 1",
        "UPDATE ops.customer_order SET status = 'DISPATCHED' WHERE id = 1",
        "UPDATE ops.customer_order SET status = 'FAILED' WHERE id = 1",
        "UPDATE ops.trip_stop SET status = 'failed' WHERE order_id = 1",
        "UPDATE ops.delivery_trip SET status = 'completed' WHERE id = 1",
        "UPDATE plan.stock_reservation SET status = 'consumed' WHERE order_id = 1",
    )
    result = run(db, lambda s: transition(s, 1, S.SUBMITTED, "dispatcher", "Re-deliver"))
    assert result.closed is not None and result.closed.cancelled_trip_ids == ()
    assert result.closed.released == {"stock": 0, "prep": 1, "vehicle": 1}
    assert trip_state(db, 1) == ("failed", "completed")
    assert reservation_statuses(db, 1)["stock_reservation"] == ["consumed", "consumed"]


def test_rejected_transition_closes_nothing(db: str) -> None:
    err: DomainError = error_of(lambda: run(db, lambda s: transition(s, 1, S.SUBMITTED, "dispatcher", " ")))
    assert err.code == "REASON_REQUIRED"
    err = error_of(lambda: run(db, lambda s: transition(s, 1, S.SUBMITTED, "warehouse", "x")))
    assert err.code == "FORBIDDEN"
    assert plan_statuses(db) == {1: "approved", 2: "approved", 3: "proposed"}
    assert order_plan_fields(db, 1)[:2] == ("APPROVED", 1)
    assert trip_state(db, 1) == ("pending", "planned")
