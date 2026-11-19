"""E1: chỉ hai mốc demo cô lập được phép bật đường WMS giả lập."""

import pytest

from app.adapters.synthetic_wms import ALLOWED_DEMO_CLOCKS, DEMO_NOW, E0_04_DEMO_NOW


def test_US_E1_01_AC1_allowlist_contains_exactly_two_demo_clocks() -> None:
    assert ALLOWED_DEMO_CLOCKS == frozenset({DEMO_NOW, E0_04_DEMO_NOW})
    assert DEMO_NOW == "2026-11-04T10:05:00+01:00"
    assert E0_04_DEMO_NOW == "2026-12-01T10:05:00+01:00"


@pytest.mark.parametrize("clock", ["2026-11-02T10:05:00+01:00", "2026-12-02T10:05:00+01:00", ""])
def test_US_E1_01_AC2_other_clocks_are_not_allowed(clock: str) -> None:
    assert clock not in ALLOWED_DEMO_CLOCKS
