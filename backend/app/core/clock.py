"""Đồng hồ duy nhất của hệ thống (09 bất biến 17, 08 mục 1.6).

Mọi mã nghiệp vụ lấy giờ qua `clock.now()`; KHÔNG gọi datetime.now()/date.today() ở nơi khác
(ruff DTZ chặn). Khi đặt APP_NOW, đồng hồ đứng yên ở thời điểm đó để demo/test lặp lại được.
Engine không import module này: "bây giờ" được truyền vào engine qua tham số `now`.

Owner: Dev 1 (luồng A) — M0.
"""

from datetime import UTC, datetime

_frozen: datetime | None = None


def set_now(value: datetime | None) -> None:
    """Đặt (hoặc bỏ) thời điểm cố định — dùng trong test và khi khởi động với APP_NOW."""
    global _frozen
    if value is not None and value.tzinfo is None:
        raise ValueError("clock.set_now requires a timezone-aware datetime")
    _frozen = value


def now() -> datetime:
    """Thời điểm hiện tại, luôn có múi giờ (UTC nếu không cố định)."""
    return _frozen if _frozen is not None else datetime.now(UTC)


def init_from_settings(app_now: str | None) -> None:
    """Đọc chuỗi ISO 8601 từ APP_NOW (nếu có) và cố định đồng hồ."""
    set_now(datetime.fromisoformat(app_now) if app_now else None)
