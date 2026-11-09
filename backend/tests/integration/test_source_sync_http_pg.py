"""Integration: real PostgreSQL routing/audit through the Sync & Check ASGI route.

Only the external Source transport is replaced by a synthetic typed snapshot.
The Dev 1 acceptance service, DB transaction, advisory lock, routing and audit
are REAL. The disposable Compose preflight separately tests real Source HTTP.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.order_wire import SourceOrder
from app.adapters.registry import AdapterRegistry
from app.api.v1.source_sync import router
from app.core.errors import install_error_handlers
from app.deps import CurrentUser, get_current_user, get_db
from tests.integration.conftest import async_url, fetch
from tests.integration.test_ingest_orders import db as db  # noqa: F401
from tests.integration.test_ingest_orders import source
from tests.integration.test_ingest_references import mapped

pytestmark = pytest.mark.integration
URL = "/integration/orders/sync-now"
ACTOR = CurrentUser(
    id=1, employee_id=1, roles=("sales",), market="SE", location_ids=(2,)
)


@pytest.fixture
def client(db: str, monkeypatch: pytest.MonkeyPatch):
    mapped(db)
    engine = create_async_engine(async_url(db))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def session_dependency():
        async with sessions() as session, session.begin():
            yield session

    api = FastAPI()
    api.include_router(router)
    install_error_handlers(api)
    api.dependency_overrides[get_db] = session_dependency
    api.dependency_overrides[get_current_user] = lambda: ACTOR
    state = SimpleNamespace(raw=source(version=2), cancelled=False, unavailable=False)

    async def fetch_order(self, external_ref: str):
        del self
        if state.unavailable:
            from app.adapters.rest_adapter import SourceReadError

            raise SourceReadError("synthetic transport failed")
        if state.cancelled or state.raw["id"] != external_ref:
            return None
        return SourceOrder.model_validate(state.raw)

    monkeypatch.setattr(AdapterRegistry, "configure", lambda *args, **kwargs: None)

    # A transport-only stub preserves the real PostgreSQL acceptance call.
    class Reader:
        async def fetch_order_for_sync(self, external_ref: str):
            return await fetch_order(self, external_ref)

    monkeypatch.setattr(AdapterRegistry, "get", lambda *args: Reader())
    with TestClient(api, raise_server_exceptions=False) as test:
        yield test, state, api
    import asyncio

    asyncio.run(engine.dispose(close=False))


def post(client: TestClient, key: str, ref: str = "EXT-1"):
    return client.post(
        URL, headers={"Idempotency-Key": key}, json={"external_ref": ref}
    )


def test_route_real_postgres_exactly_once_retries_and_audit(client, db: str) -> None:
    http, state, _ = client
    key = str(uuid4())
    first = post(http, key)
    assert first.status_code == 200, first.text
    assert first.json()["routing_status"] == "cfo"
    assert first.json()["source_version"] == 2
    repeat = post(http, key)
    assert repeat.status_code == 200
    assert repeat.json() == first.json()
    second = post(http, str(uuid4()))
    assert second.status_code == 200
    assert second.json()["order_id"] == first.json()["order_id"]
    assert second.json()["already_decided"] is True
    assert fetch(db, "SELECT count(*) FROM ops.customer_order")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 1
    assert (
        fetch(
            db, "SELECT count(*) FROM audit.decision_log WHERE action='ROUTING_DECIDED'"
        )[0][0]
        == 1
    )
    assert fetch(db, "SELECT count(*) FROM ops.idempotency_key")[0][0] == 2


def test_route_real_postgres_concurrent_distinct_keys_one_decision(
    client, db: str
) -> None:
    http, _, _ = client
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(post, http, str(uuid4())) for _ in range(2)]
        results = [f.result(timeout=15) for f in futures]
    assert all(r.status_code == 200 for r in results), [r.status_code for r in results]
    assert len({r.json()["order_id"] for r in results}) == 1
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.customer_order")[0][0] == 1
    assert (
        fetch(
            db, "SELECT count(*) FROM audit.decision_log WHERE action='ROUTING_DECIDED'"
        )[0][0]
        == 1
    )


def test_route_market_store_scope_cannot_write(client, db: str) -> None:
    http, _, api = client
    out_of_scope = CurrentUser(
        id=1, employee_id=1, roles=("sales",), market="SE", location_ids=(1,)
    )
    api.dependency_overrides[get_current_user] = lambda: out_of_scope
    response = post(http, str(uuid4()))
    assert response.status_code == 404
    assert fetch(db, "SELECT count(*) FROM ops.customer_order")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 0


def test_route_cancelled_and_transport_failed_do_not_write(client, db: str) -> None:
    http, state, _ = client
    state.cancelled = True
    assert post(http, str(uuid4())).status_code == 404
    state.cancelled = False
    state.unavailable = True
    assert post(http, str(uuid4())).status_code == 503
    assert fetch(db, "SELECT count(*) FROM ops.customer_order")[0][0] == 0
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 0


def test_route_stale_source_version_rejected_without_mutating_routing(
    client, db: str
) -> None:
    http, state, _ = client
    assert post(http, str(uuid4())).status_code == 200
    state.raw = source(version=3, address="New synthetic delivery location")
    assert post(http, str(uuid4())).status_code == 200
    state.raw = source(version=2)
    stale = post(http, str(uuid4()))
    assert stale.status_code == 409
    assert fetch(db, "SELECT count(*) FROM ops.customer_order")[0][0] == 1
    assert fetch(db, "SELECT count(*) FROM ops.order_routing")[0][0] == 1
    assert (
        fetch(
            db, "SELECT count(*) FROM audit.decision_log WHERE action='ROUTING_DECIDED'"
        )[0][0]
        == 1
    )
