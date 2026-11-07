"""Model SQLAlchemy cho schema `stg` (docs/05).

Bảng: sync_run, sync_reject, sync_checkpoint.
Không đổi tên bảng/cột (09 mục 6).
Owner: Dev 1 (luồng A) — M1.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.base import TSTZ, Base, TimestampMixin, bigint_pk

SCHEMA = {"schema": "stg"}


class SyncRun(TimestampMixin, Base):
    __tablename__ = "sync_run"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"))
    entity: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, server_default=text("'api'"))
    checkpoint_from: Mapped[datetime | None] = mapped_column(TSTZ)
    checkpoint_to: Mapped[datetime | None] = mapped_column(TSTZ)
    file_name: Mapped[str | None] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(TSTZ, server_default=text("now()"))
    finished_at: Mapped[datetime | None] = mapped_column(TSTZ)
    status: Mapped[str] = mapped_column(Text, server_default=text("'running'"))
    rows_in: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    rows_ok: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    rows_rejected: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    data_as_of: Mapped[datetime | None] = mapped_column(TSTZ)
    error: Mapped[str | None] = mapped_column(Text)


class SyncReject(TimestampMixin, Base):
    __tablename__ = "sync_reject"
    __table_args__ = SCHEMA

    id: Mapped[int] = bigint_pk()
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stg.sync_run.id"))
    external_key: Mapped[str | None] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class SyncCheckpoint(TimestampMixin, Base):
    __tablename__ = "sync_checkpoint"
    __table_args__ = SCHEMA

    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"), primary_key=True)
    entity: Mapped[str] = mapped_column(Text, primary_key=True)
    last_updated_since: Mapped[datetime] = mapped_column(TSTZ)
