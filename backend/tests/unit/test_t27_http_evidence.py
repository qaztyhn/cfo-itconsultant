"""Focused T27 outcome tests run without the optional browser dependency."""

import json
from pathlib import Path

import pytest

from tests.e2e.t27_http_evidence import dispatch_rejection, eta_history_status

VEHICLE_PREREQUISITE = "Vehicle regulatory scope is unverified."
ETA_PATH = "/api/v1/orders/1/eta-forecasts"


@pytest.mark.parametrize(
    ("http", "code", "message"),
    [
        (409, "PLAN_NOT_APPROVABLE", None),
        (409, "PLAN_NOT_APPROVABLE", "Approved plan is unavailable."),
        (409, "PLAN_NOT_APPROVABLE", "Unexpected internal rejection detail."),
        (409, "ILLEGAL_TRANSITION", VEHICLE_PREREQUISITE),
        (401, "AUTH_INVALID", None),
        (403, "FORBIDDEN", VEHICLE_PREREQUISITE),
        (500, "INTERNAL_ERROR", VEHICLE_PREREQUISITE),
    ],
)
def test_US_EXE_02_AC1_unexpected_dispatch_rejection_is_fail(
    http: int, code: str, message: str | None
) -> None:
    result = dispatch_rejection(http, code, message)
    assert result["status"] == result["dispatch_status"] == "FAIL"
    assert message is None or message not in str(result)


def test_US_EXE_02_AC1_explicit_dispatch_prerequisite_is_blocked() -> None:
    result = dispatch_rejection(409, "PLAN_NOT_APPROVABLE", VEHICLE_PREREQUISITE)
    assert result["status"] == result["dispatch_status"] == "BLOCKED"
    assert result["reason"] == "Vehicle regulatory scope was unverified for this trip."


def test_US_CS_01_AC1_eta_stub_requires_same_request_failure_in_backend_log(tmp_path: Path) -> None:
    log = tmp_path / "api.log"
    correlation_id = "00000000-0000-4000-8000-000000000001"
    entry = {
        "correlation_id": correlation_id,
        "event": "request.unhandled_error",
        "service": "api",
        "extra": {"path": ETA_PATH, "error": "NotImplementedError"},
    }
    log.write_text(f"INFO: Test API startup\n{json.dumps(entry)}\n", encoding="utf-8")

    assert eta_history_status(500, "INTERNAL_ERROR", log, ETA_PATH, correlation_id) == "BLOCKED"
    assert eta_history_status(500, "INTERNAL_ERROR", log, ETA_PATH, "different-request") == "FAIL"
    assert (
        eta_history_status(500, "INTERNAL_ERROR", log, "/api/v1/orders/2/eta-forecasts", correlation_id)
        == "FAIL"
    )
    assert eta_history_status(403, "FORBIDDEN", log, ETA_PATH, correlation_id) == "FAIL"
    assert eta_history_status(None, None, log, ETA_PATH, correlation_id) == "FAIL"
    assert eta_history_status(200, None, log, ETA_PATH, correlation_id) == "NOT VERIFIED"

    entry["extra"] = {"path": ETA_PATH, "error": "RuntimeError"}
    log.write_text(json.dumps(entry), encoding="utf-8")
    assert eta_history_status(500, "INTERNAL_ERROR", log, ETA_PATH, correlation_id) == "FAIL"
