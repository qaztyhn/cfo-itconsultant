"""Prepare and verify E0-04 on a NEW disposable Compose project.

Run from the repository root after creating private .env. Never targets a
non-demo project, resets a database, prints secrets or approves a plan.
"""

import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine.url import make_url

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "cfo-demo-e004"
BASE_NOW = "2026-11-04T10:05:00+01:00"
E0_NOW = "2026-12-01T10:05:00+01:00"
REF = "SE-2026-000249"
COMPOSE = ["docker", "compose", "--env-file", str(ROOT / ".env"), "-p", PROJECT]


def execute(command: list[str], env: dict[str, str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode:
        raise RuntimeError(
            f"Step failed (exit {result.returncode}): {command[0]} {command[1] if len(command)>1 else ''}"
        )
    return (result.stdout or "").strip()


def compose(env: dict[str, str], *args: str, capture: bool = False) -> str:
    return execute([*COMPOSE, *args], env, capture=capture)


def sql(env: dict[str, str], query: str) -> str:
    return compose(
        env,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "cfo",
        "-d",
        "cfo",
        "-Atc",
        query,
        capture=True,
    )


def main() -> int:
    values = dotenv_values(ROOT / ".env")
    base = {**os.environ, **{k: v for k, v in values.items() if v is not None}}
    if base.get("APP_ENV") != "test" or base.get("DEMO_DISPOSABLE") != "1":
        print("BLOCKED: private .env must explicitly mark a disposable test demo")
        return 2
    base.update(
        APP_NOW=BASE_NOW,
        COMPOSE_PROJECT_NAME=PROJECT,
    )
    if not all(
        base.get(k)
        for k in (
            "POSTGRES_PASSWORD",
            "DATABASE_URL",
            "SOURCE_SE_DATABASE_URL",
            "SOURCE_SE_API_KEY",
            "JWT_SECRET",
            "SEED_DEMO_PASSWORD",
            "INTERNAL_TICK_KEY",
        )
    ):
        print("BLOCKED: private .env is missing required demo keys")
        return 2
    try:
        cfo_url = make_url(base["DATABASE_URL"])
        source_url = make_url(base["SOURCE_SE_DATABASE_URL"])
    except ValueError:
        print("BLOCKED: invalid private demo database URLs")
        return 2
    if (cfo_url.host, cfo_url.database, source_url.host, source_url.database) != (
        "postgres",
        "cfo",
        "postgres",
        "source_se",
    ):
        print(
            "BLOCKED: demo database URLs must target only local Compose cfo/source_se"
        )
        return 2
    if datetime.now(UTC) >= datetime.fromisoformat(E0_NOW).astimezone(UTC):
        print(
            "BLOCKED: fixed E0-04 demo instant is now past; choose a reviewed future clock"
        )
        return 2
    bash = (
        Path(r"C:\Program Files\Git\bin\bash.exe")
        if os.name == "nt"
        else Path(shutil.which("bash") or "")
    )
    if not bash.is_file():
        print("BLOCKED: Git Bash or a POSIX bash is required for base demo setup")
        return 2
    base["MSYS_NO_PATHCONV"] = "1"
    try:
        if compose(base, "ps", "-q", capture=True):
            raise RuntimeError(
                "cfo-demo-e004 already has containers; reset only this disposable project first"
            )
        execute([str(bash), "tools/demo_setup.sh"], base)
        if (
            sql(base, "SELECT count(*) FROM ref.stock_admin_grant") != "0"
            or sql(base, "SELECT count(*) FROM ops.stock_scope_version") != "0"
        ):
            raise RuntimeError(
                "Existing stock governance state; use a freshly reset disposable project"
            )
        compose(
            base,
            "exec",
            "-T",
            "-e",
            "APP_NOW=",
            "-e",
            "DEMO_DISPOSABLE=1",
            "cfo-api",
            "python",
            "-m",
            "scripts.provision_stock_demo_admins",
            "--execute",
        )
        ids = sql(
            base,
            "SELECT u.id || ':' || e.employee_no FROM ref.app_user u JOIN hr.employee e ON e.id=u.employee_id "
            "WHERE e.employee_no IN ('DEMO-ADMIN','DEMO-STOCKOPERATOR','DEMO-STOCKAPPROVER') ORDER BY u.id",
        )
        if ids.splitlines() != [
            "2:DEMO-ADMIN",
            "131:DEMO-STOCKOPERATOR",
            "132:DEMO-STOCKAPPROVER",
        ]:
            raise RuntimeError("Dedicated stock admin IDs differ from reviewed fixture")
        delegated = [
            "-e",
            "APP_NOW=",
            "-e",
            "DEMO_DISPOSABLE=1",
            "-e",
            "STOCK_GRANT_SYSTEM_ADMIN_USER_ID=131",
            "-e",
            "STOCK_GRANT_AUTHORIZED_MARKET=SE",
            "-e",
            "STOCK_GRANT_OWNER_AUTHORIZATION_REF=E0-04-user-request-2026-11-19",
        ]
        for recipient, expected in (("2", "0"), ("132", "1")):
            compose(
                base,
                "exec",
                "-T",
                *delegated,
                "cfo-api",
                "python",
                "-m",
                "scripts.bootstrap_stock_grant",
                "--market",
                "SE",
                "--operator-id",
                "131",
                "--recipient-id",
                recipient,
                "--capability",
                "scope",
                "--reason",
                f"E0-04-disposable-scope-{recipient}",
                "--expected-grants",
                expected,
                "--execute",
            )
        scope = [
            "exec",
            "-T",
            "-e",
            "APP_NOW=",
            "-e",
            "DEMO_DISPOSABLE=1",
            "cfo-api",
            "python",
            "-m",
            "scripts.manage_stock_demo_scope",
        ]
        compose(
            base,
            *scope,
            "--market",
            "SE",
            "--actor-id",
            "2",
            "--execute",
            "create",
            "--sku",
            "SE-BRD-GYP-13",
            "--warehouse-id",
            "6",
            "--warehouse-id",
            "7",
            "--warehouse-id",
            "8",
            "--reason",
            "E0-04-disposable-order-scope",
        )
        compose(
            base,
            *scope,
            "--market",
            "SE",
            "--actor-id",
            "132",
            "--execute",
            "approve",
            "--scope-id",
            "1",
        )
        execute([sys.executable, "tools/e0_04_d7_fixture.py"], base)
        future = {**base, "APP_NOW": E0_NOW, "DEMO_D7_FIXTURE_DIR": "/srv/e0_04_d7"}
        compose(
            future,
            "up",
            "-d",
            "--build",
            "--wait",
            "--wait-timeout",
            "120",
            "source-se",
            "cfo-api",
        )
        compose(
            future,
            "exec",
            "-T",
            "-e",
            "APP_ENV=test",
            "-e",
            "DEMO_DISPOSABLE=1",
            "source-se",
            "python",
            "-m",
            "app.seed_e0_04",
        )
        for module in (
            "app.demo_e0_04_shifts",
            "app.demo_e0_04_fleet",
            "app.demo_ingest",
        ):
            args = ["stock"] if module == "app.demo_ingest" else []
            compose(
                future,
                "exec",
                "-T",
                "-e",
                "DEMO_DISPOSABLE=1",
                "cfo-api",
                "python",
                "-m",
                module,
                *args,
            )
        execute([sys.executable, "tools/e0_04_check.py", "--sync-only"], future)
        order_id = sql(
            future, f"SELECT id FROM ops.customer_order WHERE external_ref='{REF}'"
        )
        if not order_id.isdecimal():
            raise RuntimeError("Sales Sync now did not create exactly one CFO order")
        compose(
            future,
            "exec",
            "-T",
            "-e",
            "DEMO_DISPOSABLE=1",
            "cfo-api",
            "python",
            "-m",
            "app.demo_stock_preflight",
            "--external-ref",
            REF,
        )
        compose(
            future,
            "exec",
            "-T",
            "-e",
            "DEMO_DISPOSABLE=1",
            "cfo-api",
            "python",
            "-m",
            "app.demo_e0_04_routes",
            "--order-id",
            order_id,
        )
        execute([sys.executable, "tools/e0_04_check.py"], future)
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print("PASS: E0-04 feasible planning run; proposal remains unapproved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
