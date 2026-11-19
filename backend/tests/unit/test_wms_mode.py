import pytest

from app.core.config import get_settings
from app.core.errors import DomainError
from app.services import wms_mode

DEMO_NOW = "2026-11-04T10:05:00+01:00"


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _env(monkeypatch, *, mode="simulated", app_env="test", disposable="1", now=DEMO_NOW) -> None:
    monkeypatch.setenv("WMS_RESERVATION_MODE", mode)
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("APP_NOW", now)
    if disposable is None:
        monkeypatch.delenv("DEMO_DISPOSABLE", raising=False)
    else:
        monkeypatch.setenv("DEMO_DISPOSABLE", disposable)
    get_settings.cache_clear()


def test_default_is_off(monkeypatch) -> None:
    _env(monkeypatch, mode="disabled")
    assert wms_mode.simulated_enabled() is False
    assert wms_mode.require_simulated_or_off() is False


def test_all_four_conditions_enable(monkeypatch) -> None:
    _env(monkeypatch)
    assert wms_mode.simulated_enabled() is True
    assert wms_mode.require_simulated_or_off() is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_env": "production"},
        {"app_env": "local"},
        {"disposable": None},
        {"disposable": "0"},
        {"now": "2026-11-05T10:05:00+01:00"},
        {"mode": "bogus"},
    ],
)
def test_wrong_environment_or_mode_is_409(monkeypatch, overrides) -> None:
    _env(monkeypatch, **overrides)
    assert wms_mode.simulated_enabled() is False
    with pytest.raises(DomainError) as caught:
        wms_mode.require_simulated_or_off()
    assert caught.value.code == "PLAN_NOT_APPROVABLE"
