"""D8 operational-review slots: 07:00 and 13:00 market-local (DEC-D8-OPS-20261109). Pure, NOT scheduled.

Only the owner-approved clock times are encoded. No cron/worker is activated here (hosting, SLA, tick
auth and other D8 jobs require separate production approval; other proposed cadences are
staging/demo-only under DEC-D8-STAGING-SCHEDULE-20261109). Order polling and event-driven processing are
separate flows. Each slot has a stable key per market/local date/time so a catch-up or a DST day never
runs a slot twice.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

REVIEW_TIMES: tuple[time, ...] = (time(7, 0), time(13, 0))


@dataclass(frozen=True)
class ReviewSlot:
    key: str  # "SE:2026-11-10:07:00"
    due_at: datetime  # aware instant


def slots_for_day(market: str, tz: str, local_day: date) -> tuple[ReviewSlot, ...]:
    zone = ZoneInfo(tz)
    out = []
    for at in REVIEW_TIMES:
        due = datetime.combine(
            local_day, at, zone
        )  # 07:00/13:00 never fall in a DST gap/fold (changes are ~02-03h)
        out.append(ReviewSlot(f"{market}:{local_day.isoformat()}:{at:%H:%M}", due))
    return tuple(out)


def due_slots(market: str, tz: str, now: datetime, done: Collection[str]) -> tuple[ReviewSlot, ...]:
    """Slots of the current market-local day whose time has passed and that have not run yet."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Review time must be aware")
    local_day = now.astimezone(ZoneInfo(tz)).date()
    return tuple(s for s in slots_for_day(market, tz, local_day) if s.due_at <= now and s.key not in done)


def next_slot(market: str, tz: str, now: datetime) -> ReviewSlot:
    zone = ZoneInfo(tz)
    day = now.astimezone(zone).date()
    for offset in (0, 1):
        for slot in slots_for_day(market, tz, day + timedelta(days=offset)):
            if slot.due_at > now:
                return slot
    raise AssertionError("unreachable")
