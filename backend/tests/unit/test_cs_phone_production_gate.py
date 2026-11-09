"""BE-02: production phone-search gate and first-party application-log safety.

These tests are local and do NOT prove ingress, proxy, WAF, APM or browser-history
protection. The disabled production path executes no database access.
"""

from fastapi.testclient import TestClient

from app.core import logging as cfo_logging
from app.core.config import Settings
from app.core.cs_phone_gate import phone_shaped_query
from app.main import create_app


def test_be02_classifier_matches_cs_phone_shapes_without_short_fragment() -> None:
    assert phone_shaped_query("+46 (70) 123-45-67")
    assert phone_shaped_query("0046701234567")
    assert not phone_shaped_query("POS-137")
    assert not phone_shaped_query("1234567")
    assert phone_shaped_query("+46")  # attempts are blocked even when too short for search


def test_be02_production_disabled_without_opt_in(monkeypatch) -> None:
    settings = Settings(app_env="production", cs_phone_search_production_enabled=False)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/v1/orders", params={"q": "+46 70 123 45 67"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.json()["error"]["correlation_id"] == response.headers["X-Correlation-ID"]
        assert "+46" not in response.text
        assert "1234567" not in response.text
        # Non-phone requests still enter the usual auth/RBAC flow.
        assert client.get("/api/v1/orders", params={"q": "POS-137"}).status_code == 401
        assert client.get("/api/v1/orders", params={"q": "Erik"}).status_code == 401


def test_be02_explicit_production_opt_in_does_not_bypass_authentication(monkeypatch) -> None:
    settings = Settings(app_env="production", cs_phone_search_production_enabled=True)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        assert client.get("/api/v1/orders", params={"q": "+46701234567"}).status_code == 401


def test_be02_app_log_query_redaction_with_nested_url() -> None:
    raw = "+46701234567"
    built = cfo_logging.build_record(
        "api",
        "request GET /api/v1/orders?q=%2B46701234567",
        q=raw,
        nested={"request_url": "https://example.test/api/v1/orders?q=%2B46701234567"},
        detail="blocked GET /api/v1/orders?q=%2B46701234567",
    )
    import json

    rendered = json.dumps(built)
    assert raw not in rendered
    assert "46701234567" not in rendered
    assert "request_url" not in rendered
    assert built["extra"]["nested"] == {}
    assert "[redacted]" in rendered
