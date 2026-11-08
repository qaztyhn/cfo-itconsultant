"""D7 independent fixture contracts; no DB, API, engine, or legal-rule implementation."""

from __future__ import annotations

import copy
import hashlib
import unittest
from datetime import UTC, datetime

from generate import FIXTURES, build, encoded, generate
from validate import FixtureError, instant, read_payloads, validate


class D7FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payloads = read_payloads()
        cls.by_id = {row["scenario_id"]: row for row in cls.payloads["scenarios.json"]["records"]}

    def test_D7_approved_population_and_56_day_coverage(self) -> None:
        count = validate(self.payloads)
        self.assertEqual(count, {"vehicles": 9, "drivers": 10, "history_days": 56,
                                 "history_rows": 560, "future_shifts": 51, "scenarios": 13})

    def test_D7_determinism_and_committed_snapshot(self) -> None:
        self.assertEqual(generate(check=True), [])
        a = {name: hashlib.sha256(encoded(value)).hexdigest() for name, value in build().items()}
        b = {name: hashlib.sha256(encoded(value)).hexdigest() for name, value in build().items()}
        self.assertEqual(a, b)
        self.assertEqual(set(a), {x.name for x in FIXTURES.glob("*.json")})

    def test_D7_payload_mass_is_not_max_permissible_mass(self) -> None:
        vs = self.payloads["vehicles.json"]["records"]
        van = next(x for x in vs if x["vehicle_code"] == "GBG-03-02")
        self.assertEqual((van["capacity_kg"], van["max_permissible_mass_kg"]), (1000, 3500))
        self.assertTrue(all(0 < x["capacity_kg"] < x["max_permissible_mass_kg"] for x in vs))

    def test_D7_scope_preserved_as_explicit_three_way_value(self) -> None:
        vs = self.payloads["vehicles.json"]["records"]
        self.assertEqual({x["regulation_561_scope"] for x in vs},
                         {"in_scope", "out_of_scope", "unknown"})
        unknown = [x for x in vs if x["regulation_561_scope"] == "unknown"]
        self.assertTrue(unknown)
        self.assertTrue(all(x["scope_evidence"] is None for x in unknown))
        self.assertEqual(self.by_id["transport_context_changed"]["expected_outcome"],
                         "unknown_fail_closed")

    def test_D7_missing_history_is_explicit_not_zero_duty(self) -> None:
        entries = [row for w in range(1, 9)
                   for row in self.payloads[f"history_week_{w:02d}.json"]["records"]]
        missing = [row for row in entries if row["coverage_status"] == "missing"]
        self.assertEqual(len(missing), 1)
        self.assertEqual((missing[0]["driver_code"], missing[0]["work_date"]), ("D07", "2026-10-30"))
        self.assertIsNone(missing[0]["driving_min"])
        self.assertFalse(missing[0]["verified_off_duty"])
        self.assertIsNone(missing[0]["rest_before_duty"])
        self.assertEqual(self.by_id["missing_history"]["expected_outcome"], "unknown_fail_closed")

    def test_D7_default_rest_is_11h_with_no_9h_exception(self) -> None:
        scenario = self.by_id["insufficient_rest"]
        end = instant(scenario["input_overrides"]["additional_duty"]["duty_end"])
        start = instant(scenario["proposed_duty_start"])
        actual_hours = (start - end).total_seconds() / 3600
        self.assertEqual(actual_hours, 8)
        self.assertLess(actual_hours, 11)
        self.assertEqual(scenario["expected_reason_codes"], ["DRIVER_REST_INSUFFICIENT"])
        self.assertFalse(any("reduced_rest" in str(x) for x in self.payloads.values()))

    def test_D7_duty_driving_are_independent_and_consistent(self) -> None:
        row = self.payloads["history_week_08.json"]["records"][0]
        self.assertEqual(row["driving_min"], 240)
        self.assertEqual((instant(row["duty_end"]) - instant(row["duty_start"])).total_seconds(),
                         8 * 3600)
        self.assertLess(row["driving_min"], 8 * 60)
        drive = self.by_id["driving_day_over_limit"]
        self.assertGreater(drive["proposed_driving_min"], 9 * 60)
        self.assertIn("DRIVING_TIME_EXCEEDED", drive["expected_reason_codes"])

    def test_D7_official_future_shifts_and_night_window(self) -> None:
        shifts = self.payloads["future_shifts.json"]["records"]
        self.assertEqual(len({(x["driver_code"], x["work_date"]) for x in shifts}), len(shifts))
        self.assertTrue(all(x["authority_status"] == "synthetic_offline_not_db_confirmed"
                            for x in shifts))
        night = next(x for x in shifts if x["driver_code"] == "D06"
                     and x["work_date"] == "2026-11-14")
        self.assertEqual(night["shift_start"][:10], "2026-11-14")
        self.assertEqual(night["shift_end"][:10], "2026-11-15")
        self.assertEqual(self.by_id["overnight_duty"]["expected_outcome"],
                         "candidate_for_planner_review")

    def test_D7_stockholm_dst_fall_is_5_elapsed_hours(self) -> None:
        rows = self.payloads["history_week_06.json"]["records"]
        night = next(x for x in rows if x["driver_code"] == "D09"
                     and x["work_date"] == "2026-10-25")
        self.assertEqual((instant(night["duty_end"]) - instant(night["duty_start"])) .total_seconds(),
                         5 * 3600)
        self.assertEqual(night["driving_min"], 120)
        self.assertIn("+02:00", night["duty_start"])
        self.assertIn("+01:00", night["duty_end"])
        self.assertEqual(self.by_id["dst_overnight_history"]["expected_outcome"],
                         "historical_evidence_only")

    def test_D7_licence_expiry_and_missing_data_scenarios(self) -> None:
        ds = self.payloads["drivers.json"]["records"]
        expired = next(x for x in ds if x["driver_code"] == "D10")
        self.assertLess(expired["licence_expires_on"], "2026-11-09")
        self.assertIn("LICENCE_EXPIRED", self.by_id["expired_licence"]["expected_reason_codes"])
        for key in ("unknown_vehicle_scope", "missing_vehicle_mass", "missing_shift",
                    "licence_data_missing", "transport_context_changed"):
            self.assertEqual(self.by_id[key]["expected_outcome"], "unknown_fail_closed")
        self.assertIsNone(self.by_id["missing_vehicle_mass"]["input_overrides"]["vehicle_override"]
                          ["max_permissible_mass_kg"])

    def test_D7_unapproved_rules_not_encoded_as_eligibility(self) -> None:
        scenarios = self.payloads["scenarios.json"]["records"]
        self.assertFalse(any(x["legal_compliance_certified"] for x in scenarios))
        self.assertFalse(any(x["expected_outcome"] == "automatically_approvable" for x in scenarios))

    def test_D7_validator_rejects_unknown_silently_eligible(self) -> None:
        corrupted = copy.deepcopy(self.payloads)
        row = next(x for x in corrupted["scenarios.json"]["records"]
                   if x["scenario_id"] == "unknown_vehicle_scope")
        row["expected_reason_codes"] = []
        with self.assertRaises(FixtureError):
            validate(corrupted)

    def test_D7_validator_rejects_missing_as_verified_off_duty(self) -> None:
        corrupted = copy.deepcopy(self.payloads)
        row = next(x for x in corrupted["history_week_07.json"]["records"]
                   if x["driver_code"] == "D07" and x["work_date"] == "2026-10-30")
        row["verified_off_duty"] = True
        with self.assertRaises(FixtureError):
            validate(corrupted)

    def test_D7_validator_rejects_referential_error(self) -> None:
        corrupted = copy.deepcopy(self.payloads)
        corrupted["scenarios.json"]["records"][0]["driver_code"] = "MISSING"
        with self.assertRaises(FixtureError):
            validate(corrupted)

    def test_D7_every_timestamp_has_offset(self) -> None:
        self.assertEqual(datetime.fromisoformat("2026-10-25T04:30+01:00").astimezone(UTC).hour, 3)
        for name, payload in self.payloads.items():
            if not name.startswith("history_week_"):
                continue
            for row in payload["records"]:
                for key in ("duty_start", "duty_end"):
                    if row[key] is not None:
                        self.assertIsNotNone(datetime.fromisoformat(row[key]).utcoffset())


if __name__ == "__main__":
    unittest.main()
