"""Deterministic, non-authoritative CFO demo inputs (08 §§5, 6.3).

This is fixture *intent*, not engine output or legal driver verification. The source
WMS publishes inventory; CFO must ingest it. Workflow states/approvals are reached
by E2E actions, never manufactured by this module.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from random import Random
from typing import TypedDict

RANDOM_SEED = 20261104
APP_NOW = "2026-11-04T10:05:00+01:00"
STOCK_AS_OF = "2026-11-04T09:55:00+01:00"
WAREHOUSES = ("GBG", "STO", "MLM")
GROUP_COUNTS = {"N1": 25, "N2": 20, "N3": 20, "N4": 8, "N5": 15, "N6": 12}
EXAMPLES = {
    ("N1", 1): "SE-PNT-INT-10",
    ("N2", 1): "SE-BRD-GYP-13",
    ("N2", 2): "SE-TIL-POR-60",
    ("N2", 20): "448812",
    ("N3", 1): "SE-CEM-MOR-25",
    ("N3", 2): "SE-TIL-ADH-25",
    ("N3", 3): "SE-TIL-GRT-05",
    ("N3", 20): "88412",
    ("N5", 1): "SE-TMB-C24-4895",
    ("N5", 15): "449130",
}
UNMAPPED_SKUS = frozenset({"448812", "88412", "449130"})

# These are the *documented* expectations, not assertions that current input
# contracts/engine have satisfied them. Preserve them when prerequisites fail.
GOLDEN = {
    "SE-2026-000123": {"plans": 3, "gross_kg": "4120", "volume_m3": "9.6"},
    "SE-2026-000137": {"result": "NO_FEASIBLE_DATE", "earliest_date": "2026-11-12"},
    "SE-2026-000144": {"result": "NO_FEASIBLE_DATE", "failed_check": "truck", "reason": "capability"},
    "SE-2026-000160": {"vehicle_count": 2, "preferred_pair": ["GBG-18-01", "GBG-12-03"]},
}
# Actual deficiencies are tracked, never repaired by spoofing passed engine tests.
BLOCKERS = {
    "SE-2026-000123": (
        "Existing reference catalogue has 0.1 m3 per unit; a 4,120 kg "
        "order cannot match the documented 9.6 m3 without a reviewed catalogue fixture."
    ),
    "SE-2026-000144": (
        "No existing global product carries an order-wide crane requirement; "
        "the 11 t crane golden case needs a reviewed requirement input."
    ),
    "SE-2026-000160": (
        "Existing GBG-18-01 + GBG-12-03 payload limits are 10 t + 6 t, "
        "not 20 t; no change to documented expected vehicle pair."
    ),
    "D7": (
        "Current DB schema lacks approved attested, versioned 56-day daily proof; "
        "synthetic records are not legally verified driver eligibility."
    ),
    "E2E-11": (
        "08 §6.3 says auto-reopen SKU 000156 after mapping, but approved ASM-005 "
        "forbids retroactive CFO routing of originally unmapped orders."
    ),
    "E2E-13": (
        "08 §6.3 still says 30-day GPS retention; approved "
        "DEC-GPS-RET-20261109 instead caps restricted history at 7 days."
    ),
}


class DemoFixture(TypedDict):
    schema_version: str
    seed: int
    app_now: str
    gps_enabled: bool
    orders: list[dict[str, object]]
    completed_orders: list[dict[str, object]]
    stock_snapshot: dict[str, object]
    inbound: list[dict[str, object]]
    vehicle_calendar: list[dict[str, object]]
    driver_shifts: list[dict[str, object]]
    driver_history: list[dict[str, object]]
    e2e_scenarios: list[dict[str, object]]
    golden_expected: dict[str, dict[str, object]]
    blockers: dict[str, str]


# Each of the 18 required E2E flows has fixture keys; this does not claim
# Playwright execution, automatic approval, or simulation of genuine GPS.
E2E: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "happy_path", ("000123",)),
    (2, "confirmed_inbound", ("000137",)),
    (3, "no_feasible_date", ("000137",)),
    (4, "prep_cutoff", ("000155",)),
    (5, "stock_approval_race", ("000180", "000181")),
    (6, "multi_vehicle_and_crane", ("000160", "000144")),
    (7, "receiving_hours", ("000152",)),
    (8, "risk_prediction", ("000141",)),
    (9, "vehicle_approval_race", ("000123", "000160")),
    (10, "ingest_replay_and_reject", ("000123",)),
    (11, "unmapped_sku", ("000156",)),
    (12, "failed_redelivery", ("000118",)),
    (13, "gps_permissions_retention", ("000129",)),
    (14, "holds_extend_expire", ("000123",)),
    (15, "role_and_location_scopes", ("000131",)),
    (16, "post_approval_source_change", ("000138",)),
    (17, "revenue_scope_and_timezone", ("000118",)),
    (18, "prep_pause_resume", ("000149",)),
)


def catalog_skus() -> tuple[str, ...]:
    """Follow the existing independent reference catalogue, including 3 pending SKUs."""
    return tuple(
        EXAMPLES.get((group, i), f"SE-DEMO-{group}-{i:03d}")
        for group, count in GROUP_COUNTS.items()
        for i in range(1, count + 1)
    )


def _order(
    number: int,
    customer: int,
    skus: tuple[tuple[str, int], ...],
    day: str,
    window: tuple[str, str] = ("07:00", "16:00"),
    *,
    store: int = 1,
    expectation: str = "SUBMITTED",
) -> dict[str, object]:
    key = f"SE-2026-{number:06d}"
    return {
        "id": key,
        "customer_id": f"DEMO-C{customer:03d}",
        "address_id": f"DEMO-C{customer:03d}-A1",
        "store_code": f"ST-{store:03d}",
        "sales_code": "DEMO-SALES" if store == 1 else f"DEMO-ST-{store:03d}-S0",
        "date_mode": "exact",
        "date_from": day,
        "date_to": day,
        "window_start": window[0],
        "window_end": window[1],
        "status": "SUBMITTED_FOR_PLANNING",
        "target_cfo_status": expectation,
        "lines": [{"line_no": i, "sku": sku, "qty": str(qty)} for i, (sku, qty) in enumerate(skus, 1)],
    }


def _orders() -> list[dict[str, object]]:
    # 000123: 4 lines and exactly 4,120 kg under present reference weights;
    # volume mismatch is explicitly reported in BLOCKERS, never hidden.
    cases = (
        (
            123,
            1,
            (("SE-CEM-MOR-25", 160), ("SE-BRD-GYP-13", 4), ("SE-TMB-C24-4895", 4), ("SE-PNT-INT-10", 4)),
            "2026-11-10",
            ("08:00", "14:30"),
            "PLANNED",
        ),
        (
            137,
            5,
            (("SE-TIL-ADH-25", 160), ("SE-TIL-POR-60", 20), ("SE-CEM-MOR-25", 10)),
            "2026-11-09",
            ("07:00", "15:00"),
            "NO_FEASIBLE_DATE",
        ),
        (141, 2, (("SE-BRD-GYP-13", 40),), "2026-11-05", ("10:00", "12:30"), "PREPARING"),
        (138, 3, (("SE-TIL-POR-60", 80),), "2026-11-05", ("13:00", "16:00"), "LOADED"),
        (129, 31, (("SE-PNT-INT-10", 10),), "2026-11-05", ("12:00", "18:00"), "DISPATCHED"),
        (131, 4, (("SE-CEM-MOR-25", 40),), "2026-11-05", ("07:00", "11:00"), "APPROVED"),
        (144, 8, (("SE-TMB-C24-4895", 1100),), "2026-11-06", ("06:30", "10:00"), "NO_FEASIBLE_DATE"),
        (160, 7, (("SE-CEM-MOR-25", 800),), "2026-11-10", ("09:00", "16:00"), "PLANNED"),
        (152, 6, (("SE-BRD-GYP-13", 15),), "2026-11-11", ("07:00", "16:00"), "SUBMITTED"),
        (118, 7, (("SE-PNT-INT-10", 10),), "2026-11-03", ("07:00", "16:00"), "DELIVERED"),
        (146, 1, (("SE-CEM-MOR-25", 40),), "2026-11-05", ("07:00", "16:00"), "APPROVED"),
        (149, 2, (("SE-BRD-GYP-13", 10),), "2026-11-05", ("07:00", "16:00"), "PREPARING"),
        (150, 3, (("SE-PNT-INT-10", 4),), "2026-11-05", ("07:00", "16:00"), "GOODS_READY"),
        (153, 4, (("SE-TIL-POR-60", 30),), "2026-11-05", ("07:00", "16:00"), "APPROVED"),
        (155, 5, (("SE-CEM-MOR-25", 30),), "2026-11-05", ("07:00", "16:00"), "PREPARING"),
        (156, 6, (("88412", 1),), "2026-11-10", ("07:00", "16:00"), "LEGACY_UNMAPPED"),
        (180, 7, (("SE-DEMO-N3-004", 80),), "2026-11-10", ("07:00", "16:00"), "SUBMITTED"),
        (181, 7, (("SE-DEMO-N3-004", 70),), "2026-11-10", ("07:00", "16:00"), "SUBMITTED"),
    )
    return [
        _order(n, customer, lines, day, window, expectation=status)
        for n, customer, lines, day, window, status in cases
    ]


def _completed_orders(seed: int) -> list[dict[str, object]]:
    rng = Random(seed)
    result: list[dict[str, object]] = []
    # Completed-order *inputs* for E2E. Source cannot set CFO DELIVERED:
    # the execution service must create proper plans, events and POD.
    for i in range(48):
        number = 200 + i
        customer = 1 + (i % 40)
        store = 1 + (i % 25)
        day = date(2026, 11, 3) + timedelta(days=i % 7)
        result.append(
            _order(
                number,
                customer,
                (("SE-CEM-MOR-25", rng.randint(1, 24)),),
                day.isoformat(),
                store=store,
                expectation="DELIVERED",
            )
        )
    # 000200 is deliberately unassigned to a store in CFO revenue *target*,
    # not on the source where missing store may violate POS validation.
    result[0]["target_cfo_store"] = None
    return result


def _stock() -> dict[str, object]:
    items = []
    for wh in WAREHOUSES:
        for sku in catalog_skus():
            amount = 5000
            if sku == "SE-DEMO-N3-004" and wh == "GBG":
                amount = 100
            if sku == "SE-TIL-ADH-25":
                amount = {"GBG": 42, "STO": 5000, "MLM": 0}[wh]
            items.append({"warehouse_code": wh, "sku": sku, "on_hand": str(amount), "reserved": "0"})
    return {"as_of": STOCK_AS_OF, "items": items}


def _driver_history() -> list[dict[str, object]]:
    first = date(2026, 9, 9)  # inclusive 56 days through 2026-11-03
    records: list[dict[str, object]] = []
    for index in range(1, 11):
        for offset in range(56):
            day = first + timedelta(days=offset)
            records.append(
                {
                    "employee_no": f"DEMO-DRIVER-{index}",
                    "market_local_day": day.isoformat(),
                    "activity": "off_duty" if day.isoweekday() > 5 else "duty",
                    "reg_561_scope": "unknown",
                    "evidence_type": "synthetic_demo_unverified",
                    "verified": False,
                    "reviewer_id": None,
                    "source_version": "demo-v1",
                }
            )
    return records


def _driver_shifts() -> list[dict[str, object]]:
    shifts = []
    first = date(2026, 11, 4)
    for index in range(1, 11):
        wh = WAREHOUSES[(index - 1) % 3]
        for offset in range(10):
            day = first + timedelta(days=offset)
            if day.isoweekday() > 5:
                continue
            shifts.append(
                {
                    "employee_no": f"DEMO-DRIVER-{index}",
                    "warehouse_code": wh,
                    "work_date": day.isoformat(),
                    "start": "06:00",
                    "end": "14:00",
                    "break_start": "10:00",
                    "break_end": "11:00",
                    "authority": f"DEMO-{wh}-W00",
                    "purpose": "synthetic_official_shift_fixture",
                }
            )
    return shifts


def generate(seed: int = RANDOM_SEED) -> DemoFixture:
    """Pure repeatable fixture. Does not touch production/source/CFO databases."""
    if seed != RANDOM_SEED:
        raise ValueError("Approved CFO demo seed must be 20261104")
    orders = _orders()
    return {
        "schema_version": "cfo-demo-v1",
        "seed": seed,
        "app_now": APP_NOW,
        "gps_enabled": False,
        "orders": orders,
        "completed_orders": _completed_orders(seed),
        "stock_snapshot": _stock(),
        "inbound": [
            {
                "inbound_ref": "IN-SE-88213",
                "warehouse_code": "MLM",
                "sku": "SE-TIL-ADH-25",
                "qty": "200",
                "eta_date": "2026-11-11",
                "confirmed": True,
                "received": False,
            }
        ],
        "vehicle_calendar": [
            {
                "vehicle_code": "MLM-12-02",
                "from_ts": "2026-11-10T06:00:00+01:00",
                "to_ts": "2026-11-10T18:00:00+01:00",
                "kind": "busy",
            }
        ],
        "driver_shifts": _driver_shifts(),
        "driver_history": _driver_history(),
        "e2e_scenarios": [
            {"number": number, "name": label, "order_ids": [f"SE-2026-{key}" for key in ids]}
            for number, label, ids in E2E
        ],
        "golden_expected": GOLDEN,
        "blockers": BLOCKERS,
    }


def canonical_json(value: DemoFixture) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def digest(value: DemoFixture) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate(value: DemoFixture) -> None:
    """Validate fixtures, not engine outputs or D7 legal approval."""
    orders = value["orders"] + value["completed_orders"]
    names = [str(order["id"]) for order in orders]
    if len(names) != 66 or len(set(names)) != len(names):
        raise ValueError("Expected 18 scenario orders and 48 history orders without collisions")
    if len(value["e2e_scenarios"]) != 18:
        raise ValueError("All 18 E2E scenarios must be represented")
    if {s["number"] for s in value["e2e_scenarios"]} != set(range(1, 19)):
        raise ValueError("E2E scenario identifiers must be 1–18")
    expected_skus = set(catalog_skus())
    rows = value["stock_snapshot"]["items"]
    if not isinstance(rows, list) or len(rows) != 3 * len(expected_skus):
        raise ValueError("Stock batch is not complete across three warehouses")
    keys = [(r["warehouse_code"], r["sku"]) for r in rows]
    if len(keys) != len(set(keys)) or set(keys) != {(wh, sku) for wh in WAREHOUSES for sku in expected_skus}:
        raise ValueError("Duplicate/incomplete WMS stock keys")
    if any(Decimal(str(r["reserved"])) < 0 or Decimal(str(r["on_hand"])) < 0 for r in rows):
        raise ValueError("Stock quantities must be nonnegative")
    if any(line["sku"] not in expected_skus for o in orders for line in o["lines"]):
        raise ValueError("Order includes SKU outside source catalogue")
    if len(value["driver_history"]) != 560 or any(
        row["verified"] is not False or row["reg_561_scope"] != "unknown" for row in value["driver_history"]
    ):
        raise ValueError("Synthetic D7 data must remain explicitly unverified")
    if value["gps_enabled"]:
        raise ValueError("No implicit GPS opt-in")
