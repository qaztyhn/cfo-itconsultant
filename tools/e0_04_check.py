"""Perform the Sales Sync now -> Check feasibility -> open plan HTTP path safely."""

import argparse
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv

REF = "SE-2026-000249"
BASE = "http://127.0.0.1:8000/api/v1"


def call(
    path: str, *, token: str = "", body: dict | None = None, key: str = ""
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if key:
        headers["Idempotency-Key"] = key
    request = Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        try:
            payload = json.load(exc)
        except ValueError:
            payload = {}
        return exc.code, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync-only", action="store_true")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if (
        os.getenv("APP_ENV") != "test"
        or os.getenv("DEMO_DISPOSABLE") != "1"
        or os.getenv("APP_NOW") != "2026-12-01T10:05:00+01:00"
    ):
        print("BLOCKED: disposable E0-04 environment required")
        return 2
    status, login = call(
        "/auth/login",
        body={"email": "sales@cfo.demo", "password": os.environ["SEED_DEMO_PASSWORD"]},
    )
    if status != 200:
        print(f"BLOCKED: Sales login HTTP {status}")
        return 2
    token = login["access_token"]
    sync_status, sync = call(
        "/integration/orders/sync-now",
        token=token,
        body={"external_ref": REF},
        key=str(uuid5(NAMESPACE_URL, "e0-04-sync:" + REF)),
    )
    order_id = sync.get("order_id")
    print(
        f"Sync now: HTTP {sync_status}, order_id={order_id}, routing={sync.get('routing_status')}"
    )
    if (
        sync_status != 200
        or sync.get("routing_status") != "cfo"
        or not isinstance(order_id, int)
    ):
        return 2
    if args.sync_only:
        return 0
    plan_status, run = call(f"/orders/{order_id}/plan", token=token, body={})
    if plan_status != 200:
        print(
            f"Check feasibility: HTTP {plan_status}, code={run.get('error', {}).get('code')}"
        )
        return 2
    run_id = run.get("id")
    plans = run.get("plans") or []
    print(
        f"Check feasibility: HTTP 200, runId={run_id}, result={run.get('result')}, plans={len(plans)}"
    )
    if run.get("result") != "feasible" or not isinstance(run_id, int) or not plans:
        print(
            f"Planner blocker: {run.get('failed_check') or run.get('rejected_candidates')}"
        )
        return 2
    plan_id = plans[0]["id"]
    detail_status, detail = 404, {}
    for attempt in range(10):
        detail_status, detail = call(f"/plans/{plan_id}", token=token)
        if detail_status != 404:
            break
        time.sleep(0.1 * (attempt + 1))
    print(
        f"Open plan: HTTP {detail_status}, planId={plan_id}, rank={detail.get('rank')}"
    )
    if (
        detail_status != 200
        or detail.get("id") != plan_id
        or detail.get("status") != "proposed"
    ):
        return 2
    evidence = {
        "external_ref": REF,
        "cfo_order_id": order_id,
        "run_id": run_id,
        "result": run["result"],
        "plan_id": plan_id,
        "rank": detail.get("rank"),
        "status": detail.get("status"),
        "target_date": detail.get("target_date"),
        "eta_at": detail.get("eta_at"),
        "vehicle_count": detail.get("vehicle_count"),
        "sales_approvable": run.get("sales_approvable"),
    }
    Path(".e0-04-after.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
