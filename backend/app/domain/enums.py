"""Enum khớp 1-1 với docs/05 mục 2 (tên là bất biến — 09 mục 4).

Owner: Dev 1 (luồng A) — M0.
"""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    DISPATCHER = "dispatcher"
    WAREHOUSE = "warehouse"
    SALES = "sales"
    DRIVER = "driver"
    CUSTOMER_SERVICE = "customer_service"
    VIEWER = "viewer"


class OrderStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    BLOCKED_UNMAPPED_SKU = "BLOCKED_UNMAPPED_SKU"
    PLANNED = "PLANNED"
    NO_FEASIBLE_DATE = "NO_FEASIBLE_DATE"
    APPROVED = "APPROVED"
    PREPARING = "PREPARING"
    GOODS_READY = "GOODS_READY"
    LOADED = "LOADED"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DateMode(StrEnum):
    EXACT = "exact"
    RANGE = "range"
    LATEST = "latest"


class EventType(StrEnum):
    START_PREP = "START_PREP"
    PREP_PAUSED = "PREP_PAUSED"
    PREP_RESUMED = "PREP_RESUMED"
    GOODS_READY = "GOODS_READY"
    LOADED = "LOADED"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    SHORTAGE = "SHORTAGE"
    BREAKAGE = "BREAKAGE"
    VEHICLE_ISSUE = "VEHICLE_ISSUE"
    SHIFT_CHANGE = "SHIFT_CHANGE"


class KpiScope(StrEnum):
    """v1.2: phân biệt Business owner và Project lead (cùng vai trò viewer)."""

    REVENUE_ALL = "revenue_all"
    OPS = "ops"


class RunKind(StrEnum):
    INITIAL = "initial"
    RERUN = "rerun"
    REPLAN_SUGGESTION = "replan_suggestion"  # không giữ chỗ, coi kế hoạch cũ như không tồn tại


class RiskStatus(StrEnum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    PREDICTED_LATE = "PREDICTED_LATE"
    OVERDUE = "OVERDUE"


class RiskColor(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


class NotifTemplate(StrEnum):
    CONFIRMED = "CONFIRMED"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DELAY = "DELAY"


class NotifStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


class PlanStatus(StrEnum):
    PROPOSED = "proposed"
    EXPIRED = "expired"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    MANUAL = "manual"


class ResStatus(StrEnum):
    HELD = "held"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class TransferStatus(StrEnum):
    SUGGESTED = "suggested"
    APPROVED = "approved"
    SOURCE_CONFIRMED = "source_confirmed"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class CheckName(StrEnum):
    STOCK = "stock"
    PREPARATION = "preparation"
    TRUCK = "truck"
    SITE_DATE = "site_date"
    SAFETY = "safety"


class PrepUnit(StrEnum):
    LINE = "line"
    PALLET = "pallet"
    M3 = "m3"
    BUNDLE = "bundle"
    PACKAGE = "package"
