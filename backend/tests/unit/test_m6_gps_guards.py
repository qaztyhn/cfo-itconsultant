"""M6 D3 fail-closed boundaries, independent of database integration."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.core.errors import DomainError
from app.services import gps_service


def test_US_GPS_01_AC1_requires_shared_transaction() -> None:
    actor = SimpleNamespace(employee_id=5, roles=("driver",), market="SE")
    with pytest.raises(DomainError) as caught:
        asyncio.run(gps_service.ingest_positions(1, actor, []))
    assert caught.value.code == "PLAN_NOT_APPROVABLE"


def test_US_GPS_01_AC2_untrusted_naive_time_is_rejected() -> None:
    with pytest.raises(DomainError) as caught:
        gps_service._aware(datetime(2026, 11, 10, 7, 0, tzinfo=UTC).replace(tzinfo=None))
    assert caught.value.code == "VALIDATION_ERROR"


def test_US_GPS_02_AC1_market_scope_is_not_dispatcher_trip_assignment() -> None:
    market_dispatcher = SimpleNamespace(
        employee_id=2, roles=("dispatcher",), market="SE", location_ids=(1, 2, 3)
    )
    with pytest.raises(DomainError) as caught:
        asyncio.run(gps_service.live(market_dispatcher))
    assert caught.value.code == "FORBIDDEN"


def test_US_GPS_03_AC2_cleanup_requires_explicit_transaction() -> None:
    with pytest.raises(DomainError) as caught:
        asyncio.run(gps_service.purge_expired())
    assert caught.value.code == "PLAN_NOT_APPROVABLE"


def test_US_GPS_03_AC1_signal_check_requires_explicit_transaction() -> None:
    with pytest.raises(DomainError) as caught:
        asyncio.run(gps_service.lost_check())
    assert caught.value.code == "PLAN_NOT_APPROVABLE"
