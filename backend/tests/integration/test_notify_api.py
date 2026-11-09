"""API RBAC, typed-input rejection and masked previews on PostgreSQL."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.deps import get_current_user, get_db
from app.main import create_app
from app.services import notify_service
from tests.integration.conftest import async_url
from tests.integration.dev2_helpers import transact
from tests.integration.test_notify_backend import WINDOW, actor, prepare

pytestmark = pytest.mark.integration


@pytest.fixture
def notifications_api(empty_db: str) -> Iterator[tuple[TestClient, dict[str, SimpleNamespace], str]]:
    prepare(empty_db)
    roles = {"actor": actor()}
    engine = create_async_engine(async_url(empty_db), poolclass=NullPool)
    maker = async_sessionmaker(engine)

    async def test_db() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    def test_user() -> SimpleNamespace:
        return roles["actor"]

    app = create_app()
    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = test_user
    with TestClient(app) as client:
        yield client, roles, empty_db
    asyncio.run(engine.dispose())


def test_US_NOT_02_AC5_send_auth_and_free_text_rejected(
    notifications_api: tuple[TestClient, dict[str, SimpleNamespace], str],
) -> None:
    client, roles, dsn = notifications_api
    draft = transact(
        dsn,
        lambda session: notify_service.create_delay_draft(
            1, {**WINDOW, "version": 1}, session=session, actor=actor()
        ),
    )
    assert draft is not None
    url = f"/api/v1/notifications/{draft}/send"
    payload = {"eta_window": WINDOW, "version": 1}
    assert client.post(url, json=payload).status_code == 400
    for extra in ("subject", "body", "gps", "driver_name", "cs_notes"):
        response = client.post(
            url,
            json={**payload, extra: "private value"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 422, response.text
    roles["actor"] = actor("customer_service")
    denied = client.post(url, json=payload, headers={"Idempotency-Key": str(uuid4())})
    assert denied.status_code == 403
    roles["actor"] = actor("dispatcher", market="NO")
    hidden = client.post(url, json=payload, headers={"Idempotency-Key": str(uuid4())})
    assert hidden.status_code == 404
    roles["actor"] = actor()
    approved = client.post(url, json=payload, headers={"Idempotency-Key": str(uuid4())})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "queued"


def test_US_NOT_01_AC2_notification_list_scoped_and_preview_masked(
    notifications_api: tuple[TestClient, dict[str, SimpleNamespace], str],
) -> None:
    client, roles, dsn = notifications_api
    transact(dsn, lambda s: notify_service.enqueue(1, "CONFIRMED", 1, session=s))
    listing = client.get("/api/v1/notifications?template=CONFIRMED")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    masked = client.get("/api/v1/notifications/1")
    assert masked.status_code == 200
    body = masked.json()
    assert body["recipient_masked"] == "d***@cfo.test"
    assert body["template"] == "CONFIRMED"
    assert "demo@cfo.test" not in str(body)
    assert "contact_name" not in str(body)
    roles["actor"] = actor("sales")
    assert client.get("/api/v1/notifications").status_code == 403
    roles["actor"] = actor("customer_service", market="NO")
    assert client.get("/api/v1/notifications/1").status_code == 404
    assert client.get("/api/v1/notifications").json()["total"] == 0


def test_US_NOT_02_AC3_discard_request_requires_reason(
    notifications_api: tuple[TestClient, dict[str, SimpleNamespace], str],
) -> None:
    client, _, dsn = notifications_api
    draft = transact(
        dsn,
        lambda s: notify_service.create_delay_draft(1, {**WINDOW, "version": 1}, session=s, actor=actor()),
    )
    assert client.post(f"/api/v1/notifications/{draft}/discard", json={}).status_code == 422
    invalid = client.post(f"/api/v1/notifications/{draft}/discard", json={"reason_text": "  "})
    assert invalid.status_code == 422
    response = client.post(f"/api/v1/notifications/{draft}/discard", json={"reason_text": "Do not notify"})
    assert response.status_code == 200
    assert response.json() == {"id": draft, "status": "suppressed"}
