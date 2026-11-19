"""Real Chrome, FastAPI and PostgreSQL walkthrough for US-WH-04 and US-EXE-01."""

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import Browser, Error, Page, Response, expect, sync_playwright

from alembic import command
from tests.e2e.prep_queue_fixture import (
    APP_NOW,
    BUSINESS_DATE,
    DRIVER_EMAILS,
    TIME_ZONE,
    WAREHOUSE_EMAIL,
    seed_approved_order,
    vehicle_code,
)
from tests.integration.conftest import (
    BACKEND_DIR,
    _admin_exec,
    _plain_dsn,
    _with_database,
    alembic_config,
    async_url,
    fetch,
)

FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
QUEUE_PATH = "/api/v1/warehouses/1/prep-queue"
EVENT_PATH = "/api/v1/orders/1/events"
DRIVER_PATH = "/api/v1/driver/trips"


def loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@contextmanager
def local_service(args: list[str], cwd: Path, env: dict[str, str], url: str, log: Path) -> Iterator[None]:
    with log.open("w", encoding="utf-8") as output:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 40
            while proc.poll() is None and time.monotonic() < deadline:
                try:
                    if httpx.get(url, timeout=1, trust_env=False).is_success:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError(f"Local service did not become ready. See {log.name}.")
            yield
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def response_for(response: Response, method: str, url: str) -> bool:
    return response.request.method == method and response.url == url


def require_ok(response: Response) -> None:
    if response.ok:
        return
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        error = {}
    raise AssertionError(
        f"{response.request.method} {urlsplit(response.url).path} returned {response.status} "
        f"{error.get('code', '')} {error.get('message', '')}"
    )


def sign_in(page: Page, web: str, api: str, email: str, password: str, role: str) -> None:
    page.goto(f"{web}/login")
    page.locator('input[type="email"]').fill(email)
    try:
        page.get_by_label("Password", exact=True).fill(password)
    except Error:
        raise AssertionError("Could not enter the synthetic password on /login.") from None
    with page.expect_response(lambda res: response_for(res, "POST", f"{api}/api/v1/auth/login")) as result:
        page.get_by_role("button", name="Sign in", exact=True).click()
    response = result.value
    require_ok(response)
    user = response.json()["user"]
    assert user["roles"] == [role] and user["location_ids"] == [1]


def queue_state(response: Response, order_no: str, status: str, loaded: list[int]) -> dict[str, object]:
    require_ok(response)
    queue = response.json()
    assert queue["date"] == BUSINESS_DATE
    [order] = queue["orders"]
    assert (order["order_no"], order["order_id"], order["status"]) == (order_no, 1, status)
    assert order["lines"] == 1
    assert [row["trip_id"] for row in order["loading"] if row["loaded"]] == loaded
    return {"http": response.status, "date": queue["date"], "status": status, "loaded_trips": loaded}


