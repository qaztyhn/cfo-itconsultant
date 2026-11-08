/**
 * Tính GET /orders/counts đúng docs/06 mục 5.4 (v1.4). Hàm thuần để test từng bucket với fixture.
 * "Hôm nay" theo ref.market.timezone (docs/05 mục 1), không theo múi giờ trình duyệt.
 * Owner: Dev 3 (luồng C).
 */

export interface CountOrder {
  status: string;
  risk_color: string | null;
  /** ISO timestamp; có khi status = DELIVERED. */
  delivered_at?: string | null;
  /** ISO timestamp; có khi status = CANCELLED. */
  cancelled_at?: string | null;
}

export interface CountAlert {
  type: string;
  /** Alert mở ⇔ resolved_at rỗng (docs/06 mục 7, GET /alerts?resolved=false). */
  resolved_at?: string | null;
}

export interface OrderCounts {
  all: number;
  needs_plan: number;
  awaiting_approval: number;
  no_feasible_date: number;
  in_execution: number;
  replan_suggested: number;
  delivered_today: number;
  nav: { order_queue: number; exceptions: number; tracking_risk: number };
}

export interface CountOptions {
  /** Thời điểm "bây giờ" (ISO). */
  now: string;
  /** IANA timezone của market, ví dụ "Europe/Stockholm". */
  timezone: string;
  /**
   * Số planning_run kind='replan_suggestion' chưa được duyệt/giữ nguyên.
   * DEPENDENCY: mock chưa có planning_run nên truyền vào; mặc định 0.
   */
  replanSuggested?: number;
}

const IN_EXECUTION = ["APPROVED", "PREPARING", "GOODS_READY", "LOADED", "DISPATCHED"];
const OPEN_ALERT_TYPES = ["EXCEPTION", "REPLAN_SUGGESTED"];

/** Ngày nghiệp vụ YYYY-MM-DD của một thời điểm, theo timezone market. */
export function toMarketDay(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(iso),
  );
}

export function computeOrderCounts(orders: CountOrder[], alerts: CountAlert[], options: CountOptions): OrderCounts {
  const today = toMarketDay(options.now, options.timezone);
  const closedDay = (o: CountOrder): string | null => {
    const at = o.status === "DELIVERED" ? o.delivered_at : o.status === "CANCELLED" ? o.cancelled_at : null;
    return at ? toMarketDay(at, options.timezone) : null;
  };
  const byStatus = (status: string) => orders.filter((o) => o.status === status).length;

  // `all`: bỏ BLOCKED_UNMAPPED_SKU legacy và đơn DELIVERED/CANCELLED đã đóng trước hôm nay.
  const all = orders.filter((o) => {
    if (o.status === "BLOCKED_UNMAPPED_SKU") return false;
    const day = closedDay(o);
    return !(day !== null && day < today);
  }).length;

  const needsPlan = byStatus("SUBMITTED");
  const awaitingApproval = byStatus("PLANNED");
  const noFeasibleDate = byStatus("NO_FEASIBLE_DATE");

  return {
    all,
    needs_plan: needsPlan,
    awaiting_approval: awaitingApproval,
    no_feasible_date: noFeasibleDate,
    in_execution: orders.filter((o) => IN_EXECUTION.includes(o.status)).length,
    replan_suggested: options.replanSuggested ?? 0,
    delivered_today: orders.filter((o) => o.status === "DELIVERED" && closedDay(o) === today).length,
    nav: {
      order_queue: needsPlan + awaitingApproval + noFeasibleDate,
      exceptions: alerts.filter((a) => OPEN_ALERT_TYPES.includes(a.type) && !a.resolved_at).length,
      tracking_risk: orders.filter(
        (o) => IN_EXECUTION.includes(o.status) && (o.risk_color === "orange" || o.risk_color === "red"),
      ).length,
    },
  };
}