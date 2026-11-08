"""Explicit SE demo receiving calendar from holidays, distinct from CFO driver/staff duty."""

from datetime import date

import holidays


def calendar_values(year: int) -> dict[str, object]:
    return {
        "id": "instance",
        "timezone": "Europe/Stockholm",
        "valid_from": date(year, 1, 1),
        "valid_to": date(year + 1, 12, 31),
        "working_days": [1, 2, 3, 4, 5],
        "holidays": sorted(
            day.isoformat() for day in holidays.country_holidays("SE", years=(year, year + 1))
        ),
    }


def demo_receiving_hours() -> dict[str, list[list[str]]]:
    return {str(day): [["07:00", "16:00"]] for day in range(1, 6)}
