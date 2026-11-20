/**
 * MSW handlers mô phỏng API (docs/08 mục 2) với dữ liệu khớp seed (SE-2026-000123, 137, 141…) để frontend
 * không phải chờ backend. Owner: Dev 3 (luồng C) — M0..M4.
 */
import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "../config";
import { computeOrderCounts } from "./orderCounts";
import { listOrders, type OrderRecord, type RefCode } from "./orderList";

// Dùng chung API_BASE_URL (đã gồm /api/v1) để dev:mock hoạt động với mọi cấu hình VITE_API_URL.
const BASE = API_BASE_URL;
// /health nằm ở gốc host, không thuộc /api/v1.
const ORIGIN = API_BASE_URL.replace(/\/api\/v1$/, "");

// ─── Seed data ───────────────────────────────────────────────────────────────

const ORDERS = [
  {
    id: 123,
    order_no: "SE-2026-000123",
    status: "PLANNED",
    customer_name: "Nordbygg Entreprenad AB",
    site_name: "Kungsbacka",
    site_address: "Storgatan 12, 434 30 Kungsbacka",
    date_mode: "exact",
    date_from: "2026-11-10",
    date_to: "2026-11-10",
    window_start: "08:00",
    window_end: "14:30",
    total_lines: 4,
    total_kg: 4120,
    total_m3: 9.6,
    warehouse_code: "GBG",
    risk_color: null,
    risk_status: null,
    approved_plan_id: null,
    created_at: "2026-11-04T07:30:00+01:00",
  },
  {
    id: 137,
    order_no: "SE-2026-000137",
    status: "NO_FEASIBLE_DATE",
    customer_name: "Skånska Kakel & Klinker AB",
    site_name: "Lund",
    site_address: "Malmövägen 5, 221 00 Lund",
    date_mode: "exact",
    date_from: "2026-11-09",
    date_to: "2026-11-09",
    window_start: "07:00",
    window_end: "15:00",
    total_lines: 3,
    total_kg: 2800,
    total_m3: 7.2,
    warehouse_code: null,
    risk_color: null,
    risk_status: null,
    approved_plan_id: null,
    earliest_feasible_date: "2026-11-12",
    created_at: "2026-11-04T08:00:00+01:00",
  },
  {
    id: 141,
    order_no: "SE-2026-000141",
    status: "PREPARING",
    customer_name: "Uppsala Takservice AB",
    site_name: "Uppsala",
    site_address: "Fyrisgatan 20, 753 20 Uppsala",
    date_mode: "exact",
    date_from: "2026-11-04",
    date_to: "2026-11-04",
    window_start: "10:00",
    window_end: "12:30",
    total_lines: 5,
    total_kg: 3200,
    total_m3: 8.1,
    warehouse_code: "STO",
    risk_color: "orange",
    risk_status: "PREDICTED_LATE",
    approved_plan_id: 141,
    created_at: "2026-11-03T09:00:00+01:00",
  },
  {
    id: 138,
    order_no: "SE-2026-000138",
    status: "LOADED",
    customer_name: "Mälardalens Golv AB",
    site_name: "Västerås",
    site_address: "Eriksgatan 3, 722 12 Västerås",
    date_mode: "exact",
    date_from: "2026-11-04",
    date_to: "2026-11-04",
    window_start: "13:00",
    window_end: "16:00",
    total_lines: 4,
    total_kg: 2900,
    total_m3: 6.5,
    warehouse_code: "STO",
    risk_color: "yellow",
    risk_status: "AT_RISK",
    approved_plan_id: 138,
    created_at: "2026-11-03T10:00:00+01:00",
  },
  {
    id: 129,
    order_no: "SE-2026-000129",
    status: "DISPATCHED",
    customer_name: "Privatperson Malmö",
    site_name: "Malmö",
    site_address: "Östra Förstadsgatan 4, 211 28 Malmö",
    date_mode: "exact",
    date_from: "2026-11-04",
    date_to: "2026-11-04",
    window_start: "12:00",
    window_end: "18:00",
    total_lines: 2,
    total_kg: 1200,
    total_m3: 3.0,
    warehouse_code: "MLM",
    risk_color: "green",
    risk_status: "ON_TRACK",
    approved_plan_id: 129,
    created_at: "2026-11-03T11:00:00+01:00",
  },
  {
    id: 131,
    order_no: "SE-2026-000131",
    status: "APPROVED",
    customer_name: "Öresund Fastighetsservice AB",
    site_name: "Helsingborg",
    site_address: "Stortorget 1, 251 00 Helsingborg",
    date_mode: "exact",
    date_from: "2026-11-05",
    date_to: "2026-11-05",
    window_start: "07:00",
    window_end: "11:00",
    total_lines: 6,
    total_kg: 5100,
    total_m3: 12.3,
    warehouse_code: "MLM",
    risk_color: "green",
    risk_status: "ON_TRACK",
    approved_plan_id: 131,
    created_at: "2026-11-03T08:00:00+01:00",
  },
  {
    id: 144,
    order_no: "SE-2026-000144",
    status: "NO_FEASIBLE_DATE",
    customer_name: "Nordic Ställning AB",
    site_name: "Södertälje",
    site_address: "Industrivägen 15, 151 38 Södertälje",
    date_mode: "exact",
    date_from: "2026-11-06",
    date_to: "2026-11-06",
    window_start: "06:30",
    window_end: "10:00",
    total_lines: 3,
    total_kg: 11000,
    total_m3: 24.0,
    warehouse_code: null,
    risk_color: null,
    risk_status: null,
    approved_plan_id: null,
    created_at: "2026-11-04T06:00:00+01:00",
  },
  {
    id: 160,
    order_no: "SE-2026-000160",
    status: "PLANNED",
    customer_name: "Göta Renovering AB",
    site_name: "Borås",
    site_address: "Fristadbron 10, 503 30 Borås",
    date_mode: "exact",
    date_from: "2026-11-05",
    date_to: "2026-11-05",
    window_start: "07:00",
    window_end: "15:00",
    total_lines: 8,
    total_kg: 20000,
    total_m3: 38.5,
    warehouse_code: "GBG",
    risk_color: null,
    risk_status: null,
    approved_plan_id: null,
    vehicle_count: 2,
    created_at: "2026-11-04T07:00:00+01:00",
  },
  {
    id: 118,
    order_no: "SE-2026-000118",
    status: "DELIVERED",
    customer_name: "Göta Renovering AB",
    site_name: "Borås",
    site_address: "Fristadbron 10, 503 30 Borås",
    date_mode: "exact",
    date_from: "2026-11-04",
    date_to: "2026-11-04",
    window_start: "07:00",
    window_end: "15:00",
    total_lines: 4,
    total_kg: 3600,
    total_m3: 9.0,
    warehouse_code: "GBG",
    risk_color: "green",
    risk_status: "ON_TRACK",
    approved_plan_id: 118,
    delivered_at: "2026-11-04T09:20:00+01:00",
    created_at: "2026-11-03T07:00:00+01:00",
  },
];

