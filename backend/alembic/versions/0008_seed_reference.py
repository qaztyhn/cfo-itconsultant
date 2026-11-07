"""0008_seed_reference

Seed tham chiếu: market SE + MarketConfig mặc định, handling_group N1–N6 (05 mục 11), special_flag,
position, order_transition (v1.2: NO_FEASIBLE_DATE → APPROVED khi lập tay;
PREPARING/GOODS_READY/LOADED/FAILED → APPROVED khi duyệt gợi ý lập lại), position.default_kpi_scopes.

Diễn giải ghi ở docs/ASSUMPTIONS.md ASM-002 (vai trò "system" = mảng rỗng, gps_enabled, min_crew N2, nhóm
position). KHÔNG seed tài khoản, nhân viên, mật khẩu hay dữ liệu demo (thuộc seed/generate_data.py — Dev 2,
09 bất biến 25). Không có thiết bị kho (09 bất biến 23).

Nguồn sự thật: docs/05_Database_Design.md. Không đổi tên bảng/cột/enum (09 mục 6).
Owner: Dev 1 (luồng A).
"""

import json

from alembic import op

revision = "0008"
down_revision = "0007"

# 04 mục 8 — MarketConfig mặc định [A], sao chép nguyên văn.
MARKET_CONFIG: dict[str, object] = {
    "working_days": [1, 2, 3, 4, 5],
    "default_receiving_hours": {"mon-fri": ["07:00", "16:00"]},
    "search_days_max": 14,
    "reserve_safe_days": 2,
    "promise_window_hours": 2,
    "eta_round_min": 15,
    "delivery_share": 0.90,
    "final_inspection_hours": 0.5,
    "flag_multiplier_cap": 2.0,
    "loading": {"base_min": 20, "min_per_ton": 6},
    "unloading": {"base_min": 20, "min_per_ton": 6},
    "after_loaded_min": 10,
    "driver_max_hours_day": 9,
    "receiving_lead_days": 1,
    "multi_vehicle": {"max_arrival_spread_min": 30},
    "transfer_lead_days_default": 1,
    "rank": {
        "w_km": 0.5,
        "w_fill": 0.5,
        "dz_km_abs": 2,
        "dz_km_pct": 0.05,
        "dz_fill": 0.05,
        "tie_eps": 0.001,
    },
    "risk": {
        "yellow_pct": 33,
        "orange_pct": 66,
        "consecutive_negative": 2,
        "min_reserve_min": 30,
        "milestone_grace_min": 30,
        "consecutive_min_gap_min": 5,
    },
    "hold": {"ttl_min": 15, "max_extensions": 2},
    "stale_stock_min": 15,
    "gps": {"interval_min": 30, "lost_min": 60, "retention_days": 30},
    "notify": {"quiet_hours": ["21:00", "07:00"], "delay_min_shift_min": 30, "max_attempts": 3},
    "data_retention_days": {"personal": 365, "order": 730},
    "sync": {"interval_min": 5, "overlap_min": 2},
    "routing": {"allow_fallback": True},  # 06 Phụ lục A
}

# 05 mục 11 — (code, name, description, prep_unit, fixed_hours, labour_hours_per_unit, min_crew, vehicle_req)
HANDLING_GROUPS: tuple[tuple[str, str, str, str, str, str, int, tuple[str, ...]], ...] = (
    ("N1", "Small items & accessories", "Hàng nhỏ nhặt tay (keo tuýp, ốc vít, dụng cụ, sơn lon)",
     "line", "0", "0.05", 1, ()),
    ("N2", "Boards, sheets & tiles", "Hàng tấm, thùng xếp chồng (ván, thạch cao, gạch ốp)",
     "pallet", "0.25", "0.40", 1, ()),
    ("N3", "Bagged cement & mortar", "Hàng bao nặng theo pallet (xi măng, vữa, keo dán gạch)",
     "pallet", "0.25", "0.15", 1, ()),
    ("N4", "Bulk materials", "Vật liệu rời (cát, đá, sỏi)",
     "m3", "0.50", "0.10", 1, ("dump",)),
    ("N5", "Long goods", "Hàng dài, nặng (gỗ dài, thép cây, ống, xà gồ)",
     "bundle", "0.50", "0.50", 2, ()),
    ("N6", "Large & fragile items", "Hàng lớn, dễ vỡ, giá trị cao (kính, khung cửa, cửa, sứ vệ sinh)",
     "package", "0.25", "0.60", 2, ()),
)  # fmt: skip

SPECIAL_FLAGS: tuple[tuple[str, str, str], ...] = (
    ("FRAGILE", "Fragile", "1.25"),
    ("SPECIAL_STORAGE", "Special storage", "1.15"),
    ("HAZARDOUS", "Hazardous", "1.30"),
    ("FAR_OR_OUTDOOR", "Far or outdoor", "1.20"),
)

