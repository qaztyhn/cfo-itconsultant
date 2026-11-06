"""Bảo mật: băm mật khẩu argon2, phát/kiểm JWT HS256 (hết hạn 8 giờ), giới hạn tần suất login.

Claims JWT: sub (user id), roles, employee_id, location_ids, market, kpi_scopes (06 mục 4).
Quá 5 lần/phút → 429 (06 mục 4).

Owner: Dev 1 (luồng A) — M0.
"""


def hash_password(plain: str) -> str:
    """Băm argon2. TODO(#M0-auth)."""
    raise NotImplementedError


def verify_password(plain: str, hashed: str) -> bool:
    """So khớp argon2. TODO(#M0-auth)."""
    raise NotImplementedError


def issue_token(user_id: int, claims: dict[str, object]) -> str:
    """Phát JWT HS256 với hạn settings.jwt_ttl_hours. TODO(#M0-auth)."""
    raise NotImplementedError


def decode_token(token: str) -> dict[str, object]:
    """Giải và kiểm hạn JWT; sai → DomainError AUTH_INVALID (401). TODO(#M0-auth)."""
    raise NotImplementedError
