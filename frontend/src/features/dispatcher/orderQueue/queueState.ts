/**
 * Trạng thái bộ lọc của Order Queue nằm trên URL (trừ `q`, để số điện thoại/tên khách không vào lịch sử trình duyệt).
 * Mọi giá trị lạ trên URL rơi về mặc định. Đây là bộ lọc hiển thị gửi cho SERVER, không phải kiểm soát truy cập.
 */
import { PAGE_SIZES, type QueueQuery, type QueueSort } from "./api";
import type { RiskColor } from "./model";

export const BUCKETS = ["active", "needs_plan", "awaiting_approval", "no_feasible_date", "in_execution"] as const;
export type Bucket = (typeof BUCKETS)[number];
export const DEFAULT_BUCKET: Bucket = "active";
export const DEFAULT_PAGE_SIZE = 50;
export const MAX_SEARCH_LENGTH = 100;

/** Không gồm BLOCKED_UNMAPPED_SKU (legacy, ASM-005). */
export const STATUS_OPTIONS = ["SUBMITTED", "PLANNED", "NO_FEASIBLE_DATE", "APPROVED", "PREPARING",
  "GOODS_READY", "LOADED", "DISPATCHED", "DELIVERED", "FAILED", "CANCELLED"] as const;

export const BUCKET_STATUSES: Record<Bucket, readonly string[]> = {
  active: ["SUBMITTED", "PLANNED", "NO_FEASIBLE_DATE", "APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED", "FAILED"],
  needs_plan: ["SUBMITTED"],
  awaiting_approval: ["PLANNED"],
  no_feasible_date: ["NO_FEASIBLE_DATE"],
  in_execution: ["APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED"],
};
export const RISK_OPTIONS: readonly RiskColor[] = ["green", "yellow", "orange", "red"];
export const SORT_OPTIONS: readonly QueueSort[] = ["submitted_at", "date_to", "promise_end", "committed_date", "order_no", "status"];

export interface QueueState {
  bucket: Bucket;
  /** Một trạng thái cụ thể; nếu có thì ghi đè bucket. */
  status: string | null;
  risk: RiskColor | null;
  from: string | null;
  to: string | null;
  /** null = FIFO mặc định của server (submitted_at ASC, id ASC). */
  sort: QueueSort | null;
  desc: boolean;
  page: number;
  pageSize: number;
}

function pick<T extends string>(list: readonly T[], value: string | null): T | null {
  return value !== null && (list as readonly string[]).includes(value) ? (value as T) : null;
}
function validDate(value: string | null): string | null {
  if (value === null || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value ? value : null;
}
function positiveInt(value: string | null): number | null {
  if (value === null || !/^\d{1,6}$/.test(value)) return null;
  const parsed = Number(value);
  return parsed >= 1 ? parsed : null;
}

export function parseQueueState(params: URLSearchParams): QueueState {
  const sort = pick(SORT_OPTIONS, params.get("sort"));
  const size = positiveInt(params.get("page_size"));
  return {
    bucket: pick(BUCKETS, params.get("bucket")) ?? DEFAULT_BUCKET,
    status: pick(STATUS_OPTIONS, params.get("status")),
    risk: pick(RISK_OPTIONS, params.get("risk")),
    from: validDate(params.get("from")),
    to: validDate(params.get("to")),
    sort,
    desc: sort !== null && params.get("desc") === "1",
    page: positiveInt(params.get("page")) ?? 1,
    pageSize: size !== null && (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_PAGE_SIZE,
  };
}

export function isDateRangeInvalid(state: QueueState): boolean {
  return state.from !== null && state.to !== null && state.from > state.to;
}

export function toQueueQuery(state: QueueState, search = ""): QueueQuery {
  const rangeOk = !isDateRangeInvalid(state);
  const text = search.trim().slice(0, MAX_SEARCH_LENGTH);
  return {
    q: text || undefined,
    status: (state.status ? [state.status] : BUCKET_STATUSES[state.bucket]).join(","),
    riskColor: state.risk ?? undefined,
    committedFrom: rangeOk ? state.from ?? undefined : undefined,
    committedTo: rangeOk ? state.to ?? undefined : undefined,
    sort: state.sort ?? undefined,
    descending: state.sort ? state.desc : undefined,
    page: state.page,
    pageSize: state.pageSize,
  };
}

/** Đổi bộ lọc: về trang 1 trừ khi đổi chính `page`; chọn bucket xóa status và ngược lại; bỏ giá trị mặc định khỏi URL. */
export function updateParams(current: URLSearchParams, changes: Record<string, string | null>): URLSearchParams {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(changes)) {
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
  }
  if (changes.bucket) next.delete("status");
  if (changes.status) next.delete("bucket");
  if (!("page" in changes)) next.delete("page");
  if (next.get("bucket") === DEFAULT_BUCKET) next.delete("bucket");
  if (next.get("page") === "1") next.delete("page");
  if (next.get("page_size") === String(DEFAULT_PAGE_SIZE)) next.delete("page_size");
  if (next.get("desc") === "0") next.delete("desc");
  return next;
}