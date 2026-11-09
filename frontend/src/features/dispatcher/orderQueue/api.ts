/**
 * Order Queue API (docs/06 mục 5.4): GET /orders, GET /orders/counts.
 * Lọc, sắp xếp, phân trang do SERVER thực hiện; frontend không dùng lọc cục bộ làm biện pháp bảo mật.
 * Không ghi giá trị tìm kiếm `q` ra log/console (docs/09 mục 10, DEC-CS-SEARCH).
 */
import { apiGet, type QueryParams } from "../../../api/client";
import { projectCounts, projectPage, type QueueCounts, type QueuePage } from "./model";

export const PAGE_SIZES = [25, 50, 100] as const;
export type QueueSort = "submitted_at" | "date_to" | "promise_end" | "committed_date" | "order_no" | "status";

export interface QueueQuery {
  q?: string;
  /** Một hoặc nhiều trạng thái, phân tách bằng dấu phẩy (đúng hợp đồng backend). */
  status?: string;
  riskColor?: string;
  committedFrom?: string;
  committedTo?: string;
  warehouseId?: number;
  /** Bỏ trống = mặc định FIFO của server: submitted_at ASC, id ASC. */
  sort?: QueueSort;
  descending?: boolean;
  page: number;
  pageSize: number;
}

export function buildQueueParams(query: QueueQuery): QueryParams {
  const search = query.q?.trim();
  return {
    status: query.status,
    risk_color: query.riskColor,
    committed_date_from: query.committedFrom,
    committed_date_to: query.committedTo,
    warehouse_id: query.warehouseId,
    q: search ? search : undefined,
    sort: query.sort ? `${query.descending ? "-" : ""}${query.sort}` : undefined,
    page: query.page,
    page_size: query.pageSize,
    // Đơn legacy BLOCKED_UNMAPPED_SKU không thuộc hàng đợi CFO (ASM-005). Chỉ là bộ lọc hiển thị.
    blocked: false,
  };
}

export async function fetchOrderQueue(query: QueueQuery, signal?: AbortSignal): Promise<QueuePage> {
  const raw = await apiGet<unknown>("/orders", buildQueueParams(query), signal);
  return projectPage(raw, query.page, query.pageSize);
}

/** null = phản hồi không đúng hợp đồng; UI hiện lỗi chứ không tự điền số 0. */
export async function fetchQueueCounts(signal?: AbortSignal): Promise<QueueCounts | null> {
  return projectCounts(await apiGet<unknown>("/orders/counts", undefined, signal));
}