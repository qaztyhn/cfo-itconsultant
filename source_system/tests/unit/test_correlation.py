from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_US_SRC_02_AC1_correlation_headers_and_error_body_share_one_safe_id() -> None:
    app = create_app(Settings("postgresql+asyncpg://localhost/source", "src_test", "synthetic-key"))
    with TestClient(app) as client:
        app.state.engine = Mock()
        app.state.engine.connect.side_effect = OSError("private-connection-value")
        health = client.get(
            "/api/v1/health", headers={"X-Correlation-ID": "00000000-0000-4000-8000-000000000001"}
        )
        assert health.status_code == 503
        assert health.headers["X-Correlation-ID"] == "00000000-0000-4000-8000-000000000001"
        missing_key = client.get("/api/v1/orders", headers={"X-Correlation-ID": "private-invalid-id"})
        invalid_body = client.post(
            "/api/v1/orders", headers={"X-API-Key": "synthetic-key"}, json={"private": "value"}
        )
        for response in (missing_key, invalid_body):
            value = response.headers["X-Correlation-ID"]
            assert str(UUID(value)) == value and response.json()["error"]["correlation_id"] == value
            assert (
                "private-invalid-id" not in response.text and "private-connection-value" not in response.text
            )
