"""T27 step 8: no UI/PG checkpoint may be promoted by a mock or wrong trip."""
import unittest

from tests.e2e.t27_http_evidence import dispatch_rejection
from tools.t27_driver_step8 import (
    EvidenceMismatch,
    step8_pass,
    verify_event_request,
    verify_position_request,
)


NOW = "2026-12-02T09:05:00+01:00"
EARLIER = "2026-12-02T09:01:00+01:00"
POINT = {
    "lat": 57.7,
    "lon": 11.97,
    "accuracy_m": 20.0,
    "recorded_at": "2026-12-02T09:03:00+01:00",
}


class TestT27DriverStep8(unittest.TestCase):
    def test_US_EXE_02_AC4_expired_t12_qualification_blocks_dispatch(self):
        result = dispatch_rejection(422, "LICENCE_EXPIRED", "Verified driver qualification has expired.")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["dispatch_status"], "BLOCKED")
        self.assertEqual(result["tasks"], ["T12"])
        self.assertEqual(dispatch_rejection(422, "VALIDATION_ERROR", "bad timestamp")["status"], "FAIL")

    def test_US_GPS_01_AC1_point_must_be_aware_and_within_server_clock(self):
        self.assertEqual(
            verify_position_request(POINT, server_now=NOW, not_before=EARLIER),
            POINT["recorded_at"],
        )
        for changed in (
            {**POINT, "recorded_at": "2026-12-02T08:01:00+01:00"},
            {**POINT, "recorded_at": "2026-12-02T09:06:00+01:00"},
            {**POINT, "recorded_at": "2026-12-02T09:03:00"},
            {**POINT, "lat": "57.7"},
            {**POINT, "source": "device"},
        ):
            with self.subTest(changed_keys=set(changed)):
                with self.assertRaises(EvidenceMismatch):
                    verify_position_request(changed, server_now=NOW, not_before=EARLIER)
        with self.assertRaises(EvidenceMismatch):
            verify_position_request(POINT, server_now=NOW, not_before=EARLIER,
                                    newer_than="2026-12-02T09:03:00+01:00")

    def test_US_EXE_02_AC2_completion_requires_new_position_and_same_trip(self):
        request = {
            "event_type": "DELIVERED", "occurred_at": NOW,
            "payload": {"trip_id": 12, "recipient_name": "Synthetic Demo Recipient",
                        "position": {**POINT, "recorded_at": "2026-12-02T09:04:00+01:00"}},
        }
        self.assertEqual(
            verify_event_request(request, event_type="DELIVERED", trip_id=12,
                                 server_now=NOW, not_before=POINT["recorded_at"]),
            NOW,
        )
        with self.assertRaises(EvidenceMismatch):
            verify_event_request(request, event_type="DELIVERED", trip_id=13,
                                 server_now=NOW, not_before=EARLIER)
        with self.assertRaises(EvidenceMismatch):
            verify_event_request({**request, "payload": {"trip_id": 12}},
                                 event_type="DELIVERED", trip_id=12,
                                 server_now=NOW, not_before=EARLIER)

    def test_T27_step8_pass_requires_all_three_authoritative_same_trip_checkpoints(self):
        values = {
            "dispatch": {"status": "PASS", "order_id": 24, "trip_id": 12, "event_id": 99, "db_verified": True},
            "gps": {"status": "PASS", "order_id": 24, "trip_id": 12, "position_id": 11, "db_verified": True},
            "delivered": {"status": "PASS", "order_id": 24, "trip_id": 12, "event_id": 100, "db_verified": True},
        }
        self.assertTrue(step8_pass(values, 24, 12))
        self.assertFalse(step8_pass({k: v for k, v in values.items() if k != "delivered"}, 24, 12))
        self.assertFalse(step8_pass({**values, "gps": {**values["gps"], "db_verified": False}}, 24, 12))
        self.assertFalse(step8_pass({**values, "delivered": {**values["delivered"], "trip_id": 13}}, 24, 12))
        self.assertFalse(step8_pass({**values, "dispatch": {**values["dispatch"], "event_id": None}}, 24, 12))