export const LEGACY_ORDERS = [{
    id: 156,
    order_no: "SE-2026-000156",
    status: "BLOCKED_UNMAPPED_SKU",
    customer_name: "—",
    site_name: "—",
    site_address: "—",
    date_mode: "exact",
    date_from: null,
    date_to: null,
    window_start: null,
    window_end: null,
    total_lines: 2,
    total_kg: 500,
    total_m3: 1.5,
    warehouse_code: null,
    risk_color: null,
    risk_status: null,
    approved_plan_id: null,
    created_at: "2026-11-04T09:00:00+01:00",
  },
];

// Mốc "bây giờ" của dữ liệu demo (khớp APP_NOW trong .env.example và data_as_of của integration overview).
// Cố định để delivered_today không tự về 0 khi đồng hồ thật qua ngày.
const MOCK_NOW = "2026-11-04T10:05:00+01:00";
const MARKET_TIMEZONE = "Europe/Stockholm"; // ref.market.timezone (docs/05)

// Danh sách đơn theo docs/06 mục 5.4 (v1.4): dựng từ seed ORDERS. Trường seed chưa có là giá trị MOCK, ghi rõ bên dưới.
const WAREHOUSE_REFS: Record<string, RefCode> = {
  GBG: { id: 1, code: "GBG" },
  STO: { id: 2, code: "STO" },
  MLM: { id: 3, code: "MLM" },
}; // id khớp GET /locations của mock
const ORIGIN_STORE: RefCode = { id: 101, code: "GBG-V" }; // MOCK: id 101 theo location_ids của tài khoản Sales; mã theo ví dụ docs/06 mục 5.4
const ORDER_AMOUNTS: Record<number, string> = {
  123: "48300.00",
  137: "31200.00",
  141: "22750.00",
  138: "15400.00",
  129: "67800.00",
  131: "12950.00",
  144: "9800.00",
  160: "18600.00",
  118: "25300.00",
}; // MOCK: seed chưa có tiền

