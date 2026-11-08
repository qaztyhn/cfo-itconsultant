"""T18 transfer REST API (06 §7): thin request validation; service owns guards and writes."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Header, Query
from pydantic import BaseModel, Field

from app.api.v1.common import PageNo, PageSize
from app.deps import AuthUser, DbSession
from app.services import transfer_service

router = APIRouter(tags=["transfers"])

TransferStatus = Literal["suggested", "approved", "source_confirmed", "received", "cancelled"]
IdempotencyHeader = Annotated[UUID, Header(alias="Idempotency-Key")]


class TransferLineIn(BaseModel):
    global_product_id: int = Field(gt=0)
    qty: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class TransferApproveIn(BaseModel):
    from_warehouse_id: int = Field(gt=0)
    to_warehouse_id: int = Field(gt=0)
    lines: list[TransferLineIn] = Field(min_length=1)
    lead_days: int = Field(ge=1, le=32767)


class TransferCancelIn(BaseModel):
    reason_text: str = Field(min_length=1)


@router.post("/orders/{order_id}/transfers")
async def approve_transfer(
    order_id: int,
    user: AuthUser,
    db: DbSession,
    idempotency_key: IdempotencyHeader,
    body: Annotated[TransferApproveIn, Body()],
) -> dict[str, object]:
    return await transfer_service.approve(
        db, user, order_id, body.model_dump(mode="json"), str(idempotency_key)
    )


@router.get("/transfers")
async def list_transfers(
    user: AuthUser,
    db: DbSession,
    status: TransferStatus | None = None,
    warehouse_id: Annotated[int | None, Query(gt=0)] = None,
    page: PageNo = 1,
    page_size: PageSize = 50,
) -> dict[str, object]:
    return await transfer_service.list_transfers(
        db, user, status=status, warehouse_id=warehouse_id, page=page, page_size=page_size
    )


@router.post("/transfers/{transfer_id}/confirm-source")
async def confirm_source(
    transfer_id: int, user: AuthUser, db: DbSession, idempotency_key: IdempotencyHeader
) -> dict[str, object]:
    return await transfer_service.confirm_source(db, user, transfer_id, str(idempotency_key))


@router.post("/transfers/{transfer_id}/receive")
async def receive_transfer(
    transfer_id: int, user: AuthUser, db: DbSession, idempotency_key: IdempotencyHeader
) -> dict[str, object]:
    return await transfer_service.receive(db, user, transfer_id, str(idempotency_key))


@router.post("/transfers/{transfer_id}/cancel")
async def cancel_transfer(
    transfer_id: int,
    user: AuthUser,
    db: DbSession,
    idempotency_key: IdempotencyHeader,
    body: Annotated[TransferCancelIn, Body()],
) -> dict[str, object]:
    return await transfer_service.cancel(db, user, transfer_id, body.reason_text, str(idempotency_key))
