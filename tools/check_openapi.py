"""Compare generated OpenAPI with an approved artifact; never create a baseline from stubs.

--readiness is a CI dependency check, not a successful contract test. The actual
comparison exits nonzero if the artifact is absent, empty, or differs.
"""

import argparse
import importlib
import json
import os
import sys
from pathlib import Path


def load_baseline(path: Path) -> dict:
    if not path.is_file():
        return {}
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--readiness", action="store_true")
    args = parser.parse_args()
    baseline = load_baseline(args.baseline)
    ready = isinstance(baseline, dict) and bool(baseline.get("paths"))
    if args.readiness:
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"ready={str(ready).lower()}\n")
        message = (
            f"OpenAPI artifact available: {args.baseline}"
            if ready
            else f"BLOCKED: approved OpenAPI artifact absent/empty: {args.baseline}; contract NOT VERIFIED"
        )
        print(message)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as stream:
                stream.write(message + "\n")
        return 0
    if not ready:
        print("BLOCKED: approved OpenAPI artifact absent/empty; contract NOT VERIFIED")
        return 2
    sys.path.insert(0, str(Path.cwd()))
    module, name = args.app.split(":", 1)
    actual = getattr(importlib.import_module(module), name).openapi()
    if actual != baseline:
        print(
            "FAIL: generated OpenAPI differs from the approved artifact; review contract changes"
        )
        return 1
    print("PASS: generated OpenAPI matches the approved artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
