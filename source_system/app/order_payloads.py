"""Approved D1 source write shapes. Empty lines/contact/date details may remain incomplete in DRAFT."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    phone: str | None = None
    email: str | None = None


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_no: int = Field(gt=0, strict=True)
    sku: str = Field(min_length=1)
    qty: Decimal = Field(gt=0, decimal_places=3, allow_inf_nan=False)
    unit_price: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]{2}$")]


class OrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str = Field(min_length=1)
    address_id: str = Field(min_length=1)
    store_code: str = Field(min_length=1)
    date_mode: Literal["exact", "range", "latest"]
    sales_code: str | None = None
    contact: ContactIn | None = None
    date_from: date | None = None
    date_to: date | None = None
    window_start: Annotated[str | None, Field(pattern=r"^[0-2][0-9]:[0-5][0-9]$")] = None
    window_end: Annotated[str | None, Field(pattern=r"^[0-2][0-9]:[0-5][0-9]$")] = None
    receiving_restrictions: str | None = None
    special_requirements: str | None = None
    lines: list[LineIn] = Field(default_factory=list)


class OrderEditIn(OrderIn):
    expected_version: int = Field(ge=1, strict=True)
    refresh_address: bool = False


class CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, strict=True)
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    reason_text: str | None = Field(default=None, max_length=1000)
