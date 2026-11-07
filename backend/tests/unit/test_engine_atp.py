"""Bước 2a — ATP theo thời gian (04 mục 6.2; US-ATP-01; 08 mục 6.2 hàng ATP)."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from app.engine.atp import add_working_days, check_atp, stock_check
from app.engine.types import InboundCtx, OrderCtx, WarehouseCtx
from tests.unit.engine_factory import CFG, N3, WED, cfg, line

NOW = datetime(2026, 11, 4, 10, 5, tzinfo=UTC)  # đồng hồ demo; ngày theo market do service truyền vào


def _order(*lines_: object) -> OrderCtx:
    return OrderCtx(1, 1, 59.0, 18.0, "latest", None, WED + timedelta(days=14), None, tuple(lines_), NOW)  # type: ignore[arg-type]


def _wh(stock: dict[int, str], *inbound: InboundCtx) -> WarehouseCtx:
    return WarehouseCtx(
        1, "WH", time(15), Decimal(1), {p: Decimal(q) for p, q in stock.items()}, inbound, {}, (), (), None
    )


def _inb(product: int, qty: str, eta_offset: int, ref: str = "INB-1") -> InboundCtx:
    return InboundCtx(product, Decimal(qty), WED + timedelta(days=eta_offset), ref)


def test_ready_now_when_available_stock_covers_all_lines() -> None:
    res = check_atp(_order(line(N3, "60", "40")), _wh({1: "60"}), CFG)
    assert (res.classification, res.stock_ready_date, res.shortage, res.inbound_refs) == (
        "ready_now",
        WED,
        {},
        (),
    )
    assert stock_check(res).code == "STOCK_OK" and stock_check(res).passed


def test_US_ATP_01_AC1_usable_50_less_than_60_is_short() -> None:
    # service đã trừ wms_reserved (20) và giữ chỗ đơn khác (30): 100 − 20 − 30 = 50
    res = check_atp(_order(line(N3, "60", "40")), _wh({1: "50"}), CFG)
    assert res.classification == "short" and res.stock_ready_date is None
    assert res.shortage == {1: Decimal(10)}
    check = stock_check(res)
    assert (check.passed, check.code) == (False, "STOCK_SHORT") and "message" in check.detail


def test_US_ATP_01_AC2_confirmed_inbound_counts_after_one_receiving_working_day() -> None:
    # hàng nhập ETA Thứ Năm 5/11 + 1 ngày làm việc nhận kho → dùng được Thứ Sáu 6/11
    res = check_atp(_order(line(N3, "60", "40")), _wh({1: "50"}, _inb(1, "40", 1)), CFG)
    assert res.classification == "after_inbound"
    assert res.stock_ready_date == WED + timedelta(days=2)
    assert res.inbound_refs == ("INB-1",)
    assert stock_check(res).code == "STOCK_AFTER_INBOUND" and stock_check(res).passed


def test_receiving_lead_days_skip_weekend() -> None:
    # ETA Thứ Sáu 6/11 + 1 ngày làm việc → Thứ Hai 9/11
    res = check_atp(_order(line(N3, "60", "40")), _wh({1: "50"}, _inb(1, "40", 2)), CFG)
    assert res.stock_ready_date == WED + timedelta(days=5)
    assert add_working_days(WED + timedelta(days=2), 1, CFG) == WED + timedelta(days=5)


def test_US_ATP_01_AC3_unconfirmed_inbound_is_not_passed_to_engine() -> None:
    """Service chỉ truyền hàng nhập confirmed & chưa received (WarehouseCtx.inbound); engine không tự lọc."""
    res = check_atp(_order(line(N3, "60", "40")), _wh({1: "50"}), CFG)
    assert res.classification == "short"


def test_US_ATP_01_AC4_not_enough_within_search_horizon_is_short() -> None:
    late = _inb(1, "40", CFG.search_days_max + 1)
    res = check_atp(_order(line(N3, "60", "40")), _wh({1: "50"}, late), CFG)
    assert res.classification == "short" and res.shortage == {1: Decimal(10)}
    longer = check_atp(_order(line(N3, "60", "40")), _wh({1: "50"}, late), cfg(search_days_max=30))
    assert longer.classification == "after_inbound"


def test_lines_of_same_product_are_summed_and_other_products_checked() -> None:
    order = _order(
        line(N3, "30", "40", product_id=1), line(N3, "30", "40", product_id=1), line(N3, "5", product_id=2)
    )
    res = check_atp(order, _wh({1: "60", 2: "4"}), CFG)
    assert res.classification == "short" and res.shortage == {2: Decimal(1)}


def test_shortage_after_partial_inbound_reports_remaining_quantity() -> None:
    res = check_atp(_order(line(N3, "100", "40")), _wh({1: "50"}, _inb(1, "20", 1)), CFG)
    assert res.shortage == {1: Decimal(30)}
