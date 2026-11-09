"""CFO stock scope and independence-evidence governance (DEC-OWNER-20261109 S1-S5).

Everything runs in the CALLER's transaction (events + audit commit or roll back together). No stock writer
is enabled here: `resolve_stock_context` / `require_expected_coverage` / `record_write_run` are the contract
Dev 2's Source/WMS stock writer must call before it may publish a batch.

- S1: only an Admin with an explicit, active, market-specific, revocable grant may author/approve scope or
  approve evidence (an `admin` role or market affiliation alone is never enough).
- S2: scope author != approver; evidence submitter (Warehouse Manager of that warehouse) != approver.
- S3: market-wide versioned scope, effective from approval (never retroactive), selected by the trusted
  Source batch `as_of`, never by sync time.
- S4: every expected warehouse x in-scope SKU row must be present in a complete batch; a missing row is
  unknown and rejects the whole write. Only an explicit zero means zero.
- S5: independent-stock evidence lasts at most 30 days; mapping / unit / conversion / scope changes
  invalidate it automatically (the fingerprint is recomputed on every use, so a missed hook still fails
  closed).
"""

import hashlib
import os
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.errors import DomainError
from app.domain.models.hr import Employee
from app.domain.models.ops import StockIndependenceEvidence, StockScopeVersion, StockWriteRun
from app.domain.models.ref import AppUser, Market, ProductSE, StockAdminGrant

MAX_EVIDENCE_DAYS = 30
CAPABILITIES = ("scope", "evidence")


class StockScopeError(DomainError):
    """Fail-closed stock governance error; never carries source content."""


def _error(code: str, message: str) -> StockScopeError:
    # STOCK_UNAVAILABLE keeps the Source contract status (DEC-SRC-Q9-ERROR-001: 503).
    return StockScopeError(code, message, http_status=503 if code == "STOCK_UNAVAILABLE" else None)


@dataclass(frozen=True)
class StockContext:
    """What a stock write is allowed to use, bound to the trusted batch `as_of`."""

    market_id: int
    scope_version_id: int
    scope_version: int
    skus: frozenset[str]
    warehouse_ids: frozenset[int]
    verified_independent: tuple[frozenset[str], ...]
    evidence_ids: tuple[int, ...]


def _roles(actor: object) -> tuple[str, ...]:
    return tuple(getattr(actor, "roles", ()))


def _user_id(actor: object) -> int:
    value = getattr(actor, "id", None)
    if type(value) is not int:
        raise _error("FORBIDDEN", "Authenticated user required.")
    return value


def _employee_id(actor: object) -> int | None:
    value = getattr(actor, "employee_id", None)
    return value if type(value) is int else None


async def _market(session: AsyncSession, actor: object) -> Market:
    code = getattr(actor, "market", None)
    market = await session.scalar(select(Market).where(Market.code == code)) if code else None
    if market is None:
        raise _error("FORBIDDEN", "A market-scoped account is required.")
    return market


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise _error("VALIDATION_ERROR", "Timestamps must be timezone-aware.")
    return value


async def has_active_grant(
    session: AsyncSession, user_id: int, market_id: int, capability: str, at: datetime
) -> bool:
    return (
        await session.scalar(
            select(StockAdminGrant.id)
            .where(
                StockAdminGrant.user_id == user_id,
                StockAdminGrant.market_id == market_id,
                StockAdminGrant.capability == capability,
                StockAdminGrant.revoked_at.is_(None),
                StockAdminGrant.valid_from <= at,
                (StockAdminGrant.valid_to.is_(None) | (StockAdminGrant.valid_to > at)),
            )
            .limit(1)
        )
    ) is not None


async def _require_admin_grant(session: AsyncSession, actor: object, market: Market, capability: str) -> None:
    if "admin" not in _roles(actor) or not await has_active_grant(
        session, _user_id(actor), market.id, capability, clock.now()
    ):
        raise _error("FORBIDDEN", "An active market-specific stock grant is required.")


