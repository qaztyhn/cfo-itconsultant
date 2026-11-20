"""Prepare and verify E0-04 on a NEW disposable Compose project.

Run from the repository root after creating private .env. Never targets a
non-demo project, resets a database, prints secrets or approves a plan.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine.url import make_url

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "cfo-demo-e004"
BASE_NOW = "2026-11-04T10:05:00+01:00"
E0_NOW = "2026-12-01T10:05:00+01:00"
REF = "SE-2026-000249"
T26_FIXTURE = ROOT / "source_system/seed/se/t26.json"


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
    return execute(
        [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env"),
            "-p",
            env["COMPOSE_PROJECT_NAME"],
            *args,
        ],
        env,
        capture=capture,
    )


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stop-before-sync",
        action="store_true",
        help="T27: stop after fully scoped stock/roster/Source prep; CFO order stays absent.",
    )
    parser.add_argument(
        "--seed-report", type=Path, help="Write T26 seed IDs and counts to JSON."
    )
    parser.add_argument(
        "--t26",
        action="store_true",
        help="Seed R3 on the dedicated cfo-demo-t26 project.",
    )
    cli = parser.parse_args()
    fixture = json.loads(T26_FIXTURE.read_text(encoding="utf-8")) if cli.t26 else None
    project = "cfo-demo-t26" if cli.t26 else PROJECT
    values = dotenv_values(ROOT / ".env")
    base = {**os.environ, **{k: v for k, v in values.items() if v is not None}}
    if base.get("APP_ENV") != "test" or base.get("DEMO_DISPOSABLE") != "1":
        print("BLOCKED: private .env must explicitly mark a disposable test demo")
        return 2
    base.update(
        APP_NOW=BASE_NOW,
        COMPOSE_PROJECT_NAME=project,
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
    stock_as_of = datetime.fromisoformat(E0_NOW).astimezone(UTC) - timedelta(minutes=5)
    if datetime.now(UTC) >= stock_as_of:
        print(
            "BLOCKED: fixed Source stock as_of is now past; choose a reviewed future clock"
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
    # Compose bind mounts create missing host directories as root on Linux.
    # Make the synthetic fixture directory writable by the invoking user first.
    fixture_dir = ROOT / ".e0_04_d7"
    if fixture_dir.is_symlink():
        print("BLOCKED: disposable D7 fixture directory must not be a symlink")
        return 2
    try:
        fixture_dir.mkdir(mode=0o700, exist_ok=True)
        if not os.access(fixture_dir, os.W_OK):
            print("BLOCKED: D7 fixture directory is not writable by this user")
            return 2
    except OSError:
        print("BLOCKED: cannot create disposable D7 fixture directory")
        return 2
    base["MSYS_NO_PATHCONV"] = "1"
    try:
        if compose(base, "ps", "--all", "-q", capture=True):
            raise RuntimeError(
                f"{project} already has containers; reset only this disposable project first"
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
        scope_skus = fixture["stock_scope_skus"] if fixture else ["SE-BRD-GYP-13"]
        warehouse_ids = ["6", "7", "8"]
        if fixture:
            warehouse_ids = sql(
                base,
                "SELECT id FROM ref.location WHERE type='warehouse' AND code IN ('GBG','STO') "
                "AND market_id=(SELECT id FROM ref.market WHERE code='SE') ORDER BY id",
            ).splitlines()
            if len(warehouse_ids) != 2 or not all(
                value.isdecimal() for value in warehouse_ids
            ):
                raise RuntimeError("T26 requires GBG and STO warehouse IDs")
        compose(
            base,
            *scope,
            "--market",
            "SE",
            "--actor-id",
            "2",
            "--execute",
            "create",
            *(arg for sku in scope_skus for arg in ("--sku", sku)),
            *(arg for wh in warehouse_ids for arg in ("--warehouse-id", wh)),
            "--reason",
            "T26-disposable-order-scope" if fixture else "E0-04-disposable-order-scope",
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
            module_args = ["stock"] if module == "app.demo_ingest" else []
            if fixture and module == "app.demo_e0_04_shifts":
                module_args = ["--round3"]
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
                *module_args,
            )
        if fixture:
            compose(future, "cp", str(T26_FIXTURE), "cfo-api:/tmp/t26.json")
            report = compose(
                future,
                "exec",
                "-T",
                "cfo-api",
                "python",
                "-m",
                "app.seed.t26",
                "/tmp/t26.json",
                capture=True,
            )
            print(report)
            if cli.seed_report:
                cli.seed_report.write_text(report + "\n", encoding="utf-8")
        if cli.stop_before_sync or fixture:
            if (
                sql(
                    future,
                    f"SELECT count(*) FROM ops.customer_order WHERE external_ref='{REF}'",
                )
                != "0"
            ):
                raise RuntimeError(
                    "Main order already present in CFO before Sales Sync"
                )
            if fixture:
                print(
                    f"PASS: enter Source external_ref={REF} in Sales → Sync & Check; APP_NOW={E0_NOW}."
                )
            else:
                print(
                    "PASS: E0-04 stock/roster/Source prepared, CFO order absent; browser must Sync and Plan"
                )
            return 0
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
