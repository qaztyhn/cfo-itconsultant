"""Driver 56-day duty/driving/rest history verification (D7-1…D7-4, DEC-DEV2-D7-001, DEC-DRIVER-001).

Pure verification over a typed evidence document plus a reader seam. NOTHING here invents a storage contract:
how evidence is persisted/attested (docs/proposals/D7_DRIVER_HISTORY_COMPLETENESS_CONTRACT.md options A/B) is
still an owner decision, so the production reader is `None` and every caller stays FAIL CLOSED
(`EVIDENCE_MISSING`). A reader (Dev 2's verified importer, or a test double) returns `DriverEvidence`.

`history_complete` is true only when ALL hold for the rolling window of 56 market-local dates ending the day
before `target_date`:
- evidence exists, is not revoked, not expired, names a verifier and a verification time not in the future;
- synthetic demo evidence is accepted only outside production and is never legal verification;
- every date has exactly one record; `unknown`/missing/duplicate dates, naive timestamps, overlapping duties,
  driving outside its duty, a duty on a day marked off duty, or an off-duty day without a verified rest window
  make it incomplete/inconsistent. An absent record is unknown, never rest.
Rest (11 h uninterrupted by default), driving and working-time limits are then enforced by the existing engine
(`driver_problem`) from the proof's separate duty and driving data, identically for planning, approval and
dispatch. No new regulatory rule is added; Regulation 561 applicability stays with the vehicle record.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

WINDOW_DAYS = 56
Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class DayEvidence:
    local_date: date  # market-local calendar date of the duty start / of the off-duty day
    status: Literal["duty", "off_duty", "unknown"]
    duty: Interval | None = None
    driving: tuple[Interval, ...] = ()
    rest: Interval | None = None  # verified rest window; required to prove an off-duty day


@dataclass(frozen=True)
class DriverEvidence:
    employee_id: int
    version: str
    source_kind: Literal["synthetic_demo", "verified_import"]
    verified_by: str | None
    verified_at: datetime | None
    expires_at: datetime | None
    revoked: bool
    days: tuple[DayEvidence, ...]


@dataclass(frozen=True)
class HistoryProof:
    complete: bool
    reasons: tuple[str, ...]
    duty_history: tuple[Interval, ...] = ()
    driving_min_by_day: dict[date, int] = field(default_factory=dict)
    driving_min_week: int = 0
    driving_min_fortnight: int = 0
    source_kind: str | None = None
    version: str | None = None
    legal_verified: bool = False  # never true for synthetic demo evidence


class DriverEvidenceReader(Protocol):
    async def read(
        self, session: AsyncSession, employee_id: int, market_code: str, target_date: date
    ) -> DriverEvidence | None: ...


_reader: DriverEvidenceReader | None = None  # production default: no approved evidence source yet


def configure_reader(reader: DriverEvidenceReader | None) -> None:
    global _reader
    _reader = reader


def _aware(*values: datetime | None) -> bool:
    return all(v is not None and v.tzinfo is not None and v.utcoffset() is not None for v in values)


def _minutes(interval: Interval) -> int:
    return int((interval[1] - interval[0]).total_seconds() // 60)


def _fail(*reasons: str) -> HistoryProof:
    return HistoryProof(False, tuple(dict.fromkeys(reasons)))


def verify_history(
    evidence: DriverEvidence | None,
    *,
    target_date: date,
    zone: ZoneInfo,
    now: datetime,
    allow_synthetic: bool,
) -> HistoryProof:
    if evidence is None:
        return _fail("EVIDENCE_MISSING")
    if evidence.revoked:
        return _fail("EVIDENCE_REVOKED")
    if not _aware(now):
        raise ValueError("Verification time must be aware")
    if evidence.expires_at is not None and (not _aware(evidence.expires_at) or evidence.expires_at <= now):
        return _fail("EVIDENCE_EXPIRED")
    if (
        not evidence.verified_by
        or not evidence.verified_by.strip()
        or not _aware(evidence.verified_at)
        or evidence.verified_at > now  # type: ignore[operator]
    ):
        return _fail("EVIDENCE_UNVERIFIED")
    if evidence.source_kind == "synthetic_demo" and not allow_synthetic:
        return _fail("SYNTHETIC_NOT_ALLOWED")
    if evidence.source_kind not in ("synthetic_demo", "verified_import"):
        return _fail("EVIDENCE_UNVERIFIED")
    window = [target_date - timedelta(days=n) for n in range(WINDOW_DAYS, 0, -1)]
    by_date: dict[date, list[DayEvidence]] = defaultdict(list)
    for day in evidence.days:
        by_date[day.local_date].append(day)
    problems: list[str] = []
    duties: list[Interval] = []
    driving_by_day: dict[date, int] = {}
    for local_date in window:
        records = by_date.get(local_date, [])
        if not records:
            problems.append("DAY_MISSING")
            continue
        if len(records) > 1:
            problems.append("DAY_DUPLICATE")
            continue
        record = records[0]
        if record.status == "unknown":
            problems.append("DAY_UNKNOWN")
        elif record.status == "off_duty":
            if record.duty is not None or record.driving:
                problems.append("INCONSISTENT")
            elif record.rest is None or not _aware(*record.rest) or record.rest[1] <= record.rest[0]:
                problems.append("REST_UNPROVEN")  # absence of work is not proof without a rest window
        elif record.status == "duty":
            duty = record.duty
            if duty is None or not _aware(*duty) or duty[1] <= duty[0]:
                problems.append("INCONSISTENT")
                continue
            if duty[0].astimezone(zone).date() != local_date:
                problems.append("INCONSISTENT")
            segments = sorted(record.driving)
            if any(
                not _aware(*s) or s[1] <= s[0] or s[0] < duty[0] or s[1] > duty[1] for s in segments
            ) or any(b[0] < a[1] for a, b in zip(segments, segments[1:], strict=False)):
                problems.append("INCONSISTENT")  # driving must lie inside its duty and not overlap itself
            duties.append(duty)
            driving_by_day[local_date] = sum(_minutes(s) for s in segments)
        else:
            problems.append("INCONSISTENT")
    ordered = sorted(duties)
    if any(b[0] < a[1] for a, b in zip(ordered, ordered[1:], strict=False)):
        problems.append("INCONSISTENT")  # two duties overlap: contradictory evidence
    if problems:
        return _fail(*problems)
    week = sum(m for d, m in driving_by_day.items() if d >= target_date - timedelta(days=7))
    fortnight = sum(m for d, m in driving_by_day.items() if d >= target_date - timedelta(days=14))
    return HistoryProof(
        True,
        (),
        tuple(ordered),
        driving_by_day,
        week,
        fortnight,
        evidence.source_kind,
        evidence.version,
        legal_verified=False if evidence.source_kind == "synthetic_demo" else True,
    )


async def load_proof(
    session: AsyncSession,
    employee_id: int,
    market_code: str,
    zone: ZoneInfo,
    now: datetime,
) -> HistoryProof:
    """Verified history proof as of `now` (market-local today); fail closed without a reader."""
    target = now.astimezone(zone).date()
    if _reader is None:
        return _fail("EVIDENCE_MISSING")
    evidence = await _reader.read(session, employee_id, market_code, target)
    return verify_history(
        evidence,
        target_date=target,
        zone=zone,
        now=now,
        allow_synthetic=get_settings().app_env != "production",
    )
