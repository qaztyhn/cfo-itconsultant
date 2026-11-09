"""No-Docker unit tests for safe disposable database proof and evidence classification."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.demo_db_verify import (
    APP_NOW, Check, evaluate, safe_context, sync_outcome, verify,
)

ENV = {
    "APP_ENV": "test",
    "DEMO_DISPOSABLE": "1",
    "APP_NOW": APP_NOW,
    "COMPOSE_PROJECT_NAME": "cfo-demo-ci-synthetic",
    "SOURCE_SE_API_KEY": "synthetic-test-only",
}
SOURCE = "http://127.0.0.1:8100/api/v1"
GOOD = 2
NEG = 1
SNAPSHOT = {
    "good_count": 1,
    "good_min_version": GOOD,
    "good_max_version": GOOD,
    "good_route_count": 1,
    "good_route_version": GOOD,
    "negative_count": 0,
    "negative_route_count": 1,
    "negative_route_version": NEG,
}


class DemoDatabaseProofTests(unittest.TestCase):
    def test_US_INT_01_AC3_verifies_real_db_cardinality_and_source_version(self):
        checks = evaluate(dict(SNAPSHOT), GOOD, NEG)
        self.assertEqual(checks, [
            Check("postgres_once", "PASS", checks[0].detail),
            Check("postgres_legacy_negative", "PASS", checks[1].detail),
        ])

    def test_US_INT_01_AC3_never_treats_duplicate_or_stale_cfo_order_as_success(self):
        for change in (
            {"good_count": 0},
            {"good_count": 2},
            {"good_min_version": 1},
            {"good_max_version": 3},
            {"good_route_count": 0},
            {"good_route_version": 1},
        ):
            with self.subTest(change=change):
                self.assertEqual(evaluate({**SNAPSHOT, **change}, GOOD, NEG)[0].status, "FAIL")

    def test_US_INT_01_AC4_legacy_route_must_not_create_cfo_order(self):
        for change in (
            {"negative_count": 1},
            {"negative_route_count": 0},
            {"negative_route_count": 2},
            {"negative_route_version": 2},
        ):
            with self.subTest(change=change):
                self.assertEqual(evaluate({**SNAPSHOT, **change}, GOOD, NEG)[1].status, "FAIL")

    def test_US_INT_01_AC4_strict_numbers_no_string_or_boolean_database_evidence(self):
        self.assertEqual(evaluate({**SNAPSHOT, "good_count": "1"}, GOOD, NEG)[0].status, "FAIL")
        self.assertEqual(evaluate({**SNAPSHOT, "negative_count": False}, GOOD, NEG)[1].status, "FAIL")

    def test_US_INT_01_AC4_unsafe_environment_rejected(self):
        self.assertTrue(safe_context(ENV, SOURCE))
        for mutation in (
            {"APP_ENV": "production"},
            {"DEMO_DISPOSABLE": "0"},
            {"APP_NOW": "2026-11-09T10:05:00+01:00"},
            {"COMPOSE_PROJECT_NAME": "prod"},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(safe_context({**ENV, **mutation}, SOURCE))
        for url in (
            "https://real.example/api/v1",
            "http://internal.company/api/v1",
            "http://user:pass@127.0.0.1:8100/api/v1",
            "http://127.0.0.1:8100/api/v1?token=secret",
        ):
            with self.subTest(url=url):
                self.assertFalse(safe_context(ENV, url))

    def make_report(self, status: str, **changes):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "sync.json"
        checks = [
            {"check": key, "status": status if key == "sales_sync_write" else "PASS", "detail": ""}
            for key in ("sales_sync_write", "sync_idempotent", "sales_order_visible",
                        "dispatcher_order_visible", "unmapped_legacy_negative")
        ]
        for item in checks:
            if item["check"] in changes:
                item["status"] = changes[item["check"]]
        path.write_text(json.dumps({"schema": "demo-smoke-v1", "app_now": APP_NOW, "checks": checks}))
        return path

    def test_US_INT_01_AC2_blocked_sync_never_queries_database_or_invents_cfo_order(self):
        report = self.make_report("BLOCKED")
        with patch("tools.demo_db_verify.database_snapshot") as db, patch("tools.demo_db_verify.source_version") as src:
            result = verify(ENV, SOURCE, report)
        self.assertEqual([check.status for check in result], ["BLOCKED", "NOT VERIFIED"])
        db.assert_not_called()
        src.assert_not_called()

    def test_US_INT_01_AC2_unsafe_context_never_reads_source_or_database(self):
        report = self.make_report("PASS")
        with patch("tools.demo_db_verify.database_snapshot") as db, patch("tools.demo_db_verify.source_version") as src:
            result = verify({**ENV, "APP_ENV": "production"}, SOURCE, report)
        self.assertEqual(result[0].status, "FAIL")
        db.assert_not_called()
        src.assert_not_called()

    def test_US_INT_01_AC3_requires_all_http_scope_and_retry_proofs_before_db(self):
        report = self.make_report("PASS", unmapped_legacy_negative="FAIL")
        self.assertEqual(sync_outcome(report), "FAIL")
        with patch("tools.demo_db_verify.database_snapshot") as db:
            self.assertEqual(verify(ENV, SOURCE, report)[0].status, "FAIL")
        db.assert_not_called()

    def test_US_INT_01_AC3_validated_http_and_source_versions_then_database(self):
        report = self.make_report("PASS")
        with patch("tools.demo_db_verify.database_snapshot", return_value=SNAPSHOT) as db, patch(
            "tools.demo_db_verify.source_version", return_value=(GOOD, NEG)
        ) as src:
            result = verify(ENV, SOURCE, report)
        self.assertEqual([x.status for x in result], ["PASS", "PASS"])
        db.assert_called_once_with(ENV["COMPOSE_PROJECT_NAME"])
        src.assert_called_once_with(SOURCE, ENV["SOURCE_SE_API_KEY"])

    def test_US_INT_01_AC4_database_failure_not_reported_as_success(self):
        report = self.make_report("PASS")
        with patch("tools.demo_db_verify.source_version", return_value=(GOOD, NEG)), patch(
            "tools.demo_db_verify.database_snapshot", side_effect=ValueError("secret-sql-error")
        ):
            result = verify(ENV, SOURCE, report)
        self.assertEqual(result[0].status, "FAIL")
        self.assertNotIn("secret-sql-error", result[0].detail)

    def test_US_INT_01_AC2_malformed_or_absent_sync_report_denied(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        report = Path(tmp.name) / "missing"
        self.assertEqual(sync_outcome(report), "FAIL")
        report.write_text("{}")
        self.assertEqual(sync_outcome(report), "FAIL")


if __name__ == "__main__":
    unittest.main()
