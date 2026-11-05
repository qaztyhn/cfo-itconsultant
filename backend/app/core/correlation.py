"""Middleware X-Correlation-ID (06 mục 1, 04 mục 10).

Nhận header từ client hoặc sinh uuid4; gắn vào request.state và contextvar để log kỹ thuật,
decision_log và job dùng chung (US-LOG-01 AC4); luôn trả lại header.

Owner: Dev 1 (luồng A) — M0.
"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Gắn correlation_id cho mỗi request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = cid
        token = correlation_id_var.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Correlation-ID"] = cid
        return response
