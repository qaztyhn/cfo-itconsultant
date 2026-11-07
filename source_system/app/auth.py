"""Source shared-key authentication (06 section 16); never expose credentials."""

from secrets import compare_digest
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

header = APIKeyHeader(name="X-API-Key", auto_error=False)


class SourceAuthenticationError(Exception):
    def __init__(self, missing: bool) -> None:
        self.missing = missing


async def require_api_key(request: Request, supplied: Annotated[str | None, Security(header)]) -> None:
    expected = request.app.state.settings.api_key
    if not supplied:
        raise SourceAuthenticationError(missing=True)
    if not expected.strip() or not compare_digest(supplied.encode(), expected.encode()):
        raise SourceAuthenticationError(missing=False)


async def authentication_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, SourceAuthenticationError)
    try:
        correlation_id = str(UUID(request.headers.get("X-Correlation-ID", "")))
    except ValueError:
        correlation_id = str(uuid4())
    return JSONResponse(
        status_code=400 if exc.missing else 401,
        headers={"X-Correlation-ID": correlation_id},
        content={
            "error": {
                "code": "VALIDATION_ERROR" if exc.missing else "AUTH_INVALID",
                "message": "X-API-Key is required." if exc.missing else "Invalid API key.",
                "details": {},
                "correlation_id": correlation_id,
            }
        },
    )
