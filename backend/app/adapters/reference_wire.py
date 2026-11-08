"""D1 reference feed decoding shared by read-only transports; no country-specific assumptions."""

from datetime import date, time
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class SourceCustomer(BaseModel):
    id: str = Field(min_length=1)
    type: str
    name: str
    email: str | None
    phone: str | None
    updated_at: AwareDatetime


class SourceProduct(BaseModel):
    sku: str = Field(min_length=1)
    name: str
    category: str | None
    gtin: str | None
    sale_unit: str
    units_to_base: Decimal = Field(gt=0, allow_inf_nan=False)
    unit_price: Decimal = Field(ge=0, allow_inf_nan=False)
    weight_kg: Decimal | None = Field(ge=0, allow_inf_nan=False)
    volume_m3: Decimal | None = Field(ge=0, allow_inf_nan=False)
    updated_at: AwareDatetime


class SourceAddress(BaseModel):
    id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    address: str
    lat: float | None = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float | None = Field(ge=-180, le=180, allow_inf_nan=False)
    receiving_hours: dict[str, list[tuple[str, str]]] | None = None
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def slots(self) -> "SourceAddress":
        for weekday, slots in (self.receiving_hours or {}).items():
            if weekday not in {str(day) for day in range(1, 8)}:
                raise ValueError("Invalid receiving weekday")
            for begins, ends in slots:
                first, last = time.fromisoformat(begins), time.fromisoformat(ends)
                if len(begins) != 5 or len(ends) != 5 or first.tzinfo or last.tzinfo or first >= last:
                    raise ValueError("Invalid receiving slot")
        return self


class SourceInbound(BaseModel):
    inbound_ref: str = Field(min_length=1)
    warehouse_code: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    qty: Decimal = Field(ge=0, allow_inf_nan=False)
    eta_date: date
    confirmed: bool = Field(strict=True)
    received: bool = Field(strict=True)
    updated_at: AwareDatetime


class SourceFleet(BaseModel):
    vehicle_code: str = Field(min_length=1)
    start: AwareDatetime = Field(alias="from")
    end: AwareDatetime = Field(alias="to")
    kind: str
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def ordered(self) -> "SourceFleet":
        if self.start >= self.end:
            raise ValueError("Invalid fleet interval")
        return self
