"""Read-only stock transport for US-INT-03 AC1 (persistence is a separate slice)."""

import secrets
from decimal import Decimal

import httpx
import pytest

from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError, StockUnavailable


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
            content=b"""{"as_of":"2026-11-07T10:00:00+01:00","batch_id":17,"item_count":1,"items":[
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
    assert (result.batch_id, result.item_count) == (17, 1)


async def test_complete_published_empty_batch_is_authoritative_and_keeps_source_time() -> None:
    body = {"as_of": "2026-11-07T09:00:00Z", "batch_id": 3, "item_count": 0, "items": []}
    adapter = RestMarketAdapter(
        "SE",
        "https://source.test/api/v1/",
        secrets.token_urlsafe(32),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    result = await adapter.fetch_stock()
    assert result.items == () and result.batch_id == 3 and result.item_count == 0
    assert result.as_of.isoformat() == "2026-11-07T09:00:00+00:00"


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500, 503, 204])
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


ROW = '{"warehouse_code":"WH","sku":"X","on_hand":1,"reserved":0}'
HEAD = '"as_of":"2026-11-07T09:00:00Z","batch_id":1'


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b"{}",
        # legacy body: no batch markers, so no completeness proof
        b'{"as_of":"2026-11-07T09:00:00Z","items":[]}',
        b'{"as_of":"2026-11-07T09:00:00","batch_id":1,"item_count":0,"items":[]}',  # naive timestamp
        b'{"as_of":"2026-11-07T09:00:00Z","batch_id":0,"item_count":0,"items":[]}',
        b'{"as_of":"2026-11-07T09:00:00Z","batch_id":"1","item_count":0,"items":[]}',
        b'{"as_of":"2026-11-07T09:00:00Z","batch_id":1,"item_count":-1,"items":[]}',
        b'{"as_of":"2026-11-07T09:00:00Z","batch_id":1,"item_count":true,"items":[]}',
        b'{"as_of":"2026-11-07T09:00:00Z","batch_id":1,"item_count":1,"items":[{}]}',
        (
            "{"
            + HEAD
            + ',"item_count":1,"items":['
            + ROW.replace('"reserved":0', '"reserved":0,"physical_stock_pool_id":"P"')
            + "]}"
        ).encode(),
        (
            "{" + HEAD + ',"item_count":1,"items":[' + ROW.replace('"on_hand":1', '"on_hand":NaN') + "]}"
        ).encode(),
        (
            "{" + HEAD + ',"item_count":1,"items":[' + ROW.replace('"on_hand":1', '"on_hand":true') + "]}"
        ).encode(),
        ("{" + HEAD + ',"item_count":0,"items":[],"complete":true}').encode(),  # unknown top-level field
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
    body = {"as_of": "2026-11-07T09:00:00Z", "batch_id": 1, "item_count": 2, "items": [row, row]}
    adapter = RestMarketAdapter(
        "SE",
        "https://source.test",
        secrets.token_urlsafe(32),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    with pytest.raises(SourceReadError, match="duplicate"):
        await adapter.fetch_stock()


@pytest.mark.parametrize("item_count", [0, 2])
async def test_item_count_must_match_rows(item_count: int) -> None:
    row = {"warehouse_code": "WH", "sku": "X", "on_hand": 1, "reserved": 0}
    body = {"as_of": "2026-11-07T09:00:00Z", "batch_id": 1, "item_count": item_count, "items": [row]}
    adapter = RestMarketAdapter(
        "SE",
        "https://source.test",
        secrets.token_urlsafe(32),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    with pytest.raises(SourceReadError, match="incomplete"):
        await adapter.fetch_stock()


async def test_stock_unavailable_is_distinct_and_never_zero_stock() -> None:
    key = secrets.token_urlsafe(32)
    error = {"error": {"code": "STOCK_UNAVAILABLE", "message": key, "details": {}, "correlation_id": "c"}}
    adapter = RestMarketAdapter(
        "SE",
        "https://source.test",
        key,
        transport=httpx.MockTransport(lambda _: httpx.Response(503, json=error)),
    )
    with pytest.raises(StockUnavailable) as raised:
        await adapter.fetch_stock()
    assert isinstance(raised.value, SourceReadError)  # callers that only know SourceReadError still fail
    assert key not in str(raised.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"error": {"code": "INTERNAL_ERROR"}}),
        httpx.Response(503, text="down"),
        httpx.Response(500, json={"error": {"code": "STOCK_UNAVAILABLE"}}),  # wrong status
    ],
)
async def test_other_failures_are_not_reported_as_stock_unavailable(response: httpx.Response) -> None:
    adapter = RestMarketAdapter(
        "SE",
        "https://source.test",
        secrets.token_urlsafe(32),
        transport=httpx.MockTransport(lambda _: response),
    )
    with pytest.raises(SourceReadError) as raised:
        await adapter.fetch_stock()
    assert not isinstance(raised.value, StockUnavailable)


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
