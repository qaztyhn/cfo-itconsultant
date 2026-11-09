"""US-APR-02: manual selection must pass the same pure engine safety gates."""

import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from test_engine_planner_orchestration import config, order, warehouse

from app.engine.gate import all_passed
from app.engine.manual import verify_manual
from app.engine.planner import plan_order


class ManualVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.order = order()
        self.warehouse = warehouse(1)
        self.config = config()
        result = plan_order(self.order, [self.warehouse], self.config)
        self.assertEqual(result.result, "feasible")
        self.candidate = result.candidates[0]

    def verify(self, candidate=None, *, wh=None, request=None):
        return verify_manual(
            request or self.order, wh or self.warehouse, candidate or self.candidate, self.config
        )

    def test_US_APR_02_AC3_complete_selected_plan_passes_five_gates(self) -> None:
        checks = self.verify()
        self.assertTrue(all_passed(checks))
        self.assertEqual(
            tuple(c.name for c in checks), ("stock", "preparation", "truck", "site_date", "safety")
        )

    def test_US_APR_02_AC4_missing_or_extra_line_quantity_is_rejected(self) -> None:
        vehicle = self.candidate.vehicles[0]
        for delta in (Decimal("-1"), Decimal("1")):
            with self.subTest(delta=delta):
                assignment = replace(vehicle, load_lines=((1, vehicle.load_lines[0][1] + delta),))
                selected = replace(self.candidate, vehicles=(assignment,))
                checks = self.verify(selected)
                self.assertEqual(checks[-1].code, "NO_TRUCK_FIT")
                self.assertFalse(all_passed(checks))

    def test_US_APR_02_AC2_vehicle_overload_is_rejected(self) -> None:
        smaller = replace(self.warehouse.vehicles[0], capacity_kg=Decimal("100"))
        checks = self.verify(wh=replace(self.warehouse, vehicles=(smaller,)))
        self.assertEqual(checks[-1].code, "NO_TRUCK_FIT")

    def test_US_APR_02_AC4_duplicate_vehicle_or_driver_is_rejected(self) -> None:
        duplicate = replace(self.candidate, vehicles=(self.candidate.vehicles[0],) * 2)
        self.assertEqual(self.verify(duplicate)[-1].code, "NO_TRUCK_FIT")

    def test_US_APR_02_AC4_two_vehicles_split_a_line_without_overbooking(self) -> None:
        first = self.candidate.vehicles[0]
        second_vehicle = replace(self.warehouse.vehicles[0], id=11, code="TR-11")
        second_driver = replace(self.warehouse.drivers[0], employee_id=11)
        wh = replace(
            self.warehouse,
            vehicles=(*self.warehouse.vehicles, second_vehicle),
            drivers=(*self.warehouse.drivers, second_driver),
        )
        first_half = replace(
            first, load_lines=((1, Decimal(10)),), load_kg=Decimal(200), load_m3=Decimal("0.5")
        )
        second_half = replace(
            first_half,
            seq=2,
            vehicle_id=11,
            vehicle_code="TR-11",
            driver_employee_id=11,
            loading_start_at=first.depart_at,
            depart_at=first.depart_at + timedelta(minutes=30),
            eta_at=first.eta_at + timedelta(minutes=30),
            trip_end_at=first.trip_end_at + timedelta(minutes=32),
        )
        selected = replace(
            self.candidate,
            vehicles=(first_half, second_half),
            eta_at=second_half.eta_at,
            trip_end_at=second_half.trip_end_at,
        )
        self.assertTrue(all_passed(self.verify(selected, wh=wh)))
        duplicate_driver = replace(second_half, driver_employee_id=first.driver_employee_id)
        self.assertEqual(
            self.verify(replace(selected, vehicles=(first_half, duplicate_driver)), wh=wh)[-1].code,
            "NO_DRIVER",
        )

    def test_US_APR_02_AC3_missing_verified_duty_history_fails_closed(self) -> None:
        driver = replace(self.warehouse.drivers[0], history_complete=False)
        checks = self.verify(wh=replace(self.warehouse, drivers=(driver,)))
        self.assertEqual(checks[-1].code, "DRIVER_HISTORY_MISSING")

    def test_US_APR_02_AC3_missing_shift_or_unknown_regulatory_scope_fails_closed(self) -> None:
        driver = replace(self.warehouse.drivers[0], shifts=())
        self.assertEqual(self.verify(wh=replace(self.warehouse, drivers=(driver,)))[-1].code, "NO_DRIVER")
        vehicle = replace(self.warehouse.vehicles[0], regulation_561=None)
        self.assertEqual(
            self.verify(wh=replace(self.warehouse, vehicles=(vehicle,)))[-1].code, "VEHICLE_SCOPE_UNKNOWN"
        )

    def test_US_APR_02_AC3_receiving_window_is_checked(self) -> None:
        late = replace(self.candidate.vehicles[0], eta_at=self.candidate.vehicles[0].eta_at.replace(hour=19))
        checks = self.verify(replace(self.candidate, vehicles=(late,), eta_at=late.eta_at))
        self.assertEqual(checks[-1].code, "OUTSIDE_RECEIVING_HOURS")

    def test_US_APR_02_AC3_stock_and_preparation_fail_closed(self) -> None:
        self.assertEqual(self.verify(wh=warehouse(1, stock=Decimal(0)))[-1].code, "STOCK_SHORT")
        early = replace(self.candidate, goods_ready_at=self.order.now)
        self.assertEqual(self.verify(early)[-1].code, "PREP_NO_CAPACITY")


if __name__ == "__main__":
    unittest.main()
