/**
 * Quy tắc truy cập phía GIAO DIỆN: nguồn duy nhất cho route guard, menu và màn hình mặc định.
 * Chỉ điều khiển trải nghiệm. KHÔNG thay RBAC backend — máy chủ vẫn kiểm quyền mọi endpoint (docs/06 mục 3, docs/09).
 * Các ASM A–H của T4 nằm ở đây; đổi chính sách thì sửa file này.
 * Owner: Dev 3 (luồng C) — M0.
 */
import type { AuthUser, UserRole } from "../api/contracts/auth";

export type AccessRule = (user: AuthUser) => boolean;

export const anyRole =
  (...roles: UserRole[]): AccessRule =>
  (user) =>
    user.roles.some((role) => roles.includes(role));

export const isAdmin = anyRole("admin");
/** ASM-D: KPI vận hành = admin hoặc kpi_scopes có `ops`. */
export const canViewKpi: AccessRule = (user) => isAdmin(user) || user.kpi_scopes.includes("ops");
/** ASM-D/E: doanh thu toàn thị trường. Owner kho/cửa hàng chờ tín hiệu từ backend (Dev 1). */
export const canViewRevenue: AccessRule = (user) => isAdmin(user) || user.kpi_scopes.includes("revenue_all");

export const PATHS = {
  login: "/login",
  noAccess: "/no-access",
  dispatcherOrders: "/dispatcher/orders",
  dispatcherPlanReview: "/dispatcher/plan-review",
  dispatcherExceptions: "/dispatcher/exceptions",
  dispatcherTracking: "/dispatcher/tracking",
  dispatcherTransfers: "/dispatcher/transfers",
  warehousePrep: "/warehouse/prep",
  warehouseAttendance: "/warehouse/attendance",
  warehouseTransfers: "/warehouse/transfers",
  storeOrders: "/store/orders",
  csOrders: "/cs/orders",
  csContacts: "/cs/contacts",
  itIntegration: "/it/integration",
  itMapping: "/it/mapping",
  itHandlingGroups: "/it/handling-groups",
  itEmployees: "/it/employees",
  itVehicles: "/it/vehicles",
  itUsers: "/it/users",
  itMarket: "/it/market",
  notifications: "/notifications",
  kpi: "/kpi",
  revenue: "/revenue",
  driver: "/driver",
} as const;

const dispatcher = anyRole("dispatcher");
const warehouse = anyRole("warehouse");

export const ROUTE_RULES: readonly { path: string; allow: AccessRule }[] = [
  { path: PATHS.dispatcherOrders, allow: dispatcher },
  { path: PATHS.dispatcherPlanReview, allow: dispatcher },
  { path: PATHS.dispatcherExceptions, allow: dispatcher },
  { path: PATHS.dispatcherTracking, allow: dispatcher },
  { path: PATHS.dispatcherTransfers, allow: dispatcher },
  { path: PATHS.warehousePrep, allow: warehouse },
  { path: PATHS.warehouseAttendance, allow: warehouse },
  { path: PATHS.warehouseTransfers, allow: warehouse },
  { path: PATHS.storeOrders, allow: anyRole("sales") },
  { path: PATHS.csOrders, allow: anyRole("customer_service") },
  { path: PATHS.csContacts, allow: anyRole("customer_service") },
  { path: PATHS.itIntegration, allow: isAdmin },
  { path: PATHS.itMapping, allow: isAdmin },
  { path: PATHS.itHandlingGroups, allow: isAdmin },
  { path: PATHS.itEmployees, allow: isAdmin },
  { path: PATHS.itVehicles, allow: isAdmin },
  { path: PATHS.itUsers, allow: isAdmin },
  { path: PATHS.itMarket, allow: isAdmin },
  { path: PATHS.notifications, allow: anyRole("admin", "dispatcher", "customer_service") }, // 03 mục 3.2
  { path: PATHS.kpi, allow: canViewKpi },
  { path: PATHS.revenue, allow: canViewRevenue },
  { path: PATHS.driver, allow: anyRole("driver") },
];

export function ruleFor(path: string): AccessRule {
  const rule = ROUTE_RULES.find((r) => r.path === path);
  if (!rule) {
    throw new Error(`No access rule registered for ${path}`);
  }
  return rule.allow;
}

/** Quy tắc cụ thể nhất (tiền tố dài nhất) áp cho cả route con, vd. /driver/trips/7. Đường dẫn lạ → false. */
export function canAccessPath(user: AuthUser, pathname: string): boolean {
  const clean = pathname.split(/[?#]/)[0].replace(/\/+$/, "") || "/";
  const match = ROUTE_RULES.filter((r) => clean === r.path || clean.startsWith(`${r.path}/`)).sort((a, b) => b.path.length - a.path.length)[0];
  return match ? match.allow(user) : false;
}

/** Màn hình sau đăng nhập (docs/07 mục 18). ASM-B: ưu tiên theo thứ tự dưới đây khi nhiều vai trò. null = không có không gian làm việc. */
export function landingPath(user: AuthUser): string | null {
  if (isAdmin(user)) return PATHS.itIntegration;
  if (user.roles.includes("dispatcher")) return PATHS.dispatcherOrders;
  if (user.roles.includes("warehouse")) return PATHS.warehousePrep;
  if (user.roles.includes("driver")) return PATHS.driver;
  if (user.roles.includes("customer_service")) return PATHS.csOrders;
  if (user.roles.includes("sales")) return PATHS.storeOrders; // ASM-C
  if (user.kpi_scopes.includes("revenue_all")) return PATHS.revenue;
  if (user.kpi_scopes.includes("ops")) return PATHS.kpi;
  return null;
}

/** Đích sau đăng nhập: quay lại trang đang vào dở nếu được phép (và là đường dẫn nội bộ), không thì màn mặc định. */
export function resolvePostLoginPath(user: AuthUser, from?: string | null): string {
  const safe = typeof from === "string" && from.startsWith("/") && !from.startsWith("//") ? from : null;
  if (safe && canAccessPath(user, safe)) {
    return safe;
  }
  return landingPath(user) ?? PATHS.noAccess;
}