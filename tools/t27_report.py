"""Fail-closed 14-row T27 ledger derived only from real Playwright evidence."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

STEPS = (
    ("1", "CFO Sync & Check: enter the pre-submitted order reference", "E0, T26"),
    ("2", "Sales Sync and feasibility", "E0, E1"),
    ("3", "Sales rank 1-3 selection", "T19, T26"),
    ("4", "Approve, WMS ACK, Dispatcher assignment", "E1, T12, T15"),
    ("5", "CONFIRMED email", "E1, E2, T21, #223"),
    ("6", "Dispatcher Plan Review", "E4"),
    ("7", "Warehouse START_PREP, GOODS_READY, LOADED", "E3"),
    ("8", "Driver DISPATCHED, location, DELIVERED", "T06, T13, T14, T16"),
    ("9", "Dispatcher tracking, ETA and DELAY", "T08, T17, E5"),
    ("10", "Lifecycle emails", "E2, T21"),
    ("11", "CS order and ETA history", "T03, T14"),
    ("12", "Five KPIs by approval path", "T22"),
    ("12b", "Order and revenue status groups", "T26, T29, T30"),
    ("13", "FAILED exception and Dispatcher alert", "T07, T18, T26"),
)

VALID = {"PASS", "FAIL", "BLOCKED", "NOT VERIFIED"}
NOT_VERIFIED = "NOT VERIFIED"


def load(path: Path) -> dict:
    if not path.exists():
        return {"result": "NOT VERIFIED", "reason": "Missing browser output"}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Invalid T27 fixture JSON")
    return value


def _status(value: str | None) -> str:
    return value if isinstance(value, str) and value in VALID else NOT_VERIFIED


def _fixture(trips: int) -> str:
    return f"SE-E3-{trips}T"


def _with_reason(text: str, reason: str | None) -> str:
    return f"{text} ({reason})" if reason else text


def _aware_time(value: str) -> datetime:
    instant = datetime.fromisoformat(value)
    if instant.utcoffset() is None:
        raise ValueError("A milestone timestamp must include an offset")
    return instant


def _milestones(events: list[dict], *, browser: bool = False) -> list[tuple]:
    result = []
    seen: set[int] = set()
    for item in events:
        event_id = item["event_id"] if browser else item["id"]
        if type(event_id) is not int or event_id <= 0 or event_id in seen:
            raise ValueError("Invalid or repeated milestone ID")
        seen.add(event_id)
        trip_id = item["payload"].get("trip_id") if browser else item["trip_id"]
        if trip_id is not None and type(trip_id) is not int:
            raise ValueError("Invalid milestone trip ID")
        result.append(
            (event_id, item["event_type"], trip_id, _aware_time(item["occurred_at"]))
        )
    return result


def _warehouse(trips: int, case: dict) -> tuple[str, str]:
    if case.get("result") not in {"PASS", "FAIL"}:
        return NOT_VERIFIED, "Browser evidence missing or unrun"
    browser_status = case.get("warehouse_browser_status")
    if browser_status != "PASS":
        if browser_status == "FAIL" or case.get("result") == "FAIL":
            return "FAIL", "Warehouse browser milestones did not complete"
        return NOT_VERIFIED, "Warehouse browser outcome is missing"
    if case.get("trip_count") != trips or case.get("order_no") != _fixture(trips):
        return "FAIL", "Fixture identity mismatch"
    trip_ids = list(range(1, trips + 1))
    expected = [
        ("START_PREP", None),
        ("GOODS_READY", None),
        *(("LOADED", trip) for trip in trip_ids),
    ]
    try:
        events = case["events"]
        browser = _milestones(events, browser=True)
        persisted = _milestones(case["persisted_events"])
        if (
            browser != persisted
            or [(kind, trip) for _, kind, trip, _ in persisted] != expected
        ):
            return (
                "FAIL",
                "Browser and PostgreSQL milestones must match, with one LOADED per trip",
            )
        after_load = events[2:]
        if [event["order_status"] for event in after_load] != ["GOODS_READY"] * (
            trips - 1
        ) + ["LOADED"]:
            return (
                "FAIL",
                "LOADED acknowledgements disagree with the sequence of trip loads",
            )
        if not all(
            event["ack_refetch"]["status"] == event["order_status"]
            and event["ack_refetch"]["loaded_trips"] == trip_ids[:index]
            for index, event in enumerate(after_load, start=1)
        ):
            return "FAIL", "Queue refresh disagrees with the acknowledged trip loads"
        reload = case["reload_queue"]
        if reload["status"] != "LOADED" or reload["loaded_trips"] != trip_ids:
            return "FAIL", "Reloaded queue does not show every trip loaded"
    except (AttributeError, KeyError, TypeError, ValueError):
        return "FAIL", "Invalid or incomplete warehouse milestone evidence"

    postgres = case.get("warehouse_postgres")
    if postgres is None:
        return NOT_VERIFIED, "PostgreSQL order and trip state is missing"
    try:
        db_trips = [(trip["trip_id"], trip["status"]) for trip in postgres["trips"]]
        if (
            postgres["order_status"] != "LOADED"
            or postgres["milestones_match_browser"] is not True
            or any(type(trip_id) is not int for trip_id, _ in db_trips)
            or sorted(db_trips) != [(trip, "loading") for trip in trip_ids]
        ):
            return (
                "FAIL",
                "PostgreSQL order or trip state disagrees with the LOADED milestones",
            )
    except (AttributeError, KeyError, TypeError, ValueError):
        return "FAIL", "Invalid or incomplete PostgreSQL warehouse state"
    return "PASS", "Browser reload and PostgreSQL confirm every trip loaded"


def _driver_evidence(cases: tuple[dict, dict]) -> tuple[str, int, list[dict], bool]:
    details = []
    postgres_failure = False
    confirmed = 0
    for trips, case in enumerate(cases, start=1):
        continuation = case.get("t27") or {}
        stages = continuation.get("driver", [])
        dispatches = []
        seen: set[int] = set()
        for stage in stages:
            outcome = _status(stage.get("status"))
            dispatch = _status(stage.get("dispatch_status"))
            trip_id = stage.get("trip_id")
            trip_valid = (
                type(trip_id) is int and 1 <= trip_id <= trips and trip_id not in seen
            )
            if not trip_valid:
                outcome = "FAIL"
            else:
                seen.add(trip_id)
            if dispatch == "PASS":
                event_id = stage.get("event_id")
                if type(event_id) is int and event_id > 0 and trip_valid:
                    dispatches.append((event_id, trip_id))
                else:
                    dispatch = "FAIL"
            details.append(
                {
                    "fixture": _fixture(trips),
                    "trip_id": trip_id,
                    "status": outcome,
                    "dispatch_status": dispatch,
                    "responses": stage.get("http", []),
                    "last_verified": stage.get("last_verified"),
                    "reason": stage.get("reason"),
                }
            )
        persisted = continuation.get("persisted_dispatch")
        db_verified = continuation.get("postgres_dispatch_matches_browser")
        postgres_failure |= db_verified is False
        if persisted is not None:
            match = sorted(dispatches) == sorted(
                (row.get("id"), row.get("trip_id")) for row in persisted
            )
            postgres_failure |= not match
            if match and db_verified is True:
                confirmed += len(dispatches)
    statuses = {
        stage[field] for stage in details for field in ("status", "dispatch_status")
    }
    # A dependency on one trip must not conceal an unexpected failure on another.
    status = (
        "FAIL"
        if postgres_failure or "FAIL" in statuses
        else "BLOCKED" if "BLOCKED" in statuses else NOT_VERIFIED
    )
    return status, confirmed, details, postgres_failure


def _cs_evidence(cases: tuple[dict, dict]) -> tuple[str, list[dict]]:
    cases_evidence = []
    for trips, case in enumerate(cases, start=1):
        stage = (case.get("t27") or {}).get("cs") or {}
        status = _status(stage.get("status"))
        lookup = _status(stage.get("order_lookup"))
        if status == "FAIL" and lookup == NOT_VERIFIED:
            lookup = "FAIL"
        eta = (
            status
            if lookup == "PASS" and status in {"FAIL", "BLOCKED"}
            else NOT_VERIFIED
        )
        cases_evidence.append(
            {
                "fixture": _fixture(trips),
                "order_id": stage.get("order_id"),
                "order_lookup": lookup,
                "eta_history_status": eta,
                "eta_history": stage.get("eta_history"),
                "responses": stage.get("http", []),
                "reason": stage.get("reason"),
            }
        )
    statuses = {
        stage[field]
        for stage in cases_evidence
        for field in ("order_lookup", "eta_history_status")
    }
    status = (
        "FAIL"
        if "FAIL" in statuses
        else (
            "BLOCKED"
            if "BLOCKED" in statuses and NOT_VERIFIED not in statuses
            else NOT_VERIFIED
        )
    )
    return status, cases_evidence


def summarize(one: dict, two: dict, sha: str) -> dict:
    cases = (one, two)
    warehouse = [_warehouse(trips, case) for trips, case in enumerate(cases, start=1)]
    warehouse_status = (
        "FAIL"
        if any(status == "FAIL" for status, _ in warehouse)
        else (
            "PASS" if all(status == "PASS" for status, _ in warehouse) else NOT_VERIFIED
        )
    )
    warehouse_details = ". ".join(
        f"{_fixture(trips)} {status} ({reason})"
        for trips, (status, reason) in enumerate(warehouse, start=1)
    )
    app_now = {case.get("app_now") for case in cases}
    zone = {case.get("market_timezone") for case in cases}
    if warehouse_status == "PASS" and (
        len(app_now) != 1 or None in app_now or len(zone) != 1 or None in zone
    ):
        warehouse_status = "FAIL"
        warehouse_details += ". Fixture clocks/time zones are missing or inconsistent"

    driver_status, confirmed_dispatches, drivers, dispatch_mismatch = _driver_evidence(
        cases
    )
    cs_status, cs_cases = _cs_evidence(cases)
    lookup = all(case["order_lookup"] == "PASS" for case in cs_cases)

    rows = []
    for num, title, tasks in STEPS:
        row = {
            "step": num,
            "title": title,
            "tasks": tasks,
            "status": NOT_VERIFIED,
            "evidence": "Not exercised by these APPROVED-only fixtures",
        }
        if num == "7":
            row["status"] = warehouse_status
            row["evidence"] = warehouse_details
        elif num == "8":
            row["status"] = driver_status
            trip_details = ". ".join(
                _with_reason(
                    f"{trip['fixture']} trip {trip['trip_id']} {trip['status']}",
                    trip["reason"],
                )
                for trip in drivers
            )
            row["evidence"] = (
                f"Driver UI DISPATCHED matched PostgreSQL for {confirmed_dispatches}/3 trips. "
                f"Manual GPS update and POD remain unverified. {trip_details}"
                if drivers
                else "Driver browser continuation has not run"
            )
            if dispatch_mismatch:
                row[
                    "evidence"
                ] += " PostgreSQL dispatch state disagrees with browser evidence."
            row["http"] = drivers
        elif num == "11":
            row["status"] = cs_status
            row["evidence"] = ". ".join(
                _with_reason(
                    f"{case['fixture']} order lookup {case['order_lookup']}, "
                    f"ETA history {case['eta_history_status']}",
                    case["reason"] or case["eta_history"],
                )
                for case in cs_cases
            )
            row["http"] = cs_cases
        rows.append(row)

    assert len(rows) == 14 and {r["step"] for r in rows} == {s[0] for s in STEPS}
    assert all(row["status"] in VALID for row in rows)
    return {
        "schema": "t27-round3-ledger-v1",
        "source_sha": sha,
        "generated_utc": datetime.now(UTC).isoformat(),
        "origin": "APPROVED synthetic E3 fixture, not POS/Sales/Approve",
        "fixtures": ["SE-E3-1T", "SE-E3-2T"],
        "app_now": next(iter(app_now)) if len(app_now) == 1 else None,
        "market_timezone": next(iter(zone)) if len(zone) == 1 else None,
        "result_counts": {
            status: sum(r["status"] == status for r in rows) for status in sorted(VALID)
        },
        "driver_dispatch_postgres_match": confirmed_dispatches == 3,
        "cs_lookup_api_match": lookup,
        "last_verified": [
            (case.get("t27") or {}).get(
                "last_verified",
                "E3 Warehouse LOADED" if status == "PASS" else "No verified milestone",
            )
            for case, (status, _) in zip(cases, warehouse, strict=True)
        ],
        "rows": rows,
    }


def markdown(ledger: dict) -> str:
    lines = [
        "# T27 Round 3 evidence ledger",
        "",
        f"Commit: {ledger['source_sha']}",
        f"Fixture origin: {ledger['origin']}",
        f"APP_NOW: {ledger['app_now']} / Europe/Stockholm: {ledger['market_timezone']}",
        "",
        "| Step | Scenario | Status | Evidence / blocker | Task |",
        "|---|---|---|---|---|",
    ]
    for r in ledger["rows"]:
        lines.append(
            f"| {r['step']} | {r['title']} | **{r['status']}** | "
            f"{str(r['evidence']).replace('|', '/')} | {r['tasks']} |"
        )
    lines += [
        "",
        "## Reproduce (disposable PostgreSQL, real Chrome and browser UI)",
        "",
        "See backend/tests/e2e/README.md. From backend with TEST_DATABASE_URL on loopback:",
        "",
        "    python -m tests.e2e.prep_queue_browser --trips 1 --continue-driver-cs --output ../t27-flow-one",
        "    python -m tests.e2e.prep_queue_browser --trips 2 --continue-driver-cs --output ../t27-flow-two",
        (
            '    GITHUB_SHA="$(git rev-parse HEAD)" python ../tools/t27_report.py '
            "--one ../t27-flow-one/demo-prep-browser-results.json "
            "--two ../t27-flow-two/demo-prep-browser-results.json --out ../t27-evidence"
        ),
        "",
        (
            "The source JSON files contain sanitized HTTP status and error.code, plus "
            "milestone IDs and order and trip states checked against disposable PostgreSQL."
        ),
        "",
        "## T28 integration handoff",
        "",
        (
            "These synthetic warehouse fixtures start APPROVED on November 10. For E0-04 "
            "(#222), keep SE-2026-000249 on APP_NOW=2026-12-01T10:05:00+01:00 across Source, "
            "CFO and Chrome. Start before Sales Sync and trace the same order from Source "
            "submission through DELIVERED after E1 (#224) and the remaining Driver and ETA "
            "dependencies integrate. Use separate orders for untouched Plan Review, revenue/T26 "
            "and FAILED exception evidence."
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--one", type=Path, required=True)
    parser.add_argument("--two", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(
        load(args.one),
        load(args.two),
        sha=os.getenv("GITHUB_SHA", "NOT VERIFIED - local"),
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "round3-results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (args.out / "round3-results.md").write_text(markdown(result), encoding="utf-8")
    print("T27 report: 14 rows", result["result_counts"])


if __name__ == "__main__":
    main()
