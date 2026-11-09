"""N1-N5 immutable-by-convention typed snapshot and safe server rendering."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.services.notification_snapshot import (
    ApprovedEta,
    NotificationSnapshot,
    freeze_snapshot,
    read_snapshot,
)
from app.services.notification_templates import EtaWindow, MessageVariables

START = datetime(2026, 11, 10, 9, tzinfo=UTC)
END = datetime(2026, 11, 10, 11, tzinfo=UTC)
APPROVED = datetime(2026, 11, 9, 9, tzinfo=UTC)


def _approved() -> ApprovedEta:
    return ApprovedEta(
        start=START,
        end=END,
        version=3,
        approved_by_employee_id=12,
        effective_at=APPROVED,
    )


def test_US_NOT_02_AC1_snapshot_preserves_approver_version_and_window() -> None:
    window = EtaWindow(start=START, end=END)
    frozen, message = freeze_snapshot(
        NotificationSnapshot(
            template="DELAY",
            template_version="1",
            locale="en",
            timezone="Europe/Stockholm",
            variables=MessageVariables(public_order_ref="ZZ-000123", eta_window=window),
            approved_eta=_approved(),
            reason_code="PREDICTED_LATE",
        ),
        channel="email",
    )
    assert frozen["snapshot"]["template_version"] == "1"
    assert frozen["snapshot"]["approved_eta"]["version"] == 3
    assert frozen["snapshot"]["approved_eta"]["approved_by_employee_id"] == 12
    assert (
        read_snapshot(frozen, channel="email", template="DELAY", subject=message.subject, body=message.body)
        == message
    )
    assert "GPS" not in message.body and "driver" not in message.body.lower()


def test_US_NOT_01_AC2_free_text_and_sensitive_snapshot_fields_are_rejected() -> None:
    good = {
        "template": "DELAY",
        "template_version": "1",
        "locale": "en",
        "timezone": "UTC",
        "variables": {
            "public_order_ref": "ZZ-000123",
            "eta_window": {"start": START, "end": END},
        },
        "approved_eta": _approved(),
        "reason_code": "PREDICTED_LATE",
    }
    for key, value in (
        ("body", "customer GPS"),
        ("driver_name", "private"),
        ("gps", {"lat": 40}),
        ("reason_code", "arbitrary free text"),
    ):
        with pytest.raises((ValueError, ValidationError)):
            NotificationSnapshot.model_validate({**good, key: value})


def test_US_NOT_03_AC4_mutated_snapshot_fails_closed() -> None:
    envelope, rendered = freeze_snapshot(
        NotificationSnapshot(
            template="CONFIRMED",
            template_version="1",
            locale="en",
            timezone="UTC",
            variables=MessageVariables(public_order_ref="ZZ-000123"),
        ),
        channel="email",
    )
    assert (
        read_snapshot(
            envelope,
            channel="email",
            template="CONFIRMED",
            subject=rendered.subject,
            body=rendered.body,
        )
        == rendered
    )
    with pytest.raises(ValueError, match="integrity"):
        read_snapshot(
            envelope,
            channel="email",
            template="CONFIRMED",
            subject=rendered.subject,
            body="free-text GPS injected",
        )
    envelope["snapshot"]["template_version"] = "999"
    with pytest.raises(ValueError, match="version"):
        read_snapshot(
            envelope,
            channel="email",
            template="CONFIRMED",
            subject=rendered.subject,
            body=rendered.body,
        )


def test_US_NOT_02_AC1_forecast_instant_is_not_an_eta_window() -> None:
    with pytest.raises(ValueError):
        NotificationSnapshot(
            template="DELAY",
            template_version="1",
            locale="en",
            timezone="UTC",
            variables=MessageVariables(public_order_ref="ZZ-000123"),
            approved_eta=_approved(),
            reason_code="PREDICTED_LATE",
        )
