import secrets

import pytest

from app.adapters.registry import AdapterConfigurationError, AdapterRegistry


def test_US_INT_04_AC2_missing_market_does_not_fall_back_to_other_market() -> None:
    registry = AdapterRegistry()
    key = secrets.token_urlsafe(24)
    registry.configure("SE", "http://source.test/api/v1", "SOURCE_KEY", environment={"SOURCE_KEY": key})
    se = registry.get("SE")
    with pytest.raises(AdapterConfigurationError):
        registry.get("DK")
    with pytest.raises(AdapterConfigurationError):
        registry.configure("DK", "http://dk.test", "MISSING", environment={})
    assert registry.get("SE") is se
    registry.configure(
        "DK",
        "http://dk.test",
        "DK_KEY",
        environment={"DK_KEY": secrets.token_urlsafe(24)},
    )
    assert registry.get("DK").market_code == "DK"
    assert registry.get("SE").market_code == "SE"
