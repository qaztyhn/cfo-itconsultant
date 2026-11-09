"""Validate local D7 JSON fixture schema, chronology, references, and safety expectations.

This is STRUCTURAL VALIDATION only. It is NOT a regulatory eligibility engine.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from generate import FIRST_DAY, FIXTURES, HISTORY_DAYS, SCHEMA, SOURCE, build, elapsed_minutes


class FixtureError(ValueError):
    """Local fixture corruption or self-contradiction."""


def instant(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise FixtureError(f"Timestamp lacks UTC offset: {value!r}")
    return moment.astimezone(UTC)


def require(ok: bool, explanation: str) -> None:
    if not ok:
        raise FixtureError(explanation)


def read_payloads(directory: Path = FIXTURES) -> dict[str, dict[str, Any]]:
    expected = set(build())
    actual = {path.name for path in directory.glob("*.json")}
    require(
        expected == actual,
        f"Fixture filenames differ: missing={expected - actual}, extra={actual - expected}",
    )
    return {name: json.loads((directory / name).read_text(encoding="utf-8"))
            for name in sorted(expected)}


def validate(payloads: dict[str, dict[str, Any]]) -> dict[str, int]:
    for name, payload in payloads.items():
        require(payload.get("schema_version") == SCHEMA, f"{name}: schema_version mismatch")
        require(payload.get("source") == SOURCE, f"{name}: provenance missing")
    manifest = payloads["manifest.json"]
    require(manifest.get("offline_only") is True, "Manifest must prohibit DB insertion")
    require(manifest["files"] == sorted(set(payloads) - {"manifest.json", "verification.json"}), "Manifest filenames mismatch")
    vehicles = payloads["vehicles.json"]["records"]
    drivers = payloads["drivers.json"]["records"]
    require(len(vehicles) in (8, 9, 10) and len(drivers) == 10, "Incorrect pilot population")
    vmap = {v["vehicle_code"]: v for v in vehicles}
    dmap = {d["driver_code"]: d for d in drivers}
    require(len(vmap) == len(vehicles) and len(dmap) == len(drivers), "Duplicate asset/driver identity")
    require(len({d["employee_no"] for d in drivers}) == 10, "Duplicate demo employee identity")
    for v in vehicles:
        require(v["market"] == "SE", "Only Sweden vehicle fixtures allowed")
        require(v["regulation_561_scope"] in ("in_scope", "out_of_scope", "unknown"),
                "Invalid Regulation 561 scope")
        scope_known = v["regulation_561_scope"] != "unknown"
        require(bool(v["scope_evidence"]) == scope_known,
                "Known and unknown scope must have distinct provenance")
        payload, gross = v["capacity_kg"], v["max_permissible_mass_kg"]
        require(isinstance(payload, int) and isinstance(gross, int) and 0 < payload < gross,
                "Payload must be distinct from plausible permissible mass")
        require(v["required_licence"] in ("B", "C", "CE"), "Invalid required licence")
        context = v["transport_context"]
        require(context["country"] == "SE" and isinstance(context["trailer_attached"], bool),
                "Missing transport context")
        require(v["warehouse_code"] in ("GBG", "STO", "MLM"), "Invalid warehouse")
    for d in drivers:
        require(d["market"] == "SE" and d["warehouse_code"] in ("GBG", "STO", "MLM"),
                "Invalid driver market/warehouse")
        require(d["licence_class"] in ("B", "C", "CE"), "Missing licence class")
        date.fromisoformat(d["licence_expires_on"])

    dates = {FIRST_DAY + timedelta(days=n) for n in range(HISTORY_DAYS)}
    seen: set[tuple[str, str]] = set()
    history_rows: list[dict[str, Any]] = []
    for week in range(1, 9):
        payload = payloads[f"history_week_{week:02d}.json"]
        require(payload["week"] == week and len(payload["records"]) == 70,
                f"Week {week} must contain 10 drivers x 7 days")
        for row in payload["records"]:
            code, day = row["driver_code"], row["work_date"]
            require(code in dmap and date.fromisoformat(day) in dates, "Unknown driver/history day")
            key = (code, day)
            require(key not in seen, "Duplicate driver/day coverage")
            seen.add(key)
            require(row["coverage_status"] in ("complete", "missing"), "Unstated completeness")
            require(not (row["verified_off_duty"] and row["duty_start"]), "Duty conflicts with off-day")
            if row["coverage_status"] == "missing":
                require(row["duty_start"] is None and row["duty_end"] is None
                        and row["driving_min"] is None and row["rest_before_duty"] is None
                        and not row["verified_off_duty"], "Missing history silently treated as clear")
            elif row["duty_start"] is not None:
                require(row["duty_end"] is not None and row["verified_rest_window"] is None,
                        "Duty interval incomplete")
                start, end = instant(row["duty_start"]), instant(row["duty_end"])
                require(start < end, "Nonpositive duty interval")
                total = 0
                for segment in row["driving_intervals"]:
                    drive_start, drive_end = instant(segment["start"]), instant(segment["end"])
                    require(start <= drive_start < drive_end <= end, "Driving outside duty interval")
                    require(elapsed_minutes(drive_start, drive_end) == segment["elapsed_min"],
                            "Bad driving segment elapsed minutes")
                    total += segment["elapsed_min"]
                require(total == row["driving_min"] and total <= elapsed_minutes(start, end),
                        "Driving time inconsistent with duty")
                if (rest := row["rest_before_duty"]) is not None:
                    require(instant(rest["start"]) < instant(rest["end"]) <= start,
                            "Rest must precede duty")
                    rest_minutes = elapsed_minutes(instant(rest["start"]), instant(rest["end"]))
                    require(rest_minutes == rest["elapsed_min"], "Rest elapsed time inconsistent")
            else:
                rest = row["verified_rest_window"]
                require(row["verified_off_duty"] and row["driving_min"] == 0 and rest is not None,
                        "Verified off day needs explicit rest window")
                require(elapsed_minutes(instant(rest["start"]), instant(rest["end"]))
                        == rest["elapsed_min"], "Off-day duration incorrect across DST")
            history_rows.append(row)
    require(len(seen) == len(dmap) * HISTORY_DAYS, "Not all 56 days recorded per driver")

    # Rest claims must be anchored to the preceding actually known duty,
    # never manufactured across a missing coverage day.
    for driver_code in dmap:
        rows = sorted((row for row in history_rows if row["driver_code"] == driver_code),
                      key=lambda row: row["work_date"])
        previous_end: str | None = None
        gap = False
        for row in rows:
            if row["coverage_status"] == "missing":
                gap = True
                continue
            if row["duty_start"] is None:
                continue
            rest = row["rest_before_duty"]
            if previous_end is None or gap:
                require(rest is None, "Missing or pre-window rest cannot be treated as proven")
            else:
                require(rest is not None, "Known consecutive duties need rest evidence")
                require(rest["start"] == previous_end and rest["end"] == row["duty_start"],
                        "Rest evidence does not match adjacent duties")
            previous_end = row["duty_end"]
            gap = False

    shifts = payloads["future_shifts.json"]["records"]
    shift_keys: set[tuple[str, str]] = set()
    for shift in shifts:
        code, day = shift["driver_code"], shift["work_date"]
        require(code in dmap and shift["warehouse_code"] == dmap[code]["warehouse_code"],
                "Shift references wrong driver warehouse")
        require(shift["status"] == "scheduled" and shift["record_kind"] == "official_shift_fixture",
                "Not a scheduled fixture")
        require(shift["authority_status"] == "synthetic_offline_not_db_confirmed",
                "Fixture must not masquerade as an authorized DB assignment")
        require(instant(shift["shift_start"]) < instant(shift["shift_end"]), "Invalid shift interval")
        require((code, day) not in shift_keys, "More than one official shift per person/day")
        require(shift["shift_start"][:10] == day, "Shift start not on work_date")
        shift_keys.add((code, day))
    require(len(shifts) == 51, "Expected 50 weekday shifts and one overnight duty")

    scenarios = payloads["scenarios.json"]["records"]
    ids: set[str] = set()
    for scenario in scenarios:
        key = scenario["scenario_id"]
        require(key not in ids, "Duplicate scenario ID")
        ids.add(key)
        require(scenario["driver_code"] in dmap and scenario["vehicle_code"] in vmap,
                "Scenario has unresolved fixture reference")
        require(instant(scenario["proposed_duty_start"]) < instant(scenario["proposed_duty_end"]),
                "Invalid proposed duty interval")
        require(0 <= scenario["proposed_driving_min"] <= elapsed_minutes(
                instant(scenario["proposed_duty_start"]), instant(scenario["proposed_duty_end"])),
                "Proposed driving exceeds elapsed duty")
        require(scenario["legal_compliance_certified"] is False,
                "Fixture may not certify legal compliance")
        overrides = scenario["input_overrides"]
        if "additional_duty" in overrides:
            extra = overrides["additional_duty"]
            day = extra["duty_start"][:10]
            require(overrides.get("supersedes_verified_off_duty_on") == day,
                    "Added duty must explicitly supersede off-duty evidence")
            require(instant(extra["duty_start"]) < instant(extra["duty_end"]),
                    "Added duty interval invalid")
        if scenario["expected_outcome"] == "unknown_fail_closed":
            require(bool(scenario["expected_reason_codes"]), "Unknown cannot be an eligible candidate")
        if scenario["expected_outcome"] == "candidate_for_planner_review":
            driver, vehicle = dmap[scenario["driver_code"]], vmap[scenario["vehicle_code"]]
            require(driver["warehouse_code"] == vehicle["warehouse_code"],
                    "Candidate driver and vehicle warehouse mismatch")
            require(vehicle["regulation_561_scope"] != "unknown", "Unknown vehicle cannot be candidate")
            require(date.fromisoformat(driver["licence_expires_on"]) >= date.fromisoformat(
                scenario["proposed_duty_start"][:10]), "Expired licence cannot be candidate")
            require(not any(row["coverage_status"] == "missing" for row in history_rows
                            if row["driver_code"] == scenario["driver_code"]),
                    "Candidate history cannot contain a missing day")
            require(any(shift["driver_code"] == scenario["driver_code"]
                        and instant(shift["shift_start"]) <= instant(scenario["proposed_duty_start"])
                        and instant(scenario["proposed_duty_end"]) <= instant(shift["shift_end"])
                        for shift in shifts), "Candidate lacks covering offline shift fixture")
        require(scenario["expected_outcome"] in (
            "candidate_for_planner_review", "block_automatic_approval", "unknown_fail_closed",
            "historical_evidence_only"), "Unexpected outcome classification")
    required = {"valid_candidate", "insufficient_rest", "missing_history", "off_shift_driver",
                "expired_licence", "unknown_vehicle_scope", "missing_vehicle_mass",
                "driving_day_over_limit", "overnight_duty", "missing_shift",
                "transport_context_changed", "licence_data_missing", "dst_overnight_history"}
    require(required <= ids, "Missing D7 golden scenarios")
    require(sum(1 for row in history_rows if row["coverage_status"] == "missing") == 1,
            "Missing-data scenario must remain explicit")
    return {"vehicles": len(vehicles), "drivers": len(drivers), "history_days": HISTORY_DAYS,
            "history_rows": len(seen), "future_shifts": len(shifts), "scenarios": len(scenarios)}


def main() -> int:
    try:
        result = validate(read_payloads())
    except (FixtureError, ValueError, KeyError, TypeError) as exc:
        print(f"D7 fixture validation failed: {exc}")
        return 1
    print("D7 fixture validation passed: " + ", ".join(f"{key}={value}" for key, value in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
