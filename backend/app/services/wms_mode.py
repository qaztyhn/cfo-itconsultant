"""Công tắc rõ ràng cho đường đặt giữ hàng WMS mô phỏng (E1, DEC-WMS-RESERVE-SYNC-20261109).

Mặc định TẮT. Đường mô phỏng chỉ chạy khi đủ cả bốn điều kiện: WMS_RESERVATION_MODE=simulated,
APP_ENV=test, DEMO_DISPOSABLE=1 và APP_NOW là đồng hồ demo. Yêu cầu bật mô phỏng ở môi trường
khác (hoặc giá trị mode lạ) bị từ chối bằng 409 PLAN_NOT_APPROVABLE TRƯỚC khi gọi adapter.
"""

import os

from app.adapters.synthetic_wms import DEMO_NOW
from app.core.config import get_settings
from app.core.errors import DomainError

_MODES = ("disabled", "simulated")


def _mode() -> str:
    return (get_settings().wms_reservation_mode or "disabled").strip().lower()


def simulated_enabled() -> bool:
    """True chỉ khi đường mô phỏng được yêu cầu VÀ môi trường cho phép (không ném lỗi)."""
    settings = get_settings()
    return (
        _mode() == "simulated"
        and settings.app_env == "test"
        and os.environ.get("DEMO_DISPOSABLE") == "1"
        and settings.app_now == DEMO_NOW
    )


def require_simulated_or_off() -> bool:
    """False: mode tắt, giữ hành vi hiện có. True: được phép chạy đường mô phỏng.

    Mode lạ hoặc "simulated" ở môi trường không cho phép -> 409 PLAN_NOT_APPROVABLE.
    """
    mode = _mode()
    if mode not in _MODES:
        raise DomainError("PLAN_NOT_APPROVABLE", "WMS reservation mode is invalid.")
    if mode == "disabled":
        return False
    if not simulated_enabled():
        raise DomainError(
            "PLAN_NOT_APPROVABLE",
            "Simulated WMS reservation is not permitted in this environment.",
        )
    return True
