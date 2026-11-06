"""Fail early on known Dev 1/M1 stubs; this is not a substitute for DB tests."""

import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def is_stub(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            expression = node.exc
            if isinstance(expression, ast.Call):
                expression = expression.func
            if (
                isinstance(expression, ast.Name)
                and expression.id == "NotImplementedError"
            ):
                return True
    return False


def blockers(target: str) -> list[Path]:
    if target == "seed":
        path = ROOT / "backend/app/seed/generate_data.py"
        return [path] if not path.is_file() or is_stub(path) else []
    env = ROOT / "backend/alembic/env.py"
    result = []
    if not env.is_file() or not any(
        isinstance(node, ast.Attribute) and node.attr == "run_migrations"
        for node in ast.walk(ast.parse(env.read_text(encoding="utf-8")))
    ):
        result.append(env)
    revisions = sorted((ROOT / "backend/alembic/versions").glob("*.py"))
    if not revisions:
        result.append(ROOT / "backend/alembic/versions")
    result.extend(path for path in revisions if is_stub(path))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("migrations", "seed"))
    args = parser.parse_args()
    pending = blockers(args.target)
    if pending:
        print(f"BLOCKED: {args.target} implementation must be handed off by its owner:")
        for path in pending:
            print(f"  {path.relative_to(ROOT)}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
