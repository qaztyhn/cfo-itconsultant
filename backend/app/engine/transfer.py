"""Gợi ý chuyển kho bằng quy tắc (04 mục 6.4; BR-ATP-05; US-ATP-02).

Khi mọi kho STOCK_SHORT: kho nguồn s ≠ w đủ điều kiện nếu tồn sẵn có ≥ phần thiếu mọi dòng
(không dựa hàng nhập). Sắp theo lead_days tăng rồi khoảng cách tăng; tối đa 3.

Owner: Dev 1 (luồng A).
"""

from decimal import Decimal

from app.engine.types import TransferSuggestion, WarehouseCtx

MAX_SUGGESTIONS = 3


def suggest_transfers(
    target: WarehouseCtx,
    shortage: dict[int, Decimal],
    others: list[WarehouseCtx],
    lead_days: dict[tuple[int, int], int],
    distance_km: dict[tuple[int, int], Decimal],
    default_lead_days: int,
) -> tuple[TransferSuggestion, ...]:
    """Tối đa 3 gợi ý chuyển kho tới `target`.

    Kho nguồn hợp lệ khi tồn sẵn có (`stock_available`, không tính hàng nhập) ≥ phần thiếu cho MỌI sản phẩm.
    Sắp theo lead_days (theo cặp kho, mặc định `default_lead_days`) tăng, rồi khoảng cách tăng, rồi id kho.
    `distance_km` phải có cho mọi cặp nguồn → đích hợp lệ (service tính từ tọa độ); thiếu → ValueError.
    """
    if not shortage:
        return ()
    found: list[TransferSuggestion] = []
    for source in others:
        if source.id == target.id:
            continue
        if any(source.stock_available.get(p, Decimal(0)) < qty for p, qty in shortage.items()):
            continue
        pair = (source.id, target.id)
        if pair not in distance_km:
            raise ValueError(f"missing distance for warehouse pair {pair}")
        found.append(
            TransferSuggestion(
                from_warehouse_id=source.id,
                to_warehouse_id=target.id,
                lines=tuple(sorted(shortage.items())),
                lead_days=lead_days.get(pair, default_lead_days),
                distance_km=distance_km[pair],
            )
        )
    found.sort(key=lambda t: (t.lead_days, t.distance_km, t.from_warehouse_id))
    return tuple(found[:MAX_SUGGESTIONS])
