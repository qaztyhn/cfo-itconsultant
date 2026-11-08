/**
 * Đối chiếu từng bucket của computeOrderCounts với docs/06 mục 5.4 (v1.4). Fixture có ngày giao, trạng thái, alert.
 * Owner: Dev 3 (luồng C).
 */
import { describe, expect, it } from "vitest";
import { computeOrderCounts, toMarketDay, type CountAlert, type CountOrder } from "./orderCounts";

const NOW = "2026-11-04T10:05:00+01:00"; // hôm nay (market) = 2026-11-04
const TZ = "Europe/Stockholm";

const order = (status: string, extra: Partial<CountOrder> = {}): CountOrder => ({ status, risk_color: null, ...extra });

const ORDERS: CountOrder[] = [
  order("SUBMITTED"),
  order("SUBMITTED"),
  order("PLANNED", { risk_color: "red" }), // có rủi ro nhưng chưa thực thi → không vào tracking_risk
  order("NO_FEASIBLE_DATE"),
  order("APPROVED", { risk_color: "green" }),
  order("PREPARING", { risk_color: "orange" }),
  order("LOADED", { risk_color: "red" }),
  order("DISPATCHED", { risk_color: "green" }),
  order("APPROVED", { risk_color: "yellow" }),
  order("DELIVERED", { risk_color: "orange", delivered_at: "2026-11-04T09:20:00+01:00" }), // giao hôm nay
  order("DELIVERED", { delivered_at: "2026-11-03T23:30:00Z" }), // = 00:30 ngày 04/11 giờ Stockholm → hôm nay
  order("DELIVERED", { delivered_at: "2026-11-03T15:00:00+01:00" }), // hôm qua → đã đóng
  order("CANCELLED", { cancelled_at: "2026-11-03T12:00:00+01:00" }), // hủy hôm qua → đã đóng
  order("CANCELLED", { cancelled_at: "2026-11-04T08:00:00+01:00" }), // hủy hôm nay → còn tính vào all
  order("BLOCKED_UNMAPPED_SKU"), // legacy
];

const ALERTS: CountAlert[] = [
  { type: "EXCEPTION", resolved_at: null }, // mở
  { type: "EXCEPTION", resolved_at: "2026-11-04T09:00:00+01:00" }, // đã xử lý
  { type: "REPLAN_SUGGESTED" }, // mở (thiếu resolved_at = chưa xử lý)
  { type: "REPLAN_SUGGESTED", resolved_at: "2026-11-04T09:30:00+01:00" }, // đã xử lý
  { type: "RISK", resolved_at: null }, // loại khác → không tính
];

describe("computeOrderCounts đối chiếu docs/06 mục 5.4", () => {
  const counts = computeOrderCounts(ORDERS, ALERTS, { now: NOW, timezone: TZ, replanSuggested: 1 });

  it("all: loại legacy và DELIVERED/CANCELLED đã đóng trước hôm nay", () => {
    // 15 đơn − 1 legacy − 1 DELIVERED hôm qua − 1 CANCELLED hôm qua = 12
    expect(counts.all).toBe(12);
  });

  it("needs_plan: chỉ SUBMITTED", () => {
    expect(counts.needs_plan).toBe(2);
  });

  it("awaiting_approval: PLANNED", () => {
    expect(counts.awaiting_approval).toBe(1);
  });

  it("no_feasible_date: NO_FEASIBLE_DATE", () => {
    expect(counts.no_feasible_date).toBe(1);
  });

  it("in_execution: gồm APPROVED, PREPARING, GOODS_READY, LOADED, DISPATCHED", () => {
    expect(counts.in_execution).toBe(5);
    expect(computeOrderCounts([order("APPROVED")], [], { now: NOW, timezone: TZ }).in_execution).toBe(1);
    expect(computeOrderCounts([order("GOODS_READY")], [], { now: NOW, timezone: TZ }).in_execution).toBe(1);
  });

  it("replan_suggested: lấy từ planning_run, mặc định 0", () => {
    expect(counts.replan_suggested).toBe(1);
    expect(computeOrderCounts(ORDERS, ALERTS, { now: NOW, timezone: TZ }).replan_suggested).toBe(0);
  });

  it("delivered_today: chỉ DELIVERED có delivered_at hôm nay theo múi giờ market", () => {
    // đơn 09:20+01 và đơn 23:30Z (00:30 giờ Stockholm); không tính đơn giao hôm qua
    expect(counts.delivered_today).toBe(2);
  });

  it("nav.order_queue: needs_plan + awaiting_approval + no_feasible_date", () => {
    expect(counts.nav.order_queue).toBe(counts.needs_plan + counts.awaiting_approval + counts.no_feasible_date);
    expect(counts.nav.order_queue).toBe(4);
  });

  it("nav.exceptions: alert mở EXCEPTION/REPLAN_SUGGESTED, không phụ thuộc trạng thái đơn", () => {
    expect(counts.nav.exceptions).toBe(2);
    expect(computeOrderCounts([order("NO_FEASIBLE_DATE")], [], { now: NOW, timezone: TZ }).nav.exceptions).toBe(0);
  });

  it("nav.tracking_risk: chỉ đơn đang thực thi có risk cam/đỏ", () => {
    // PREPARING cam + LOADED đỏ = 2; bỏ qua PLANNED đỏ và DELIVERED cam
    expect(counts.nav.tracking_risk).toBe(2);
  });
});

describe("toMarketDay", () => {
  it("tính ngày theo múi giờ market, không theo UTC", () => {
    expect(toMarketDay("2026-11-03T23:30:00Z", TZ)).toBe("2026-11-04");
    expect(toMarketDay("2026-11-04T10:05:00+01:00", TZ)).toBe("2026-11-04");
  });
});