"""Source service independently validates the CFO demo manifest without importing CFO."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from app.seed_demo import check_manifest


def _fixture() -> dict:
    path = Path(__file__).resolve().parents[3] / "backend" / "app" / "seed" / "scenarios.py"
    return runpy.run_path(str(path))["generate"]()


def test_US_SRC_01_AC1_source_accepts_complete_unverified_d7_manifest() -> None:
    check_manifest(_fixture())


def test_US_SRC_01_AC1_source_rejects_fake_evidence_and_incomplete_batch() -> None:
    fixture = _fixture()
    fixture["driver_history"][0]["verified"] = True
    with pytest.raises(ValueError, match="verified"):
        check_manifest(fixture)
    fixture = _fixture()
    fixture["stock_snapshot"]["items"].pop()
    with pytest.raises(ValueError, match="snapshot"):
        check_manifest(fixture)


def test_US_SRC_01_AC1_source_rejects_implicit_gps_and_duplicate_order() -> None:
    fixture = _fixture()
    fixture["gps_enabled"] = True
    with pytest.raises(ValueError, match="manifest"):
        check_manifest(fixture)
    fixture = _fixture()
    fixture["orders"][1]["id"] = fixture["orders"][0]["id"]
    with pytest.raises(ValueError, match="Duplicate"):
        check_manifest(fixture)
