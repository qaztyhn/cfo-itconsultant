"""CI-only isolated demo harness: generates ephemeral credentials, runs Compose, cleans up.

NEVER deploys, sends production notifications or touches a non-cfo-demo-* project.
Successful preflight is NOT a claim that blocked Sales sync/D7 E2E passed.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> str:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return str(listener.getsockname()[1])


def disposable_env() -> dict[str, str]:
    env = dict(os.environ)
    token = secrets.token_urlsafe(24)
    ports = {
        key: free_port() for key in (
            "POSTGRES_PORT", "CFO_API_PORT", "CFO_WEB_PORT",
            "SOURCE_PORT", "MAILPIT_HTTP_PORT", "MAILPIT_SMTP_PORT",
        )
    }
    env.update(ports)
    env.update({
        "APP_ENV": "test",
        "DEMO_DISPOSABLE": "1",
        "APP_NOW": "2026-11-04T10:05:00+01:00",
        "COMPOSE_PROJECT_NAME": "cfo-demo-ci-" + secrets.token_hex(4),
        "POSTGRES_PASSWORD": token,
        "DATABASE_URL": f"postgresql+asyncpg://cfo:{token}@postgres:5432/cfo",
        "SOURCE_SE_DATABASE_URL": f"postgresql+asyncpg://cfo:{token}@postgres:5432/source_se",
        "SOURCE_SE_API_KEY": secrets.token_urlsafe(24),
        "JWT_SECRET": secrets.token_urlsafe(32),
        "INTERNAL_TICK_KEY": secrets.token_urlsafe(24),
        "SEED_DEMO_PASSWORD": secrets.token_urlsafe(24),
        "SOURCE_DB_NAME": "source_se",
        "SOURCE_SCHEMA": "src_se",
        "SOURCE_SE_BASE_URL": "http://source-se:8100/api/v1",
        "VITE_API_URL": f"http://127.0.0.1:{ports['CFO_API_PORT']}/api/v1",
        "CORS_ORIGINS": json.dumps([f"http://127.0.0.1:{ports['CFO_WEB_PORT']}"]),
    })
    return env


def check_report(path: Path, *, mutating: bool) -> bool:
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        checks = {item["check"]: item["status"] for item in data["checks"]}
    except (OSError, ValueError, KeyError, TypeError):
        return False
    required = (
        "source_db", "cfo_db", "frontend_http", "source_auth_negative",
        "source_fixture", "source_read_repeat", "cfo_auth_negative",
        "role_sales", "role_dispatcher", "role_warehouse", "role_driver",
        "sales_orders_read", "dispatcher_orders_read",
    )
    if any(checks.get(item) != "PASS" for item in required):
        return False
    if not mutating:
        return checks.get("sales_sync_write") == "NOT VERIFIED"
    if checks.get("sales_sync_write") == "BLOCKED":
        return checks.get("planning_approval") == "BLOCKED"
    return all(checks.get(item) == "PASS" for item in (
        "sales_sync_write", "sync_idempotent", "sales_order_visible",
        "dispatcher_order_visible", "unmapped_legacy_negative",
    )) and checks.get("planning_run") in ("PASS", "BLOCKED")


def check_db_report(sync_path: Path, db_path: Path) -> bool:
    """A blocked preflight remains blocked; a routed order MUST have DB proof."""
    try:
        sync = json.loads(sync_path.read_text(encoding="utf-8"))
        proof = json.loads(db_path.read_text(encoding="utf-8"))
        if sync.get("schema") != "demo-smoke-v1" or proof.get("schema") != "demo-db-proof-v1":
            return False
        statuses = {item["check"]: item["status"] for item in sync["checks"]}
        db_statuses = {item["check"]: item["status"] for item in proof["checks"]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    if statuses.get("sales_sync_write") == "BLOCKED":
        return db_statuses.get("postgres_once") == "BLOCKED" and db_statuses.get("postgres_legacy_negative") == "NOT VERIFIED"
    if statuses.get("sales_sync_write") == "PASS":
        return all(db_statuses.get(key) == "PASS" for key in ("postgres_once", "postgres_legacy_negative"))
    return False


def cli() -> int:
    if not shutil_which("docker") or not shutil_which("bash"):
        print("BLOCKED: this harness requires Docker Compose and bash.")
        return 2
    env = disposable_env()
    print("Starting a uniquely named disposable local Compose demo; no secrets shown.")
    def call(args: list[str]) -> int:
        return subprocess.run(args, env=env, cwd=ROOT, check=False).returncode

    try:
        if call(["bash", "tools/demo_setup.sh"]) != 0:
            print("FAIL: synthetic demo setup did not complete.")
            return 1
        # Compose --wait checks health only where a healthcheck exists. The
        # Vite dev container has none; require a REAL HTTP response before
        # running the smoke rather than classifying a startup race as failure.
        web_url = f"http://127.0.0.1:{env['CFO_WEB_PORT']}/"
        ready = False
        for _ in range(45):
            try:
                with urlopen(web_url, timeout=3) as response:
                    ready = response.status == 200
                if ready:
                    break
            except (URLError, OSError, TimeoutError):
                pass
            time.sleep(2)
        if not ready:
            print("FAIL: the real Vite frontend did not serve HTTP 200 in the disposable environment.")
            return 1
        base = [
            sys.executable, "tools/demo_smoke.py",
            "--source-url", f"http://127.0.0.1:{env['SOURCE_PORT']}/api/v1",
            "--cfo-url", f"http://127.0.0.1:{env['CFO_API_PORT']}/api/v1",
            "--web-url", f"http://127.0.0.1:{env['CFO_WEB_PORT']}",
        ]
        read_report = ROOT / "demo-ci-read-results.json"
        sync_report = ROOT / "demo-ci-sync-results.json"
        if call(base + ["--report", str(read_report)]) not in (0, 2) or not check_report(read_report, mutating=False):
            print("FAIL: real-HTTP read-only demonstration did not match expected contracts.")
            return 1
        # The real login limiter allows five attempts/minute per IP. The
        # read-only smoke already authenticated four roles; wait for the
        # complete window before the second smoke instead of disabling,
        # bypassing or resetting the security limiter.
        print("Respecting the 60-second authentication rate-limit window between probes.")
        time.sleep(61)
        if call(base + ["--exercise-sync", "--report", str(sync_report)]) not in (0, 2):
            print("FAIL: real-HTTP Sales Sync & Check was not safely classified.")
            return 1
        if not check_report(sync_report, mutating=True):
            print("FAIL: Source->CFO smoke has an unexpected error, do not report E2E PASS.")
            return 1
        db_report = ROOT / "demo-ci-db-results.json"
        db_rc = call([
            sys.executable, "tools/demo_db_verify.py",
            "--source-url", f"http://127.0.0.1:{env['SOURCE_PORT']}/api/v1",
            "--sync-report", str(sync_report),
            "--report", str(db_report),
        ])
        if db_rc not in (0, 2) or not check_db_report(sync_report, db_report):
            print("FAIL: Source->CFO PostgreSQL exact-once/legacy evidence failed or was bypassed.")
            return 1
        print("PASS: disposable Source/CFO/frontend preflight and negative authentication checks.")
        print("DATABASE RESULT: see demo-ci-db-results.json; blocked routing is NOT verified uniqueness.")
        print("INTEGRATION RESULT: see safe demo-ci-sync-results.json; BLOCKED != E2E PASS.")
        return 0
    finally:
        # Only the generated, isolated cfo-demo-ci-* project is eligible.
        call(["bash", "tools/demo_reset.sh", "--confirm-disposable-data-loss"])


def shutil_which(command: str) -> str | None:
    from shutil import which

    return which(command)


if __name__ == "__main__":
    raise SystemExit(cli())
