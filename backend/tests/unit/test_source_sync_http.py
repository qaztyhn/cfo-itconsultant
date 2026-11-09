"""Dev 2 Sync & Check HTTP boundary — role, source verification and idempotency.

The real routing/atomic PostgreSQL tests live in Dev 1 PR #202. Here, only the
source HTTP boundary and thin API integration are mocked; no false E2E claim.
"""

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.order_wire import SourceOrder
from app.adapters.rest_adapter import RestMarketAdapter, SourceReadError
from app.api.v1 import source_sync
from app.core.errors import DomainError, install_error_handlers
from app.deps import CurrentUser, get_current_user, get_db
from app.services import source_handoff
from tests.unit.test_rest_order_feeds import order

KEY = "11111111-2222-4333-8444-555555555555"
URL = "/integration/orders/sync-now"


class FakeDb:
    async def scalar(self, query: object) -> SimpleNamespace:
        del query
        return SimpleNamespace(
            code="SE",
            source_base_url="https://source.example.test/api/v1",
            source_api_key_ref="DEMO_SOURCE_KEY",
            timezone="Europe/Stockholm",
        )


def setup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    role: str = "sales",
    source_status: str = "submitted",
    failure: bool = False,
) -> tuple[TestClient, list[tuple[object, ...]], list[str]]:
    api = FastAPI()
    api.include_router(source_sync.router)
    install_error_handlers(api)
    actor = CurrentUser(id=13, employee_id=19, roles=(role,), market="SE", location_ids=(1,))
    api.dependency_overrides[get_current_user] = lambda: actor
    api.dependency_overrides[get_db] = lambda: FakeDb()
    monkeypatch.setenv("DEMO_SOURCE_KEY", "synthetic-only-key")
    reads: list[str] = []

    async def fetch(self: RestMarketAdapter, external_ref: str) -> SourceOrder | None:
        del self
        reads.append(external_ref)
        if failure or source_status == "conflict":
            raise SourceReadError("Remote Source returned secret-only-error")
        if source_status in {"missing", "cancelled"}:
            return None
        if source_status == "submitted":
            return SourceOrder.model_validate(order("POS-SE-123"))
        raise AssertionError("Unexpected source test state")

    monkeypatch.setattr(RestMarketAdapter, "fetch_order_for_sync", fetch)
    calls: list[tuple[object, ...]] = []

    async def accept(session: object, user: object, source: SourceOrder, key: str) -> dict[str, object]:
        calls.append((session, user, source, key))
        return {
            "order_id": 45,
            "external_ref": source.id,
            "source_version": source.version,
            "routing_status": "cfo",
            "sync_status": "synced",
            "already_decided": False,
        }

    monkeypatch.setattr(source_handoff, "accept_source_order", accept)
    return TestClient(api, raise_server_exceptions=False), calls, reads


def post(client: TestClient, key: str = KEY, ref: str = "POS-SE-123"):
    return client.post(URL, headers={"Idempotency-Key": key}, json={"external_ref": ref})


def test_US_INT_01_AC2_exact_trusted_source_passed_to_DB_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, calls, reads = setup(monkeypatch)
    with client:
        response = post(client)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "order_id": 45,
        "external_ref": "POS-SE-123",
        "source_version": 1,
        "routing_status": "cfo",
        "sync_status": "synced",
        "already_decided": False,
    }
    assert reads == ["POS-SE-123"]
    assert len(calls) == 1
    assert calls[0][2].id == "POS-SE-123"
    assert calls[0][3] == str(UUID(KEY))


@pytest.mark.parametrize("role", ["warehouse", "driver", "customer_service", "viewer"])
def test_US_INT_01_AC3_wrong_role_never_reads_source(monkeypatch: pytest.MonkeyPatch, role: str) -> None:
    client, calls, reads = setup(monkeypatch, role=role)
    with client:
        response = post(client)
    assert response.status_code == 403
    assert not calls and not reads


@pytest.mark.parametrize("state", ["missing", "cancelled"])
def test_US_INT_01_AC2_missing_or_cancelled_does_not_route(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    client, calls, _ = setup(monkeypatch, source_status=state)
    with client:
        response = post(client)
    assert response.status_code == 404
    assert not calls


@pytest.mark.parametrize("state,fail", [("conflict", False), ("submitted", True)])
def test_US_INT_01_AC4_inconsistent_or_unavailable_source_is_503_without_writes(
    monkeypatch: pytest.MonkeyPatch, state: str, fail: bool
) -> None:
    client, calls, _ = setup(monkeypatch, source_status=state, failure=fail)
    with client:
        response = post(client)
    assert response.status_code == 503
    assert not calls
    assert "secret-only-error" not in response.text


def test_US_INT_01_AC4_invalid_uuid_or_body_never_reads_source(monkeypatch: pytest.MonkeyPatch) -> None:
    client, calls, reads = setup(monkeypatch)
    with client:
        assert post(client, key="not-a-uuid").status_code == 422
        assert client.post(URL, json={"external_ref": "POS-SE-123"}).status_code == 422
        assert post(client, ref="").status_code == 422
    assert not calls and not reads


def test_US_INT_01_AC4_identical_retry_preserves_exact_key_to_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, calls, _ = setup(monkeypatch)
    with client:
        assert post(client).status_code == 200
        assert post(client).status_code == 200
    assert len(calls) == 2
    assert calls[0][3] == calls[1][3] == KEY


def test_US_INT_01_AC3_backend_not_found_is_not_exposed_as_customer_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = setup(monkeypatch)

    async def reject(*args: object) -> dict[str, object]:
        del args
        raise DomainError("NOT_FOUND", "Submitted source order is not available.")

    monkeypatch.setattr(source_handoff, "accept_source_order", reject)
    with client:
        response = post(client)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
