import json
from decimal import Decimal

import httpx
import pytest

from app.adapters.disposable_wms_client import DisposableWmsPort
from app.adapters.wms_reservation import (
    WmsDisabled,
    WmsRejected,
    WmsTimeout,
    WmsUnavailable,
    build_request,
)
from app.adapters.wms_sku import ReservationLine

URL = "http://127.0.0.1:8188"
LINE = ReservationLine(
    99, "SE-CEM-MOR-25", "WMS-CEM-25", "GBG", Decimal("60"), "bag", "synthetic:confirmed-v1"
)
REQUEST = build_request("SE", 50, 80, [LINE])


def _ack_body(status: str = "accepted") -> dict[str, object]:
    return {
        "source_kind": "synthetic_demo",
        "market": "SE",
        "idempotency_key": REQUEST.idempotency_key,
        "reservation_id": "SYN-abc",
        "status": status,
        "revision": "synthetic:2",
        "reflected_in_batch_id": 2,
        "lines": [
            {
                "order_line_id": 99,
                "pos_sku": "SE-CEM-MOR-25",
                "wms_sku": "WMS-CEM-25",
                "warehouse_code": "GBG",
                "wms_unit": "bag",
                "mapping_version": "synthetic:confirmed-v1",
                "quantity": "60.000",
            }
        ],
    }


def _port(handler) -> DisposableWmsPort:
    return DisposableWmsPort(
        URL, "k", source_version=2, source_ref="SYN-POS-50", transport=httpx.MockTransport(handler)
    )


async def test_reserve_sends_server_authored_body_and_maps_ack() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"], seen["path"] = request.method, request.url.path
        seen["key"] = request.headers["X-Demo-WMS-Key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ack_body())

    ack = await _port(handler).reserve(REQUEST)
    assert (seen["method"], seen["path"], seen["key"]) == ("POST", "/v1/reserve", "k")
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["source_version"] == 2 and body["source_ref"] == "SYN-POS-50"
    assert body["idempotency_key"] == REQUEST.idempotency_key
    assert body["lines"][0]["quantity"] == "60.000"
    assert ack.reservation_id == "SYN-abc" and ack.status == "accepted"
    assert ack.reflected_in_batch_id == 2 and ack.idempotency_key == REQUEST.idempotency_key
    assert ack.lines[0].quantity == Decimal("60")


async def test_status_404_is_none_and_200_is_ack() -> None:
    port404 = _port(lambda r: httpx.Response(404, json={"detail": "RESERVATION_NOT_FOUND"}))
    assert await port404.status("SE", "k1") is None
    port200 = _port(lambda r: httpx.Response(200, json=_ack_body()))
    found = await port200.status("SE", "k1")
    assert found is not None and found.reservation_id == "SYN-abc"


async def test_release_returns_released_ack() -> None:
    port = _port(lambda r: httpx.Response(200, json=_ack_body("released")))
    assert (await port.release("SE", "SYN-abc", "key:release")).status == "released"


async def test_fetch_batch_returns_raw_dict() -> None:
    port = _port(lambda r: httpx.Response(200, json={"batch_id": 3, "items": []}))
    assert (await port.fetch_batch())["batch_id"] == 3


async def test_timeout_and_connection_errors_are_mapped() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(WmsTimeout):
        await _port(slow).reserve(REQUEST)
    with pytest.raises(WmsUnavailable):
        await _port(down).reserve(REQUEST)


async def test_http_errors_are_mapped_to_static_codes() -> None:
    rejected = _port(lambda r: httpx.Response(409, json={"detail": "WMS_INSUFFICIENT_STOCK"}))
    with pytest.raises(WmsRejected) as caught:
        await rejected.reserve(REQUEST)
    assert caught.value.reason == "WMS_INSUFFICIENT_STOCK"
    disabled = _port(lambda r: httpx.Response(503, json={"detail": "DISPOSABLE_WMS_DISABLED"}))
    with pytest.raises(WmsDisabled):
        await disabled.reserve(REQUEST)
    broken = _port(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(WmsUnavailable):
        await broken.reserve(REQUEST)


async def test_malformed_ack_is_unavailable_not_trusted() -> None:
    port = _port(lambda r: httpx.Response(200, json={"status": "accepted"}))
    with pytest.raises(WmsUnavailable):
        await port.reserve(REQUEST)


@pytest.mark.parametrize("url", ["https://127.0.0.1:8188", "http://example.com:8188", "http://10.0.0.5:8188"])
def test_only_loopback_http_is_allowed(url: str) -> None:
    with pytest.raises(ValueError):
        DisposableWmsPort(url, "k", source_version=2, source_ref="SYN-POS-50")


def test_requires_key_and_pinned_source_evidence() -> None:
    with pytest.raises(ValueError):
        DisposableWmsPort(URL, "", source_version=2, source_ref="SYN-POS-50")
    with pytest.raises(ValueError):
        DisposableWmsPort(URL, "k", source_version=0, source_ref="SYN-POS-50")
    with pytest.raises(ValueError):
        DisposableWmsPort(URL, "k", source_version=2, source_ref=" ")
