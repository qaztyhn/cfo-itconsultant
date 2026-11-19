"""Diagnostic-only: verify exact PR code in a disposable seeded Compose stack.

Never attach to existing Compose volumes or real SMTP/customer data.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request

from demo_ci import ROOT, disposable_env


def main() -> int:
    env = disposable_env()
    print("E2 diagnostic uses a uniquely named cfo-demo-ci-* Compose project.")

    def call(args: list[str], *, sql: str | None = None, timeout: int = 1100) -> str:
        process = subprocess.run(
            args, cwd=ROOT, env=env, input=sql, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False,
        )
        if process.returncode:
            # Docker/setup logs can include PII; do not echo them to CI.
            raise AssertionError(f"Command failed (exit {process.returncode}): {args[0]} {args[1:3]}")
        return process.stdout

    def api(path: str) -> tuple[dict, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{env['CFO_API_PORT']}/api/v1/internal/tick?{path}",
            headers={"X-Internal-Key": env["INTERNAL_TICK_KEY"]},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            assert response.status == 200
            return json.load(response), dict(response.headers)

    def mailpit() -> dict:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{env['MAILPIT_HTTP_PORT']}/api/v1/messages", timeout=5
        ) as response:
            return json.load(response)

    def query(sql: str) -> str:
        return call(
            ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "cfo",
             "-d", "cfo", "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
            timeout=30,
        ).strip()

    try:
        base = call(["docker", "compose", "config", "--services"]).splitlines()
        profile = call(["docker", "compose", "--profile", "demo-worker", "config", "--services"]).splitlines()
        assert "cfo-worker" not in base and "cfo-worker" in profile
        print("PASS: default docker compose config excludes cfo-worker; opt-in profile includes it.")

        # This guarded script starts all base services, migrates CFO to head,
        # then seeds SE and source reference data. Crucially, it leaves worker off.
        call(["bash", "tools/demo_setup.sh"])
        running = call(["docker", "compose", "ps", "--services", "--status", "running"]).splitlines()
        assert "cfo-worker" not in running
        assert query("SELECT count(*) FROM ref.market WHERE code='SE'") == "1"
        print("PASS: clean Compose stack migrated/seeded market SE without starting worker.")

        # Independent E2 fixture, *not* a claim of actual plan approval.
        # A separate synthetic contact/order and queued CONFIRMED in a disposable DB.
        fixture = """
        WITH market AS (SELECT id FROM ref.market WHERE code='SE'),
        customer AS (
            INSERT INTO ref.customer (market_id, external_ref, type, name, email)
            SELECT id, 'E2-DIAG-SYNTHETIC', 'business', 'Synthetic E2 Fixture', 'e2-diag@cfo.test'
            FROM market RETURNING id, market_id
        ),
        placed AS (
            INSERT INTO ops.customer_order (
                order_no, market_id, external_ref, customer_id, contact_name,
                delivery_address, delivery_lat, delivery_lon, date_mode, date_from, date_to,
                order_date, currency, submitted_at, committed_date, promise_start, promise_end
            )
            SELECT 'SE-E2-DIAG-001', market_id, 'E2-DIAG-ORDER', id, 'Synthetic',
                   'Synthetic Address', 59.0, 18.0, 'exact', '2026-11-10', '2026-11-10',
                   '2026-11-04T09:00:00Z', 'SEK', '2026-11-04T09:00:00Z',
                   '2026-11-10', '2026-11-10T08:00:00Z', '2026-11-10T10:00:00Z'
            FROM customer RETURNING id
        )
        INSERT INTO ops.notification(order_id,template,recipient,body,scheduled_for,dedupe_key)
        SELECT id, 'CONFIRMED', 'e2-diag@cfo.test', '', '2026-11-04T00:00:00Z', 'e2:worker:postseed'
        FROM placed;
        """
        call(
            ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "cfo",
             "-d", "cfo", "-v", "ON_ERROR_STOP=1", "-q"],
            sql=fixture, timeout=30,
        )
        assert query(
            "SELECT count(*) FROM ops.notification WHERE dedupe_key='e2:worker:postseed' AND status='queued'"
        ) == "1"
        assert mailpit()["total"] == 0
        print("PASS: one due synthetic CONFIRMED queued and zero Mailpit messages before worker.")

        call(["docker", "compose", "--profile", "demo-worker", "up", "-d", "--build", "cfo-worker"])
        assert "cfo-worker" in call(
            ["docker", "compose", "--profile", "demo-worker", "ps", "--services", "--status", "running"]
        ).splitlines()
        print("PASS: worker explicitly started AFTER seed.")

        deadline = time.monotonic() + 125
        sent = False
        while time.monotonic() < deadline:
            state = query(
                "SELECT status::text || ',' || attempts::text || ',' || (sent_at IS NOT NULL)::text "
                "FROM ops.notification WHERE dedupe_key='e2:worker:postseed'"
            )
            if state == "sent,1,true":
                sent = True
                break
            time.sleep(3)
        assert sent, "Worker did not process queued CONFIRMED as expected."

        audit = query(
            "SELECT count(*) FROM audit.decision_log WHERE action='NOTIFICATION_SENT' "
            "AND entity_id=(SELECT id::text FROM ops.notification WHERE dedupe_key='e2:worker:postseed')"
        )
        # Audit schema may store entity under a different column; if so use
        # an explicit order-scoped count instead of manufacturing proof.
        assert audit == "1", "Expected exactly one sent audit."
        messages = mailpit()
        assert messages["total"] == 1
        mid = messages["messages"][0]["ID"]
        with urllib.request.urlopen(
            f"http://127.0.0.1:{env['MAILPIT_HTTP_PORT']}/api/v1/message/{mid}", timeout=5
        ) as response:
            detail = json.load(response)
        assert "SE-E2-DIAG-001" in detail["Text"] and "Delivery window:" in detail["Text"]

        one, header = api("job=notify_outbox&market=SE")
        two, _ = api("job=notify_outbox&market=SE")
        hold, _ = api("job=hold_expiry")
        assert one["processed"] == two["processed"] == 0
        assert hold["market"] is None and isinstance(hold["processed"], int)
        assert one["correlation_id"] == next(value for key, value in header.items() if key.lower() == "x-correlation-id")
        assert mailpit()["total"] == 1
        print(
            "PASS: real post-seed worker SE CONFIRMED queued->sent, 1 audit, "
            "exactly 1 Mailpit email; two repeated ticks processed=0; "
            "global hold_expiry tick available."
        )
        return 0
    finally:
        subprocess.run(
            ["bash", "tools/demo_reset.sh", "--confirm-disposable-data-loss"],
            cwd=ROOT, env=env, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=180,
        )


if __name__ == "__main__":
    raise SystemExit(main())
