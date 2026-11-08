"""Approved D1 source order/cancellation decoding, isolated from persistence and routing."""

from datetime import date, time
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.adapters.base import CancellationDTO, OrderDTO, OrderLineDTO


class Contact(BaseModel):
    name: str = Field(min_length=1)
    phone: str | None = None
    email: str | None = None


class Line(BaseModel):
    line_no: int = Field(gt=0, strict=True)
    sku: str = Field(min_length=1)
    qty: Decimal = Field(gt=0, decimal_places=3, allow_inf_nan=False)
    unit_price: Decimal = Field(ge=0, decimal_places=2, allow_inf_nan=False)


class SourceOrder(BaseModel):
    id: str = Field(min_length=1)
    version: int = Field(ge=1, strict=True)
    updated_at: AwareDatetime
    status: Literal["SUBMITTED_FOR_PLANNING"]
    customer_id: str = Field(min_length=1)
    address_id: str = Field(min_length=1)
    address: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    contact: Contact
    date_mode: Literal["exact", "range", "latest"]
    date_from: date | None
    date_to: date | None
    window_start: str | None = None
    window_end: str | None = None
    receiving_restrictions: str | None = None
    special_requirements: str | None = None
    sales_code: str | None = None
    store_code: str = Field(min_length=1)
    lines: list[Line] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent(self) -> "SourceOrder":
        if self.date_mode == "exact":
            valid = self.date_from is not None and self.date_to is None
        elif self.date_mode == "latest":
            valid = self.date_from is None and self.date_to is not None
        else:
            valid = self.date_from is not None and self.date_to is not None and self.date_from <= self.date_to
        if not valid or len({line.line_no for line in self.lines}) != len(self.lines):
            raise ValueError("Invalid source order date/line identity")
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("Source receiving window is incomplete")
        if self.window_start is not None and self.window_end is not None:
            try:
                start, end = time.fromisoformat(self.window_start), time.fromisoformat(self.window_end)
            except ValueError:
                raise ValueError("Source receiving window is invalid") from None
            if (
                len(self.window_start) != 5
                or len(self.window_end) != 5
                or start.tzinfo
                or end.tzinfo
                or start >= end
            ):
                raise ValueError("Source receiving window is invalid")
        if not self.contact.name.strip() or not any(
            (v or "").strip() for v in (self.contact.email, self.contact.phone)
        ):
            raise ValueError("Source contact is incomplete")
        return self

    def dto(self) -> OrderDTO:
        end = self.date_to or self.date_from
        assert end is not None  # coherent() validates the approved source date-mode shapes.
        return OrderDTO(
            self.id,
            self.version,
            self.updated_at,
            self.status,
            self.customer_id,
            self.address,
            self.lat,
            self.lon,
            {"name": self.contact.name, "phone": self.contact.phone, "email": self.contact.email},
            self.date_mode,
            self.date_from,
            end,
            self.window_start,
            self.window_end,
            self.receiving_restrictions,
            self.special_requirements,
            self.sales_code,
            self.store_code,
            tuple(
                OrderLineDTO(line.line_no, line.sku, line.qty, line.unit_price)
                for line in sorted(self.lines, key=lambda line: line.line_no)
            ),
            address_ref=self.address_id,
        )


class Reason(BaseModel):
    reason_code: str
    reason_text: str | None = None


class SourceCancellation(BaseModel):
    id: str = Field(min_length=1)
    version: int = Field(ge=1, strict=True)
    updated_at: AwareDatetime
    status: Literal["CANCELLED"]
    cancel_reason: Reason | None = None
    cancelled_at: AwareDatetime | None = None

    def dto(self) -> CancellationDTO:
        reason = (
            None
            if self.cancel_reason is None
            else {
                "reason_code": self.cancel_reason.reason_code,
                "reason_text": self.cancel_reason.reason_text,
            }
        )
        return CancellationDTO(self.id, self.version, self.updated_at, reason, self.cancelled_at)
