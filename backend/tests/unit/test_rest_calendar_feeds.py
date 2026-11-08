from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.adapters.registry import AdapterConfigurationError, AdapterRegistry
from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError

NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)


def page(items: list[dict[str, object]]) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"X-Total-Count": str(len(items))},
        json={"page": 1, "page_size": 50, "total": len(items), "items": items},
    )


@pytest.mark.parametrize("hours", [None, {}, {"1": [["07:00", "16:00"]]}])
async def test_D1_addresses_preserve_explicit_or_unknown_receiving_schedule(hours: object) -> None:
    def source(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.path == "/api/v1/addresses"
        assert request.url.params["updated_since"] == NOW.isoformat()
        return page(
            [
                {
                    "id": "A1",
                    "customer_id": "C1",
                    "address": "Synthetic",
                    "lat": None,
                    "lon": None,
                    "receiving_hours": hours,
                    "updated_at": NOW.isoformat(),
                }
            ]
        )

    reader = RestMarketAdapter(
        "ZZ", "https://source.test/api/v1", "synthetic-key", transport=httpx.MockTransport(source)
    )
    rows = [row async for row in reader.fetch_addresses(NOW)]
    assert rows[0].customer_ref == "C1" and rows[0].lat is None
    assert rows[0].receiving_hours == ({"1": [("07:00", "16:00")]} if hours else hours)


@pytest.mark.parametrize("hours", [{"8": []}, {"1": [["16:00", "07:00"]]}, {"1": [["07:00", "private"]]}])
async def test_D1_invalid_receiving_slots_fail_without_echoing_private_values(hours: object) -> None:
    reader = RestMarketAdapter(
        "ZZ",
        "https://source.test",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda request: page(
                [
                    {
                        "id": "A1",
                        "customer_id": "C1",
                        "address": "private",
                        "lat": 59,
                        "lon": 18,
                        "receiving_hours": hours,
                        "updated_at": NOW.isoformat(),
                    }
                ]
            )
        ),
    )
    with pytest.raises(SourceReadError) as error:
        _ = [row async for row in reader.fetch_addresses(NOW)]
    assert "private" not in str(error.value)


async def test_US_INT_03_inbound_preserves_composite_keys_decimal_and_received_flag() -> None:
    def source(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/inbound" and request.url.params["updated_since"] == NOW.isoformat()
        return page(
            [
                {
                    "inbound_ref": "I1",
                    "warehouse_code": code,
                    "sku": "P1",
                    "qty": "1.125",
                    "eta_date": "2026-11-05",
                    "confirmed": True,
                    "received": received,
                    "updated_at": NOW.isoformat(),
                }
                for code, received in [("W1", False), ("W2", True)]
            ]
        )

    reader = RestMarketAdapter(
        "ZZ", "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
    )
    rows = await reader.fetch_inbound(updated_since=NOW)
    assert len(rows) == 2 and rows[0].qty == Decimal("1.125")
    assert not rows[0].received and rows[1].received and rows[1].updated_at == NOW


async def test_US_INT_03_fleet_uses_market_midnights_across_dst_and_preserves_full_intervals() -> None:
    def source(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fleet/calendar" and "updated_since" not in request.url.params
        start, end = (datetime.fromisoformat(request.url.params[key]) for key in ("from", "to"))
        assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(hours=49)
        return page(
            [
                {
                    "vehicle_code": "V1",
                    "from": "2026-10-23T20:00:00Z",
                    "to": "2026-10-27T10:00:00Z",
                    "kind": "external",
                    "updated_at": NOW.isoformat(),
                }
            ]
        )

    reader = RestMarketAdapter(
        "ZZ",
        "https://source.test",
        "synthetic-key",
        market_timezone="Europe/Stockholm",
        transport=httpx.MockTransport(source),
    )
    rows = await reader.fetch_fleet(date(2026, 10, 24), date(2026, 10, 26))
    assert rows[0].start == datetime(2026, 10, 23, 20, tzinfo=UTC)
    assert rows[0].end == datetime(2026, 10, 27, 10, tzinfo=UTC)


async def test_US_INT_03_fleet_requires_configured_timezone_and_ordered_exclusive_dates() -> None:
    reader = RestMarketAdapter("ZZ", "https://source.test", "synthetic-key")
    with pytest.raises(SourceReadError, match="timezone"):
        await reader.fetch_fleet(date(2026, 11, 4), date(2026, 11, 5))
    reader = RestMarketAdapter("ZZ", "https://source.test", "synthetic-key", market_timezone="UTC")
    with pytest.raises(ValueError, match="half-open"):
        await reader.fetch_fleet(date(2026, 11, 5), date(2026, 11, 5))


def test_US_INT_04_registry_rejects_unknown_timezone_without_cross_market_fallback() -> None:
    registry = AdapterRegistry()
    with pytest.raises(AdapterConfigurationError):
        registry.configure(
            "ZZ",
            "https://source.test",
            "KEY",
            environment={"KEY": "synthetic-key"},
            market_timezone="Invalid/private",
        )
    with pytest.raises(AdapterConfigurationError):
        registry.get("ZZ")


async def test_US_INT_03_inbound_reads_all_pages_without_guessing_a_checkpoint() -> None:
    calls: list[int] = []

    def source(request: httpx.Request) -> httpx.Response:
        assert "updated_since" not in request.url.params
        number = int(request.url.params["page"])
        calls.append(number)
        rows = [
            {
                "inbound_ref": "I1",
                "warehouse_code": "W1",
                "sku": f"P{i:03d}",
                "qty": "1.000",
                "eta_date": "2026-11-05",
                "confirmed": True,
                "received": False,
                "updated_at": NOW.isoformat(),
            }
            for i in (range(50) if number == 1 else range(50, 51))
        ]
        return httpx.Response(
            200,
            headers={"X-Total-Count": "51"},
            json={"items": rows, "page": number, "page_size": 50, "total": 51},
        )

    reader = RestMarketAdapter(
        "ZZ", "https://source.test", "synthetic-key", transport=httpx.MockTransport(source)
    )
    rows = await reader.fetch_inbound()
    assert calls == [1, 2] and len(rows) == 51 and rows[-1].sku == "P050"


@pytest.mark.parametrize("failure", ["reversed", "duplicate", "naive", "interval"])
async def test_US_INT_03_fleet_rejects_invalid_or_misordered_composite_keys(failure: str) -> None:
    rows = [
        {
            "vehicle_code": "V1",
            "from": f"2026-11-0{i}T10:00:00Z",
            "to": f"2026-11-0{i}T11:00:00Z",
            "kind": "external",
            "updated_at": NOW.isoformat(),
        }
        for i in (4, 5)
    ]
    if failure == "reversed":
        rows.reverse()
    elif failure == "duplicate":
        rows[1] = rows[0].copy()
    elif failure == "naive":
        rows[0]["from"] = "2026-11-04T10:00:00"
    else:
        rows[0]["to"] = rows[0]["from"]
    reader = RestMarketAdapter(
        "ZZ",
        "https://source.test",
        "synthetic-key",
        market_timezone="UTC",
        transport=httpx.MockTransport(lambda request: page(rows)),
    )
    with pytest.raises(SourceReadError):
        await reader.fetch_fleet(date(2026, 11, 4), date(2026, 11, 6), updated_since=NOW)
