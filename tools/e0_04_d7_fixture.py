"""Build a hash-attested synthetic D7 input for the fixed disposable E0-04 clock.

This is fixture-only verification, never legal tachograph evidence. It does not
write HR tables or grant driver availability; named future shifts are separate.
"""

import hashlib
import json
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / ".e0_04_d7"
VEHICLES = (
    Path(__file__).resolve().parent
    / "d7_driver_fixtures"
    / "fixtures"
    / "vehicles.json"
)
TARGET = date(2026, 12, 1)
ZONE = ZoneInfo("Europe/Stockholm")


def stamp(day: date, hour: int) -> str:
    return datetime.combine(day, time(hour), ZONE).isoformat()


def write(name: str, value: dict) -> str:
    raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    (ROOT / name).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    ROOT.mkdir(exist_ok=True)
    shutil.copyfile(VEHICLES, ROOT / "vehicles.json")
    first = TARGET - timedelta(days=56)
    hashes = {
        "manifest.json": write(
            "manifest.json",
            {
                "source": "synthetic_demo",
                "market": "SE",
                "timezone": "Europe/Stockholm",
                "history_start": first.isoformat(),
                "history_end": (TARGET - timedelta(days=1)).isoformat(),
                "history_days_per_driver": 56,
                "offline_only": True,
            },
        ),
        "drivers.json": write(
            "drivers.json",
            {
                "records": [
                    {
                        "driver_code": "D02",
                        "employee_no": "DEMO-DRIVER-2",
                        "market": "SE",
                    }
                ]
            },
        ),
    }
    for week in range(8):
        records = []
        for offset in range(7):
            day = first + timedelta(days=7 * week + offset)
            if day.weekday() >= 5:
                records.append(
                    {
                        "driver_code": "D02",
                        "work_date": day.isoformat(),
                        "coverage_status": "complete",
                        "verified_off_duty": True,
                        "verified_rest_window": {
                            "start": stamp(day, 0),
                            "end": stamp(day + timedelta(days=1), 0),
                        },
                    }
                )
            else:
                records.append(
                    {
                        "driver_code": "D02",
                        "work_date": day.isoformat(),
                        "coverage_status": "complete",
                        "verified_off_duty": False,
                        "duty_start": stamp(day, 8),
                        "duty_end": stamp(day, 16),
                        "driving_intervals": [
                            {"start": stamp(day, 9), "end": stamp(day, 11)},
                            {"start": stamp(day, 12), "end": stamp(day, 14)},
                        ],
                    }
                )
        name = f"history_week_{week + 1:02d}.json"
        hashes[name] = write(name, {"source": "synthetic_demo", "records": records})
    write(
        "verification.json",
        {
            "source_kind": "synthetic_demo",
            "legal_verified": False,
            "verified_by": "Synthetic E0-04 Fixture Reviewer",
            "verified_at": "2026-12-01T09:00:00+01:00",
            "expires_at": "2026-12-02T09:00:00+01:00",
            "revoked": False,
            "sha256": hashes,
        },
    )
    print(
        "E0-04 synthetic D7 fixture ready for the disposable demo; legal_verified=false"
    )


if __name__ == "__main__":
    main()
