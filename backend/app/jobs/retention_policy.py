"""Versioned D5 synthetic-pilot retention review, never a deletion authorization.

Pure policy calculation on non-PII metadata. Caller/controller supplies the correct shared-record
anchor, holds and statutory classification; unknowns fail closed. No DB, archive or immutable-log writes.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

POLICY_VERSION = "2026-11-08.1"


@dataclass(frozen=True)
class Rule:
    amount: int
    unit: Literal["days", "months", "accounting_years", "workflow"]
    anchor: str
    purpose: str
    action: Literal["review", "statutory_review", "immutable_review", "gps_cleanup"] = "review"
    lawful_basis: str = "controller/legal review required before real-data use"


RULES = {
    "customer_contact": Rule(90, "days", "last associated terminal order/case closure", "delivery contact"),
    "cs_notification": Rule(90, "days", "resolved case/last associated terminal order", "customer service"),
    "operational_order": Rule(
        365, "days", "delivered/cancelled closure, not unresolved FAILED", "operations"
    ),
    "former_staff_contact": Rule(90, "days", "employment end, no active assignment", "staff account/contact"),
    "shift_attendance": Rule(24, "months", "official shift end", "nonstatutory workforce scheduling"),
    "app_log": Rule(30, "days", "log creation", "application operations"),
    "security_log": Rule(90, "days", "log creation", "security investigation"),
    "staging_backup": Rule(30, "days", "backup creation", "synthetic staging recovery"),
    "tachograph": Rule(12, "months", "record creation", "applicable statutory evidence", "statutory_review"),
    "driver_work_time": Rule(24, "months", "duty end", "applicable statutory evidence", "statutory_review"),
    "accounting": Rule(
        7,
        "accounting_years",
        "actual financial-year end",
        "qualifying accounting evidence",
        "statutory_review",
    ),
    "immutable_audit": Rule(
        24, "months", "event creation", "decision/milestone accountability", "immutable_review"
    ),
    "raw_gps": Rule(
        7,
        "days",
        "end of the verified collection window (trip terminal or duty end, whichever first)",
        "restricted trip investigation/complaint only (DEC-GPS-RET-20261109)",
        "gps_cleanup",
    ),
}


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    anchor: AwareDatetime | None = None
    timezone: str
    legal_hold: bool | None = None
    other_valid_purpose: bool | None = None
    regulated: bool | None = None
    terminal: bool | None = None


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_version: Literal["2026-11-08.1"]
    synthetic_only: Literal[True]
    items: list[ReviewRecord] = Field(max_length=100000)


def review_date(anchor: date, rule: Rule) -> date:
    if rule.unit == "days":
        return anchor + timedelta(days=rule.amount)
    if rule.unit == "accounting_years":
        # Keep through Dec 31 of the seventh calendar year after the actual fiscal-year end.
        return date(anchor.year + rule.amount + 1, 1, 1)
    if rule.unit == "months":
        year, month = divmod(anchor.year * 12 + anchor.month - 1 + rule.amount, 12)
        return date(year, month + 1, min(anchor.day, monthrange(year, month + 1)[1]))
    return anchor


def assess(record: ReviewRecord, *, now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Retention review time must be aware")
    rule = RULES.get(record.category)
    if rule is None:
        return "blocked_unknown_category"
    zone = ZoneInfo(record.timezone)
    if rule.action == "gps_cleanup":
        if record.terminal is not True:
            return "active_gps_or_unknown_workflow"
        # DEC-GPS-RET-20261109: valid collected points are kept at most 7 absolute days after the window end.
        if record.anchor is None or now >= record.anchor + timedelta(days=rule.amount):
            return "gps_cleanup_required"  # unknown anchor: deleting is the privacy-safe direction
        return "gps_retained_within_seven_days"
    if record.anchor is None:
        return "blocked_missing_anchor"
    if rule.action not in ("statutory_review", "immutable_review"):
        if record.legal_hold is not False or record.other_valid_purpose is not False:
            return "blocked_hold_or_shared_purpose"
        if record.regulated is not False:
            return "blocked_statutory_classification"
        if record.category in (
            "customer_contact",
            "cs_notification",
            "operational_order",
            "former_staff_contact",
        ):
            if record.terminal is not True:
                return "blocked_active_or_unknown_workflow"
    due = review_date(record.anchor.astimezone(zone).date(), rule)
    if now.astimezone(zone).date() < due:
        return "retain"
    if rule.action == "immutable_review":
        return "immutable_review_only"
    if rule.action == "statutory_review":
        return "statutory_review_only"
    return "candidate_for_privacy_review"


def summarize(data: ReviewInput, *, now: datetime) -> dict[str, object]:
    counts: dict[str, dict[str, int]] = {}
    for item in data.items:
        outcome = assess(item, now=now)
        category = item.category if item.category in RULES else "unknown"
        bucket = counts.setdefault(category, {})
        bucket[outcome] = bucket.get(outcome, 0) + 1
    return {"policy_version": POLICY_VERSION, "dry_run": True, "deletion_enabled": False, "counts": counts}
