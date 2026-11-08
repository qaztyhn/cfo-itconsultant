"""Source clock with explicit APP_NOW injection (09 invariant 17)."""

from datetime import UTC, datetime


def now(override: str | None = None) -> datetime:
    value = datetime.fromisoformat(override) if override else datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Source clock must be timezone-aware")
    return value.astimezone(UTC)
