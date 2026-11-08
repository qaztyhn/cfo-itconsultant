from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.jobs.retention_policy import (
    POLICY_VERSION,
    RULES,
    ReviewInput,
    ReviewRecord,
    assess,
    review_date,
    summarize,
)

NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)


def record(category: str = "customer_contact", **extra: object) -> ReviewRecord:
    return ReviewRecord.model_validate(
        {
            "category": category,
            "anchor": "2026-01-01T00:00:00Z",
            "timezone": "UTC",
            "legal_hold": False,
            "other_valid_purpose": False,
            "regulated": False,
            "terminal": True,
            **extra,
        }
    )


@pytest.mark.parametrize("field", ["legal_hold", "other_valid_purpose", "regulated", "terminal"])
def test_D5_unknown_hold_shared_purpose_or_workflow_never_authorizes_candidate(field: str) -> None:
    assert assess(record(**{field: None}), now=NOW).startswith("blocked_")


def test_D5_operational_closure_not_failed_or_updated_timestamp() -> None:
    assert assess(record("operational_order", anchor=None), now=NOW) == "blocked_missing_anchor"
    assert assess(record("operational_order", terminal=False), now=NOW).startswith("blocked_")
    assert assess(record("customer_contact"), now=NOW) == "candidate_for_privacy_review"
    assert assess(record("operational_order"), now=NOW) == "retain"


def test_D5_months_are_calendar_months_and_accounting_uses_actual_fiscal_year() -> None:
    assert review_date(date(2024, 2, 29), RULES["shift_attendance"]) == date(2026, 2, 28)
    assert review_date(date(2026, 1, 31), replace(RULES["shift_attendance"], amount=1)) == date(2026, 2, 28)
    assert review_date(date(2026, 6, 30), RULES["accounting"]) == date(2034, 1, 1)


def test_D5_local_calendar_cutoff_is_inclusive() -> None:
    entry = record(anchor="2026-08-10T00:30:00+02:00", timezone="Europe/Stockholm")
    assert assess(entry, now=datetime(2026, 11, 7, 23, tzinfo=UTC)) == "candidate_for_privacy_review"
    assert assess(entry, now=datetime(2026, 11, 7, 22, 59, tzinfo=UTC)) == "retain"


@pytest.mark.parametrize(
    "category,outcome",
    [
        ("immutable_audit", "immutable_review_only"),
        ("tachograph", "statutory_review_only"),
        ("driver_work_time", "statutory_review_only"),
        ("accounting", "statutory_review_only"),
    ],
)
def test_D5_statutory_minimum_and_immutable_review_are_never_deletion_eligibility(
    category: str, outcome: str
) -> None:
    assert assess(record(category, anchor="2000-01-01T00:00:00Z"), now=NOW) == outcome


def test_D3_gps_workflow_overrides_a_day_count_and_duty_history_is_separate() -> None:
    assert assess(record("raw_gps", anchor=None), now=NOW) == "gps_cleanup_required"
    assert assess(record("raw_gps", terminal=False), now=NOW) == "active_gps_or_unknown_workflow"
    assert RULES["driver_work_time"].unit == "months"


def test_D5_summary_contains_counts_only_and_has_no_deletion_switch() -> None:
    data = ReviewInput(policy_version=POLICY_VERSION, synthetic_only=True, items=[record(), record()])
    result = summarize(data, now=NOW)
    assert result["counts"] == {"customer_contact": {"candidate_for_privacy_review": 2}}
    assert result["deletion_enabled"] is False
    for payload in ({"synthetic_only": False}, {"execute": True}, {"customer_name": "private"}):
        with pytest.raises(ValidationError):
            ReviewInput.model_validate(
                {"policy_version": POLICY_VERSION, "synthetic_only": True, "items": [], **payload}
            )
