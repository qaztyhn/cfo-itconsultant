"""Declarative Base và mixin created_at/updated_at (05 mục 1).

- Schema do migration Alembic tạo (09 mục 6); model chỉ ánh xạ, KHÔNG dùng `metadata.create_all`.
- Cột chung theo ASM-001: `updated_at` do trigger `trg_set_updated_at` (0007) cập nhật → `server_onupdate`
  là FetchedValue để ORM đọc lại giá trị DB sau UPDATE.
- Ràng buộc UNIQUE/CHECK/EXCLUDE và chỉ mục nằm ở migration; model chỉ khai báo PK, FK, kiểu, nullable
  (test drift `tests/integration/test_models_drift.py`).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, FetchedValue, Identity, SmallInteger, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TSTZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    """Base cho mọi model CFO."""


class TimestampMixin:
    """created_at / updated_at timestamptz NOT NULL DEFAULT now() (05 mục 1, ASM-001)."""

    created_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        TSTZ, server_default=text("now()"), server_onupdate=FetchedValue()
    )


def bigint_pk() -> Mapped[int]:
    """bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY (05 mục 1)."""
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def smallint_pk() -> Mapped[int]:
    """smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY (ref.market, ref.handling_group)."""
    return mapped_column(SmallInteger, Identity(always=True), primary_key=True)
