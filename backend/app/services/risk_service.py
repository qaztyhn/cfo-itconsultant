"""M7 forecast orchestration (US-RSK-01/02; docs/04 §6.3).

This module is deliberately transaction-bound. M6/approval/GPS must pass their
existing AsyncSession; a separate autonomous commit would break milestone and
risk atomicity. Missing planned prep, GPS duration, or approved DELAY window
remains unknown, never estimated or promoted to verified.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import MarketConfig
from app.core.errors import DomainError
from app.domain.models.ops import (
    CustomerOrder,
    DeliveryTrip,
    EtaForecast,
    MilestoneEvent,
    TripStop,
    VehiclePosition,
)
from app.domain.models.plan import FulfilmentPlan, PlanVehicle
from app.domain.models.ref import Location, Market
from app.engine.forecast import MilestoneState, assess_risk, forecast_eta, order_forecast
from app.services import alert_service, notify_service

_EVENT_KINDS = frozenset(
    {
        "START_PREP",
        "PREP_PAUSED",
        "PREP_RESUMED",
        "GOODS_READY",
        "LOADED",
        "DISPATCHED",
        "DELIVERED",
        "FAILED",
        "SHORTAGE",
        "BREAKAGE",
        "VEHICLE_ISSUE",
        "SHIFT_CHANGE",
    }
)
_FIXED_SIGNALS = frozenset(
    {
        "approval",
        "source_change",
        "overdue_milestone",
        "morning_check",
        "gps",
    }
)
_ACTIVE = frozenset({"APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED"})


def _missing(message: str) -> DomainError:
    return DomainError("PLAN_NOT_APPROVABLE", message)


def _validated_minutes(delta: timedelta, label: str) -> int:
    seconds = delta.total_seconds()
    if seconds < 0 or seconds % 60 != 0:
        raise _missing(f"Approved {label} timing is incomplete.")
    return int(seconds // 60)


def _known_config(market: Market) -> MarketConfig:
    try:
        config = MarketConfig.model_validate(market.config or {})
        risk = config.risk
        if (
            not 0 <= risk.yellow_pct < risk.orange_pct <= 100
            or risk.consecutive_negative < 2
            or risk.consecutive_min_gap_min < 1
            or risk.min_reserve_min < 1
            or risk.milestone_grace_min < 0
            or config.eta_round_min < 1
            or config.after_loaded_min < 0
            or config.gps.lost_min < 1
        ):
            raise ValueError("Invalid approved risk configuration")
        return config
    except (ValueError, ValidationError) as exc:
        raise _missing("Approved market risk configuration is unavailable.") from exc


async def _valid_signal(
    session: AsyncSession,
    order: CustomerOrder,
    plan: FulfilmentPlan,
    trigger: str,
    events: list[MilestoneEvent],
    previous: EtaForecast | None,
    now: datetime,
    signal_at: datetime | None,
    config: MarketConfig,
) -> bool:
    """Require an actual input change, not an unsubstantiated periodic refresh."""
    if trigger.startswith("event:"):
        event_type = trigger.split(":", 1)[1]
        if event_type not in _EVENT_KINDS:
            raise DomainError("VALIDATION_ERROR", "Unsupported execution signal.")
        relevant = [e for e in events if e.event_type == event_type]
        if not relevant:
            return False
        observed = max(e.received_at for e in relevant)
        return previous is None or observed > previous.computed_at
    if trigger not in _FIXED_SIGNALS:
        raise DomainError("VALIDATION_ERROR", "Unsupported forecast signal.")
    if trigger == "approval":
        observed = order.approved_at
        if observed is None:
            return False
        return previous is None or observed > previous.computed_at
    if trigger == "overdue_milestone":
        if any(e.event_type == "GOODS_READY" for e in events):
            return False
        if now <= plan.goods_ready_at + timedelta(minutes=config.risk.milestone_grace_min):
            return False
        return previous is None or now - previous.computed_at >= timedelta(
            minutes=config.risk.consecutive_min_gap_min
        )
    # Source, GPS and morning jobs must supply a trusted, aware source watermark.
    # Otherwise calling the service twice would create bogus consecutive forecasts.
    if signal_at is None or signal_at.tzinfo is None or signal_at.utcoffset() is None:
        raise _missing("Verified source signal timestamp is required.")
    if signal_at > now:
        raise DomainError("VALIDATION_ERROR", "Source signal cannot be in the future.")
    return previous is None or signal_at > previous.computed_at


async def _vehicle_inputs(
    session: AsyncSession,
    order: CustomerOrder,
    plan: FulfilmentPlan,
    market: Market,
    events: list[MilestoneEvent],
    now: datetime,
    config: MarketConfig,
    trusted_remaining: Mapping[int, tuple[datetime, int]] | None,
) -> list[tuple[int, datetime, datetime]]:
    """Only approved plan vehicles with their matching trips; never infer route from GPS."""
    assignments = (
        await session.execute(
            select(PlanVehicle, DeliveryTrip, TripStop)
            .join(DeliveryTrip, DeliveryTrip.plan_vehicle_id == PlanVehicle.id)
            .join(TripStop, TripStop.trip_id == DeliveryTrip.id)
            .where(
                PlanVehicle.plan_id == plan.id,
                TripStop.order_id == order.id,
                DeliveryTrip.warehouse_id == plan.warehouse_id,
                TripStop.status != "cancelled",
            )
            .order_by(PlanVehicle.seq)
        )
    ).all()
    if not assignments or len(assignments) != plan.vehicle_count:
        raise _missing("Complete approved vehicle/trip evidence is required.")
    if len({pv.id for pv, _, _ in assignments}) != len(assignments):
        raise _missing("Each approved vehicle must have one matching order stop.")
    goods_ready = max(
        (e.occurred_at for e in events if e.event_type == "GOODS_READY"),
        default=None,
    )
    start_prep = min(
        (e.occurred_at for e in events if e.event_type == "START_PREP"),
        default=None,
    )
    paused = bool(events) and events[-1].event_type == "PREP_PAUSED"
    zone = ZoneInfo(market.timezone)
    cutoff = await session.scalar(
        select(Location.loading_cutoff_time).where(
            Location.id == plan.warehouse_id,
            Location.market_id == market.id,
            Location.type == "warehouse",
        )
    )
    if cutoff is None:
        raise _missing("Approved warehouse loading cutoff is unavailable.")
    output: list[tuple[int, datetime, datetime]] = []
    for pv, trip, stop in assignments:
        drive = _validated_minutes(pv.eta_at - pv.depart_at, "vehicle drive")
        loading = _validated_minutes(pv.depart_at - pv.loading_start_at, "vehicle loading")
        loaded = max(
            (e.occurred_at for e in events if e.event_type == "LOADED" and e.trip_id == trip.id),
            default=None,
        )
        # Trip-level GPS is usable only with an actual stored position, matching
        # timestamp, trusted routing duration, and configured freshness.
        gps_at: datetime | None = None
        remaining: int | None = None
        gps_point = await session.scalar(
            select(VehiclePosition.recorded_at)
            .where(VehiclePosition.trip_id == trip.id)
            .order_by(VehiclePosition.recorded_at.desc())
            .limit(1)
        )
        if gps_point is not None and now - gps_point <= timedelta(minutes=config.gps.lost_min):
            if trusted_remaining is None or trip.id not in trusted_remaining:
                raise _missing("Recent GPS requires verified remaining route duration.")
            gps_at, remaining = trusted_remaining[trip.id]
            if (
                gps_at != gps_point
                or gps_at.tzinfo is None
                or gps_at.utcoffset() is None
                or not isinstance(remaining, int)
                or remaining < 0
            ):
                raise _missing("GPS remaining route evidence is invalid.")
        cutoff_date = pv.loading_start_at.astimezone(zone).date()
        cutoff_at = datetime.combine(cutoff_date, cutoff, tzinfo=zone)
        # Future shift cannot be synthesized from a market calendar.
        if not loaded and not trip.depart_actual_at:
            if goods_ready is not None and goods_ready > cutoff_at:
                raise _missing("Next official loading shift is required after cutoff.")
            if goods_ready is None and now > cutoff_at:
                raise _missing("Next official loading shift is required after cutoff.")
        state = MilestoneState(
            planned_goods_ready=plan.goods_ready_at,
            planned_start_prep=None,  # not persisted in approved plan; never invent it
            planned_depart=pv.depart_at,
            drive_min=drive,
            loading_min=loading,
            actual_start_prep=start_prep,
            goods_ready_at=goods_ready,
            loaded_at=loaded,
            departed_at=trip.depart_actual_at,
            gps_recorded_at=gps_at,
            gps_remaining_min=remaining,
            paused=paused,
            cutoff_at=cutoff_at,
        )
        try:
            eta = (
                stop.completed_at
                if stop.status == "delivered"
                else forecast_eta(state, now, config.eta_round_min, config.after_loaded_min)
            )
        except ValueError as exc:
            raise _missing("Verified preparation or routing evidence is insufficient.") from exc
        if eta is None:
            raise _missing("Vehicle forecast evidence is unavailable.")
        output.append((trip.id, pv.eta_at, eta))
    return output


async def recalculate(
    order_id: int,
    trigger: str,
    *,
    session: AsyncSession | None = None,
    signal_at: datetime | None = None,
    trusted_remaining: Mapping[int, tuple[datetime, int]] | None = None,
    delay_window: dict[str, str] | None = None,
) -> dict[str, object] | None:
    """Persist one signal-driven version and deduped alerts in the CALLER transaction.

    The current M6 stub does not pass its transaction yet: it fails closed instead
    of writing a forecast that survives a rolled-back execution event.
    No customer notification is sent; an approved window/draft adapter is pending.
    """
    if session is None:
        raise _missing("Transactional risk integration requires the caller's session.")
    now = clock.now()
    order = await session.scalar(select(CustomerOrder).where(CustomerOrder.id == order_id).with_for_update())
    if order is None:
        raise DomainError("NOT_FOUND", "Order not found.")
    if order.status not in _ACTIVE:
        return None
    if order.approved_plan_id is None or order.promise_end is None:
        raise _missing("Approved plan and commitment deadline are required.")
    market = await session.get(Market, order.market_id)
    plan = await session.get(FulfilmentPlan, order.approved_plan_id)
    if market is None or plan is None or plan.order_id != order.id:
        raise _missing("Approved market/plan evidence is unavailable.")
    config = _known_config(market)
    previous = await session.scalar(
        select(EtaForecast)
        .where(EtaForecast.order_id == order.id)
        .order_by(EtaForecast.version.desc())
        .limit(1)
    )
    events = (
        await session.scalars(
            select(MilestoneEvent)
            .where(MilestoneEvent.order_id == order.id, MilestoneEvent.plan_id == plan.id)
            .order_by(MilestoneEvent.occurred_at, MilestoneEvent.id)
        )
    ).all()
    if not await _valid_signal(session, order, plan, trigger, list(events), previous, now, signal_at, config):
        return None
    vehicle_inputs = await _vehicle_inputs(
        session, order, plan, market, list(events), now, config, trusted_remaining
    )
    try:
        overall_eta = order_forecast([eta for _, _, eta in vehicle_inputs])
        # Gap applies between the TWO ACTUAL consecutive persisted calculations.
        # An intervening fast negative signal cannot count as a second confirmation.
        prev_negative = 0
        if previous is not None and previous.slack_min < 0:
            if now - previous.computed_at >= timedelta(minutes=config.risk.consecutive_min_gap_min):
                prev_negative = previous.consecutive_negative
            elif previous.consecutive_negative >= config.risk.consecutive_negative:
                prev_negative = previous.consecutive_negative
        assessed = assess_risk(
            plan.eta_at,
            overall_eta,
            order.promise_end,
            now,
            prev_negative,
            config.risk.yellow_pct,
            config.risk.orange_pct,
            config.risk.min_reserve_min,
            config.risk.consecutive_negative,
        )
        trip_results = []
        for trip_id, planned, eta in vehicle_inputs:
            single = assess_risk(
                planned,
                eta,
                order.promise_end,
                now,
                0,
                config.risk.yellow_pct,
                config.risk.orange_pct,
                config.risk.min_reserve_min,
                config.risk.consecutive_negative,
            )
            trip_results.append(
                {
                    "trip_id": trip_id,
                    "forecast_eta": eta.isoformat(),
                    "risk_status": single.risk_status,
                    "risk_color": single.risk_color,
                }
            )
    except ValueError as exc:
        raise _missing("Invalid approved risk calculation evidence.") from exc
    if assessed.consumption_pct > Decimal("9999.99"):
        raise _missing("Forecast exceeds documented numeric storage range.")
    row = EtaForecast(
        order_id=order.id,
        version=(previous.version + 1 if previous else 1),
        computed_at=now,
        trigger=trigger,
        planned_eta=plan.eta_at,
        forecast_eta=overall_eta,
        commitment_deadline=order.promise_end,
        reserve_total_min=assessed.reserve_total_min,
        slack_min=assessed.slack_min,
        consumption_pct=assessed.consumption_pct,
        consecutive_negative=assessed.consecutive_negative,
        risk_status=assessed.risk_status,
        risk_color=assessed.risk_color,
    )
    session.add(row)
    await session.flush()
    # Critical conditions and orange warnings are order-scoped and DB-deduped.
    levels = {
        "RISK_ORANGE": assessed.risk_color == "orange",
        "PREDICTED_LATE": assessed.risk_status == "PREDICTED_LATE",
        "OVERDUE": assessed.risk_status == "OVERDUE",
    }
    for kind, active in levels.items():
        key = f"risk:{order.id}:{kind}"
        if active:
            await alert_service.raise_alert(
                session,
                market_id=order.market_id,
                type_=kind,
                level="warning" if kind == "RISK_ORANGE" else "critical",
                message=f"Order risk signal: {kind}.",
                dedupe_key=key,
                target_roles=("dispatcher",),
                order_id=order.id,
            )
        else:
            await alert_service.resolve(session, key, now=now)
    draft_status = "not_required"
    if assessed.risk_status == "PREDICTED_LATE" and (
        previous is None or previous.risk_status != "PREDICTED_LATE"
    ):
        # A forecast instant does NOT specify the customer-facing ETA window.
        # Never make up its boundaries. If owner-approved window is supplied,
        # request the existing D4 draft interface (which is still a stub on main).
        draft_status = "blocked_missing_approved_window"
        if delay_window is not None:
            try:
                from app.services.notification_templates import EtaWindow

                EtaWindow.model_validate(delay_window)
                await notify_service.create_delay_draft(order.id, delay_window)
                draft_status = "draft_requested"
            except NotImplementedError:
                draft_status = "blocked_notification_adapter"
            except ValueError as exc:
                raise _missing("Approved DELAY window is invalid.") from exc
    return {
        "version": row.version,
        "order_id": order.id,
        "forecast_eta": overall_eta.isoformat(),
        "risk_status": assessed.risk_status,
        "risk_color": assessed.risk_color,
        "consumption_pct": str(assessed.consumption_pct),
        "slack_min": assessed.slack_min,
        "consecutive_negative": assessed.consecutive_negative,
        "vehicles": trip_results,
        "delay_draft": draft_status,
    }
