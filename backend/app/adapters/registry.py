"""Tra adapter theo market_code. Market chưa có adapter → lỗi cấu hình rõ ràng, không ảnh hưởng nước
khác (US-INT-04 AC2).

Owner: Dev 2 (luồng B) — M2.
"""

import os
from collections.abc import Mapping

from app.adapters.rest_adapter import RestMarketAdapter


class AdapterConfigurationError(ValueError):
    """Configuration error contains no key or database values."""


class AdapterRegistry:
    """Instance-scoped registration avoids cross-market fallback or global leakage."""

    def __init__(self) -> None:
        self._adapters: dict[str, RestMarketAdapter] = {}

    def configure(
        self,
        market_code: str,
        base_url: str | None,
        key_ref: str | None,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        env = os.environ if environment is None else environment
        if not base_url or not key_ref or not env.get(key_ref, "").strip():
            raise AdapterConfigurationError("Source URL and API key reference must be configured")
        try:
            adapter = RestMarketAdapter(market_code, base_url, env[key_ref])
        except ValueError:
            raise AdapterConfigurationError("Invalid source adapter configuration") from None
        self._adapters[market_code] = adapter

    def get(self, market_code: str) -> RestMarketAdapter:
        try:
            return self._adapters[market_code]
        except KeyError:
            raise AdapterConfigurationError("No source adapter configured for this market") from None


registry = AdapterRegistry()


def get_adapter(market_code: str) -> RestMarketAdapter:
    return registry.get(market_code)
