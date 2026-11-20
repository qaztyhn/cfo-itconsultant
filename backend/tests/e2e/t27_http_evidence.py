"""Classify observed T27 outcomes without storing raw API errors or log records."""

import json
from pathlib import Path
from typing import Literal

_DRIVER_PREREQUISITES = {
    "Vehicle regulatory scope is unverified.": (
        ["T12", "T16"],
        "Vehicle regulatory scope was unverified for this trip.",
    ),
    "Driver is not eligible to operate (not_verified).": (
        ["T12"],
        "The fleet availability or vehicle qualification is missing or revoked.",
    ),
    "Driver is not eligible to operate (outside_shift).": (
        ["T12"],
        "The trip is outside the verified fleet availability window.",
    ),
    "Driver is not eligible to operate (driving).": (
        ["T12"],
        "The trip exceeds the fleet-confirmed daily driving budget.",
    ),
    "Event is outside the verified official driver shift.": (
        ["T12", "T16"],
        "The event was outside a verified official driver shift.",
    ),
    "Driver 56-day history completeness is not verified: EVIDENCE_MISSING": (
        ["T12", "T16"],
        "The backend reported missing 56-day driver history evidence.",
    ),
    "Mandatory ETA or notification integration is not available.": (
        ["T14", "E2"],
        "The backend reported an unavailable mandatory ETA or notification integration.",
    ),
}


def dispatch_rejection(http: int, code: str | None, message: str | None) -> dict[str, object]:
    prerequisite = (
        _DRIVER_PREREQUISITES.get(message or "") if (http, code) == (409, "PLAN_NOT_APPROVABLE") else None
    )
    if prerequisite is None:
        return {
            "status": "FAIL",
            "dispatch_status": "FAIL",
            "tasks": ["T06", "T16"],
            "reason": "Unexpected DISPATCHED rejection. See the captured HTTP status and error code.",
        }
    tasks, reason = prerequisite
    return {"status": "BLOCKED", "dispatch_status": "BLOCKED", "tasks": tasks, "reason": reason}


def _logged_eta_stub(log: Path, path: str, correlation_id: str | None) -> bool:
    if not correlation_id or not path.endswith("/eta-forecasts"):
        return False
    try:
        with log.open(encoding="utf-8", errors="replace") as records:
            for line in records:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(entry, dict) or entry.get("correlation_id") != correlation_id:
                    continue
                if entry.get("service") != "api" or entry.get("event") != "request.unhandled_error":
                    continue
                extra = entry.get("extra")
                if (
                    isinstance(extra, dict)
                    and extra.get("path") == path
                    and extra.get("error") == "NotImplementedError"
                ):
                    return True
    except OSError:
        return False
    return False


def eta_history_status(
    http: int | None, code: str | None, log: Path, path: str, correlation_id: str | None
) -> Literal["BLOCKED", "FAIL", "NOT VERIFIED"]:
    if http == 200:
        return "NOT VERIFIED"
    if (http, code) == (500, "INTERNAL_ERROR") and _logged_eta_stub(log, path, correlation_id):
        return "BLOCKED"
    return "FAIL"
