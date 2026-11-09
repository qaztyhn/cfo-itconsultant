"""S1-S5 (DEC-OWNER-20261109): stock scope / independence evidence governance on real PostgreSQL."""

import asyncio
from collections.abc import Callable, Coroutine, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core import clock
from app.deps import CurrentUser
from app.services import stock_scope_service as svc
from app.services.stock_scope_service import StockScopeError
from tests.integration import rows
from tests.integration.conftest import alembic_config, async_url, execute, fetch, rejects
from tests.integration.order_rows import product_sql

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 9, 9, 0, tzinfo=UTC)


def _user(
    user_id: int, role: str, employee: int, *, market: str = "SE", wh: tuple[int, ...] = ()
) -> CurrentUser:
    return CurrentUser(id=user_id, employee_id=employee, roles=(role,), market=market, location_ids=wh)


ADMIN_A = _user(2, "admin", 2)  # holds scope + evidence grants
ADMIN_B = _user(3, "admin", 3)  # holds scope + evidence grants
ADMIN_C = _user(4, "admin", 4)  # admin role only, no grant
MANAGER = _user(5, "warehouse", 5, wh=(1,))
OTHER_MANAGER = _user(6, "warehouse", 6, wh=(2,))
DISPATCHER = _user(1, "dispatcher", 1)


@pytest.fixture
def db(empty_db: str) -> Iterator[str]:
    command.upgrade(alembic_config(empty_db), "head")
    clock.set_now(NOW)
    emp = "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, hire_date) "
    execute(
        empty_db,
        *rows.REF_HR,
        "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
        "VALUES (1,'warehouse','WH-2','W2',59,18,'15:00')",
        *(emp + f"VALUES (1,'E{n}','T','T{n}','TEST_POS','2026-01-01')" for n in (3, 4, 5, 6)),
        *(
            f"INSERT INTO ref.app_user (employee_id, email, password_hash, roles) VALUES "
            f"({n}, 'u{n}@cfo.test', 'x', '{{{role}}}')"
            for n, role in ((2, "admin"), (3, "admin"), (4, "admin"), (5, "warehouse"), (6, "warehouse"))
        ),
        product_sql("A", "confirmed", "1", "1"),
        product_sql("B", "confirmed", "1", "1"),
        product_sql("C", "confirmed", "1", "1"),
        # bootstrap runbook: the first grants are inserted directly, never through the service
        *(
            "INSERT INTO ref.stock_admin_grant (market_id,user_id,capability,valid_from,granted_by,"
            "reason_text) "
            f"VALUES (1,{uid},'{cap}','2026-11-01T00:00Z',1,'bootstrap runbook')"
            for uid in (2, 3)
            for cap in ("scope", "evidence")
        ),
    )
    try:
        yield empty_db
    finally:
        clock.set_now(None)


