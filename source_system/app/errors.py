"""Standard error body for framework validation errors (06 section 2): no echoed input values."""

from uuid import UUID, uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class ErrorItem(BaseModel):
    loc: list[str | int]
    type: str
    msg: str


class ErrorDetails(BaseModel):
    errors: list[ErrorItem] | None = None


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    details: ErrorDetails
    correlation_id: UUID


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def request_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    if isinstance(value, str):
        return value
    try:
        value = str(UUID(request.headers.get("X-Correlation-ID", "")))
    except ValueError:
        value = str(uuid4())
    request.state.correlation_id = value
    return value


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
    correlation_id = request_id(request)
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
    correlation_id = request_id(request)
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