def run_warehouse(
    page: Page, web: str, api: str, order_no: str, password: str, trip_count: int, out: Path, report: dict
) -> None:
    queue_url, event_url = f"{api}{QUEUE_PATH}", f"{api}{EVENT_PATH}"
    with page.expect_response(lambda res: response_for(res, "GET", queue_url)) as initial:
        sign_in(page, web, api, WAREHOUSE_EMAIL, password, "warehouse")
    assert urlsplit(page.url).path == "/warehouse/prep"
    report["initial_queue"] = queue_state(initial.value, order_no, "APPROVED", [])
    row = page.locator("tbody tr").filter(has_text=order_no)
    expect(row.locator('[data-label="Status"]')).to_have_text("APPROVED")
    page.screenshot(path=out / "00-approved.png")

    steps = [
        ("START_PREP", "Start preparation", "10:05:10", {"crew_size": 3}, "PREPARING", []),
        ("GOODS_READY", "Goods ready", "10:05:40", {}, "GOODS_READY", []),
        (
            "LOADED",
            "Mark loaded",
            "10:05:50",
            {"trip_id": 1},
            "LOADED" if trip_count == 1 else "GOODS_READY",
            [1],
        ),
    ]
    if trip_count == 2:
        steps.append(("LOADED", "Mark loaded", "10:05:55", {"trip_id": 2}, "LOADED", [1, 2]))
    keys: set[str] = set()
    for index, (kind, action, when, payload, status, loaded) in enumerate(steps, start=1):
        button_name = f"{action} · {vehicle_code(payload['trip_id'])}" if kind == "LOADED" else action
        row.get_by_role("button", name=button_name, exact=True).click()
        dialog = page.get_by_role("dialog", name=f"Confirm {action}")
        local_at = f"{BUSINESS_DATE}T{when}"
        dialog.get_by_label("Occurred at (device local time)", exact=True).fill(local_at)
        if kind == "START_PREP":
            dialog.get_by_label("Crew size (people actually working)").fill("3")

        # The interval is shorter than the queue's 20s polling cadence.
        with page.expect_response(lambda res: response_for(res, "GET", queue_url), timeout=10_000) as refresh:
            with page.expect_response(lambda res: response_for(res, "POST", event_url)) as receipt:
                dialog.get_by_role("button", name=f"Confirm {action}", exact=True).click()
            post = receipt.value
            request = post.request.post_data_json
            entry = {"path": EVENT_PATH, "http": post.status, **request, "entered_local_time": local_at}
            report["events"].append(entry)
            require_ok(post)
            ack = post.json()
            entry.update(
                event_id=ack["event_id"],
                order_status=ack["order_status"],
                risk_version=ack["risk"]["version"],
            )
            key = post.request.header_value("Idempotency-Key")
            assert key and key not in keys
            keys.add(key)
            assert request["event_type"] == kind and request["payload"] == payload
            assert datetime.fromisoformat(request["occurred_at"]) == datetime.fromisoformat(
                f"{local_at}+01:00"
            )
            assert isinstance(ack["event_id"], int) and ack["order_status"] == status
        entry["ack_refetch"] = queue_state(refresh.value, order_no, status, loaded)
        expect(row.locator('[data-label="Status"]')).to_have_text(status)
        expect(dialog).to_have_count(0)
        page.screenshot(path=out / f"{index:02d}-{kind.lower()}-{payload.get('trip_id', 'order')}.png")

    with page.expect_response(lambda res: response_for(res, "GET", queue_url)) as reloaded:
        page.reload()
    report["reload_queue"] = queue_state(reloaded.value, order_no, "LOADED", list(range(1, trip_count + 1)))
    expect(row.locator('[data-label="Status"]')).to_have_text("LOADED")
    expect(row.get_by_role("button")).to_have_count(0)
    page.screenshot(path=out / "warehouse-reloaded.png")


def check_driver(
    browser: Browser, web: str, api: str, order_no: str, trip_id: int, password: str, out: Path, report: dict
) -> None:
    page = browser.new_page(
        timezone_id=TIME_ZONE, viewport={"width": 430, "height": 932}, service_workers="block"
    )
    page.set_default_timeout(12_000)
    try:
        with page.expect_response(lambda res: response_for(res, "GET", f"{api}{DRIVER_PATH}")) as received:
            sign_in(page, web, api, DRIVER_EMAILS[trip_id - 1], password, "driver")
        response = received.value
        result = {"path": DRIVER_PATH, "http": response.status, "expected_trip_id": trip_id}
        report["driver_handoff"].append(result)
        require_ok(response)
        trips = response.json()["items"]
        result["returned_trip_ids"] = [trip["trip_id"] for trip in trips]
        [trip] = trips
        assert trip["trip_id"] == trip_id and trip["status"] == "loading"
        assert [stop["order_no"] for stop in trip["stops"]] == [order_no]
        card = page.get_by_role("article").filter(has_text=f"Trip {trip_id}")
        expect(card.get_by_role("heading", name=vehicle_code(trip_id))).to_be_visible()
        expect(card.get_by_text(order_no, exact=False)).to_be_visible()
        expect(card.get_by_role("button", name="Review and dispatch")).to_be_enabled()
        assert urlsplit(page.url).path == "/driver"
        result.update(status=trip["status"], order_no=order_no, visible=True)
        page.screenshot(path=out / f"driver-trip-{trip_id}.png")
    finally:
        page.close()


