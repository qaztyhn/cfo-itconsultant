"""T30 T27-step-12b: real Chrome -> Vite -> FastAPI T29 -> disposable PostgreSQL.

Uses synthetic *T29-style* grouped order rows, not the official T26 demo seed.
No mock handlers, no credentials/tokens/customer names persisted to evidence.
"""

import argparse
import asyncio
import json
import os
import secrets
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

from alembic import command
from app.audit.actions import Action
from app.audit.recorder import record_decision
from app.core.security import hash_password
from app.domain.transitions import S, transition
from tests.e2e.prep_queue_browser import FRONTEND_DIR, local_service, loopback_port
from tests.integration import rows
from tests.integration.conftest import (
    BACKEND_DIR,
    _admin_exec,
    _plain_dsn,
    _with_database,
    alembic_config,
    async_url,
    execute,
    fetch,
)
from tests.integration.test_revenue_api import SEED
from tests.integration.test_revenue_service import _order, run

APP_NOW = "2026-11-19T10:05:00+01:00"
ZONE = "Europe/Stockholm"
PERIOD = {"from": "2026-11-01", "to": "2026-11-30"}
VIEWER = "business@cfo.test"
GROUP_COUNTS = {"approved": 2, "in_transit": 1, "completed": 1, "failed": 1, "cancelled": 1}


def seed_report(dsn: str, password: str) -> None:
    # A16b groups and committed dates sourced from the T29 test helpers.
    # All entries are synthetic; none reached states through a production workflow.
    records = (
        (1, "APPROVED", "101.00", 2, "2026-11-17", None),
        (2, "DISPATCHED", "202.00", 2, "2026-11-18", None),
        (3, "DELIVERED", "303.00", 2, "2026-11-19", "2026-11-19T09:00:00Z"),
        (4, "FAILED", "404.00", 2, "2026-11-19", None),
        (5, "PLANNED", "505.00", 2, None, None),  # cancel before approve
        (6, "APPROVED", "606.00", 3, "2026-11-19", None),
    )
    sql = [*SEED]
    plan_id = 0
    for no, status, amount, store, committed, delivered in records:
        sql.append(_order(no, status, amount, store, committed=committed, delivered=delivered))
        if status != "PLANNED":
            plan_id += 1
            sql.extend(
                (
                    rows.run_sql(no, 1),
                    rows.plan_sql(plan_id, no, 1, "approved"),
                    f"UPDATE plan.fulfilment_plan SET warehouse_id=4 WHERE id={plan_id}",
                    f"UPDATE ops.customer_order SET approved_plan_id={plan_id} WHERE id={no}",
                )
            )
    execute(dsn, *sql)

    async def cancel(session):
        reason = "Synthetic pre-approval cancellation for T30 report"
        async with session.begin():
            with patch("app.core.clock.now", return_value=datetime.fromisoformat(APP_NOW)):
                result = await transition(session, 5, S.CANCELLED, "dispatcher", reason)
                assert result.closed is not None
                await record_decision(
                    session,
                    Action.ORDER_CANCELLED,
                    entity="order",
                    entity_id="5",
                    order_id=5,
                    actor_user_id=4,
                    actor_employee_id=4,
                    actor_role="dispatcher",
                    reason_text=reason,
                    before=result.closed.before | {"status": result.from_status.value},
                    after={"status": "CANCELLED"},
                )

    run(dsn, cancel)
    updated = fetch(
        dsn,
        "UPDATE ref.app_user SET password_hash=$1 WHERE email=$2 RETURNING id",
        hash_password(password),
        VIEWER,
    )
    assert len(updated) == 1


