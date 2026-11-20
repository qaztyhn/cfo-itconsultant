"""Independent real Chrome E5 draft -> queued -> worker/Mailpit acceptance.

Only a *fixture-created* DELAY draft is exercised here. This test does NOT
establish that T08 generated a draft from a live PREDICTED_LATE alert.
Never run outside the isolated cfo-demo-e5 Compose project.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8004/api/v1"
WEB = "http://localhost:5174"
MAILPIT = "http://127.0.0.1:8027"
NOW = "2026-11-09T11:00:00+01:00"
ORDER_NO = "ZZ-000001"
SUBJECT = f"Delivery update for order {ORDER_NO}"
START = "2026-11-10T09:00+01:00"
END = "2026-11-10T11:00+01:00"
COMPOSE = ["docker", "compose", "--env-file", str(ROOT / ".env"), "-p", "cfo-demo-e5"]


def compose(*args: str) -> str:
    proc = subprocess.run(
        [*COMPOSE, *args], cwd=ROOT, env=os.environ, capture_output=True,
        text=True, check=False, timeout=140,
    )
    if proc.returncode != 0:
        raise RuntimeError("Disposable E5 Compose command failed")
    return proc.stdout.strip()


def sql(statement: str) -> str:
    # Only synthetic IDs and statuses. No customer details/coordinates/passwords.
    return compose(
        "exec", "-T", "postgres", "psql", "-U", "cfo", "-d", "cfo",
        "-v", "ON_ERROR_STOP=1", "-Atc", statement,
    )


def ready(path: str) -> None:
    for _ in range(60):
        try:
            response = httpx.get(path, timeout=2, trust_env=False)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("Disposable HTTP app not ready")


def click_send(out: Path) -> dict[str, object]:
    password = os.getenv("SEED_DEMO_PASSWORD")
    if not password:
        raise RuntimeError("Private demo password missing")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        try:
            page = browser.new_page(
                timezone_id="Europe/Stockholm", viewport={"width": 1280, "height": 900},
                service_workers="block",
            )
            page.set_default_timeout(15_000)
            page.clock.install(time=datetime.fromisoformat(NOW))
            page.goto(WEB + "/login")
            page.locator('input[type="email"]').fill("user1@cfo.test")
            page.get_by_label("Password", exact=True).fill(password)
            with page.expect_response(
                lambda r: r.request.method == "POST"
                and urlsplit(r.url).path == "/api/v1/auth/login"
            ) as auth:
                page.get_by_role("button", name="Sign in", exact=True).click()
            if auth.value.status != 200:
                raise RuntimeError("Synthetic E5 login rejected")
            page.goto(WEB + "/notifications?order_id=1")
            expect(page.get_by_text("Saved preview window:", exact=False)).to_be_visible()
            expect(page.get_by_text(ORDER_NO, exact=False).first).to_be_visible()
            expect(page.get_by_text("Times in Europe/Stockholm")).to_be_visible()
            out.mkdir(parents=True, exist_ok=False)
            page.locator("main").first.screenshot(path=out / "e5-01-draft.png")
            with page.expect_response(
                lambda r: r.request.method == "POST"
                and urlsplit(r.url).path == "/api/v1/notifications/1/send"
            ) as posted:
                page.get_by_role("button", name="Send", exact=True).click()
            sent = posted.value
            if sent.status != 200 or sent.json().get("status") != "queued":
                error_code = sent.json().get("error", {}).get("code") if not sent.ok else None
                raise RuntimeError(f"DELAY Send HTTP {sent.status} code {error_code}")
            expect(page.get_by_text("Queued for delivery.", exact=False)).to_be_visible()
            page.locator("main").first.screenshot(path=out / "e5-02-queued.png")
            return {"post_status": sent.status, "notification_id": 1}
        finally:
            browser.close()


def confirm_outbox() -> dict[str, object]:
    before = sql(
        "SELECT id||'|'||status||'|'||attempts FROM ops.notification "
        "WHERE id=1 AND order_id=1 AND template='DELAY'"
    )
    if before != "1|queued|0":
        raise RuntimeError("E5 Send failed to commit one queued DELAY")
    if sql("SELECT count(*) FROM ops.notification") != "1":
        raise RuntimeError("E5 fixture produced unexpected notification rows")
    compose("--profile", "demo-worker", "up", "-d", "--build", "cfo-worker")
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        record = sql(
            "SELECT status||'|'||attempts||'|'||(sent_at IS NOT NULL)::text "
            "FROM ops.notification WHERE id=1 AND order_id=1 AND template='DELAY'"
        )
        if record == "sent|1|true":
            break
        if record.startswith(("failed|", "suppressed|")):
            raise RuntimeError("E5 worker did not send the DELAY notification")
        time.sleep(2)
    else:
        raise RuntimeError("E5 notification was not sent within the bounded worker run")
    if sql(
        "SELECT count(*) FROM audit.decision_log WHERE "
        "action='NOTIFICATION_SENT' AND order_id=1 AND entity_id='1'"
    ) != "1":
        raise RuntimeError("E5 sent audit count did not equal one")
    if sql(
        "SELECT count(*) FROM ops.notification WHERE order_id=1 AND "
        "template='DELAY' AND status='sent' AND attempts=1"
    ) != "1":
        raise RuntimeError("E5 PostgreSQL sent notification count did not equal one")
    api_response = httpx.get(MAILPIT + "/api/v1/messages", timeout=8, trust_env=False)
    if api_response.status_code != 200:
        raise RuntimeError("E5 Mailpit API is unavailable")
    messages = api_response.json().get("messages") or []
    matching = [row for row in messages if row.get("Subject") == SUBJECT]
    if len(matching) != 1 or len(messages) != 1:
        raise RuntimeError("E5 Mailpit does not hold exactly one DELAY email")
    message_id = matching[0].get("ID")
    detail = httpx.get(MAILPIT + "/api/v1/message/" + str(message_id), timeout=8, trust_env=False)
    if detail.status_code != 200:
        raise RuntimeError("E5 Mailpit message detail unavailable")
    body = detail.json().get("Text", "")
    if (
        f"Order {ORDER_NO}: Delivery timing has changed." not in body
        or f"Delivery window: {START} – {END}." not in body
    ):
        raise RuntimeError("E5 message did not match the synthetic order/approved ETA")
    return {"db_status": "sent", "attempts": 1, "sent_audits": 1,
            "mailpit_count": 1, "mailpit_message_id": message_id,
            "expected_window": [START, END]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    allowed = (
        os.getenv("APP_ENV") == "test"
        and os.getenv("DEMO_DISPOSABLE") == "1"
        and os.getenv("COMPOSE_PROJECT_NAME") == "cfo-demo-e5"
        and os.getenv("APP_NOW") == NOW
        and os.getenv("POSTGRES_PORT") == "5434"
    )
    if not allowed or not (ROOT / ".env").exists():
        parser.error("Requires exact isolated cfo-demo-e5 environment")
    if sql("SELECT id||'|'||status FROM ops.notification WHERE id=1") != "1|draft":
        parser.error("A fresh E5 fixture DELAY draft is required")
    ready(API + "/health")
    ready(WEB)
    result = {
        "git_sha": os.getenv("GITHUB_SHA", "NOT VERIFIED (local)"),
        "fixture": "E5 explicit create_delay_draft on synthetic approved order",
        "origin": "fixture, NOT an actual T08 PREDICTED_LATE risk event",
        "app_now": NOW, "timezone": "Europe/Stockholm",
        "order_no": ORDER_NO, "template": "DELAY",
        "risk_generated_draft": "NOT VERIFIED",
    }
    result["ui"] = click_send(args.output)
    result["worker_mailpit"] = confirm_outbox()
    result["fixture_send_to_mailpit"] = "PASS"
    (args.output / "e5-synthetic-evidence.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print("E5 separate fixture: real Chrome Send HTTP200, PostgreSQL sent, "
          "one Mailpit email, same notification ID. Risk-generated draft NOT VERIFIED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
