"""Read-only database proof after a REAL disposable Source->CFO Sync & Check.

This does not create orders, routing decisions, stock, plans, regulatory evidence
or approval. It never prints credentials, raw Source orders or SQL error text.
Exit 0: both database proofs PASS. 1: mismatch/unsafe context. 2: BLOCKED.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

APP_NOW = "2026-11-04T10:05:00+01:00"
GOOD_REF = "SE-2026-000149"
UNMAPPED_REF = "SE-2026-000156"
PROJECT = re.compile(r"^cfo-demo-[a-zA-Z0-9_-]+$")


@dataclass(frozen=True)
class Check:
    check: str
    status: str
    detail: str


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def safe_context(env: dict[str, str], source_url: str) -> bool:
    parsed = urlsplit(source_url)
    return (
        env.get("APP_ENV") == "test"
        and env.get("DEMO_DISPOSABLE") == "1"
        and env.get("APP_NOW") == APP_NOW
        and bool(PROJECT.fullmatch(env.get("COMPOSE_PROJECT_NAME", "")))
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and parsed.username is None
        and parsed.password is None
        and parsed.query == ""
        and parsed.fragment == ""
    )


def sync_outcome(path: Path) -> str:
    """Require exact expected smoke schema/check names, never infer from a 200."""
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if obj.get("schema") != "demo-smoke-v1" or obj.get("app_now") != APP_NOW:
            return "FAIL"
        checks = {entry["check"]: entry["status"] for entry in obj["checks"]}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return "FAIL"
    if checks.get("sales_sync_write") == "BLOCKED":
        return "BLOCKED"
    required = (
        "sales_sync_write", "sync_idempotent", "sales_order_visible",
        "dispatcher_order_visible", "unmapped_legacy_negative",
    )
    return "PASS" if all(checks.get(key) == "PASS" for key in required) else "FAIL"


def source_version(source_url: str, api_key: str) -> tuple[int, int]:
    """Scan BOTH fully paginated D1 status feeds and require exact unmodified versions.

    Page-one-only lookup is unsafe once source records exceed 100. Fail closed
    on partial pages, contradictory cancellation, duplicate IDs, version
    changes, stale totals or invalid market/store metadata. This is a
    read-only verifier, never a substitute for the transactional Source API.
    """
    if not api_key:
        raise ValueError("Missing Source authentication.")
    versions: dict[str, int] = {}
    cancelled: set[str] = set()
    opener = build_opener(NoRedirect())
    targets = {GOOD_REF, UNMAPPED_REF}
    page_size = 100
    for status in ("SUBMITTED_FOR_PLANNING", "CANCELLED"):
        seen: set[str] = set()
        total: int | None = None
        page = 1
        while True:
            if page > 100:
                raise ValueError("Source order feed exceeds verified page bound.")
            req = Request(
                source_url.rstrip("/") +
                f"/orders?status={status}&page={page}&page_size={page_size}",
                headers={"X-API-Key": api_key}, method="GET",
            )
            with opener.open(req, timeout=12) as response:
                if (
                    response.status != 200
                    or "json" not in response.headers.get("Content-Type", "").lower()
                ):
                    raise ValueError("Source read was not authenticated JSON.")
                body = json.loads(response.read(262144))
            if not isinstance(body, dict):
                raise ValueError("Invalid Source page.")
            items = body.get("items")
            count = body.get("total")
            if (
                type(count) is not int or count < 0 or count > 10000
                or type(body.get("page")) is not int or body["page"] != page
                or type(body.get("page_size")) is not int or body["page_size"] != page_size
                or not isinstance(items, list) or len(items) > page_size
                or (total is not None and total != count)
            ):
                raise ValueError("Incomplete or inconsistent Source pagination.")
            total = count
            for row in items:
                if not isinstance(row, dict):
                    raise ValueError("Invalid Source record.")
                ref, version = row.get("id"), row.get("version")
                if (
                    not isinstance(ref, str) or not ref
                    or ref in seen
                    or row.get("status") != status
                    or type(version) is not int or version <= 0
                ):
                    raise ValueError("Duplicate or invalid Source record.")
                seen.add(ref)
                if ref in targets:
                    if status == "CANCELLED":
                        cancelled.add(ref)
                    else:
                        if row.get("store_code") != "ST-001":
                            raise ValueError("Source store scope is not approved.")
                        versions[ref] = version
            if len(seen) == total:
                break
            if not items or len(seen) > total or page * page_size >= total:
                raise ValueError("Source pagination ended before all records were checked.")
            page += 1
    if set(versions) != targets or cancelled.intersection(targets):
        raise ValueError("Required submitted Source records are absent or cancelled.")
    return versions[GOOD_REF], versions[UNMAPPED_REF]

# Only fixed, synthetic references, never user-supplied SQL values or identifiers.
SQL = """
SELECT json_build_object(
    'good_count', (
        SELECT count(*) FROM ops.customer_order o JOIN ref.market m ON m.id=o.market_id
        WHERE m.code='SE' AND o.external_ref='SE-2026-000149'
    ),
    'good_min_version', (
        SELECT min(o.source_version) FROM ops.customer_order o JOIN ref.market m ON m.id=o.market_id
        WHERE m.code='SE' AND o.external_ref='SE-2026-000149'
    ),
    'good_max_version', (
        SELECT max(o.source_version) FROM ops.customer_order o JOIN ref.market m ON m.id=o.market_id
        WHERE m.code='SE' AND o.external_ref='SE-2026-000149'
    ),
    'good_route_count', (
        SELECT count(*) FROM ops.order_routing r JOIN ref.market m ON m.id=r.market_id
        WHERE m.code='SE' AND r.external_ref='SE-2026-000149' AND r.route='cfo'
    ),
    'good_route_version', (
        SELECT max(r.decided_source_version) FROM ops.order_routing r JOIN ref.market m ON m.id=r.market_id
        WHERE m.code='SE' AND r.external_ref='SE-2026-000149'
    ),
    'negative_count', (
        SELECT count(*) FROM ops.customer_order o JOIN ref.market m ON m.id=o.market_id
        WHERE m.code='SE' AND o.external_ref='SE-2026-000156'
    ),
    'negative_route_count', (
        SELECT count(*) FROM ops.order_routing r JOIN ref.market m ON m.id=r.market_id
        WHERE m.code='SE' AND r.external_ref='SE-2026-000156' AND r.route='legacy'
    ),
    'negative_route_version', (
        SELECT max(r.decided_source_version) FROM ops.order_routing r JOIN ref.market m ON m.id=r.market_id
        WHERE m.code='SE' AND r.external_ref='SE-2026-000156'
    )
)::text;
"""


def database_snapshot(project: str) -> dict[str, Any]:
    # Never log the command, stdout, stderr or credential environment.
    completed = subprocess.run(
        ["docker", "compose", "--project-name", project, "exec", "-T", "postgres",
         "psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-U", "cfo", "-d", "cfo", "-c", SQL],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if completed.returncode != 0:
        raise ValueError("Read-only PostgreSQL check unavailable.")
    parsed = json.loads(completed.stdout.strip())
    if not isinstance(parsed, dict):
        raise ValueError("Unexpected PostgreSQL evidence.")
    return parsed


def evaluate(snapshot: dict[str, Any], good_version: int, negative_version: int) -> list[Check]:
    """No success based only on the matching HTTP order ID."""
    def whole(key: str, value: int) -> bool:
        return type(snapshot.get(key)) is int and snapshot[key] == value

    positive = (
        whole("good_count", 1)
        and whole("good_min_version", good_version)
        and whole("good_max_version", good_version)
        and whole("good_route_count", 1)
        and whole("good_route_version", good_version)
    )
    negative = (
        whole("negative_count", 0)
        and whole("negative_route_count", 1)
        and whole("negative_route_version", negative_version)
    )
    return [
        Check("postgres_once", "PASS" if positive else "FAIL",
              "Exactly one SE CFO order and one immutable CFO route at the Source version."
              if positive else "Missing, duplicate, or stale order/routing evidence."),
        Check("postgres_legacy_negative", "PASS" if negative else "FAIL",
              "Unmapped-SKU Source order has no CFO order and one immutable legacy decision."
              if negative else "Unmapped-SKU order or routing contradicted the contract."),
    ]


def verify(env: dict[str, str], source_url: str, report: Path) -> list[Check]:
    if not safe_context(env, source_url):
        return [Check("environment", "FAIL", "Only a local, explicitly disposable Swedish test project is permitted.")]
    state = sync_outcome(report)
    if state == "BLOCKED":
        return [
            Check("postgres_once", "BLOCKED", "Sync endpoint not integrated; no CFO order presumed."),
            Check("postgres_legacy_negative", "NOT VERIFIED", "No routed legacy decision to inspect."),
        ]
    if state != "PASS":
        return [Check("sync_evidence", "FAIL", "Verified successful Sync & Check smoke report is required.")]
    try:
        good, negative = source_version(source_url, env.get("SOURCE_SE_API_KEY", ""))
        return evaluate(database_snapshot(env["COMPOSE_PROJECT_NAME"]), good, negative)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return [Check("postgres_once", "FAIL", "Source or read-only PostgreSQL evidence unavailable.")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync-report", type=Path, required=True)
    parser.add_argument("--source-url", default="http://127.0.0.1:8100/api/v1")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify(dict(os.environ), args.source_url, args.sync_report)
    if args.report:
        if args.report.exists():
            print("Refusing to overwrite existing demo database proof.", file=sys.stderr)
            return 1
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump({"schema": "demo-db-proof-v1", "app_now": APP_NOW,
                       "checks": [asdict(item) for item in result]}, stream, indent=2)
    for item in result:
        print(f"{item.status:<12} {item.check}: {item.detail}")
    return 1 if any(item.status == "FAIL" for item in result) else (
        2 if any(item.status != "PASS" for item in result) else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
