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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

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
        except HTTPError:
            return False
        except (URLError, TimeoutError):
            time.sleep(1)
    return False


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
        POSTGRES_PASSWORD=password,
        DATABASE_URL=f"postgresql+asyncpg://cfo:{password}@postgres:5432/cfo",
        SOURCE_SE_DATABASE_URL=f"postgresql+asyncpg://cfo:{password}@postgres:5432/source_se",
        SOURCE_TEST_DATABASE_URL=f"postgresql+asyncpg://cfo:{password}@localhost:{env['POSTGRES_PORT']}/source_se",
        SOURCE_DB_NAME="source_se",
        SOURCE_SCHEMA="src_se",
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
            outcomes.append(
                run(
                    "start CFO API and web",
                    compose + ["up", "-d", "--build", "cfo-api", "cfo-web"],
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
