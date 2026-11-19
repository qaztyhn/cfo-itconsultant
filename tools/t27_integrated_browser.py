"""T27 E0-04 real Chrome → E1 loopback WMS → E2 Mailpit → E3 → Driver → CS.

Starts with the Source order submitted but ABSENT from CFO. No TestClient performs
Sync, Plan or Approve. Existing E0-04 --stop-before-sync builds only inputs.
Runs exclusively against cfo-demo-e004; never touches production resources.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from playwright.sync_api import Error, Page, Response, expect, sync_playwright

REF = "SE-2026-000249"
NOW = "2026-12-01T10:05:00+01:00"
ZONE = "Europe/Stockholm"
API = "http://localhost:8000"
WEB = "http://localhost:5173"
MAILPIT = "http://127.0.0.1:8025"
ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", str(ROOT / ".env"), "-p", "cfo-demo-e004"]
STEPS = (
    ("1", "POS submit", "E0"),
    ("2", "Sales Sync and feasibility", "E0, E1"),
    ("3", "Sales rank alternatives", "T19, T26"),
    ("4", "Dispatcher Approve + WMS", "E1, T12, T15"),
    ("5", "CONFIRMED -> Mailpit", "E2, T21"),
    ("6", "Dispatcher Plan Review", "E4"),
    ("7", "Warehouse prep and loading", "E3, T05"),
    ("8", "Driver dispatch, GPS and POD", "T06, T12, T13, T14, T16"),
    ("9", "Dispatcher tracking and DELAY send", "T08, T17, E5"),
    ("10", "Lifecycle email", "E2, T21"),
    ("11", "CS lookup + ETA history", "T03, T14"),
    ("12", "Five KPIs", "T22"),
    ("12b", "Orders and revenue", "T26, T29, T30"),
    ("13", "FAILED exception", "T07, T18, T26"),
)


def stage_report() -> dict:
    return {
        "revision": os.getenv("GITHUB_SHA", "NOT VERIFIED (local commit)"),
        "app_now": NOW,
        "market_timezone": ZONE,
        "order_reference": REF,
        "origin": "Source SUBMITTED; CFO record ABSENT, pre-Sync fixture",
        "result": "PARTIAL",
        "last_verified": "Source pre-Sync fixture",
        "steps": [
            {"step": n, "scenario": title, "status": "NOT VERIFIED",
             "task": dep, "evidence": "Not tested in this browser run"}
            for n, title, dep in STEPS
        ],
        "api": [],
        "milestones": [],
    }


def mark(report: dict, number: str, status: str, evidence: str, **details: object) -> None:
    assert status in {"PASS", "FAIL", "BLOCKED", "NOT VERIFIED"}
    item = next(row for row in report["steps"] if row["step"] == number)
    item.update({"status": status, "evidence": evidence, **details})


def metadata(response: Response) -> dict[str, object]:
    code = None
    if not response.ok:
        try:
            error = response.json().get("error")
            if isinstance(error, dict) and isinstance(error.get("code"), str):
                code = error["code"]
        except (ValueError, AttributeError, Error):
            pass
    return {"path": urlsplit(response.url).path, "http": response.status, "error_code": code}


def body(response: Response, report: dict) -> dict:
    info = metadata(response)
    report["api"].append(info)
    if not response.ok:
        raise RuntimeError(f"HTTP {info['http']} / {info['path']} code {info['error_code']}")
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("Expected object from application API")
    return value


def cmd(*args: str, env: dict[str, str], capture: bool = False) -> str:
    result = subprocess.run(
        list(args), cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        check=False, timeout=150,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Disposable preparation command failed: {args[0]} {args[1] if len(args)>1 else ''}")
    return result.stdout.strip() if capture else ""


def compose(*args: str, env: dict[str, str], capture: bool = False) -> str:
    return cmd(*COMPOSE, *args, env=env, capture=capture)


def sql(query: str, env: dict[str, str]) -> str:
    # Read-only SQL for exact synthetic IDs/status; never select recipients, tokens or coordinates.
    return compose("exec", "-T", "postgres", "psql", "-U", "cfo", "-d", "cfo",
                   "-v", "ON_ERROR_STOP=1", "-Atc", query, env=env, capture=True)


def screenshot(page: Page, out: Path, name: str) -> None:
    page.screenshot(path=out / name, full_page=True, animations="disabled")


def login(browser, target: str, account: str, password: str, out: Path, label: str) -> Page:
    page = browser.new_page(timezone_id=ZONE, viewport={"width": 1440, "height": 950},
                            service_workers="block")
    page.set_default_timeout(15_000)
    page.clock.install(time=datetime.fromisoformat(NOW))
    page.goto(WEB + "/login")
    page.locator('input[type="email"]').fill(account)
    page.get_by_label("Password", exact=True).fill(password)
    with page.expect_response(lambda r: r.request.method == "POST" and
                              urlsplit(r.url).path == "/api/v1/auth/login") as sent:
        page.get_by_role("button", name="Sign in", exact=True).click()
    if not sent.value.ok:
        raise RuntimeError(f"Synthetic {label} login rejected HTTP {sent.value.status}")
    page.goto(WEB + target)
    return page


def sales(browser, password: str, out: Path, report: dict, env: dict[str, str]) -> tuple[int, int, int]:
    page = login(browser, "/store/sync-check", "sales@cfo.demo", password, out, "Sales")
    try:
        expect(page.get_by_role("heading", name="Sync & confirm delivery")).to_be_visible()
        page.get_by_label("External POS order reference").fill(REF)
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == "/api/v1/integration/orders/sync-now") as sent:
            page.get_by_role("button", name="Sync & check routing").click()
        sync = body(sent.value, report)
        if sync.get("routing_status") != "cfo" or type(sync.get("order_id")) is not int:
            raise RuntimeError("Sales Sync did not produce authoritative CFO routing")
        order_id = sync["order_id"]
        report["last_verified"] = "Sales UI Sync now"
        screenshot(page, out, "01-sales-sync.png")
        # Route matrix preparation is explicitly SETUP (not a UI action).
        # Existing E0-04 planner needs this read-only offline fallback first.
        compose("exec", "-T", "-e", "DEMO_DISPOSABLE=1", "cfo-api", "python", "-m",
                "app.demo_e0_04_routes", "--order-id", str(order_id), env=env)
        report["setup_after_sync"] = "Offline fallback routes computed after UI Sync"
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == f"/api/v1/orders/{order_id}/plan",
                                  timeout=30000) as planned:
            page.get_by_role("button", name="Check feasibility").click()
        run = body(planned.value, report)
        plans = run.get("plans") or []
        if run.get("result") != "feasible" or len(plans) != 1:
            raise RuntimeError("E0-04 planner did not produce exactly one feasible proposed plan")
        run_id, plan_id = run["id"], plans[0]["id"]
        if sql(f"SELECT status FROM plan.fulfilment_plan WHERE id={plan_id}", env) != "proposed":
            raise RuntimeError("Plan was already approved during setup (not browser tested)")
        expect(page.get_by_role("heading", name="Feasible — not confirmed")).to_be_visible()
        screenshot(page, out, "02-feasible-proposed.png")
        report["run_id"], report["plan_id"], report["order_id"] = run_id, plan_id, order_id
        report["last_verified"] = "Sales UI Sync + Check feasibility; proposed plan"
        mark(report, "2", "PASS", "Both Sync and Check clicked through Chrome; two HTTP 200 responses; plan proposed",
             order_id=order_id, run_id=run_id, plan_id=plan_id)
        return order_id, run_id, plan_id
    finally:
        page.close()


def start_disposable_wms(env: dict[str, str], report: dict) -> None:
    # The existing E1 simulator is deliberately restricted to loopback.
    # Start it inside the cfo-api container's *same* network namespace rather
    # than weakening DisposableWmsPort to permit arbitrary remote hosts.
    fixture = ROOT / ".t27-wms-fixture.json"
    cmd(sys.executable, "tools/t27_prepare_wms_fixture.py", "--output", str(fixture), env=env)
    compose("cp", str(fixture), "cfo-api:/tmp/t27-wms-fixture.json", env=env)
    compose("exec", "-d", "-e", "SYNTHETIC_WMS_FIXTURE=/tmp/t27-wms-fixture.json",
            "-e", "SYNTHETIC_WMS_DB=/tmp/t27-wms.sqlite",
            "cfo-api", "python", "-m", "app.adapters.disposable_wms_service", env=env)
    for attempt in range(30):
        try:
            compose("exec", "-T", "cfo-api", "python", "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/openapi.json',timeout=2)",
                    env=env)
            report["wms_fixture"] = "E1 SQLite synthetic WMS, private loopback, ready"
            return
        except RuntimeError:
            time.sleep(0.3)
    raise RuntimeError("E1 loopback WMS did not start in disposable container")


def approve(browser, password: str, run_id: int, plan_id: int, order_id: int,
            out: Path, report: dict, env: dict[str, str]) -> list[int]:
    # E0-04's Dispatcher user is profile id=1 (also used in E1's
    # verified TestClient actor). Discover its demo login from the seeded
    # database; the T27 E3 fixture's user1@cfo.test is a DIFFERENT seed.
    account = sql(
        "SELECT email FROM ref.app_user WHERE id=1 AND 'dispatcher'=ANY(roles)", env
    )
    if not account:
        raise RuntimeError("E1 Dispatcher identity not found in disposable market seed")
    page = login(browser, f"/dispatcher/plan-review/{run_id}", account, password, out, "Dispatcher")
    try:
        expect(page.get_by_role("heading", name="Plan review")).to_be_visible()
        tight = page.get_by_role("checkbox", name="I accept the tight schedule")
        if tight.count():
            # The actual Dispatcher explicitly acknowledges a tight plan.
            # This is not an automatic approval or a bypass of backend recheck.
            tight.check()
        decision = page.get_by_role("region", name="Decision")
        action = decision.get_by_role("button", name="Approve #1")
        try:
            expect(action).to_be_enabled(timeout=10000)
        except AssertionError:
            # The decision-region text is a known safe generic UI reason;
            # never export the whole page/customer data or guess an API code.
            why = decision.locator("p").first.inner_text()[:300]
            screenshot(page, out, "03-dispatcher-disabled.png")
            mark(report, "4", "BLOCKED", "Dispatcher UI rejected Approve before POST",
                 ui_reason=why, http=None, task="E1, E4, T12")
            report["last_verified"] = "Sales Sync+Check; Dispatcher showed disabled Approve"
            return []
        screenshot(page, out, "03-dispatcher-proposed.png")
        action.click()
        dialog = page.get_by_role("dialog", name="Approve plan #1")
        expect(dialog).to_be_visible()
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == f"/api/v1/plans/{plan_id}/approve",
                                  timeout=40000) as confirmed:
            dialog.get_by_role("button", name="Approve #1", exact=True).click()
        response = confirmed.value
        info = metadata(response)
        report["api"].append(info)
        if not response.ok:
            mark(report, "4", "BLOCKED" if response.status in (409, 422, 503) else "FAIL",
                 "Dispatcher UI clicked Approve, backend rejected without a committed order",
                 http=info)
            report["last_verified"] = "Dispatcher Approve request rejected; Sales feasible is last PASS"
            return []
        result = response.json()
        if result.get("order", {}).get("status") != "APPROVED":
            raise RuntimeError("HTTP 200 without APPROVED is not approval")
        trip_ids = result.get("trip_ids")
        notifications = result.get("notifications")
        if not isinstance(trip_ids, list) or len(trip_ids) != 1 or not isinstance(notifications, list):
            raise RuntimeError("Missing committed trips or notification metadata")
        confirmed = [item for item in notifications if item.get("template") == "CONFIRMED"]
        if len(confirmed) != 1 or type(confirmed[0].get("id")) is not int:
            raise RuntimeError("CONFIRMED ID absent from actual Approve response")
        notify_id = confirmed[0]["id"]
        report["notification_id"] = notify_id
        report["trip_ids"] = trip_ids
        report["approve_http"] = 200
        # Real PostgreSQL ledger. The WMS ACK must be synthetic with verified
        # reflected batch provenance; otherwise no PASS.
        row = sql(
            "SELECT o.status||'|'||p.status||'|'||w.source_kind||'|'||"
            "i.reflected_in_batch_id||'|'||w.source_batch_id "
            "FROM ops.customer_order o JOIN plan.fulfilment_plan p ON p.id=o.approved_plan_id "
            "JOIN ops.wms_reservation_intent i ON i.order_id=o.id "
            "JOIN ops.stock_write_run w ON w.id=i.stock_write_run_id "
            f"WHERE o.id={order_id}", env,
        ).split("|")
        queued = sql(f"SELECT template||'|'||status FROM ops.notification WHERE id={notify_id}", env)
        trips_db = sql(
            "SELECT t.id FROM ops.delivery_trip t JOIN plan.plan_vehicle pv ON pv.id=t.plan_vehicle_id "
            f"WHERE pv.plan_id={plan_id} ORDER BY t.id", env,
        ).splitlines()
        if (row[:3] != ["APPROVED", "approved", "wms_synthetic"] or row[3] != row[4]
            or trips_db != [str(t) for t in trip_ids] or queued != "CONFIRMED|queued"):
            raise RuntimeError("Approve/SQL/WMS batch or notification IDs did not agree")
        mark(report, "4", "PASS", "Dispatcher UI Approve HTTP 200; PostgreSQL APPROVED, trip, synthetic WMS ACK reflected in signed batch",
             plan_id=plan_id, trip_ids=trip_ids, wms_source="wms_synthetic", reflected_batch=row[3])
        report["last_verified"] = "Dispatcher UI approved; WMS synthetic batch and queued CONFIRMED verified"
        screenshot(page, out, "04-dispatcher-approved.png")
        return trip_ids
    finally:
        page.close()


def mailpit_confirm(report: dict, env: dict[str, str]) -> None:
    notify_id = report.get("notification_id")
    if type(notify_id) is not int:
        return
    # Worker intentionally opts-in ONLY after the full seed+migrations.
    compose("--profile", "demo-worker", "up", "-d", "cfo-worker", env=env)
    report["worker_start"] = "After migrate and seed, opt-in demo-worker"
    deadline = time.monotonic() + 95
    while time.monotonic() < deadline:
        row = sql(
            f"SELECT status||'|'||attempts FROM ops.notification WHERE id={notify_id}", env
        )
        if row.startswith("sent|"):
            break
        if row.startswith("suppressed|") or row.startswith("failed|"):
            mark(report, "5", "BLOCKED", "Worker did not send queued CONFIRMED", notification_id=notify_id,
                 db_status=row)
            return
        time.sleep(2)
    else:
        mark(report, "5", "BLOCKED", "Worker timed out before CONFIRMED reached sent",
             notification_id=notify_id)
        return
    response = httpx.get(MAILPIT + "/api/v1/messages", timeout=8, trust_env=False)
    if response.status_code != 200:
        mark(report, "5", "BLOCKED", "Mailpit API did not respond with HTTP 200")
        return
    messages = response.json().get("messages") or response.json().get("Messages") or []
    matching = [msg for msg in messages if REF in str(msg.get("Subject", ""))]
    if len(matching) != 1:
        mark(report, "5", "FAIL", "Mailpit does not contain exactly one matching synthetic CONFIRMED",
             matching_count=len(matching), notification_id=notify_id)
        return
    # Validate customer-visible order reference + scheduled window without
    # persisting the message body, address, recipient or private email.
    message_id = matching[0].get("ID")
    detail = httpx.get(MAILPIT + f"/api/v1/message/{message_id}", timeout=8, trust_env=False)
    body_text = detail.text
    if detail.status_code != 200 or REF not in body_text or "2026-12-02" not in body_text:
        mark(report, "5", "FAIL", "Mailpit message missing expected order reference or window")
        return
    audit = sql(
        "SELECT count(*) FROM audit.decision_log WHERE action='NOTIFICATION_SENT' "
        f"AND order_id={report['order_id']}", env,
    )
    if audit != "1":
        mark(report, "5", "FAIL", "CONFIRMED had not exactly one committed NOTIFICATION_SENT audit")
        return
    mark(report, "5", "PASS", "Approve notification ID matched PostgreSQL queued→sent; worker, 1 audit, exactly 1 Mailpit message",
         notification_id=notify_id, mailpit_count=1, mailpit_http=200)
    report["last_verified"] = "CONFIRMED sent with matching ID and exactly one Mailpit email"


def warehouse(browser, password: str, order_id: int, trip_ids: list[int],
              out: Path, report: dict, env: dict[str, str]) -> bool:
    wh_id = int(sql(f"SELECT warehouse_id FROM ops.delivery_trip WHERE id={trip_ids[0]}", env))
    account = sql(
        "SELECT u.email FROM ref.app_user u JOIN hr.employee e ON e.id=u.employee_id "
        "WHERE e.employee_no='DEMO-STO-W00'", env,
    )
    page = login(browser, "/warehouse/prep", account, password, out, "Warehouse")
    try:
        row = page.locator("tbody tr").filter(has_text=REF)
        expect(row).to_be_visible(timeout=15000)
        report["warehouse_id"] = wh_id
        results = []
        actions = [("START_PREP", "Start preparation", {}), ("GOODS_READY", "Goods ready", {}),
                   *[("LOADED", "Mark loaded", {"trip_id": trip}) for trip in trip_ids]]
        for index, (kind, label, extra) in enumerate(actions, start=1):
            button_name = label if kind != "LOADED" else None
            if button_name:
                row.get_by_role("button", name=button_name, exact=True).click()
            else:
                # Only one vehicle in E0-04. Use exact assigned trip ID and
                # rendered vehicle code, never a guessed index.
                row.get_by_role("button", name=__import__("re").compile("^Mark loaded")).click()
            dialog = page.get_by_role("dialog", name=f"Confirm {label}")
            dialog.get_by_label("Occurred at (device local time)").fill("2026-12-01T10:05:00")
            if kind == "START_PREP":
                dialog.get_by_label("Crew size (people actually working)").fill("3")
            with page.expect_response(lambda r: r.request.method == "POST" and
                                      urlsplit(r.url).path == f"/api/v1/orders/{order_id}/events") as posted:
                dialog.get_by_role("button", name=f"Confirm {label}", exact=True).click()
            info = metadata(posted.value)
            report["api"].append(info)
            if not posted.value.ok:
                mark(report, "7", "BLOCKED" if posted.value.status in (409, 422) else "FAIL",
                     f"Warehouse UI {kind} was rejected; previous committed milestone is last verified",
                     last_action=kind, http=info)
                return False
            ack = posted.value.json()
            if ack.get("order_status") not in ("PREPARING", "GOODS_READY", "LOADED"):
                raise RuntimeError("Warehouse event success without valid authoritative status")
            ev_id = ack.get("event_id")
            if type(ev_id) is not int:
                raise RuntimeError("Warehouse event did not return event_id")
            result = {"event_type": kind, "event_id": ev_id, "trip_id": extra.get("trip_id"),
                      "order_status": ack["order_status"], "http": info}
            results.append(result)
            report["milestones"].append(result)
            screenshot(page, out, f"0{4+index}-{kind.lower()}.png")
            if kind == "LOADED":
                expect(row.locator('[data-label="Status"]')).to_have_text("LOADED", timeout=12000)
        ids = ",".join(str(entry["event_id"]) for entry in results)
        persisted = sql(
            "SELECT id||'|'||event_type||'|'||coalesce(trip_id::text,'-') "
            f"FROM ops.milestone_event WHERE order_id={order_id} AND id IN ({ids}) ORDER BY id", env
        ).splitlines()
        expected = [
            f"{entry['event_id']}|{entry['event_type']}|{entry['trip_id'] if entry['trip_id'] else '-'}"
            for entry in results
        ]
        if persisted != expected or sql(f"SELECT status FROM ops.customer_order WHERE id={order_id}", env) != "LOADED":
            raise RuntimeError("Warehouse UI/SQL milestone/trip mismatch")
        mark(report, "7", "PASS", "Same approved order: warehouse UI START_PREP → GOODS_READY → LOADED, IDs/trip IDs verified in PostgreSQL",
             events=results)
        report["last_verified"] = "Warehouse UI LOADED and matching PostgreSQL events"
        return True
    finally:
        page.close()


def driver(browser, password: str, trip_id: int, order_id: int,
           out: Path, report: dict, env: dict[str, str]) -> None:
    account = sql(
        "SELECT u.email FROM ref.app_user u JOIN ops.delivery_trip t ON t.driver_employee_id=u.employee_id "
        f"WHERE t.id={trip_id}", env
    )
    page = login(browser, "/driver", account, password, out, "Driver")
    try:
        card = page.get_by_role("article").filter(has_text=f"Trip {trip_id}")
        expect(card).to_be_visible(timeout=16000)
        card.get_by_role("button", name="Review and dispatch").click()
        screenshot(page, out, "08-driver-dispatch-ready.png")
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == f"/api/v1/orders/{order_id}/events") as posted:
            page.get_by_role("button", name="Mark dispatched").click()
        info = metadata(posted.value)
        report["api"].append(info)
        if not posted.value.ok:
            from tests.e2e.t27_http_evidence import dispatch_rejection
            try:
                error = posted.value.json().get("error", {})
                code = error.get("code")
                msg = error.get("message")
            except (ValueError, AttributeError, Error):
                code, msg = None, None
            classified = dispatch_rejection(posted.value.status, code, msg)
            mark(report, "8", classified["status"], classified["reason"],
                 task=", ".join(classified["tasks"]), http=info, trip_id=trip_id)
            report["last_verified"] = "Assigned Driver UI trip visible; DISPATCHED rejected"
            return
        ack = posted.value.json()
        if ack.get("order_status") != "DISPATCHED" or type(ack.get("event_id")) is not int:
            raise RuntimeError("Driver DISPATCHED HTTP200 without state/event")
        db = sql(
            "SELECT event_type||'|'||trip_id||'|'||o.status FROM ops.milestone_event e "
            "JOIN ops.customer_order o ON o.id=e.order_id "
            f"WHERE e.id={ack['event_id']} AND e.order_id={order_id}", env)
        if db != f"DISPATCHED|{trip_id}|DISPATCHED":
            raise RuntimeError("Driver ACK/milestone/DB status mismatched")
        report["last_verified"] = "Driver UI DISPATCHED committed"
        mark(report, "8", "BLOCKED", "DISPATCHED PASS via UI + PG; Round 3 manual GPS/POD remains unverified",
             last_verified="DISPATCHED", http=info, event_id=ack["event_id"])
        screenshot(page, out, "09-driver-dispatched.png")
        # Never press legacy no-location DELIVERED and claim R3 mandatory GPS.
    finally:
        page.close()


def cs(browser, password: str, order_id: int, out: Path, report: dict, env: dict[str, str]) -> None:
    account = sql(
        "SELECT u.email FROM ref.app_user u JOIN hr.employee e ON e.id=u.employee_id "
        "WHERE 'customer_service'=ANY(u.roles) AND e.market_id=1 ORDER BY u.id LIMIT 1", env,
    )
    if not account:
        mark(report, "11", "BLOCKED", "No authorized market-scoped CS fixture account", task="T03")
        return
    page = login(browser, "/cs/orders", account, password, out, "CS")
    try:
        page.get_by_role("searchbox", name="Search orders").fill(REF)
        with page.expect_response(lambda r: r.request.method == "GET" and
                                  urlsplit(r.url).path == "/api/v1/orders" and
                                  "q=" in urlsplit(r.url).query) as listed:
            page.get_by_role("button", name="Search", exact=True).click()
        data = body(listed.value, report)
        if len([item for item in data.get("items", []) if item.get("order_no") == REF]) != 1:
            mark(report, "11", "BLOCKED", "CS can search but the same order not in permitted scope",
                 http=metadata(listed.value), task="T03")
            return
        with page.expect_response(lambda r: r.request.method == "GET" and
                                  urlsplit(r.url).path == f"/api/v1/orders/{order_id}") as got:
            page.get_by_role("button", name=__import__("re").compile(REF)).click()
        detail = body(got.value, report)
        if detail.get("order_no") != REF:
            raise RuntimeError("CS order reference mismatch")
        expect(page.get_by_label("Order details").get_by_text(REF, exact=True)).to_be_visible()
        screenshot(page, out, "10-cs-order-lookup.png")
        report["cs_lookup"] = {"status": "PASS", "order_id": order_id,
                               "http": metadata(got.value), "status_from_api": detail.get("status")}
        report["last_verified"] = "CS UI looked up same order; detail matches API"
        # Separate API contract, distinct from the CS order projection.
        # HTTP500 is a failure unless correlated backend logs prove a known T14 stub.
        token = page.evaluate("localStorage.getItem('cfo_token')")
        if not isinstance(token, str) or not token:
            raise RuntimeError("CS authenticated browser session did not expose a token")
        # Same authorized CS session, but this is a separate API probe, NOT a
        # customer-visible UI action or a test of history rendering.
        try:
            probe = page.request.get(API + f"/api/v1/orders/{order_id}/eta-forecasts",
                                     headers={"Authorization": "Bearer " + token}, timeout=10_000)
        except Error:
            report["eta_history"] = {"http": None, "error_code": None, "transport_error": True}
        else:
            code = None
            if not probe.ok:
                try:
                    code = probe.json().get("error", {}).get("code")
                except (ValueError, AttributeError, Error):
                    pass
            report["eta_history"] = {"http": probe.status, "error_code": code,
                                     "status": "NOT VERIFIED" if probe.ok else "BLOCKED"}
        mark(report, "11", "BLOCKED", "CS UI lookup/detail matched same order; ETA history separately probed using CS auth",
             cs_lookup="PASS", eta_history=report["eta_history"], task="T14")
    finally:
        page.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env = dict(os.environ)
    data = dotenv_values(ROOT / ".env")
    if (env.get("APP_ENV"), env.get("DEMO_DISPOSABLE"), env.get("APP_NOW"),
        env.get("COMPOSE_PROJECT_NAME")) != ("test", "1", NOW, "cfo-demo-e004"):
        parser.error("Disposable E0-04 environment and fixed clock required")
    if not str(env.get("COMPOSE_FILE", "")).endswith("tools/t27_e1_compose.override.yml"):
        parser.error("Missing isolated E1 loopback Compose override")
    password = data.get("SEED_DEMO_PASSWORD")
    if not isinstance(password, str) or not password:
        parser.error("Private .env demo password required")
    args.output.mkdir(parents=True, exist_ok=False)
    report = stage_report()
    try:
        if sql(f"SELECT count(*) FROM ops.customer_order WHERE external_ref='{REF}'", env) != "0":
            raise RuntimeError("Pre-Sync fixture invalid: CFO order already present")
        report["start_verified"] = "Source-only pre-Sync (CFO count=0)"
        mark(report, "1", "NOT VERIFIED", "Source order pre-seeded; POS creation UI not exercised")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome")
            try:
                report["active_step"] = "2"
                order_id, run_id, plan_id = sales(browser, password, args.output, report, env)
                report["active_step"] = "4"
                start_disposable_wms(env, report)
                trip_ids = approve(browser, password, run_id, plan_id, order_id, args.output, report, env)
                if trip_ids:
                    report["active_step"] = "5"
                    mailpit_confirm(report, env)
                    report["active_step"] = "7"
                    if warehouse(browser, password, order_id, trip_ids, args.output, report, env):
                        report["active_step"] = "8"
                        driver(browser, password, trip_ids[0], order_id, args.output, report, env)
                    report["active_step"] = "11"
                    cs(browser, password, order_id, args.output, report, env)
                else:
                    # Same order may still be available for CS even when approval
                    # was blocked; do not attempt unauthorized warehouse actions.
                    report["active_step"] = "11"
                    cs(browser, password, order_id, args.output, report, env)
            finally:
                browser.close()
        report["result"] = "PASS_WITH_BLOCKERS" if not any(
            row["status"] == "FAIL" for row in report["steps"]
        ) else "FAIL"
    except Exception as exc:
        report["result"] = "FAIL"
        report["failure_type"] = type(exc).__name__
        report["failure_stage"] = report["last_verified"]
        active = report.get("active_step")
        if active:
            prior = next(row for row in report["steps"] if row["step"] == active)
            if prior["status"] == "NOT VERIFIED":
                mark(report, active, "FAIL",
                     "Unexpected browser/setup failure; inspect safe HTTP log and workflow logs",
                     exception_type=type(exc).__name__)
        # Do not serialize raw exception text; may embed database IDs or headers.
        raise
    finally:
        # Preserve blocked substeps as not completed. T30 and E5 are separate
        # fixture runs, not evidence of success on SE-2026-000249.
        mark(report, "3", "BLOCKED", "One E0-04 proposal, not three ranked choices; T19/T26", task="T19, T26")
        mark(report, "9", "BLOCKED", "Requires separate E5 DELAY draft/worker plus T08/T17", task="E5, T08, T17")
        mark(report, "10", "BLOCKED", "Lifecycle DISPATCHED/DELIVERED/DELAY not checked on this order", task="E2, T21")
        mark(report, "12b", "NOT VERIFIED", "T30 T29 fixture separate; official T26 seed not yet replayed", task="T26, T30")
        (args.output / "t27-integrated.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        rows = ["# T27 integrated attempt — fixture SE-2026-000249",
                "", f"Commit: {report['revision']}", f"APP_NOW: {NOW} / {ZONE}",
                f"Origin: {report['origin']}", f"Last verified: {report['last_verified']}",
                "", "| Step | Status | Evidence | Task |", "|---|---|---|---|"]
        for item in report["steps"]:
            rows.append(f"| {item['step']} | {item['status']} | {item['evidence'].replace('|','/')} | {item['task']} |")
        (args.output / "t27-integrated.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
        print("T27 result", report["result"], "| last verified", report["last_verified"])
        print("T27 statuses", json.dumps({s: sum(item["status"] == s for item in report["steps"])
            for s in ("PASS", "FAIL", "BLOCKED", "NOT VERIFIED")}))
    return 0 if report["result"] == "PASS_WITH_BLOCKERS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
