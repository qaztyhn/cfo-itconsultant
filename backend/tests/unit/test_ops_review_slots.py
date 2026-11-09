from datetime import UTC, date, datetime

import pytest

from app.jobs.ops_review_slots import due_slots, next_slot, slots_for_day

TZ = "Europe/Stockholm"


def test_two_slots_at_07_and_13_market_local_with_dst_offsets() -> None:
    winter = slots_for_day("SE", TZ, date(2026, 11, 10))
    summer = slots_for_day("SE", TZ, date(2026, 7, 10))
    assert [s.due_at.astimezone(UTC).hour for s in winter] == [6, 12]  # UTC+1
    assert [s.due_at.astimezone(UTC).hour for s in summer] == [5, 11]  # UTC+2
    assert winter[0].key == "SE:2026-11-10:07:00"


@pytest.mark.parametrize("day", [date(2026, 3, 29), date(2026, 10, 25)])  # both DST change days
def test_dst_change_days_still_have_exactly_two_slots(day: date) -> None:
    assert len(slots_for_day("SE", TZ, day)) == 2


def test_catch_up_runs_each_slot_once_and_only_for_the_current_local_day() -> None:
    now = datetime(2026, 11, 10, 12, 30, tzinfo=UTC)  # 13:30 local
    first = due_slots("SE", TZ, now, set())
    assert [s.key for s in first] == ["SE:2026-11-10:07:00", "SE:2026-11-10:13:00"]
    assert due_slots("SE", TZ, now, {s.key for s in first}) == ()  # no double execution
    assert [s.key for s in due_slots("SE", TZ, datetime(2026, 11, 10, 6, 30, tzinfo=UTC), set())] == [
        "SE:2026-11-10:07:00"
    ]
    assert due_slots("SE", TZ, datetime(2026, 11, 10, 5, 59, tzinfo=UTC), set()) == ()  # 06:59 local


def test_next_slot_and_naive_time_rejected() -> None:
    assert next_slot("SE", TZ, datetime(2026, 11, 10, 12, 30, tzinfo=UTC)).key == "SE:2026-11-11:07:00"
    with pytest.raises(ValueError):
        due_slots("SE", TZ, datetime(2026, 11, 10, 12, 30), set())  # noqa: DTZ001