const ORDER_RECORDS: OrderRecord[] = ORDERS.map((o) => ({
  id: o.id,
  order_no: o.order_no,
  external_ref: `POS-${o.id}`, // MOCK
  status: o.status,
  customer_name: o.customer_name,
  site: (o.site_address.split(",").pop() ?? "").trim(), // docs/06: phần sau dấu phẩy cuối của delivery_address
  warehouse: o.warehouse_code ? (WAREHOUSE_REFS[o.warehouse_code] ?? null) : null,
  origin_store: ORIGIN_STORE,
  date_request: { mode: o.date_mode, date_from: o.date_from, date_to: o.date_to },
  // Đơn đã có kế hoạch được duyệt thì có ngày cam kết và hạn hứa; suy ra từ ngày/giờ yêu cầu của seed.
  committed_date: o.approved_plan_id !== null ? o.date_from : null,
  promise_end: o.approved_plan_id !== null ? `${o.date_to}T${o.window_end}:00+01:00` : null,
  risk_color: o.risk_color,
  block_reason: null,
  total_amount: ORDER_AMOUNTS[o.id] ?? "0.00",
  currency: "SEK",
  submitted_at: o.created_at, // MOCK: seed chưa tách submitted_at khỏi created_at
}));

const ALERTS = [
  {
    id: 1,
    type: "RISK",
    level: "critical",
    message: "SE-2026-000141 · ETA 13:15 vs site closes 12:30",
    detail: "Goods ready not recorded; planning assumes now. Drive 65 min → forecast 13:15.",
    order_id: 141,
    created_at: "2026-11-04T10:00:00+01:00",
    acknowledged_at: null,
  },
  {
    id: 2,
    type: "RISK",
    level: "warning",
    message: "SE-2026-000138 · loading 25 min late, slack 34 min",
    detail: "LOADED at 12:40 vs plan 12:15. Drive to Västerås 90 min. Window closes 16:00.",
    order_id: 138,
    created_at: "2026-11-04T10:30:00+01:00",
    acknowledged_at: null,
  },
    {
    id: 3,
    type: "EXCEPTION",
    level: "warning",
    message: "SE-2026-000137 · no feasible delivery date before 2026-11-12",
    detail: "Planning found no feasible date for the requested day; earliest feasible date is 2026-11-12.",
    order_id: 137,
    created_at: "2026-11-04T08:05:00+01:00",
    acknowledged_at: null,
    resolved_at: null,
  },
  {
    id: 4,
    type: "EXCEPTION",
    level: "warning",
    message: "SE-2026-000144 · no feasible delivery date",
    detail: "Planning found no feasible delivery date for this order.",
    order_id: 144,
    created_at: "2026-11-04T07:05:00+01:00",
    acknowledged_at: null,
    resolved_at: null,
  },
];

const INTEGRATION_OVERVIEW = {
  sources: [
    { name: "POS orders", status: "ok", rows: 42, rejected: 0, data_as_of: "2026-11-04T10:05:00+01:00", interval_min: 5 },
    { name: "WMS stock", status: "ok", rows: 1823, rejected: 0, data_as_of: "2026-11-04T10:05:00+01:00", interval_min: 5 },
    { name: "WMS inbound", status: "ok", rows: 14, rejected: 0, data_as_of: "2026-11-04T10:05:00+01:00", interval_min: 5 },
    { name: "ERP products", status: "ok", rows: 100, rejected: 0, unmapped: 3, data_as_of: "2026-11-04T10:00:00+01:00", interval_min: 5 },
    { name: "Fleet calendar", status: "ok", rows: 10, rejected: 0, data_as_of: "2026-11-04T10:04:00+01:00", interval_min: 5 },
  ],
  next_sync_at: "2026-11-04T10:10:00+01:00",
  stale: false,
};

