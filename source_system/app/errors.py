"""Standard error body for framework validation errors (06 section 2): no echoed input values."""

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
