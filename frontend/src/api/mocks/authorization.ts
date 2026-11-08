/**
 * Mô phỏng xác thực + phân quyền + lọc trường của backend cho MSW (docs/06 mục 3, 5.2, 5.3, 9).
 * Mock này chỉ phục vụ UI demo/test: nó KHÔNG chứng minh API thật đã bảo vệ dữ liệu (09: server kiểm quyền mọi endpoint).
 * Owner: Dev 3 (luồng C).
 */
import type { AuthUser, UserRole } from "../contracts/auth";
import { accountFromRequest, errorResponse, type MockAccount } from "./authHandlers";
import type { OrderListItem, OrderRecord } from "./orderList";

export type AuthResult = { ok: true; account: MockAccount } | { ok: false; response: Response };

/** Quyền đọc đơn theo docs/06 mục 5.2: `viewer` → 403. */
export const ORDER_READ_ROLES: readonly UserRole[] = ["admin", "dispatcher", "warehouse", "sales", "driver", "customer_service"];
/** GPS: xem chỉ dispatcher (docs/06 mục 3, mục 9; 09 bất biến 4). */
export const GPS_READ_ROLES: readonly UserRole[] = ["dispatcher"];

/** Không token/sai token → 401 AUTH_INVALID; vai trò không được phép → 403 FORBIDDEN. */
export function authorize(request: Request, allowed: readonly UserRole[]): AuthResult {
  const account = accountFromRequest(request);
  if (!account) {
    return { ok: false, response: errorResponse(request, 401, "AUTH_INVALID", "Not signed in or token expired.") };
  }
  if (!account.user.roles.some((r) => allowed.includes(r))) {
    return { ok: false, response: errorResponse(request, 403, "FORBIDDEN", "Your role cannot access this resource.") };
  }
  return { ok: true, account };
}

/** MOCK: seed chưa có quan hệ tài xế ↔ chuyến; driver1@ (user id 4) chỉ có chuyến của đơn 129. */
const DRIVER_ORDER_IDS: Record<number, readonly number[]> = { 4: [129] };

/** Phạm vi đơn theo docs/06 mục 5.2 (market mock là SE nên admin/dispatcher/CS thấy mọi đơn CFO). */
export function orderInScope(user: AuthUser, order: OrderRecord): boolean {
  const roles = user.roles;
  if (roles.some((r) => r === "admin" || r === "dispatcher" || r === "customer_service")) return true;
  if (roles.includes("warehouse") && order.warehouse !== null && user.location_ids.includes(order.warehouse.id)) return true;
  if (roles.includes("sales") && order.origin_store !== null && user.location_ids.includes(order.origin_store.id)) return true;
  if (roles.includes("driver") && (DRIVER_ORDER_IDS[user.id] ?? []).includes(order.id)) return true;
  return false;
}

type ViewLevel = "full" | "standard" | "driver";

/** Nhiều vai trò → lấy mức xem rộng nhất. full = admin/dispatcher/warehouse; standard = sales/CS; driver = chỉ driver. */
function viewLevel(user: AuthUser): ViewLevel {
  if (user.roles.some((r) => r === "admin" || r === "dispatcher" || r === "warehouse")) return "full";
  if (user.roles.some((r) => r === "sales" || r === "customer_service")) return "standard";
  return "driver";
}

function omit<T extends object>(obj: T, keys: readonly string[]): Partial<T> {
  return Object.fromEntries(Object.entries(obj).filter(([k]) => !keys.includes(k))) as Partial<T>;
}

/** docs/06 mục 5.4: trường bị cấm theo mục 5.3 thì BỎ HẲN (không trả null). Driver không có `date_request` vì mock chưa có `window`. */
const DRIVER_LIST_OMIT = ["origin_store", "block_reason", "total_amount", "currency", "risk_color", "date_request"] as const;

export function projectOrderListItem(user: AuthUser, item: OrderListItem): Partial<OrderListItem> {
  return viewLevel(user) === "driver" ? omit(item, DRIVER_LIST_OMIT) : item;
}

/** Chi tiết đơn (seed thô) theo docs/06 mục 5.3. */
const STANDARD_DETAIL_OMIT = ["approved_plan_id", "total_kg", "total_m3"] as const;
const DRIVER_DETAIL_OMIT = [
  ...STANDARD_DETAIL_OMIT, "risk_color", "risk_status", "earliest_feasible_date", "date_mode", "date_from", "date_to",
] as const;

export function projectOrderDetail<T extends object>(user: AuthUser, order: T): Partial<T> {
  const level = viewLevel(user);
  if (level === "full") return order;
  return omit(order, level === "standard" ? STANDARD_DETAIL_OMIT : DRIVER_DETAIL_OMIT);
}