const PREP_QUEUE = [
  {
    id: 146,
    order_no: "SE-2026-000146",
    total_lines: 5,
    total_kg: 3340,
    handling_mix: [{ code: "N2", name: "Boards, sheets & tiles" }, { code: "N3", name: "Bagged cement & mortar" }],
    work_min: 126,
    prep_window_start: "06:00",
    prep_window_end: "08:06",
    loading_at: "2026-11-04T08:30:00+01:00",
    loading_vehicle: "GBG-12-03",
    loading_after_cutoff: false,
    status: "APPROVED",
    vehicles: [{ vehicle_code: "GBG-12-03", vehicle_type: "Truck 12 t" }],
  },
  {
    id: 149,
    order_no: "SE-2026-000149",
    total_lines: 7,
    total_kg: 5200,
    handling_mix: [{ code: "N5", name: "Long goods" }],
    work_min: 210,
    prep_window_start: "06:00",
    prep_window_end: "09:30",
    loading_at: "2026-11-04T10:00:00+01:00",
    loading_vehicle: "GBG-18-01",
    loading_after_cutoff: false,
    status: "PREPARING",
    crew_size: 4,
    vehicles: [{ vehicle_code: "GBG-18-01", vehicle_type: "Truck 18 t" }],
  },
  {
    id: 150,
    order_no: "SE-2026-000150",
    total_lines: 2,
    total_kg: 980,
    handling_mix: [{ code: "N1", name: "Small items & accessories" }],
    work_min: 45,
    prep_window_start: "09:30",
    prep_window_end: "10:15",
    loading_at: "2026-11-04T10:30:00+01:00",
    loading_vehicle: "GBG-03-02",
    loading_after_cutoff: false,
    status: "GOODS_READY",
    vehicles: [{ vehicle_code: "GBG-03-02", vehicle_type: "Van 3.5 t" }],
  },
  {
    id: 155,
    order_no: "SE-2026-000155",
    total_lines: 4,
    total_kg: 2800,
    handling_mix: [{ code: "N3", name: "Bagged cement & mortar" }],
    work_min: 70,
    prep_window_start: "13:00",
    prep_window_end: "14:10",
    loading_at: "2026-11-05T06:00:00+01:00",
    loading_vehicle: "GBG-26-01",
    loading_after_cutoff: true,
    status: "APPROVED",
    vehicles: [{ vehicle_code: "GBG-26-01", vehicle_type: "Truck 26 t" }],
  },
];

const CAPACITY_TODAY = {
  warehouse_id: 1,
  date: "2026-11-04",
  total_min: 5292,
  booked_min: 4600,
  free_min: 692,
  shifts: [
    { name: "Shift 1", start: "06:00", end: "14:00", present_staff: 8, useful_hours: 7.0, capacity_min: 3024 },
    { name: "Shift 2", start: "14:00", end: "22:00", present_staff: 6, useful_hours: 7.0, capacity_min: 2268 },
  ],
  cutoff: "15:00",
};

const KPI_SUMMARY = {
  period_label: "Demo week 3–9 Nov",
  orders_closed: 48,
  planning_time_min: 3.2,
  planning_time_baseline_min: 15,
  on_time_pct: 92,
  labour_per_delivery_h: 9.8,
  labour_baseline_h: 11.2,
  distance_per_delivery_km: 31.4,
  distance_baseline_km: 42.1,
  prep_error_min: 11,
  eta_error_min: 14,
  plan_acceptance_pct: 81,
  alternatives_chosen: 7,
  manual_plans: 2,
  failed_delivery_rate_pct: 2.1,
  capacity_utilisation_pct: 78,
  hard_constraint_violations: 0,
  alert_latency_ms_p50: 4000,
};

const DECISION_LOG = [
  {
    id: 1,
    created_at: "2026-11-04T09:45:00+01:00",
    actor_name: "Anna Lindqvist",
    action: "PLAN_APPROVED",
    entity: "fulfilment_plan",
    entity_id: 123,
    order_no: "SE-2026-000123",
    reason_text: null,
  },
  {
    id: 2,
    created_at: "2026-11-04T09:30:00+01:00",
    actor_name: "Anna Lindqvist",
    action: "ALT_SELECTED",
    entity: "fulfilment_plan",
    entity_id: 131,
    order_no: "SE-2026-000131",
    reason_text: "MLM closer to delivery site, lower distance score.",
  },
  {
    id: 3,
    created_at: "2026-11-04T08:00:00+01:00",
    actor_name: "Erik Svensson",
    action: "MAPPING_CONFIRMED",
    entity: "product_mapping",
    entity_id: 55,
    order_no: null,
    reason_text: null,
  },
];