def run[T](dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async def go() -> T:
        engine = create_async_engine(async_url(dsn), poolclass=NullPool)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


async def _id(awaitable: Coroutine[Any, Any, Any]) -> int:
    """Read the primary key inside the transaction (instances are detached after commit)."""
    return int((await awaitable).id)


def fails(dsn: str, fn: Callable[[AsyncSession], Coroutine[Any, Any, Any]], code: str) -> StockScopeError:
    with pytest.raises(StockScopeError) as caught:
        run(dsn, fn)
    assert caught.value.code == code
    return caught.value


def _scope(db: str, author: CurrentUser = ADMIN_A, approver: CurrentUser | None = ADMIN_B) -> int:
    scope_id = run(
        db,
        lambda s: _create(s, author),
    )
    if approver is not None:
        run(db, lambda s: svc.approve_scope(s, approver, scope_id))
    return scope_id


async def _create(s: AsyncSession, actor: CurrentUser) -> int:
    row = await svc.create_scope(
        s, actor, skus=["A", "B", "C"], warehouse_ids=[1, 2], reason_text="Pilot scope"
    )
    return row.id


def audit(db: str, action: str) -> int:
    return fetch(db, f"SELECT count(*) AS n FROM audit.decision_log WHERE action='{action}'")[0]["n"]


# --- S1 ----------------------------------------------------------------------------------------------


def test_S1_admin_role_alone_or_other_roles_cannot_manage_scope(db: str) -> None:
    for actor in (ADMIN_C, DISPATCHER, MANAGER):
        fails(db, lambda s, a=actor: _create(s, a), "FORBIDDEN")
    assert fetch(db, "SELECT count(*) AS n FROM ops.stock_scope_version")[0]["n"] == 0


def test_S1_grant_is_market_specific_expiring_and_revocable(db: str) -> None:
    execute(db, "INSERT INTO ref.market (code,name,timezone,currency) VALUES ('YY','Other','UTC','EUR')")
    other_market_admin = _user(2, "admin", 2, market="YY")  # same user, but no YY grant
    fails(db, lambda s: _create(s, other_market_admin), "FORBIDDEN")
    execute(db, "UPDATE ref.stock_admin_grant SET valid_to='2026-11-09T08:00Z' WHERE user_id=2")  # expired
    fails(db, lambda s: _create(s, ADMIN_A), "FORBIDDEN")
    # revocation: B revokes nothing of its own; A (expired) cannot grant, B grants C, then revokes
    grant = run(
        db,
        lambda s: _id(
            svc.grant_admin(s, ADMIN_B, user_id=4, capability="scope", reason_text="Backup approver")
        ),
    )
    run(db, lambda s: _create(s, ADMIN_C))
    run(db, lambda s: svc.revoke_grant(s, ADMIN_B, grant, "Left the project"))
    fails(db, lambda s: _create(s, ADMIN_C), "FORBIDDEN")
    fails(db, lambda s: svc.revoke_grant(s, ADMIN_B, grant, "again"), "ILLEGAL_TRANSITION")
    assert audit(db, "STOCK_GRANT_CREATED") == 1 and audit(db, "STOCK_GRANT_REVOKED") == 1


def test_S1_self_grant_and_unprivileged_grants_are_refused(db: str) -> None:
    fails(
        db,
        lambda s: svc.grant_admin(s, ADMIN_A, user_id=2, capability="scope", reason_text="me"),
        "FORBIDDEN",
    )
    fails(
        db, lambda s: svc.grant_admin(s, ADMIN_C, user_id=4, capability="scope", reason_text="x"), "FORBIDDEN"
    )
    rejects(
        db,
        asyncpg.CheckViolationError,
        "ck_grant_not_self",
        "INSERT INTO ref.stock_admin_grant (market_id,user_id,capability,valid_from,granted_by,reason_text) "
        "VALUES (1,4,'scope',now(),4,'self')",
    )


# --- S2 / S3 -----------------------------------------------------------------------------------------


def test_S2_author_cannot_approve_own_scope_service_and_database(db: str) -> None:
    scope_id = _scope(db, approver=None)
    fails(db, lambda s: svc.approve_scope(s, ADMIN_A, scope_id), "FORBIDDEN")
    rejects(
        db,
        asyncpg.CheckViolationError,
        "ck_scope_author_not_approver",
        f"UPDATE ops.stock_scope_version SET status='approved', approved_by=2, approved_at=now(), "
        f"effective_from=now() WHERE id={scope_id}",
    )
    assert fetch(db, "SELECT status FROM ops.stock_scope_version")[0]["status"] == "draft"
    assert audit(db, "STOCK_SCOPE_APPROVED") == 0


def test_S3_scope_is_effective_only_from_approval_and_selected_by_as_of(db: str) -> None:
    first = _scope(db)  # approved at NOW
    clock.set_now(NOW + timedelta(days=1))
    second = _scope(db, author=ADMIN_B, approver=ADMIN_A)

    async def pick(s: AsyncSession, at: datetime) -> int | None:
        row = await svc.scope_effective_at(s, 1, at)
        return row.id if row else None

    assert run(db, lambda s: pick(s, NOW - timedelta(minutes=1))) is None  # no retroactive approval
    assert run(db, lambda s: pick(s, NOW + timedelta(hours=5))) == first
    assert run(db, lambda s: pick(s, NOW + timedelta(days=1, hours=1))) == second
    statuses = {r["id"]: r["status"] for r in fetch(db, "SELECT id,status FROM ops.stock_scope_version")}
    assert statuses == {first: "superseded", second: "approved"}
    assert audit(db, "STOCK_SCOPE_CREATED") == 2 and audit(db, "STOCK_SCOPE_APPROVED") == 2


def test_S3_approved_scope_history_is_immutable(db: str) -> None:
    scope_id = _scope(db)
    for statement in (
        f"UPDATE ops.stock_scope_version SET skus='{{A}}' WHERE id={scope_id}",
        f"UPDATE ops.stock_scope_version SET effective_from='2020-01-01Z' WHERE id={scope_id}",
        f"DELETE FROM ops.stock_scope_version WHERE id={scope_id}",
    ):
        rejects(db, asyncpg.IntegrityConstraintViolationError, None, statement)
    fails(db, lambda s: svc.approve_scope(s, ADMIN_B, scope_id), "ILLEGAL_TRANSITION")


def test_S3_concurrent_approvals_leave_exactly_one_approved_version(db: str) -> None:
    ids = [_scope(db, approver=None), _scope(db, approver=None)]

    async def both() -> None:
        engine = create_async_engine(async_url(db), poolclass=NullPool)
        factory = async_sessionmaker(engine)

        async def approve(scope_id: int) -> None:
            async with factory() as session, session.begin():
                await svc.approve_scope(session, ADMIN_B, scope_id)

        try:
            await asyncio.gather(*(approve(i) for i in ids))
        finally:
            await engine.dispose()

    asyncio.run(both())
    counts = {
        r["status"]: r["n"]
        for r in fetch(db, "SELECT status, count(*) AS n FROM ops.stock_scope_version GROUP BY 1")
    }
    assert counts == {"approved": 1, "superseded": 1}


def test_scope_approval_rolls_back_with_its_transaction(db: str) -> None:
    scope_id = _scope(db, approver=None)

    async def approve_then_fail(s: AsyncSession) -> None:
        await svc.approve_scope(s, ADMIN_B, scope_id)
        raise RuntimeError("late failure")

    with pytest.raises(RuntimeError):
        run(db, approve_then_fail)
    assert fetch(db, "SELECT status FROM ops.stock_scope_version")[0]["status"] == "draft"
    assert audit(db, "STOCK_SCOPE_APPROVED") == 0


# --- S2 / S5 evidence --------------------------------------------------------------------------------


def _evidence(db: str, submitter: CurrentUser = MANAGER, skus: tuple[str, ...] = ("A", "B")) -> int:
    return run(
        db,
        lambda s: _id(
            svc.submit_evidence(
                s, submitter, warehouse_id=1, local_skus=skus, evidence_ref="WMS-PROOF-2026-11-09"
            )
        ),
    )


def _approve(
    db: str, evidence_id: int, actor: CurrentUser = ADMIN_A, days: int = 30, start: datetime | None = None
):
    begin = start or NOW

    async def go(s: AsyncSession) -> str:
        row = await svc.approve_evidence(
            s, actor, evidence_id, valid_from=begin, valid_to=begin + timedelta(days=days)
        )
        return row.status

    return run(db, go)


def test_S2_only_the_warehouses_manager_can_submit_and_only_for_scoped_skus(db: str) -> None:
    _scope(db)

    def submit(actor: CurrentUser, wh: int = 1, skus: tuple[str, ...] = ("A", "B")):
        return lambda s: svc.submit_evidence(s, actor, warehouse_id=wh, local_skus=skus, evidence_ref="REF")

    fails(db, submit(OTHER_MANAGER), "FORBIDDEN")  # manager of another warehouse
    fails(db, submit(ADMIN_A), "FORBIDDEN")  # not a warehouse manager
    fails(db, submit(MANAGER, skus=("A", "OUT")), "PLAN_NOT_APPROVABLE")  # SKU outside scope / unmapped
    fails(db, submit(MANAGER, skus=("A",)), "VALIDATION_ERROR")  # independence needs >= 2 SKUs
    assert _evidence(db) > 0
    assert audit(db, "STOCK_EVIDENCE_SUBMITTED") == 1


def test_S2_submitter_cannot_approve_and_approval_needs_an_evidence_grant(db: str) -> None:
    _scope(db)
    evidence_id = _evidence(db)
    fails(
        db,
        lambda s: svc.approve_evidence(
            s, ADMIN_C, evidence_id, valid_from=NOW, valid_to=NOW + timedelta(days=1)
        ),
        "FORBIDDEN",
    )
    fails(
        db,
        lambda s: svc.approve_evidence(
            s, MANAGER, evidence_id, valid_from=NOW, valid_to=NOW + timedelta(days=1)
        ),
        "FORBIDDEN",
    )
    # even a (mis)granted submitter is blocked by identity: make the manager an admin with a grant
    execute(
        db,
        "UPDATE ref.app_user SET roles='{admin}' WHERE id=5",
        "INSERT INTO ref.stock_admin_grant (market_id,user_id,capability,valid_from,granted_by,reason_text) "
        "VALUES (1,5,'evidence','2026-11-01T00:00Z',1,'test')",
    )
    fails(
        db,
        lambda s: svc.approve_evidence(
            s, _user(5, "admin", 5), evidence_id, valid_from=NOW, valid_to=NOW + timedelta(days=1)
        ),
        "FORBIDDEN",
    )
    rejects(
        db,
        asyncpg.CheckViolationError,
        "ck_evidence_submitter_not_approver",
        f"UPDATE ops.stock_independence_evidence SET status='approved', approved_by=5, approved_at=now(), "
        f"valid_from=now(), valid_to=now()+interval '1 day' WHERE id={evidence_id}",
    )
    assert audit(db, "STOCK_EVIDENCE_APPROVED") == 0


def test_S5_validity_is_at_most_30_days_and_never_retroactive_or_overlapping(db: str) -> None:
    _scope(db)
    evidence_id = _evidence(db)
    fails(
        db,
        lambda s: svc.approve_evidence(
            s, ADMIN_A, evidence_id, valid_from=NOW, valid_to=NOW + timedelta(days=31)
        ),
        "VALIDATION_ERROR",
    )
    fails(
        db,
        lambda s: svc.approve_evidence(
            s, ADMIN_A, evidence_id, valid_from=NOW - timedelta(days=1), valid_to=NOW + timedelta(days=5)
        ),
        "VALIDATION_ERROR",
    )
    rejects(
        db,
        asyncpg.CheckViolationError,
        "ck_evidence_max_30_days",
        f"UPDATE ops.stock_independence_evidence SET status='approved', approved_by=2, approved_at=now(), "
        f"valid_from=now(), valid_to=now()+interval '31 days' WHERE id={evidence_id}",
    )
    assert _approve(db, evidence_id) == "approved"
    second = _evidence(db, skus=("B", "C"))
    fails(
        db,
        lambda s: svc.approve_evidence(
            s, ADMIN_B, second, valid_from=NOW + timedelta(days=10), valid_to=NOW + timedelta(days=20)
        ),
        "RESOURCE_CONFLICT",
    )
    assert audit(db, "STOCK_EVIDENCE_APPROVED") == 1


def test_S5_mapping_unit_or_conversion_change_invalidates_evidence_automatically(db: str) -> None:
    _scope(db)
    evidence_id = _evidence(db)
    _approve(db, evidence_id)
    ctx = run(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(days=1)))
    assert ctx.verified_independent == (frozenset({"A", "B"}),) and ctx.evidence_ids == (evidence_id,)
    # conversion changed and NO hook was called: use-time fingerprint check still fails closed
    execute(db, "UPDATE ref.product_se SET units_to_base=5 WHERE local_sku='A'")
    ctx = run(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(days=1)))
    assert ctx.verified_independent == () and ctx.evidence_ids == ()
    # the hook revokes (and audits) the affected evidence permanently
    execute(
        db, "UPDATE ref.product_se SET units_to_base=2.5 WHERE local_sku='A'"
    )  # restoring never reactivates
    revoked = run(db, lambda s: svc.invalidate_evidence_for_skus(s, 1, ["A"], reason="conversion changed"))
    assert revoked == 1
    ctx = run(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(days=1)))
    assert ctx.verified_independent == ()
    assert fetch(db, "SELECT status FROM ops.stock_independence_evidence")[0]["status"] == "revoked"
    rejects(
        db,
        asyncpg.IntegrityConstraintViolationError,
        None,
        f"UPDATE ops.stock_independence_evidence SET status='approved' WHERE id={evidence_id}",
    )
    assert audit(db, "STOCK_EVIDENCE_REVOKED") == 1


