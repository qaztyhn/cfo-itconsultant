"""Verify T26 on the disposable stack. Default is read-only after login."""

import argparse
import hashlib
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from uuid import NAMESPACE_URL, uuid5

import e0_04_check as api
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "source_system/seed/se/t26.json"
GROUP = {
    "APPROVED": "approved",
    "DISPATCHED": "in_transit",
    "DELIVERED": "completed",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def get(path, token, **params):
    status, response = api.call(
        path + ("?" + urlencode(params) if params else ""), token=token
    )
    require(
        status == 200,
        f"{path} HTTP {status}, code={response.get('error', {}).get('code')}",
    )
    return response


def login(email):
    status, result = api.call(
        "/auth/login",
        body={"email": email, "password": os.environ["SEED_DEMO_PASSWORD"]},
    )
    require(status == 200, f"Demo login HTTP {status}")
    return result["access_token"]


def expected(rows):
    groups = {}
    for key in GROUP.values():
        records = [row for row in rows if GROUP[row[1]] == key]
        groups[key] = {
            "orders": len(records),
            "amount": format(
                sum((Decimal(row[2]) for row in records), Decimal(0)), ".2f"
            ),
            "order_nos": sorted(f"SE-2026-9{row[0][1:]}" for row in records),
        }
    return groups


def verify_report(fixture, locations):
    token = login("owner@cfo.demo")
    report = {}
    for view, index, field in (("store", 3, "stores"), ("warehouse", 4, "warehouses")):
        report[view] = {}
        for code, location_id in [(None, None), *locations[field].items()]:
            filters = dict(fixture["period"], view=view)
            rows = fixture["report_orders"]
            if code is not None:
                filters["location_id"] = location_id
                rows = [row for row in rows if row[index] == code]
            groups = expected(rows)
            cards = get("/revenue/order-status", token, **filters)
            require(
                cards["period"] == fixture["period"],
                "Report period differs from fixture",
            )
            actual = {
                group["key"]: (group["orders"], group["amount"])
                for group in cards["groups"]
            }
            require(
                actual
                == {
                    key: (value["orders"], value["amount"])
                    for key, value in groups.items()
                },
                f"Cards mismatch: {view} {code}",
            )
            require(
                cards["total"]
                == {
                    "orders": len(rows),
                    "amount": format(
                        sum((Decimal(row[2]) for row in rows), Decimal(0)), ".2f"
                    ),
                },
                f"Total mismatch: {view} {code}",
            )
            if location_id is not None:
                for key, group in groups.items():
                    drill = get("/revenue/orders", token, **filters, status_group=key)
                    require(
                        drill["total"] == group["orders"],
                        f"Drill-down count mismatch: {code} {key}",
                    )
                    require(
                        sorted(row["order_no"] for row in drill["items"])
                        == group["order_nos"],
                        f"Drill-down IDs mismatch: {code} {key}",
                    )
                    require(
                        sum(
                            (Decimal(row["amount"]) for row in drill["items"]),
                            Decimal(0),
                        )
                        == Decimal(group["amount"]),
                        f"Drill-down amount mismatch: {code} {key}",
                    )
            summary = get("/revenue/summary", token, **filters)
            recognised = format(
                sum(
                    (Decimal(row[2]) for row in rows if row[1] == "DELIVERED"),
                    Decimal(0),
                ),
                ".2f",
            )
            require(
                summary["recognised"] == recognised,
                f"Recognised revenue mismatch: {view} {code}",
            )
            report[view][code or "market"] = {
                "total": cards["total"],
                "groups": groups,
                "recognised": recognised,
            }
    store_owner = login("demo-st-001-mgr@cfo.demo")
    own = get(
        "/revenue/order-status",
        store_owner,
        **fixture["period"],
        view="store",
        location_id=locations["stores"]["ST-001"],
    )
    require(own["total"]["orders"] == 5, "Store owner scope differs")
    filters = urlencode(
        dict(fixture["period"], view="store", location_id=locations["stores"]["ST-002"])
    )
    forbidden, _ = api.call("/revenue/order-status?" + filters, token=store_owner)
    require(forbidden == 404, "Store owner accessed another store")
    return report


def check_main(fixture):
    token = login("sales@cfo.demo")
    ref = fixture["main_external_ref"]
    sync_status, sync = api.call(
        "/integration/orders/sync-now",
        token=token,
        body={"external_ref": ref},
        key=str(uuid5(NAMESPACE_URL, f"{fixture['version']}:{ref}")),
    )
    order_id = sync.get("order_id")
    require(
        sync_status == 200
        and sync.get("routing_status") == "cfo"
        and isinstance(order_id, int),
        f"Sync {ref} HTTP {sync_status}, routing={sync.get('routing_status')}",
    )
    status, run = api.call(f"/orders/{order_id}/plan", token=token, body={})
    require(
        status == 200 and run.get("result") == "feasible" and run.get("plans"),
        f"Check {ref} HTTP {status}, result={run.get('result')}, failed_check={run.get('failed_check')}, "
        f"code={run.get('error', {}).get('code')}",
    )
    order = get(f"/orders/{order_id}", token)
    plan = get(f"/plans/{run['plans'][0]['id']}", token)
    return {
        "external_ref": ref,
        "order_id": order_id,
        "order_no": order["order_no"],
        "run_id": run["id"],
        "plan_id": plan["id"],
        "result": run["result"],
        "plan_status": plan["status"],
        "target_date": plan["target_date"],
        "vehicle_count": plan["vehicle_count"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "seed_report", type=Path, help="JSON line emitted by the T26 seed"
    )
    parser.add_argument(
        "--exercise-main",
        action="store_true",
        help="Actually Sync and Check, consuming the pre-Sync state",
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    if os.getenv("APP_ENV") != "test" or os.getenv("DEMO_DISPOSABLE") != "1":
        parser.error("T26 disposable environment required")
    if os.getenv("CFO_API_PORT"):
        api.BASE = f"http://127.0.0.1:{int(os.environ['CFO_API_PORT'])}/api/v1"
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    baseline = json.loads(args.seed_report.read_text(encoding="utf-8"))
    require(
        baseline["version"] == fixture["version"], "Seed version differs from fixture"
    )
    result = {
        "seed": baseline,
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "period": fixture["period"],
        "revenue": verify_report(fixture, baseline),
    }
    if args.exercise_main:
        result["main_sync_and_check"] = check_main(fixture)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
