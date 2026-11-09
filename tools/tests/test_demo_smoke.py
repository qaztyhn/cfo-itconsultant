"""Pure control tests for the actual localhost-HTTP demo probe (no external calls)."""

from __future__ import annotations

import unittest
from pathlib import Path
from runpy import run_path

from tools.demo_smoke import APP_NOW, GOOD_REF, UNMAPPED_REF, Http, Result, allow_mutation, run, verdict

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = run_path(str(ROOT / "backend" / "app" / "seed" / "scenarios.py"))["generate"]()


class FakeHttp:
    def __init__(self, *, routed: bool = False) -> None:
        self.routed = routed
        self.calls: list[tuple[str, str, object, object]] = []
        # Source API adds version on top of the generator's input manifest.
        self.good = {**next(o for o in FIXTURE["orders"] if o["id"] == GOOD_REF), "version": 1}
        self.bad = {**next(o for o in FIXTURE["orders"] if o["id"] == UNMAPPED_REF), "version": 1}

    def send(self, url: str, *, method: str = "GET", headers=None, body=None):
        self.calls.append((method, url, body, headers))
        if url.endswith("/health"):
            return 200, {"status": "ok", "db": "ok"}
        if url.endswith(":5173/"):
            return 200, None
        if "/orders?status=SUBMITTED_FOR_PLANNING" in url:
            return 200, {"items": [self.good, self.bad, {
                **next(o for o in FIXTURE["orders"] if o["id"].endswith("000137")), "version": 1,
            }]}
        if url.endswith("/orders?page_size=1"):
            return (400 if ":8100/" in url else 401), None
        if url.endswith("/orders?page_size=2"):
            return 200, {"items": [], "page": 1, "page_size": 2, "total": 0}
        if "/auth/login" in url:
            name = body["email"].split("@")[0]
            role = {"sales": "sales", "dispatcher": "dispatcher", "wm.got": "warehouse", "driver1": "driver"}[name]
            return 200, {"access_token": "internal-test-token", "user": {"roles": [role], "market": "SE"}}
        if "/integration/orders/sync-now" in url:
            if not self.routed:
                return 404, None
            if body["external_ref"] == UNMAPPED_REF:
                return 200, {"external_ref": UNMAPPED_REF, "routing_status": "legacy"}
            return 200, {"external_ref": GOOD_REF, "routing_status": "cfo", "order_id": 9, "source_version": 1}
        if url.endswith("/orders/9"):
            return 200, {"external_ref": GOOD_REF, "id": 9}
        if url.endswith("/orders/9/plan"):
            return 409, None
        return 401, None


ENV = {"SOURCE_SE_API_KEY": "synthetic-only", "SEED_DEMO_PASSWORD": "synthetic-only"}
URLS = ("http://127.0.0.1:8100/api/v1", "http://127.0.0.1:8000/api/v1", "http://127.0.0.1:5173")


