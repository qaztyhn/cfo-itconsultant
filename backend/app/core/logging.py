"""Log kỹ thuật JSONL (04 mục 10, 09 mục 10).

Trường: ts, level, service (api|engine|integration|scheduler|notify), correlation_id, order_id,
market, event, duration_ms, extra. File logs/<service>/<YYYY-MM-DD>.jsonl (local), stdout (online).
KHÔNG PII: không tên, điện thoại, email, địa chỉ khách (09 bất biến 16; US-LOG-01 AC3).
Engine KHÔNG ghi log (09 bất biến 6).

- Khóa thuộc PII_KEYS bị loại ở mọi cấp của `extra`; chuỗi có dạng email bị che (lớp bảo vệ thứ hai).
- correlation_id lấy từ contextvar của middleware nếu không truyền (US-LOG-01 AC4).
- Ghi file chỉ khi `configure_logging(file_dir=...)` được gọi (create_app làm khi APP_ENV=local).

Owner: Dev 1 (luồng A) — M0.
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from app.core import clock
from app.core.correlation import correlation_id_var

PII_KEYS = frozenset(
    {
        "name",
        "phone",
        "email",
        "address",
        "contact_name",
        "contact_phone",
        "contact_email",
        "delivery_address",
        "recipient_name",
    }
)
SERVICES = frozenset({"api", "engine", "integration", "scheduler", "notify"})
LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})
_TOP_LEVEL = ("order_id", "market", "duration_ms")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_REDACTED = "[redacted]"

_logger = logging.getLogger("cfo.jsonl")
_logger.propagate = False
_file_dir: Path | None = None


def configure_logging(file_dir: Path | None = None) -> None:
    """Gắn handler stdout (một lần) và bật/tắt ghi file JSONL theo service/ngày."""
    global _file_dir
    _file_dir = file_dir
    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.DEBUG)


def scrub(value: Any) -> Any:
    """Loại khóa PII (đệ quy) và che chuỗi có dạng email; trả bản sao an toàn để ghi log."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if str(k).lower() not in PII_KEYS}
    if isinstance(value, list | tuple | set):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return _EMAIL_RE.sub(_REDACTED, value)
    return value


def build_record(service: str, event: str, level: str = "info", **fields: object) -> dict[str, object]:
    """Dựng một bản ghi log theo đúng bộ trường 04 mục 10 (không PII)."""
    if service not in SERVICES:
        raise ValueError(f"unknown log service: {service}")
    if level not in LEVELS:
        raise ValueError(f"unknown log level: {level}")
    correlation_id = fields.pop("correlation_id", None) or correlation_id_var.get()
    top = {key: fields.pop(key, None) for key in _TOP_LEVEL}
    return {
        "ts": clock.now().isoformat(),
        "level": level,
        "service": service,
        "correlation_id": correlation_id,
        "order_id": top["order_id"],
        "market": top["market"],
        "event": _EMAIL_RE.sub(_REDACTED, event),
        "duration_ms": top["duration_ms"],
        "extra": scrub(fields),
    }


def log_event(service: str, event: str, level: str = "info", **fields: object) -> None:
    """Ghi một dòng JSONL; tự loại khóa thuộc PII_KEYS."""
    record = build_record(service, event, level, **fields)
    line = json.dumps(record, ensure_ascii=False, default=str)
    if not _logger.handlers:
        configure_logging(_file_dir)
    _logger.log(logging.getLevelName(level.upper()), line)
    if _file_dir is not None:
        path = _file_dir / service / f"{str(record['ts'])[:10]}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