def test_S5_expired_future_unapproved_and_rejected_evidence_is_never_used(db: str) -> None:
    _scope(db)
    pending = _evidence(db)
    rejected = _evidence(db, skus=("B", "C"))
    run(db, lambda s: svc.reject_evidence(s, ADMIN_A, rejected, "Counts do not match"))
    fails(db, lambda s: svc.reject_evidence(s, ADMIN_A, rejected, "again"), "ILLEGAL_TRANSITION")
    ctx = run(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(hours=1)))
    assert ctx.evidence_ids == ()
    _approve(db, pending, start=NOW + timedelta(days=2))  # starts later
    assert run(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(hours=1))).evidence_ids == ()
    at = NOW + timedelta(days=2, hours=1)
    assert run(db, lambda s: svc.resolve_stock_context(s, 1, at)).evidence_ids == (pending,)
    assert run(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(days=33))).evidence_ids == ()


def test_scope_change_makes_old_scope_evidence_unusable(db: str) -> None:
    _scope(db)
    evidence_id = _evidence(db)
    _approve(db, evidence_id)
    clock.set_now(NOW + timedelta(days=1))
    _scope(db, author=ADMIN_B, approver=ADMIN_A)  # new scope version => old evidence is bound to old version
    ctx = run(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(days=1, hours=1)))
    assert ctx.evidence_ids == () and ctx.scope_version == 2
    # the old evidence is permanently revoked and audited, and cannot be silently reactivated
    assert fetch(db, "SELECT status FROM ops.stock_independence_evidence")[0]["status"] == "revoked"
    assert audit(db, "STOCK_EVIDENCE_REVOKED") == 1


