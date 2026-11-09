"""Dev 2 D1 source lookup: exact reference, full feed verification, cancelled safety.

The approved Source API has only paginated GET /orders, not GET /orders/{id}.
These are boundary tests using HTTPX, not evidence of CFO DB routing or approval.
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError
from tests.unit.test_rest_order_feeds import order

NOW = datetime(2026, 11, 4, 9, 5, tzinfo=UTC)


def client(
    submitted: list[dict[str, object]],
    cancelled: list[dict[str, object]] | None = None,
    *,
    invalid_source: bool = False,
) -> tuple[RestMarketAdapter, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path.endswith("/orders")
        assert request.headers["X-API-Key"] == "synthetic-demo-key"
        assert "updated_since" not in request.url.params
        assert request.url.params["status"] in {"SUBMITTED_FOR_PLANNING", "CANCELLED"}
        rows = submitted if request.url.params["status"] == "SUBMITTED_FOR_PLANNING" else (cancelled or [])
        index = int(request.url.params["page"]) - 1
        page_size = int(request.url.params["page_size"])
        assert page_size == 200
        if invalid_source:
            return httpx.Response(503, json={"error": {"code": "UNAVAILABLE"}})
        return httpx.Response(
            200,
            headers={"X-Total-Count": str(len(rows))},
            json={
                "page": index + 1,
                "page_size": page_size,
                "total": len(rows),
                "items": rows[index * page_size : (index + 1) * page_size],
            },
        )

    return (
        RestMarketAdapter(
            "SE",
            "https://source.example.test/api/v1",
            "synthetic-demo-key",
            transport=httpx.MockTransport(handle),
        ),
        calls,
    )


def cancelled(source_id: str) -> dict[str, object]:
    return {
        "id": source_id,
        "version": 2,
        "status": "CANCELLED",
        "updated_at": NOW.isoformat(),
        "cancel_reason": {"reason_code": "duplicate", "reason_text": None},
        "cancelled_at": NOW.isoformat(),
    }


async def test_US_INT_01_AC1_exact_reference_requires_fresh_authenticated_source_read() -> None:
    adapter, calls = client([order("O1"), order("O2")])
    result = await adapter.fetch_order_for_sync("O2")
    assert result is not None
    assert result.id == "O2" and result.version == 1
    assert result.store_code == "ST1"
    assert len(calls) == 2
    assert [c.url.params["status"] for c in calls] == ["SUBMITTED_FOR_PLANNING", "CANCELLED"]
    assert "O2" not in str(calls[0].url)  # never send an unapproved Source by-ID query


async def test_US_INT_01_AC2_missing_and_cancelled_order_never_accepted() -> None:
    adapter, _ = client([order("O1")])
    assert await adapter.fetch_order_for_sync("NOT-FOUND") is None
    cancelled_adapter, _ = client([], [cancelled("O1")])
    assert await cancelled_adapter.fetch_order_for_sync("O1") is None


async def test_US_INT_01_AC2_conflicting_source_versions_fail_closed() -> None:
    adapter, _ = client([order("O1")], [cancelled("O1")])
    with pytest.raises(SourceReadError, match="changed while verifying"):
        await adapter.fetch_order_for_sync("O1")


async def test_US_INT_01_AC4_invalid_source_or_transport_does_not_create_verified_result() -> None:
    bad, _ = client([order("O1")], invalid_source=True)
    with pytest.raises(SourceReadError):
        await bad.fetch_order_for_sync("O1")
    malformed, _ = client([order("O1", date_to="2026-11-06")])
    with pytest.raises(SourceReadError):
        await malformed.fetch_order_for_sync("O1")


async def test_US_INT_01_AC4_reference_scope_is_exact_and_input_is_bounded() -> None:
    adapter, _ = client([order("POS-SE-100"), order("POS-SE-1000")])
    result = await adapter.fetch_order_for_sync("POS-SE-100")
    assert result is not None and result.id == "POS-SE-100"
    for ref in ("", " POS-SE-100", "POS-SE-100 ", "x" * 121):
        with pytest.raises(ValueError, match="Invalid external reference"):
            await adapter.fetch_order_for_sync(ref)


async def test_US_INT_01_AC4_unsafe_related_source_row_blocks_success_not_skipped() -> None:
    adapter, _ = client([order("O1"), order("O2", lat=None)])
    with pytest.raises(SourceReadError):
        await adapter.fetch_order_for_sync("O1")
