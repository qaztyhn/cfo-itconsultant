"""D1-B/D1-D explicit source calendars. No always-open or inferred holiday fallback."""

from datetime import date, time
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CalendarConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    timezone: str
    valid_from: date
    valid_to: date
    working_days: set[Annotated[int, Field(ge=1, le=7)]] = Field(min_length=1)
    holidays: set[date]

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except KeyError:
            raise ValueError("Unknown calendar timezone") from None
        return value

    @model_validator(mode="after")
    def ordered(self) -> "CalendarConfig":
        if self.valid_from > self.valid_to:
            raise ValueError("Calendar coverage must be ordered")
        return self


class ReceivingHours(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Explicit absent weekdays are closed; a missing whole calendar remains unknown.
    days: dict[str, list[tuple[str, str]]]

    @field_validator("days")
    @classmethod
    def valid_slots(cls, value: dict[str, list[tuple[str, str]]]) -> dict[str, list[tuple[str, str]]]:
        for weekday, slots in value.items():
            if weekday not in {str(day) for day in range(1, 8)}:
                raise ValueError("Invalid receiving weekday")
            for start, end in slots:
                if len(start) != 5 or len(end) != 5:
                    raise ValueError("Receiving times must be HH:MM")
                begins, ends = time.fromisoformat(start), time.fromisoformat(end)
                if begins.tzinfo or ends.tzinfo or begins >= ends:
                    raise ValueError("Receiving slots must be ordered local times")
        return value


def day_error(
    calendar: CalendarConfig | None,
    hours: ReceivingHours | None,
    day: date,
    start: time | None = None,
    end: time | None = None,
) -> str | None:
    if calendar is None or hours is None or not calendar.valid_from <= day <= calendar.valid_to:
        return "receiving_calendar_missing"
    if (start is not None and start.tzinfo is not None) or (end is not None and end.tzinfo is not None):
        return "invalid_receiving_window"
    if (start is None) != (end is None) or (start is not None and end is not None and start >= end):
        return "invalid_receiving_window"
    if day.isoweekday() not in calendar.working_days or day in calendar.holidays:
        return "outside_receiving_hours"
    slots = hours.days.get(str(day.isoweekday()), [])
    for begins, ends in slots:
        if start is None or (
            time.fromisoformat(begins) <= start and end is not None and end <= time.fromisoformat(ends)
        ):
            return None
    return "outside_receiving_hours"
