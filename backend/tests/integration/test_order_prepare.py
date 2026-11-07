"""transition() và prepare_for_planning trên PostgreSQL.

US-PRD-01 AC1/AC2; FR-PRD-02; 05 mục 6; 09 bất biến 12.

Market 1 = SE (seed 0008). rows.REF_HR: nhân viên 1, product_global 1 (G-1). Danh mục SE:
SE-OK-1 confirmed (G-1, units_to_base 2.5), SE-NEW-77 pending, SE-REJ rejected.
"""

from collections.abc import Callable
from decimal import Decimal

import pytest

from app.domain.enums import OrderStatus as S
from app.domain.transitions import Transitioned, transition
from app.services import mapping_service
from app.services.order_service import prepare_for_planning
from tests.integration.conftest import execute, fetch
from tests.integration.order_rows import db, error_of, order_sql, run, status_of, tasks

__all__ = ["db"]  # fixture

pytestmark = pytest.mark.integration


# --- prepare_for_planning -------------------------------------------------------------------------------


def test_US_PRD_01_AC1_unmapped_sku_blocks_order_and_creates_task(db: str) -> None:
    execute(db, *order_sql(1, "SUBMITTED", ("SE-OK-1", "SE-NEW-77")))
    result = run(db, lambda s: prepare_for_planning(s, 1))
    assert result.status == S.BLOCKED_UNMAPPED_SKU and result.unmapped_skus == ("SE-NEW-77",)
    status, reason = status_of(db, 1)
    assert status == "BLOCKED_UNMAPPED_SKU" and reason is not None and "SE-NEW-77" in reason
    assert "SE-OK-1" not in reason
    assert tasks(db) == [("SE-NEW-77", 1, "open")]
    lines = fetch(db, "SELECT local_sku, global_product_id, qty_base FROM ops.order_line ORDER BY line_no")
    assert (lines[0]["global_product_id"], lines[0]["qty_base"]) == (1, Decimal("10.000"))
    assert (lines[1]["global_product_id"], lines[1]["qty_base"]) == (None, None)


def test_US_PRD_01_AC2_two_orders_share_one_task(db: str) -> None:
    execute(
        db, *order_sql(1, "SUBMITTED", ("SE-NEW-77",)), *order_sql(2, "SUBMITTED", ("SE-NEW-77", "SE-OK-1"))
    )
    run(db, lambda s: prepare_for_planning(s, 1))
    run(db, lambda s: prepare_for_planning(s, 2))
    assert tasks(db) == [("SE-NEW-77", 2, "open")]


def test_US_PRD_01_AC2_recount_does_not_double_count(db: str) -> None:
    execute(db, *order_sql(1, "SUBMITTED", ("SE-NEW-77",)))
    run(db, lambda s: prepare_for_planning(s, 1))
    run(db, lambda s: mapping_service.ensure_task(s, 1, "SE-NEW-77"))
    assert tasks(db) == [("SE-NEW-77", 1, "open")]


def test_US_PRD_01_all_lines_mapped_stays_submitted_with_qty_base(db: str) -> None:
    execute(db, *order_sql(1, "SUBMITTED", ("SE-OK-1",)))
    result = run(db, lambda s: prepare_for_planning(s, 1))
    assert result.status == S.SUBMITTED and result.unmapped_skus == ()
    assert status_of(db, 1) == ("SUBMITTED", None)
    assert fetch(db, "SELECT qty_base FROM ops.order_line")[0]["qty_base"] == Decimal("10.000")
    assert tasks(db) == []


def test_US_PRD_03_AC2_rejected_and_unknown_skus_keep_order_blocked(db: str) -> None:
    execute(db, *order_sql(1, "SUBMITTED", ("SE-REJ", "SE-NOT-IN-CATALOGUE")))
    result = run(db, lambda s: prepare_for_planning(s, 1))
    assert result.unmapped_skus == ("SE-REJ", "SE-NOT-IN-CATALOGUE")
    assert [t[:2] for t in tasks(db)] == [("SE-NOT-IN-CATALOGUE", 1), ("SE-REJ", 1)]


def test_prepare_rejects_order_not_submitted(db: str) -> None:
    execute(db, *order_sql(1, "PLANNED", ("SE-NEW-77",)))
    err = error_of(lambda: run(db, lambda s: prepare_for_planning(s, 1)))
    assert (err.code, err.http_status) == ("ILLEGAL_TRANSITION", 409)
    assert status_of(db, 1) == ("PLANNED", None) and tasks(db) == []


def test_prepare_unknown_order_is_not_found(db: str) -> None:
    assert error_of(lambda: run(db, lambda s: prepare_for_planning(s, 999))).code == "NOT_FOUND"


# --- transition() --------------------------------------------------------------------------------------


def test_transition_allowed_pair_and_role_updates_status(db: str) -> None:
    execute(db, *order_sql(1, "PLANNED", ()))
    result = run(db, lambda s: transition(s, 1, S.APPROVED, "dispatcher"))
    assert (result.from_status, result.closed) == (S.PLANNED, None) and status_of(db, 1)[0] == "APPROVED"


def test_transition_pair_not_in_table_is_illegal(db: str) -> None:
    execute(db, *order_sql(1, "SUBMITTED", ()))
    err = error_of(lambda: run(db, lambda s: transition(s, 1, S.DELIVERED, "driver")))
    assert (err.code, err.http_status) == ("ILLEGAL_TRANSITION", 409)
    assert err.details == {"from_status": "SUBMITTED", "to_status": "DELIVERED"}
    assert status_of(db, 1)[0] == "SUBMITTED"


def test_transition_wrong_role_is_forbidden(db: str) -> None:
    execute(db, *order_sql(1, "SUBMITTED", ()), *order_sql(2, "PLANNED", ()))
    # SUBMITTED → PLANNED chỉ hệ thống (allowed_roles rỗng, ASM-002).
    assert error_of(lambda: run(db, lambda s: transition(s, 1, S.PLANNED, "dispatcher"))).code == "FORBIDDEN"
    # PLANNED → APPROVED chỉ dispatcher; hệ thống không được tự duyệt (09 bất biến 1).
    assert error_of(lambda: run(db, lambda s: transition(s, 2, S.APPROVED, "system"))).code == "FORBIDDEN"
    assert error_of(lambda: run(db, lambda s: transition(s, 2, S.APPROVED, "warehouse"))).code == "FORBIDDEN"
    assert (status_of(db, 1)[0], status_of(db, 2)[0]) == ("SUBMITTED", "PLANNED")


def _cancel(dsn: str, order_id: int, reason: str | None) -> Callable[[], Transitioned]:
    return lambda: run(dsn, lambda s: transition(s, order_id, S.CANCELLED, "dispatcher", reason))


def test_transition_missing_reason_is_rejected(db: str) -> None:
    execute(db, *order_sql(1, "NO_FEASIBLE_DATE", ()))
    for blank in (None, "", "   "):
        err = error_of(_cancel(db, 1, blank))
        assert (err.code, err.http_status) == ("REASON_REQUIRED", 422)
    assert status_of(db, 1)[0] == "NO_FEASIBLE_DATE"


def test_transition_with_reason_succeeds(db: str) -> None:
    execute(db, *order_sql(1, "NO_FEASIBLE_DATE", ()))
    run(db, lambda s: transition(s, 1, S.CANCELLED, "dispatcher", "Customer withdrew"))
    assert status_of(db, 1)[0] == "CANCELLED"


def test_transition_unknown_order_is_not_found(db: str) -> None:
    assert error_of(lambda: run(db, lambda s: transition(s, 999, S.PLANNED, "system"))).code == "NOT_FOUND"
