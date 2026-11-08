from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError

NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)


def order(key: str = "O1", **changes: object) -> dict[str, object]:
    return {
        "id": key,
        "version": 1,
        "updated_at": NOW.isoformat(),
        "status": "SUBMITTED_FOR_PLANNING",
        "customer_id": "C1",
        "address_id": "A1",
        "address": "Synthetic address",
        "lat": 59,
        "lon": 18,
        "contact": {"name": "Synthetic", "email": "synthetic@example.test", "phone": None},
        "date_mode": "exact",
        "date_from": "2026-11-05",
        "date_to": None,
        "window_start": "09:00",
        "window_end": "11:00",
        "store_code": "ST1",
        "sales_code": "S1",
        "lines": [{"line_no": 1, "sku": "PENDING-SOURCE-SKU", "qty": 1.125, "unit_price": "0.00"}],
        **changes,
    }


@pytest.mark.parametrize(
    "mode,first,last,normalized_end",
    [
        ("exact", "2026-11-05", None, date(2026, 11, 5)),
        ("range", "2026-11-05", "2026-11-10", date(2026, 11, 10)),
        ("latest", None, "2026-11-10", date(2026, 11, 10)),
    ],
)
async def test_US_INT_01_orders_preserve_version_source_data_and_normalize_exact_end(
    mode: str, first: str | None, last: str | None, normalized_end: date
) -> None:
    def source(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET" and request.url.params["status"] == "SUBMITTED_FOR_PLANNING"
        assert request.url.params["updated_since"] == NOW.isoformat()
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            headers={"X-Total-Count": "2"},
            json={
                "page": page,
                "page_size": 1,
                "total": 2,
                "items": [order(f"O{page}", date_mode=mode, date_from=first, date_to=last)],
            },
        )

    reader = RestMarketAdapter(
        "ZZ", "https://source.test/api/v1", "synthetic-key", transport=httpx.MockTransport(source)
    )
    rows = [row async for row in reader.fetch_orders(NOW, page_size=1)]
    assert len(rows) == 2 and rows[0].external_ref == "O1" and rows[0].version == 1
    assert rows[0].date_to == normalized_end
    assert rows[0].lines[0].qty == Decimal("1.125") and rows[0].lines[0].unit_price == Decimal("0.00")
    assert rows[0].lines[0].sku == "PENDING-SOURCE-SKU"  # mapping/routing is not a transport decision.


async def test_D1_cancel_feed_is_independent_and_does_not_require_delivery_pii() -> None:
    def source(request: httpx.Request) -> httpx.Response:
        assert request.url.params["status"] == "CANCELLED"
        return httpx.Response(
            200,
            headers={"X-Total-Count": "1"},
            json={
                "page": 1,
                "page_size": 200,
                "total": 1,
                "items": [
                    {
                        "id": "O1",
                        "version": 2,
                        "updated_at": NOW.isoformat(),
                        "status": "CANCELLED",
                        "cancel_reason": {"reason_code": "duplicate", "reason_text": None},
                        "cancelled_at": NOW.isoformat(),
                    }
                ],
            },
        )

    reader = RestMarketAdapter(
        "ZZ", "https://source.test/api/v1", "synthetic-key", transport=httpx.MockTransport(source)
    )
    rows = [row async for row in reader.fetch_cancelled_orders(NOW)]
    assert rows[0].external_ref == "O1" and rows[0].version == 2
    assert rows[0].cancel_reason == {"reason_code": "duplicate", "reason_text": None}
    assert not hasattr(rows[0], "address") and not hasattr(rows[0], "contact")


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "DRAFT"},
        {"version": 0},
        {"lat": None},
        {"contact": None},
        {"date_to": "2026-11-06"},
        {"window_end": None},
        {"window_start": "private-sensitive-time"},
    ],
)
async def test_D1_invalid_order_feed_cannot_advance_as_success_and_never_echoes_source_data(
    changes: dict[str, object],
) -> None:
    reader = RestMarketAdapter(
        "ZZ",
        "https://source.test",
        "synthetic-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"X-Total-Count": "1"},
                json={"page": 1, "page_size": 200, "total": 1, "items": [order(**changes)]},
            )
        ),
    )
    with pytest.raises(SourceReadError) as error:
        _ = [row async for row in reader.fetch_orders(NOW)]
    assert "synthetic@example.test" not in str(error.value) and "private-sensitive" not in str(error.value)