def browser_check(api: str, web: str, password: str, output: Path, evidence: dict) -> None:
    with sync_playwright() as playwright, closing(playwright.chromium.launch(channel="chrome")) as browser:
        evidence["chrome"] = browser.version
        page = browser.new_page(
            timezone_id=ZONE, viewport={"width": 1440, "height": 1080}, service_workers="block"
        )
        page.set_default_timeout(15_000)
        safe_requests = []

        def save_response(res):
            parsed = urlsplit(res.url)
            if parsed.path.startswith("/api/v1/revenue/"):
                params = parse_qs(parsed.query)
                safe_requests.append(
                    {
                        "path": parsed.path,
                        "http": res.status,
                        "query": {
                            key: params[key][0]
                            for key in ("view", "from", "to", "location_id", "status_group", "page")
                            if key in params
                        },
                    }
                )

        page.on("response", save_response)
        try:
            page.goto(f"{web}/login")
            page.locator('input[type="email"]').fill(VIEWER)
            page.get_by_label("Password", exact=True).fill(password)
            with page.expect_response(
                lambda res: res.request.method == "POST" and urlsplit(res.url).path == "/api/v1/auth/login"
            ) as auth:
                page.get_by_role("button", name="Sign in", exact=True).click()
            assert auth.value.status == 200, auth.value.status
            page.goto(f"{web}/revenue")
            page.get_by_role("heading", name="Đơn hàng & doanh thu").wait_for()
            page.get_by_label("From date").fill(PERIOD["from"])
            with page.expect_response(
                lambda res: urlsplit(res.url).path == "/api/v1/revenue/order-status"
                and "to=2026-11-30" in res.url
            ) as grouped:
                page.get_by_label("To date").fill(PERIOD["to"])
            all_groups = grouped.value
            assert all_groups.status == 200, all_groups.status
            agg = all_groups.json()
            assert agg["period"] == PERIOD and agg["total"]["orders"] == 6, agg
            assert {g["key"]: g["orders"] for g in agg["groups"]} == GROUP_COUNTS, agg
            for group in agg["groups"]:
                label = {
                    "approved": "Đã duyệt",
                    "in_transit": "Đang vận chuyển",
                    "completed": "Đã hoàn thành",
                    "failed": "Thất bại",
                    "cancelled": "Đã hủy",
                }[group["key"]]
                page.get_by_role("button", name=f"{label}: {group['orders']} orders").wait_for()
            assert "303 SEK" in page.get_by_label("Primary order and revenue metrics").inner_text()
            page.screenshot(path=output / "01-period-five-groups.png")
            evidence["period_five_groups"] = {
                "http": all_groups.status,
                "orders": agg["total"]["orders"],
                "groups": {row["key"]: row["orders"] for row in agg["groups"]},
            }

            page.get_by_role("button", name="Đã duyệt: 2 orders").click()
            page.get_by_text("Chọn một địa điểm được phép", exact=False).wait_for()
            assert not any(item["path"].endswith("/revenue/orders") for item in safe_requests)
            page.screenshot(path=output / "02-group-selected-location-required.png")

            def scoped(res):
                parsed = urlsplit(res.url)
                return parsed.path == "/api/v1/revenue/order-status" and "location_id=2" in parsed.query

            with page.expect_response(
                lambda res: urlsplit(res.url).path == "/api/v1/revenue/orders"
                and "status_group=approved" in res.url
                and "location_id=2" in res.url
            ) as selected_orders:
                with page.expect_response(scoped) as scoped_status:
                    page.get_by_label("Location filter").select_option("2")
            status_response = scoped_status.value
            listed = selected_orders.value
            assert status_response.status == 200
            scoped_data = status_response.json()
            scoped_group = next(g for g in scoped_data["groups"] if g["key"] == "approved")
            assert scoped_data["total"]["orders"] == 5 and scoped_group["orders"] == 1
            page.get_by_role("button", name="Đã duyệt: 1 orders").wait_for()
            assert listed.status == 200, listed.status
            parsed = urlsplit(listed.url)
            query = parse_qs(parsed.query)
            assert query["status_group"] == ["approved"]
            assert query["location_id"] == ["2"] and query["view"] == ["store"]
            assert query["from"] == [PERIOD["from"]] and query["to"] == [PERIOD["to"]]
            assert query["page"] == ["1"]
            assert listed.json()["total"] == scoped_group["orders"]
            page.get_by_role("heading", name="Orders · Đã duyệt · store: Store 1").wait_for()
            page.get_by_text("SE-000001", exact=True).wait_for()
            assert page.get_by_role("columnheader", name="Customer").count() == 0
            assert "Test customer" not in page.get_by_label("Revenue order details").inner_text()
            page.screenshot(path=output / "03-group-orders-db-matched.png")

            persisted = evidence["postgres"]
            assert persisted["orders_all"] == agg["total"]["orders"]
            assert persisted["orders_store_1"] == scoped_data["total"]["orders"]
            evidence["drilldown"] = {
                "status_http": status_response.status,
                "orders_http": listed.status,
                "group": "approved",
                "store_location_id": 2,
                "group_orders": scoped_group["orders"],
                "list_total": listed.json()["total"],
                "page": query["page"][0],
            }
            evidence["result"] = "PASS"
        finally:
            evidence["http_evidence"] = safe_requests
            page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dsn_admin = _plain_dsn(os.environ.get("TEST_DATABASE_URL", ""))
    if urlsplit(dsn_admin).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Use only a disposable PostgreSQL 16 instance on loopback")
    args.output.mkdir(parents=True, exist_ok=True)
    db_name = "cfo_t30_" + secrets.token_hex(6)
    dsn = _with_database(dsn_admin, db_name)
    evidence = {
        "result": "FAIL",
        "task": "T30 / T27 step 12b",
        "fixture": "T29-style synthetic six order seed, NOT official T26",
        "app_now": APP_NOW,
        "market_timezone": ZONE,
        "period": PERIOD,
    }
    asyncio.run(_admin_exec(dsn_admin, f'CREATE DATABASE "{db_name}"'))
    try:
        command.upgrade(alembic_config(dsn), "head")
        password = secrets.token_urlsafe(22)
        seed_report(dsn, password)
        ledger = fetch(
            dsn,
            "SELECT status, count(*) AS n FROM ops.customer_order "
            "WHERE market_id=1 GROUP BY status ORDER BY status",
        )
        evidence["postgres"] = {
            "status_counts": {row["status"]: row["n"] for row in ledger},
            "orders_all": sum(row["n"] for row in ledger),
            "orders_store_1": fetch(
                dsn, "SELECT count(*) AS n FROM ops.customer_order WHERE origin_store_id=2"
            )[0]["n"],
        }
        api_port, web_port = loopback_port(), loopback_port()
        api, web = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
        api_env = os.environ | {
            "APP_ENV": "test",
            "APP_NOW": APP_NOW,
            "DATABASE_URL": async_url(dsn),
            "JWT_SECRET": secrets.token_urlsafe(32),
            "CORS_ORIGINS": json.dumps([web]),
        }
        web_env = os.environ | {"VITE_API_URL": f"{api}/api/v1", "VITE_USE_MOCKS": "false"}
        api_cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--no-access-log",
        ]
        vite_cmd = [
            "node",
            str(FRONTEND_DIR / "node_modules/vite/bin/vite.js"),
            "--host",
            "127.0.0.1",
            "--port",
            str(web_port),
            "--strictPort",
        ]
        with (
            local_service(api_cmd, BACKEND_DIR, api_env, f"{api}/api/v1/health", args.output / "api.log"),
            local_service(vite_cmd, FRONTEND_DIR, web_env, web, args.output / "vite.log"),
        ):
            browser_check(api, web, password, args.output, evidence)
    except Exception as exc:
        evidence["error_type"] = type(exc).__name__
        raise
    finally:
        (args.output / "t30-evidence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        asyncio.run(_admin_exec(dsn_admin, f'DROP DATABASE "{db_name}" WITH (FORCE)'))


if __name__ == "__main__":
    main()
