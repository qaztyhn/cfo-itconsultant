"""P0 actual PostgreSQL planner after governed Source -> CFO stock ingestion.

Remove the existing fixture stock row, then ingest only through the reviewed
T07 writer. No fake CFO stock insert or governance bypass is used.
"""

import pytest

from app.deps import CurrentUser
from app.services import planning_service, stock_scope_service
from tests.integration.conftest import execute, fetch
from tests.integration.dev2_helpers import transact
from tests.integration.test_demo_standard_planning import DISPATCHER
from tests.integration.test_demo_standard_planning import standard_order as standard_order  # noqa: F401
from tests.integration.test_ingest_stock import run_stock, snapshot
from tests.integration.test_ingest_orders import db as db  # noqa: F401

pytestmark = pytest.mark.integration


def test_source_stock_ingestion_then_real_planning_service(standard_order: str) -> None:
    execute(
        standard_order,
        "DELETE FROM ops.stock_snapshot WHERE warehouse_id=1 AND global_product_id=1",
        "INSERT INTO hr.employee (market_id,employee_no,first_name,last_name,position_code,hire_date) "
        "VALUES (1,'STOCK-ADMIN-A','Synthetic','Admin','TEST_POS','2026-01-01'),"
        "(1,'STOCK-ADMIN-B','Synthetic','Approver','TEST_POS','2026-01-01')",
        "INSERT INTO ref.app_user (employee_id,email,password_hash,roles) "
        "VALUES (3,'stock.admin.a@example.test','fake-only','{admin}'),"
        "(4,'stock.admin.b@example.test','fake-only','{admin}')",
        "INSERT INTO ref.stock_admin_grant (market_id,user_id,capability,valid_from,granted_by,reason_text) "
        "VALUES (1,2,'scope','2026-11-01T00:00:00Z',1,'Test-only authorized governance bootstrap'),"
        "(1,3,'scope','2026-11-01T00:00:00Z',1,'Test-only authorized governance bootstrap')",
    )
    author = CurrentUser(id=2, employee_id=3, roles=("admin",), market="SE", location_ids=())
    approver = CurrentUser(id=3, employee_id=4, roles=("admin",), market="SE", location_ids=())

    async def create(session) -> int:
        scope = await stock_scope_service.create_scope(
            session,
            author,
            skus=["P1"],
            warehouse_ids=[1],
            reason_text="Reviewed isolated source stock ingestion",
        )
        return scope.id

    scope_id = transact(standard_order, create)
    transact(standard_order, lambda s: stock_scope_service.approve_scope(s, approver, scope_id))

    outcome, usable = run_stock(
        standard_order,
        snapshot(
            items=[
                {
                    "warehouse_code": "WH-1",
                    "sku": "P1",
                    "on_hand": "100.000",
                    "reserved": "0.000",
                }
            ]
        ),
    )
    assert outcome.status == "ok"
    assert usable is True
    rows = fetch(
        standard_order,
        "SELECT on_hand,wms_reserved FROM ops.stock_snapshot " "WHERE warehouse_id=1 AND global_product_id=1",
    )
    assert len(rows) == 1 and tuple(rows[0]) == (100, 0)
    assert (
        fetch(standard_order, "SELECT count(*) FROM ops.stock_write_run WHERE status='accepted'")[0][0] == 1
    )

    run_id = transact(standard_order, lambda s: planning_service.plan(1, DISPATCHER, {}, session=s))
    result = fetch(standard_order, "SELECT result FROM plan.planning_run WHERE id=$1", run_id)[0][0]
    assert result == "feasible"
    assert fetch(standard_order, "SELECT status FROM ops.customer_order WHERE id=1")[0][0] == "PLANNED"
