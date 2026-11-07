/**
 * Menu sidebar theo vai trò (docs/03 mục 3.2). Hàm thuần: cùng quy tắc với route guard (access.ts), không bao giờ lệch nhau.
 * Driver không dùng sidebar (PWA riêng) nên không có mục nào.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { PATHS, anyRole, ruleFor, type AccessRule } from "./access";
import type { AuthUser } from "../api/contracts/auth";

export type BadgeKey = "order_queue" | "plan_review" | "exceptions" | "tracking_risk";

/** Phần của GET /orders/counts (docs/06 mục 5) mà menu cần. */
export interface BadgeCounts {
  awaiting_approval: number;
  nav: { order_queue: number; exceptions: number; tracking_risk: number };
}

export interface MenuItem {
  id: string;
  label: string;
  /** Route trong SPA. */
  to?: string;
  /** Ứng dụng ngoài (ASM-G); Sidebar ghép URL từ config. */
  external?: "pos";
  badge?: BadgeKey;
}

export interface MenuGroup {
  id: string;
  label: string;
  items: MenuItem[];
}

interface Def extends MenuItem {
  group: string;
  allow: AccessRule;
}

const GROUP_ORDER = ["DISPATCHER", "REVENUE", "SALES", "WAREHOUSE", "CUSTOMER SERVICE", "ADMIN"] as const;

const route = (group: string, label: string, to: string, badge?: BadgeKey): Def => ({
  group,
  id: to,
  label,
  to,
  badge,
  allow: ruleFor(to),
});

const DEFS: Def[] = [
  route("DISPATCHER", "Order queue", PATHS.dispatcherOrders, "order_queue"),
  route("DISPATCHER", "Plan review", PATHS.dispatcherPlanReview, "plan_review"),
  route("DISPATCHER", "Exceptions", PATHS.dispatcherExceptions, "exceptions"),
  route("DISPATCHER", "Tracking & risk", PATHS.dispatcherTracking, "tracking_risk"),
  route("DISPATCHER", "Transfers", PATHS.dispatcherTransfers),
  route("DISPATCHER", "KPIs & decision log", PATHS.kpi),
  route("REVENUE", "Revenue", PATHS.revenue),
  { group: "SALES", id: "pos-new-order", label: "New order", external: "pos", allow: anyRole("sales") },
  route("SALES", "My store orders", PATHS.storeOrders),
  route("WAREHOUSE", "Prep queue", PATHS.warehousePrep),
  route("WAREHOUSE", "Attendance & shifts", PATHS.warehouseAttendance),
  route("WAREHOUSE", "Transfers", PATHS.warehouseTransfers),
  route("CUSTOMER SERVICE", "Order lookup", PATHS.csOrders),
  route("CUSTOMER SERVICE", "Contact log", PATHS.csContacts),
  route("ADMIN", "Data integration", PATHS.itIntegration),
  route("ADMIN", "Product mapping", PATHS.itMapping),
  route("ADMIN", "Handling groups & norms", PATHS.itHandlingGroups),
  route("ADMIN", "Employees & locations", PATHS.itEmployees),
  route("ADMIN", "Vehicles & drivers", PATHS.itVehicles),
  route("ADMIN", "Users", PATHS.itUsers),
  route("ADMIN", "Market config & GPS", PATHS.itMarket),
  route("ADMIN", "Notification inbox", PATHS.notifications),
];

export function buildMenu(user: AuthUser): MenuGroup[] {
  return GROUP_ORDER.map((label) => ({
    id: label,
    label,
    items: DEFS.filter((d) => d.group === label && d.allow(user)).map(({ id, label: itemLabel, to, external, badge }) => ({
      id,
      label: itemLabel,
      to,
      external,
      badge,
    })),
  })).filter((group) => group.items.length > 0);
}

/** Giá trị huy hiệu; undefined khi chưa tải counts (không hiện số 0 giả). ASM-F: Plan review = awaiting_approval. */
export function badgeValue(counts: BadgeCounts | undefined, key: BadgeKey): number | undefined {
  if (!counts) {
    return undefined;
  }
  return key === "plan_review" ? counts.awaiting_approval : counts.nav[key];
}