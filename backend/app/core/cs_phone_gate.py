"""Production-deny gate for phone-shaped GET /orders?q= searches (DEC-INT-CS-GET-PRIVACY).

A GET query can leak in upstream access/WAF/proxy/APM/browser logs *before* this app
receives it. This gate protects the CFO lookup path but cannot redact those sources.
Real-customer phone search requires independently reviewed infrastructure controls
and an explicit opt-in. Local/staging modes MUST use synthetic data only.
"""

import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import error_response

_PHONE_CHARACTERS = re.compile(r"[+0-9 ()./-]+\Z")


def phone_shaped_query(raw: str) -> bool:
    """Match the existing CS phone-query classifier without persisting its value."""
    value = raw.strip()
    digits = re.sub(r"[^0-9]", "", value)
    return bool(_PHONE_CHARACTERS.fullmatch(value)) and (
        value.startswith("+") or len(digits) >= 8
    )


class CsPhoneProductionGate(BaseHTTPMiddleware):
    """Fail closed in non-synthetic environments until explicitly enabled.

    Authentication/market scoping, query specificity and the existing application
    limiter still apply AFTER this gate; none are bypassed by the opt-in.
    """

    def __init__(self, app: object, *, app_env: str, live_enabled: bool = False) -> None:
        super().__init__(app)
        self.app_env = app_env.strip().lower()
        self.live_enabled = live_enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method == "GET"
            and request.url.path == "/api/v1/orders"
            and request.query_params.get("q") is not None
            and phone_shaped_query(request.query_params["q"])
            and self.app_env not in {"local", "test", "staging", "demo"}
            and not self.live_enabled
        ):
            response = error_response(
                request,
                403,
                "FORBIDDEN",
                "Contact-phone lookup is disabled pending production privacy verification.",
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        return await call_next(request)
