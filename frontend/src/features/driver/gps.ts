/**
 * Gửi vị trí mỗi gps.interval_min (30') CHỈ khi chuyến on_road, sau khi hiện thông báo quyền riêng tư và xin quyền
 * vị trí (US-GPS-01 AC3/AC5). Từ chối quyền → app vẫn dùng cho mốc, dispatcher thấy "Location off".
 * Owner: Dev 3 (luồng C) — M6.
 */
export function startTracking(tripId: number): () => void {
  void tripId; // TODO(#M6-gps)
  return () => undefined;
}
