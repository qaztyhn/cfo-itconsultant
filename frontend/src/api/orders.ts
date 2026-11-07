/**
 * Lời gọi đơn hàng (docs/06 mục 5). Owner: Dev 3 (luồng C) — M0.
 * DEPENDENCY: kiểu BadgeCounts mượn tạm từ menu.ts (phần của /orders/counts mà sidebar cần); thay bằng kiểu sinh từ OpenAPI khi có schema.d.ts.
 */
import type { BadgeCounts } from "../app/menu";
import { apiGet } from "./client";

export function fetchOrderCounts(signal?: AbortSignal): Promise<BadgeCounts> {
  return apiGet<BadgeCounts>("/orders/counts", undefined, signal);
}