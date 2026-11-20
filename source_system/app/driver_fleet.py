"""Verified fleet feeds (06 §19.6) with the Source list convention."""

from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy import select

from app.lists_read import Paging, fetch_page
from app.models import DriverAvailability, DriverEligibility


class FleetEvidence(BaseModel):
    source_ref: str
    employee_no: str
    verified_by: str
    verified_at: datetime
    updated_at: datetime
    source: str


class AvailabilityOut(FleetEvidence):
    work_date: date
    available_from: datetime
    available_to: datetime
    max_driving_min: int
    superseded: bool


class EligibilityOut(FleetEvidence):
    vehicle_code: str | None
    licence_class: str | None
    verified_until: date
    revoked: bool


class FleetEvidencePage[T: FleetEvidence](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int


async def availability(paging: Paging) -> FleetEvidencePage[AvailabilityOut]:
    model = DriverAvailability
    rows, total = await fetch_page(paging, select(model), model.updated_at, model.source_ref)
    return FleetEvidencePage[AvailabilityOut](
        items=[AvailabilityOut.model_validate(row, from_attributes=True) for row in rows],
        page=paging.page,
        page_size=paging.page_size,
        total=total,
    )


async def eligibility(paging: Paging) -> FleetEvidencePage[EligibilityOut]:
    model = DriverEligibility
    rows, total = await fetch_page(paging, select(model), model.updated_at, model.source_ref)
    return FleetEvidencePage[EligibilityOut](
        items=[EligibilityOut.model_validate(row, from_attributes=True) for row in rows],
        page=paging.page,
        page_size=paging.page_size,
        total=total,
    )
