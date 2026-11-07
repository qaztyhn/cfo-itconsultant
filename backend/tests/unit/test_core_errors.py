"""Định dạng lỗi chuẩn 06 mục 1.1 cho mọi loại lỗi, kèm correlation_id; không lộ stack trace/đầu vào."""

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core import logging as cfo_logging
from app.core.errors import DomainError
from app.main import create_app


class _Body(BaseModel):
    password: str
    qty: int


def _probe() -> APIRouter:
    router = APIRouter()

    @router.get("/_probe/domain")
    async def domain() -> None:
        raise DomainError("HOLD_EXPIRED", "Planning hold expired. Re-run planning.", {"run_id": 812})

    @router.get("/_probe/crash")
    async def crash() -> None:
        raise RuntimeError("secret connection string postgresql://u:p@db/x")

    @router.post("/_probe/body")
    async def body(payload: _Body) -> dict[str, int]:
        return {"qty": payload.qty}

    return router


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.include_router(_probe(), prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _error(response: object) -> dict[str, object]:
    body = response.json()  # type: ignore[attr-defined]
    assert set(body) == {"error"}
    error: dict[str, object] = body["error"]
    assert set(error) == {"code", "message", "details", "correlation_id"}
    assert error["correlation_id"] == response.headers["X-Correlation-ID"]  # type: ignore[attr-defined]
    return error


def test_domain_error_standard_format_and_client_correlation_id(client: TestClient) -> None:
    cid = "6c0f6c0f-0000-4000-8000-000000000002"
    response = client.get("/api/v1/_probe/domain", headers={"X-Correlation-ID": cid})
    assert response.status_code == 409
    error = _error(response)
    assert error == {
        "code": "HOLD_EXPIRED",
        "message": "Planning hold expired. Re-run planning.",
        "details": {"run_id": 812},
        "correlation_id": cid,
    }


def test_validation_error_422_without_echoing_input(client: TestClient) -> None:
    response = client.post("/api/v1/_probe/body", json={"password": "hunter2-secret", "qty": "many"})
    assert response.status_code == 422
    error = _error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert "hunter2-secret" not in response.text and "many" not in response.text
    assert error["details"]["errors"][0]["loc"] == ["body", "qty"]  # type: ignore[index]


def test_unknown_route_404_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404 and _error(response)["code"] == "NOT_FOUND"


def test_unhandled_error_500_without_stack_trace_or_message(client: TestClient) -> None:
    response = client.get("/api/v1/_probe/crash")
    assert response.status_code == 500
    error = _error(response)
    assert error["code"] == "INTERNAL_ERROR" and error["message"] == "Internal server error."
    assert "Traceback" not in response.text and "postgresql://" not in response.text


@pytest.mark.parametrize("header", ["request-123", "", "   ", "6c0f6c0f-0000-4000-8000", "x" * 300])
def test_invalid_correlation_header_replaced_by_uuid(client: TestClient, header: str) -> None:
    response = client.get("/api/v1/_probe/domain", headers={"X-Correlation-ID": header})
    cid = response.headers["X-Correlation-ID"]
    assert str(uuid.UUID(cid)) == cid and cid != header.strip()
    assert _error(response)["correlation_id"] == cid


def test_valid_correlation_header_normalised_and_echoed(client: TestClient) -> None:
    response = client.get(
        "/api/v1/_probe/domain", headers={"X-Correlation-ID": " 6C0F6C0F-0000-4000-8000-000000000003 "}
    )
    assert response.headers["X-Correlation-ID"] == "6c0f6c0f-0000-4000-8000-000000000003"


@pytest.mark.parametrize("header", ["6c0f6c0f-0000-4000-8000-000000000004", None])
def test_unhandled_error_log_has_same_correlation_id_as_response(
    client: TestClient, tmp_path: Path, header: str | None
) -> None:
    cfo_logging.configure_logging(tmp_path)
    try:
        response = client.get("/api/v1/_probe/crash", headers={"X-Correlation-ID": header} if header else {})
    finally:
        cfo_logging.configure_logging(None)
    (log_file,) = (tmp_path / "api").glob("*.jsonl")
    (record,) = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert record["event"] == "request.unhandled_error"
    assert (
        record["correlation_id"] == response.headers["X-Correlation-ID"] == _error(response)["correlation_id"]
    )
    assert record["correlation_id"] is not None
    assert "postgresql://" not in log_file.read_text(encoding="utf-8")
