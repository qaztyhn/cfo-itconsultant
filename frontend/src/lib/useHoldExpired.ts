/**
 * Hold đã hết hạn chưa (so mốc hold_expires_at của server với đồng hồ máy). Chỉ để khoá nút sớm:
 * server vẫn là bên quyết định cuối cùng (409 HOLD_EXPIRED). Owner: Dev 3 (luồng C).
 */
import { useEffect, useState } from "react";

export function useHoldExpired(expiresAt: string | null | undefined): boolean {
  const [, tick] = useState(0);
  useEffect(() => {
    if (!expiresAt) return;
    const timer = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);

  if (!expiresAt) return false;
  const ms = new Date(expiresAt).getTime();
  return Number.isNaN(ms) || ms <= Date.now();
}