def order_trip_states(dsn: str) -> tuple[str, list[dict]]:
    order_status = fetch(dsn, "SELECT status FROM ops.customer_order WHERE id=1")[0]["status"]
    trips = fetch(
        dsn,
        "SELECT t.id AS trip_id, t.status FROM ops.delivery_trip t "
        "JOIN ops.trip_stop s ON s.trip_id=t.id WHERE s.order_id=1 ORDER BY t.id",
    )
    return order_status, [dict(trip) for trip in trips]


def verify_warehouse_postgres(dsn: str, trip_count: int, report: dict) -> None:
    events = fetch(
        dsn,
        "SELECT id, event_type, trip_id, occurred_at FROM ops.milestone_event "
        "WHERE order_id=1 AND event_type IN ('START_PREP','GOODS_READY','LOADED') ORDER BY id",
    )
    report["persisted_events"] = [
        dict(event) | {"occurred_at": event["occurred_at"].isoformat()} for event in events
    ]
    matches = [
        (event["id"], event["event_type"], event["trip_id"], event["occurred_at"]) for event in events
    ] == [
        (
            expected["event_id"],
            expected["event_type"],
            expected["payload"].get("trip_id"),
            datetime.fromisoformat(expected["occurred_at"]),
        )
        for expected in report["events"]
    ]
    order_status, trips = order_trip_states(dsn)
    report["warehouse_postgres"] = {
        "order_status": order_status,
        "trips": trips,
        "milestones_match_browser": matches,
    }
    assert matches and len(events) == trip_count + 2
    assert order_status == "LOADED"
    assert trips == [{"trip_id": trip_id, "status": "loading"} for trip_id in range(1, trip_count + 1)]


def verify_dispatch_postgres(dsn: str, trip_count: int, evidence: dict) -> None:
    dispatched = fetch(
        dsn,
        "SELECT id, event_type, trip_id FROM ops.milestone_event "
        "WHERE order_id=1 AND event_type='DISPATCHED' ORDER BY id",
    )
    evidence["persisted_dispatch"] = [dict(item) for item in dispatched]
    order_status, trips = order_trip_states(dsn)
    evidence["db_order_status"] = order_status
    evidence["db_trip_states"] = trips
    observed = [item for item in evidence["driver"] if item.get("dispatch_status") == "PASS"]
    matched_events = [(item["id"], item["trip_id"]) for item in dispatched] == [
        (item["event_id"], item["trip_id"]) for item in observed
    ]
    departed = {item["trip_id"] for item in observed}
    matched_states = order_status == ("DISPATCHED" if departed else "LOADED") and trips == [
        {"trip_id": trip_id, "status": "on_road" if trip_id in departed else "loading"}
        for trip_id in range(1, trip_count + 1)
    ]
    evidence["postgres_dispatch_matches_browser"] = matched_events and matched_states
    assert matched_events and matched_states


