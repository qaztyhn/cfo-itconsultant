"""T27 driver-step 8 evidence rules; no PII or raw coordinates in reports."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping


class EvidenceMismatch(ValueError):
    """A successful HTTP status is not sufficient without matching identifiers and DB."""


def aware(value: object) -> datetime:
    if not isinstance(value, str):
        raise EvidenceMismatch("Missing ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceMismatch("Invalid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceMismatch("Timestamp has no timezone")
    return parsed


def verify_event_request(
    request: Mapping[str, object],
    *,
    event_type: str,
    trip_id: int,
    server_now: str,
    not_before: str,
) -> str:
    """Inspect real browser POST body without exporting position or recipient data."""
    if request.get("event_type") != event_type:
        raise EvidenceMismatch("Driver event type does not match clicked action")
    payload = request.get("payload")
    if not isinstance(payload, dict) or payload.get("trip_id") != trip_id:
        raise EvidenceMismatch("Driver event references a different trip")
    occurred = aware(request.get("occurred_at"))
    if not aware(not_before) <= occurred <= aware(server_now):
        raise EvidenceMismatch("Event occurred_at outside dispatch/server clock")
    if event_type == "DELIVERED":
        if not isinstance(payload.get("recipient_name"), str) or not payload["recipient_name"].strip():
            raise EvidenceMismatch("Delivery request lacks demo recipient")
        verify_position_request(
            payload.get("position"), server_now=server_now, not_before=not_before
        )
    return occurred.isoformat()


def verify_position_request(
    point: object,
    *,
    server_now: str,
    not_before: str,
    newer_than: str | None = None,
) -> str:
    """Check shape and order, but NEVER return or persist lat/lon/recipient."""
    if not isinstance(point, dict) or set(point) != {
        "lat", "lon", "accuracy_m", "recorded_at"
    }:
        raise EvidenceMismatch("GPS fix missing required four-field shape")
    for field in ("lat", "lon", "accuracy_m"):
        val = point[field]
        if not isinstance(val, (float, int)) or isinstance(val, bool):
            raise EvidenceMismatch("GPS numeric field invalid")
    stamp = aware(point["recorded_at"])
    if not aware(not_before) <= stamp <= aware(server_now):
        raise EvidenceMismatch("GPS recorded_at outside dispatch/server clock")
    if newer_than is not None and stamp <= aware(newer_than):
        raise EvidenceMismatch("Completion GPS is not newer than driver_tap")
    return stamp.isoformat()


def step8_pass(stages: Mapping[str, object], order_id: int, trip_id: int) -> bool:
    """Only all three authoritative checkpoints on the same trip make Step 8 PASS."""
    for key in ("dispatch", "gps", "delivered"):
        stage = stages.get(key)
        if not isinstance(stage, dict):
            return False
        if (stage.get("status") != "PASS" or stage.get("order_id") != order_id
                or stage.get("trip_id") != trip_id
                or stage.get("db_verified") is not True):
            return False
        if key != "gps" and (not isinstance(stage.get("event_id"), int)
                            or stage["event_id"] <= 0):
            return False
        if key == "gps" and (not isinstance(stage.get("position_id"), int)
                             or stage["position_id"] <= 0):
            return False
    return True
