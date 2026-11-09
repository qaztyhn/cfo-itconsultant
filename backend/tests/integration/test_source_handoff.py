"""PostgreSQL guard tests for Dev 1's explicit routed Source -> CFO acceptance.

These invoke the real transactional service with typed synthetic Source snapshots.
Dev 2 separately owns the authenticated Source GET / sync-now HTTP integration.
"""

import pytest

from app.adapters.order_wire import SourceOrder
from app.core.errors import DomainError
from app.deps import CurrentUser
from app.services.source_handoff import accept_source_order
from tests.integration.conftest import execute, fetch
from tests.integration.dev2_helpers import transact
from tests.integration.test_ingest_orders import db as db  # noqa: F401 (PostgreSQL fixture)
from tests.integration.test_ingest_orders import source
from tests.integration.test_ingest_references import mapped

pytestmark = pytest.mark.integration
DISPATCHER = CurrentUser(
    id=1, employee_id=1, roles=("dispatcher",), market="SE", location_ids=(2,)
)
SALES = CurrentUser(
    id=1, employee_id=1, roles=("sales",), market="SE", location_ids=(2,)
)
OTHER_STORE = CurrentUser(
    id=1, employee_id=1, roles=("sales",), market="SE", location_ids=(1,)
)
VIEWER = CurrentUser(
    id=1, employee_id=1, roles=("viewer",), market="SE", location_ids=(2,)
)


def accept(
    dsn: str, raw: dict[str, object], key: str, actor: CurrentUser = DISPATCHER
) -> dict[str, object]:
    typed = SourceOrder.model_validate(raw)
    return transact(
        dsn, lambda session: accept_source_order(session, actor, typed, key)
    )


def test_US_INT_01_AC1_explicit_cfo_route_order_lines_audit_and_replay(db: str) -> None:
    mapped(db)
    first = accept(db, source(version=2), "source-1")
    assert (
        first["routing_status"], first["sync_status"], first["already_decided"]
    ) == (
        "cfo", "synced", False
    )
    assert first["order_id"] is not None
    assert accept(db, source(version=2), "source-1") == first
    second = accept(db, source(version=2), "source-2")
    assert second["order_id"] == first["order_id"]
    assert second["sync_status"] == "already_current"
    assert second["already_decided"] is True
    assert tuple(fetch(db, """
        SELECT route,reason_code,decided_by_user_id,decided_by_role,decided_source_version
        FROM ops.order_routing
    """)[0]) == ("cfo", "all_confirmed", 1, "dispatcher", 2)
    assert tuple(fetch(db, """
        SELECT market_id,external_ref,source_version,status,origin_store_id,total_amount
        FROM ops.customer_order
    """)[0]) == (1, "EXT-1", 2, "SUBMITTED", 2, 2.25)
    assert fetch(db, "SELECT count(*) FROM ops.order_line")[0][0] == 1
    assert (
        fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='ROUTING_DECIDED'")[0][0]
        == 1
    )
    assert fetch(db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 2


def test_DEC_ROUTING_002_legacy_is_immutable_even_after_mapping_confirmed(
    db: str,
) -> None:
    mapped(db)
    execute(
        db,
        "INSERT INTO ref.product_se(local_sku,name,category,sale_unit,units_to_base,unit_price) "
        "VALUES('P-PENDING','Synthetic','Test','pcs',1,0)",
    )
    raw = source(
        version=2,
        lines=[{"line_no": 1, "sku": "P-PENDING", "qty": "2.000", "unit_price": "1.00"}],
    )
    result = accept(db, raw, "legacy-1", SALES)
    assert result["routing_status"] == "legacy" and result["order_id"] is None
    assert not fetch(db, "SELECT id FROM ops.customer_order")
    execute(
        db,
        "UPDATE ref.product_se SET mapping_status='confirmed',global_product_id=1,mapped_by=1 "
        "WHERE local_sku='P-PENDING'",
    )
    again = accept(db, source(**{**raw, "version": 3}), "legacy-2", SALES)
    assert (again["routing_status"], again["already_decided"]) == ("legacy", True)
    assert not fetch(db, "SELECT id FROM ops.customer_order")
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='ROUTING_DECIDED'")[0][0] == 1


def test_DEC_ROUTING_002_unknown_catalog_is_unresolved_not_legacy(db: str) -> None:
    mapped(db)
    raw = source(
        lines=[{"line_no": 1, "sku": "P-MISSING", "qty": "1.000", "unit_price": "1.00"}]
    )
    unresolved = accept(db, raw, "check-1")
    assert (
        unresolved["routing_status"] == "unresolved" and unresolved["order_id"] is None
    )
    assert not fetch(db, "SELECT * FROM ops.order_routing")
    assert not fetch(db, "SELECT * FROM ops.customer_order")
    execute(
        db,
        "INSERT INTO ref.product_se(local_sku,name,category,sale_unit,units_to_base,unit_price,"
        "global_product_id,mapping_status,mapped_by) "
        "VALUES('P-MISSING','Synthetic','Test','pcs',1,1,1,'confirmed',1)",
    )
    recovered = accept(db, raw, "check-1")
    assert recovered["routing_status"] == "cfo" and recovered["order_id"] is not None


@pytest.mark.parametrize("actor", [VIEWER, OTHER_STORE])
def test_US_INT_01_AC4_forbidden_roles_or_other_store_never_create_a_route(
    db: str, actor: CurrentUser
) -> None:
    mapped(db)
    with pytest.raises(DomainError) as exc:
        accept(db, source(), "wrong-scope", actor)
    assert exc.value.http_status == (403 if actor == VIEWER else 404)
    assert not fetch(db, "SELECT * FROM ops.order_routing")
    assert not fetch(db, "SELECT * FROM ops.customer_order")


def test_US_INT_01_AC2_newer_source_updates_only_existing_cfo_record(db: str) -> None:
    mapped(db)
    created = accept(db, source(version=2), "src-2")
    changed = accept(db, source(version=3, address="Revised synthetic site"), "src-3")
    assert changed["order_id"] == created["order_id"]
    assert (changed["routing_status"], changed["sync_status"]) == (
        "cfo", "already_current"
    )
    assert tuple(fetch(db, """
        SELECT source_version,version,delivery_address FROM ops.customer_order
    """)[0]) == (3, 2, "Revised synthetic site")
    assert fetch(db, "SELECT count(*) FROM ops.order_line")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM audit.decision_log WHERE action='ROUTING_DECIDED'")[0][0] == 1
    with pytest.raises(DomainError) as exc:
        accept(db, source(version=1), "src-old")
    assert exc.value.code == "RESOURCE_CONFLICT"


def test_US_INT_01_AC4_idempotency_key_cannot_be_reused_for_another_source(
    db: str,
) -> None:
    mapped(db)
    accept(db, source(version=2), "key-one")
    with pytest.raises(DomainError) as exc:
        accept(db, source(2, version=2), "key-one")
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 1


def test_DEC_ROUTING_002_duplicate_sku_is_rejected_before_route_write(db: str) -> None:
    mapped(db)
    with pytest.raises(DomainError) as exc:
        accept(
            db,
            source(lines=[
                {"line_no": 1, "sku": "P1", "qty": "1", "unit_price": "1.00"},
                {"line_no": 2, "sku": "P1", "qty": "1", "unit_price": "1.00"},
            ]),
            "dupe-sku",
        )
    assert exc.value.http_status == 422
    assert not fetch(db, "SELECT * FROM ops.order_routing")
    assert not fetch(db, "SELECT * FROM ops.customer_order")
