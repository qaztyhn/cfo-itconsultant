"""core.security: argon2, JWT HS256 theo clock, giới hạn tần suất login (không cần DB)."""

import secrets
from collections.abc import Iterator
from datetime import timedelta

import jwt
import pytest

from app.core import clock
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.security import (
    LoginRateLimiter,
    decode_token,
    hash_password,
    issue_token,
    verify_password,
)


@pytest.fixture
def jwt_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    secret = secrets.token_urlsafe(32)  # sinh lúc chạy, không ghi bí mật vào mã (09 bất biến 25)
    monkeypatch.setenv("JWT_SECRET", secret)
    get_settings.cache_clear()
    yield secret
    get_settings.cache_clear()


def test_argon2_hash_and_verify() -> None:
    password = secrets.token_urlsafe(12)
    hashed = hash_password(password)
    assert hashed.startswith("$argon2id$") and password not in hashed
    assert verify_password(password, hashed)
    assert not verify_password(password + "x", hashed)
    assert not verify_password(password, "not-an-argon2-hash")


def test_token_round_trip_has_claims_and_8h_expiry(jwt_secret: str) -> None:
    token = issue_token(12, {"roles": ["dispatcher"], "location_ids": [7], "kpi_scopes": ["ops"]})
    payload = decode_token(token)
    assert payload["sub"] == "12" and payload["roles"] == ["dispatcher"] and payload["location_ids"] == [7]
    assert payload["exp"] - payload["iat"] == 8 * 3600  # type: ignore[operator]


def test_token_expiry_follows_app_clock(jwt_secret: str, frozen_clock: object) -> None:
    token = issue_token(1, {})
    clock.set_now(clock.now() + timedelta(hours=8) - timedelta(seconds=1))
    decode_token(token)
    clock.set_now(clock.now() + timedelta(seconds=1))
    with pytest.raises(DomainError) as caught:
        decode_token(token)
    assert caught.value.code == "AUTH_INVALID" and caught.value.http_status == 401


def test_token_with_wrong_signature_or_algorithm_rejected(jwt_secret: str) -> None:
    payload = {"sub": "1", "exp": int((clock.now() + timedelta(hours=1)).timestamp())}
    forged = jwt.encode(payload, secrets.token_urlsafe(32), algorithm="HS256")
    unsigned = jwt.encode(payload, None, algorithm="none")
    for token in (forged, unsigned, "garbage"):
        with pytest.raises(DomainError) as caught:
            decode_token(token)
        assert caught.value.code == "AUTH_INVALID"


def test_missing_jwt_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            issue_token(1, {})
    finally:
        get_settings.cache_clear()


def test_login_rate_limiter_sliding_window() -> None:
    now = [100.0]
    limiter = LoginRateLimiter(max_attempts=5, window_s=60, monotonic=lambda: now[0])
    for _ in range(5):
        limiter.hit("1.2.3.4")
    with pytest.raises(DomainError) as caught:
        limiter.hit("1.2.3.4")
    assert caught.value.http_status == 429
    limiter.hit("5.6.7.8")  # khóa khác không bị ảnh hưởng
    now[0] += 60
    limiter.hit("1.2.3.4")  # hết cửa sổ 1 phút
