"""Replay T27 reporting steps on the official isolated T26 seed."""

from __future__ import annotations

import argparse
import json
import os
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


def kpi(browser, password: str, output: Path, fixture: dict) -> dict:
    period = fixture["period"]
    page = demo.login(browser, "/kpi?from=" + period["from"] + "&to=" + period["to"],
                      "projectlead@cfo.demo", password, output, "Project lead")
    try:
        with page.expect_response(lambda r: urlsplit(r.url).path == "/api/v1/kpi/summary") as got:
            page.reload()
        if got.value.status != 200:
            raise EvidenceMismatch(f"KPI summary HTTP {got.value.status}")
        metrics = got.value.json()["metrics"]
        expect(page.get_by_label("Operational KPIs")).to_be_visible()
        page.get_by_label("Operational KPIs").screenshot(path=output / "12-kpi.png")
        missing = sorted(R3_KPI - metrics.keys())
        legacy = sorted(metrics.keys() - R3_KPI)
        by_path = all(set(metrics.get(key, {}).get("by_path", {})) == {"sales", "dispatcher"}
                      for key in ("planning_time_min", "plan_acceptance_rate"))
        eta = metrics.get("eta_error_min", {})
        eta_r3 = {"median", "p90", "target"} <= eta.keys() and "baseline" not in eta
        return {
            "status": "PASS" if not missing and not legacy and by_path and eta_r3 else "BLOCKED",
            "http": 200, "period": period, "metric_keys": sorted(metrics),
            "missing_r3_metrics": missing, "legacy_metrics": legacy,
            "sales_dispatcher_breakdown": by_path, "eta_median_p90_target": eta_r3,
        }
    finally:
        page.close()


def sales_rank_probe(browser, password: str, output: Path, fixture: dict) -> dict:
    source_ref = next(ref for ref, scenario in fixture["source_cases"].items()
                      if scenario["purpose"] == "sales_rank_2")
    page = demo.login(browser, "/store/sync-check", "sales@cfo.demo", password, output, "Sales")
    try:
        page.get_by_label("External POS order reference").fill(source_ref)
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == "/api/v1/integration/orders/sync-now") as synced:
            page.get_by_role("button", name="Sync & check routing").click()
        sync = synced.value.json()
        order_id = sync.get("order_id")
        if synced.value.status != 200 or sync.get("routing_status") != "cfo" or type(order_id) is not int:
            return {"status": "BLOCKED", "source_ref": source_ref, "sync": demo.metadata(synced.value)}
        with page.expect_response(lambda r: r.request.method == "POST" and
                                  urlsplit(r.url).path == f"/api/v1/orders/{order_id}/plan") as planned:
            page.get_by_role("button", name="Check feasibility").click()
        response = planned.value
        info = {"status": "BLOCKED", "source_ref": source_ref, "order_id": order_id,
                "sync": demo.metadata(synced.value), "plan": demo.metadata(response)}
        if response.status == 200:
            payload = response.json()
            info.update(available_ranks=[plan["rank"] for plan in payload["plans"]], result=payload["result"])
            result = page.get_by_role("region", name="Sales planning result")
            expect(result).to_be_visible()
            info["rank_one_only_notice"] = result.get_by_text("Rank-1 plan, one truck", exact=False).count() == 1
            result.screenshot(path=output / "03-sales-rank-probe.png")
        info["completion_evidence"] = "Sales rank 2 approval and audit belong to the T19 acceptance replay."
        return info
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
    args.output.mkdir(parents=True, exist_ok=False)
    result = {"revision": demo.stage_report()["revision"], "seed_version": seed["version"], "steps": {}}
    with demo.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        try:
            for step, run in (
                ("12", lambda: kpi(browser, password, args.output, fixture)),
                ("12b", lambda: revenue(browser, password, args.output, fixture, seed)),
                ("3", lambda: sales_rank_probe(browser, password, args.output, fixture)),
            ):
                try:
                    result["steps"][step] = run()
                except (AssertionError, EvidenceMismatch, demo.Error, KeyError, ValueError) as exc:
                    result["steps"][step] = {"status": "FAIL", "error_type": type(exc).__name__}
        finally:
            browser.close()
            payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            (args.output / "t27-reporting.json").write_text(payload, encoding="utf-8")
            print(payload)
    if any(row["status"] == "FAIL" for row in result["steps"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