# 05 mục 4 — (code, name, grp, default_roles, default_kpi_scopes).
# Công nhân kho không có tài khoản (09 bất biến 18).
POSITIONS: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("WAREHOUSE_MANAGER", "Warehouse manager", "warehouse", ("warehouse",), ("ops",)),
    ("WAREHOUSE_DEPUTY", "Warehouse deputy manager", "warehouse", ("warehouse",), ("ops",)),
    ("WAREHOUSE_SUPERVISOR", "Warehouse shift supervisor", "warehouse", ("warehouse",), ()),
    ("WAREHOUSE_OPERATOR", "Warehouse operator", "warehouse", (), ()),
    ("FORKLIFT_OPERATOR", "Forklift operator", "warehouse", (), ()),
    ("DRIVER", "Driver", "transport", ("driver",), ()),
    ("DISPATCHER", "Dispatcher", "transport", ("dispatcher",), ("ops",)),
    ("STORE_MANAGER", "Store manager", "store", ("sales",), ()),
    ("SALES_RETAIL", "Sales (retail)", "store", ("sales",), ()),
    ("SALES_TRADE", "Sales (trade)", "store", ("sales",), ()),
    ("CUSTOMER_SERVICE", "Customer service", "central", ("customer_service",), ()),
    ("IT_INTEGRATION", "IT integration", "central", ("admin",), ()),
    ("BUSINESS_OWNER", "Business owner", "central", ("viewer",), ("revenue_all",)),
    ("PROJECT_LEAD", "Project lead", "central", ("viewer",), ("ops",)),
)

# 05 mục 6 — bảng chuyển trạng thái; vai trò "system" lưu là mảng rỗng (ASM-002).
D, W, DR = ("dispatcher",), ("warehouse",), ("driver",)
TRANSITIONS: tuple[tuple[str, str, bool, tuple[str, ...]], ...] = (
    ("SUBMITTED", "PLANNED", False, ()),
    ("SUBMITTED", "BLOCKED_UNMAPPED_SKU", False, ()),
    ("SUBMITTED", "NO_FEASIBLE_DATE", False, ()),
    ("BLOCKED_UNMAPPED_SKU", "SUBMITTED", False, ()),
    ("PLANNED", "APPROVED", False, D),
    ("NO_FEASIBLE_DATE", "APPROVED", True, D),
    ("PLANNED", "SUBMITTED", True, D),
    ("NO_FEASIBLE_DATE", "SUBMITTED", True, D),
    ("NO_FEASIBLE_DATE", "CANCELLED", True, D),
    ("PLANNED", "CANCELLED", True, D),
    ("APPROVED", "PREPARING", False, W),
    ("APPROVED", "SUBMITTED", True, D),
    ("PREPARING", "APPROVED", True, D),
    ("GOODS_READY", "APPROVED", True, D),
    ("LOADED", "APPROVED", True, D),
    ("FAILED", "APPROVED", True, D),
    ("PREPARING", "GOODS_READY", False, W),
    ("GOODS_READY", "LOADED", False, W),
    ("LOADED", "DISPATCHED", False, DR),
    ("DISPATCHED", "DELIVERED", False, DR),
    ("DISPATCHED", "FAILED", True, DR),
    ("FAILED", "SUBMITTED", True, D),
    ("APPROVED", "CANCELLED", True, D),
    ("PREPARING", "CANCELLED", True, D),
    ("GOODS_READY", "CANCELLED", True, D),
    ("LOADED", "CANCELLED", True, D),
)


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _arr(values: tuple[str, ...], cast: str) -> str:
    return "'{" + ",".join(values) + "}'::" + cast


def upgrade() -> None:
    """Chèn dữ liệu tham chiếu (hằng số trong mã, không đọc input ngoài)."""
    op.execute(
        "INSERT INTO ref.market (code, name, timezone, locale, currency, gps_enabled, shadow_mode, "
        "source_api_key_ref, config) VALUES ('SE', 'Sweden', 'Europe/Stockholm', 'en', 'SEK', false, false, "
        f"'SOURCE_SE_API_KEY', {_q(json.dumps(MARKET_CONFIG))}::jsonb)"
    )
    for code, name, desc, unit, fixed, per_unit, crew, req in HANDLING_GROUPS:
        op.execute(
            "INSERT INTO ref.handling_group (code, name, description, prep_unit, fixed_hours, "
            "labour_hours_per_unit, min_crew, vehicle_requirement) VALUES "
            f"({_q(code)}, {_q(name)}, {_q(desc)}, {_q(unit)}, {fixed}, {per_unit}, {crew}, "
            f"{_arr(req, 'text[]')})"
        )
    for code, name, multiplier in SPECIAL_FLAGS:
        op.execute(
            "INSERT INTO ref.special_flag (code, name, multiplier) "
            f"VALUES ({_q(code)}, {_q(name)}, {multiplier})"
        )
    for code, name, grp, roles, scopes in POSITIONS:
        op.execute(
            "INSERT INTO hr.position (code, name, grp, default_roles, default_kpi_scopes) VALUES "
            f"({_q(code)}, {_q(name)}, {_q(grp)}, {_arr(roles, 'ref.user_role[]')}, {_arr(scopes, 'text[]')})"
        )
    for src, dst, reason, roles in TRANSITIONS:
        op.execute(
            "INSERT INTO ops.order_transition (from_status, to_status, requires_reason, allowed_roles) "
            "VALUES "
            f"({_q(src)}, {_q(dst)}, {str(reason).lower()}, {_arr(roles, 'ref.user_role[]')})"
        )


def downgrade() -> None:
    """Xóa đúng các dòng đã seed."""
    op.execute("DELETE FROM ops.order_transition")
    codes = ", ".join(_q(p[0]) for p in POSITIONS)
    op.execute(f"DELETE FROM hr.position WHERE code IN ({codes})")
    flags = ", ".join(_q(f[0]) for f in SPECIAL_FLAGS)
    op.execute(f"DELETE FROM ref.special_flag WHERE code IN ({flags})")
    groups = ", ".join(_q(g[0]) for g in HANDLING_GROUPS)
    op.execute(f"DELETE FROM ref.handling_group WHERE code IN ({groups})")
    op.execute("DELETE FROM ref.market WHERE code = 'SE'")
