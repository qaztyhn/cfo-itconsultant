"""US-INT-05 AC3 / 09 bất biến 6: engine không import hạ tầng."""

import ast
import pathlib

FORBIDDEN = (
    "sqlalchemy",
    "httpx",
    "requests",
    "app.services",
    "app.adapters",
    "app.providers",
    "app.core",
    "app.api",
    "app.jobs",
)
ENGINE_DIR = pathlib.Path(__file__).resolve().parents[2] / "app" / "engine"


def test_US_INT_05_AC3_engine_has_no_infrastructure_imports() -> None:
    offenders: list[str] = []
    for path in ENGINE_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [f"{path.name}: {n}" for n in names if n.startswith(FORBIDDEN)]
    assert offenders == []


def test_engine_never_calls_datetime_now() -> None:
    """09 bất biến 6, 17: "bây giờ" phải truyền vào engine qua tham số `now`."""
    offenders: list[str] = []
    for path in ENGINE_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"now", "today", "utcnow"}:
                    offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
