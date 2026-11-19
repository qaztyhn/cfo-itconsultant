"""Fail-closed 14-row T27 ledger derived only from real Playwright evidence."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

STEPS = (
    ("1", "POS create and submit", "E0"),
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


def load(path: Path) -> dict:
    if not path.exists():
        return {"result": "NOT VERIFIED", "reason": "Missing browser output"}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid T27 fixture JSON")
    return value


def summarize(one: dict, two: dict, sha: str) -> dict:
    cases = (one, two)
    errors = []
    for trips, case in ((1, one), (2, two)):
        if case.get("trip_count") != trips or case.get("order_no") != f"SE-E3-{trips}T":
            errors.append(f"{trips}-trip identity mismatch")
        elif case.get("result") != "PASS":
            errors.append(f"{trips}-trip browser not PASS")
        elif len(case.get("persisted_events", [])) != trips + 2:
            errors.append(f"{trips}-trip PostgreSQL milestone count incorrect")

    app_now = {case.get("app_now") for case in cases if case.get("app_now")}
    zone = {case.get("market_timezone") for case in cases if case.get("market_timezone")}
    if len(app_now) != 1 or len(zone) != 1:
        errors.append("Fixture clocks/time zones missing or inconsistent")
    e3 = not errors

    drivers = [s for case in cases for s in (case.get("t27") or {}).get("driver", [])]
    dispatches = [s for s in drivers if s.get("dispatch_status") == "PASS" and isinstance(s.get("event_id"), int)]
    matches = (
        len(drivers) == 3 and len(dispatches) == 3 and all(
            case.get("t27", {}).get("postgres_dispatch_matches_browser") for case in cases
        )
    )
    gps_blocked = any(s.get("status") == "BLOCKED" and "T16" in s.get("tasks", []) for s in drivers)
    cs = [(case.get("t27") or {}).get("cs", {}) for case in cases]
    lookup = all(s.get("order_lookup") == "PASS" for s in cs)
    eta_blocked = any(s.get("status") == "BLOCKED" and "T14" in s.get("tasks", []) for s in cs)

    rows = []
    for num, title, tasks in STEPS:
        row = {"step": num, "title": title, "tasks": tasks, "status": "NOT VERIFIED",
               "evidence": "Not exercised by these APPROVED-only fixtures"}
        if num == "7":
            row["status"] = "PASS" if e3 else "NOT VERIFIED" if not all(
                case.get("result") == "PASS" for case in cases
            ) else "FAIL"
            row["evidence"] = (
                "Real Chrome warehouse UI: 1-trip and 2-trip; two-trip first LOADED kept "
                "GOODS_READY; second LOADED gave LOADED; SQL event IDs, trip IDs and times matched."
                if e3 else "; ".join(errors)
            )
        elif num == "8":
            row["status"] = "BLOCKED" if gps_blocked else "FAIL" if drivers and not matches else "NOT VERIFIED"
            row["evidence"] = (
                f"Driver UI DISPATCHED persisted {len(dispatches)}/3 trip events; "
                f"PostgreSQL match={matches}. GPS manual update/POD remains unverified. "
                "Never infer Round 3 compliant DELIVERED from older UI."
                if drivers else "Driver browser continuation has not run"
            )
            row["http"] = [
                {"trip_id": s.get("trip_id"), "responses": s.get("http", []), "last_verified": s.get("last_verified")}
                for s in drivers
            ]
        elif num == "11":
            row["status"] = "BLOCKED" if lookup and eta_blocked else "FAIL" if cs and not lookup else "NOT VERIFIED"
            row["evidence"] = (
                "CS UI lookup and detail matched the same order/API. ETA history GET unavailable (T14)."
                if lookup and eta_blocked else "CS lookup or ETA history not verified"
            )
            row["http"] = [{"order_id": s.get("order_id"), "responses": s.get("http", [])} for s in cs]
        elif num in {"3", "4", "5", "9", "10", "12b", "13"}:
            row["status"] = "BLOCKED"
            row["evidence"] = "Task/fixture dependency not integrated; no complete live UI/API/DB proof"
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
        "result_counts": {status: sum(r["status"] == status for r in rows) for status in sorted(VALID)},
        "driver_dispatch_postgres_match": matches,
        "cs_lookup_api_match": lookup,
        "last_verified": [
            (case.get("t27") or {}).get("last_verified", "E3 Warehouse LOADED") for case in cases
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
        "    python ../tools/t27_report.py --one ../t27-flow-one/demo-prep-browser-results.json "
        "--two ../t27-flow-two/demo-prep-browser-results.json --out ../t27-evidence",
        "",
        "The source JSON files contain per-step sanitized HTTP status and error.code, plus "
        "warehouse and dispatched milestone IDs matched with disposable PostgreSQL.",
        "No JWT, recipient email, raw GPS coordinates or private credentials are included "
        "in this shared ledger.",
        "",
        "## T28 integration handoff",
        "",
        "The above fixtures begin APPROVED, not POS or Sales. For the main candidate "
        "SE-2026-000249 align Source/CFO/browser APP_NOW, Europe/Stockholm business date "
        "and staffing. E0-04 preparation already runs Sync and Plan, so begin with a "
        "pre-Sync order for true Sales UI acceptance. Run separate order references for "
        "an untouched Plan Review, a revenue/T26 case and a FAILED exception case.",
        "Re-run blocked/unverified steps once E1, E2, T13/T14/T16, T19 and T26 integrate; "
        "T27 itself is not closed on partial fixture evidence.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--one", type=Path, required=True)
    parser.add_argument("--two", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(load(args.one), load(args.two), sha=os.getenv("GITHUB_SHA", "NOT VERIFIED - local"))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "round3-results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (args.out / "round3-results.md").write_text(markdown(result), encoding="utf-8")
    print("T27 report: 14 rows", result["result_counts"])


if __name__ == "__main__":
    main()