const NOTIFICATIONS = [
  {
    id: 1,
    template: "CONFIRMED",
    channel: "email",
    status: "sent",
    sent_at: "2026-11-04T09:46:00+01:00",
    order_no: "SE-2026-000123",
    customer_name_masked: "N••••••• E••••••••• AB",
    to_masked: "n•••@nordbygg.se",
    subject: "Your delivery is confirmed — order SE-2026-000123",
    body_preview: "Your delivery is planned for Tue 10 Nov, 08:00–14:30.",
  },
  {
    id: 2,
    template: "DISPATCHED",
    channel: "sms",
    status: "sent",
    sent_at: "2026-11-04T10:52:00+01:00",
    order_no: "SE-2026-000129",
    customer_name_masked: "P••••••••• M••••",
    to_masked: "+46 •• ••• 56 78",
    subject: null,
    body_preview: "CFO demo: order SE-2026-000129 has left Malmö DC. Expected arrival 13:10–13:40.",
  },
  {
    id: 3,
    template: "DELAY",
    channel: "email",
    status: "draft",
    sent_at: null,
    order_no: "SE-2026-000141",
    customer_name_masked: "U••••• T••••••••• AB",
    to_masked: "u•••@takservice.demo",
    subject: "Delivery update for order SE-2026-000141",
    body_preview: "Your delivery is running later than planned. We now expect to arrive between 13:00 and 13:30 today.",
    new_window_start: "13:00",
    new_window_end: "13:30",
  },
  {
    id: 4,
    template: "DELIVERED",
    channel: "email",
    status: "sent",
    sent_at: "2026-11-04T09:15:00+01:00",
    order_no: "SE-2026-000118",
    customer_name_masked: "G••• R••••••••• AB",
    to_masked: "g•••@gotarenovering.se",
    subject: "Your order was delivered",
    body_preview: "Delivered at 09:12, received by Björn Eriksson.",
  },
  {
    id: 5,
    template: "CONFIRMED",
    channel: "email",
    status: "suppressed",
    sent_at: null,
    order_no: "SE-2026-000138",
    customer_name_masked: "M•••••••••• G••• AB",
    to_masked: "m•••@malardalensgolv.se",
    subject: "Delivery update for order SE-2026-000138",
    body_preview: "ETA moved < 30 min from last notified window. Suppressed per BR-NOT-02.",
    suppressed_reason: "delta_lt_30min",
  },
];

const DRIVER_TRIPS = [
  {
    id: 1,
    order_id: 129,
    order_no: "SE-2026-000129",
    status: "LOADED",
    vehicle_code: "MLM-12-02",
    site_name: "Malmö",
    site_address: "Östra Förstadsgatan 4, 211 28 Malmö",
    customer_name: "Privatperson Malmö",
    window_start: "12:00",
    window_end: "18:00",
    drive_min: 25,
    total_lines: 2,
    loading_at: "2026-11-04T11:30:00+01:00",
    depart_at: "2026-11-04T12:00:00+01:00",
    eta_at: "2026-11-04T12:25:00+01:00",
    receiving_note: "Ring doorbell at gate.",
  },
];

const REVENUE_SUMMARY = {
  period_start: "2026-10-05",
  period_end: "2026-11-04",
  recognised_sek: "1284500",
  booked_sek: "487200",
  orders_delivered: 48,
  avg_order_value_sek: "26760",
  share_of_market_pct: "12.4",
  currency: "SEK",
};

const REVENUE_DAILY = Array.from({ length: 30 }, (_, i) => {
  const d = new Date("2026-10-06");
  d.setDate(d.getDate() + i);
  return {
    date: d.toISOString().split("T")[0],
    recognised_sek: String(Math.floor(30000 + Math.random() * 60000)),
    booked_sek: String(Math.floor(10000 + Math.random() * 30000)),
    orders: Math.floor(1 + Math.random() * 4),
  };
});

// ─── Handlers ────────────────────────────────────────────────────────────────

