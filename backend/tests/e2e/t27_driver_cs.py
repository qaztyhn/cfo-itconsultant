"""T27 browser continuation: real assigned Driver -> CS on the E3 APPROVED fixture.

Never fabricates the missing Round 3 location/ETA contracts. Only sanitized HTTP
status/error.code, synthetic order/trip/event IDs and safe screenshots enter evidence.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Browser, Error, Page, Response, expect
from playwright.sync_api import TimeoutError as BrowserTimeout

from tests.e2e.prep_queue_browser import DRIVER_PATH, EVENT_PATH, require_ok, response_for, sign_in
from tests.e2e.prep_queue_fixture import APP_NOW, DRIVER_EMAILS, TIME_ZONE, vehicle_code

CS_ACCOUNT = "cs@cfo.test"
ETA_STUB_TASK = "T14"
GPS_UI_TASKS = ["T13", "T14", "T16"]


def _metadata(response: Response) -> dict[str, object]:
    """Never persist raw request bodies, auth headers or third-party PII."""
    code = None
    if not response.ok:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict) and isinstance(error.get("code"), str):
                    code = error["code"]
        except (ValueError, TypeError):
            pass
    return {"path": urlsplit(response.url).path, "http": response.status, "error_code": code}


def _block(stage: dict[str, object], task: list[str], why: str) -> None:
    stage["status"] = "BLOCKED"
    stage["tasks"] = task
    stage["reason"] = why


def _failed(stage: dict[str, object], task: list[str], exc: Exception) -> None:
    stage["status"] = "FAIL"
    stage["tasks"] = task
    # No passwords, raw response bodies, recipient names, headers or coordinates.
    stage["exception_type"] = type(exc).__name__


def _driver_dispatch(
    browser: Browser, web: str, api: str, trip_id: int, order_no: str, password: str, output: Path
) -> dict[str, object]:
    stage: dict[str, object] = {
        "trip_id": trip_id,
        "order_no": order_no,
        "status": "NOT VERIFIED",
        "http": [],
    }
    page = browser.new_page(
        timezone_id=TIME_ZONE, viewport={"width": 430, "height": 932}, service_workers="block"
    )
    page.set_default_timeout(15_000)
    try:
        # Driver UI otherwise uses the real machine clock (weeks after the
        # seeded business date), violating event occurrence chronology.
        page.clock.install(time=datetime.fromisoformat(APP_NOW))
        with page.expect_response(lambda r: response_for(r, "GET", f"{api}{DRIVER_PATH}")) as get_trips:
            sign_in(page, web, api, DRIVER_EMAILS[trip_id - 1], password, "driver")
        stage["http"].append(_metadata(get_trips.value))
        require_ok(get_trips.value)
        items = get_trips.value.json()["items"]
        assert len(items) == 1 and items[0]["trip_id"] == trip_id
        assert items[0]["status"] == "loading"
        assert [stop["order_no"] for stop in items[0]["stops"]] == [order_no]
        card = page.get_by_role("article").filter(has_text=f"Trip {trip_id}")
        expect(card.get_by_role("heading", name=vehicle_code(trip_id))).to_be_visible()
        card.get_by_role("button", name="Review and dispatch").click()
        expect(page.get_by_role("button", name="Mark dispatched")).to_be_enabled()
        page.screenshot(path=output / f"t27-driver-{trip_id}-before-dispatch.png")

        with page.expect_response(
            lambda r: response_for(r, "POST", f"{api}{EVENT_PATH}"), timeout=30000
        ) as sent:
            page.get_by_role("button", name="Mark dispatched").click()
        res = sent.value
        stage["http"].append(_metadata(res))
        stage["event_type"] = "DISPATCHED"
        if not res.ok:
            stage["last_verified"] = "Assigned trip visible; DISPATCHED rejected by backend"
            _block(
                stage,
                ["T12", "E1", "T16"],
                "DISPATCHED rejected: verified official shift, 56-day D7/vehicle "
                "proof or integrated ETA/notification may be missing",
            )
            return stage
        ack = res.json()
        assert isinstance(ack.get("event_id"), int)
        stage["event_id"] = ack["event_id"]
        stage["order_status"] = ack.get("order_status")
        stage["status"] = "PASS"
        page.get_by_role("button", name="Refresh trips").click()
        # Round 3 requires a manual coordinate update and position on POD.
        # Do not treat older no-GPS DELIVERED UI as a compliant pass.
        if page.get_by_text("GPS upload is off.", exact=False).count():
            _block(stage, GPS_UI_TASKS, "Driver UI has no authorized manual location-upload control")
            stage["dispatch_status"] = "PASS"
            stage["last_verified"] = "DISPATCHED committed; GPS update unavailable"
            page.screenshot(path=output / f"t27-driver-{trip_id}-gps-blocked.png")
        else:
            stage["next_check"] = "Verify location POST and mandatory POD separately against R3 contract"
            stage["dispatch_status"] = "PASS"
        return stage
    except (AssertionError, BrowserTimeout, Error, KeyError, ValueError) as exc:
        _failed(stage, ["T06", "T16"], exc)
        return stage
    finally:
        page.close()


def _cs_lookup(
    browser: Browser, web: str, api: str, order_no: str, password: str, output: Path
) -> dict[str, object]:
    stage: dict[str, object] = {"order_no": order_no, "status": "NOT VERIFIED", "http": []}
    page: Page = browser.new_page(
        timezone_id=TIME_ZONE, viewport={"width": 1440, "height": 1000}, service_workers="block"
    )
    page.set_default_timeout(15_000)
    observed: dict[str, Response] = {}

    def capture(response: Response) -> None:
        # Record only endpoint objects, never tokens, addresses or raw payloads.
        path = urlsplit(response.url).path
        if response.request.method == "GET" and path.startswith("/api/v1/orders/"):
            observed[path] = response

    page.on("response", capture)
    try:
        page.goto(f"{web}/login")
        page.locator('input[type="email"]').fill(CS_ACCOUNT)
        page.get_by_label("Password", exact=True).fill(password)
        with page.expect_response(lambda r: response_for(r, "POST", f"{api}/api/v1/auth/login")) as login:
            page.get_by_role("button", name="Sign in", exact=True).click()
        stage["http"].append(_metadata(login.value))
        require_ok(login.value)
        assert login.value.json()["user"]["roles"] == ["customer_service"]

        page.goto(f"{web}/cs/orders")
        page.get_by_role("searchbox", name="Search orders").fill(order_no)
        with page.expect_response(
            lambda r: r.request.method == "GET"
            and urlsplit(r.url).path == "/api/v1/orders"
            and "q=" in urlsplit(r.url).query
        ) as listing:
            page.get_by_role("button", name="Search", exact=True).click()
        stage["http"].append(_metadata(listing.value))
        require_ok(listing.value)
        items = listing.value.json()["items"]
        target = [item for item in items if item.get("order_no") == order_no]
        assert len(target) == 1
        order_id = target[0]["id"]
        stage["order_id"] = order_id
        detail_path = f"/api/v1/orders/{order_id}"
        eta_path = f"/api/v1/orders/{order_id}/eta-forecasts"
        page.get_by_role("button", name=re.compile(re.escape(order_no))).click()
        # Validate what is actually painted in the CS panel, then independently
        # compare with the real API response captured from this same UI click.
        expect(page.get_by_label("Order details").get_by_text(order_no, exact=True)).to_be_visible(
            timeout=15_000
        )
        details = observed.get(detail_path)
        if details is None:
            raise AssertionError("CS details rendered without an observable live HTTP GET")
        stage["http"].append(_metadata(details))
        require_ok(details)
        detail = details.json()
        assert detail["id"] == order_id and detail["order_no"] == order_no
        stage["status_from_api"] = detail["status"]
        # CS should not receive location/GPS or internal approval scores.
        assert "approved_plan_id" not in detail
        assert "latest_run_id" not in detail
        assert "lat" not in str(detail.get("delivery", {}).keys())
        stage["order_lookup"] = "PASS"
        stage["last_verified"] = "CS UI result and details match real /orders API"
        page.screenshot(path=output / "t27-cs-order-lookup.png")

        # The separate ETA request may finish before the detail GET. A
        # response listener installed before selecting the order captures both.
        eta_response = observed.get(eta_path)
        if eta_response is None:
            stage["eta_history"] = "No ETA history HTTP response observed"
            _block(stage, [ETA_STUB_TASK], "ETA history unavailable; no live HTTP response")
        else:
            stage["http"].append(_metadata(eta_response))
            if not eta_response.ok:
                _block(stage, [ETA_STUB_TASK], "ETA history HTTP error; CS order lookup passed")
            else:
                stage["eta_history"] = "HTTP responded; versioned API/DB rows not yet correlated"
                stage["status"] = "NOT VERIFIED"
        page.screenshot(path=output / "t27-cs-eta-history.png")
        return stage
    except (AssertionError, BrowserTimeout, Error, KeyError, ValueError, TypeError) as exc:
        stage["http"].extend(
            _metadata(response)
            for path, response in observed.items()
            if path not in {str(item["path"]) for item in stage["http"]}
        )
        _failed(stage, ["T03", "T14"], exc)
        page.screenshot(path=output / "t27-cs-last-verified.png")
        return stage
    finally:
        page.close()


def run_driver_cs(
    browser: Browser, web: str, api: str, order_no: str, password: str, trips: int, out: Path, report: dict
) -> None:
    """Continue after all E3 milestones; each browser step is independent."""
    evidence: dict[str, object] = {
        "origin": "APPROVED synthetic E3 fixture (NOT POS/Sales/Approve)",
        "app_now": APP_NOW,
        "market_timezone": TIME_ZONE,
        "driver": [],
        "cs": {},
        "last_verified": "Warehouse LOADED from E3 browser",
    }
    report["t27"] = evidence
    for trip_id in range(1, trips + 1):
        stage = _driver_dispatch(browser, web, api, trip_id, order_no, password, out)
        evidence["driver"].append(stage)
        if stage.get("dispatch_status") == "PASS":
            evidence["last_verified"] = f"Driver DISPATCHED trip {trip_id}"
    evidence["cs"] = _cs_lookup(browser, web, api, order_no, password, out)
    if evidence["cs"].get("order_lookup") == "PASS":
        evidence["last_verified"] = "CS UI order lookup and API detail matched"
