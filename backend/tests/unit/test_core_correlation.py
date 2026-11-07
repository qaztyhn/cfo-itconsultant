"""normalize_correlation_id: chỉ chấp nhận UUID (cột audit.decision_log.correlation_id là uuid)."""

import uuid

import pytest

from app.core.correlation import normalize_correlation_id


def test_valid_uuid_is_canonicalised() -> None:
    assert (
        normalize_correlation_id(" 6C0F6C0F-0000-4000-8000-000000000001 ")
        == "6c0f6c0f-0000-4000-8000-000000000001"
    )


@pytest.mark.parametrize("value", [None, "", "request-123", "6c0f6c0f", "'; DROP TABLE x; --"])
def test_missing_or_invalid_value_gets_new_uuid4(value: str | None) -> None:
    cid = normalize_correlation_id(value)
    assert uuid.UUID(cid).version == 4 and cid != value