def walkthrough(
    dsn: str,
    node: str,
    trip_count: int,
    out: Path,
    report: dict,
    *,
    continue_driver_cs: bool = False,
    chrome_path: Path | None = None,
) -> None:
    password = secrets.token_urlsafe(24)
    order_no = seed_approved_order(dsn, trip_count, password)
    report["order_no"] = order_no
    api_port, web_port = loopback_port(), loopback_port()
    api, web = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    api_env = os.environ | {
        "APP_ENV": "test",
        "APP_NOW": APP_NOW,
        "DATABASE_URL": async_url(dsn),
        "JWT_SECRET": secrets.token_urlsafe(32),
        "CORS_ORIGINS": json.dumps([web]),
    }
    web_env = os.environ | {"VITE_API_URL": f"{api}/api/v1", "VITE_USE_MOCKS": "false"}
    api_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(api_port),
        "--no-access-log",
    ]
    vite_cmd = [
        node,
        str(FRONTEND_DIR / "node_modules/vite/bin/vite.js"),
        "--host",
        "127.0.0.1",
        "--port",
        str(web_port),
        "--strictPort",
    ]
    with (
        local_service(api_cmd, BACKEND_DIR, api_env, f"{api}/api/v1/health", out / "api.log"),
        local_service(vite_cmd, FRONTEND_DIR, web_env, web, out / "vite.log"),
        sync_playwright() as playwright,
        closing(playwright.chromium.launch(channel="chrome", executable_path=chrome_path)) as browser,
        ThreadPoolExecutor(max_workers=1) as postgres,
    ):
        report["chrome_version"] = browser.version
        page = browser.new_page(
            timezone_id=TIME_ZONE, viewport={"width": 1440, "height": 1000}, service_workers="block"
        )
        page.set_default_timeout(12_000)
        report["warehouse_browser_status"] = "FAIL"
        run_warehouse(page, web, api, order_no, password, trip_count, out, report)
        page.close()
        report["warehouse_browser_status"] = "PASS"
        # Playwright's synchronous API owns the main thread's event loop.
        # The PostgreSQL helpers use their own asyncio.run in the worker.
        postgres.submit(verify_warehouse_postgres, dsn, trip_count, report).result()
        # The continuation verifies the same assigned trip through its own
        # driver browser session. Avoid duplicate logins: real auth rate limit
        # must not be disabled just to exercise the two-trip case.
        if not continue_driver_cs:
            for trip_id in range(1, trip_count + 1):
                check_driver(browser, web, api, order_no, trip_id, password, out, report)
        if continue_driver_cs:
            from tests.e2e.t27_driver_cs import run_driver_cs

            try:
                run_driver_cs(browser, web, api, order_no, password, trip_count, out, report)
            finally:
                postgres.submit(verify_dispatch_postgres, dsn, trip_count, report["t27"]).result()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trips", type=int, choices=(1, 2), default=1)
    parser.add_argument(
        "--continue-driver-cs",
        action="store_true",
        help="T27: use the SAME APPROVED fixture for Driver dispatch and CS UI, record Round 3 blockers.",
    )
    parser.add_argument("--node", default="node")
    parser.add_argument("--chrome-path", type=Path, help="Path to a local Chrome for Testing binary.")
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for screenshots and results."
    )
    args = parser.parse_args()
    admin_dsn = _plain_dsn(os.environ.get("TEST_DATABASE_URL", ""))
    if urlsplit(admin_dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("TEST_DATABASE_URL must point to a local disposable PostgreSQL server.")
    args.output.mkdir(parents=True)
    name = f"cfo_e3_{secrets.token_hex(6)}"
    dsn = _with_database(admin_dsn, name)
    report = {
        "result": "FAIL",
        "app_now": APP_NOW,
        "market_timezone": TIME_ZONE,
        "warehouse_id": 1,
        "warehouse_code": "WH-1",
        "order_id": 1,
        "trip_count": args.trips,
        "events": [],
        "driver_handoff": [],
        "queue_path": QUEUE_PATH,
    }
    asyncio.run(_admin_exec(admin_dsn, f'CREATE DATABASE "{name}"'))
    try:
        command.upgrade(alembic_config(dsn), "head")
        walkthrough(
            dsn,
            args.node,
            args.trips,
            args.output,
            report,
            continue_driver_cs=args.continue_driver_cs,
            chrome_path=args.chrome_path,
        )
        report["result"] = "PASS"
    except Exception as exc:
        report["failure"] = type(exc).__name__
        raise
    finally:
        try:
            (args.output / "demo-prep-browser-results.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
        finally:
            asyncio.run(_admin_exec(admin_dsn, f'DROP DATABASE "{name}" WITH (FORCE)'))


if __name__ == "__main__":
    main()
