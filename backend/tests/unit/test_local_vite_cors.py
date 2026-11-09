"""CORS regression for the Vite 5173 to 5174 fallback, local-only.

This tests browser preflight policy, not the presence or success of sync-now.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

REQUEST_HEADERS = "authorization,content-type,idempotency-key,x-correlation-id"


def _preflight(client: TestClient, origin: str):
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": REQUEST_HEADERS,
    }
    return client.options("/api/v1/integration/orders/sync-now", headers=headers)


@pytest.mark.parametrize("origin", ["http://localhost:5174", "http://127.0.0.1:5174"])
def test_US_INT_06_AC1_local_vite_preflight(monkeypatch, origin: str) -> None:
    settings = Settings(app_env="local", cors_origins=["http://localhost:5173"])
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    with TestClient(create_app()) as client:
        response = _preflight(client, origin)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "idempotency-key" in allowed


@pytest.mark.parametrize("app_env", ["demo", "staging", "production"])
def test_US_INT_06_AC1_other_environments_keep_cors(monkeypatch, app_env: str) -> None:
    settings = Settings(app_env=app_env, cors_origins=["https://cfo.example.test"])
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    with TestClient(create_app()) as client:
        blocked = _preflight(client, "http://localhost:5174")
        allowed = _preflight(client, "https://cfo.example.test")
    assert blocked.status_code == 400
    assert "access-control-allow-origin" not in blocked.headers
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://cfo.example.test"
