"""core.logging: bộ trường JSONL 04 mục 10, không PII (US-LOG-01 AC3), correlation_id (AC4)."""

import json
from pathlib import Path

import pytest

from app.core import logging as cfo_logging
from app.core.correlation import correlation_id_var

SAMPLE_PII = {
    "name": "Erik Berg",
    "contact_phone": "+46701234567",
    "email": "erik@example.se",
    "delivery_address": "Storgatan 12, Göteborg",
}


def test_record_has_exactly_the_04_fields() -> None:
    record = cfo_logging.build_record(
        "api", "plan.created", order_id=4021, market="SE", duration_ms=12, run_id=9
    )
    assert list(record) == [
        "ts", "level", "service", "correlation_id", "order_id", "market", "event", "duration_ms", "extra",
    ]  # fmt: skip
    assert record["order_id"] == 4021 and record["market"] == "SE" and record["extra"] == {"run_id": 9}


def test_US_LOG_01_AC3_no_customer_pii_in_jsonl(tmp_path: Path) -> None:
    cfo_logging.configure_logging(tmp_path)
    try:
        cfo_logging.log_event(
            "integration",
            "order.ingested for erik@example.se",
            order_id=1,
            customer={**SAMPLE_PII, "id": 311},
            lines=[{"recipient_name": "Erik Berg", "qty": 2}],
            note="contact erik@example.se",
            **SAMPLE_PII,
        )
    finally:
        cfo_logging.configure_logging(None)
    (file,) = (tmp_path / "integration").glob("*.jsonl")
    text = file.read_text(encoding="utf-8")
    for value in (*SAMPLE_PII.values(), "Erik", "example.se"):
        assert value not in text
    record = json.loads(text)
    assert record["extra"]["customer"] == {"id": 311}
    assert record["extra"]["lines"] == [{"qty": 2}]


def test_US_LOG_01_AC4_correlation_id_from_request_context() -> None:
    token = correlation_id_var.set("6c0f6c0f-0000-4000-8000-000000000001")
    try:
        assert (
            cfo_logging.build_record("api", "x")["correlation_id"] == "6c0f6c0f-0000-4000-8000-000000000001"
        )
    finally:
        correlation_id_var.reset(token)


def test_unknown_service_or_level_rejected() -> None:
    with pytest.raises(ValueError):
        cfo_logging.build_record("web", "x")
    with pytest.raises(ValueError):
        cfo_logging.build_record("api", "x", level="loud")