import { authHandlers, errorResponse } from "./authHandlers";
import { planningHandlers } from "./planningHandlers";
import { trackingHandlers } from "./trackingHandlers";
import {
  authorize,
  ORDER_READ_ROLES,
  orderInScope,
  projectOrderDetail,
  projectOrderListItem,
} from "./authorization";

export const handlers = [
  ...authHandlers,
  ...planningHandlers,
  // Orders — chỉ đơn CFO (DEC-ROUTING-002). Đơn legacy (LEGACY_ORDERS) không có trong list/detail/counts;
  // GET /orders/:id của đơn legacy trả 404 NOT_FOUND.
  http.get(`${BASE}/orders`, ({ request }) => {
    const auth = authorize(request, ORDER_READ_ROLES);
    if (!auth.ok) return auth.response;
    const scoped = ORDER_RECORDS.filter((o) => orderInScope(auth.account.user, o));
    const result = listOrders(scoped, new URL(request.url).searchParams);
    if (!result.ok) {
      const cid = request.headers.get("X-Correlation-ID") ?? crypto.randomUUID();
      return HttpResponse.json(
        { error: { code: "VALIDATION_ERROR", message: result.message, correlation_id: cid } },
        { status: 422, headers: { "X-Correlation-ID": cid } },
      );
    }
    return HttpResponse.json({ ...result.body, items: result.body.items.map((i) => projectOrderListItem(auth.account.user, i)) });
  }),

  http.get(`${BASE}/orders/counts`, ({ request }) => {
    const auth = authorize(request, ORDER_READ_ROLES);
    if (!auth.ok) return auth.response;
    const wh = new URL(request.url).searchParams.get("warehouse_id");
    const ids = new Set(
      ORDER_RECORDS.filter(
        (o) => orderInScope(auth.account.user, o) && (wh === null || o.warehouse?.id === Number(wh)),
      ).map((o) => o.id),
    );
    return HttpResponse.json(
      computeOrderCounts(
        ORDERS.filter((o) => ids.has(o.id)),
        ALERTS.filter((a) => ids.has(a.order_id)),
        { now: MOCK_NOW, timezone: MARKET_TIMEZONE },
      ),
    );
  }),

  http.get(`${BASE}/orders/:id`, ({ params, request }) => {
    const auth = authorize(request, ORDER_READ_ROLES);
    if (!auth.ok) return auth.response;
    const id = Number(params.id);
    const order = ORDERS.find((o) => o.id === id);
    const record = ORDER_RECORDS.find((o) => o.id === id);
    if (!order || !record || !orderInScope(auth.account.user, record)) {
      return errorResponse(request, 404, "NOT_FOUND", "Order not found."); // ngoài phạm vi cũng 404, không lộ sự tồn tại
    }
    const detail = projectOrderDetail(auth.account.user, order);
    const dateRequest = auth.account.user.roles.includes("driver")
      ? { window: { start: order.window_start, end: order.window_end } }
      : { mode: order.date_mode, date_from: order.date_from, date_to: order.date_to };
    return HttpResponse.json({ ...detail, date_request: dateRequest });
  }),

  // Alerts
  http.get(`${BASE}/alerts`, () => {
    return HttpResponse.json({ items: ALERTS, total: ALERTS.length });
  }),

  // Integration
  http.get(`${BASE}/integration/overview`, () => {
    return HttpResponse.json(INTEGRATION_OVERVIEW);
  }),

  // Prep queue
  http.get(`${BASE}/warehouses/:id/prep-queue`, () => {
    return HttpResponse.json({ items: PREP_QUEUE, capacity: CAPACITY_TODAY });
  }),

  http.get(`${BASE}/warehouses/:id/capacity`, () => {
    return HttpResponse.json(CAPACITY_TODAY);
  }),

  // Execution events
  http.post(`${BASE}/orders/:id/events`, () => {
    return HttpResponse.json({ event_id: 999, status: "recorded" });
  }),

  // KPI
  http.get(`${BASE}/kpi/summary`, () => {
    return HttpResponse.json(KPI_SUMMARY);
  }),

  http.get(`${BASE}/audit/decisions`, () => {
    return HttpResponse.json({ items: DECISION_LOG, total: DECISION_LOG.length });
  }),

  // Notifications
  http.get(`${BASE}/notifications`, () => {
    return HttpResponse.json({ items: NOTIFICATIONS, total: NOTIFICATIONS.length });
  }),

  http.post(`${BASE}/notifications/:id/send`, () => {
    return HttpResponse.json({ status: "sent" });
  }),

  http.delete(`${BASE}/notifications/:id`, () => {
    return HttpResponse.json({ status: "discarded" });
  }),

  // Driver
  http.get(`${BASE}/driver/trips`, () => {
    return HttpResponse.json({ items: DRIVER_TRIPS });
  }),

  http.post(`${BASE}/driver/trips/:id/events`, () => {
    return HttpResponse.json({ event_id: 998, status: "recorded" });
  }),

  // T17: live tracking, eligible receivers and handover.
  ...trackingHandlers,

  // Revenue — use the current US-REV-01 read DTOs. Legacy demo responses lacked period/points/rows
  // and could crash the Revenue screen after Business owner signed in (push CI).
  http.get(`${BASE}/revenue/summary`, ({ request }) => {
    const url = new URL(request.url);
    return HttpResponse.json({
      period: {
        from: url.searchParams.get("from") ?? REVENUE_SUMMARY.period_start,
        to: url.searchParams.get("to") ?? REVENUE_SUMMARY.period_end,
      },
      view: url.searchParams.get("view") ?? "store",
      location_id: Number(url.searchParams.get("location_id")) || null,
      currency: REVENUE_SUMMARY.currency,
      recognised: REVENUE_SUMMARY.recognised_sek,
      booked_not_delivered: REVENUE_SUMMARY.booked_sek,
      orders_delivered: REVENUE_SUMMARY.orders_delivered,
      avg_order_value: REVENUE_SUMMARY.avg_order_value_sek,
      share_of_market_pct: Number(REVENUE_SUMMARY.share_of_market_pct),
    });
  }),

  // T30 / A16b synthetic status report, visibly mock-only (not a T26 integrated seed).
  // Keep the period aligned with summary so default 30-day browser rendering remains coherent.
  http.get(`${BASE}/revenue/order-status`, ({ request }) => {
    const url = new URL(request.url);
    const groups = [
      { key: "approved", statuses: ["APPROVED", "PREPARING", "GOODS_READY", "LOADED"], orders: 16, amount: "402100.00" },
      { key: "in_transit", statuses: ["DISPATCHED"], orders: 5, amount: "88400.00" },
      { key: "completed", statuses: ["DELIVERED"], orders: 48, amount: "1012600.00" },
      { key: "failed", statuses: ["FAILED"], orders: 2, amount: "41000.00" },
      { key: "cancelled", statuses: ["CANCELLED"], orders: 3, amount: "25000.00" },
    ];
    return HttpResponse.json({
      period: {
        from: url.searchParams.get("from") ?? REVENUE_SUMMARY.period_start,
        to: url.searchParams.get("to") ?? REVENUE_SUMMARY.period_end,
      },
      view: url.searchParams.get("view") ?? "store",
      location_id: Number(url.searchParams.get("location_id")) || null,
      currency: REVENUE_SUMMARY.currency,
      total: { orders: 74, amount: "1569100.00" },
      groups: groups.map(group => ({
        ...group, date_basis: group.key === "cancelled" ? "cancelled_at" : "committed_date",
      })),
    });
  }),

  http.get(`${BASE}/revenue/orders`, ({ request }) => {
    const url = new URL(request.url);
    const group = url.searchParams.get("status_group");
    const counts: Record<string, number> = {
      approved: 16, in_transit: 5, completed: 48, failed: 2, cancelled: 3,
    };
    const total = group && group in counts ? counts[group] : 74;
    const page = Math.max(1, Number(url.searchParams.get("page") ?? 1));
    const pageSize = 25;
    const start = (page - 1) * pageSize;
    const rows = Array.from({ length: Math.max(0, Math.min(pageSize, total - start)) }, (_, index) => ({
      order_no: `SE-MOCK-${group ?? "ALL"}-${start + index + 1}`,
      delivered_at: group === "completed" ? "2026-11-03T10:00:00Z" : null,
      amount: "100.00",
      currency: REVENUE_SUMMARY.currency,
      status: ({
        approved: "APPROVED", in_transit: "DISPATCHED", completed: "DELIVERED",
        failed: "FAILED", cancelled: "CANCELLED",
      } as Record<string, string>)[group ?? ""] ?? "APPROVED",
    }));
    return HttpResponse.json({ items: rows, page, page_size: pageSize, total });
  }),

  http.get(`${BASE}/revenue/daily`, () => {
    return HttpResponse.json({
      currency: REVENUE_SUMMARY.currency,
      points: REVENUE_DAILY.map((point) => ({
        day: point.date,
        recognised: point.recognised_sek,
        booked: point.booked_sek,
      })),
    });
  }),

  http.get(`${BASE}/revenue/by-location`, () => {
    return HttpResponse.json({
      view: "store",
      currency: REVENUE_SUMMARY.currency,
      rows: [
        { location_id: 101, code: "GBG-V", name: "Store Göteborg Väst", orders_delivered: 8, recognised: "248000", booked_not_delivered: "0", share_pct: 19.3 },
        { location_id: 102, code: "STO-V", name: "Store Uppsala", orders_delivered: 6, recognised: "187500", booked_not_delivered: "52000", share_pct: 14.6 },
        { location_id: 103, code: "MLM-V", name: "Store Malmö City", orders_delivered: 5, recognised: "156000", booked_not_delivered: "31200", share_pct: 12.1 },
        { location_id: null, code: null, name: "Unassigned store", orders_delivered: 2, recognised: "48000", booked_not_delivered: "0", share_pct: 3.7 },
      ],
    });
  }),

  // Mapping
  http.get(`${BASE}/mapping/tasks`, () => {
    return HttpResponse.json({
      items: [
        {
          id: 1,
          market_sku: "ERP-448812",
          sku_name: "Gipsskiva GN13 900×2700",
          market: "SE",
          orders_blocked: 1,
          age_hours: 24,
          candidates: [
            { global_product_id: 55, name: "Gypsum board 13 × 900 × 2700", group: "N2", score: 0.92, reason: "GTIN match" },
          ],
        },
        {
          id: 2,
          market_sku: "POS-88412",
          sku_name: "Fogbruk grå 5 kg",
          market: "SE",
          orders_blocked: 1,
          age_hours: 12,
          candidates: [
            { global_product_id: 60, name: "Tile grout 5 kg grey", group: "N3", score: 0.87, reason: "Name similarity 0.87" },
          ],
        },
        {
          id: 3,
          market_sku: "ERP-449130",
          sku_name: "Trall 28×120 impregnerad 4.2 m",
          market: "SE",
          orders_blocked: 0,
          age_hours: 6,
          candidates: [
            { global_product_id: 70, name: "Decking board 28×120 treated 4.2 m", group: "N5", score: 0.95, reason: "Dimension match" },
          ],
        },
      ],
      total: 3,
    });
  }),

  http.post(`${BASE}/mapping/tasks/:id/confirm`, () => {
    return HttpResponse.json({ status: "confirmed" });
  }),

  http.post(`${BASE}/mapping/tasks/:id/reject`, () => {
    return HttpResponse.json({ status: "rejected" });
  }),

  // Transfers
  http.get(`${BASE}/transfers`, () => {
    return HttpResponse.json({ items: [], total: 0 });
  }),

  // Employees (HR)
  http.get(`${BASE}/employees`, () => {
    return HttpResponse.json({ items: [], total: 0 });
  }),

  http.get(`${BASE}/locations`, () => {
    return HttpResponse.json({
      items: [
        { id: 1, code: "GBG", name: "Göteborg DC", type: "warehouse", timezone: "Europe/Stockholm", cutoff: "15:00" },
        { id: 2, code: "STO", name: "Stockholm DC", type: "warehouse", timezone: "Europe/Stockholm", cutoff: "15:00" },
        { id: 3, code: "MLM", name: "Malmö DC", type: "warehouse", timezone: "Europe/Stockholm", cutoff: "15:00" },
        { id: 4, code: "DC", name: "Dispatch Center", type: "dispatch_center", timezone: "Europe/Stockholm", cutoff: "15:00" },
      ],
    });
  }),

  http.get(`${BASE}/vehicles`, () => {
    return HttpResponse.json({ items: [], total: 0 });
  }),

  // Health
  http.get(`${ORIGIN}/health`, () => {
    return HttpResponse.json({ status: "ok", env: "demo" });
  }),
];
