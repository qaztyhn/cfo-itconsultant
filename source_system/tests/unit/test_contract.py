"""OpenAPI baseline and controlled errors for unbuilt endpoints (06 section 16; D1 contract tests)."""

from pathlib import Path
from uuid import UUID

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

KEY = "contract-test-key-not-a-secret"
BASELINE = Path(__file__).resolve().parents[2] / "openapi.yaml"
UNBUILT = [
    ("POST", "/orders"),
    ("PUT", "/orders/test"),
    ("POST", "/orders/test/validate"),
    ("POST", "/orders/test/submit"),
    ("POST", "/orders/test/cancel"),
]


def _app(schema: str) -> FastAPI:
    return create_app(Settings("postgresql+asyncpg://localhost/source", schema, KEY))


@pytest.mark.parametrize("schema", ["src_se", "src_demo"])
def test_openapi_matches_approved_baseline_for_every_instance(schema: str) -> None:
    baseline = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    assert baseline["paths"], "baseline must not be empty"
    assert _app(schema).openapi() == baseline  # run `python -m app.openapi_export` and review the diff


def test_baseline_documents_only_built_endpoints_and_declares_the_key() -> None:
    spec = yaml.safe_load(BASELINE.read_text(encoding="utf-8"))
    assert sorted(spec["paths"]) == [
        "/api/v1/addresses", "/api/v1/customers", "/api/v1/fleet/calendar", "/api/v1/health",
        "/api/v1/inbound", "/api/v1/orders", "/api/v1/products", "/api/v1/stock",
    ]  # fmt: skip
    assert all(set(op) <= {"get"} for op in spec["paths"].values())  # no stub is presented as a contract
    assert spec["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"


@pytest.mark.parametrize(("method", "path"), UNBUILT)
def test_unbuilt_endpoints_answer_controlled_501_after_authentication(method: str, path: str) -> None:
    with TestClient(_app("src_se")) as client:
        denied = client.request(method, "/api/v1" + path)
        assert denied.status_code == 400  # key is still required first
        response = client.request(method, "/api/v1" + path, headers={"X-API-Key": KEY})
    assert response.status_code == 501
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("NOT_IMPLEMENTED", {})
    assert str(UUID(error["correlation_id"])) == response.headers["X-Correlation-ID"]
    assert "Traceback" not in response.text and "EndpointNotImplemented" not in response.text


def test_unexpected_errors_never_leak_internals() -> None:
    app = _app("src_se")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret-internal-detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-internal-detail" not in response.text
