"""DEC-R3-07 records received from the authenticated market Source."""

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class DriverEvidence(BaseModel):
    source_ref: Text
    employee_no: Text
    verified_by: Text
    verified_at: AwareDatetime
    updated_at: AwareDatetime
    source: Literal["fleet_api", "synthetic_demo"] = "fleet_api"
    market: Text | None = None


class SourceDriverAvailability(DriverEvidence):
    work_date: date
    available_from: AwareDatetime
    available_to: AwareDatetime
    max_driving_min: Annotated[int, Field(strict=True, ge=0, le=900)]
    superseded: bool


class SourceDriverEligibility(DriverEvidence):
    vehicle_code: Text | None
    licence_class: Literal["B", "C", "CE"] | None
    verified_until: date
    revoked: bool
