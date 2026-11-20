"""Launch the disposable E1 API acceptance using an existing E0-04 database.

Set E0_DEMO_ENV_FILE to the private E0-04 .env path when using worktrees.
No credential or token is printed or written to the fixture.
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
env_file = Path(os.getenv("E0_DEMO_ENV_FILE", str(ROOT / ".env")))
if not env_file.is_file():
    raise SystemExit("Private disposable E0-04 .env is required")
env = {
    **os.environ,
    **{k: v for k, v in dotenv_values(env_file).items() if v is not None},
}
if env.get("APP_ENV") != "test" or env.get("DEMO_DISPOSABLE") != "1":
    raise SystemExit("E0-04 disposable test environment is required")
env.update(
    APP_NOW="2026-12-01T10:05:00+01:00",
    WMS_RESERVATION_MODE="simulated",
    SYNTHETIC_WMS_URL="http://127.0.0.1:8188",
    DEMO_D7_FIXTURE_DIR="",
    SYNTHETIC_WMS_FIXTURE=str((ROOT / ".e1_wms_fixture.json").resolve()),
    SYNTHETIC_WMS_DB=str((ROOT / ".e1_wms.sqlite").resolve()),
    PYTHONPATH=str(ROOT / "backend"),
)
key = secrets.token_urlsafe(36)
env["SYNTHETIC_WMS_API_KEY"] = key
env["SYNTHETIC_WMS_SHARED_KEY"] = key
env["DATABASE_URL"] = env["DATABASE_URL"].replace("@postgres:5432", "@127.0.0.1:5432")
if "@127.0.0.1:5432" not in env["DATABASE_URL"]:
    raise SystemExit("Only the disposable local PostgreSQL is supported")
subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=ROOT / "backend",
    env=env,
    check=True,
)
raise SystemExit(
    subprocess.call(
        [sys.executable, "tools/e1_demo_accept.py"],
        cwd=ROOT,
        env=env,
    )
)
