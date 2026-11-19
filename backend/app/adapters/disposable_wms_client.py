"""HTTP client của WMS disposable (SQLite) cho đường duyệt mô phỏng E1.

Chỉ nói chuyện với dịch vụ loopback trong demo test; KHÔNG phải adapter WMS thật. Cài đặt
WmsReservationPort. Mọi lỗi được đổi sang mã tĩnh, không mang nội dung phản hồi.
"""

from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from app.adapters.wms_reservation import (
    AckLine,
    ReservationAck,
    ReservationRequest,
    WmsDisabled,
    WmsRejected,
    WmsTimeout,
    WmsUnavailable,
)

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def _qty(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.001")), "f")


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        raise WmsUnavailable() from None
    if not isinstance(data, dict):
        raise WmsUnavailable()
    return data


def _detail(response: httpx.Response) -> str:
    try:
        value = response.json().get("detail")
    except (ValueError, AttributeError):
        return "UNKNOWN"
    return value if isinstance(value, str) and len(value) <= 64 else "UNKNOWN"


def _fail(response: httpx.Response) -> None:
    if response.status_code == 503:
        if _detail(response) == "DISPOSABLE_WMS_DISABLED":
            raise WmsDisabled()
        raise WmsUnavailable()
    if response.status_code >= 500:
        raise WmsUnavailable()
    raise WmsRejected(_detail(response))


def _ack(data: dict[str, Any]) -> ReservationAck:
    try:
        return ReservationAck(
            reservation_id=str(data["reservation_id"]),
            status=str(data["status"]),
            lines=tuple(
                AckLine(str(row["wms_sku"]), str(row["warehouse_code"]), Decimal(str(row["quantity"])))
                for row in data["lines"]
            ),
            revision=str(data["revision"]),
            reflected_in_batch_id=int(data["reflected_in_batch_id"]),
            idempotency_key=str(data["idempotency_key"]),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise WmsUnavailable() from None


class DisposableWmsPort:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        source_version: int,
        source_ref: str,
        timeout: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parts = urlsplit(base_url)
        if (
            parts.scheme != "http"
            or parts.hostname not in _LOOPBACK
            or not api_key
            or source_version <= 0
            or not source_ref.strip()
        ):
            raise ValueError("Disposable WMS needs a loopback http URL, API key and pinned source evidence")
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._source_version = source_version
        self._source_ref = source_ref
        self._timeout = timeout
        self._transport = transport

    async def _send(self, method: str, path: str, body: dict[str, Any] | None = None) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._base, timeout=self._timeout, transport=self._transport
            ) as client:
                return await client.request(method, path, json=body, headers={"X-Demo-WMS-Key": self._key})
        except httpx.TimeoutException:
            raise WmsTimeout() from None
        except httpx.HTTPError:
            raise WmsUnavailable() from None

    async def reserve(self, request: ReservationRequest) -> ReservationAck:
        body = {
            "market": request.market,
            "order_id": request.order_id,
            "plan_id": request.plan_id,
            "source_version": self._source_version,
            "source_ref": self._source_ref,
            "idempotency_key": request.idempotency_key,
            "lines": [
                {
                    "order_line_id": line.order_line_id,
                    "pos_sku": line.pos_sku,
                    "wms_sku": line.wms_sku,
                    "warehouse_code": line.warehouse_code,
                    "wms_unit": line.wms_unit,
                    "mapping_version": line.mapping_version,
                    "quantity": _qty(line.quantity),
                }
                for line in request.lines
            ],
        }
        response = await self._send("POST", "/v1/reserve", body)
        if response.status_code != 200:
            _fail(response)
        return _ack(_json(response))

    async def status(self, market: str, idempotency_key: str) -> ReservationAck | None:
        path = f"/v1/status/{quote(market, safe='')}/{quote(idempotency_key, safe='')}"
        response = await self._send("GET", path)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            _fail(response)
        return _ack(_json(response))

    async def release(self, market: str, reservation_id: str, idempotency_key: str) -> ReservationAck:
        body = {"market": market, "reservation_id": reservation_id, "idempotency_key": idempotency_key}
        response = await self._send("POST", "/v1/release", body)
        if response.status_code != 200:
            _fail(response)
        return _ack(_json(response))

    async def fetch_batch(self) -> dict[str, Any]:
        """Batch tồn kho đầy đủ đã ký (chưa xác minh chữ ký; người gọi dùng verify_batch)."""
        response = await self._send("GET", "/v1/stock")
        if response.status_code != 200:
            _fail(response)
        return _json(response)
