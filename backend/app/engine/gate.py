"""Bước 3 — gate 5 check (04 mục 6.2; BR-GATE-01).

Thứ tự stock → preparation → truck → site_date → safety; dừng ở lỗi đầu tiên.
failed_check khi không còn ứng viên = check xa nhất mà ít nhất một kho đã tới (hòa → check sớm hơn).
Mã: STOCK_OK/STOCK_AFTER_INBOUND/STOCK_SHORT, PREP_OK/PREP_AFTER_CUTOFF/PREP_NO_CAPACITY,
TRUCK_OK/NO_TRUCK_FIT/TRUCK_BUSY/NO_DRIVER, DATE_OK/OUTSIDE_RECEIVING_HOURS/DATE_AFTER_DEADLINE/
NON_WORKING_DAY/ROUTE_DATA_UNAVAILABLE, SAFETY_OK/OVER_LOAD/DRIVER_HOURS_EXCEEDED/LICENCE_EXPIRED.

Owner: Dev 1 (luồng A).
"""

from app.engine.types import CheckNameT, CheckResult

CHECK_ORDER: tuple[CheckNameT, ...] = ("stock", "preparation", "truck", "site_date", "safety")


def all_passed(checks: tuple[CheckResult, ...]) -> bool:
    """True nếu đủ 5 check và đều đạt."""
    return len(checks) == len(CHECK_ORDER) and all(c.passed for c in checks)


def first_failure(checks: tuple[CheckResult, ...]) -> CheckResult | None:
    """Check hỏng đầu tiên của một ứng viên (gate dừng ở lỗi đầu tiên)."""
    return next((c for c in checks if not c.passed), None)


def furthest_failed_check(reached: list[tuple[CheckResult, ...]]) -> CheckNameT | None:
    """Check xa nhất trong thứ tự mà ít nhất một kho đã tới rồi hỏng.

    Mỗi phần tử của `reached` là các check một kho đã chạy (dừng ở lỗi đầu tiên).
    """
    failed = [f.name for f in (first_failure(checks) for checks in reached) if f is not None]
    if not failed:
        return None
    return max(failed, key=CHECK_ORDER.index)
