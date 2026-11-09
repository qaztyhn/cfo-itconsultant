"""Observe complete Source stock and CFO governed persistence, WITHOUT importing stock.

Invoked only by disposable Compose preflight; reports counts/status, never SKU
payloads, API keys, contact data or database credentials.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

FROZEN = "2026-11-04T10:05:00+01:00"
REPORT = Path(__file__).resolve().parents[1] / "demo-ci-stock-results.json"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def observe(env: dict[str, str]) -> dict[str, object]:
    if (
        env.get("APP_ENV") != "test"
        or env.get("DEMO_DISPOSABLE") != "1"
        or env.get("APP_NOW") != FROZEN
        or re.fullmatch(r"cfo-demo-ci-[a-z0-9]+", env.get("COMPOSE_PROJECT_NAME", "")) is None
        or not env.get("SOURCE_SE_API_KEY")
    ):
        return {"source": "BLOCKED_UNSAFE_ENV", "cfo": "NOT_VERIFIED"}
    source: dict[str, object] = {"status": "BLOCKED_SOURCE_NOT_VERIFIED"}
    try:
        port = int(env.get("SOURCE_PORT", "0"))
        if not 1 <= port <= 65535:
            raise ValueError("bad port")
        req = Request(
            f"http://127.0.0.1:{port}/api/v1/stock",
            headers={"X-API-Key": env["SOURCE_SE_API_KEY"]},
            method="GET",
        )
        with build_opener(NoRedirect()).open(req, timeout=12) as response:
            if response.status != 200 or "json" not in response.headers.get("Content-Type", "").lower():
                raise ValueError("Source stock contract unavailable")
            body = json.loads(response.read(262144))
        items = body.get("items")
        count = body.get("item_count")
        if (
            type(count) is not int or count <= 0
            or not isinstance(items, list) or count != len(items)
            or type(body.get("batch_id")) is not int or body["batch_id"] <= 0
            or not isinstance(body.get("as_of"), str)
        ):
            raise ValueError("Source batch incomplete")
        source = {
            "status": "PASS_COMPLETE_SOURCE_BATCH", "item_count": count,
            "batch_id": body["batch_id"], "as_of": body["as_of"],
        }
    except (HTTPError, URLError, OSError, ValueError, TypeError, AttributeError):
        pass

    cfo: dict[str, object] = {"status": "BLOCKED_CFO_NOT_VERIFIED"}
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "-e", "DEMO_DISPOSABLE=1",
             "cfo-api", "python", "-m", "app.demo_stock_readonly"],
            capture_output=True, text=True, timeout=35, check=False,
            env=env, cwd=REPORT.parent,
        )
        if result.returncode == 0:
            obj = json.loads(result.stdout)
            if (
                obj.get("market") == "SE"
                and obj.get("status") in ("PRESENT_NOT_APPROVAL_PROOF", "BLOCKED_STOCK_NOT_GOVERNED")
                and all(type(obj.get(key)) is int and obj[key] >= 0 for key in
                        ("stock_rows", "accepted_write_runs", "approved_scope_versions"))
            ):
                cfo = obj
    except (subprocess.SubprocessError, OSError, ValueError, TypeError):
        pass
    return {"source": source, "cfo": cfo, "planning": "BLOCKED_UNTIL_REAL_GOVERNED_STOCK"}


def main() -> int:
    output = observe(dict(os.environ))
    if REPORT.exists():
        print("BLOCKED: refusing to overwrite prior stock evidence.")
        return 2
    REPORT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("SOURCE STOCK: " + str(output["source"].get("status", "BLOCKED")))
    print("CFO STOCK: " + str(output["cfo"].get("status", "BLOCKED")))
    print("STOCK DIAGNOSTIC: read-only; no source rows or CFO inventory were written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
