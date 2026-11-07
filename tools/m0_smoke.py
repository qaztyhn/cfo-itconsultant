"""Verify M0 in a new Compose project with generated credentials and tmpfs PostgreSQL.

No credentials are written to files or printed. Only the new test project's
containers are stopped on exit; no volumes or existing containers are removed.
Run with a Python 3.12 environment containing backend/source dev dependencies.
"""

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> str:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return str(listener.getsockname()[1])


def run(label: str, command: list[str], env: dict[str, str], cwd: Path = ROOT) -> bool:
    print(f"\n[RUN] {label}", flush=True)
    result = subprocess.run(command, cwd=cwd, env=env, check=False)
    print(f"[{'PASS' if result.returncode == 0 else 'FAIL'}] {label}", flush=True)
    return result.returncode == 0


def wait_for_http(url: str, *, healthy: bool) -> bool:
    for _ in range(30):
        try:
            with urlopen(url, timeout=5) as response:
                if not healthy:
                    return response.status == 200
                data = json.load(response)
                return data.get("status") == "ok" and data.get("db") == "ok"
        except HTTPError as exc:
            if exc.code != 503:
                return False
            time.sleep(1)
        except (URLError, TimeoutError):
            time.sleep(1)
    return False


def check_auth(base: str, password: str, set_active: Callable[[bool], bool]) -> bool:
    """One login only; never log response bodies containing credentials/tokens."""
    try:
        body = json.dumps(
            {"email": "dispatcher@cfo.demo", "password": password}
        ).encode()
        with urlopen(
            Request(
                base + "/auth/login",
                data=body,
                headers={"Content-Type": "application/json"},
            ),
            timeout=10,
        ) as response:
            login = json.load(response)
        if login.get("expires_in") != 28800 or login["user"]["roles"] != ["dispatcher"]:
            return False
        if not login["user"].get("location_ids"):
            return False
        with urlopen(
            Request(
                base + "/auth/me",
                headers={"Authorization": "Bearer " + login["access_token"]},
            ),
            timeout=10,
        ) as response:
            if json.load(response) != login["user"]:
                return False
        for headers in ({}, {"Authorization": "Bearer invalid"}):
            try:
                with urlopen(Request(base + "/auth/me", headers=headers), timeout=10):
                    return False
            except HTTPError as exc:
                error = json.load(exc).get("error", {})
                if (
                    exc.code != 401
                    or error.get("code") != "AUTH_INVALID"
                    or not error.get("correlation_id")
                ):
                    return False
        if not set_active(False):
            return False
        try:
            try:
                with urlopen(
                    Request(
                        base + "/auth/me",
                        headers={"Authorization": "Bearer " + login["access_token"]},
                    ),
                    timeout=10,
                ):
                    return False
            except HTTPError as exc:
                if exc.code != 401:
                    return False
        finally:
            restored = set_active(True)
        if not restored:
            return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker", default=shutil.which("docker"))
    args = parser.parse_args()
    if not args.docker:
        parser.error("Docker is required; use --docker with its executable path")
    env = os.environ.copy()
    # Docker Desktop also launches its credential helper from PATH on Windows.
    env["PATH"] = (
        str(Path(args.docker).resolve().parent) + os.pathsep + env.get("PATH", "")
    )
    password = secrets.token_urlsafe(32)
    for key in (
        "POSTGRES_PORT",
        "MAILPIT_HTTP_PORT",
        "MAILPIT_SMTP_PORT",
        "SOURCE_PORT",
        "CFO_API_PORT",
        "CFO_WEB_PORT",
    ):
        env[key] = free_port()
    env.update(
        PYTHONUTF8="1",
        POSTGRES_PASSWORD=password,
        DATABASE_URL=f"postgresql+asyncpg://cfo:{password}@postgres:5432/cfo",
        SOURCE_SE_DATABASE_URL=f"postgresql+asyncpg://cfo:{password}@postgres:5432/source_se",
        SOURCE_TEST_DATABASE_URL=f"postgresql+asyncpg://cfo:{password}@localhost:{env['POSTGRES_PORT']}/source_se",
        SOURCE_DB_NAME="source_se",
        SOURCE_SCHEMA="src_se",
        TEST_DATABASE_URL=f"postgresql+asyncpg://cfo:{password}@localhost:{env['POSTGRES_PORT']}/cfo",
        SEED_DEMO_PASSWORD=secrets.token_urlsafe(32),
        JWT_SECRET=secrets.token_urlsafe(32),
        INTERNAL_TICK_KEY=secrets.token_urlsafe(32),
        SOURCE_SE_API_KEY=secrets.token_urlsafe(32),
        APP_ENV="test",
        VITE_API_URL=f"http://localhost:{env['CFO_API_PORT']}/api/v1",
        CORS_ORIGINS=json.dumps([f"http://localhost:{env['CFO_WEB_PORT']}"]),
    )
    project = "cfo-m0-check-" + secrets.token_hex(4)
    print(f"Isolated test project: {project}", flush=True)
    with tempfile.TemporaryDirectory(prefix="cfo-m0-") as temporary:
        override = Path(temporary) / "compose.yml"
        init_script = (ROOT / "tools/postgres/init-source-db.sh").as_posix()
        override.write_text(
            "services:\n  postgres:\n    volumes: !override\n"
            f"      - '{init_script}:/docker-entrypoint-initdb.d/10-source-db.sh:ro'\n"
            "    tmpfs: [/var/lib/postgresql/data]\n",
            encoding="utf-8",
        )
        compose = [
            args.docker,
            "compose",
            "--project-name",
            project,
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(override),
        ]
        outcomes = []
        try:
            if not run("docker compose config", compose + ["config", "--quiet"], env):
                return 1
            if not run(
                "start postgres, mailpit, source",
                compose
                + [
                    "up",
                    "-d",
                    "--build",
                    "--wait",
                    "--wait-timeout",
                    "120",
                    "postgres",
                    "mailpit",
                    "source-se",
                ],
                env,
            ):
                return 1
            outcomes.append(
                run(
                    "source schema bootstrap",
                    compose
                    + ["exec", "-T", "source-se", "python", "-m", "app.init_db"],
                    env,
                )
            )
            outcomes.append(
                run(
                    "source unit + PostgreSQL tests",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "tests/unit",
                        "tests/integration",
                        "-q",
                    ],
                    env,
                    ROOT / "source_system",
                )
            )
            if not run("build CFO API", compose + ["build", "cfo-api"], env):
                return 1
            for label, command in (
                ("CFO migrations", ["alembic", "upgrade", "head"]),
                ("M0 account seed", ["python", "-m", "app.seed.m0_accounts"]),
            ):
                if not run(
                    label,
                    compose + ["run", "--rm", "--no-deps", "cfo-api"] + command,
                    env,
                ):
                    return 1
            outcomes.append(
                run(
                    "start CFO API and web",
                    # Dependencies are already healthy and bootstrapped. Do not
                    # recreate tmpfs PostgreSQL after migrations and seeding.
                    compose + ["up", "-d", "--build", "--no-deps", "cfo-api", "cfo-web"],
                    env,
                )
            )
            source_ok = wait_for_http(
                f"http://localhost:{env['SOURCE_PORT']}/api/v1/health", healthy=True
            )
            cfo_ok = wait_for_http(
                f"http://localhost:{env['CFO_API_PORT']}/api/v1/health", healthy=True
            )
            web_ok = wait_for_http(
                f"http://localhost:{env['CFO_WEB_PORT']}", healthy=False
            )
            print(
                f"Source health: {source_ok}; CFO health: {cfo_ok}; web HTTP: {web_ok}",
                flush=True,
            )
            outcomes.extend([source_ok, cfo_ok, web_ok])

            def set_active(active: bool) -> bool:
                # This callback only targets the newly seeded, isolated test DB.
                sql = (
                    "UPDATE ref.app_user SET is_active="
                    + ("true" if active else "false")
                    + " WHERE email='dispatcher@cfo.demo'"
                )
                return run(
                    "restore test account" if active else "disable test account",
                    compose
                    + [
                        "exec",
                        "-T",
                        "postgres",
                        "psql",
                        "-U",
                        "cfo",
                        "-d",
                        "cfo",
                        "-v",
                        "ON_ERROR_STOP=1",
                        "-c",
                        sql,
                    ],
                    env,
                )

            auth_ok = check_auth(
                f"http://localhost:{env['CFO_API_PORT']}/api/v1",
                env["SEED_DEMO_PASSWORD"],
                set_active,
            )
            print(f"Authentication smoke: {auth_ok}", flush=True)
            outcomes.append(auth_ok)
            outcomes.append(
                run(
                    "Harness verify",
                    [sys.executable, "tools/harness.py", "verify"],
                    env,
                )
            )
            env["CFO_HEALTH_URL"] = (
                f"http://localhost:{env['CFO_API_PORT']}/api/v1/health"
            )
            env["SOURCE_HEALTH_URL"] = (
                f"http://localhost:{env['SOURCE_PORT']}/api/v1/health"
            )
            outcomes.append(
                run("Harness smoke", [sys.executable, "tools/harness.py", "smoke"], env)
            )
            run("container status", compose + ["ps", "-a"], env)
            return 0 if all(outcomes) else 1
        finally:
            run(
                "stop only this test project (no volume deletion)",
                compose + ["stop"],
                env,
            )


if __name__ == "__main__":
    raise SystemExit(main())
