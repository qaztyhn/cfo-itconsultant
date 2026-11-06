"""Nạp ngữ cảnh từ DB cho engine lập kế hoạch (04 mục 6.1; 05 mục 6–7). Chỉ đọc, không khóa.

- `available_stock`: on_hand − wms_reserved − giữ chỗ hàng của ĐƠN KHÁC (committed + held còn hạn), không âm.
  Lúc lập kế hoạch KHÔNG khóa (09 bất biến 11; không `FOR UPDATE` trên ops.stock_snapshot — 09 mục 5).
- `confirmed_inbound`: hàng nhập confirmed, chưa received (hàng chưa xác nhận không tính — BR-ATP).
- `fleet_context`: xe `available` của kho (nhóm hàng theo mã, năng lực, bằng yêu cầu, khoảng bận = lịch
  vehicle_availability + giữ chỗ xe của ĐƠN KHÁC) và tài xế cùng kho gốc (ngày có mặt theo điểm danh, trừ nghỉ
  phép đã duyệt; giờ đã giữ theo ngày; khoảng bận).
- `route_info`: đọc plan.route_matrix đã tính trước; engine không gọi API (09 mục 8). Thiếu cặp → None
  (engine áp dụng `routing.allow_fallback`).
Truy vấn gom theo tập kho/sản phẩm (không N+1).

Owner: Dev 1 (A) — M4.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal, cast

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.hr import Absence, Attendance, DriverStaff
from app.domain.models.ops import InboundShipment, StockSnapshot
from app.domain.models.plan import PlanningRun, RouteMatrix, StockReservation, VehicleReservation
from app.domain.models.ref import HandlingGroup, Vehicle, VehicleAvailability
from app.engine.types import DriverCtx, InboundCtx, RouteInfo, VehicleCtx

LicenceT = Literal["B", "C", "CE"]


async def available_stock(
    session: AsyncSession,
    warehouse_ids: Sequence[int],
    product_ids: Sequence[int],
    *,
    now: datetime,
    exclude_order_id: int | None,
) -> dict[int, dict[int, Decimal]]:
    """{kho: {sản phẩm: tồn khả dụng}} cho mọi cặp được hỏi (thiếu ảnh chụp → 0)."""
    on_hand: dict[tuple[int, int], Decimal] = {
        (w, p): oh - res
        for w, p, oh, res in (
            await session.execute(
                select(
                    StockSnapshot.warehouse_id,
                    StockSnapshot.global_product_id,
                    StockSnapshot.on_hand,
                    StockSnapshot.wms_reserved,
                ).where(
                    StockSnapshot.warehouse_id.in_(warehouse_ids),
                    StockSnapshot.global_product_id.in_(product_ids),
                )
            )
        ).all()
    }
    held_query = (
        select(
            StockReservation.warehouse_id, StockReservation.global_product_id, func.sum(StockReservation.qty)
        )
        .join(PlanningRun, PlanningRun.id == StockReservation.run_id)
        .where(
            StockReservation.warehouse_id.in_(warehouse_ids),
            StockReservation.global_product_id.in_(product_ids),
            or_(
                StockReservation.status == "committed",
                and_(StockReservation.status == "held", PlanningRun.hold_expires_at > now),
            ),
        )
        .group_by(StockReservation.warehouse_id, StockReservation.global_product_id)
    )
    if exclude_order_id is not None:
        held_query = held_query.where(StockReservation.order_id != exclude_order_id)
    reserved = {(w, p): q for w, p, q in (await session.execute(held_query)).all()}
    return {
        w: {
            p: max(Decimal(0), on_hand.get((w, p), Decimal(0)) - reserved.get((w, p), Decimal(0)))
            for p in product_ids
        }
        for w in warehouse_ids
    }


async def confirmed_inbound(
    session: AsyncSession, warehouse_ids: Sequence[int], product_ids: Sequence[int]
) -> dict[int, tuple[InboundCtx, ...]]:
    """{kho: hàng nhập confirmed & chưa received của các sản phẩm được hỏi}, sắp theo ETA rồi mã."""
    result = await session.execute(
        select(InboundShipment)
        .where(
            InboundShipment.warehouse_id.in_(warehouse_ids),
            InboundShipment.global_product_id.in_(product_ids),
            InboundShipment.confirmed.is_(True),
            InboundShipment.received.is_(False),
        )
        .order_by(InboundShipment.eta_date, InboundShipment.inbound_ref)
    )
    by_wh: dict[int, list[InboundCtx]] = defaultdict(list)
    for row in result.scalars():
        by_wh[row.warehouse_id].append(
            InboundCtx(row.global_product_id, row.qty, row.eta_date, row.inbound_ref)
        )
    return {w: tuple(items) for w, items in by_wh.items()}


async def route_info(
    session: AsyncSession, warehouse_ids: Sequence[int], to_lat: Decimal, to_lon: Decimal
) -> dict[int, RouteInfo | None]:
    """{kho: RouteInfo hoặc None} từ plan.route_matrix cho điểm giao (tọa độ numeric(8,5) khớp chính xác)."""
    result = await session.execute(
        select(RouteMatrix).where(
            RouteMatrix.warehouse_id.in_(warehouse_ids),
            RouteMatrix.to_lat == to_lat,
            RouteMatrix.to_lon == to_lon,
        )
    )
    found = {
        r.warehouse_id: RouteInfo(r.distance_km, r.duration_min, "ors" if r.provider == "ors" else "fallback")
        for r in result.scalars()
    }
    return {w: found.get(w) for w in warehouse_ids}


def _active_reservations(now: datetime, exclude_order_id: int | None) -> Select[VehicleReservation]:
    query = (
        select(VehicleReservation)
        .join(PlanningRun, PlanningRun.id == VehicleReservation.run_id)
        .where(
            or_(
                VehicleReservation.status == "committed",
                and_(VehicleReservation.status == "held", PlanningRun.hold_expires_at > now),
            )
        )
    )
    if exclude_order_id is not None:
        query = query.where(VehicleReservation.order_id != exclude_order_id)
    return query


async def fleet_context(
    session: AsyncSession,
    warehouse_id: int,
    days: Sequence[date],
    *,
    now: datetime,
    today: date,
    exclude_order_id: int | None,
) -> tuple[tuple[VehicleCtx, ...], tuple[DriverCtx, ...]]:
    """Xe và tài xế của một kho cho các ngày đang xét (giữ chỗ của đơn khác: committed + held còn hạn)."""
    if not days:
        return (), ()
    first, last = min(days), max(days)
    window_start = datetime.combine(first, time.min, tzinfo=now.tzinfo)
    window_end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=now.tzinfo)
    group_codes = {g.id: g.code for g in (await session.execute(select(HandlingGroup))).scalars()}

    vehicles = (
        (
            await session.execute(
                select(Vehicle)
                .where(Vehicle.home_warehouse_id == warehouse_id, Vehicle.status == "available")
                .order_by(Vehicle.code)
            )
        )
        .scalars()
        .all()
    )
    vehicle_ids = [v.id for v in vehicles]
    busy_vehicle: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
    for va in (
        await session.execute(
            select(VehicleAvailability).where(VehicleAvailability.vehicle_id.in_(vehicle_ids))
        )
    ).scalars():
        if va.during.lower is not None and va.during.upper is not None:
            if va.during.lower < window_end and window_start < va.during.upper:
                busy_vehicle[va.vehicle_id].append((va.during.lower, va.during.upper))

    drivers = (
        (
            await session.execute(
                select(DriverStaff)
                .where(DriverStaff.home_warehouse_id == warehouse_id)
                .order_by(DriverStaff.employee_id)
            )
        )
        .scalars()
        .all()
    )
    driver_ids = [d.employee_id for d in drivers]
    busy_driver: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
    booked: dict[int, dict[date, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for res in (await session.execute(_active_reservations(now, exclude_order_id))).scalars():
        lower, upper = res.during.lower, res.during.upper
        if lower is None or upper is None or not (lower < window_end and window_start < upper):
            continue
        if res.vehicle_id in vehicle_ids:
            busy_vehicle[res.vehicle_id].append((lower, upper))
        if res.driver_employee_id in driver_ids:
            busy_driver[res.driver_employee_id].append((lower, upper))
            booked[res.driver_employee_id][lower.date()] += (
                Decimal(int((upper - lower).total_seconds())) / 3600
            )

    approved_leave = select(Absence.id).where(
        Absence.employee_id == Attendance.employee_id,
        Absence.approved.is_(True),
        Absence.start_date <= Attendance.work_date,
        Absence.end_date >= Attendance.work_date,
    )
    present_rows = await session.execute(
        select(Attendance.employee_id, Attendance.work_date).where(
            Attendance.employee_id.in_(driver_ids),
            Attendance.work_date.between(first, last),
            or_(
                Attendance.status == "present",
                and_(Attendance.status == "planned", Attendance.work_date > today),
            ),
            ~approved_leave.exists(),
        )
    )
    available: dict[int, set[date]] = defaultdict(set)
    for employee_id, work_date in present_rows.all():
        available[employee_id].add(work_date)

    vehicle_ctx = tuple(
        VehicleCtx(
            id=v.id,
            code=v.code,
            capacity_kg=v.capacity_kg,
            capacity_m3=v.capacity_m3,
            capabilities=frozenset(v.capabilities),
            required_licence=cast(LicenceT, v.required_licence),
            allowed_group_codes=frozenset(group_codes[g] for g in v.allowed_group_ids if g in group_codes),
            busy=tuple(sorted(busy_vehicle[v.id])),
        )
        for v in vehicles
    )
    driver_ctx = tuple(
        DriverCtx(
            employee_id=d.employee_id,
            licence_class=cast(LicenceT, d.licence_class),
            licence_expires_on=d.licence_expires_on,
            available_days=frozenset(available[d.employee_id]),
            booked_hours_by_day=dict(booked[d.employee_id]),
            busy=tuple(sorted(busy_driver[d.employee_id])),
        )
        for d in drivers
    )
    return vehicle_ctx, driver_ctx
