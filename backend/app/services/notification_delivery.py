"""Deliver already queued notifications; does not render content or authorize DELAY sends.

US-NOT-01 AC3/4, US-NOT-03 AC1..3. Caller owns transaction and supplies transports.
One attempt per invocation; failed attempts remain queued until the configured cap.
"""

import os
from datetime import UTC, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core import clock
from app.core.config import MarketConfig, get_settings
from app.core.db import get_sessionmaker
from app.domain.models.ops import CustomerOrder, Notification
from app.domain.models.ref import Market
from app.providers.email_smtp import EmailDeliveryError, SmtpEmailProvider
from app.providers.sms_sim import SimulatedSmsProvider


class EmailTransport(Protocol):
    async def send(self, *, recipient: str, subject: str, text: str) -> None: ...


class SmsTransport(Protocol):
    async def send(self, *, recipient: str, body: str) -> object: ...


def delivery_time(now: datetime, *, timezone: str, quiet_hours: tuple[str, str], delay: bool) -> datetime:
    """Return now or the end of quiet hours in the market's local calendar."""
    if now.tzinfo is None:
        raise ValueError("Delivery time must have a timezone")
    if delay:
        return now
    start, end = (time.fromisoformat(value) for value in quiet_hours)
    if start.tzinfo or end.tzinfo or start == end:
        raise ValueError("Quiet hours must be distinct local times")
    local = now.astimezone(ZoneInfo(timezone))
    current = local.time()
    overnight = start > end
    quiet = (current >= start or current < end) if overnight else start <= current < end
    if not quiet:
        return now
    day = local.date() + timedelta(days=int(overnight and current >= start))
    return datetime.combine(day, end, tzinfo=local.tzinfo).astimezone(UTC)


async def deliver_queued(
    session: AsyncSession, *, now: datetime, email: EmailTransport, sms: SmsTransport, limit: int = 100
) -> int:
    if now.tzinfo is None or limit <= 0:
        raise ValueError("Invalid outbox run parameters")
    records = await session.execute(
        select(Notification, Market)
        .join(CustomerOrder, CustomerOrder.id == Notification.order_id)
        .join(Market, Market.id == CustomerOrder.market_id)
        .where(Notification.status == "queued", Notification.scheduled_for <= now)
        .order_by(Notification.scheduled_for, Notification.id)
        .limit(limit)
        .with_for_update(of=Notification, skip_locked=True)
    )
    processed = 0
    for notification, market in records:
        config = MarketConfig.model_validate(market.config).notify
        if config.max_attempts <= 0:
            raise ValueError("Notification attempt cap must be positive")
        if market.shadow_mode:
            notification.status, notification.suppressed_reason = "suppressed", "shadow_mode"
            await record_decision(
                session,
                Action.NOTIFICATION_SUPPRESSED,
                "notification",
                str(notification.id),
                order_id=notification.order_id,
                plan_id=notification.plan_id,
                reason_code="shadow_mode",
                after={"status": "suppressed"},
            )
            processed += 1
            continue
        # A DELAY row can only leave draft via an explicit dispatcher action.
        if notification.template == "DELAY" and notification.created_by_employee_id is None:
            continue
        scheduled = delivery_time(
            now,
            timezone=market.timezone,
            quiet_hours=config.quiet_hours,
            delay=notification.template == "DELAY",
        )
        if scheduled > now:
            notification.scheduled_for = scheduled
            continue
        if notification.attempts >= config.max_attempts:
            notification.status = "failed"
            continue
        notification.attempts += 1
        try:
            if notification.channel == "email":
                await email.send(
                    recipient=notification.recipient,
                    subject=notification.subject or "",
                    text=notification.body,
                )
            elif notification.channel == "sms_sim":
                await sms.send(recipient=notification.recipient, body=notification.body)
            else:
                raise ValueError("Unsupported notification channel")
        except (EmailDeliveryError, ValueError):
            notification.last_error = "Delivery failed."
            if notification.attempts >= config.max_attempts:
                notification.status = "failed"
        else:
            notification.status, notification.sent_at, notification.last_error = "sent", now, None
            await record_decision(
                session,
                Action.NOTIFICATION_SENT,
                "notification",
                str(notification.id),
                order_id=notification.order_id,
                plan_id=notification.plan_id,
                actor_employee_id=notification.created_by_employee_id,
                after={"status": "sent"},
            )
        processed += 1
    return processed


async def process_outbox() -> int:
    email = SmtpEmailProvider(
        os.environ.get("SMTP_HOST", "mailpit"),
        int(os.environ.get("SMTP_PORT", "1025")),
        sender=os.environ.get("SMTP_FROM", "noreply@cfo.demo"),
        app_env=get_settings().app_env,
        username=os.environ.get("SMTP_USER"),
        password=os.environ.get("SMTP_PASSWORD"),
        starttls=os.environ.get("SMTP_STARTTLS", "false").lower() == "true",
    )
    async with get_sessionmaker()() as session, session.begin():
        return await deliver_queued(session, now=clock.now(), email=email, sms=SimulatedSmsProvider())
