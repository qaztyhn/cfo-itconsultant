"""Replay T27 reporting steps on the official isolated T26 seed."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values
from playwright.sync_api import expect

from tools import t27_integrated_browser as demo
from tools.t26_verify import FIXTURE, expected
from tools.t27_driver_step8 import EvidenceMismatch

LABELS = {
    "approved": "Đã duyệt",
    "in_transit": "Đang vận chuyển",
    "completed": "Đã hoàn thành",
    "failed": "Thất bại",
    "cancelled": "Đã hủy",
}
R3_KPI = {
    "planning_time_min", "on_time_rate", "plan_acceptance_rate",
    "manual_intervention_rate", "eta_error_min",
}


def report_response(response, endpoint: str, **filters: str) -> bool:
    parsed = urlsplit(response.url)
    query = parse_qs(parsed.query)
    return parsed.path == f"/api/v1/revenue/{endpoint}" and all(
        query.get(key) == [value] for key, value in filters.items()
    )


def revenue(browser, password: str, output: Path, fixture: dict, seed: dict) -> dict:
    period = fixture["period"]
    rows = fixture["report_orders"]
    by_group = expected(rows)
    recognised = sum(Decimal(row[2]) for row in rows if row[1] == "DELIVERED")
    page = demo.login(browser, "/revenue", "owner@cfo.demo", password, output, "Business owner")
    try:
        expect(page.get_by_role("heading", name="Đơn hàng & doanh thu")).to_be_visible()
        page.get_by_label("From date").fill(period["from"])
        with (
            page.expect_response(lambda r: report_response(r, "order-status", **period)) as grouped,
            page.expect_response(lambda r: report_response(r, "summary", **period)) as totals,
        ):
            page.get_by_label("To date").fill(period["to"])
        group_data, summary = grouped.value.json(), totals.value.json()
        actual = {row["key"]: (row["orders"], Decimal(row["amount"])) for row in group_data["groups"]}
        if (grouped.value.status, totals.value.status) != (200, 200) or actual != {
            key: (row["orders"], Decimal(row["amount"])) for key, row in by_group.items()
        } or group_data["total"]["orders"] != len(rows) or Decimal(summary["recognised"]) != recognised:
            raise EvidenceMismatch("T26 period, group totals or recognised revenue mismatch")
        for key, label in LABELS.items():
            expect(page.get_by_role("button", name=f"{label}: {by_group[key]['orders']} orders")).to_be_visible()
        primary = page.get_by_label("Primary order and revenue metrics")
        expect(primary.get_by_text(f"{recognised.normalize():f} SEK", exact=True)).to_be_visible()
        primary.screenshot(path=output / "12b-revenue-totals.png")
        page.get_by_label("Order status groups").screenshot(path=output / "12b-revenue-groups.png")

        store = "ST-001"
        location = str(seed["stores"][store])
        scoped = expected([row for row in rows if row[3] == store])
        page.get_by_role("button", name=f"{LABELS['approved']}: {by_group['approved']['orders']} orders").click()
        with page.expect_response(lambda r: report_response(
            r, "orders", **period, view="store", location_id=location, status_group="approved"
        )) as listed:
            page.get_by_label("Location filter").select_option(location)
        details = page.get_by_label("Revenue order details")
        scoped_list = listed.value.json()
        numbers = scoped["approved"]["order_nos"]
        if listed.value.status != 200 or sorted(row["order_no"] for row in scoped_list["items"]) != numbers:
            raise EvidenceMismatch("T26 location drilldown order numbers did not match")
        for order_no in numbers:
            expect(details.get_by_text(order_no, exact=True)).to_be_visible()
        expect(details.get_by_role("columnheader", name="Customer")).to_have_count(0)
        return {
            "status": "PASS", "http": [200, 200, 200], "period": period,
            "orders": len(rows), "groups": by_group, "recognised_sek": str(recognised),
            "drilldown": {"store": store, "group": "approved", "order_nos": numbers},
        }
    finally:
        page.close()


SALES_REF = "SE-2026-000123"
OPS_ACCOUNT = "admin@cfo.demo"
KPI_ORDER = ("planning_time_min", "on_time_rate", "plan_acceptance_rate",
             "manual_intervention_rate", "eta_error_min")
NO_DATA = "Chưa có dữ liệu"


def _close(actual: object, expected_value: float | None) -> bool:
    if expected_value is None or actual is None:
        return actual is None and expected_value is None
    return isinstance(actual, (int, float)) and abs(float(actual) - expected_value) < 1e-9


def pg_on_time_by_day(period: dict, env: dict[str, str]) -> dict[str, float | None]:
    """Independent PostgreSQL recomputation of daily on-time rate (market-local days)."""
    rows = demo.sql(
        "SELECT d::text||'|'||total||'|'||hits||'|'||incomplete FROM ("
        "SELECT (o.delivered_at AT TIME ZONE m.timezone)::date AS d, count(*) AS total, "
        "count(*) FILTER (WHERE o.promise_start IS NOT NULL AND o.promise_end IS NOT NULL "
        "AND o.delivered_at BETWEEN o.promise_start AND o.promise_end) AS hits, "
        "count(*) FILTER (WHERE o.promise_start IS NULL OR o.promise_end IS NULL) AS incomplete "
        "FROM ops.customer_order o JOIN ref.market m ON m.id=o.market_id "
        "WHERE m.code='SE' AND o.status='DELIVERED' AND o.delivered_at IS NOT NULL "
        f"AND (o.delivered_at AT TIME ZONE m.timezone)::date BETWEEN DATE '{period['from']}' "
        f"AND DATE '{period['to']}' GROUP BY 1) t ORDER BY d", env,
    )
    result: dict[str, float | None] = {}
    for line in rows.splitlines():
        day, total, hits, incomplete = line.split("|")
        result[day] = None if int(incomplete) else int(hits) / int(total)
    return result


def pg_manual_rate(period: dict, env: dict[str, str]) -> float | None:
    """Independent recomputation: committed orders whose approving plan was manual."""
    row = demo.sql(
        "SELECT count(*)||'|'||count(*) FILTER (WHERE p.status='manual' OR p.manual_reason_code IS NOT NULL "
        "OR EXISTS (SELECT 1 FROM audit.decision_log d WHERE d.plan_id=p.id AND d.action='MANUAL_PLAN_CREATED')) "
        "FROM ops.customer_order o JOIN ref.market m ON m.id=o.market_id "
        "JOIN plan.fulfilment_plan p ON p.id=o.approved_plan_id "
        "WHERE m.code='SE' AND o.committed_date IS NOT NULL AND o.approved_at IS NOT NULL "
        f"AND (o.approved_at AT TIME ZONE m.timezone)::date BETWEEN DATE '{period['from']}' "
        f"AND DATE '{period['to']}'", env,
    )
    total, manual = (int(value) for value in row.split("|"))
    return manual / total if total else None


def kpi(browser, password: str, output: Path, fixture: dict, env: dict[str, str]) -> dict:
    period = fixture["period"]
    # Ops/admin KPI scope (Project lead has no ops scope and is not the T22 reviewer).
    page = demo.login(browser, "/kpi?from=" + period["from"] + "&to=" + period["to"],
                      OPS_ACCOUNT, password, output, "Ops/Admin")
    try:
        with (
            page.expect_response(lambda r: urlsplit(r.url).path == "/api/v1/kpi/summary") as got,
            page.expect_response(lambda r: urlsplit(r.url).path == "/api/v1/kpi/daily") as trend,
        ):
            page.reload()
        if (got.value.status, trend.value.status) != (200, 200):
            raise EvidenceMismatch(f"KPI HTTP summary={got.value.status} daily={trend.value.status}")
        summary_body, daily_body = got.value.json(), trend.value.json()
        metrics = summary_body["metrics"]
        expect(page.get_by_label("Operational KPIs")).to_be_visible()
        cards = page.locator("section[data-metric]")
        expect(cards).to_have_count(5)
        shown = [cards.nth(i).get_attribute("data-metric") for i in range(5)]
        missing = sorted(R3_KPI - metrics.keys())
        legacy = sorted(metrics.keys() - R3_KPI)
        by_path = all(set(metrics.get(key, {}).get("by_path", {})) == {"sales", "dispatcher"}
                      for key in ("planning_time_min", "plan_acceptance_rate"))
        eta = metrics.get("eta_error_min", {})
        eta_r3 = ({"median", "p90", "target"} <= eta.keys() and "baseline" not in eta
                  and eta["target"] == {"median": 20, "p90": 60})
        # No measurement source exists for these in the demo data: null and the contract text.
        eta_card = page.locator('section[data-metric="eta_error_min"]')
        plan_card = page.locator('section[data-metric="planning_time_min"]')
        expect(eta_card).to_contain_text("Target: median 20 min · P90 60 min")
        null_ui = {}
        if eta["median"] is None and eta["p90"] is None:
            expect(eta_card).to_contain_text("Median " + NO_DATA)
            null_ui["eta_error_min"] = NO_DATA
        if metrics["planning_time_min"]["value"] is None:
            expect(plan_card).to_contain_text(NO_DATA)
            null_ui["planning_time_min"] = NO_DATA
        # Reconcile the values the API derives with an independent PostgreSQL query.
        pg_daily = pg_on_time_by_day(period, env)
        api_daily = {point["day"]: point["value"] for point in daily_body["points"]}
        if daily_body["metric"] != "on_time_rate":
            raise EvidenceMismatch("KPI daily metric differs from requested trend metric")
        daily_ok = all(_close(api_daily.get(day), pg_daily.get(day)) for day in api_daily)
        observed = {day: value for day, value in api_daily.items() if value is not None}
        if not observed or set(observed) != {d for d, v in pg_daily.items() if v is not None}:
            raise EvidenceMismatch("KPI daily has no PostgreSQL-backed observation")
        incomplete = any(value is None for value in pg_daily.values())
        totals = demo.sql(
            "SELECT count(*)||'|'||count(*) FILTER (WHERE promise_start IS NOT NULL AND promise_end IS NOT NULL "
            "AND delivered_at BETWEEN promise_start AND promise_end) FROM ops.customer_order o "
            "JOIN ref.market m ON m.id=o.market_id WHERE m.code='SE' AND o.status='DELIVERED' "
            "AND o.delivered_at IS NOT NULL "
            f"AND (o.delivered_at AT TIME ZONE m.timezone)::date BETWEEN DATE '{period['from']}' "
            f"AND DATE '{period['to']}'", env,
        )
        total, hits = (int(value) for value in totals.split("|"))
        expected_on_time = None if incomplete or not total else hits / total
        manual_expected = pg_manual_rate(period, env)
        reconciled = {
            "on_time_rate_summary": _close(metrics["on_time_rate"]["value"], expected_on_time),
            "on_time_rate_daily": daily_ok,
            "manual_intervention_rate_summary": _close(
                metrics["manual_intervention_rate"]["value"], manual_expected),
        }
        page.get_by_label("Operational KPIs").screenshot(path=output / "12-kpi.png")
        status = "PASS" if (not missing and not legacy and by_path and eta_r3 and all(reconciled.values())
                            and sorted(shown) == sorted(R3_KPI)) else "FAIL"
        return {
            "status": status, "http": [200, 200], "account_scope": "ops/admin", "period": period,
            "metric_keys": sorted(metrics), "cards_in_ui": sorted(shown),
            "missing_r3_metrics": missing, "legacy_metrics": legacy,
            "sales_dispatcher_breakdown": by_path, "eta_median_p90_target": eta_r3,
            "null_values_shown_as": null_ui, "postgres_reconciliation": reconciled,
            "daily_observed_days": sorted(observed),
        }
    finally:
        page.close()


def reporting_env(parser: argparse.ArgumentParser) -> dict[str, str]:
    """Environment for the isolated cfo-demo-t26 Compose project (same rules as the browser runner)."""
    data = dotenv_values(demo.ROOT / ".env")
    env = dict(os.environ)
    env.update({key: value for key, value in data.items() if value is not None})
    env.update(
        APP_NOW=demo.NOW,
        COMPOSE_PROJECT_NAME=demo.T26_PROJECT,
        COMPOSE_FILE=os.pathsep.join(("docker-compose.yml", "tools/t27_e1_compose.override.yml")),
        DEMO_D7_FIXTURE_DIR="",
        SYNTHETIC_WMS_API_KEY=env.get("SYNTHETIC_WMS_API_KEY") or secrets.token_urlsafe(32),
        MSYS_NO_PATHCONV="1",
        PYTHONPATH=os.pathsep.join(filter(None, (str(demo.ROOT), str(demo.ROOT / "backend"),
                                                 env.get("PYTHONPATH")))),
    )
    return env


def sales_rank2_approve(browser, password: str, output: Path, env: dict[str, str]) -> dict:
    """Step 3: Sales selects rank 2 for SE-2026-000123 in the UI and approves it (T19, DEC-R3-10)."""
    # Planning clock for Sales/Approve; WMS preparation asserts the container already runs it.
    demo.compose("up", "-d", "--no-deps", "--no-build", "--force-recreate", "--wait",
                 "--wait-timeout", "90", "cfo-api", env=env)
    page = demo.login(browser, "/store/sync-check", "sales@cfo.demo", password, output, "Sales")
    try:
        expect(page.get_by_role("heading", name="Sync & Check")).to_be_visible()
        page.get_by_label("External POS order reference").fill(SALES_REF)
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == "/api/v1/integration/orders/sync-now") as synced:
            page.get_by_role("button", name="Sync & check routing").click()
        sync = synced.value.json() if synced.value.ok else {}
        order_id = sync.get("order_id")
        if sync.get("routing_status") != "cfo" or type(order_id) is not int:
            raise EvidenceMismatch(f"Sales Sync HTTP {synced.value.status} did not route to CFO")
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == f"/api/v1/orders/{order_id}/plan",
                                  timeout=60000) as planned:
            page.get_by_role("button", name="Check feasibility").click()
        if planned.value.status != 200:
            raise EvidenceMismatch(f"Sales planning HTTP {planned.value.status}")
        run = planned.value.json()
        rank2 = [plan for plan in run.get("plans") or [] if plan.get("rank") == 2]
        if run.get("result") != "feasible" or len(rank2) != 1:
            return {"status": "BLOCKED", "source_ref": SALES_REF, "order_id": order_id,
                    "available_ranks": sorted(p.get("rank") for p in run.get("plans") or []),
                    "result": run.get("result"),
                    "detail": "Planner did not return exactly one rank-2 plan to select."}
        plan_id = rank2[0]["id"]
        expect(page.get_by_role("heading", name="Feasible — not confirmed")).to_be_visible()
        # Documented T19 helper: exact proposed plan + loopback simulated WMS in the same project.
        demo.prepare_t26_wms(env, SALES_REF, plan_id, 2)
        page.get_by_label("Rank 2", exact=True).check()
        reason_code = "other"
        page.get_by_label("Alternative reason code").fill(reason_code)
        agreement = page.get_by_label("Customer date agreement")
        if agreement.count():
            page.get_by_role("button", name="Record customer agreement").click()
            expect(page.get_by_role("button", name="Agreed date recorded")).to_be_visible()
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == f"/api/v1/plans/{plan_id}/approve",
                                  timeout=60000) as approved:
            page.get_by_role("button", name="Approve rank 2").click()
        response = approved.value
        info = demo.metadata(response)
        db = demo.sql(
            "SELECT p.status||'|'||o.status||'|'||COALESCE(o.approved_plan_id::text,'')||'|'||"
            "COALESCE(d.actor_role,'')||'|'||COALESCE(d.snapshot->>'rank','')||'|'||"
            "COALESCE(d.reason_code,'')||'|'||"
            "(SELECT count(*) FROM ops.notification n WHERE n.order_id=o.id AND n.template='CONFIRMED') "
            "FROM plan.fulfilment_plan p JOIN ops.customer_order o ON o.id=p.order_id "
            "LEFT JOIN audit.decision_log d ON d.order_id=o.id AND d.plan_id=p.id AND d.action='PLAN_APPROVED' "
            f"WHERE o.external_ref='{SALES_REF}' AND p.id={plan_id}", env,
        )
        screenshot_name = "03-sales-rank2-approved.png" if response.ok else "03-sales-rank2-rejected.png"
        demo.screenshot(page, output, screenshot_name)
        parts = db.splitlines()[0].split("|") if db else []
        passed = (response.status == 200 and parts == [
            "approved", "APPROVED", str(plan_id), "sales", "2", reason_code, "1"])
        return {
            "status": "PASS" if passed else "FAIL", "source_ref": SALES_REF, "order_id": order_id,
            "plan_id": plan_id, "rank": 2, "reason_code": reason_code, "approve": info,
            "postgres": dict(zip(("plan_status", "order_status", "approved_plan_id", "audit_actor_role",
                                  "audit_rank", "audit_reason_code", "confirmed_count"), parts)),
            "date_agreement_recorded": bool(agreement.count()),
        }
    finally:
        page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env = os.environ
    if (env.get("APP_ENV"), env.get("DEMO_DISPOSABLE"), env.get("COMPOSE_PROJECT_NAME")) != (
        "test", "1", "cfo-demo-t26",
    ):
        parser.error("Use the isolated cfo-demo-t26 stack")
    password = dotenv_values(demo.ROOT / ".env").get("SEED_DEMO_PASSWORD")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    seed = json.loads(args.seed_report.read_text(encoding="utf-8"))
    if not password or seed["version"] != fixture["version"] or seed["report_rows"] != len(fixture["report_orders"]):
        parser.error("Fresh official T26 seed report and demo credentials required")
    run_env = reporting_env(parser)
    args.output.mkdir(parents=True, exist_ok=False)
    result = {"revision": demo.stage_report()["revision"], "seed_version": seed["version"], "steps": {}}
    with demo.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        try:
            for step, run in (
                ("12", lambda: kpi(browser, password, args.output, fixture, dict(env))),
                ("12b", lambda: revenue(browser, password, args.output, fixture, seed)),
                # Last: it recreates cfo-api on the T19 planning clock and starts the loopback WMS.
                ("3", lambda: sales_rank2_approve(browser, password, args.output, run_env)),
            ):
                try:
                    result["steps"][step] = run()
                except (AssertionError, EvidenceMismatch, demo.Error, KeyError, ValueError,
                        RuntimeError, subprocess.TimeoutExpired) as exc:
                    # Static diagnostic only: first line, no request bodies or customer fields.
                    result["steps"][step] = {"status": "FAIL", "error_type": type(exc).__name__,
                                             "detail": str(exc).splitlines()[0][:300] if str(exc) else ""}
        finally:
            browser.close()
            payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            (args.output / "t27-reporting.json").write_text(payload, encoding="utf-8")
            print(payload)
    if any(row["status"] == "FAIL" for row in result["steps"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
