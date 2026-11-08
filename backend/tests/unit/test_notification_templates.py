from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.services.notification_templates import EtaWindow, MessageVariables, render_message

WINDOW = {"start": "2026-11-05T09:00:00Z", "end": "2026-11-05T11:00:00Z"}


@pytest.mark.parametrize("template", ["CONFIRMED", "DISPATCHED", "DELIVERED", "FAILED", "DELAY"])
def test_US_NOT_01_AC1_D4_templates_only_render_public_reference_and_validated_eta(template: str) -> None:
    from typing import cast

    from app.services.notification_templates import Template

    variables = MessageVariables.model_validate({"public_order_ref": "SE-2026-000123", "eta_window": WINDOW})
    rendered = render_message(
        cast(Template, template), variables, locale="en-SE", timezone="Europe/Stockholm"
    )
    assert rendered.version == "1"
    assert rendered.subject == "Order SE-2026-000123"
    assert "2026-11-05T10:00+01:00" in rendered.body
    assert "2026-11-05T12:00+01:00" in rendered.body
    assert (
        render_message(cast(Template, template), variables, locale="en-SE", timezone="Europe/Stockholm")
        == rendered
    )


@pytest.mark.parametrize("field", ["body", "subject", "driver_name", "lat", "lon", "notes", "reason_text"])
def test_US_NOT_01_AC2_D4_unknown_variables_and_free_text_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        MessageVariables.model_validate({"public_order_ref": "SE-123", field: "private-text"})


@pytest.mark.parametrize("reference", ["<script>", "SE-123\r\nBcc:private@example.test", "Contact Name", ""])
def test_US_NOT_01_AC2_D4_reference_cannot_inject_markup_or_private_text(reference: str) -> None:
    with pytest.raises(ValidationError):
        MessageVariables(public_order_ref=reference)


def test_US_NOT_02_AC1_D4_delay_requires_ordered_aware_eta_and_supported_locale() -> None:
    variables = MessageVariables(public_order_ref="SE-123")
    with pytest.raises(ValueError):
        render_message("DELAY", variables, locale="en", timezone="UTC")
    with pytest.raises(ValueError):
        render_message("CONFIRMED", variables, locale="unknown", timezone="UTC")
    for window in (
        {"start": WINDOW["end"], "end": WINDOW["start"]},
        {"start": "2026-11-05T09:00:00", "end": WINDOW["end"]},
        {**WINDOW, "notes": "private"},
    ):
        with pytest.raises(ValidationError):
            EtaWindow.model_validate(window)
    assert EtaWindow.model_validate(WINDOW).start == datetime(2026, 11, 5, 9, tzinfo=UTC)
