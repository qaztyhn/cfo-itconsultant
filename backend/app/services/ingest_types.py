"""Internal T07 contracts; no API/DDL or new business rules."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.order_wire import SourceOrder
from app.domain.models.ops import CustomerOrder

type ReplanSource = Callable[[AsyncSession, CustomerOrder, SourceOrder], Awaitable[int | None]]
type SourceRisk = Callable[[AsyncSession, int, str], Awaitable[None]]


class RowRejected(ValueError):
    """Static safe staging code. Never attach raw input/driver/customer data."""


class BatchRejected(ValueError):
    """A complete stock batch must fail atomically; static reason code only."""


@dataclass(frozen=True)
class IngestResult:
    run_id: int
    status: str
    rows_in: int
    rows_ok: int
    rows_rejected: int


@dataclass(frozen=True)
class RowOutcome:
    reject_code: str | None = None
    changed: bool = False


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Ingestion time must be timezone-aware")
    return value
