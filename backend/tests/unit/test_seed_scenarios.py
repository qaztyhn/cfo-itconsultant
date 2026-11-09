"""Deterministic, safe source-input fixtures for all 18 demo E2E paths."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal

import pytest

from app.seed.generate_data import write_manifest
from app.seed.scenarios import (
    BLOCKERS,
    GOLDEN,
    RANDOM_SEED,
    canonical_json,
    catalog_skus,
    digest,
    generate,
    validate,
)


def test_US_SRC_01_AC1_seed_has_fixed_hash_and_reproducible_counts() -> None:
    a, b = generate(), generate()
    validate(a)
    assert a == b and digest(a) == digest(b)
    assert a["seed"] == RANDOM_SEED
    assert len(catalog_skus()) == 100
    assert len(a["orders"]) == 18 and len(a["completed_orders"]) == 48
    assert len(a["stock_snapshot"]["items"]) == 300
    assert len(a["e2e_scenarios"]) == 18
    assert sorted(s["number"] for s in a["e2e_scenarios"]) == list(range(1, 19))
    assert json.loads(canonical_json(a)) == a


def test_US_SRC_01_AC1_manifest_is_idempotent_and_refuses_file_collision(tmp_path) -> None:
    path = tmp_path / "source" / "demo.json"
    fixture = generate()
    assert write_manifest(path, fixture) is True
    original = path.read_bytes()
    assert write_manifest(path, generate()) is False
    assert path.read_bytes() == original
    path.write_text('{"operational":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="collision"):
        write_manifest(path, fixture)
    assert path.read_text(encoding="utf-8") == '{"operational":true}'


def test_US_ATP_01_AC3_inbound_golden_no_source_stock_double_count() -> None:
    fixture = generate()
    stock = {
        (r["warehouse_code"], r["sku"]): Decimal(r["on_hand"]) for r in fixture["stock_snapshot"]["items"]
    }
    sku = "SE-TIL-ADH-25"
    assert stock["GBG", sku] == 42
    assert stock["MLM", sku] == 0
    assert stock["STO", sku] >= 160
    assert fixture["inbound"] == [
        {
            "inbound_ref": "IN-SE-88213",
            "warehouse_code": "MLM",
            "sku": sku,
            "qty": "200",
            "eta_date": "2026-11-11",
            "confirmed": True,
            "received": False,
        }
    ]
    assert GOLDEN["SE-2026-000137"]["earliest_date"] == "2026-11-12"


def test_US_PLN_03_AC3_multivehicle_and_crane_targets_preserved_not_fabricated() -> None:
    fixture = generate()
    orders = {str(o["id"]): o for o in fixture["orders"]}
    large = orders["SE-2026-000160"]
    assert large["lines"] == [{"line_no": 1, "sku": "SE-CEM-MOR-25", "qty": "800"}]
    assert Decimal("800") * Decimal("25") == Decimal("20000")
    assert GOLDEN["SE-2026-000160"]["vehicle_count"] == 2
    assert "20 t" in BLOCKERS["SE-2026-000160"]
    assert GOLDEN["SE-2026-000144"]["failed_check"] == "truck"
    assert "crane" in BLOCKERS["SE-2026-000144"]


def test_US_INT_01_AC2_stock_race_and_unmapped_are_explicit() -> None:
    fixture = generate()
    items = {(r["warehouse_code"], r["sku"]): r for r in fixture["stock_snapshot"]["items"]}
    assert items["GBG", "SE-DEMO-N3-004"]["on_hand"] == "100"
    orders = {str(o["id"]): o for o in fixture["orders"]}
    assert orders["SE-2026-000180"]["lines"][0]["qty"] == "80"
    assert orders["SE-2026-000181"]["lines"][0]["qty"] == "70"
    assert orders["SE-2026-000156"]["lines"][0]["sku"] == "88412"
    assert orders["SE-2026-000156"]["target_cfo_status"] == "LEGACY_UNMAPPED"
    assert "ASM-005" in BLOCKERS["E2E-11"]


def test_US_WH_06_AC1_named_driver_shifts_do_not_forge_legal_history() -> None:
    fixture = generate()
    counts = Counter(str(row["employee_no"]) for row in fixture["driver_history"])
    assert counts == {f"DEMO-DRIVER-{n}": 56 for n in range(1, 11)}
    assert len(fixture["driver_shifts"]) == 80
    assert not fixture["gps_enabled"]
    assert all(r["verified"] is False and r["reviewer_id"] is None for r in fixture["driver_history"])
    assert all(r["reg_561_scope"] == "unknown" for r in fixture["driver_history"])
    assert len(fixture["driver_edge_cases"]) == 9
    assert all(not r["legally_verified"] for r in fixture["driver_edge_cases"])
    assert {"REST_SHORT", "DRIVING_LIMIT", "MISSING_HISTORY", "NO_OFFICIAL_SHIFT", "LICENCE_EXPIRED", "SCOPE_UNKNOWN"} <= {
        str(r["expected_gate"]) for r in fixture["driver_edge_cases"]
    }
    assert all(r["authority"].endswith("-W00") for r in fixture["driver_shifts"])


def test_US_SRC_01_AC1_reject_tampered_manifest_without_silent_repair() -> None:
    fixture = generate()
    fixture["orders"][1]["id"] = fixture["orders"][0]["id"]
    with pytest.raises(ValueError, match="collisions"):
        validate(fixture)
    with pytest.raises(ValueError, match="20261104"):
        generate(seed=1)
