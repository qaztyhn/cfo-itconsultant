"""D7 56-day verification: pure rules (no DB)."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.driver_history import verify_history
from tests.d7_evidence import STOCKHOLM, evidence, from_d7_fixture, interval

TARGET = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


def check(ev, *, allow_synthetic=True, target=TARGET):
    return verify_history(ev, target_date=target, zone=STOCKHOLM, now=NOW, allow_synthetic=allow_synthetic)


def test_complete_verified_history_is_accepted_with_separate_duty_and_driving_data() -> None:
    proof = check(evidence(5, TARGET))
    assert proof.complete and proof.reasons == () and proof.legal_verified is False  # synthetic: demo only
    assert len(proof.duty_history) == 18 and all(m == 240 for m in proof.driving_min_by_day.values())
    assert proof.driving_min_week == sum(
        m for d, m in proof.driving_min_by_day.items() if d >= date(2026, 11, 3)
    )


def test_verified_import_is_marked_legally_verified_only_for_real_sources() -> None:
    assert check(evidence(5, TARGET, source_kind="verified_import")).legal_verified is True


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"revoked": True}, "EVIDENCE_REVOKED"),
        ({"expires_at": NOW - timedelta(minutes=1)}, "EVIDENCE_EXPIRED"),
        ({"expires_at": NOW}, "EVIDENCE_EXPIRED"),
        ({"verified_by": None}, "EVIDENCE_UNVERIFIED"),
        ({"verified_by": "  "}, "EVIDENCE_UNVERIFIED"),
        ({"verified_at": None}, "EVIDENCE_UNVERIFIED"),
        ({"verified_at": NOW + timedelta(hours=1)}, "EVIDENCE_UNVERIFIED"),
        ({"source_kind": "guess"}, "EVIDENCE_UNVERIFIED"),
    ],
)
def test_revoked_expired_or_unattested_evidence_is_rejected(kwargs: dict, reason: str) -> None:
    proof = check(evidence(5, TARGET, **kwargs))
    assert not proof.complete and reason in proof.reasons


def test_no_evidence_and_synthetic_in_production_are_rejected() -> None:
    assert check(None).reasons == ("EVIDENCE_MISSING",)
    proof = check(evidence(5, TARGET), allow_synthetic=False)
    assert not proof.complete and proof.reasons == ("SYNTHETIC_NOT_ALLOWED",)


def test_a_missing_unknown_or_duplicate_day_is_incomplete_never_rest() -> None:
    dropped = check(evidence(5, TARGET, mutate=lambda d: d[:-1]))  # the newest day has no record
    assert not dropped.complete and "DAY_MISSING" in dropped.reasons
    unknown = check(
        evidence(5, TARGET, mutate=lambda d: [*d[:10], replace(d[10], status="unknown"), *d[11:]])
    )
    assert "DAY_UNKNOWN" in unknown.reasons
    dup = check(evidence(5, TARGET, mutate=lambda d: [*d, d[0]]))
    assert "DAY_DUPLICATE" in dup.reasons


def test_window_is_rolling_a_day_57_requires_new_coverage() -> None:
    ev = evidence(5, TARGET)
    assert check(ev).complete
    assert "DAY_MISSING" in check(ev, target=TARGET + timedelta(days=1)).reasons  # yesterday not covered yet


def test_off_duty_needs_a_verified_rest_window_and_cannot_hold_duty() -> None:
    no_rest = check(
        evidence(
            5, TARGET, mutate=lambda d: [replace(x, rest=None) if x.status == "off_duty" else x for x in d]
        )
    )
    assert "REST_UNPROVEN" in no_rest.reasons

    def duty_on_off_day(days):
        off = next(i for i, x in enumerate(days) if x.status == "off_duty")
        return [
            *days[:off],
            replace(days[off], duty=interval(days[off].local_date, "08:00", "16:00")),
            *days[off + 1 :],
        ]

    assert "INCONSISTENT" in check(evidence(5, TARGET, mutate=duty_on_off_day)).reasons


def test_overlapping_duties_and_driving_outside_duty_are_inconsistent() -> None:
    def overlap(days):
        idx = [i for i, x in enumerate(days) if x.status == "duty"]
        first, second = idx[0], idx[1]
        later = interval(days[second].local_date, "08:00", "16:00")
        # make the first duty run into the second one
        start = days[first].duty[0]
        return [
            *days[:first],
            replace(days[first], duty=(start, later[0] + timedelta(hours=1))),
            *days[first + 1 :],
        ]

    assert "INCONSISTENT" in check(evidence(5, TARGET, mutate=overlap)).reasons

    def outside(days):
        i = next(i for i, x in enumerate(days) if x.status == "duty")
        return [
            *days[:i],
            replace(days[i], driving=(interval(days[i].local_date, "07:00", "09:00"),)),
            *days[i + 1 :],
        ]

    assert "INCONSISTENT" in check(evidence(5, TARGET, mutate=outside)).reasons


def test_naive_timestamps_are_inconsistent() -> None:
    def naive(days):
        i = next(i for i, x in enumerate(days) if x.status == "duty")
        s, e = days[i].duty
        return [
            *days[:i],
            replace(days[i], duty=(s.replace(tzinfo=None), e.replace(tzinfo=None))),
            *days[i + 1 :],
        ]

    assert "INCONSISTENT" in check(evidence(5, TARGET, mutate=naive)).reasons


def test_d7_fixtures_provide_valid_evidence_only_where_coverage_is_actually_complete() -> None:
    target = date(2026, 11, 4)  # day after the approved fixture window 2026-09-09 … 2026-11-03
    results = {
        code: verify_history(
            from_d7_fixture(code), target_date=target, zone=STOCKHOLM, now=NOW, allow_synthetic=True
        )
        for code in (f"D{n:02d}" for n in range(1, 11))
    }
    assert (
        results["D07"].complete is False and "DAY_UNKNOWN" in results["D07"].reasons
    )  # the missing-data driver
    complete = [c for c, p in results.items() if p.complete]
    assert len(complete) == 9 and all(not results[c].legal_verified for c in complete)
    assert check(from_d7_fixture("D01"), target=target).complete is True
    # the same fixtures are NOT usable in production
    assert not verify_history(
        from_d7_fixture("D01"), target_date=target, zone=STOCKHOLM, now=NOW, allow_synthetic=False
    ).complete