class DemoSmokeTests(unittest.TestCase):
    def test_US_SRC_01_AC1_http_probe_accepts_real_html_frontend_response(self):
        class HtmlResponse:
            status = 200
            headers = {"Content-Type": "text/html; charset=UTF-8"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self, _max_size):
                return b"<!doctype html><html><body>CFO demo</body></html>"

        class HtmlOpener:
            def open(self, *_args, **_kwargs):
                return HtmlResponse()

        client = Http()
        client.opener = HtmlOpener()
        self.assertEqual(client.send("http://127.0.0.1:5173/"), (200, None))

    def test_US_SRC_01_AC1_read_only_no_mutations_and_source_auth_negative(self):
        http = FakeHttp()
        result = run(http, *URLS, environ=ENV)
        checks = {item.check: item.status for item in result}
        self.assertEqual(checks["source_fixture"], "PASS")
        self.assertEqual(checks["source_auth_negative"], "PASS")
        self.assertEqual(checks["role_sales"], "PASS")
        self.assertEqual(checks["role_dispatcher"], "PASS")
        self.assertEqual(checks["role_warehouse"], "PASS")
        self.assertEqual(checks["role_driver"], "PASS")
        self.assertEqual(checks["sales_sync_write"], "NOT VERIFIED")
        self.assertEqual(verdict(result), 2)
        self.assertFalse(any(method == "POST" and "/auth/login" not in url for method, url, _, _ in http.calls))

    def test_US_INT_01_AC2_sync_endpoint_missing_is_blocked_not_success(self):
        http = FakeHttp()
        env = {**ENV, "APP_ENV": "test", "DEMO_DISPOSABLE": "1", "APP_NOW": APP_NOW}
        results = run(http, *URLS, write=True, environ=env)
        checks = {item.check: item.status for item in results}
        self.assertEqual(checks["sales_sync_write"], "BLOCKED")
        self.assertEqual(checks["planning_approval"], "BLOCKED")
        self.assertEqual(verdict(results), 2)

    def test_US_INT_01_AC3_sync_reuses_exact_key_and_checks_scope_negative(self):
        class RecordingHttp(FakeHttp):
            def send(self, url, *, method="GET", headers=None, body=None):
                if "/integration/orders/sync-now" in url and not self.routed:
                    self.routed = True
                return super().send(url, method=method, headers=headers, body=body)

        http = RecordingHttp(routed=True)
        env = {**ENV, "APP_ENV": "test", "DEMO_DISPOSABLE": "1", "APP_NOW": APP_NOW}
        results = run(http, *URLS, write=True, environ=env)
        checks = {item.check: item.status for item in results}
        self.assertEqual(checks["sales_sync_write"], "PASS")
        self.assertEqual(checks["sync_idempotent"], "PASS")
        self.assertEqual(checks["unmapped_legacy_negative"], "PASS")
        self.assertEqual(checks["planning_run"], "BLOCKED")
        self.assertEqual(checks["postgres_once"], "NOT VERIFIED")
        sync_calls = [(body, headers) for method, url, body, headers in http.calls
                      if method == "POST" and url.endswith("/integration/orders/sync-now")]
        self.assertEqual(len(sync_calls), 3)
        self.assertEqual(sync_calls[0][0], sync_calls[1][0])
        self.assertEqual(sync_calls[0][1]["Idempotency-Key"], sync_calls[1][1]["Idempotency-Key"])

    def test_US_INT_01_AC4_remote_urls_and_unsafe_write_rejected_without_network(self):
        safe = {**ENV, "APP_ENV": "test", "DEMO_DISPOSABLE": "1", "APP_NOW": APP_NOW}
        self.assertTrue(allow_mutation(safe, list(URLS)))
        for unsafe in ({**safe, "APP_ENV": "production"}, {**safe, "DEMO_DISPOSABLE": "0"},
                       {**safe, "APP_NOW": "2026-11-09T10:05:00+01:00"}):
            http = FakeHttp()
            result = run(http, *URLS, write=True, environ=unsafe)
            self.assertEqual(result[0].status, "FAIL")
            self.assertEqual(http.calls, [])
        http = FakeHttp()
        result = run(http, "https://example.com/api/v1", *URLS[1:], environ=ENV)
        self.assertEqual(result[0].status, "FAIL")
        self.assertEqual(http.calls, [])

    def test_US_SRC_01_AC5_existing_seed_not_promoted_to_compliance(self):
        self.assertEqual(FIXTURE["app_now"], APP_NOW)
        self.assertEqual(len(FIXTURE["orders"]), 18)
        self.assertEqual(len(FIXTURE["stock_snapshot"]["items"]), 300)
        self.assertEqual(FIXTURE["vehicle_calendar"][0]["kind"], "external_booking")
        self.assertTrue(all(row["verified"] is False for row in FIXTURE["driver_history"]))
        self.assertTrue(all(row["reg_561_scope"] == "unknown" for row in FIXTURE["driver_history"]))
        self.assertTrue(any(o["id"] == GOOD_REF and o["store_code"] == "ST-001" for o in FIXTURE["orders"]))
        self.assertTrue(any(o["id"] == UNMAPPED_REF and o["store_code"] == "ST-001" for o in FIXTURE["orders"]))

    def test_verdict_never_converts_blocked_into_pass(self):
        self.assertEqual(verdict([Result("a", "PASS", "ok")]), 0)
        self.assertEqual(verdict([Result("a", "PASS", "ok"), Result("b", "BLOCKED", "missing")]), 2)
        self.assertEqual(verdict([Result("a", "NOT VERIFIED", "missing")]), 2)
        self.assertEqual(verdict([Result("a", "FAIL", "wrong")]), 1)


if __name__ == "__main__":
    unittest.main()
