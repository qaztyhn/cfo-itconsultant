"""Standard error body for framework validation errors (06 section 2): no echoed input values."""

from uuid import UUID, uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class SourceOrderError(Exception):
    def __init__(
        self, status: int, code: str, message: str, errors: list[dict[str, object]] | None = None
    ) -> None:
        self.status, self.code, self.message, self.errors = status, code, message, errors or []


def invalid(field: str, kind: str) -> SourceOrderError:
    return SourceOrderError(
        422,
        "VALIDATION_ERROR",
        "Order validation failed.",
        [{"loc": ["body", field], "type": kind, "msg": "Order field is invalid."}],
    )


async def order_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, SourceOrderError)
    try:
        correlation_id = str(UUID(request.headers.get("X-Correlation-ID", "")))
    except ValueError:
        correlation_id = str(uuid4())
    return JSONResponse(
        status_code=exc.status,
        headers={"X-Correlation-ID": correlation_id},
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": {"errors": exc.errors},
                "correlation_id": correlation_id,
            }
        },
    )


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


class StockUnavailable(Exception):
    """No complete published stock batch (DEC-SRC-Q9-ERROR-001): unknown, never zero stock."""


async def stock_unavailable(request: Request, exc: Exception) -> JSONResponse:
    try:
        correlation_id = str(UUID(request.headers.get("X-Correlation-ID", "")))
    except ValueError:
        correlation_id = str(uuid4())
    return JSONResponse(
        status_code=503,
        headers={"X-Correlation-ID": correlation_id},
        content={
            "error": {
                "code": "STOCK_UNAVAILABLE",
                "message": "Stock snapshot is unavailable.",
                "details": {},
                "correlation_id": correlation_id,
            }
        },
    )
