"""Lỗi miền và định dạng lỗi chuẩn (06 mục 1.1).

DomainError(code, message, details, http_status) → middleware trả
{"error": {"code", "message", "details", "correlation_id"}}; không lộ stack trace (09 mục 5).
Mã lỗi hợp lệ: ERROR_CODES (06 mục 1.1).

Ngoài DomainError, handler còn chuẩn hóa: lỗi Pydantic → 422 VALIDATION_ERROR (không trả lại giá trị đầu vào,
vì có thể chứa mật khẩu/PII); HTTPException (404 route, 405…) → mã tương ứng; lỗi không bắt → 500
INTERNAL_ERROR không kèm stack trace (06 v1.2.1, chờ duyệt).
Mọi phản hồi lỗi có correlation_id và header X-Correlation-ID.

Owner: Dev 1 (luồng A) — M0.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import log_event

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
    "INTERNAL_ERROR": 500,  # 06 v1.2.1 — chờ duyệt (CHANGELOG)
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


# 06 v1.2.1 (chờ duyệt, CHANGELOG): mã kỹ thuật cho lỗi không bắt.
INTERNAL_ERROR = "INTERNAL_ERROR"
_HTTP_STATUS_CODES = {401: "AUTH_INVALID", 403: "FORBIDDEN", 404: "NOT_FOUND", 422: "VALIDATION_ERROR"}


def error_response(
    request: Request, status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    """Phản hồi lỗi chuẩn 06 mục 1.1 (kèm correlation_id ở thân và header)."""
    cid = getattr(request.state, "correlation_id", None)
    response = JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "details": details or {}, "correlation_id": cid}
        },
    )
    if cid:
        response.headers["X-Correlation-ID"] = cid
    return response


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Chỉ giữ vị trí, loại và thông báo — bỏ `input`/`ctx` để không phản hồi lại mật khẩu hay PII."""
    return [
        {"loc": list(err.get("loc", ())), "type": err.get("type"), "msg": err.get("msg")}
        for err in exc.errors()
    ]


def install_error_handlers(app: FastAPI) -> None:
    """Đăng ký handler chuyển mọi lỗi về định dạng chuẩn kèm correlation_id."""

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(request, exc.http_status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            request,
            422,
            "VALIDATION_ERROR",
            "Request validation failed.",
            {"errors": _safe_validation_errors(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_STATUS_CODES.get(
            exc.status_code, "VALIDATION_ERROR" if exc.status_code < 500 else INTERNAL_ERROR
        )
        response = error_response(request, exc.status_code, code, str(exc.detail))
        for key, value in (exc.headers or {}).items():
            response.headers[key] = value
        return response

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # contextvar đã bị middleware reset khi exception thoát ra; lấy ID trực tiếp từ request.state.
        log_event(
            "api",
            "request.unhandled_error",
            level="error",
            correlation_id=getattr(request.state, "correlation_id", None),
            path=request.url.path,
            error=type(exc).__name__,
        )
        return error_response(request, 500, INTERNAL_ERROR, "Internal server error.")
