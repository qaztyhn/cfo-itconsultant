"""Fallback lộ trình: Haversine × 1,3 tại 50 km/h, provider='fallback' (US-INT-05 AC2).

Owner: Dev 2 (luồng B) — M2.
"""

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Khoảng cách đường chim bay (km)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def estimate(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    factor: float = 1.3,
    speed_kmh: float = 50.0,
) -> tuple[float, int]:
    """Trả (distance_km, duration_min) ước lượng."""
    km = haversine_km(lat1, lon1, lat2, lon2) * factor
    return round(km, 2), math.ceil(km / speed_kmh * 60)
