"""T27 E0-04 real Chrome → E1 loopback WMS → E2 Mailpit → E3 → Driver → CS.

The full runner uses E0-04 --stop-before-sync, with Sync, Plan and Approve
performed in Chrome. Manual WMS preparation also supports an existing T26
proposal in the dedicated cfo-demo-t26 project.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from dotenv import dotenv_values
from playwright.sync_api import APIResponse, Error, Page, Response, expect, sync_playwright
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from tests.e2e.t27_http_evidence import dispatch_rejection, eta_history_status
from tools.t27_prepare_wms_fixture import E0_PROJECT, T26_PROJECT

SOURCE_REF = "SE-2026-000249"
NOW = "2026-12-01T10:05:00+01:00"
ZONE = "Europe/Stockholm"
API = "http://localhost:8000"
WEB = "http://localhost:5173"
MAILPIT = "http://127.0.0.1:8025"
ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", str(ROOT / ".env")]
STEPS = (
    ("1", "Open CFO Sales Sync & Check and enter Source reference", "E0, T26"),
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
        "external_ref": SOURCE_REF,
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


def metadata(response: Response | APIResponse) -> dict[str, object]:
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
    return cmd(*COMPOSE, "-p", env.get("COMPOSE_PROJECT_NAME", E0_PROJECT),
               *args, env=env, capture=capture)


def sql(query: str, env: dict[str, str]) -> str:
    # Read-only SQL for exact synthetic IDs/status; never select recipients, tokens or coordinates.
    return compose("exec", "-T", "postgres", "psql", "-U", "cfo", "-d", "cfo",
                   "-v", "ON_ERROR_STOP=1", "-Atc", query, env=env, capture=True)


def screenshot(page: Page, out: Path, name: str) -> None:
    # Synthetic demo sidebar displays account login addresses. Exclude the
    # navigation entirely from public evidence instead of exporting usernames.
    main = page.locator("main").first
    if main.count():
        main.screenshot(path=out / name, animations="disabled")
    else:
        page.screenshot(path=out / name, full_page=True, animations="disabled")


def login(browser, target: str, account: str, password: str, out: Path, label: str, *, app_now: str = NOW) -> Page:
    page = browser.new_page(timezone_id=ZONE, viewport={"width": 1440, "height": 950},
                            service_workers="block")
    page.set_default_timeout(15_000)
    page.clock.install(time=datetime.fromisoformat(app_now))
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
        external_ref = page.get_by_label("External POS order reference")
        external_ref.fill(SOURCE_REF)
        expect(external_ref).to_have_value(SOURCE_REF)
        mark(
            report, "1", "PASS",
            "Chrome opened CFO Sales Sync & Check and entered/verified the Source "
            "reference. POS submission was separate pre-run fixture setup.",
            source_ref=SOURCE_REF, origin="Source pre-SUBMITTED fixture",
        )
        report["last_verified"] = "Sales entered the Source reference in CFO Sync & Check"
        screenshot(page, out, "01-sales-reference.png")
        report["active_step"] = "2"
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == "/api/v1/integration/orders/sync-now") as sent:
            page.get_by_role("button", name="Sync & check routing").click()
        sync = body(sent.value, report)
        if sync.get("routing_status") != "cfo" or type(sync.get("order_id")) is not int:
            raise RuntimeError("Sales Sync did not produce authoritative CFO routing")
        order_id = sync["order_id"]
        order_no = sql(
            f"SELECT order_no FROM ops.customer_order WHERE id={order_id} AND external_ref='{SOURCE_REF}'", env
        )
        if not order_no:
            raise RuntimeError("Synced order ID did not resolve to a CFO order number for the Source reference")
        report.update(order_id=order_id, order_no=order_no)
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
        report.update(run_id=run_id, plan_id=plan_id)
        report["last_verified"] = "Sales UI Sync + Check feasibility; proposed plan"
        mark(report, "2", "PASS", "Both Sync and Check clicked through Chrome; two HTTP 200 responses; plan proposed",
             order_id=order_id, run_id=run_id, plan_id=plan_id)
        return order_id, run_id, plan_id
    finally:
        page.close()


def install_disposable_wms(env: dict[str, str], fixture: Path) -> None:
    # The existing E1 simulator is deliberately restricted to loopback.
    # Start it inside the cfo-api container's *same* network namespace rather
    # than weakening DisposableWmsPort to permit arbitrary remote hosts.
    compose("exec", "-T", "cfo-api", "python", "-c",
            "import os; assert os.environ.get('WMS_RESERVATION_MODE') == 'simulated'", env=env)
    compose("cp", str(fixture), "cfo-api:/tmp/t27-wms-fixture.json", env=env)
    compose("exec", "-d", "-e", "SYNTHETIC_WMS_FIXTURE=/tmp/t27-wms-fixture.json",
            "-e", "SYNTHETIC_WMS_DB=/tmp/t27-wms.sqlite",
            "cfo-api", "python", "-m", "app.adapters.disposable_wms_service", env=env)
    for _ in range(30):
        try:
            compose("exec", "-T", "cfo-api", "python", "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/openapi.json',timeout=2)",
                    env=env)
            return
        except RuntimeError:
            time.sleep(0.3)
    raise RuntimeError("E1 loopback WMS did not start in disposable container")


def start_disposable_wms(env: dict[str, str], report: dict) -> None:
    with TemporaryDirectory(prefix="t27-wms-") as directory:
        fixture = Path(directory) / "fixture.json"
        report["wms_plan"] = cmd(
            sys.executable, "tools/t27_prepare_wms_fixture.py", "--output", str(fixture),
            env=env, capture=True,
        )
        install_disposable_wms(env, fixture)
    report["wms_fixture"] = "E1 SQLite synthetic WMS, private loopback, ready"


def prepare_t26_wms(env: dict[str, str], source_ref: str, plan_id: int, rank: int) -> None:
    # Validate the existing stack and plan before recreating its API container.
    compose(
        "exec", "-T", "cfo-api", "python", "-c",
        "import os; assert [os.environ.get(k) for k in ('APP_ENV','DEMO_DISPOSABLE','APP_NOW')]"
        f" == ['test','1',{NOW!r}]",
        env=env,
    )
    endpoint = compose("port", "postgres", "5432", env=env, capture=True)
    host, _, port = endpoint.rpartition(":")
    if host != "127.0.0.1" or not port.isdecimal():
        raise RuntimeError("T26 PostgreSQL must have a local loopback port")
    env["POSTGRES_PORT"] = port
    with TemporaryDirectory(prefix="t26-wms-") as directory:
        fixture = Path(directory) / "fixture.json"
        result = cmd(
            sys.executable, "tools/t27_prepare_wms_fixture.py", "--output", str(fixture),
            "--project", T26_PROJECT, "--source-ref", source_ref, "--plan-id", str(plan_id),
            "--rank", str(rank), env=env, capture=True,
        )
        # Use the running project's application build (which must include T19)
        # and leave the browser, PostgreSQL and Source containers in place.
        compose(
            "up", "-d", "--no-deps", "--no-build", "--force-recreate", "--wait",
            "--wait-timeout", "90", "cfo-api", env=env,
        )
        install_disposable_wms(env, fixture)
    print(result)
    print(f"WMS simulator ready at cfo-api loopback. Approve existing rank {rank}, plan #{plan_id}.")


def prepare_manual_wms(env: dict[str, str]) -> None:
    active = sql(
        "SELECT count(*) FROM ops.wms_reservation_intent i "
        "JOIN ops.customer_order o ON o.id=i.order_id "
        f"WHERE o.external_ref='{SOURCE_REF}' AND i.status NOT IN ('released','rejected')",
        env,
    )
    if active != "0":
        raise RuntimeError("This order already has an active WMS intent; use a fresh disposable demo")
    if sql(f"SELECT status FROM ops.customer_order WHERE external_ref='{SOURCE_REF}'", env) != "PLANNED":
        raise RuntimeError("Run Sales Sync & Check and leave the E0-04 order PLANNED before preparing WMS")
    # Recreate the API with the scoped override and refresh the UI from this checkout.
    # Only these two services are touched; the existing order and PostgreSQL stay in place.
    compose("up", "-d", "--build", "--no-deps", "--force-recreate", "--wait", "--wait-timeout", "90",
            "cfo-api", "cfo-web", env=env)
    report: dict[str, str] = {}
    start_disposable_wms(env, report)
    print(report["wms_plan"])
    print("WMS simulator ready. Reload CFO and approve this plan from the UI.")


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
        # PlanReview header mounts before its async planning-run detail.
        decision = page.get_by_role("region", name="Decision")
        action = decision.get_by_role("button", name="Approve #1")
        expect(action).to_be_visible(timeout=15000)
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
            try:
                error = response.json().get("error", {})
                reason = error.get("message")
            except (ValueError, AttributeError, Error):
                reason = None
            # DomainError contains static, server-owned reasons; never serialize
            # arbitrary request payloads, headers, native SKU, or recipients.
            public_reason = reason[:240] if isinstance(reason, str) else "No error detail"
            diagnostic = {
                "error_code": info["error_code"],
                "http": info["http"],
                "server_reason": public_reason,
                "order_status": sql(
                    f"SELECT status FROM ops.customer_order WHERE id={order_id}", env
                ),
                "wms_intent_count": sql(
                    f"SELECT count(*) FROM ops.wms_reservation_intent WHERE plan_id={plan_id}", env
                ),
                "wms_reserve_count": compose(
                    "exec", "-T", "cfo-api", "python", "-c",
                    "import sqlite3; db=sqlite3.connect('/tmp/t27-wms.sqlite'); "
                    "print(db.execute('SELECT count(*) FROM reservations').fetchone()[0])",
                    env=env, capture=True,
                ),
            }
            report["approval_diagnostic"] = diagnostic
            screenshot(page, out, "04-dispatcher-approval-rejected.png")
            mark(report, "4", "BLOCKED" if response.status in (409, 422, 503) else "FAIL",
                 "Dispatcher UI clicked Approve; backend rejected, no order commit",
                 http=info, backend_reason=public_reason, wms_diagnostic=diagnostic)
            report["last_verified"] = "Dispatcher Approve request rejected; Sales feasible is last PASS"
            return []
        result = response.json()
        if result.get("order", {}).get("id") != order_id or result["order"].get("status") != "APPROVED":
            raise RuntimeError("HTTP 200 without APPROVED is not approval")
        trip_ids = result.get("trip_ids")
        notifications = result.get("notifications")
        if (not isinstance(trip_ids, list) or len(trip_ids) != 1
            or type(trip_ids[0]) is not int or not isinstance(notifications, list)):
            raise RuntimeError("Missing committed trips or notification metadata")
        confirmed = [item for item in notifications if item.get("template") == "CONFIRMED"]
        if (len(confirmed) != 1 or type(confirmed[0].get("id")) is not int
            or confirmed[0].get("status") != "queued"):
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
        queued = sql(
            "SELECT template||'|'||status FROM ops.notification "
            f"WHERE id={notify_id} AND order_id={order_id} AND plan_id={plan_id}", env,
        )
        trips_db = sql(
            "SELECT t.id FROM ops.delivery_trip t JOIN plan.plan_vehicle pv ON pv.id=t.plan_vehicle_id "
            f"WHERE pv.plan_id={plan_id} ORDER BY t.id", env,
        ).splitlines()
        if (row[:3] != ["APPROVED", "approved", "wms_synthetic"] or row[3] != row[4]
            or trips_db != [str(t) for t in trip_ids] or queued != "CONFIRMED|queued"):
            raise RuntimeError("Approve/SQL/WMS batch or notification IDs did not agree")
        # Step 4 requires T15 rotation assignment as well as approval.
        assigned = sql(
            "SELECT COALESCE(assigned_dispatcher_employee_id::text,'NULL') "
            f"FROM ops.delivery_trip WHERE id IN ({','.join(str(i) for i in trip_ids)}) "
            "ORDER BY id", env,
        ).splitlines()
        if len(assigned) != len(trip_ids):
            raise RuntimeError("Post-approve Dispatcher assignment/trip count mismatch")
        if len(set(assigned)) > 1 and "NULL" not in assigned:
            rotation_status = "FAIL"
        elif "NULL" in assigned:
            rotation_status = "BLOCKED"
        else:
            rotation_status = "NOT VERIFIED"  # T15 fairness needs separate evidence
        report["approval_subcheck"] = "PASS"
        report["rotation_subcheck"] = {
            "status": rotation_status,
            "assigned_trips": sum(value != "NULL" for value in assigned),
            "expected_trips": len(trip_ids),
        }
        mark(
            report, "4", rotation_status,
            "Dispatcher Approve UI/HTTP/DB/synthetic WMS PASS; R3 Dispatcher rotation "
            "not independently verified (T15)",
            approve_subcheck="PASS", rotation_subcheck=rotation_status,
            plan_id=plan_id, trip_ids=trip_ids, wms_source="wms_synthetic",
            reflected_batch=row[3],
        )
        report["last_verified"] = "Dispatcher UI approved; WMS synthetic batch and queued CONFIRMED verified"
        screenshot(page, out, "04-dispatcher-approved.png")
        return trip_ids
    finally:
        page.close()


def mailpit_confirm(report: dict, env: dict[str, str]) -> None:
    notify_id, order_id, order_no = report["notification_id"], report["order_id"], report["order_no"]
    window = sql(
        "SELECT promise_start::text||'|'||promise_end::text "
        f"FROM ops.customer_order WHERE id={order_id}", env,
    ).split("|")
    start, end = (
        datetime.fromisoformat(value).astimezone(ZoneInfo(ZONE)).isoformat(timespec="minutes")
        for value in window
    )
    # Worker intentionally opts-in ONLY after the full seed+migrations.
    compose("--profile", "demo-worker", "up", "-d", "cfo-worker", env=env)
    report["worker_start"] = "After migrate and seed, opt-in demo-worker"
    deadline = time.monotonic() + 95
    while time.monotonic() < deadline:
        row = sql(
            "SELECT status||'|'||attempts FROM ops.notification "
            f"WHERE id={notify_id} AND order_id={order_id} AND template='CONFIRMED'", env,
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
    messages = response.json().get("messages") or []
    subject = f"Your delivery is confirmed — order {order_no}"
    matching = [msg for msg in messages if msg.get("Subject") == subject]
    if len(matching) != 1:
        mark(report, "5", "FAIL", "Mailpit does not contain exactly one matching synthetic CONFIRMED",
             matching_count=len(matching), notification_id=notify_id)
        return
    # Validate customer-visible order reference + scheduled window without
    # persisting the message body, address, recipient or private email.
    message_id = matching[0].get("ID")
    detail = httpx.get(MAILPIT + f"/api/v1/message/{message_id}", timeout=8, trust_env=False)
    body_text = detail.json().get("Text", "") if detail.status_code == 200 else ""
    if (
        f"Order {order_no}: Delivery confirmed." not in body_text
        or f"Delivery window: {start} – {end}." not in body_text
    ):
        mark(report, "5", "FAIL", "Mailpit CONFIRMED did not match the CFO order number and exact committed window",
             order_no=order_no, promise_start=start, promise_end=end)
        return
    audit = sql(
        "SELECT count(*) FROM audit.decision_log WHERE action='NOTIFICATION_SENT' "
        f"AND order_id={order_id} AND entity_id='{notify_id}'", env,
    )
    if audit != "1":
        mark(report, "5", "FAIL", "CONFIRMED had not exactly one committed NOTIFICATION_SENT audit")
        return
    mark(report, "5", "PASS",
         f"CONFIRMED #{notify_id} queued → sent; one Mailpit email for {order_no}, {start} – {end}",
         notification_id=notify_id, mailpit_count=1, mailpit_http=200, mailpit_message_id=message_id,
         promise_start=start, promise_end=end)
    report["last_verified"] = "CONFIRMED sent with matching ID and exactly one Mailpit email"


def start_execution_day(report: dict, env: dict[str, str]) -> dict[str, str]:
    order_id, plan_id = report["order_id"], report["plan_id"]
    trip_id = report["trip_ids"][0]
    query = (
        "SELECT p.target_date::text||'|'||t.depart_planned_at::text "
        "FROM ops.customer_order o JOIN plan.fulfilment_plan p ON p.id=o.approved_plan_id "
        "JOIN plan.plan_vehicle v ON v.plan_id=p.id "
        "JOIN ops.delivery_trip t ON t.plan_vehicle_id=v.id "
        f"WHERE o.id={order_id} AND o.status='APPROVED' AND p.id={plan_id} AND t.id={trip_id}"
    )
    row = sql(query, env)
    target_date, planned_departure = row.split("|")
    execution_at = datetime.fromisoformat(planned_departure).astimezone(ZoneInfo(ZONE))
    if execution_at.date().isoformat() != target_date:
        raise RuntimeError("Trip departure and approved plan use different market dates")

    # Keep DB/Source/Mailpit intact and roll only the API clock to the T12 duty day.
    compose("--profile", "demo-worker", "stop", "cfo-worker", env=env)
    execution_env = {**env, "APP_NOW": execution_at.isoformat(), "DEMO_D7_FIXTURE_DIR": ""}
    compose("up", "-d", "--no-deps", "--wait", "--wait-timeout", "90", "cfo-api", env=execution_env)
    if sql(query, execution_env) != row:
        raise RuntimeError("Order, approved plan or trip changed during the execution-day rollover")
    report.update(execution_app_now=execution_env["APP_NOW"], target_date=target_date)
    return execution_env


def warehouse(browser, password: str, order_id: int, trip_ids: list[int],
              out: Path, report: dict, env: dict[str, str]) -> bool:
    wh_id = int(sql(f"SELECT warehouse_id FROM ops.delivery_trip WHERE id={trip_ids[0]}", env))
    account = sql(
        "SELECT u.email FROM ref.app_user u JOIN hr.employee e ON e.id=u.employee_id "
        "WHERE e.employee_no='DEMO-STO-W00'", env,
    )
    page = login(browser, "/warehouse/prep", account, password, out, "Warehouse", app_now=env["APP_NOW"])
    try:
        row = page.locator("tbody tr").filter(has=page.get_by_text(report["order_no"], exact=True))
        expect(row).to_be_visible(timeout=15000)
        report["warehouse_id"] = wh_id
        results = []
        actions = [("START_PREP", "Start preparation", {}), ("GOODS_READY", "Goods ready", {}),
                   *[("LOADED", "Mark loaded", {"trip_id": trip}) for trip in trip_ids]]
        # The real Chrome device advances within the plan's execution day
        # between execution milestones.
        # This is an explicit synthetic five-minute skew allowance (06 §8);
        # it preserves causal order without changing backend clock/gates.
        event_seconds = (10, 30, 10, *([5] * (len(trip_ids) - 1)))
        for index, (kind, label, extra) in enumerate(actions, start=1):
            page.clock.fast_forward(event_seconds[index - 1] * 1000)
            at = datetime.fromisoformat(env["APP_NOW"]) + timedelta(seconds=sum(event_seconds[:index]))
            local_at = at.strftime("%Y-%m-%dT%H:%M:%S")
            button_name = label if kind != "LOADED" else None
            if button_name:
                row.get_by_role("button", name=button_name, exact=True).click()
            else:
                # Only one vehicle in E0-04. Use exact assigned trip ID and
                # rendered vehicle code, never a guessed index.
                row.get_by_role("button", name=re.compile("^Mark loaded")).click()
            dialog = page.get_by_role("dialog", name=f"Confirm {label}")
            dialog.get_by_label("Occurred at (device local time)").fill(local_at)
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
            expect(dialog).to_be_hidden()
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
        mark(report, "7", "PASS",
             f"{report['order_no']} on {report['target_date']}: START_PREP → GOODS_READY → LOADED, same trip in PostgreSQL",
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
    page = login(browser, "/driver", account, password, out, "Driver", app_now=env["APP_NOW"])
    try:
        # Driver time is after the last warehouse event, within the server's
        # accepted +5 minute skew without bypassing the official shift gate.
        page.clock.fast_forward(60_000)
        trip_label = page.get_by_text(re.compile(rf"^(Now|Later) · Trip {trip_id}$"))
        card = page.get_by_role("article").filter(has=trip_label)
        expect(card).to_be_visible(timeout=16000)
        card.get_by_role("button", name="Review and dispatch").click()
        screenshot(page, out, "08-driver-dispatch-ready.png")
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == f"/api/v1/orders/{order_id}/events") as posted:
            page.get_by_role("button", name="Mark dispatched").click()
        info = metadata(posted.value)
        report["api"].append(info)
        report["dispatch_attempt"] = {**info, "trip_id": trip_id}
        if not posted.value.ok:
            try:
                error = posted.value.json().get("error", {})
                code = error.get("code")
                msg = error.get("message")
            except (ValueError, AttributeError, Error):
                code, msg = None, None
            classified = dispatch_rejection(posted.value.status, code, msg)
            reason = f"Driver UI Dispatch HTTP {info['http']} {info['error_code']}. {classified['reason']}"
            report["dispatch_attempt"]["reason"] = msg if classified["status"] == "BLOCKED" else classified["reason"]
            mark(report, "8", classified["status"], reason,
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
    order_no = report["order_no"]
    report["eta_history"] = {"status": "NOT VERIFIED"}
    account = sql(
        "SELECT u.email FROM ref.app_user u JOIN hr.employee e ON e.id=u.employee_id "
        "WHERE 'customer_service'=ANY(u.roles) AND e.market_id=1 ORDER BY u.id LIMIT 1", env,
    )
    if not account:
        report["cs_lookup"] = {"status": "BLOCKED"}
        mark(report, "11", "BLOCKED", "No authorized market-scoped CS fixture account; ETA not tested", task="T03")
        return
    report["cs_lookup"] = {"status": "FAIL", "order_id": order_id, "order_no": order_no}
    page = login(browser, "/cs/orders", account, password, out, "CS", app_now=env["APP_NOW"])
    try:
        page.get_by_role("searchbox", name="Search orders").fill(order_no)
        with page.expect_response(lambda r: r.request.method == "GET" and
                                  urlsplit(r.url).path == "/api/v1/orders" and
                                  "q=" in urlsplit(r.url).query) as listed:
            page.get_by_role("button", name="Search", exact=True).click()
        data = body(listed.value, report)
        matches = [item for item in data.get("items", []) if item.get("order_no") == order_no]
        if len(matches) != 1 or matches[0].get("id") != order_id:
            mark(report, "11", "FAIL", "CS lookup did not return the synced CFO order; ETA not tested",
                 http=metadata(listed.value), task="T03")
            return
        with page.expect_response(lambda r: r.request.method == "GET" and
                                  urlsplit(r.url).path == f"/api/v1/orders/{order_id}") as got:
            page.get_by_role("button", name=re.compile(re.escape(order_no))).click()
        detail = body(got.value, report)
        if detail.get("id") != order_id or detail.get("order_no") != order_no:
            raise RuntimeError("CS order ID or CFO order number mismatch")
        expect(page.get_by_label("Order details").get_by_text(order_no, exact=True)).to_be_visible()
        screenshot(page, out, "10-cs-order-lookup.png")
        report["cs_lookup"] = {"status": "PASS", "order_id": order_id, "order_no": order_no,
                               "http": metadata(got.value), "status_from_api": detail.get("status")}
        report["last_verified"] = "CS UI looked up same order; detail matches API"
        # Separate API contract, distinct from the CS order projection.
        # HTTP500 is a failure unless correlated backend logs prove a known T14 stub.
        token = page.evaluate("localStorage.getItem('cfo_token')")
        if not isinstance(token, str) or not token:
            raise RuntimeError("CS authenticated browser session did not expose a token")
        # Same authorized CS session, but this is a separate API probe, NOT a
        # customer-visible UI action or a test of history rendering.
        eta_path = f"/api/v1/orders/{order_id}/eta-forecasts"
        try:
            probe = page.request.get(API + eta_path,
                                     headers={"Authorization": "Bearer " + token}, timeout=10_000)
        except Error:
            info = {"path": eta_path, "http": None, "error_code": None, "transport_error": True}
            status, reason = "FAIL", "ETA request returned no HTTP response"
        else:
            info = metadata(probe)
            report["api"].append(info)
            correlation_id = probe.headers.get("x-correlation-id")
            with TemporaryDirectory(prefix="t27-eta-") as temp:
                log = Path(temp) / "api.log"
                if (probe.status, info["error_code"]) == (500, "INTERNAL_ERROR") and correlation_id:
                    try:
                        api_log = compose("logs", "--no-color", "--no-log-prefix", "--tail", "200",
                                          "cfo-api", env=env, capture=True)
                    except RuntimeError:
                        pass  # Without a matching log the shared classifier returns FAIL.
                    else:
                        log.write_text(api_log, encoding="utf-8")
                status = eta_history_status(probe.status, info["error_code"], log, eta_path, correlation_id)
            if status == "BLOCKED":
                reason = "T14 ETA stub confirmed by a correlated backend NotImplementedError"
            elif status == "FAIL":
                reason = f"Unexpected ETA response HTTP {info['http']} {info['error_code']}"
            else:
                reason = "ETA probe returned HTTP 200; history rendering not verified"
        report["eta_history"] = {**info, "status": status, "reason": reason}
        mark(report, "11", status, f"CS lookup PASS for {order_no}. ETA {status}. {reason}.",
             cs_lookup="PASS", eta_history=report["eta_history"], task="T14")
    finally:
        page.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path, help="Run the full Chrome scenario and save its evidence.")
    mode.add_argument("--prepare-wms", action="store_true", help="Start WMS for an existing manual demo plan.")
    parser.add_argument("--project", choices=(E0_PROJECT, T26_PROJECT), default=E0_PROJECT)
    parser.add_argument("--source-ref")
    parser.add_argument("--plan-id", type=int)
    parser.add_argument("--rank", type=int, choices=(1, 2, 3))
    args = parser.parse_args()
    selector = (args.source_ref, args.plan_id, args.rank)
    if args.project == T26_PROJECT:
        if not args.prepare_wms or not args.source_ref or not args.plan_id or args.plan_id < 1 or args.rank is None:
            parser.error("T26 requires --prepare-wms, --source-ref, --plan-id and --rank")
    elif any(value is not None for value in selector):
        parser.error("Plan selection is available only for cfo-demo-t26")
    env = dict(os.environ)
    data = dotenv_values(ROOT / ".env")
    if args.prepare_wms:
        if (data.get("APP_ENV"), data.get("DEMO_DISPOSABLE")) != ("test", "1"):
            parser.error("Private .env must specify APP_ENV=test and DEMO_DISPOSABLE=1")
        env.update({key: value for key, value in data.items() if value is not None})
        try:
            cfo_db = make_url(env.get("DATABASE_URL", ""))
            source_db = make_url(env.get("SOURCE_SE_DATABASE_URL", ""))
        except (ArgumentError, ValueError):
            parser.error("Private demo Compose database URLs required")
        if (cfo_db.host, cfo_db.port, cfo_db.database, source_db.host, source_db.database) != (
            "postgres", 5432, "cfo", "postgres", "source_se",
        ):
            parser.error("Private demo Compose database URLs required")
        env.update(
            APP_NOW=NOW,
            COMPOSE_PROJECT_NAME=args.project,
            COMPOSE_FILE=os.pathsep.join(("docker-compose.yml", "tools/t27_e1_compose.override.yml")),
            SYNTHETIC_WMS_API_KEY=env.get("SYNTHETIC_WMS_API_KEY") or secrets.token_urlsafe(32),
            MSYS_NO_PATHCONV="1",
            PYTHONPATH=os.pathsep.join(filter(None, (str(ROOT), str(ROOT / "backend"), env.get("PYTHONPATH")))),
        )
        try:
            if args.project == T26_PROJECT:
                prepare_t26_wms(env, *selector)
            else:
                env["DEMO_D7_FIXTURE_DIR"] = ""
                prepare_manual_wms(env)
        except RuntimeError as exc:
            print(f"BLOCKED: {exc}", file=sys.stderr)
            return 2
        except (OSError, subprocess.TimeoutExpired):
            print("BLOCKED: Could not run the disposable demo command or it timed out.", file=sys.stderr)
            return 2
        return 0
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
        if sql(f"SELECT count(*) FROM ops.customer_order WHERE external_ref='{SOURCE_REF}'", env) != "0":
            raise RuntimeError("Pre-Sync fixture invalid: CFO order already present")
        report["start_verified"] = "Source-only pre-Sync (CFO count=0)"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome")
            try:
                report["active_step"] = "1"
                order_id, run_id, plan_id = sales(browser, password, args.output, report, env)
                report["active_step"] = "4"
                start_disposable_wms(env, report)
                trip_ids = approve(browser, password, run_id, plan_id, order_id, args.output, report, env)
                if trip_ids:
                    report["active_step"] = "5"
                    mailpit_confirm(report, env)
                    report["active_step"] = "7"
                    execution_env = start_execution_day(report, env)
                    if warehouse(browser, password, order_id, trip_ids, args.output, report, execution_env):
                        report["active_step"] = "8"
                        driver(browser, password, trip_ids[0], order_id, args.output, report, execution_env)
                    report["active_step"] = "11"
                    cs(browser, password, order_id, args.output, report, execution_env)
                else:
                    # Same order may still be available for CS even when approval
                    # was blocked; do not attempt unauthorized warehouse actions.
                    report["active_step"] = "11"
                    cs(browser, password, order_id, args.output, report, env)
            finally:
                browser.close()
        statuses = {row["step"]: row["status"] for row in report["steps"]}
        required = ("1", "2", "5", "7")
        report["result"] = (
            "PASS_WITH_BLOCKERS"
            if all(statuses[step] == "PASS" for step in required)
            and report.get("approval_subcheck") == "PASS"
            and report.get("dispatch_attempt")
            and "FAIL" not in statuses.values()
            else "FAIL"
        )
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
                "", f"Commit: {report['revision']}", f"Sales/Approve clock: {NOW} / {ZONE}",
                f"Warehouse/Driver clock: {report.get('execution_app_now', 'NOT VERIFIED')} / {ZONE}",
                f"Source reference: {SOURCE_REF} / CFO order number: {report.get('order_no', 'NOT VERIFIED')}",
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
