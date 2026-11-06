#!/usr/bin/env python3
"""CFO developer harness: safe, cross-platform quality gates.

No third-party dependencies. Run from the repository root or any directory.
Does not install software, start/stop containers, migrate DB, print secrets,
change API contracts, or silently skip failed checks.

Usage:
    python tools/harness.py doctor
    python tools/harness.py backend
    python tools/harness.py frontend
    python tools/harness.py verify
    python tools/harness.py smoke
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    "01_PRD.md",
    "02_User_Stories_and_Acceptance_Criteria.md",
    "03_UI_UX_Specification.md",
    "04_Tech_Stack_and_Architecture.md",
    "05_Database_Design.md",
    "06_API_Specification.md",
    "07_User_Flows.md",
    "08_Development_Plan.md",
    "09_AI_Coding_Rules.md",
    "10_Team_Assignment.md",
]


def banner(message: str) -> None:
    print(f"\n=== {message} ===", flush=True)


def tool_exists(tool: str) -> bool:
    return shutil.which(tool) is not None


def python_for_backend() -> str:
    """Prefer backend's dedicated venv; otherwise use current Python interpreter."""
    candidates = (
        ROOT / "backend" / ".venv" / "Scripts" / "python.exe",
        ROOT / "backend" / ".venv" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    )
    return str(next((p for p in candidates if p.is_file()), Path(sys.executable)))


def bin_for_backend(name: str) -> str | None:
    """Find venv binaries (especially lint-imports) without assuming a shell."""
    interpreter = Path(python_for_backend())
    venv_dir = interpreter.parent
    exe_name = f"{name}.exe" if os.name == "nt" else name
    candidate = venv_dir / exe_name
    if candidate.is_file():
        return str(candidate)
    return shutil.which(name)


def run_step(label: str, command: list[str], *, cwd: Path) -> bool:
    print(f"\n[RUN] {label}", flush=True)
    print(f"      cwd: {cwd.relative_to(ROOT)}", flush=True)
    print(f"      cmd: {' '.join(command)}", flush=True)
    try:
        result = subprocess.run(command, cwd=cwd, check=False)
    except FileNotFoundError as exc:
        print(f"[FAIL] Command not installed: {exc.filename}", flush=True)
        return False
    success = result.returncode == 0
    print(f"[{'PASS' if success else 'FAIL'}] {label} (exit={result.returncode})", flush=True)
    return success


def doctor() -> bool:
    banner("Repository and toolchain doctor (read-only)")
    valid = True
    for relative in ["AGENTS.md", "Makefile", "docker-compose.yml", "backend/pyproject.toml", "frontend/package.json", ".github/workflows/ci.yml"]:
        exists = (ROOT / relative).is_file()
        print(f"[{'OK' if exists else 'MISSING'}] {relative}")
        valid = valid and exists
    for name in DOCS:
        exists = (ROOT / "docs" / name).is_file()
        print(f"[{'OK' if exists else 'MISSING'}] docs/{name}")
        valid = valid and exists
    print(f"[{'OK' if sys.version_info[:2] == (3, 12) else 'WARN'}] Host Python {sys.version.split()[0]} (project targets Python 3.12)")
    for exe in ("node", "npm", "docker", "git"):
        print(f"[{'FOUND' if tool_exists(exe) else 'NOT INSTALLED'}] {exe}")
    print(f"[{'PRESENT' if (ROOT / '.env').exists() else 'NOT PRESENT'}] .env (contents are NEVER read)")
    if not valid:
        print("[FAIL] Missing required repository/context files")
    else:
        print("[PASS] Required repository/context files exist (content not validated)")
    return valid


def backend() -> bool:
    banner("Backend quality gates")
    python = python_for_backend()
    workdir = ROOT / "backend"
    results = [
        run_step("ruff check", [python, "-m", "ruff", "check", "."], cwd=workdir),
        run_step("black check", [python, "-m", "black", "--check", "."], cwd=workdir),
        run_step("mypy engine", [python, "-m", "mypy", "app/engine"], cwd=workdir),
    ]
    import_linter = bin_for_backend("lint-imports")
    if import_linter is None:
        print("[FAIL] import-linter executable not found (install backend dev dependencies)")
        results.append(False)
    else:
        results.append(run_step("import-linter", [import_linter], cwd=workdir))
    results.append(run_step("pytest", [python, "-m", "pytest"], cwd=workdir))
    return all(results)


def frontend() -> bool:
    banner("Frontend quality gates")
    workdir = ROOT / "frontend"
    npm = "npm.cmd" if os.name == "nt" else "npm"
    results = [
        run_step("frontend lint", [npm, "run", "lint"], cwd=workdir),
        run_step("frontend test", [npm, "run", "test"], cwd=workdir),
        run_step("frontend build", [npm, "run", "build"], cwd=workdir),
    ]
    return all(results)


def smoke() -> bool:
    """Only GET health; never query/write real business data or inspect secrets."""
    banner("Local running-stack health checks")
    urls = {
        "CFO API": os.getenv("CFO_HEALTH_URL", "http://localhost:8000/api/v1/health"),
        "Simulated SE source": os.getenv("SOURCE_HEALTH_URL", "http://localhost:8100/api/v1/health"),
    }
    outcomes = []
    for name, url in urls.items():
        try:
            with urlopen(url, timeout=5) as response:
                data = response.read(65536)
                status = response.status
                # JSON parse helps catch plain-text error pages claiming HTTP 200.
                parsed = json.loads(data)
                valid = status == 200 and isinstance(parsed, dict)
                print(f"[{'PASS' if valid else 'FAIL'}] {name}: HTTP {status} ({url})")
                outcomes.append(valid)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            print(f"[FAIL] {name}: {type(exc).__name__} ({url})")
            outcomes.append(False)
    return all(outcomes)


def main() -> int:
    parser = argparse.ArgumentParser(description="CFO repository context and quality gates")
    parser.add_argument("command", choices=("doctor", "backend", "frontend", "verify", "smoke"))
    args = parser.parse_args()
    if args.command == "doctor":
        passed = doctor()
    elif args.command == "backend":
        passed = backend()
    elif args.command == "frontend":
        passed = frontend()
    elif args.command == "smoke":
        passed = smoke()
    else:
        context = doctor()
        # Still run both suites to report all failures; no short-circuit.
        backend_ok = backend()
        frontend_ok = frontend()
        passed = all((context, backend_ok, frontend_ok))
    print(f"\n{'HARNESS PASS' if passed else 'HARNESS FAIL'}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
