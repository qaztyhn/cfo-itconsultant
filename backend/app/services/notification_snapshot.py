"""Immutable-in-service notification snapshot stored in the existing eta_window JSONB.

N1-N3: a DELAY window is an approved, explicit interval (never one forecast
instant). Persist only typed public variables, the template version and the
approver/time. No arbitrary message bodies, names, GPS, driver or CS notes.

Existing schema does not guarantee column-level immutability: applications
write this envelope once and the outbox refuses tampered/unsupported versions.
A database-level immutability constraint needs a separately reviewed migration.
"""

import hashlib
import json
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.services.notification_templates import (
    TEMPLATE_VERSION,
    EtaWindow,
    MessageVariables,
    RenderedMessage,
    Template,
    render_message,
)


class ApprovedEta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: AwareDatetime
    end: AwareDatetime
    version: int = Field(gt=0)
    approved_by_employee_id: int = Field(gt=0)
    effective_at: AwareDatetime

    @model_validator(mode="after")
    def valid_interval(self) -> "ApprovedEta":
        if self.start >= self.end or self.effective_at > self.end:
            raise ValueError("Approved customer-facing ETA window is invalid")
        return self

    def window(self) -> EtaWindow:
        return EtaWindow(start=self.start, end=self.end)


class NotificationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: Template
    template_version: str
    locale: str
    timezone: str
    variables: MessageVariables
    approved_eta: ApprovedEta | None = None
    reason_code: Literal["PREDICTED_LATE"] | None = None

    @model_validator(mode="after")
    def validate_delay(self) -> "NotificationSnapshot":
        if self.template == "DELAY":
            if self.approved_eta is None or self.variables.eta_window != self.approved_eta.window():
                raise ValueError("DELAY requires an explicitly approved and versioned ETA window")
            if self.reason_code != "PREDICTED_LATE":
                raise ValueError("Only the reviewed PREDICTED_LATE reason is supported")
        elif self.approved_eta is not None or self.reason_code is not None:
            raise ValueError("Status notifications cannot carry DELAY approval metadata")
        return self


class StoredEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: NotificationSnapshot
    fingerprint: str
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None


def render_snapshot(snapshot: NotificationSnapshot, *, channel: str) -> RenderedMessage:
    if snapshot.template_version != TEMPLATE_VERSION:
        raise ValueError("Template version is no longer available")
    return render_message(
        snapshot.template,
        snapshot.variables,
        locale=snapshot.locale,
        timezone=snapshot.timezone,
        channel=channel,
    )


def _fingerprint(snapshot: NotificationSnapshot, *, channel: str, rendered: RenderedMessage) -> str:
    payload = {
        "snapshot": snapshot.model_dump(mode="json", exclude_none=True),
        "channel": channel,
        "subject": rendered.subject,
        "body": rendered.body,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def freeze_snapshot(
    snapshot: NotificationSnapshot, *, channel: str
) -> tuple[dict[str, object], RenderedMessage]:
    """Atomic immutable-by-convention variable/version envelope for an outbox row."""
    rendered = render_snapshot(snapshot, channel=channel)
    data: dict[str, object] = {
        "snapshot": snapshot.model_dump(mode="json", exclude_none=True),
        "fingerprint": _fingerprint(snapshot, channel=channel, rendered=rendered),
    }
    if snapshot.variables.eta_window is not None:
        data["start"] = snapshot.variables.eta_window.start.isoformat()
        data["end"] = snapshot.variables.eta_window.end.isoformat()
    return data, rendered


def read_snapshot(
    raw: dict[str, object] | None,
    *,
    channel: str,
    template: str,
    subject: str | None,
    body: str,
) -> RenderedMessage | None:
    """None for legacy rows; fail closed for malformed or modified new snapshots."""
    if raw is None or "snapshot" not in raw:
        return None
    stored = StoredEnvelope.model_validate(raw)
    snapshot = stored.snapshot
    rendered = render_snapshot(snapshot, channel=channel)
    if (
        snapshot.template != template
        or stored.fingerprint != _fingerprint(snapshot, channel=channel, rendered=rendered)
        or (subject or "") != rendered.subject
        or body != rendered.body
    ):
        raise ValueError("Notification snapshot integrity check failed")
    if snapshot.variables.eta_window is None:
        if stored.start is not None or stored.end is not None:
            raise ValueError("Unexpected delivery window")
    elif (
        stored.start != snapshot.variables.eta_window.start
        or stored.end != snapshot.variables.eta_window.end
    ):
        raise ValueError("Delivery window does not match immutable snapshot")
    return rendered


def snapshot_version(raw: dict[str, object] | None) -> int | None:
    """Extract approved DELAY version, never infer from a forecast or a timestamp."""
    if not raw or "snapshot" not in raw:
        return None
    parsed = StoredEnvelope.model_validate(raw)
    return parsed.snapshot.approved_eta.version if parsed.snapshot.approved_eta else None


def approved_window_from_snapshot(raw: dict[str, object] | None) -> ApprovedEta | None:
    if not raw or "snapshot" not in raw:
        return None
    parsed = StoredEnvelope.model_validate(raw)
    return parsed.snapshot.approved_eta
