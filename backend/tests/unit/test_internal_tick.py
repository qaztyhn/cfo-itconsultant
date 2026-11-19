"""Internal tick must authenticate before dispatch and honor explicit job scope."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import internal
from app.main import app


def test_US_NOT_01_AC3_tick_rejects_missing_wrong_or_unconfigured_key(monkeypatch) -> None:
    handler = AsyncMock(return_value=1)
    monkeypatch.setattr(internal.hold_expiry, "run", handler)
    client = TestClient(app)
    for configured, supplied in (("secret", None), ("secret", "wrong"), ("", "secret")):
        monkeypatch.setattr(
            internal,
            "get_settings",
            lambda key=configured: SimpleNamespace(internal_tick_key=key, app_env="test"),
        )
        headers = {"X-Internal-Key": supplied} if supplied else {}
        response = client.post("/api/v1/internal/tick?job=hold_expiry", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTH_INVALID"
    handler.assert_not_awaited()


@pytest.mark.parametrize("raw_header", [b"bad-\xe9", b"secret-\xff", b"\xc3\xa9"])
def test_US_NOT_01_AC3_tick_rejects_non_ascii_key_before_handler(monkeypatch, raw_header) -> None:
    monkeypatch.setattr(
        internal, "get_settings", lambda: SimpleNamespace(internal_tick_key="secret", app_env="test")
    )
    handler = AsyncMock(return_value=1)
    monkeypatch.setattr(internal.hold_expiry, "run", handler)
    # Byte-valued header reaches ASGI; httpx can reject Unicode str earlier.
    response = TestClient(app).post(
        "/api/v1/internal/tick?job=hold_expiry",
        headers=[(b"x-internal-key", raw_header)],
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"
    handler.assert_not_awaited()


def test_US_RES_01_AC4_tick_dispatches_global_job_and_rejects_unknown(monkeypatch) -> None:
    monkeypatch.setattr(
        internal, "get_settings", lambda: SimpleNamespace(internal_tick_key="secret", app_env="test")
    )
    handler = AsyncMock(return_value=2)
    monkeypatch.setattr(internal.hold_expiry, "run", handler)
    client = TestClient(app)
    headers = {"X-Internal-Key": "secret"}
    response = client.post("/api/v1/internal/tick?job=hold_expiry", headers=headers)
    assert response.status_code == 200
    assert response.json()["processed"] == 2
    assert response.json()["correlation_id"] == response.headers["X-Correlation-ID"]
    assert client.post("/api/v1/internal/tick?job=retention", headers=headers).status_code == 422
    assert client.post("/api/v1/internal/tick?job=hold_expiry&market=SE", headers=headers).status_code == 422
    handler.assert_awaited_once()


def test_D8_tick_is_disabled_outside_demo_and_staging(monkeypatch) -> None:
    monkeypatch.setattr(
        internal, "get_settings", lambda: SimpleNamespace(internal_tick_key="secret", app_env="production")
    )
    handler = AsyncMock(return_value=1)
    monkeypatch.setattr(internal.hold_expiry, "run", handler)
    response = TestClient(app).post(
        "/api/v1/internal/tick?job=hold_expiry", headers={"X-Internal-Key": "secret"}
    )
    assert response.status_code == 403
    handler.assert_not_awaited()


def test_US_NOT_01_AC3_tick_passes_market_to_outbox(monkeypatch) -> None:
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalar(self, _query):
            return 1

    monkeypatch.setattr(
        internal, "get_settings", lambda: SimpleNamespace(internal_tick_key="secret", app_env="test")
    )
    monkeypatch.setattr(internal, "get_sessionmaker", lambda: FakeSession)
    handler = AsyncMock(return_value=1)
    monkeypatch.setattr(internal.outbox, "run", handler)
    client = TestClient(app)
    headers = {"X-Internal-Key": "secret"}
    assert client.post("/api/v1/internal/tick?job=notify_outbox", headers=headers).status_code == 422
    response = client.post("/api/v1/internal/tick?job=notify_outbox&market=SE", headers=headers)
    assert response.status_code == 200
    assert response.json()["processed"] == 1
    handler.assert_awaited_once_with(market_code="SE")
