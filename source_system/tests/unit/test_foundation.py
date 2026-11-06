"""M0 configuration and HTTP health behavior, including database failure."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize("schema", ["public", "src_", "src_SE", "src_se; DROP SCHEMA public"])
def test_rejects_invalid_source_schema(schema: str) -> None:
    with pytest.raises(ValueError, match="SOURCE_SCHEMA"):
        Settings("postgresql+asyncpg://localhost/source", schema)


@pytest.mark.parametrize("url", ["", "invalid", "sqlite:///source.db", "postgresql://localhost/source"])
def test_rejects_invalid_database_configuration(url: str) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(url, "src_test")


def test_settings_do_not_display_database_url() -> None:
    settings = Settings("postgresql+asyncpg://localhost/source", "src_test")
    assert settings.database_url not in repr(settings)


@pytest.mark.parametrize("failure", [OSError, TimeoutError, RuntimeError])
def test_health_returns_503_without_leaking_database_errors(failure: type[Exception]) -> None:
    app = create_app(Settings("postgresql+asyncpg://localhost/source", "src_test"))
    with TestClient(app) as client:
        app.state.engine = Mock()
        app.state.engine.connect.side_effect = failure("private database connection information")
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "unavailable"}
    assert "private" not in response.text
