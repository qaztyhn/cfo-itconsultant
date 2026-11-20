/**
 * Hold đã hết hạn chưa (so mốc hold_expires_at của server với đồng hồ máy). Chỉ để khoá nút sớm:
 * server vẫn là bên quyết định cuối cùng (409 HOLD_EXPIRED). Owner: Dev 3 (luồng C).
 * "Bây giờ" được giữ trong state và cập nhật mỗi giây (không gọi Date.now() trong lúc render: react-hooks/purity).
 */
import { useEffect, useState } from "react";
import { isDemoEnv } from "../api/config";

/** The disposable demo server can pin business time independently of the browser. */
export function planningNow(): number {
  const configured = Date.parse(import.meta.env.VITE_DEMO_APP_NOW ?? "");
  return isDemoEnv() && Number.isFinite(configured) ? configured : Date.now();
}

export function useHoldExpired(expiresAt: string | null | undefined): boolean {
  const [now, setNow] = useState(planningNow);

  useEffect(() => {
    if (!expiresAt) return;
    const timer = setInterval(() => setNow(planningNow()), 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);

  if (!expiresAt) return false;
  const ms = new Date(expiresAt).getTime();
  return Number.isNaN(ms) || ms <= now;
}