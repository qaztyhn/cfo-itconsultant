from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError

NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)


def customer(key: str) -> dict[str, object]:
    return {
        "id": key,
        "type": "business",
        "name": "Synthetic",
        "email": None,
        "phone": None,
        "updated_at": NOW.isoformat(),
    }


def adapter(
    handler: Callable[[httpx.Request], httpx.Response], *, max_pages: int = 10000
) -> RestMarketAdapter:
    return RestMarketAdapter(
        "ZZ",
        "https://source.test/api/v1",
        "synthetic-key",
        transport=httpx.MockTransport(handler),
        max_pages=max_pages,
    )


def page(items: list[dict[str, object]], number: int, total: int) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"X-Total-Count": str(total)},
        json={
            "items": items,
            "page": number,
            "page_size": 50,
            "total": total,
        },
    )


async def test_US_INT_01_reference_reader_paginates_with_inclusive_checkpoint_and_source_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        number = int(request.url.params["page"])
        assert request.headers["X-API-Key"] == "synthetic-key"
        assert request.url.params["updated_since"] == NOW.isoformat()
        assert request.method == "GET"
        return page(
            [customer(f"C{i:03d}") for i in (range(50) if number == 1 else range(50, 51))], number, 51
        )

    rows = [row async for row in adapter(handler).fetch_customers(NOW)]
    assert len(rows) == 51 and rows[0].external_ref == "C000" and rows[-1].external_ref == "C050"
    assert len(requests) == 2


async def test_US_INT_01_products_preserve_decimal_nullability_and_empty_feed() -> None:
    product = {
        "sku": "P1",
        "name": "Synthetic",
        "category": None,
        "gtin": None,
        "sale_unit": "bag",
        "units_to_base": "0.125",
        "unit_price": "0.00",
        "weight_kg": "2.125",
        "volume_m3": None,
        "updated_at": NOW.isoformat(),
    }
    rows = [row async for row in adapter(lambda r: page([product], 1, 1)).fetch_products(NOW)]
    assert rows[0].units_to_base == Decimal("0.125") and rows[0].unit_price == Decimal("0.00")
    assert rows[0].category is None and rows[0].volume_m3 is None
    assert [row async for row in adapter(lambda r: page([], 1, 0)).fetch_customers(NOW)] == []


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "incomplete",
        "changed_total",
        "wrong_page",
        "missing_header",
        "private_body",
        "non_json",
        "old_timestamp",
        "bad_item",
        "redirect",
    ],
)
async def test_US_INT_01_invalid_or_partial_feeds_raise_without_exposing_source_content(failure: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params["page"])
        if failure == "private_body":
            return httpx.Response(500, text="private-contact-key")
        if failure == "non_json":
            return httpx.Response(200, text="private-contact-key")
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://untrusted.test"})
        items = [customer(f"C{i:03d}") for i in range(50)]
        total = 51
        if number == 2:
            items = [customer("C000" if failure == "duplicate" else "C050")]
        if failure == "incomplete":
            items = []
        if failure == "bad_item":
            items[0]["updated_at"] = "private-contact-key"
        if failure == "old_timestamp":
            items[0]["updated_at"] = "2025-01-01T00:00:00Z"
        if failure == "changed_total" and number == 2:
            total = 52
        response = page(items, 9 if failure == "wrong_page" else number, total)
        if failure == "missing_header":
            del response.headers["X-Total-Count"]
        return response

    with pytest.raises(SourceReadError) as caught:
        _ = [row async for row in adapter(handler).fetch_customers(NOW)]
    assert "private" not in str(caught.value) and "synthetic-key" not in str(caught.value)


async def test_US_INT_01_page_budget_bounds_retry_and_naive_checkpoint_is_rejected() -> None:
    reader = adapter(lambda r: page([customer(f"C{i:03d}") for i in range(50)], 1, 51), max_pages=1)
    with pytest.raises(SourceReadError, match="safety limit"):
        _ = [row async for row in reader.fetch_customers(NOW)]
    with pytest.raises(ValueError, match="aware"):
        _ = [row async for row in reader.fetch_products(NOW.replace(tzinfo=None))]
