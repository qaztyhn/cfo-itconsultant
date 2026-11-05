"""Bước 2d + 2e + 2f — xe, tài xế, ngày giao, cửa sổ nhận hàng, dự trữ (04 mục 6.2;
BR-DEL-01..04; US-PLN-03/04/05).

Xe: cùng kho, available, đủ kg/m³, nhóm hàng cho phép, đủ capabilities (crane/dump);
tài xế: cùng kho, có mặt, bằng ≥ yêu cầu và còn hạn, ≤ driver_max_hours_day, không trùng giờ.
Ngày: exact không sớm hơn; range từ date_from; latest ≤ date_to; ngoài cửa sổ → ngày làm việc kế.
ETA làm tròn lên eta_round_min. planning_reserve = close(window(date_to)) − earliest_feasible_eta.

Owner: Dev 1 (luồng A).
"""

from dataclasses import dataclass
from datetime import date, datetime

from app.engine.types import CheckResult, DriverCtx, EngineConfig, OrderCtx, VehicleCtx, WarehouseCtx


@dataclass(frozen=True)
class DeliveryOption:
    vehicle: VehicleCtx
    driver: DriverCtx
    target_date: date
    depart_at: datetime
    eta_at: datetime
    trip_end_at: datetime
    planning_reserve_min: int


def candidate_vehicles(order: OrderCtx, wh: WarehouseCtx) -> tuple[VehicleCtx, ...]:
    """Lọc xe hợp lệ theo tải/thể tích/nhóm/năng lực. TODO(#M4-delivery)."""
    raise NotImplementedError


def plan_delivery(
    order: OrderCtx, wh: WarehouseCtx, vehicle: VehicleCtx, loading_start_at: datetime, cfg: EngineConfig
) -> tuple[DeliveryOption | None, tuple[CheckResult, ...]]:
    """Chọn tài xế, ngày giao, ETA cho một xe; trả các check truck/site_date/safety. TODO(#M4-delivery)."""
    raise NotImplementedError
