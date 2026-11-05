"""Lỗi miền và định dạng lỗi chuẩn (06 mục 1.1).

DomainError(code, message, details, http_status) → middleware trả
{"error": {"code", "message", "details", "correlation_id"}}; không lộ stack trace (09 mục 5).
Mã lỗi hợp lệ: ERROR_CODES (06 mục 1.1).

Owner: Dev 1 (luồng A) — M0.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

ERROR_CODES: dict[str, int] = {
    "AUTH_INVALID": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "ILLEGAL_TRANSITION": 409,
    "REASON_REQUIRED": 422,
    "SKU_UNMAPPED": 409,
    "HOLD_EXPIRED": 409,
    "HOLD_EXTENSION_LIMIT": 409,
    "RESOURCE_CONFLICT": 409,
    "PLAN_NOT_APPROVABLE": 409,
    "DATE_AGREEMENT_REQUIRED": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "GPS_DISABLED": 403,
    "NOT_ON_TRIP": 409,
    "LICENCE_EXPIRED": 422,
    "ORDER_LOCKED_AFTER_DISPATCH": 409,
    "DUPLICATE_EVENT": 409,
    "SYNC_IN_PROGRESS": 409,
}


class DomainError(Exception):
    """Lỗi nghiệp vụ có mã chuẩn."""

    def __init__(
        self, code: str, message: str, details: dict[str, Any] | None = None, http_status: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status or ERROR_CODES.get(code, 400)


def install_error_handlers(app: FastAPI) -> None:
    """Đăng ký handler chuyển DomainError về định dạng chuẩn kèm correlation_id."""

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", None)
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "correlation_id": cid,
                }
            },
        )
