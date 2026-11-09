"""Transactional, test-recipient-only notification service (US-NOT-01..03).

All writes use the caller-owned AsyncSession: no hidden commit, network call or
fresh session. The independent outbox worker only sees rows after commit.
Legacy M6/risk callers without session deliberately fail closed until Dev 1
passes their transaction in a separate integration PR.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.domain.models.ops import (
    Alert,
    CustomerOrder,
    DateNegotiation,
    IdempotencyKey,
    Notification,
)
from app.domain.models.ref import Customer, Market
from app.providers.email_smtp import recipient_allowed
from app.services.notification_delivery import delivery_time
from app.services.notification_delivery import process_outbox as deliver_outbox
from app.services.notification_snapshot import (
    ApprovedEta,
    NotificationSnapshot,
    approved_window_from_snapshot,
    freeze_snapshot,
    read_snapshot,
    snapshot_version,
)
from app.services.notification_templates import (
    TEMPLATE_VERSION,
    EtaWindow,
    MessageVariables,
    Template,
    approved_window,
    render_message,
)

AUTO_TEMPLATES = frozenset({"CONFIRMED", "DISPATCHED", "DELIVERED", "FAILED"})
READ_ROLES = frozenset({"admin", "dispatcher", "customer_service"})
TEST_DOMAINS = frozenset({"test"})


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: AwareDatetime
    end: AwareDatetime
    version: int = Field(gt=0)
    date_negotiation_id: int | None = Field(default=None, gt=0)


class DelaySendInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eta_window: EtaWindow
    version: int = Field(gt=0)
    reason_code: Literal["PREDICTED_LATE"] = "PREDICTED_LATE"
    date_negotiation_id: int | None = Field(default=None, gt=0)


def _roles(actor: object) -> frozenset[str]:
    return frozenset(getattr(actor, "roles", ()))


def _market(actor: object) -> str:
    value = getattr(actor, "market", "")
    return value if isinstance(value, str) else ""


def _require_reader(actor: object) -> None:
    if not _roles(actor).intersection(READ_ROLES):
        raise DomainError("FORBIDDEN", "Notification access is not permitted.")
    if not _market(actor) and "admin" not in _roles(actor):
        raise DomainError("FORBIDDEN", "Market assignment is required.")


def _require_dispatcher(actor: object) -> tuple[int, int]:
    if "dispatcher" not in _roles(actor) or not _market(actor):
        raise DomainError("FORBIDDEN", "Only an assigned dispatcher may review DELAY.")
    user_id = getattr(actor, "id", None)
    employee_id = getattr(actor, "employee_id", None)
    if not isinstance(user_id, int) or not isinstance(employee_id, int):
        raise DomainError("FORBIDDEN", "Active dispatcher identity is required.")
    return user_id, employee_id


async def _scope_order(session: AsyncSession, order_id: int, actor: object) -> CustomerOrder:
    _require_reader(actor)
    order = await session.scalar(
        select(CustomerOrder)
        .join(Market, Market.id == CustomerOrder.market_id)
        .where(CustomerOrder.id == order_id, Market.code == _market(actor))
    )
    if order is None:
        raise DomainError("NOT_FOUND", "Order not found.")
    return order


async def _scope_notification(
    session: AsyncSession, notification_id: int, actor: object, *, lock: bool = False
) -> Notification:
    _require_reader(actor)
    query = (
        select(Notification)
        .join(CustomerOrder, CustomerOrder.id == Notification.order_id)
        .join(Market, Market.id == CustomerOrder.market_id)
        .where(Notification.id == notification_id)
    )
    if "admin" not in _roles(actor):
        query = query.where(Market.code == _market(actor))
    if lock:
        query = query.with_for_update(of=Notification)
    record = await session.scalar(query)
    if record is None:
        raise DomainError("NOT_FOUND", "Notification not found.")
    return record


async def _order_market(session: AsyncSession, order: CustomerOrder) -> Market:
    market = await session.get(Market, order.market_id)
    if market is None:
        raise DomainError("NOT_FOUND", "Market not found.")
    return market


def _recipient(customer: Customer, *, channel: str) -> tuple[str, str | None]:
    if channel == "sms_sim":
        # No real phone numbers in the demo transport or outbox.
        return "sms-simulator", None
    address = customer.email or ""
    if not recipient_allowed(address, TEST_DOMAINS):
        # Never persist an external real customer address in a new demo message.
        return "suppressed@cfo.test", "recipient_not_allowed"
    return address, None


def _mask(recipient: str, channel: str) -> str:
    if channel == "sms_sim":
        return "SMS simulator"
    if "@" not in recipient:
        return "***"
    local, domain = recipient.rsplit("@", 1)
    return local[:1] + "***@" + domain


async def _verified_date(
    session: AsyncSession,
    order: CustomerOrder,
    market: Market,
    window: EtaWindow,
    *,
    date_negotiation_id: int | None,
) -> None:
    """Only the committed date or a verified agreed negotiation can be customer-facing."""
    if order.approved_plan_id is None or order.committed_date is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "Order has no approved delivery commitment.")
    local_start = window.start.astimezone(ZoneInfo(market.timezone)).date()
    local_end = window.end.astimezone(ZoneInfo(market.timezone)).date()
    if local_start != local_end:
        raise DomainError("DATE_AGREEMENT_REQUIRED", "Delivery window spans different market dates.")
    if local_start == order.committed_date:
        return
    if date_negotiation_id is None:
        raise DomainError("DATE_AGREEMENT_REQUIRED", "Customer-agreed new date is required.")
    agreed = await session.get(DateNegotiation, date_negotiation_id)
    if (
        agreed is None
        or agreed.order_id != order.id
        or agreed.outcome != "agreed"
        or agreed.proposed_date != local_start
    ):
        raise DomainError("DATE_AGREEMENT_REQUIRED", "No matching agreed customer date was recorded.")


def _mask_response(record: Notification) -> dict[str, object]:
    return {
        "id": record.id,
        "order_id": record.order_id,
        "template": record.template,
        "channel": record.channel,
        "status": record.status,
        "recipient_masked": _mask(record.recipient, record.channel),
        "scheduled_for": record.scheduled_for.isoformat(),
        "sent_at": record.sent_at.isoformat() if record.sent_at else None,
    }


async def list_notifications(
    session: AsyncSession,
    actor: object,
    *,
    order_id: int | None = None,
    template: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, object]:
    _require_reader(actor)
    stmt = (
        select(Notification)
        .join(CustomerOrder, Notification.order_id == CustomerOrder.id)
        .join(Market, Market.id == CustomerOrder.market_id)
    )
    if "admin" not in _roles(actor):
        stmt = stmt.where(Market.code == _market(actor))
    if order_id is not None:
        stmt = stmt.where(Notification.order_id == order_id)
    if template:
        stmt = stmt.where(Notification.template == template)
    if status:
        stmt = stmt.where(Notification.status == status)
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = (
        await session.scalars(
            stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    return {
        "items": [_mask_response(item) for item in rows],
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
    }


async def get_notification(
    session: AsyncSession, notification_id: int, actor: object
) -> dict[str, object]:
    record = await _scope_notification(session, notification_id, actor)
    order = await session.get(CustomerOrder, record.order_id)
    assert order is not None
    market = await _order_market(session, order)
    rendered = read_snapshot(
        record.eta_window,
        channel=record.channel,
        template=record.template,
        subject=record.subject,
        body=record.body,
    )
    if rendered is None:
        # Legacy data is never returned directly: reconstruct from allowlisted fields.
        try:
            window = (
                EtaWindow.model_validate(record.eta_window)
                if record.template == "DELAY"
                else approved_window(order.promise_start, order.promise_end)
            )
            rendered = render_message(
                record.template,  # type: ignore[arg-type]
                MessageVariables(public_order_ref=order.order_no, eta_window=window),
                locale=market.locale,
                timezone=market.timezone,
                channel=record.channel,
            )
        except (ValueError, KeyError) as exc:
            raise DomainError("PLAN_NOT_APPROVABLE", "Notification preview is unavailable.") from exc
    public_window = None
    if record.eta_window and "start" in record.eta_window and "end" in record.eta_window:
        public_window = {
            "start": str(record.eta_window["start"]),
            "end": str(record.eta_window["end"]),
        }
    return {
        **_mask_response(record),
        "subject": rendered.subject,
        "body_html": None,
        "body_text": rendered.body,
        "eta_window": public_window,
        "suppressed_reason": record.suppressed_reason,
    }


async def _deduped_insert(
    session: AsyncSession, *,
    order: CustomerOrder,
    market: Market,
    template: Template,
    dedupe_key: str,
    window: EtaWindow | None,
    approval: ApprovedEta | None = None,
    reason_code: Literal["PREDICTED_LATE"] | None = None,
    status_override: str | None = None,
) -> int:
    customer = await session.get(Customer, order.customer_id)
    if customer is None or customer.market_id != order.market_id:
        raise DomainError("PLAN_NOT_APPROVABLE", "Customer channel is not verified.")
    channel = customer.preferred_channel
    recipient, suppressed = _recipient(customer, channel=channel)
    now = clock.now()
    snapshot = NotificationSnapshot(
        template=template,
        template_version=TEMPLATE_VERSION,
        locale=market.locale,
        timezone=market.timezone,
        variables=MessageVariables(public_order_ref=order.order_no, eta_window=window),
        approved_eta=approval,
        reason_code=reason_code,
    )
    frozen, rendered = freeze_snapshot(snapshot, channel=channel)
    status = status_override or ("suppressed" if suppressed or market.shadow_mode else "queued")
    reason = "shadow_mode" if market.shadow_mode else suppressed
    schedule = delivery_time(
        now,
        timezone=market.timezone,
        quiet_hours=MarketConfig.model_validate(market.config).notify.quiet_hours,
        delay=template == "DELAY",
    )
    stmt = (
        insert(Notification)
        .values(
            order_id=order.id,
            template=template,
            channel=channel,
            recipient=recipient,
            subject=rendered.subject,
            body=rendered.body,
            eta_window=frozen,
            status=status,
            scheduled_for=schedule,
            attempts=0,
            plan_id=order.approved_plan_id,
            dedupe_key=dedupe_key,
            suppressed_reason=reason if status == "suppressed" else None,
        )
        .on_conflict_do_nothing(index_elements=[Notification.dedupe_key])
        .returning(Notification.id)
    )
    new_id = (await session.execute(stmt)).scalar_one_or_none()
    if new_id is None:
        existing = await session.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key))
        if existing is None or existing.eta_window != frozen:
            raise DomainError("IDEMPOTENCY_CONFLICT", "Notification key was reused with changed content.")
        return int(existing.id)
    if status == "suppressed":
        await record_decision(
            session,
            Action.NOTIFICATION_SUPPRESSED,
            "notification",
            str(new_id),
            order_id=order.id,
            plan_id=order.approved_plan_id,
            reason_code=reason,
            after={"status": "suppressed"},
        )
    return int(new_id)


async def enqueue(
    order_id: int,
    template: str,
    plan_id: int | None = None,
    *,
    session: AsyncSession | None = None,
) -> int:
    """Queue an automatic template in the caller transaction, never contact SMTP.

    A missing session is a deliberately blocked M6 handoff, not permission to
    create a separate transaction that survives event/approval rollback.
    """
    if session is None:
        raise NotImplementedError("Caller must pass its existing notification transaction")
    if template not in AUTO_TEMPLATES:
        raise DomainError("VALIDATION_ERROR", "Only four automatic templates are permitted.")
    order = await session.get(CustomerOrder, order_id)
    if order is None:
        raise DomainError("NOT_FOUND", "Order not found.")
    if order.status != ("APPROVED" if template == "CONFIRMED" else template):
        raise DomainError("ILLEGAL_TRANSITION", "Notification does not match the committed order state.")
    if plan_id is None or order.approved_plan_id != plan_id:
        raise DomainError("PLAN_NOT_APPROVABLE", "Approved plan identifier is required.")
    market = await _order_market(session, order)
    try:
        window = approved_window(order.promise_start, order.promise_end)
    except ValueError as exc:
        raise DomainError("PLAN_NOT_APPROVABLE", "Approved ETA window is incomplete.") from exc
    if window is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "Approved ETA window is missing.")
    return await _deduped_insert(
        session,
        order=order,
        market=market,
        template=template,  # type: ignore[arg-type]
        dedupe_key=f"{order.id}:{template}:{plan_id}:{order.status}",
        window=window,
    )


async def create_delay_draft(
    order_id: int,
    eta_window: dict[str, object],
    *,
    session: AsyncSession | None = None,
    actor: object | None = None,
) -> int | None:
    """Risk must supply an authorized, already-reviewed interval, not a forecast instant.

    Until the risk caller can supply its transaction and an approved reviewer,
    it stays blocked. An authenticated dispatcher may create a reviewed draft.
    """
    if session is None or actor is None:
        raise NotImplementedError("Approved dispatcher window and caller transaction are required")
    _, employee_id = _require_dispatcher(actor)
    try:
        data = DraftInput.model_validate(eta_window)
        window = EtaWindow(start=data.start, end=data.end)
    except ValueError as exc:
        raise DomainError("VALIDATION_ERROR", "A reviewed start/end/version is required.") from exc
    order = await _scope_order(session, order_id, actor)
    market = await _order_market(session, order)
    await _verified_date(session, order, market, window, date_negotiation_id=data.date_negotiation_id)
    active = await session.scalar(
        select(Alert.id).where(
            Alert.order_id == order_id,
            Alert.type == "PREDICTED_LATE",
            Alert.resolved_at.is_(None),
        )
    )
    if active is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "No active predicted-late alert for this order.")
    existing = (
        await session.scalars(
            select(Notification)
            .where(Notification.order_id == order.id, Notification.template == "DELAY")
            .order_by(Notification.id.desc())
            .with_for_update()
        )
    ).all()
    dedupe = f"{order.id}:DELAY:{order.approved_plan_id}:{data.version}"
    if any(v.dedupe_key == dedupe for v in existing):
        duplicate = next(v for v in existing if v.dedupe_key == dedupe)
        if not duplicate.eta_window or (
            str(duplicate.eta_window.get("start")) != window.start.isoformat()
            or str(duplicate.eta_window.get("end")) != window.end.isoformat()
        ):
            raise DomainError("IDEMPOTENCY_CONFLICT", "DELAY version was already used for another window.")
        return int(duplicate.id)
    prior_versions = [snapshot_version(v.eta_window) for v in existing]
    if any(v is not None and v >= data.version for v in prior_versions):
        raise DomainError("ILLEGAL_TRANSITION", "A newer DELAY window has already been reviewed.")
    config = MarketConfig.model_validate(market.config).notify
    latest_sent = next((v for v in existing if v.status in ("sent", "queued")), None)
    if latest_sent is not None:
        previous = approved_window_from_snapshot(latest_sent.eta_window)
        if previous is not None:
            minutes = max(
                abs((window.start - previous.start).total_seconds()),
                abs((window.end - previous.end).total_seconds()),
            ) / 60
            if minutes < config.delay_min_shift_min:
                return None
    approved = ApprovedEta(
        start=window.start,
        end=window.end,
        version=data.version,
        approved_by_employee_id=employee_id,
        effective_at=clock.now(),
    )
    # Draft is not sendable via the outbox; created_by_employee_id stays NULL.
    return await _deduped_insert(
        session,
        order=order,
        market=market,
        template="DELAY",
        dedupe_key=dedupe,
        window=window,
        approval=approved,
        reason_code="PREDICTED_LATE",
        status_override="draft",
    )


def _payload_hash(notification_id: int, payload: DelaySendInput) -> str:
    canonical = json.dumps(
        {"notification_id": notification_id, "payload": payload.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


async def _claim_send(
    session: AsyncSession, *, key: str, user_id: int, notification_id: int, payload: DelaySendInput
) -> tuple[IdempotencyKey, dict[str, object] | None]:
    try:
        UUID(key)
    except (ValueError, AttributeError) as exc:
        raise DomainError("VALIDATION_ERROR", "A UUID Idempotency-Key is required.") from exc
    endpoint = f"POST /notifications/{notification_id}/send"
    digest = _payload_hash(notification_id, payload)
    await session.execute(
        insert(IdempotencyKey)
        .values(key=key, user_id=user_id, endpoint=endpoint, request_hash=digest)
        .on_conflict_do_nothing(index_elements=["key", "user_id"])
    )
    record = await session.scalar(
        select(IdempotencyKey)
        .where(IdempotencyKey.key == key, IdempotencyKey.user_id == user_id)
        .with_for_update()
    )
    if record is None or record.endpoint != endpoint or record.request_hash != digest:
        raise DomainError("IDEMPOTENCY_CONFLICT", "Idempotency-Key was used for a different request.")
    if record.response_status == 200 and record.response_body is not None:
        return record, dict(record.response_body)
    if record.response_status is not None:
        raise DomainError("IDEMPOTENCY_CONFLICT", "Previous request cannot be replayed.")
    return record, None


async def send_draft(
    notification_id: int,
    actor: object,
    payload: dict[str, object],
    idempotency_key: str,
    *,
    session: AsyncSession | None = None,
) -> dict[str, object]:
    """Explicit dispatcher approval only queues a DELAY; external delivery runs later."""
    if session is None:
        raise NotImplementedError("Caller transaction is required")
    user_id, employee_id = _require_dispatcher(actor)
    try:
        data = DelaySendInput.model_validate(payload)
    except ValueError as exc:
        raise DomainError("VALIDATION_ERROR", "Only reviewed ETA/version/reason inputs are allowed.") from exc
    record_key, replay = await _claim_send(
        session, key=idempotency_key, user_id=user_id, notification_id=notification_id, payload=data
    )
    if replay is not None:
        return replay
    notification = await _scope_notification(session, notification_id, actor, lock=True)
    if notification.template != "DELAY" or notification.status != "draft":
        raise DomainError("ILLEGAL_TRANSITION", "Only an unsent DELAY draft may be approved.")
    order = await _scope_order(session, notification.order_id, actor)
    market = await _order_market(session, order)
    await _verified_date(
        session, order, market, data.eta_window, date_negotiation_id=data.date_negotiation_id
    )
    previous = approved_window_from_snapshot(notification.eta_window)
    if previous is None:
        raise DomainError("PLAN_NOT_APPROVABLE", "Missing approved draft ETA evidence.")
    if data.version < previous.version or (
        data.version == previous.version and data.eta_window != previous.window()
    ):
        raise DomainError("ILLEGAL_TRANSITION", "Modified window requires a new approval version.")
    next_approval = (
        previous
        if data.version == previous.version
        else ApprovedEta(
            start=data.eta_window.start,
            end=data.eta_window.end,
            version=data.version,
            approved_by_employee_id=employee_id,
            effective_at=clock.now(),
        )
    )
    snapshot = NotificationSnapshot(
        template="DELAY",
        template_version=TEMPLATE_VERSION,
        locale=market.locale,
        timezone=market.timezone,
        variables=MessageVariables(public_order_ref=order.order_no, eta_window=data.eta_window),
        approved_eta=next_approval,
        reason_code=data.reason_code,
    )
    frozen, rendered = freeze_snapshot(snapshot, channel=notification.channel)
    # Only mutable until queued; the outbox later validates the frozen content.
    notification.eta_window = frozen
    notification.subject, notification.body = rendered.subject, rendered.body
    notification.created_by_employee_id = employee_id
    notification.status = "suppressed" if market.shadow_mode else "queued"
    notification.suppressed_reason = "shadow_mode" if market.shadow_mode else None
    notification.scheduled_for = delivery_time(
        clock.now(),
        timezone=market.timezone,
        quiet_hours=MarketConfig.model_validate(market.config).notify.quiet_hours,
        delay=True,
    )
    await session.flush()
    if market.shadow_mode:
        await record_decision(
            session,
            Action.NOTIFICATION_SUPPRESSED,
            "notification",
            str(notification.id),
            order_id=order.id,
            plan_id=notification.plan_id,
            actor_user_id=user_id,
            actor_employee_id=employee_id,
            actor_role="dispatcher",
            reason_code="shadow_mode",
            after={"status": "suppressed"},
        )
    response: dict[str, object] = {
        "id": notification.id,
        "status": notification.status,
        "template": "DELAY",
        "eta_window": {"start": data.eta_window.start.isoformat(), "end": data.eta_window.end.isoformat()},
        "version": next_approval.version,
    }
    record_key.response_status, record_key.response_body = 200, response
    return response


async def discard_draft(
    notification_id: int,
    actor: object,
    reason_text: str,
    *,
    session: AsyncSession | None = None,
) -> dict[str, object]:
    if session is None:
        raise NotImplementedError("Caller transaction is required")
    user_id, employee_id = _require_dispatcher(actor)
    if not isinstance(reason_text, str) or not reason_text.strip():
        raise DomainError("REASON_REQUIRED", "Discarding a DELAY draft requires a reason.")
    notification = await _scope_notification(session, notification_id, actor, lock=True)
    if notification.template != "DELAY":
        raise DomainError("ILLEGAL_TRANSITION", "Only DELAY drafts may be discarded.")
    if notification.status == "suppressed" and notification.suppressed_reason == "dispatcher_discard":
        return {"id": notification.id, "status": "suppressed"}
    if notification.status != "draft":
        raise DomainError("ILLEGAL_TRANSITION", "Only an unsent DELAY draft may be discarded.")
    notification.status = "suppressed"
    notification.suppressed_reason = "dispatcher_discard"
    await record_decision(
        session,
        Action.NOTIFICATION_SUPPRESSED,
        "notification",
        str(notification.id),
        order_id=notification.order_id,
        plan_id=notification.plan_id,
        actor_user_id=user_id,
        actor_employee_id=employee_id,
        actor_role="dispatcher",
        reason_code="dispatcher_discard",
        reason_text=reason_text.strip(),
        after={"status": "suppressed"},
    )
    return {"id": notification.id, "status": "suppressed"}


async def process_outbox() -> int:
    """Job-compatible wrapper; sending remains entirely post-commit and test-only."""
    return await deliver_outbox()
