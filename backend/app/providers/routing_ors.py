"""RoutingProvider dùng OpenRouteService (driving-hgv) — tính ma trận (kho, điểm giao) và chỉ đường
còn lại cho GPS (04 mục 3, 5.2 bước 9; US-INT-05). Engine KHÔNG gọi module này.

Owner: Dev 2 (luồng B) — M2.
"""


class OrsRoutingProvider:
    """Gọi ORS matrix/directions; lỗi/hết quota → để service chuyển sang fallback. TODO(#M2-routing)."""
