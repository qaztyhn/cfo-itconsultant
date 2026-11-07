"""Xác nhận / từ chối ánh xạ trên PostgreSQL (US-PRD-02 AC1–AC4, US-PRD-03 AC1/AC2, US-PRD-04 AC4; BR-PRD-02).

Dữ liệu chung ở order_rows. Nhân viên 1 là IT (admin); nhân viên 2 dùng cho vai trò khác.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import OrderStatus as S
from app.services import mapping_service as ms
from app.services.order_service import PrepareResult, prepare_for_planning
from tests.integration.conftest import execute, fetch
from tests.integration.order_rows import db, error_of, order_sql, run, status_of, tasks

__all__ = ["db"]  # fixture

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class Actor:
    id: int
    employee_id: int | None
    roles: tuple[str, ...]


IT = Actor(1, 1, ("admin",))
SYSTEM_ADMIN = Actor(9, None, ("admin",))
EXISTING = ms.ConfirmInput(units_to_base=Decimal("40"), global_product_id=1)


def new_global(group: str = "N3", **overrides: object) -> ms.NewGlobal:
    values: dict[str, object] = {
        "code": "G-000500",
        "name": "Cement 25kg",
        "category": "Cement",
        "gtin": "7312345678901",
        "base_unit": "bag",
        "weight_kg": Decimal("25"),
        "volume_m3": Decimal("0.018"),
        "handling_group_code": group,
        "base_units_per_prep_unit": Decimal("40"),
    }
    values.update(overrides)
    return ms.NewGlobal(**values)  # type: ignore[arg-type]


def _prepare(order_id: int) -> Callable[[AsyncSession], Coroutine[Any, Any, PrepareResult]]:
    return lambda s: prepare_for_planning(s, order_id)


def _confirm(dsn: str, actor: Actor, payload: ms.ConfirmInput, task_id: int = 1) -> Callable[[], object]:
    return lambda: run(dsn, lambda s: ms.confirm(s, task_id, actor, payload))


def _reject(dsn: str, actor: Actor, reason: str | None, task_id: int = 1) -> Callable[[], object]:
    return lambda: run(dsn, lambda s: ms.reject(s, task_id, actor, reason))


def blocked(dsn: str, *orders: tuple[int, tuple[str, ...]]) -> None:
    """Tạo đơn SUBMITTED rồi chuẩn bị → BLOCKED_UNMAPPED_SKU + mapping_task (id 1 cho SKU đầu tiên)."""
    for no, skus in orders:
        execute(dsn, *order_sql(no, "SUBMITTED", skus))
        run(dsn, _prepare(no))


def product(dsn: str, sku: str = "SE-NEW-77") -> dict[str, object]:
    return dict(
        fetch(
            dsn,
            "SELECT global_product_id, units_to_base, mapping_status::text AS status, mapped_by, mapped_at "
            "FROM ref.product_se WHERE local_sku = $1",
            sku,
        )[0]
    )


def decisions(dsn: str) -> list[dict[str, object]]:
    sql = (
        "SELECT action, entity, entity_id, actor_employee_id, actor_role, reason_text, before, after "
        "FROM audit.decision_log ORDER BY id"
    )
    return [dict(r) for r in fetch(dsn, sql)]


# --- confirm ---------------------------------------------------------------------------------------------


def test_US_PRD_02_AC1_confirm_does_not_pull_legacy_orders_into_cfo(db: str) -> None:
    """ASM-005 (PR #49): confirm chỉ xác nhận SKU; đơn đã đi quy trình cũ không tự quay lại CFO."""
    blocked(db, (1, ("SE-NEW-77",)), (2, ("SE-NEW-77", "SE-OK-1")))
    result = run(db, lambda s: ms.confirm(s, 1, IT, EXISTING))
    assert result == ms.ConfirmResult(1)
    row = product(db)
    assert (row["global_product_id"], row["units_to_base"], row["status"], row["mapped_by"]) == (
        1,
        Decimal("40.0000"),
        "confirmed",
        1,
    )
    assert row["mapped_at"] is not None
    assert status_of(db, 1)[0] == "BLOCKED_UNMAPPED_SKU" and status_of(db, 2)[0] == "BLOCKED_UNMAPPED_SKU"
    assert fetch(db, "SELECT qty_base FROM ops.order_line WHERE order_id = 1")[0]["qty_base"] is None
    assert fetch(db, "SELECT count(*) AS n FROM plan.planning_run")[0]["n"] == 0  # không lập kế hoạch/giữ chỗ
    assert tasks(db)[0][0::2] == ("SE-NEW-77", "done")


def test_US_PRD_00_new_order_after_confirm_is_eligible(db: str) -> None:
    """Đơn MỚI có 100% SKU confirmed sau khi IT xác nhận thì đi được luồng CFO (US-PRD-00 AC1/AC2)."""
    blocked(db, (1, ("SE-NEW-77",)))
    run(db, lambda s: ms.confirm(s, 1, IT, EXISTING))
    execute(db, *order_sql(2, "SUBMITTED", ("SE-NEW-77",)))
    assert run(db, _prepare(2)).status == S.SUBMITTED
    assert status_of(db, 1)[0] == "BLOCKED_UNMAPPED_SKU"


def test_US_PRD_02_AC1_confirm_leaves_legacy_order_untouched(db: str) -> None:
    blocked(db, (1, ("SE-NEW-77", "SE-REJ")))
    run(db, lambda s: ms.confirm(s, 1, IT, EXISTING))
    assert status_of(db, 1) == ("BLOCKED_UNMAPPED_SKU", "UNMAPPED_SKU: SE-NEW-77, SE-REJ")


def test_US_PRD_02_AC2_non_it_roles_are_forbidden(db: str) -> None:
    blocked(db, (1, ("SE-NEW-77",)))
    for roles in (("dispatcher",), ("warehouse",), ("sales",), ("cs",), ("viewer",)):
        actor = Actor(2, 2, roles)
        assert error_of(_confirm(db, actor, EXISTING)).code == "FORBIDDEN"
        assert error_of(_reject(db, actor, "x")).code == "FORBIDDEN"
    # admin hệ thống không có hồ sơ nhân viên: mapped_by NOT NULL khi confirmed (ck_se_confirmed).
    assert error_of(lambda: run(db, lambda s: ms.confirm(s, 1, SYSTEM_ADMIN, EXISTING))).code == "FORBIDDEN"
    assert product(db)["status"] == "pending" and status_of(db, 1)[0] == "BLOCKED_UNMAPPED_SKU"


def test_US_PRD_02_AC3_create_global_success(db: str) -> None:
    blocked(db, (1, ("SE-NEW-77",)))
    payload = ms.ConfirmInput(units_to_base=Decimal("1"), create_global=new_global(flags=("FRAGILE",)))
    result = run(db, lambda s: ms.confirm(s, 1, IT, payload))
    created = fetch(
        db,
        "SELECT g.code, h.code AS grp, g.flags, g.created_by FROM ref.product_global g "
        "JOIN ref.handling_group h ON h.id = g.handling_group_id WHERE g.id = $1",
        result.global_product_id,
    )[0]
    assert (created["code"], created["grp"], created["flags"], created["created_by"]) == (
        "G-000500",
        "N3",
        ["FRAGILE"],
        1,
    )
    assert product(db)["global_product_id"] == result.global_product_id
    assert status_of(db, 1)[0] == "BLOCKED_UNMAPPED_SKU"


def test_US_PRD_02_AC3_create_global_validation(db: str) -> None:
    blocked(db, (1, ("SE-NEW-77",)))
    cases: list[tuple[ms.ConfirmInput, str]] = [
        (ms.ConfirmInput(units_to_base=Decimal("0"), global_product_id=1), "units_to_base"),
        (ms.ConfirmInput(units_to_base=Decimal("1")), "global_product_id"),
        (
            ms.ConfirmInput(units_to_base=Decimal("1"), global_product_id=1, create_global=new_global()),
            "global_product_id",
        ),
        (ms.ConfirmInput(units_to_base=Decimal("1"), global_product_id=999), "global_product_id"),
        (
            ms.ConfirmInput(
                units_to_base=Decimal("1"), create_global=new_global(base_units_per_prep_unit=None)
            ),
            "create_global.base_units_per_prep_unit",
        ),
        (
            ms.ConfirmInput(units_to_base=Decimal("1"), create_global=new_global(weight_kg=Decimal("0"))),
            "create_global.weight_kg",
        ),
        (
            ms.ConfirmInput(units_to_base=Decimal("1"), create_global=new_global(volume_m3=Decimal("0"))),
            "create_global.volume_m3",
        ),
        (
            ms.ConfirmInput(units_to_base=Decimal("1"), create_global=new_global(base_unit=" ")),
            "create_global.base_unit",
        ),
        (
            ms.ConfirmInput(units_to_base=Decimal("1"), create_global=new_global(group="N9")),
            "create_global.handling_group_code",
        ),
        (
            ms.ConfirmInput(units_to_base=Decimal("1"), create_global=new_global(flags=("NOPE",))),
            "create_global.flags",
        ),
        (
            ms.ConfirmInput(units_to_base=Decimal("1"), create_global=new_global(code="G-1")),
            "create_global.code",
        ),
    ]
    for payload, field_name in cases:
        err = error_of(_confirm(db, IT, payload))
        assert (err.code, err.http_status, err.details) == ("VALIDATION_ERROR", 422, {"field": field_name})
    assert product(db)["status"] == "pending" and decisions(db) == []
    assert fetch(db, "SELECT count(*) AS n FROM ref.product_global")[0]["n"] == 1


def test_US_PRD_02_AC3_line_group_does_not_need_prep_conversion(db: str) -> None:
    blocked(db, (1, ("SE-NEW-77",)))
    payload = ms.ConfirmInput(
        units_to_base=Decimal("1"), create_global=new_global(group="N1", base_units_per_prep_unit=None)
    )
    assert run(db, lambda s: ms.confirm(s, 1, IT, payload)).global_product_id == 2


def test_US_PRD_04_AC4_n6_with_fragile_is_rejected(db: str) -> None:
    blocked(db, (1, ("SE-NEW-77",)))
    payload = ms.ConfirmInput(
        units_to_base=Decimal("1"), create_global=new_global(group="N6", flags=("FRAGILE",))
    )
    err = error_of(lambda: run(db, lambda s: ms.confirm(s, 1, IT, payload)))
    assert (err.code, err.details) == ("VALIDATION_ERROR", {"field": "create_global.flags"})


def test_US_PRD_02_AC4_confirm_logs_before_and_after(db: str) -> None:
    blocked(db, (1, ("SE-NEW-77",)))
    run(db, lambda s: ms.confirm(s, 1, IT, EXISTING))
    [log] = decisions(db)
    assert (log["action"], log["entity"], log["entity_id"], log["actor_employee_id"], log["actor_role"]) == (
        "MAPPING_CONFIRMED",
        "mapping_task",
        "1",
        1,
        "admin",
    )
    assert '"mapping_status": "pending"' in str(log["before"])
    assert '"mapping_status": "confirmed"' in str(log["after"]) and "ready_order_ids" not in str(log["after"])


def test_confirm_unknown_task_is_not_found(db: str) -> None:
    assert error_of(lambda: run(db, lambda s: ms.confirm(s, 42, IT, EXISTING))).code == "NOT_FOUND"


def test_confirm_requires_local_product_in_catalogue(db: str) -> None:
    blocked(db, (1, ("SE-NOT-IN-CATALOGUE",)))
    err = error_of(lambda: run(db, lambda s: ms.confirm(s, 1, IT, EXISTING)))
    assert (err.code, err.details) == ("VALIDATION_ERROR", {"field": "local_sku"})


# --- reject ----------------------------------------------------------------------------------------------


def test_US_PRD_03_AC1_reject_without_reason(db: str) -> None:
    blocked(db, (1, ("SE-NEW-77",)))
    for blank in (None, "", "  "):
        err = error_of(_reject(db, IT, blank))
        assert (err.code, err.http_status) == ("REASON_REQUIRED", 422)
    assert product(db)["status"] == "pending" and decisions(db) == []


def test_US_PRD_03_AC2_reject_keeps_reason_for_it_and_leaves_orders_alone(db: str) -> None:
    """ASM-005: lý do từ chối lưu cho IT (decision_log); không gắn đơn vào hàng đợi Dispatcher."""
    blocked(db, (1, ("SE-NEW-77",)), (2, ("SE-NEW-77", "SE-REJ")))
    before = [status_of(db, i) for i in (1, 2)]
    run(db, lambda s: ms.reject(s, 1, IT, "Discontinued item"))
    assert product(db)["status"] == "rejected"
    assert [status_of(db, i) for i in (1, 2)] == before  # block_reason không đổi
    assert tasks(db)[0][0::2] == ("SE-NEW-77", "done")
    [log] = decisions(db)
    assert (log["action"], log["reason_text"], log["actor_role"]) == (
        "MAPPING_REJECTED",
        "Discontinued item",
        "admin",
    )


def test_reject_resolved_or_confirmed_is_invalid(db: str) -> None:
    """ASM-005: task đã xong không từ chối lại; ánh xạ đã confirmed không từ chối được."""
    blocked(db, (1, ("SE-NEW-77",)))
    run(db, lambda s: ms.reject(s, 1, IT, "Discontinued item"))
    err = error_of(lambda: run(db, lambda s: ms.reject(s, 1, IT, "again")))
    assert (err.code, err.details) == ("VALIDATION_ERROR", {"field": "status"})
    execute(db, "INSERT INTO ref.mapping_task (market_id, local_sku) VALUES (1, 'SE-OK-1')")
    err = error_of(lambda: run(db, lambda s: ms.reject(s, 2, IT, "wrong")))
    assert (err.code, err.details) == ("VALIDATION_ERROR", {"field": "mapping_status"})


def test_confirm_after_reject(db: str) -> None:
    """ASM-005 mục 4: IT có thể xác nhận sau khi đã từ chối; đơn cũ vẫn không quay lại CFO."""
    blocked(db, (1, ("SE-NEW-77",)))
    run(db, lambda s: ms.reject(s, 1, IT, "Need supplier data"))
    assert run(db, lambda s: ms.confirm(s, 1, IT, EXISTING)) == ms.ConfirmResult(1)
    assert product(db)["status"] == "confirmed" and status_of(db, 1)[0] == S.BLOCKED_UNMAPPED_SKU.value
