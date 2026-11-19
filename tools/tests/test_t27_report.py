"""Regression tests for aggregation of sanitized T27 evidence."""

import unittest

from tools.t27_report import markdown, summarize


def evidence(trips: int) -> dict:
    steps = [("START_PREP", None, "PREPARING"), ("GOODS_READY", None, "GOODS_READY")]
    steps.extend(
        ("LOADED", trip, "LOADED" if trip == trips else "GOODS_READY")
        for trip in range(1, trips + 1)
    )
    browser, persisted = [], []
    for event_id, (event_type, trip, order_status) in enumerate(steps, start=1):
        browser.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "payload": {"trip_id": trip} if trip is not None else {},
                "occurred_at": f"2026-11-10T10:05:0{event_id}+01:00",
                "order_status": order_status,
                "ack_refetch": {
                    "status": order_status,
                    "loaded_trips": list(range(1, (trip or 0) + 1)),
                },
            }
        )
        persisted.append(
            {
                "id": event_id,
                "event_type": event_type,
                "trip_id": trip,
                "occurred_at": f"2026-11-10T09:05:0{event_id}Z",
            }
        )
    return {
        "result": "PASS",
        "trip_count": trips,
        "order_no": f"SE-E3-{trips}T",
        "app_now": "2026-11-10T10:06:00+01:00",
        "market_timezone": "Europe/Stockholm",
        "warehouse_browser_status": "PASS",
        "events": browser,
        "persisted_events": persisted,
        "reload_queue": {"status": "LOADED", "loaded_trips": list(range(1, trips + 1))},
        "warehouse_postgres": {
            "order_status": "LOADED",
            "trips": [
                {"trip_id": trip, "status": "loading"} for trip in range(1, trips + 1)
            ],
            "milestones_match_browser": True,
        },
    }


class T27ReportTests(unittest.TestCase):
    def setUp(self):
        self.one, self.two = evidence(1), evidence(2)

    def ledger(self):
        return summarize(self.one, self.two, "synthetic-sha")

    def row(self, step: str):
        return next(row for row in self.ledger()["rows"] if row["step"] == step)

    def test_US_WH_04_AC1_requires_per_trip_postgres_state_and_keeps_step_12b(self):
        ledger = self.ledger()
        self.assertEqual(len(ledger["rows"]), 14)
        self.assertEqual(sum(row["step"] == "12b" for row in ledger["rows"]), 1)
        self.assertEqual(self.row("12b")["status"], "NOT VERIFIED")
        self.assertEqual(self.row("7")["status"], "PASS")
        self.two["warehouse_postgres"]["trips"][1]["status"] = "planned"
        self.assertEqual(self.row("7")["status"], "FAIL")

    def test_US_WH_04_AC1_reports_missing_db_state_as_unverified(self):
        self.two.pop("warehouse_postgres")
        self.assertEqual(self.row("7")["status"], "NOT VERIFIED")

    def test_US_WH_04_AC1_warehouse_pass_survives_later_driver_failure(self):
        self.two["result"] = "FAIL"
        self.two["t27"] = {"driver": [{"trip_id": 1, "status": "FAIL"}]}
        self.assertEqual(self.row("7")["status"], "PASS")
        self.assertEqual(self.row("8")["status"], "FAIL")

    def test_US_WH_04_AC1_matching_counts_cannot_hide_duplicate_loaded_trip(self):
        self.two["persisted_events"][-1]["trip_id"] = 1
        self.two["events"][-1]["payload"]["trip_id"] = 1
        self.assertEqual(self.row("7")["status"], "FAIL")

    def test_US_EXE_02_driver_failure_outranks_blocked_trip(self):
        self.one["t27"] = {"driver": [{"trip_id": 1, "status": "BLOCKED"}]}
        self.two["t27"] = {
            "driver": [
                {"trip_id": 1, "status": "BLOCKED"},
                {
                    "trip_id": 2,
                    "status": "FAIL",
                    "http": [{"http": 500, "error_code": "INTERNAL_ERROR"}],
                },
            ]
        }
        row = self.row("8")
        self.assertEqual(row["status"], "FAIL")
        self.assertEqual(
            row["http"][-1]["responses"],
            [{"http": 500, "error_code": "INTERNAL_ERROR"}],
        )
        self.assertEqual(row["http"][-1]["fixture"], "SE-E3-2T")

    def test_US_EXE_02_zero_accepted_dispatches_can_match_db_but_remain_blocked(self):
        self.one["t27"] = {
            "driver": [
                {"trip_id": 1, "status": "BLOCKED", "dispatch_status": "BLOCKED"}
            ],
            "postgres_dispatch_matches_browser": True,
            "persisted_dispatch": [],
        }
        self.assertEqual(self.row("8")["status"], "BLOCKED")
        self.assertFalse(self.ledger()["driver_dispatch_postgres_match"])
        self.one["t27"]["postgres_dispatch_matches_browser"] = False
        self.assertEqual(self.row("8")["status"], "FAIL")

    def test_US_EXE_02_keeps_dispatch_proof_when_later_driver_operation_fails(self):
        self.one["t27"] = {
            "driver": [
                {
                    "trip_id": 1,
                    "status": "FAIL",
                    "dispatch_status": "PASS",
                    "event_id": 10,
                    "reason": "Later driver operation failed",
                }
            ],
            "postgres_dispatch_matches_browser": True,
            "persisted_dispatch": [{"id": 10, "trip_id": 1}],
        }
        row = self.row("8")
        self.assertEqual(row["status"], "FAIL")
        self.assertIn("matched PostgreSQL for 1/3 trips", row["evidence"])
        self.assertIn("Later driver operation failed", row["evidence"])

    def test_cs_reports_lookup_and_eta_per_case_even_when_one_case_did_not_run(self):
        self.one["t27"] = {
            "cs": {
                "order_id": 1,
                "order_lookup": "PASS",
                "status": "BLOCKED",
                "http": [{"http": 500, "error_code": "INTERNAL_ERROR"}],
            }
        }
        self.assertEqual(self.row("11")["status"], "NOT VERIFIED")
        report = markdown(self.ledger())
        self.assertIn("SE-E3-1T order lookup PASS, ETA history BLOCKED", report)
        self.assertIn(
            "SE-E3-2T order lookup NOT VERIFIED, ETA history NOT VERIFIED", report
        )
        self.two["t27"] = self.one["t27"]
        self.assertEqual(self.row("11")["status"], "BLOCKED")

    def test_cs_eta_http_success_without_verified_rows_does_not_pass(self):
        self.one["t27"] = {
            "cs": {
                "order_id": 1,
                "order_lookup": "PASS",
                "status": "NOT VERIFIED",
                "eta_history": "GET 200; versioned ETA rows not yet compared with PostgreSQL",
            }
        }
        self.two["t27"] = self.one["t27"]
        self.assertTrue(self.ledger()["cs_lookup_api_match"])
        self.assertEqual(self.row("11")["status"], "NOT VERIFIED")

    def test_cs_failure_is_distinct_from_unrun(self):
        self.one["t27"] = {"cs": {"status": "FAIL"}}
        row = self.row("11")
        self.assertEqual(row["status"], "FAIL")
        self.assertEqual(row["http"][0]["order_lookup"], "FAIL")
        self.assertEqual(row["http"][0]["eta_history_status"], "NOT VERIFIED")
        self.assertEqual(row["http"][1]["order_lookup"], "NOT VERIFIED")


if __name__ == "__main__":
    unittest.main()