# --- S4 / write-run binding ---------------------------------------------------------------------------


def test_S4_missing_expected_row_rejects_the_write_and_explicit_zero_is_valid(db: str) -> None:
    _scope(db)
    ctx = run(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(hours=1)))
    expected = svc.expected_rows(ctx, {1: "WH-1", 2: "WH-2"})
    assert len(expected) == 6  # 2 warehouses x 3 SKUs
    present = set(expected) | {("WH-1", "OUT-OF-SCOPE")}  # extra out-of-scope rows are ignored
    svc.require_expected_coverage(expected, present)  # zero quantities are rows too: complete
    with pytest.raises(StockScopeError) as caught:
        svc.require_expected_coverage(expected, present - {("WH-2", "B")})
    assert caught.value.code == "STOCK_UNAVAILABLE" and caught.value.http_status == 503
    with pytest.raises(StockScopeError):
        svc.expected_rows(ctx, {1: "WH-1"})  # a scope warehouse without a source code is unknown


def test_S3_no_effective_scope_fails_closed(db: str) -> None:
    fails(db, lambda s: svc.resolve_stock_context(s, 1, NOW), "STOCK_UNAVAILABLE")
    _scope(db, approver=None)  # draft only
    fails(db, lambda s: svc.resolve_stock_context(s, 1, NOW + timedelta(hours=1)), "STOCK_UNAVAILABLE")