async def _lock_market(session: AsyncSession, market_id: int) -> None:
    """Serialize governance writes of one market (transaction-scoped advisory lock)."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:ns, :key)"), {"ns": 2026, "key": market_id})


def _require_owner_delegated_operator(actor: object) -> None:
    """Deployment must bind the reviewed Owner delegation to one exact operator account."""
    configured = os.environ.get("STOCK_GRANT_SYSTEM_ADMIN_USER_ID", "")
    authorization = os.environ.get("STOCK_GRANT_OWNER_AUTHORIZATION_REF", "")
    market = os.environ.get("STOCK_GRANT_AUTHORIZED_MARKET", "")
    if not configured.isdecimal() or not authorization.strip() or _user_id(actor) != int(configured):
        raise _error("FORBIDDEN", "Owner-delegated System Admin required for stock grants.")
    if market != getattr(actor, "market", None):
        raise _error("FORBIDDEN", "Owner delegation does not cover this market.")
    if "admin" not in _roles(actor):
        raise _error("FORBIDDEN", "Owner-delegated System Admin must have an active Admin role.")


async def _require_market_admin_account(session: AsyncSession, user_id: int, market_id: int) -> AppUser:
    account = await session.get(AppUser, user_id)
    employee = await session.get(Employee, account.employee_id) if account and account.employee_id else None
    if (
        account is None
        or not account.is_active
        or "admin" not in account.roles
        or employee is None
        or employee.market_id != market_id
        or employee.status != "active"
    ):
        raise _error("FORBIDDEN", "Grant account must be an active Admin in the authorized market.")
    return account


# --- S1: grants ------------------------------------------------------------------------------------------


async def grant_admin(
    session: AsyncSession,
    actor: object,
    *,
    user_id: int,
    capability: str,
    reason_text: str,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> StockAdminGrant:
    """Only the configured Owner-delegated System Admin may issue a grant."""
    market = await _market(session, actor)
    _require_owner_delegated_operator(actor)
    await _require_market_admin_account(session, _user_id(actor), market.id)
    if capability not in CAPABILITIES or not reason_text.strip():
        raise _error("VALIDATION_ERROR", "Capability and reason are required.")
    await _lock_market(session, market.id)
    if user_id == _user_id(actor):
        raise _error("FORBIDDEN", "A grant cannot be self-issued.")
    # Recipient account eligibility is checked directly, including first-time recipients.
    await _require_market_admin_account(session, user_id, market.id)
    now = clock.now()
    start = _aware(valid_from) if valid_from is not None else now
    if start < now:
        raise _error("VALIDATION_ERROR", "Grant activation cannot be backdated.")
    end = _aware(valid_to) if valid_to is not None else None
    if end is not None and end <= start:
        raise _error("VALIDATION_ERROR", "Grant window is invalid.")
    duplicate = await session.scalar(
        select(StockAdminGrant.id)
        .where(
            StockAdminGrant.market_id == market.id,
            StockAdminGrant.user_id == user_id,
            StockAdminGrant.capability == capability,
            StockAdminGrant.revoked_at.is_(None),
            (StockAdminGrant.valid_to.is_(None) | (StockAdminGrant.valid_to > now)),
        )
        .limit(1)
    )
    if duplicate is not None:
        raise _error("RESOURCE_CONFLICT", "An unrevoked grant already exists for this capability.")
    row = StockAdminGrant(
        market_id=market.id,
        user_id=user_id,
        capability=capability,
        valid_from=start,
        valid_to=end,
        granted_by=_user_id(actor),
        reason_text=reason_text.strip(),
    )
    session.add(row)
    await session.flush()
    await record_decision(
        session,
        Action.STOCK_GRANT_CREATED,
        "stock_admin_grant",
        str(row.id),
        reason_text=reason_text.strip(),
        before={},
        after={
            "user_id": user_id,
            "capability": capability,
            "market_id": market.id,
            "granted_by": _user_id(actor),
            "reason_text": reason_text.strip(),
            "valid_from": start.isoformat(),
            "valid_to": end.isoformat() if end else None,
            "owner_authorization_ref": os.environ["STOCK_GRANT_OWNER_AUTHORIZATION_REF"],
        },
        actor_user_id=_user_id(actor),
        actor_employee_id=_employee_id(actor),
        actor_role="admin",
    )
    return row


async def revoke_grant(session: AsyncSession, actor: object, grant_id: int, reason_text: str) -> None:
    market = await _market(session, actor)
    _require_owner_delegated_operator(actor)
    await _require_market_admin_account(session, _user_id(actor), market.id)
    await _lock_market(session, market.id)
    grant = await session.scalar(
        select(StockAdminGrant)
        .where(StockAdminGrant.id == grant_id, StockAdminGrant.market_id == market.id)
        .with_for_update()
    )
    if grant is None:
        raise _error("NOT_FOUND", "Grant not found.")
    if grant.revoked_at is not None:
        raise _error("ILLEGAL_TRANSITION", "Grant is already revoked.")
    if not reason_text.strip():
        raise _error("REASON_REQUIRED", "Revoking a grant requires a reason.")
    grant.revoked_at, grant.revoked_by, grant.revoke_reason = (
        clock.now(),
        _user_id(actor),
        reason_text.strip(),
    )
    await session.flush()
    await record_decision(
        session,
        Action.STOCK_GRANT_REVOKED,
        "stock_admin_grant",
        str(grant.id),
        reason_text=reason_text.strip(),
        before={"user_id": grant.user_id, "capability": grant.capability, "revoked_at": None},
        after={
            "revoked_at": grant.revoked_at.isoformat(),
            "revoked_by": _user_id(actor),
            "revoke_reason": reason_text.strip(),
            "owner_authorization_ref": os.environ["STOCK_GRANT_OWNER_AUTHORIZATION_REF"],
        },
        actor_user_id=_user_id(actor),
        actor_employee_id=_employee_id(actor),
        actor_role="admin",
    )


# --- S2/S3: scope versions -------------------------------------------------------------------------------


def _scope_out(row: StockScopeVersion) -> dict[str, object]:
    return {
        "id": row.id,
        "version": row.version,
        "status": row.status,
        "skus": sorted(row.skus),
        "warehouse_ids": sorted(row.warehouse_ids),
    }


async def create_scope(
    session: AsyncSession,
    actor: object,
    *,
    skus: Collection[str],
    warehouse_ids: Collection[int],
    reason_text: str,
) -> StockScopeVersion:
    market = await _market(session, actor)
    await _require_admin_grant(session, actor, market, "scope")
    clean = sorted({sku.strip() for sku in skus})
    if not clean or any(not sku for sku in clean) or not warehouse_ids or not reason_text.strip():
        raise _error("VALIDATION_ERROR", "SKUs, warehouses and a reason are required.")
    await _lock_market(session, market.id)
    version = (
        await session.scalar(
            select(func.coalesce(func.max(StockScopeVersion.version), 0)).where(
                StockScopeVersion.market_id == market.id
            )
        )
    ) or 0
    row = StockScopeVersion(
        market_id=market.id,
        version=version + 1,
        skus=clean,
        warehouse_ids=sorted(set(warehouse_ids)),
        reason_text=reason_text.strip(),
        created_by=_user_id(actor),
    )
    session.add(row)
    await session.flush()
    await record_decision(
        session,
        Action.STOCK_SCOPE_CREATED,
        "stock_scope_version",
        str(row.id),
        after=_scope_out(row),
        actor_user_id=_user_id(actor),
        actor_employee_id=_employee_id(actor),
        actor_role="admin",
    )
    return row


async def approve_scope(session: AsyncSession, actor: object, scope_id: int) -> StockScopeVersion:
    market = await _market(session, actor)
    await _require_admin_grant(session, actor, market, "scope")
    await _lock_market(session, market.id)
    row = await session.scalar(
        select(StockScopeVersion)
        .where(StockScopeVersion.id == scope_id, StockScopeVersion.market_id == market.id)
        .with_for_update()
    )
    if row is None:
        raise _error("NOT_FOUND", "Scope version not found.")
    if row.status != "draft":
        raise _error("ILLEGAL_TRANSITION", "Only a draft scope can be approved.")
    if row.created_by == _user_id(actor):
        raise _error("FORBIDDEN", "A scope author cannot approve their own scope.")
    now = clock.now()
    previous = await session.scalar(
        select(StockScopeVersion)
        .where(StockScopeVersion.market_id == market.id, StockScopeVersion.status == "approved")
        .with_for_update()
    )
    before = _scope_out(row)
    if previous is not None:
        previous.status, previous.superseded_at = "superseded", now
        await session.flush()
        # S5: a scope change invalidates evidence bound to the superseded version (renewal = new approval).
        await _revoke_evidence_of_scope(session, previous.id, "Scope version superseded", actor)
    row.status, row.approved_by, row.approved_at, row.effective_from = "approved", _user_id(actor), now, now
    await session.flush()
    await record_decision(
        session,
        Action.STOCK_SCOPE_APPROVED,
        "stock_scope_version",
        str(row.id),
        before=before,
        after=_scope_out(row) | {"superseded_version_id": previous.id if previous else None},
        actor_user_id=_user_id(actor),
        actor_employee_id=_employee_id(actor),
        actor_role="admin",
    )
    return row


async def scope_effective_at(
    session: AsyncSession, market_id: int, as_of: datetime
) -> StockScopeVersion | None:
    """S3: the immutable approved version in force at the trusted Source batch `as_of`."""
    _aware(as_of)
    return await session.scalar(
        select(StockScopeVersion)
        .where(
            StockScopeVersion.market_id == market_id,
            StockScopeVersion.status.in_(("approved", "superseded")),
            StockScopeVersion.effective_from <= as_of,
            (StockScopeVersion.superseded_at.is_(None) | (StockScopeVersion.superseded_at > as_of)),
        )
        .order_by(StockScopeVersion.version.desc())
        .limit(1)
    )


# --- S2/S5: independence evidence ------------------------------------------------------------------------


async def mapping_fingerprint(session: AsyncSession, skus: Iterable[str]) -> str:
    """Hash of the confirmed mapping, unit and conversion of every SKU; any change alters it (S5)."""
    wanted = sorted(set(skus))
    rows = {
        r.local_sku: r
        for r in (await session.scalars(select(ProductSE).where(ProductSE.local_sku.in_(wanted)))).all()
    }
    parts: list[str] = []
    for sku in wanted:
        row = rows.get(sku)
        if row is None or row.mapping_status != "confirmed" or row.global_product_id is None:
            raise _error("PLAN_NOT_APPROVABLE", "Evidence SKUs need a confirmed mapping.")
        factor: Decimal = row.units_to_base
        parts.append(f"{sku}|{row.global_product_id}|{row.sale_unit}|{factor.normalize():f}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


async def submit_evidence(
    session: AsyncSession,
    actor: object,
    *,
    warehouse_id: int,
    local_skus: Collection[str],
    evidence_ref: str,
) -> StockIndependenceEvidence:
    """A Warehouse Manager of that warehouse submits WMS/warehouse proof; it is not usable until approved."""
    market = await _market(session, actor)
    if "warehouse" not in _roles(actor) or warehouse_id not in tuple(getattr(actor, "location_ids", ())):
        raise _error("FORBIDDEN", "Only a manager of this warehouse can submit evidence.")
    skus = sorted({sku.strip() for sku in local_skus})
    if len(skus) < 2 or not evidence_ref.strip():
        raise _error("VALIDATION_ERROR", "At least two SKUs and an evidence reference are required.")
    await _lock_market(session, market.id)
    scope = await scope_effective_at(session, market.id, clock.now())
    if scope is None or warehouse_id not in scope.warehouse_ids or not set(skus) <= set(scope.skus):
        raise _error("PLAN_NOT_APPROVABLE", "Evidence must cover the effective scope warehouses and SKUs.")
    fingerprint = await mapping_fingerprint(session, skus)
    version = (
        await session.scalar(
            select(func.coalesce(func.max(StockIndependenceEvidence.version), 0)).where(
                StockIndependenceEvidence.market_id == market.id,
                StockIndependenceEvidence.warehouse_id == warehouse_id,
            )
        )
    ) or 0
    row = StockIndependenceEvidence(
        market_id=market.id,
        warehouse_id=warehouse_id,
        version=version + 1,
        scope_version_id=scope.id,
        local_skus=skus,
        mapping_fingerprint=fingerprint,
        evidence_ref=evidence_ref.strip(),
        submitted_by=_user_id(actor),
    )
    session.add(row)
    await session.flush()
    await record_decision(
        session,
        Action.STOCK_EVIDENCE_SUBMITTED,
        "stock_independence_evidence",
        str(row.id),
        after={"warehouse_id": warehouse_id, "local_skus": skus, "version": row.version},
        actor_user_id=_user_id(actor),
        actor_employee_id=_employee_id(actor),
        actor_role="warehouse",
    )
    return row


async def _locked_evidence(
    session: AsyncSession, market: Market, evidence_id: int
) -> StockIndependenceEvidence:
    row = await session.scalar(
        select(StockIndependenceEvidence)
        .where(StockIndependenceEvidence.id == evidence_id, StockIndependenceEvidence.market_id == market.id)
        .with_for_update()
    )
    if row is None:
        raise _error("NOT_FOUND", "Evidence not found.")
    return row


async def approve_evidence(
    session: AsyncSession,
    actor: object,
    evidence_id: int,
    *,
    valid_from: datetime,
    valid_to: datetime,
) -> StockIndependenceEvidence:
    market = await _market(session, actor)
    await _require_admin_grant(session, actor, market, "evidence")
    await _lock_market(session, market.id)
    row = await _locked_evidence(session, market, evidence_id)
    if row.status != "submitted":
        raise _error("ILLEGAL_TRANSITION", "Only submitted evidence can be approved.")
    if row.submitted_by == _user_id(actor):
        raise _error("FORBIDDEN", "The submitter cannot approve their own evidence.")
    start, end, now = _aware(valid_from), _aware(valid_to), clock.now()
    if start < now:
        raise _error("VALIDATION_ERROR", "Evidence cannot be approved retroactively.")
    if end <= start or end - start > timedelta(days=MAX_EVIDENCE_DAYS):
        raise _error("VALIDATION_ERROR", "Evidence validity must be positive and at most 30 days.")
    if await mapping_fingerprint(session, row.local_skus) != row.mapping_fingerprint:
        raise _error("PLAN_NOT_APPROVABLE", "Mapping, unit or conversion changed since submission.")
    scope = await scope_effective_at(session, market.id, now)
    if scope is None or scope.id != row.scope_version_id:
        raise _error("PLAN_NOT_APPROVABLE", "The scope version of this evidence is no longer effective.")
    overlapping = (
        await session.scalars(
            select(StockIndependenceEvidence).where(
                StockIndependenceEvidence.market_id == market.id,
                StockIndependenceEvidence.warehouse_id == row.warehouse_id,
                StockIndependenceEvidence.status == "approved",
                StockIndependenceEvidence.valid_from < end,
                StockIndependenceEvidence.valid_to > start,
                StockIndependenceEvidence.local_skus.overlap(row.local_skus),
            )
        )
    ).all()
    if overlapping:
        raise _error("RESOURCE_CONFLICT", "Approved evidence for these SKUs already overlaps this window.")
    row.status, row.approved_by, row.approved_at = "approved", _user_id(actor), now
    row.valid_from, row.valid_to = start, end
    await session.flush()
    await record_decision(
        session,
        Action.STOCK_EVIDENCE_APPROVED,
        "stock_independence_evidence",
        str(row.id),
        before={"status": "submitted"},
        after={"status": "approved", "valid_from": start.isoformat(), "valid_to": end.isoformat()},
        actor_user_id=_user_id(actor),
        actor_employee_id=_employee_id(actor),
        actor_role="admin",
    )
    return row


async def reject_evidence(
    session: AsyncSession, actor: object, evidence_id: int, reason_text: str
) -> StockIndependenceEvidence:
    market = await _market(session, actor)
    await _require_admin_grant(session, actor, market, "evidence")
    row = await _locked_evidence(session, market, evidence_id)
    if row.status != "submitted":
        raise _error("ILLEGAL_TRANSITION", "Only submitted evidence can be rejected.")
    if row.submitted_by == _user_id(actor):
        raise _error("FORBIDDEN", "The submitter cannot decide their own evidence.")
    if not reason_text.strip():
        raise _error("REASON_REQUIRED", "Rejecting evidence requires a reason.")
    row.status = "rejected"
    await session.flush()
    await record_decision(
        session,
        Action.STOCK_EVIDENCE_REJECTED,
        "stock_independence_evidence",
        str(row.id),
        reason_text=reason_text.strip(),
        before={"status": "submitted"},
        after={"status": "rejected"},
        actor_user_id=_user_id(actor),
        actor_employee_id=_employee_id(actor),
        actor_role="admin",
    )
    return row


async def revoke_evidence(
    session: AsyncSession, actor: object, evidence_id: int, reason_text: str
) -> StockIndependenceEvidence:
    market = await _market(session, actor)
    await _require_admin_grant(session, actor, market, "evidence")
    row = await _locked_evidence(session, market, evidence_id)
    if row.status != "approved":
        raise _error("ILLEGAL_TRANSITION", "Only approved evidence can be revoked.")
    if not reason_text.strip():
        raise _error("REASON_REQUIRED", "Revoking evidence requires a reason.")
    row.status, row.revoked_at, row.revoke_reason = "revoked", clock.now(), reason_text.strip()
    await session.flush()
    await record_decision(
        session,
        Action.STOCK_EVIDENCE_REVOKED,
        "stock_independence_evidence",
        str(row.id),
        reason_text=reason_text.strip(),
        before={"status": "approved"},
        after={"status": "revoked"},
        actor_user_id=_user_id(actor),
        actor_employee_id=_employee_id(actor),
        actor_role="admin",
    )
    return row


async def _revoke_evidence_of_scope(
    session: AsyncSession, scope_version_id: int, reason: str, actor: object
) -> None:
    rows = (
        await session.scalars(
            select(StockIndependenceEvidence)
            .where(
                StockIndependenceEvidence.scope_version_id == scope_version_id,
                StockIndependenceEvidence.status == "approved",
            )
            .with_for_update()
        )
    ).all()
    for row in rows:
        row.status, row.revoked_at, row.revoke_reason = "revoked", clock.now(), reason
        await record_decision(
            session,
            Action.STOCK_EVIDENCE_REVOKED,
            "stock_independence_evidence",
            str(row.id),
            reason_text=reason,
            before={"status": "approved"},
            after={"status": "revoked"},
            actor_user_id=_user_id(actor),
            actor_employee_id=_employee_id(actor),
            actor_role="admin",
        )
    await session.flush()


async def invalidate_evidence_for_skus(
    session: AsyncSession, market_id: int, skus: Collection[str], *, reason: str, actor: object | None = None
) -> int:
    """S5 hook for mapping / unit / conversion / scope changes: revoke affected approved evidence.

    Callers (mapping confirm, scope approval) invoke it in their own transaction. Validity is additionally
    recomputed from the fingerprint at use time, so a missed call can never make stale evidence usable.
    """
    rows = (
        await session.scalars(
            select(StockIndependenceEvidence)
            .where(
                StockIndependenceEvidence.market_id == market_id,
                StockIndependenceEvidence.status == "approved",
                StockIndependenceEvidence.local_skus.overlap(sorted(set(skus))),
            )
            .with_for_update()
        )
    ).all()
    for row in rows:
        row.status, row.revoked_at, row.revoke_reason = "revoked", clock.now(), reason
        await record_decision(
            session,
            Action.STOCK_EVIDENCE_REVOKED,
            "stock_independence_evidence",
            str(row.id),
            reason_text=reason,
            before={"status": "approved"},
            after={"status": "revoked"},
            actor_user_id=getattr(actor, "id", None) if actor is not None else None,
            actor_role="system",
        )
    await session.flush()
    return len(rows)


# --- stock writer contract (Dev 2 calls these; nothing is written to ops.stock_snapshot here) -------------


async def resolve_stock_context(session: AsyncSession, market_id: int, as_of: datetime) -> StockContext:
    """Scope and still-valid evidence for a trusted batch `as_of`; fail closed when none is effective."""
    scope = await scope_effective_at(session, market_id, as_of)
    if scope is None:
        raise _error("STOCK_UNAVAILABLE", "No approved stock scope is effective for this batch.")
    evidence = (
        await session.scalars(
            select(StockIndependenceEvidence).where(
                StockIndependenceEvidence.market_id == market_id,
                StockIndependenceEvidence.status == "approved",
                StockIndependenceEvidence.scope_version_id == scope.id,
                StockIndependenceEvidence.valid_from <= as_of,
                StockIndependenceEvidence.valid_to > as_of,
            )
        )
    ).all()
    usable = []
    for row in evidence:
        try:
            if await mapping_fingerprint(session, row.local_skus) == row.mapping_fingerprint:
                usable.append(row)
        except StockScopeError:
            continue  # unconfirmed/missing mapping now: the evidence no longer counts
    return StockContext(
        market_id=market_id,
        scope_version_id=scope.id,
        scope_version=scope.version,
        skus=frozenset(scope.skus),
        warehouse_ids=frozenset(scope.warehouse_ids),
        verified_independent=tuple(frozenset(r.local_skus) for r in usable),
        evidence_ids=tuple(sorted(r.id for r in usable)),
    )


def expected_rows(context: StockContext, warehouse_codes: dict[int, str]) -> frozenset[tuple[str, str]]:
    """S4: expected (warehouse_code, sku) pairs = scope warehouses x scope SKUs."""
    missing = context.warehouse_ids - warehouse_codes.keys()
    if missing:
        raise _error("STOCK_UNAVAILABLE", "A scope warehouse has no source warehouse code.")
    return frozenset((warehouse_codes[w], sku) for w in context.warehouse_ids for sku in context.skus)


def require_expected_coverage(
    expected: Collection[tuple[str, str]], present: Collection[tuple[str, str]]
) -> None:
    """S4: an absent expected row is unknown (never zero) and rejects the entire write."""
    if set(expected) - set(present):
        raise _error("STOCK_UNAVAILABLE", "The Source batch lacks required warehouse x SKU rows.")


async def record_write_run(
    session: AsyncSession,
    *,
    market_id: int,
    source_batch_id: int,
    as_of: datetime,
    context: StockContext | None,
    expected: int,
    recorded: int,
    reject_code: str | None = None,
) -> StockWriteRun:
    """Append the binding of one stock write attempt to its scope/evidence versions (S3)."""
    accepted = reject_code is None
    if accepted and context is None:
        raise _error("STOCK_UNAVAILABLE", "An accepted stock write needs a resolved scope version.")
    run = StockWriteRun(
        market_id=market_id,
        source_batch_id=source_batch_id,
        as_of=_aware(as_of),
        scope_version_id=context.scope_version_id if context else None,
        evidence_ids=list(context.evidence_ids) if context else [],
        expected_rows=expected,
        recorded_rows=recorded if accepted else 0,
        status="accepted" if accepted else "rejected",
        reject_code=reject_code,
    )
    session.add(run)
    await session.flush()
    return run

