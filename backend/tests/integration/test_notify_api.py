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
from tests.integration import rows
from tests.integration.conftest import async_url, execute, fetch
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
    roles["actor"] = actor("admin")
    assert client.get(f"/api/v1/notifications/{draft}").status_code == 200
    assert client.post(url, json=payload, headers={"Idempotency-Key": str(uuid4())}).status_code == 403
    assert (
        client.post(f"/api/v1/notifications/{draft}/discard", json={"reason_text": "Read-only"}).status_code
        == 403
    )
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
    assert listing.json()["items"][0]["order_no"] == "ZZ-000001"
    masked = client.get("/api/v1/notifications/1")
    assert masked.status_code == 200
    body = masked.json()
    assert body["recipient_masked"] == "d***@cfo.test"
    assert body["template"] == "CONFIRMED"
    assert body["order_no"] == "ZZ-000001"
    assert body["market_timezone"] == "Europe/Stockholm"
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


def test_US_NOT_02_AC2_draft_detail_exposes_approved_version(
    notifications_api: tuple[TestClient, dict[str, SimpleNamespace], str],
) -> None:
    client, _, dsn = notifications_api
    draft = transact(
        dsn,
        lambda s: notify_service.create_delay_draft(1, {**WINDOW, "version": 3}, session=s, actor=actor()),
    )
    assert draft is not None
    detail = client.get(f"/api/v1/notifications/{draft}")
    assert detail.status_code == 200
    assert detail.json()["eta_window"] == {**WINDOW, "version": 3}
    assert detail.json()["order_no"] == "ZZ-000001"
    assert detail.json()["market_timezone"] == "Europe/Stockholm"
    assert detail.json()["committed_date"] == "2026-11-10"


@pytest.mark.parametrize("return_to_commitment", [False, True], ids=["saved_move", "return_to_commitment"])
def test_US_NOT_02_AC2_send_uses_committed_market_date(
    notifications_api: tuple[TestClient, dict[str, SimpleNamespace], str],
    return_to_commitment: bool,
) -> None:
    client, _, dsn = notifications_api
    execute(
        dsn,
        rows.order_sql(2),
        "INSERT INTO ops.date_negotiation(order_id,proposed_date,outcome,channel,contacted_at,recorded_by)"
        " VALUES (1,'2026-11-11','agreed','phone','2026-11-09T09:00Z',1),"
        "(2,'2026-11-11','agreed','phone','2026-11-09T09:00Z',1),"
        "(1,'2026-11-11','declined','phone','2026-11-09T09:00Z',1),"
        "(1,'2026-11-12','agreed','phone','2026-11-09T09:00Z',1)",
    )
    # Start's UTC date differs from its Stockholm date in both windows.
    moved = {"start": "2026-11-10T23:15:00Z", "end": "2026-11-11T00:15:00Z"}
    draft = transact(
        dsn,
        lambda session: notify_service.create_delay_draft(
            1, {**moved, "version": 3, "date_negotiation_id": 1}, session=session, actor=actor()
        ),
    )
    detail = client.get(f"/api/v1/notifications/{draft}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["committed_date"] == "2026-11-10"
    assert detail.json()["eta_window"]["version"] == 3
    url = f"/api/v1/notifications/{draft}/send"
    if return_to_commitment:
        committed = {"start": "2026-11-09T23:15:00Z", "end": "2026-11-10T00:15:00Z"}
        payload: dict[str, object] = {"eta_window": committed, "version": 4}
    else:
        for invalid_agreement in (
            {},
            {"date_negotiation_id": 2},
            {"date_negotiation_id": 3},
            {"date_negotiation_id": 4},
        ):
            rejected = client.post(
                url,
                json={"eta_window": moved, "version": 3, **invalid_agreement},
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert rejected.status_code == 409
            assert rejected.json()["error"]["code"] == "DATE_AGREEMENT_REQUIRED"
            assert (
                "date negotiation ID" in rejected.text or "ID of an agreed date negotiation" in rejected.text
            )
        payload = {"eta_window": moved, "version": 3, "date_negotiation_id": 1}

    headers = {"Idempotency-Key": str(uuid4())}
    sent = client.post(url, json=payload, headers=headers)
    assert sent.status_code == 200, sent.text
    result = sent.json()
    assert (result["id"], result["template"], result["status"], result["version"]) == (
        draft,
        "DELAY",
        "queued",
        payload["version"],
    )
    assert client.post(url, json=payload, headers=headers).json() == result
    queued = client.get(f"/api/v1/notifications/{draft}").json()
    assert queued["committed_date"] == "2026-11-10"
    assert queued["eta_window"]["version"] == payload["version"]


def test_US_NOT_02_AC1_order_routes_reachable_without_orders_stubs(
    notifications_api: tuple[TestClient, dict[str, SimpleNamespace], str],
) -> None:
    client, roles, _dsn = notifications_api
    # The orders router previously shadowed both paths with NotImplementedError.
    listing = client.get("/api/v1/orders/1/notifications")
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 0
    draft = client.post("/api/v1/orders/1/delay-notice", json={**WINDOW, "version": 1})
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "draft"
    assert client.get("/api/v1/orders/1/notifications").json()["total"] == 1

    roles["actor"] = actor("customer_service")
    assert client.get("/api/v1/orders/1/notifications").status_code == 200
    assert client.post("/api/v1/orders/1/delay-notice", json={**WINDOW, "version": 2}).status_code == 403
    roles["actor"] = actor("dispatcher", market="NO")
    assert client.get("/api/v1/orders/1/notifications").status_code == 404
    assert client.post("/api/v1/orders/1/delay-notice", json={**WINDOW, "version": 2}).status_code == 404


def test_US_NOT_02_no_email_reports_suppressed_instead_of_a_sendable_draft(
    notifications_api: tuple[TestClient, dict[str, SimpleNamespace], str],
) -> None:
    client, _, dsn = notifications_api
    execute(dsn, "UPDATE ref.customer SET email = NULL WHERE id = 1")
    response = client.post("/api/v1/orders/1/delay-notice", json={**WINDOW, "version": 1})
    assert response.status_code == 200
    assert response.json()["status"] == "suppressed"
    assert tuple(fetch(dsn, "SELECT recipient, skipped_reason FROM ops.notification")[0]) == (
        None,
        "SKIPPED_NO_CHANNEL",
    )
    assert client.get("/api/v1/notifications/1").json()["committed_date"] == "2026-11-10"
