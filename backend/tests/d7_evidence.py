"""Test helpers: DriverEvidence builders (synthetic only). Never imported by application code."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.driver_history import DayEvidence, DriverEvidence

STOCKHOLM = ZoneInfo("Europe/Stockholm")
FIXTURES = Path(__file__).resolve().parents[2] / "tools" / "d7_driver_fixtures" / "fixtures"
VERIFIED_AT = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


def interval(day: date, start: str, end: str, *, next_day: bool = False) -> tuple[datetime, datetime]:
    begin = datetime.fromisoformat(f"{day.isoformat()}T{start}").replace(tzinfo=STOCKHOLM)
    finish_day = day + timedelta(days=int(next_day))
    return begin, datetime.fromisoformat(f"{finish_day.isoformat()}T{end}").replace(tzinfo=STOCKHOLM)


def evidence(
    employee_id: int,
    target: date,
    *,
    duty_every: int = 3,
    version: str = "v1",
    source_kind: str = "synthetic_demo",
    verified_by: str | None = "Synthetic Compliance Reviewer",
    verified_at: datetime | None = VERIFIED_AT,
    expires_at: datetime | None = None,
    revoked: bool = False,
    mutate=None,
) -> DriverEvidence:
    """56 complete market-local days before `target`: 08-16 duty (4 h driving) or a verified off day."""
    days: list[DayEvidence] = []
    for n in range(56, 0, -1):
        day = target - timedelta(days=n)
        if n % duty_every == 0:
            duty = interval(day, "08:00", "16:00")
            drive = (interval(day, "09:00", "11:00"), interval(day, "12:00", "14:00"))
            days.append(DayEvidence(day, "duty", duty, drive))
        else:
            days.append(DayEvidence(day, "off_duty", None, (), interval(day, "00:00", "23:59")))
    if mutate is not None:
        days = mutate(days)
    return DriverEvidence(
        employee_id, version, source_kind, verified_by, verified_at, expires_at, revoked, tuple(days)  # type: ignore[arg-type]
    )


def from_d7_fixture(driver_code: str) -> DriverEvidence:
    """Map the committed D7 synthetic history (fixture-local JSON) to the evidence document."""
    days: list[DayEvidence] = []
    for week in sorted(FIXTURES.glob("history_week_*.json")):
        for rec in json.loads(week.read_text(encoding="utf-8"))["records"]:
            if rec["driver_code"] != driver_code:
                continue
            local = date.fromisoformat(rec["work_date"])
            parse = datetime.fromisoformat
            if rec["coverage_status"] == "missing":
                days.append(DayEvidence(local, "unknown"))
            elif rec["verified_off_duty"]:
                w = rec["verified_rest_window"]
                days.append(DayEvidence(local, "off_duty", None, (), (parse(w["start"]), parse(w["end"]))))
            else:
                days.append(
                    DayEvidence(
                        local,
                        "duty",
                        (parse(rec["duty_start"]), parse(rec["duty_end"])),
                        tuple((parse(s["start"]), parse(s["end"])) for s in rec["driving_intervals"]),
                    )
                )
    return DriverEvidence(
        0, "d7.synthetic.v1", "synthetic_demo", "Synthetic Reviewer", VERIFIED_AT, None, False, tuple(days)
    )
