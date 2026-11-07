"""Middleware X-Correlation-ID (06 mục 1, 04 mục 10).

Nhận header từ client nếu là UUID hợp lệ (chuẩn hóa), ngược lại sinh uuid4 mới;
gắn vào request.state và contextvar để log kỹ thuật,
decision_log và job dùng chung (US-LOG-01 AC4); luôn trả lại header.

Owner: Dev 1 (luồng A) — M0.
"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def normalize_correlation_id(value: str | None) -> str:
    """UUID hợp lệ → dạng chuẩn; thiếu/không hợp lệ (vd. "request-123") → uuid4 mới.

    `audit.decision_log.correlation_id` là cột uuid NOT NULL: giá trị lạ từ client không được làm hỏng
    INSERT nhật ký và rollback nghiệp vụ (06 mục 1: header là uuid).
    """
    if value:
        try:
            return str(uuid.UUID(value.strip()))
        except ValueError:
            pass
    return str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Gắn correlation_id cho mỗi request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = normalize_correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = cid
        token = correlation_id_var.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Correlation-ID"] = cid
        return response
