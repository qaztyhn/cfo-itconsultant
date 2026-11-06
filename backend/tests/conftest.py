"""Fixture dùng chung. Test không phụ thuộc giờ thật: đặt clock cố định ở APP_NOW demo (09 mục 11)."""

import os
from collections.abc import Iterator

# Trước mọi import app.*: không ghi file log, không khởi động scheduler khi test (main.py).
os.environ.setdefault("APP_ENV", "test")
from datetime import datetime

import pytest

from app.core import clock

DEMO_NOW = datetime.fromisoformat("2026-11-04T10:05:00+01:00")


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[datetime]:
    """Cố định đồng hồ ở thời điểm demo cho mọi test."""
    clock.set_now(DEMO_NOW)
    yield DEMO_NOW
    clock.set_now(None)
