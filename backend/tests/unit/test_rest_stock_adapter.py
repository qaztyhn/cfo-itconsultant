"""Read-only stock transport for US-INT-03 AC1 (persistence is a separate slice)."""

import secrets
from decimal import Decimal

import httpx
import pytest

from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError


@pytest.mark.parametrize("market", ["SE", "DK"])
async def test_US_INT_03_AC1_fetch_stock_preserves_precision_and_source_timestamp(market: str) -> None:
    key = secrets.token_urlsafe(32)

    def source(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://source.test/api/v1/stock"
        assert request.headers["X-API-Key"] == key
        assert request.extensions["timeout"]["read"] == 2.5
        return httpx.Response(
            200,
            content=b"""{"as_of":"2026-11-07T10:00:00+01:00","items":[
            {"warehouse_code":"WH","sku":"X","on_hand":750.1234567890123456789,"reserved":20}]}""",
        )

    adapter = RestMarketAdapter(
        market,
        "https://source.test/api/v1",
        key,
        timeout_seconds=2.5,
        transport=httpx.MockTransport(source),
    )
    result = await adapter.fetch_stock()
    assert result.as_of.isoformat() == "2026-11-07T10:00:00+01:00"
    assert result.items[0].on_hand == Decimal("750.1234567890123456789")
    assert result.items[0].reserved == Decimal(20)
    assert result.items[0].warehouse_code == "WH"
    assert result.items[0].sku == "X"


async def test_empty_snapshot_preserves_source_time() -> None:
    adapter = RestMarketAdapter(
        "SE",
        "https://source.test/api/v1/",
        secrets.token_urlsafe(32),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"as_of": "2026-11-07T09:00:00Z", "items": []})
        ),
    )
    assert (await adapter.fetch_stock()).items == ()


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500, 503])
async def test_http_failures_and_redirects_do_not_leak_credentials(status: int) -> None:
    key = secrets.token_urlsafe(32)
    calls = []

    def source(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, text=key, headers={"Location": "https://other.test/"})

    adapter = RestMarketAdapter(
        "SE", "https://source.test/api/v1", key, transport=httpx.MockTransport(source)
    )
    with pytest.raises(SourceReadError) as error:
        await adapter.fetch_stock()
    assert len(calls) == 1
    assert key not in str(error.value)
    assert "source.test" not in str(error.value)


async def test_transport_timeout_is_sanitized() -> None:
    key = secrets.token_urlsafe(32)

    def source(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(key, request=request)

    adapter = RestMarketAdapter("SE", "https://source.test", key, transport=httpx.MockTransport(source))
    with pytest.raises(SourceReadError, match="request failed") as error:
        await adapter.fetch_stock()
    assert key not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b"{}",
        b'{"as_of":"2026-11-07T09:00:00","items":[]}',
        b'{"as_of":"2026-11-07T09:00:00Z","items":[{}]}',
        b'{"as_of":"2026-11-07T09:00:00Z","items":[{"warehouse_code":"WH","sku":"X","on_hand":NaN,"reserved":0}]}',
        b'{"as_of":"2026-11-07T09:00:00Z","items":[{"warehouse_code":"WH","sku":"X","on_hand":true,"reserved":0}]}',
    ],
)
async def test_invalid_snapshot_fails_atomically(body: bytes) -> None:
    adapter = RestMarketAdapter(
        "SE",
        "https://source.test",
        secrets.token_urlsafe(32),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)),
    )
    with pytest.raises(SourceReadError, match="response is invalid"):
        await adapter.fetch_stock()


async def test_duplicate_natural_key_is_rejected() -> None:
    row = {"warehouse_code": "WH", "sku": "X", "on_hand": 1, "reserved": 0}
    adapter = RestMarketAdapter(
        "SE",
        "https://source.test",
        secrets.token_urlsafe(32),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"as_of": "2026-11-07T09:00:00Z", "items": [row, row]})
        ),
    )
    with pytest.raises(SourceReadError, match="duplicate"):
        await adapter.fetch_stock()


@pytest.mark.parametrize(
    "url", ["file:///tmp/feed", "https://user:password@source.test", "https://source.test?k=v"]
)
def test_unsafe_base_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="base URL"):
        RestMarketAdapter("SE", url, secrets.token_urlsafe(32))


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_timeout_must_be_bounded(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        RestMarketAdapter("SE", "https://source.test", secrets.token_urlsafe(32), timeout_seconds=timeout)


def test_missing_key_is_a_configuration_error() -> None:
    with pytest.raises(ValueError, match="API key"):
        RestMarketAdapter("SE", "https://source.test", "")
