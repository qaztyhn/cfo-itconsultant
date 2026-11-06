"""Bước 2d + 2e + 2f — bộ xe, tài xế, ngày giao, cửa sổ nhận hàng, dự trữ (04 mục 6.2;
BR-DEL-01..05; US-PLN-03/04/05, US-ORD-05).

v1.2 — NHIỀU XE: chọn bộ xe hợp lệ (cùng kho, available, nhóm hàng cho phép, đủ capabilities crane/dump)
rảnh cùng ngày với Σ kg ≥ tổng kg, Σ m³ ≥ tổng m³, SỐ XE ÍT NHẤT; cùng số xe thì tổng tải nhỏ hơn.
Không giới hạn số xe. Chia hàng theo tải/thể tích (một dòng được tách). Mỗi xe một tài xế: cùng kho,
có mặt, bằng ≥ yêu cầu và còn hạn, ≤ driver_max_hours_day, không trùng giờ. Lên hàng lần lượt; mọi xe
tới trong cửa sổ, chênh ≤ max_arrival_spread_min. Không có bộ xe → NO_TRUCK_FIT (detail.reason =
capability | combined_capacity) / TRUCK_BUSY / NO_DRIVER. Không ghép đơn.
Ngày: exact không sớm hơn; range từ date_from; latest ≤ date_to; ngoài cửa sổ → ngày làm việc kế.
ETA làm tròn lên eta_round_min; ETA phương án = xe tới cuối. planning_reserve = close(window(date_to))
− earliest_feasible_eta.

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.engine.types import CheckResult, EngineConfig, OrderCtx, VehicleAssignment, VehicleCtx, WarehouseCtx


@dataclass(frozen=True)
class DeliveryOption:
    vehicles: tuple[VehicleAssignment, ...]
    target_date: date
    planning_reserve_min: int


def eligible_vehicles(order: OrderCtx, wh: WarehouseCtx) -> tuple[VehicleCtx, ...]:
    """Xe hợp lệ theo nhóm hàng và năng lực (chưa xét tải). TODO(#M4-delivery)."""
    raise NotImplementedError


def choose_vehicle_sets(
    order: OrderCtx, wh: WarehouseCtx, day: date, max_sets: int = 2
) -> tuple[tuple[VehicleCtx, ...], ...]:
    """Các bộ xe rảnh trong ngày đủ tổng kg/m³, sắp theo (số xe, tổng tải) tăng dần. TODO(#M4-delivery)."""
    raise NotImplementedError


def split_load(
    order: OrderCtx, vehicle_set: tuple[VehicleCtx, ...]
) -> tuple[tuple[tuple[int, Decimal], ...], ...]:
    """Chia dòng hàng cho các xe theo tải và thể tích; một dòng có thể tách. TODO(#M4-delivery)."""
    raise NotImplementedError


def plan_delivery(
    order: OrderCtx,
    wh: WarehouseCtx,
    vehicle_set: tuple[VehicleCtx, ...],
    goods_ready_at: datetime,
    cfg: EngineConfig,
) -> tuple[DeliveryOption | None, tuple[CheckResult, ...]]:
    """Gán tài xế, xếp giờ lên hàng/xuất phát để các xe tới cùng lúc; trả check truck/site_date/safety.
    TODO(#M4-delivery)."""
    raise NotImplementedError
