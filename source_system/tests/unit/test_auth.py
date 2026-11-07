"""US-SRC-02 foundation: the same protected contract for every source instance."""

import secrets
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.auth import require_api_key
from app.config import Settings
from app.main import create_app

ROUTES = [
    ("GET", "/orders"),
    ("GET", "/customers"),
    ("GET", "/products"),
    ("GET", "/stock"),
    ("GET", "/inbound"),
    ("GET", "/fleet/calendar?date_from=2026-11-01&date_to=2026-11-02"),
    ("GET", "/addresses"),
    ("POST", "/orders"),
    ("PUT", "/orders/test"),
    ("POST", "/orders/test/validate"),
    ("POST", "/orders/test/submit"),
    ("POST", "/orders/test/cancel"),
]


@pytest.mark.parametrize("schema", ["src_se", "src_demo"])
@pytest.mark.parametrize("method,path", ROUTES)
def test_US_SRC_02_AC1_source_routes_reject_missing_and_wrong_key(
    schema: str, method: str, path: str
) -> None:
    key = secrets.token_urlsafe(32)
    app = create_app(Settings("postgresql+asyncpg://localhost/source", schema, key))
    with TestClient(app) as client:
        for headers, status, code in (
            ({}, 400, "VALIDATION_ERROR"),
            ({"X-API-Key": secrets.token_urlsafe(32)}, 401, "AUTH_INVALID"),
        ):
            response = client.request(method, "/api/v1" + path, headers=headers)
            assert response.status_code == status
            error = response.json()["error"]
            assert error["code"] == code
            assert str(UUID(error["correlation_id"])) == response.headers["X-Correlation-ID"]
            assert key not in response.text
            assert all(value not in response.text for value in headers.values())


def test_US_SRC_02_AC1_instance_keys_do_not_authenticate_other_instances() -> None:
    keys = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
    for index, schema in enumerate(("src_se", "src_demo")):
        app = create_app(Settings("postgresql+asyncpg://localhost/source", schema, keys[index]))

        @app.get("/auth-probe", dependencies=[Depends(require_api_key)])
        async def probe() -> dict[str, bool]:
            return {"accepted": True}

        with TestClient(app) as client:
            assert client.get("/auth-probe", headers={"X-API-Key": keys[index]}).json() == {"accepted": True}
            assert client.get("/auth-probe", headers={"X-API-Key": keys[1 - index]}).status_code == 401


@pytest.mark.parametrize("key", ["", "   "])
def test_unconfigured_key_fails_closed(key: str) -> None:
    app = create_app(Settings("postgresql+asyncpg://localhost/source", "src_test", key))
    with TestClient(app) as client:
        response = client.get("/api/v1/products", headers={"X-API-Key": secrets.token_urlsafe(32)})
        assert response.status_code == 401


def test_key_configuration_is_private_and_auth_errors_preserve_correlation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = secrets.token_urlsafe(32)
    monkeypatch.setenv("API_KEY", key)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/source")
    monkeypatch.setenv("SOURCE_SCHEMA", "src_test")
    settings = Settings.from_env()
    assert settings.api_key == key
    assert key not in repr(settings)
    with TestClient(create_app(settings)) as client:
        correlation = str(uuid4())
        response = client.get("/api/v1/products", headers={"X-Correlation-ID": correlation})
        assert response.headers["X-Correlation-ID"] == correlation
        response = client.get("/api/v1/products", headers={"X-Correlation-ID": "invalid"})
        UUID(response.headers["X-Correlation-ID"])


def test_openapi_declares_security_for_every_business_route_only() -> None:
    schema = create_app().openapi()
    assert schema["components"]["securitySchemes"]["APIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            if path == "/api/v1/health":
                assert "security" not in operation
            else:
                assert operation["security"] == [{"APIKeyHeader": []}]
