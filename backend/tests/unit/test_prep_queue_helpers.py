"""Pure helpers of the canonical Prep Queue and the location timezone guard (no database)."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.errors import DomainError
from app.services import hr_read_service
from app.services.prep_queue_service import _allocate, _minutes, _next_action, _zone


@pytest.mark.parametrize("zone", ["Europe/Stockholm", "Europe/Copenhagen", "Europe/Oslo"])
def test_valid_market_timezones_resolve(zone: str) -> None:
    assert str(_zone(SimpleNamespace(timezone=zone))) == zone  # type: ignore[arg-type]


@pytest.mark.parametrize("zone", ["", "  ", "Not/AZone"])
def test_missing_or_invalid_market_timezone_is_an_error_never_utc(zone: str) -> None:
    with pytest.raises(DomainError) as caught:
        _zone(SimpleNamespace(timezone=zone))  # type: ignore[arg-type]
    assert caught.value.code == "INTERNAL_ERROR"


def test_location_timezone_lookup_rejects_missing_and_invalid_markets() -> None:
    class Result:
        def __init__(self, rows: list[tuple[int, str]]) -> None:
            self._rows = rows

        def all(self) -> list[tuple[int, str]]:
            return self._rows

    class Session:
        def __init__(self, rows: list[tuple[int, str]]) -> None:
            self.rows = rows

        async def execute(self, _statement: object) -> Result:
            return Result(self.rows)

    ok = asyncio.run(hr_read_service._market_timezones(Session([(1, "Europe/Oslo")]), {1}))  # type: ignore[arg-type]
    assert ok == {1: "Europe/Oslo"}
    for rows in ([], [(1, "")], [(1, "Bad/Zone")]):
        with pytest.raises(DomainError) as caught:
            asyncio.run(hr_read_service._market_timezones(Session(rows), {1}))  # type: ignore[arg-type]
        assert caught.value.code == "INTERNAL_ERROR"


def test_minutes_round_half_up_to_integers() -> None:
    assert _minutes(Decimal("377.5")) == 378 and _minutes(Decimal("377.4")) == 377
    assert isinstance(_minutes(Decimal("90")), int)


def test_booked_allocation_adds_up_exactly_and_is_proportional() -> None:
    assert sum(_allocate(100, [1, 1, 1])) == 100
    assert _allocate(90, [378]) == [90]
    assert _allocate(0, [10, 20]) == [0, 0] and _allocate(50, []) == []
    assert _allocate(480, [378, 0]) == [480, 0]  # booked may exceed a shift: no negative free is derived here


@pytest.mark.parametrize(
    ("status", "state", "loadings", "expected"),
    [
        ("APPROVED", None, [], "START_PREP"),
        ("PREPARING", "running", [], "GOODS_READY"),
        ("PREPARING", "paused", [], "PREP_RESUMED"),
        ("GOODS_READY", None, [{"loaded": True}, {"loaded": False}], "LOADED"),
        ("LOADED", None, [{"loaded": True}, {"loaded": True}], None),
    ],
)
def test_next_action_is_derived_from_server_state(
    status: str, state: str | None, loadings: list[dict[str, object]], expected: str | None
) -> None:
    assert _next_action(status, state, loadings) == expected
