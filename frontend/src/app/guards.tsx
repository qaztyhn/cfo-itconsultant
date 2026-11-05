/**
 * RequireRole: chặn route không đúng vai trò, chuyển về điểm vào mặc định (docs/07 mục 18).
 * Owner: Dev 3 (luồng C) — M0.
 */
import type { ReactNode } from "react";

export type Role = "admin" | "dispatcher" | "warehouse" | "sales" | "driver" | "customer_service" | "viewer";

export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  void roles; // TODO(#M0-guards)
  return <>{children}</>;
}
