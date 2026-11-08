from datetime import date, time

import pytest
from pydantic import ValidationError

from app.receiving import CalendarConfig, ReceivingHours, day_error
from seed.se.receiving import calendar_values, demo_receiving_hours


def calendar() -> CalendarConfig:
    values = calendar_values(2026)
    values.pop("id")
    return CalendarConfig.model_validate(values)


def test_US_SRC_03_AC1_receiving_is_explicit_and_closed_on_holidays_weekends() -> None:
    config, hours = calendar(), ReceivingHours(days=demo_receiving_hours())
    assert "2026-12-25" in {day.isoformat() for day in config.holidays}
    assert day_error(config, hours, date(2026, 11, 4), time(7), time(16)) is None
    assert day_error(config, hours, date(2026, 11, 4), time(6), time(8)) == "outside_receiving_hours"
    assert day_error(config, hours, date(2026, 11, 7)) == "outside_receiving_hours"
    assert day_error(config, hours, date(2026, 12, 25)) == "outside_receiving_hours"


def test_US_SRC_03_AC1_missing_or_uncovered_receiving_data_never_means_always_open() -> None:
    config, hours = calendar(), ReceivingHours(days=demo_receiving_hours())
    day = date(2026, 11, 4)
    assert day_error(None, hours, day) == "receiving_calendar_missing"
    assert day_error(config, None, day) == "receiving_calendar_missing"
    assert day_error(config, hours, date(2028, 1, 1)) == "receiving_calendar_missing"
    assert day_error(config, ReceivingHours(days={}), day) == "outside_receiving_hours"
    assert day_error(config, hours, day, time(9), None) == "invalid_receiving_window"


@pytest.mark.parametrize(
    "slots", [{"0": []}, {"1": [["16:00", "07:00"]]}, {"1": [["07:00", "07:00"]]}, {"1": [["7:00", "16:00"]]}]
)
def test_US_SRC_03_AC1_invalid_receiving_configuration_is_rejected(slots: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReceivingHours.model_validate({"days": slots})
