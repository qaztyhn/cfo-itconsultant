"""Standard error bodies (06 section 2): no echoed input values, no stack traces, no internal messages."""

from uuid import UUID, uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    try:
        correlation_id = str(UUID(request.headers.get("X-Correlation-ID", "")))
    except ValueError:
        correlation_id = str(uuid4())
    errors = [
        {"loc": list(err.get("loc", ())), "type": err.get("type"), "msg": err.get("msg")}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        headers={"X-Correlation-ID": correlation_id},
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": {"errors": errors},
                "correlation_id": correlation_id,
            }
        },
    )


class EndpointNotImplemented(Exception):
    """Contract endpoint that is routed but not built yet; answered with a controlled 501."""


def _correlation_id(request: Request) -> str:
    try:
        return str(UUID(request.headers.get("X-Correlation-ID", "")))
    except ValueError:
        return str(uuid4())


def _body(request: Request, status: int, code: str, message: str) -> JSONResponse:
    correlation_id = _correlation_id(request)
    return JSONResponse(
        status_code=status,
        headers={"X-Correlation-ID": correlation_id},
        content={
            "error": {"code": code, "message": message, "details": {}, "correlation_id": correlation_id}
        },
    )


async def not_implemented(request: Request, exc: Exception) -> JSONResponse:
    return _body(request, 501, "NOT_IMPLEMENTED", "This source endpoint is not implemented yet.")


async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    return _body(request, 500, "INTERNAL_ERROR", "Internal server error.")
