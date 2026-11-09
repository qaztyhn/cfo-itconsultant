"""Fail-closed, explicitly attested *synthetic* D7 reader for disposable Swedish demos.

This is not a production HR/tachograph importer. Every read rechecks the manifest,
the attestation hashes and the exact 56-day coverage for the frozen demo clock.
Actual legal verification is always false (see driver_history.verify_history).
Official future shifts still come solely from the existing database workflow.
"""

import hashlib
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.hr import Employee
from app.services.driver_history import DayEvidence, DriverEvidence

DEMO_NOW = "2026-11-04T10:05:00+01:00"
DEMO_MARKET = "SE"
WEEKS = tuple(f"history_week_{n:02d}.json" for n in range(1, 9))
FILES = ("manifest.json", "drivers.json", *WEEKS)


def _demo_enabled() -> bool:
    s = get_settings()
    return s.app_env == "test" and s.app_now == DEMO_NOW and os.environ.get("DEMO_DISPOSABLE") == "1"


def _document(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid synthetic D7 document")
    return value


def _instant(value: str) -> datetime:
    when = datetime.fromisoformat(value)
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("Naive D7 timestamp")
    return when


class DisposableD7Reader:
    """Only accepts hash-matched, named synthetic attestation; no implicit verifier.

    Dev 2 supplies 'verification.json' in a disposable fixture mount:
    {"source_kind":"synthetic_demo", "verified_by":"Synthetic Demo Reviewer",
     "verified_at":"...offset...", "expires_at":"...offset...",
     "sha256":{"manifest.json":"...", "drivers.json":"...",
               "history_week_01.json":"...", ...}}
    Never set this file from unverified production data.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _load(self, employee_no: str, target: date, employee_id: int) -> DriverEvidence | None:
        manifest = _document(self.root / "manifest.json")
        start = target - timedelta(days=56)
        end = target - timedelta(days=1)
        if (
            manifest.get("source") != "synthetic_demo"
            or manifest.get("market") != DEMO_MARKET
            or manifest.get("timezone") != "Europe/Stockholm"
            or manifest.get("history_start") != start.isoformat()
            or manifest.get("history_end") != end.isoformat()
            or manifest.get("history_days_per_driver") != 56
            or manifest.get("offline_only") is not True
        ):
            return None
        proof = _document(self.root / "verification.json")
        if proof.get("source_kind") != "synthetic_demo" or proof.get("revoked") is not False:
            return None
        who = proof.get("verified_by")
        if not isinstance(who, str) or not who.strip():
            return None
        hashes = proof.get("sha256")
        if not isinstance(hashes, dict) or set(hashes) != set(FILES):
            return None
        for name in FILES:
            expected = hashes.get(name)
            if not isinstance(expected, str) or len(expected) != 64:
                return None
            if hashlib.sha256((self.root / name).read_bytes()).hexdigest() != expected:
                return None
        verified_at = _instant(proof["verified_at"])
        expires_at = _instant(proof["expires_at"])
        drivers = _document(self.root / "drivers.json")
        matches = [
            row["driver_code"]
            for row in drivers.get("records", [])
            if row.get("employee_no") == employee_no and row.get("market") == DEMO_MARKET
        ]
        if len(matches) != 1:
            return None
        code = matches[0]
        days = []
        for name in WEEKS:
            week = _document(self.root / name)
            if week.get("source") != "synthetic_demo":
                return None
            for row in week.get("records", []):
                if row.get("driver_code") != code:
                    continue
                day = date.fromisoformat(row["work_date"])
                if row.get("coverage_status") == "missing":
                    days.append(DayEvidence(day, "unknown"))
                elif row.get("coverage_status") != "complete":
                    return None
                elif row.get("verified_off_duty") is True:
                    rest = row.get("verified_rest_window")
                    if not isinstance(rest, dict):
                        return None
                    days.append(
                        DayEvidence(
                            day, "off_duty", rest=(_instant(rest["start"]), _instant(rest["end"]))
                        )
                    )
                else:
                    driving = tuple(
                        (_instant(span["start"]), _instant(span["end"]))
                        for span in row.get("driving_intervals", [])
                    )
                    days.append(
                        DayEvidence(
                            day,
                            "duty",
                            duty=(_instant(row["duty_start"]), _instant(row["duty_end"])),
                            driving=driving,
                        )
                    )
        # The authoritative 56-day verifier still checks missing/duplicate/unknown
        # days, overlaps, work/rest, expiry and future attestation timestamps.
        return DriverEvidence(
            employee_id=employee_id,
            version="d7.synthetic:" + hashes["manifest.json"],
            source_kind="synthetic_demo",
            verified_by=who,
            verified_at=verified_at,
            expires_at=expires_at,
            revoked=False,
            days=tuple(days),
        )

    async def read(
        self, session: AsyncSession, employee_id: int, market_code: str, target_date: date
    ) -> DriverEvidence | None:
        if not _demo_enabled() or market_code != DEMO_MARKET:
            return None
        employee = await session.get(Employee, employee_id)
        if employee is None:
            return None
        try:
            return self._load(employee.employee_no, target_date, employee_id)
        except (OSError, ValueError, KeyError, TypeError, OverflowError):
            return None


def configure_disposable_reader() -> None:
    """Opt-in at app creation, never auto-enabled by APP_ENV alone."""
    path = os.environ.get("DEMO_D7_FIXTURE_DIR")
    if not path:
        return
    if not _demo_enabled():
        raise RuntimeError("D7 synthetic reader may only run in the frozen disposable demo")
    from app.services.driver_history import configure_reader

    configure_reader(DisposableD7Reader(Path(path)))
