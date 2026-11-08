"""Generate deterministic, OFFLINE Swedish D7 golden fixtures (standard library only).

No database, API, seed or filesystem access outside this directory. These are local
fixture schemas, not SQLAlchemy rows and not a source of legally certified scope.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
TZ = ZoneInfo("Europe/Stockholm")
FIRST_DAY = date(2026, 9, 14)
HISTORY_DAYS = 56
FUTURE_START = date(2026, 11, 9)
SCHEMA = "d7.synthetic.v1"
SOURCE = "synthetic_demo"
WAREHOUSES = ("GBG", "STO", "MLM")


def local(day: date, hour: int, minute: int = 0, *, fold: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, fold=fold), TZ)


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="minutes")


def elapsed_minutes(start: datetime, end: datetime) -> int:
    """Absolute elapsed time: aware subtraction via UTC handles DST folds correctly."""
    return int((end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() // 60)


def interval(start: datetime, end: datetime) -> dict[str, object]:
    return {"start": iso(start), "end": iso(end), "elapsed_min": elapsed_minutes(start, end)}


def wrapped(records: list[dict[str, object]], kind: str, **meta: object) -> dict[str, object]:
    return {"schema_version": SCHEMA, "source": SOURCE, "kind": kind, **meta, "records": records}


def vehicles() -> dict[str, object]:
    # Payload is NOT max permissible mass. Scope labels are synthetic reference
    # inputs, never derived from type, payload, or mass.
    specs = (
        ("GBG-03-02", "GBG", "van", 1000, 3500, "B", "unknown", None),
        ("GBG-12-03", "GBG", "rigid", 6000, 12000, "C", "in_scope", "synthetic_checked_context"),
        ("STO-12-04", "STO", "rigid", 6000, 12000, "C", "in_scope", "synthetic_checked_context"),
        ("MLM-12-02", "MLM", "rigid", 6000, 12000, "C", "in_scope", "synthetic_checked_context"),
        ("GBG-18-01", "GBG", "rigid", 10000, 18000, "C", "in_scope", "synthetic_checked_context"),
        ("MLM-18-01", "MLM", "rigid", 10000, 18000, "C", "in_scope", "synthetic_checked_context"),
        ("GBG-26-01", "GBG", "articulated", 16000, 26000, "CE", "in_scope", "synthetic_checked_context"),
        ("STO-CR-01", "STO", "crane", 8000, 18000, "C", "unknown", None),
        ("MLM-DUMP-01", "MLM", "tipper", 12000, 26000, "C", "out_of_scope", "synthetic_checked_context"),
    )
    records: list[dict[str, object]] = []
    for code, warehouse, kind, payload, mass, licence, scope, evidence in specs:
        records.append({
            "vehicle_code": code,
            "market": "SE",
            "warehouse_code": warehouse,
            "vehicle_type": kind,
            "capacity_kg": payload,
            "max_permissible_mass_kg": mass,
            "required_licence": licence,
            "regulation_561_scope": scope,
            "scope_evidence": evidence,
            "transport_context": {"country": "SE", "operation": "domestic_goods",
                                  "trailer_attached": False, "trailer_max_permissible_mass_kg": None,
                                  "exception_claim": None},
            "scope_note": "Synthetic classification input; legal applicability requires independent review",
        })
    return wrapped(records, "vehicles")


def drivers() -> dict[str, object]:
    licences = ("B", "C", "CE", "C", "C", "CE", "C", "B", "CE", "C")
    records = []
    for n, licence in enumerate(licences, start=1):
        records.append({
            "driver_code": f"D{n:02d}", "employee_no": f"DEMO-DRIVER-{n}",
            "market": "SE", "warehouse_code": WAREHOUSES[(n - 1) % 3],
            "licence_class": licence, "licence_expires_on": "2026-01-01" if n == 10 else "2030-01-01",
            "adr": False,
        })
    return wrapped(records, "drivers")


def one_history_day(driver: str, day: date, previous_end: datetime | None,
                    gap: bool) -> tuple[dict[str, object], datetime | None, bool]:
    missing = driver == "D07" and day == date(2026, 10, 30)
    dst_night = driver == "D09" and day == date(2026, 10, 25)
    working = day.weekday() < 5 or dst_night
    base = {"driver_code": driver, "work_date": day.isoformat(),
            "coverage_status": "missing" if missing else "complete",
            "duty_start": None, "duty_end": None, "driving_min": None if missing else 0,
            "driving_intervals": [], "rest_before_duty": None, "verified_off_duty": False,
            "verified_rest_window": None}
    if missing:
        return base, previous_end, True
    if not working:
        base["verified_off_duty"] = True
        base["verified_rest_window"] = interval(local(day, 0), local(day + timedelta(days=1), 0))
        return base, previous_end, gap
    start = local(day, 0, 30) if dst_night else local(day, 8)
    end = local(day, 4, 30) if dst_night else local(day, 16)
    if dst_night:
        drive = (interval(local(day, 1), local(day, 2, fold=0)),
                 interval(local(day, 2, 30, fold=1), local(day, 3, 30)))
    else:
        drive = (interval(local(day, 9), local(day, 11)),
                 interval(local(day, 12), local(day, 14)))
    base.update({"duty_start": iso(start), "duty_end": iso(end),
                 "driving_min": sum(int(x["elapsed_min"]) for x in drive),
                 "driving_intervals": list(drive)})
    if previous_end is not None and not gap:
        base["rest_before_duty"] = interval(previous_end, start)
    return base, end, False


def history() -> list[dict[str, object]]:
    days = [FIRST_DAY + timedelta(days=n) for n in range(HISTORY_DAYS)]
    by_week: list[list[dict[str, object]]] = [[] for _ in range(8)]
    for n in range(1, 11):
        driver = f"D{n:02d}"
        previous: datetime | None = None
        gap = False
        for offset, day in enumerate(days):
            record, previous, gap = one_history_day(driver, day, previous, gap)
            by_week[offset // 7].append(record)
    return [wrapped(rows, "driver_history", week=week + 1,
                    date_from=days[week * 7].isoformat(),
                    date_to=days[week * 7 + 6].isoformat(),
                    timezone="Europe/Stockholm", coverage_days=7)
            for week, rows in enumerate(by_week)]


def future_shifts() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for n in range(1, 11):
        for delta in range(5):
            day = FUTURE_START + timedelta(days=delta)
            wh = WAREHOUSES[(n - 1) % 3]
            rows.append({
                "driver_code": f"D{n:02d}", "warehouse_code": wh,
                "work_date": day.isoformat(), "status": "scheduled",
                "shift_start": iso(local(day, 7)), "shift_end": iso(local(day, 16)),
                "assigned_by_employee_no": f"DEMO-{wh}-W00",
                "authority_status": "synthetic_offline_not_db_confirmed",
                "record_kind": "official_shift_fixture",
            })
    day = date(2026, 11, 14)
    rows.append({"driver_code": "D06", "warehouse_code": "MLM",
                 "work_date": day.isoformat(), "status": "scheduled",
                 "shift_start": iso(local(day, 20)),
                 "shift_end": iso(local(day + timedelta(days=1), 4)),
                 "assigned_by_employee_no": "DEMO-MLM-W00",
                 "authority_status": "synthetic_offline_not_db_confirmed",
                 "record_kind": "official_shift_fixture"})
    return wrapped(rows, "future_shifts", timezone="Europe/Stockholm")


def scenarios() -> dict[str, object]:
    # Outcome/reason are GOLDEN EXPECTATIONS for later gate tests, NOT an
    # eligibility engine and NOT a finding of legal compliance.
    data = (
        ("valid_candidate", "D04", "GBG-12-03", "2026-11-09T09:00+01:00", "2026-11-09T14:00+01:00", 240,
         "candidate_for_planner_review", [], {}),
        ("insufficient_rest", "D04", "GBG-12-03", "2026-11-09T07:00+01:00", "2026-11-09T12:00+01:00", 180,
         "block_automatic_approval", ["DRIVER_REST_INSUFFICIENT"],
         {"additional_duty": {"duty_start": "2026-11-08T20:00+01:00",
                              "duty_end": "2026-11-08T23:00+01:00", "driving_min": 60},
          "supersedes_verified_off_duty_on": "2026-11-08"}),
        ("missing_history", "D07", "GBG-12-03", "2026-11-09T09:00+01:00", "2026-11-09T13:00+01:00", 120,
         "unknown_fail_closed", ["DRIVER_HISTORY_MISSING"], {}),
        ("off_shift_driver", "D04", "GBG-12-03", "2026-11-09T18:00+01:00", "2026-11-09T22:00+01:00", 120,
         "block_automatic_approval", ["OUTSIDE_DRIVER_SHIFT"], {}),
        ("expired_licence", "D10", "GBG-12-03", "2026-11-09T09:00+01:00", "2026-11-09T13:00+01:00", 120,
         "block_automatic_approval", ["LICENCE_EXPIRED"], {}),
        ("unknown_vehicle_scope", "D01", "GBG-03-02", "2026-11-09T09:00+01:00", "2026-11-09T12:00+01:00", 90,
         "unknown_fail_closed", ["VEHICLE_SCOPE_UNKNOWN"], {}),
        ("missing_vehicle_mass", "D04", "GBG-12-03", "2026-11-09T09:00+01:00", "2026-11-09T13:00+01:00", 100,
         "unknown_fail_closed", ["VEHICLE_DATA_MISSING"],
         {"vehicle_override": {"max_permissible_mass_kg": None}}),
        ("driving_day_over_limit", "D04", "GBG-12-03",
         "2026-11-09T07:00+01:00", "2026-11-09T18:00+01:00", 550,
         "block_automatic_approval", ["DRIVING_TIME_EXCEEDED", "DRIVER_HOURS_EXCEEDED"],
         {"future_shift_override": {"shift_start": "2026-11-09T07:00+01:00",
                                    "shift_end": "2026-11-09T20:00+01:00"}}),
        ("overnight_duty", "D06", "MLM-12-02", "2026-11-14T21:00+01:00", "2026-11-15T02:00+01:00", 180,
         "candidate_for_planner_review", [], {}),
        ("missing_shift", "D04", "GBG-12-03", "2026-11-15T09:00+01:00", "2026-11-15T13:00+01:00", 120,
         "unknown_fail_closed", ["DRIVER_SHIFT_MISSING"], {}),
        ("transport_context_changed", "D04", "GBG-12-03",
         "2026-11-09T09:00+01:00", "2026-11-09T12:00+01:00", 120,
         "unknown_fail_closed", ["VEHICLE_SCOPE_UNKNOWN"],
         {"vehicle_override": {"regulation_561_scope": "unknown",
                               "transport_context": {"country": "SE", "operation": "international_goods",
                                                     "trailer_attached": True,
                                                     "trailer_max_permissible_mass_kg": None,
                                                     "exception_claim": None}}}),
        ("licence_data_missing", "D01", "GBG-03-02", "2026-11-09T09:00+01:00", "2026-11-09T12:00+01:00", 100,
         "unknown_fail_closed", ["DRIVER_LICENCE_MISSING"],
         {"driver_override": {"licence_class": None}}),
        ("dst_overnight_history", "D09", "MLM-18-01", "2026-10-25T00:30+02:00", "2026-10-25T04:30+01:00", 120,
         "historical_evidence_only", [], {"history_reference": "history_week_06.json"}),
    )
    records = []
    for key, driver, vehicle, start, end, drive_min, outcome, reasons, overrides in data:
        records.append({"scenario_id": key, "driver_code": driver, "vehicle_code": vehicle,
                        "proposed_duty_start": start, "proposed_duty_end": end,
                        "proposed_driving_min": drive_min,
                        "expected_outcome": outcome, "expected_reason_codes": reasons,
                        "input_overrides": overrides,
                        "legal_compliance_certified": False})
    return wrapped(records, "scenarios", timezone="Europe/Stockholm",
                   note="Golden expectations; not a safety-gate implementation")


def build() -> dict[str, dict[str, object]]:
    files = {"vehicles.json": vehicles(), "drivers.json": drivers(),
             "future_shifts.json": future_shifts(), "scenarios.json": scenarios()}
    for n, rows in enumerate(history(), start=1):
        files[f"history_week_{n:02d}.json"] = rows
    files["manifest.json"] = {"schema_version": SCHEMA, "source": SOURCE,
                              "market": "SE", "timezone": "Europe/Stockholm",
                              "history_start": FIRST_DAY.isoformat(),
                              "history_end": (FIRST_DAY + timedelta(days=HISTORY_DAYS - 1)).isoformat(),
                              "history_days_per_driver": HISTORY_DAYS,
                              "future_start": FUTURE_START.isoformat(),
                              "vehicle_count": len(files["vehicles.json"]["records"]),
                              "driver_count": len(files["drivers.json"]["records"]),
                              "files": sorted(files), "offline_only": True}
    return files


def encoded(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def generate(*, check: bool) -> list[str]:
    expected = build()
    errors: list[str] = []
    if not check:
        FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, payload in expected.items():
        target = FIXTURES / name
        data = encoded(payload)
        if check:
            if not target.is_file() or target.read_bytes() != data:
                errors.append(f"Missing or nondeterministic fixture: {name}")
        else:
            target.write_bytes(data)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--write", action="store_true", help="Regenerate local JSON fixtures only")
    options.add_argument("--check", action="store_true", help="Compare committed JSON against generator")
    args = parser.parse_args()
    issues = generate(check=args.check)
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print(f"D7 offline fixtures {'verified' if args.check else 'generated'}: {len(build())} JSON files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
