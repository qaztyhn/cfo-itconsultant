"""Bảo mật: băm mật khẩu argon2, phát/kiểm JWT HS256 (hết hạn 8 giờ), giới hạn tần suất login.

Claims JWT: sub (user id), roles, employee_id, location_ids, market, kpi_scopes (06 mục 4).
Quá 5 lần/phút → 429 (06 mục 4).

- Hạn token tính theo `clock.now()` (09 bất biến 17) để đúng cả khi APP_NOW cố định đồng hồ demo.
- Bộ đếm tần suất dùng đồng hồ đơn điệu của tiến trình (thời gian kỹ thuật, không phải giờ nghiệp vụ),
  nên không bị "đóng băng" khi đặt APP_NOW. In-memory theo tiến trình — đủ cho MVP một instance (ASM-003).
- Không ghi mật khẩu, hash hay token ra log (09 bất biến 16, 25).

Owner: Dev 1 (luồng A) — M0.
"""

import time
from collections import deque
from collections.abc import Callable
from datetime import timedelta
from threading import Lock

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core import clock
from app.core.config import get_settings
from app.core.errors import DomainError

ALGORITHM = "HS256"
_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    """Băm argon2 (argon2id, tham số mặc định của argon2-cffi)."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """So khớp argon2; hash sai định dạng hoặc không khớp → False (không ném lỗi ra ngoài)."""
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _secret() -> str:
    secret = get_settings().jwt_secret
    if not secret:
        raise RuntimeError("JWT_SECRET is not set")
    return secret


def token_ttl() -> timedelta:
    return timedelta(hours=get_settings().jwt_ttl_hours)


def issue_token(user_id: int, claims: dict[str, object]) -> str:
    """Phát JWT HS256 với hạn settings.jwt_ttl_hours (mặc định 8 giờ) tính từ clock.now()."""
    issued = clock.now()
    payload: dict[str, object] = {
        **claims,
        "sub": str(user_id),
        "iat": int(issued.timestamp()),
        "exp": int((issued + token_ttl()).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, object]:
    """Giải và kiểm chữ ký + hạn JWT; sai/hết hạn → DomainError AUTH_INVALID (401)."""
    try:
        payload: dict[str, object] = jwt.decode(
            token,
            _secret(),
            algorithms=[ALGORITHM],
            options={"verify_exp": False, "verify_iat": False, "require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise DomainError("AUTH_INVALID", "Invalid or expired token.") from exc
    exp = payload.get("exp")
    if not isinstance(exp, int) or clock.now().timestamp() >= exp:
        raise DomainError("AUTH_INVALID", "Invalid or expired token.")
    return payload


class LoginRateLimiter:
    """Cửa sổ trượt: tối đa `max_attempts` lần thử đăng nhập trong `window_s` giây cho mỗi khóa (IP)."""

    def __init__(
        self, max_attempts: int = 5, window_s: float = 60.0, monotonic: Callable[[], float] = time.monotonic
    ) -> None:
        self.max_attempts = max_attempts
        self.window_s = window_s
        self._monotonic = monotonic
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def hit(self, key: str) -> None:
        """Ghi một lần thử; vượt giới hạn → DomainError 429 (không tính lần bị chặn)."""
        now = self._monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.max_attempts:
                raise DomainError(
                    "AUTH_INVALID",
                    "Too many login attempts. Try again in a minute.",
                    http_status=429,
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_rate_limiter = LoginRateLimiter()
