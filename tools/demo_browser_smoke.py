"""Read-only browser evidence plus guarded planning attempt on the disposable CFO demo.

Invoked from demo_ci.py only after Source sync and PostgreSQL verification.
Never infers success from HTTP 200 for Vite, invents a run ID, or clicks Approve.
Screenshots and JSON contain synthetic demo UI only, not credentials or tokens.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from demo_smoke import APP_NOW, allow_mutation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo-browser-evidence"


def safe_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"} and parsed.username is None


def check_environment() -> tuple[str, str] | None:
    env = os.environ
    web = "http://127.0.0.1:" + env.get("CFO_WEB_PORT", "")
    api = "http://127.0.0.1:" + env.get("CFO_API_PORT", "") + "/api/v1"
    source = "http://127.0.0.1:" + env.get("SOURCE_PORT", "") + "/api/v1"
    if not all(safe_url(url) for url in (web, api, source)):
        return None
    if not allow_mutation(env, [web, api, source]) or env.get("APP_NOW") != APP_NOW:
        return None
    if env.get("VITE_USE_MOCKS") == "true" or not env.get("SEED_DEMO_PASSWORD"):
        return None
    if not env.get("COMPOSE_PROJECT_NAME", "").startswith("cfo-demo-ci-"):
        return None
    return web, api


def responses(driver: webdriver.Chrome, api: str) -> list[dict[str, object]]:
    observed: list[dict[str, object]] = []
    for item in driver.get_log("performance"):
        try:
            message = json.loads(item["message"])["message"]
            if message["method"] != "Network.responseReceived":
                continue
            params = message["params"]
            response = params["response"]
            url = response["url"]
            if not url.startswith(api + "/"):
                continue
            path = urlsplit(url).path
            # Save only endpoint names/status; never response bodies or auth headers.
            if path.endswith("/plan") or "/planning-runs/" in path or path.endswith("/auth/login") or path.endswith("/orders"):
                observed.append({"path": path, "status": int(response["status"]), "request_id": params["requestId"]})
        except (ValueError, KeyError, TypeError):
            continue
    return observed


def report(checks: list[dict[str, str]], http: list[dict[str, object]], result: str) -> None:
    OUT.mkdir(exist_ok=True)
    safe_http = [{"path": row["path"], "status": row["status"]} for row in http]
    (OUT / "status.json").write_text(json.dumps({
        "schema": "demo-browser-p0-v1", "result": result,
        "checks": checks, "http": safe_http,
        "browser_verified": result in ("BLOCKED_RESOURCE_CONFLICT", "PLAN_CREATED"),
        "approval_verified": False, "wms_verified": False,
    }, indent=2), encoding="utf-8")
    for check in checks:
        print(f"{check['status']:<12} {check['name']}: {check['detail']}")
    print(f"BROWSER RESULT: {result}; approval/WMS E2E NOT VERIFIED.")


def main() -> int:
    config = check_environment()
    if config is None:
        print("FAIL: browser smoke requires exactly the guarded disposable localhost environment.")
        return 1
    web, api = config
    OUT.mkdir(exist_ok=True)
    checks: list[dict[str, str]] = []
    observed: list[dict[str, object]] = []
    browser: webdriver.Chrome | None = None

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,900")
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        browser = webdriver.Chrome(options=options)
        browser.execute_cdp_cmd("Network.enable", {})
        wait = WebDriverWait(browser, 35)

        browser.get(web + "/login")
        wait.until(lambda d: d.find_element(By.CSS_SELECTOR, '[data-screen="SignIn"]'))
        browser.save_screenshot(str(OUT / "01-dispatcher-login.png"))
        email = browser.find_element(By.ID, "signin-email")
        password = browser.find_element(By.ID, "signin-password")
        email.send_keys("dispatcher@cfo.demo")
        password.send_keys(os.environ["SEED_DEMO_PASSWORD"])
        browser.find_element(By.CSS_SELECTOR, 'form button[type="submit"]').click()
        wait.until(lambda d: "/dispatcher/orders" in urlsplit(d.current_url).path)
        wait.until(lambda d: d.find_element(By.CSS_SELECTOR, '[data-screen="OrderQueue"]'))
        add("dispatcher_login", "PASS", "Real browser login redirected to Dispatcher Order Queue.")

        # The Source reference is not the CFO-generated order number shown
        # in the Queue. The preceding real PostgreSQL verifier established
        # Source-to-CFO routing; select only its current SUBMITTED queue row.
        buttons = wait.until(lambda d: d.find_elements(
            By.CSS_SELECTOR, 'table button[aria-label^="Run planning for order"]',
        ))
        if len(buttons) != 1:
            add("queue_order", "NOT VERIFIED", "Expected one SUBMITTED CFO queue action in this disposable slice.")
            report(checks, observed, "NOT_VERIFIED")
            return 2
        button = buttons[0]
        row = button.find_element(By.XPATH, "./ancestor::tr")
        if "SUBMITTED" not in row.text:
            add("queue_order", "NOT VERIFIED", "Visible CFO order is not SUBMITTED.")
            report(checks, observed, "NOT_VERIFIED")
            return 2
        add("synced_order_visible", "PASS", "One current SUBMITTED CFO order displayed; Source routing separately verified in PostgreSQL.")
        browser.save_screenshot(str(OUT / "02-dispatcher-order-queue.png"))

        button.click()
        def finished(d: webdriver.Chrome) -> bool:
            if re.search(r"/dispatcher/plan-review/\d+$", urlsplit(d.current_url).path):
                return True
            return any("RESOURCE_CONFLICT" in item.text for item in d.find_elements(By.CSS_SELECTOR, '[role="alert"]'))
        wait.until(finished)
        browser.save_screenshot(str(OUT / "03-planning-result.png"))

        observed.extend(responses(browser, api))
        plan_http = [entry for entry in observed if str(entry["path"]).endswith("/plan")]
        if not plan_http:
            add("planning_http", "NOT VERIFIED", "No browser planning HTTP response captured.")
            report(checks, observed, "NOT_VERIFIED")
            return 2
        latest = plan_http[-1]
        status = latest["status"]
        if status == 409:
            alerts = [item.text for item in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')]
            if not any("RESOURCE_CONFLICT" in value for value in alerts):
                add("planning_conflict", "FAIL", "HTTP 409 not accurately shown to Dispatcher.")
                report(checks, observed, "FAIL")
                return 1
            if "/dispatcher/plan-review/" in urlsplit(browser.current_url).path:
                add("planning_conflict", "FAIL", "Blocked planning unexpectedly navigated to a run.")
                report(checks, observed, "FAIL")
                return 1
            add("planning_conflict", "PASS", "Real HTTP 409 RESOURCE_CONFLICT displayed; no fabricated planning run.")
            result = "BLOCKED_RESOURCE_CONFLICT"
        elif status == 200:
            route = re.search(r"/dispatcher/plan-review/(\d+)$", urlsplit(browser.current_url).path)
            if not route:
                add("planning_run", "NOT VERIFIED", "HTTP 200 did not navigate to a planning-run detail.")
                report(checks, observed, "NOT_VERIFIED")
                return 2
            # Compare the rendered URL to the exact server-issued POST response ID.
            try:
                response = browser.execute_cdp_cmd("Network.getResponseBody", {"requestId": latest["request_id"]})
                body = response["body"]
                if response.get("base64Encoded"):
                    body = base64.b64decode(body).decode("utf-8")
                run_id = json.loads(body)["id"]
            except (KeyError, ValueError, TypeError):
                run_id = None
            if type(run_id) is not int or run_id <= 0 or str(run_id) != route.group(1):
                add("server_run_id", "FAIL", "Route does not match a verified server-issued run ID.")
                report(checks, observed, "FAIL")
                return 1
            wait.until(lambda d: d.find_element(By.CSS_SELECTOR, '[data-screen="PlanReview"]'))
            add("server_run_id", "PASS", "Browser opened the exact backend-issued run ID.")
            browser.save_screenshot(str(OUT / "04-server-run-plan-review.png"))
            observed.extend(responses(browser, api))
            result = "PLAN_CREATED"
        else:
            add("planning_http", "NOT VERIFIED", f"Unexpected real planning HTTP {status}.")
            report(checks, observed, "NOT_VERIFIED")
            return 2

        if "CFO reports APPROVED" in browser.page_source:
            add("approval_safety", "FAIL", "UI incorrectly presented APPROVED without an approval request.")
            report(checks, observed, "FAIL")
            return 1
        add("approval_safety", "PASS", "No APPROVED/WMS success presented from planning alone.")

        browser.set_window_size(390, 844)
        browser.save_screenshot(str(OUT / "05-dispatcher-mobile.png"))
        add("mobile", "PASS", "Mobile viewport captured from the running real API frontend.")
        report(checks, observed, result)
        return 0
    except Exception as error:
        # Do not leak passwords, URLs with tokens, source rows, or raw HTTP payloads.
        add("browser", "NOT VERIFIED", f"Browser test could not complete ({type(error).__name__}).")
        if browser is not None:
            try:
                browser.save_screenshot(str(OUT / "browser-incomplete.png"))
            except Exception:
                pass
        report(checks, observed, "NOT_VERIFIED")
        return 2
    finally:
        if browser is not None:
            browser.quit()


if __name__ == "__main__":
    sys.exit(main())
