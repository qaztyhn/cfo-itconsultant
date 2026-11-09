/**
 * Hiển thị một hàng Order Queue. Thuần logic, không suy diễn: thiếu dữ liệu thì trả "Not available".
 */
import { PATHS } from "../../../app/access";
import type { QueueOrder } from "./model";

export interface Destination { to: string; label: string }

const IN_EXECUTION = new Set(["APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED"]);

/**
 * Chỉ tới màn DANH SÁCH: Plan Review cần runId và Tracking chưa có chi tiết theo đơn, nên không đoán id.
 * SUBMITTED và FAILED không có đích được tài liệu xác định.
 */
export function destinationFor(order: Pick<QueueOrder, "status">): Destination | null {
  if (order.status === "PLANNED") return { to: PATHS.dispatcherPlanReview, label: "Plan review" };
  if (order.status === "NO_FEASIBLE_DATE") return { to: PATHS.dispatcherExceptions, label: "Exceptions" };
  if (IN_EXECUTION.has(order.status)) return { to: PATHS.dispatcherTracking, label: "Tracking" };
  return null;
}

export function requestedLabel(order: Pick<QueueOrder, "dateMode" | "dateFrom" | "dateTo">): string {
  const { dateMode, dateFrom, dateTo } = order;
  if (dateMode === "exact" && (dateTo ?? dateFrom)) return (dateTo ?? dateFrom) as string;
  if (dateMode === "range" && dateFrom && dateTo) return `${dateFrom} → ${dateTo}`;
  if (dateMode === "latest" && dateTo) return `By ${dateTo}`;
  return "Not available";
}

export function warehouseLabel(order: Pick<QueueOrder, "warehouse">): string {
  if (!order.warehouse) return "No source yet";
  return order.warehouse.code ?? `Warehouse #${order.warehouse.id}`;
}

export function customerSite(order: Pick<QueueOrder, "customer" | "site">): { customer: string; site: string } {
  return { customer: order.customer ?? "Customer unavailable", site: order.site ?? "Site unavailable" };
}