def test_S3_write_run_binds_versions_is_unique_per_batch_and_append_only(db: str) -> None:
    _scope(db)
    evidence_id = _evidence(db)
    _approve(db, evidence_id)
    as_of = NOW + timedelta(hours=2)

    async def record(s: AsyncSession, batch: int, *, reject: str | None = None) -> int:
        ctx = await svc.resolve_stock_context(s, 1, as_of)
        run_row = await svc.record_write_run(
            s,
            market_id=1,
            source_batch_id=batch,
            as_of=as_of,
            context=ctx,
            expected=6,
            recorded=6,
            reject_code=reject,
        )
        return run_row.id

    run(db, lambda s: record(s, 10))
    run(db, lambda s: record(s, 11, reject="MISSING_ROWS"))
    got = fetch(
        db,
        "SELECT source_batch_id,status,recorded_rows,evidence_ids,scope_version_id "
        "FROM ops.stock_write_run ORDER BY id",
    )
    assert [(r["source_batch_id"], r["status"], r["recorded_rows"]) for r in got] == [
        (10, "accepted", 6),
        (11, "rejected", 0),
    ]
    assert list(got[0]["evidence_ids"]) == [evidence_id] and got[0]["scope_version_id"] == 1
    with pytest.raises(Exception, match="stock_write_run_market_id_source_batch_id_key|duplicate"):
        run(db, lambda s: record(s, 10))
    rejects(db, asyncpg.RaiseError, None, "UPDATE ops.stock_write_run SET recorded_rows=0")
    rejects(db, asyncpg.RaiseError, None, "DELETE FROM ops.stock_write_run")
    fails(
        db,
        lambda s: svc.record_write_run(
            s, market_id=1, source_batch_id=12, as_of=as_of, context=None, expected=0, recorded=0
        ),
        "STOCK_UNAVAILABLE",
    )
