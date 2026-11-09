"""Read-only by default, real-HTTP Swedish demo acceptance probe.

Write mode is permitted ONLY on an explicitly disposable localhost APP_ENV=test
environment. Neither results nor logs include tokens, source payloads or PII.
Exit 0: all required checks PASS; 2: one or more BLOCKED/NOT VERIFIED; 1: FAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import NAMESPACE_URL, uuid5

APP_NOW = "2026-11-04T10:05:00+01:00"
GOOD_REF = "SE-2026-000123"
DATE_REF = "SE-2026-000137"
UNMAPPED_REF = "SE-2026-000156"
ROLES = {
    "sales": "sales@cfo.demo",
    "dispatcher": "dispatcher@cfo.demo",
    "warehouse": "wm.got@cfo.demo",
    "driver": "driver1@cfo.demo",
}


@dataclass
class Result:
    check: str
    status: str
    detail: str


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class Http:
    """Intentionally do not follow redirects with private credentials."""

    def __init__(self) -> None:
        self.opener = build_opener(NoRedirect())

    def send(
        self, url: str, *, method: str = "GET", headers: dict[str, str] | None = None,
        body: dict[str, object] | None = None,
    ) -> tuple[int, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            url, data=data, method=method,
            headers={**(headers or {}), **({"Content-Type": "application/json"} if data is not None else {})},
        )
        try:
            with self.opener.open(request, timeout=12) as response:
                payload = response.read(262144)
                return response.status, json.loads(payload) if payload else None
        except HTTPError as error:
            # Do not print or persist error bodies (which might contain PII).
            return error.code, None
        except (URLError, TimeoutError, OSError, ValueError):
            return 0, None


def localhost(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"} and not parsed.username


def allow_mutation(environ: dict[str, str], urls: list[str]) -> bool:
    return (
        environ.get("APP_ENV") == "test"
        and environ.get("DEMO_DISPOSABLE") == "1"
        and environ.get("APP_NOW") == APP_NOW
        and all(localhost(url) for url in urls)
    )


def verdict(results: list[Result]) -> int:
    if any(result.status == "FAIL" for result in results):
        return 1
    return 2 if any(result.status != "PASS" for result in results) else 0


def _safe_ok(status: int, body: Any) -> bool:
    return status == 200 and isinstance(body, dict)


def run(
    http: Http, source: str, cfo: str, web: str,
    *, write: bool = False, approval: bool = False,
    environ: dict[str, str] | None = None,
) -> list[Result]:
    env = os.environ if environ is None else environ
    urls = [source, cfo, web]
    if not all(localhost(url) for url in urls):
        return [Result("environment", "FAIL", "All endpoints must be localhost HTTP. No remote environment is permitted.")]
    if (write or approval) and not allow_mutation(env, urls):
        return [Result("environment", "FAIL", "Mutating demo requires APP_ENV=test, DEMO_DISPOSABLE=1 and approved APP_NOW.")]
    if approval and not write:
        return [Result("environment", "FAIL", "Approval smoke requires explicit --exercise-sync first.")]
    results: list[Result] = []

    def add(check: str, status: str, detail: str) -> None:
        results.append(Result(check, status, detail))

    source_health, sh = http.send(f"{source}/health")
    cfo_health, ch = http.send(f"{cfo}/health")
    web_status, _ = http.send(web + "/")
    for name, status, body in (("source_db", source_health, sh), ("cfo_db", cfo_health, ch)):
        add(name, "PASS" if _safe_ok(status, body) and body.get("db") == "ok" else "FAIL",
            "Live database health checked." if status == 200 else f"Health HTTP {status}.")
    add("frontend_http", "PASS" if web_status == 200 else "FAIL", f"Web HTTP {web_status}; browser rendering NOT VERIFIED.")
    if any(item.status == "FAIL" for item in results):
        return results

    source_key = env.get("SOURCE_SE_API_KEY", "")
    password = env.get("SEED_DEMO_PASSWORD", "")
    if not source_key or not password:
        add("credentials", "FAIL", "SOURCE_SE_API_KEY and SEED_DEMO_PASSWORD must be supplied privately.")
        return results

    denied_status, _ = http.send(f"{source}/orders?page_size=1")
    add("source_auth_negative", "PASS" if denied_status in (400, 401) else "FAIL",
        f"Unauthenticated Source read HTTP {denied_status}; expected 400/401.")
    auth = {"X-API-Key": source_key}
    source_status, source_body = http.send(f"{source}/orders?status=SUBMITTED_FOR_PLANNING&page=1&page_size=100", headers=auth)
    items = source_body.get("items") if _safe_ok(source_status, source_body) else None
    if not isinstance(items, list):
        add("source_read", "FAIL", f"Source submitted-orders read HTTP {source_status} / invalid response.")
        return results
    by_ref = {o.get("id"): o for o in items if isinstance(o, dict)}
    selected = [by_ref.get(ref) for ref in (GOOD_REF, DATE_REF, UNMAPPED_REF)]
    valid_source = all(isinstance(order, dict) and order.get("status") == "SUBMITTED_FOR_PLANNING"
                       and order.get("store_code") == "ST-001"
                       and isinstance(order.get("version"), int) and order["version"] > 0
                       and isinstance(order.get("lines"), list) and order["lines"]
                       for order in selected)
    add("source_fixture", "PASS" if valid_source else "FAIL",
        "Selected ST-001 synthetic positive/date/unknown-SKU orders exist in real Source API."
        if valid_source else "Required seeded orders missing, invalid, or not in ST-001.")
    if not valid_source:
        return results
    again_status, again_body = http.send(f"{source}/orders?status=SUBMITTED_FOR_PLANNING&page=1&page_size=100", headers=auth)
    rerun = {o.get("id"): o for o in again_body.get("items", []) if isinstance(o, dict)} if _safe_ok(again_status, again_body) else {}
    stable = all(rerun.get(ref, {}).get("version") == by_ref[ref]["version"]
                 for ref in (GOOD_REF, DATE_REF, UNMAPPED_REF))
    add("source_read_repeat", "PASS" if stable else "FAIL", "Source versions stable on repeated GET." if stable else "Source version changed.")

    tokens: dict[str, str] = {}
    profiles: dict[str, dict[str, Any]] = {}
    for role, email in ROLES.items():
        status, body = http.send(f"{cfo}/auth/login", method="POST", body={"email": email, "password": password})
        ok = status == 200 and isinstance(body, dict) and isinstance(body.get("access_token"), str)
        user = body.get("user", {}) if ok else {}
        ok = ok and isinstance(user, dict) and role in user.get("roles", []) and user.get("market") == "SE"
        add(f"role_{role}", "PASS" if ok else "FAIL",
            "Verified authenticated role and Swedish market." if ok else f"Demo role login/profile HTTP {status} invalid.")
        if ok:
            tokens[role] = body["access_token"]
            profiles[role] = user
    if "sales" not in tokens or "dispatcher" not in tokens:
        return results

    def scoped(role: str, path: str) -> tuple[int, Any]:
        return http.send(cfo + path, headers={"Authorization": "Bearer " + tokens[role]})

    sales_status, sales_orders = scoped("sales", "/orders?page_size=2")
    dispatcher_status, dispatcher_orders = scoped("dispatcher", "/orders?page_size=2")
    for role, status, body in (("sales", sales_status, sales_orders), ("dispatcher", dispatcher_status, dispatcher_orders)):
        add(f"{role}_orders_read", "PASS" if status == 200 and isinstance(body, dict)
            and isinstance(body.get("items"), list) else "FAIL", f"Scoped CFO GET /orders HTTP {status}.")
    unauth, _ = http.send(f"{cfo}/orders?page_size=1")
    add("cfo_auth_negative", "PASS" if unauth == 401 else "FAIL", f"Unauthenticated CFO order read HTTP {unauth}.")

    if not write:
        add("sales_sync_write", "NOT VERIFIED", "No mutation in default read-only mode; use --exercise-sync on isolated demo.")
        add("planning_approval", "BLOCKED", "No approved D7 56-day evidence or production WMS ACK; never fabricate eligibility.")
        add("postgres_once", "NOT VERIFIED", "Verify row count with documented SQL after sync; HTTP alone is not database uniqueness proof.")
        return results

    def sync(ref: str) -> tuple[int, Any]:
        key = str(uuid5(NAMESPACE_URL, "cfo-demo-sync:" + ref))
        return http.send(f"{cfo}/integration/orders/sync-now", method="POST",
                         headers={"Authorization": "Bearer " + tokens["sales"], "Idempotency-Key": key},
                         body={"external_ref": ref})

    status, response = sync(GOOD_REF)
    if status in (404, 405, 501):
        add("sales_sync_write", "BLOCKED", "BE-SALES: approved sync-now endpoint missing; no CFO creation or routing assumed.")
        add("planning_approval", "BLOCKED", "Cannot plan or approve an order not accepted through approved routing.")
        add("postgres_once", "NOT VERIFIED", "No successful routing write to check.")
        return results
    valid = status == 200 and isinstance(response, dict) and response.get("routing_status") == "cfo"
    order_id = response.get("order_id") if valid else None
    valid = bool(valid and type(order_id) is int and order_id > 0
                 and response.get("source_version") == by_ref[GOOD_REF]["version"])
    add("sales_sync_write", "PASS" if valid else "FAIL",
        "CFO accepted eligible source version and returned a scoped order ID."
        if valid else f"Sync-now HTTP {status} did not prove CFO routing and source version.")
    if not valid:
        return results

    second_status, second = sync(GOOD_REF)
    same = second_status == 200 and isinstance(second, dict) and second.get("order_id") == order_id and second.get("routing_status") == "cfo"
    add("sync_idempotent", "PASS" if same else "FAIL", "Repeated identical key returns same CFO order." if same else "Repeated sync differed.")
    for role in ("sales", "dispatcher"):
        result_status, detail = scoped(role, f"/orders/{order_id}")
        ok = result_status == 200 and isinstance(detail, dict) and detail.get("external_ref") == GOOD_REF
        add(f"{role}_order_visible", "PASS" if ok else "FAIL", f"Scoped real order detail HTTP {result_status}.")

    negative_status, negative = sync(UNMAPPED_REF)
    negative_ok = negative_status == 200 and isinstance(negative, dict) and negative.get("routing_status") == "legacy" and not negative.get("order_id")
    add("unmapped_legacy_negative", "PASS" if negative_ok else "FAIL",
        "Pending-mapping SKU remains legacy without CFO order." if negative_ok else
        f"Negative SKU routing did not fail closed (HTTP {negative_status}).")
    plan_status, plan = http.send(f"{cfo}/orders/{order_id}/plan", method="POST",
                                  headers={"Authorization": "Bearer " + tokens["sales"]}, body={})
    plan_ok = plan_status == 200 and isinstance(plan, dict)
    add("planning_run", "PASS" if plan_ok else "BLOCKED",
        "Server returned a genuine planning run." if plan_ok else
        f"Planner HTTP {plan_status}; missing source/stock/official-duty proof cannot be bypassed.")
    if not approval or not plan_ok:
        add("planning_approval", "NOT VERIFIED" if plan_ok else "BLOCKED",
            "Approval not attempted (requires --exercise-approval) or plan not verified.")
    else:
        plans = plan.get("plans")
        eligible = plan.get("result") == "feasible" and plan.get("sales_approvable") is True and isinstance(plans, list)
        eligible = bool(eligible and len(plans) == 1 and plans[0].get("rank") == 1
                        and plans[0].get("vehicle_count") == 1)
        if not eligible:
            add("planning_approval", "BLOCKED", "Server did not certify a single Sales-approvable standard plan.")
        else:
            plan_id = plans[0].get("id")
            if type(plan_id) is not int:
                add("planning_approval", "BLOCKED", "Planning DTO did not supply a valid plan ID.")
            else:
                key = str(uuid5(NAMESPACE_URL, f"cfo-demo-approval:{plan_id}"))
                approved_status, approved = http.send(
                    f"{cfo}/plans/{plan_id}/approve", method="POST",
                    headers={"Authorization": "Bearer " + tokens["sales"], "Idempotency-Key": key}, body={},
                )
                add("planning_approval",
                    "PASS" if approved_status == 200 and isinstance(approved, dict)
                    and approved.get("status") == "APPROVED" else "BLOCKED",
                    "Server confirmed explicit approval." if approved_status == 200 else
                    f"Server approval HTTP {approved_status}; legal/WMS gates remain mandatory.")
    add("postgres_once", "NOT VERIFIED", "Use documented read-only PostgreSQL count query; HTTP retry is not uniqueness proof.")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default="http://127.0.0.1:8100/api/v1")
    parser.add_argument("--cfo-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--web-url", default="http://127.0.0.1:5173")
    parser.add_argument("--exercise-sync", action="store_true", help="Mutates the disposable demo's routing only.")
    parser.add_argument("--exercise-approval", action="store_true", help="Explicit synthetic-only approval attempt.")
    parser.add_argument("--report", type=Path, help="Optional structured status file (no tokens or PII).")
    args = parser.parse_args()
    results = run(
        Http(), args.source_url.rstrip("/"), args.cfo_url.rstrip("/"), args.web_url.rstrip("/"),
        write=args.exercise_sync, approval=args.exercise_approval,
    )
    record = {"schema": "demo-smoke-v1", "app_now": APP_NOW, "checks": [asdict(x) for x in results]}
    if args.report:
        if args.report.exists():
            print("Report already exists; refusing to overwrite.", file=sys.stderr)
            return 1
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2)
    for item in results:
        print(f"{item.status:<12} {item.check}: {item.detail}")
    return verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
