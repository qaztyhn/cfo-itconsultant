"""Durable WMS reservation saga ledger; no production adapter is enabled."""

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.models.base import Base, TimestampMixin, bigint_pk


class WmsReservationIntent(TimestampMixin, Base):
    __tablename__ = "wms_reservation_intent"
    __table_args__ = {"schema": "ops"}

    id: Mapped[int] = bigint_pk()
    market_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("ref.market.id"))
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ops.customer_order.id"))
    plan_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("plan.fulfilment_plan.id"))
    order_version: Mapped[int] = mapped_column(Integer)
    source_version: Mapped[int] = mapped_column(Integer)
    request_key: Mapped[str] = mapped_column(Text)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    request_digest: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    reservation_id: Mapped[str | None] = mapped_column(Text)
    ack_revision: Mapped[str | None] = mapped_column(Text)
    ack_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reflected_in_batch_id: Mapped[int | None] = mapped_column(BigInteger)
    refreshed_batch_id: Mapped[int | None] = mapped_column(BigInteger)
    stock_write_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ops.stock_write_run.id"))
    verified_batch_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    verified_batch_sha256: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean)
