/**
 * MSW handlers mô phỏng API (docs/08 mục 2) với dữ liệu khớp seed (SE-2026-000123, 137, 141…) để frontend
 * không phải chờ backend. Owner: Dev 3 (luồng C) — M0..M4.
 */
import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "../config";

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

const needsPlan = ORDERS.filter((o) => o.status === "SUBMITTED").length;
const noFeasibleDate = ORDERS.filter((o) => o.status === "NO_FEASIBLE_DATE").length;
const replanSuggested = 0;

// Hình dạng theo docs/06 mục 5 (`all` + `nav`). ORDERS chỉ chứa đơn CFO (đơn legacy nằm ở LEGACY_ORDERS,
// DEC-ROUTING-002) nên mọi số liệu suy ra từ ORDERS, khớp đúng với GET /orders.
const COUNTS = {
  all: ORDERS.length,
  needs_plan: needsPlan,
  awaiting_approval: ORDERS.filter((o) => o.status === "PLANNED").length,
  no_feasible_date: noFeasibleDate,
  in_execution: ORDERS.filter((o) => ["PREPARING", "GOODS_READY", "LOADED", "DISPATCHED"].includes(o.status)).length,
  replan_suggested: replanSuggested,
  delivered_today: ORDERS.filter((o) => o.status === "DELIVERED").length,
  nav: {
    order_queue: needsPlan,
    exceptions: noFeasibleDate + replanSuggested,
    tracking_risk: ORDERS.filter((o) => o.risk_color === "orange" || o.risk_color === "red").length,
  },
};

const PLAN_CANDIDATES = [
  {
    id: 1,
    rank: 1,
    warehouse_id: 1,
    warehouse_name: "Göteborg DC",
    warehouse_code: "GBG",
    score: 0.26,
    distance_km: "48",
    capacity_fill: "0.60",
    prep_hours: "10.15",
    goods_ready_at: "2026-11-10T09:30:00+01:00",
    depart_at: "2026-11-10T10:48:00+01:00",
    eta_at: "2026-11-10T12:38:00+01:00",
    trip_end_at: "2026-11-10T13:40:00+01:00",
    planning_reserve_min: 5220,
    reserve_class: "safe",
    complexity_points: 1,
    route_provenance: "ors",
    reason_codes: ["LOWEST_SCORE_OF_3"],
    explanation:
      "Göteborg DC has stock ready today and 60% warehouse capacity used. 48 km drive, 1h 50min. Planning reserve 3.6 days (safe).",
    vehicles: [
      {
        seq: 1,
        vehicle_code: "GBG-12-03",
        vehicle_type: "Truck 12 t",
        driver_name: "Björn Eriksson",
        capacity_kg: "12000",
        load_kg: "4120",
        capacity_m3: "40",
        load_m3: "9.6",
        depart_at: "2026-11-10T10:48:00+01:00",
        eta_at: "2026-11-10T12:38:00+01:00",
      },
    ],
    checks: [
      { name: "stock", passed: true, code: "STOCK_OK", detail: { message: "All 4 lines in stock at Göteborg DC." } },
      { name: "preparation", passed: true, code: "PREP_OK", detail: { message: "10.15 h fits in 2 shifts before loading cut-off." } },
      { name: "truck", passed: true, code: "TRUCK_OK", detail: { message: "GBG-12-03 available, licence CE, 4120 kg / 9.6 m³ fits." } },
      { name: "site_date", passed: true, code: "DATE_OK", detail: { message: "Tue 10 Nov is a working day; ETA 12:38 within site window 08:00–14:30." } },
      { name: "safety", passed: true, code: "SAFETY_OK", detail: { message: "Driver hours within limit." } },
    ],
    prep_by_day: { "2026-11-09": "10.15" },
  },
  {
    id: 2,
    rank: 2,
    warehouse_id: 3,
    warehouse_name: "Malmö DC",
    warehouse_code: "MLM",
    score: 0.50,
    distance_km: "262",
    capacity_fill: "0.50",
    prep_hours: "10.15",
    goods_ready_at: "2026-11-10T09:30:00+01:00",
    depart_at: "2026-11-10T10:48:00+01:00",
    eta_at: "2026-11-10T14:38:00+01:00",
    trip_end_at: "2026-11-10T15:30:00+01:00",
    planning_reserve_min: 2400,
    reserve_class: "safe",
    complexity_points: 1,
    route_provenance: "ors",
    reason_codes: [],
    explanation:
      "Malmö DC has full stock but 262 km drive increases distance score. Planning reserve 1.7 days.",
    vehicles: [
      {
        seq: 1,
        vehicle_code: "MLM-18-01",
        vehicle_type: "Truck 18 t",
        driver_name: "Per Magnusson",
        capacity_kg: "18000",
        load_kg: "4120",
        capacity_m3: "60",
        load_m3: "9.6",
        depart_at: "2026-11-10T10:48:00+01:00",
        eta_at: "2026-11-10T14:38:00+01:00",
      },
    ],
    checks: [
      { name: "stock", passed: true, code: "STOCK_OK", detail: { message: "All lines in stock." } },
      { name: "preparation", passed: true, code: "PREP_OK", detail: { message: "10.15 h fits in 2 shifts." } },
      { name: "truck", passed: true, code: "TRUCK_OK", detail: { message: "MLM-18-01 available." } },
      { name: "site_date", passed: true, code: "DATE_OK", detail: { message: "ETA 14:38 within site window." } },
      { name: "safety", passed: true, code: "SAFETY_OK", detail: { message: "Driver hours OK." } },
    ],
    prep_by_day: { "2026-11-09": "10.15" },
  },
  {
    id: 3,
    rank: 3,
    warehouse_id: 1,
    warehouse_name: "Göteborg DC",
    warehouse_code: "GBG",
    score: 0.50,
    distance_km: "48",
    capacity_fill: "0.60",
    prep_hours: "10.15",
    goods_ready_at: "2026-11-10T09:30:00+01:00",
    depart_at: "2026-11-10T11:30:00+01:00",
    eta_at: "2026-11-10T13:20:00+01:00",
    trip_end_at: "2026-11-10T14:30:00+01:00",
    planning_reserve_min: 3800,
    reserve_class: "safe",
    complexity_points: 1,
    route_provenance: "ors",
    reason_codes: [],
    explanation:
      "Same Göteborg DC, larger truck GBG-18-01. Same distance score, tie-break: larger total capacity.",
    vehicles: [
      {
        seq: 1,
        vehicle_code: "GBG-18-01",
        vehicle_type: "Truck 18 t",
        driver_name: "Anders Pettersen",
        capacity_kg: "18000",
        load_kg: "4120",
        capacity_m3: "60",
        load_m3: "9.6",
        depart_at: "2026-11-10T11:30:00+01:00",
        eta_at: "2026-11-10T13:20:00+01:00",
      },
    ],
    checks: [
      { name: "stock", passed: true, code: "STOCK_OK", detail: { message: "All lines in stock." } },
      { name: "preparation", passed: true, code: "PREP_OK", detail: { message: "10.15 h fits." } },
      { name: "truck", passed: true, code: "TRUCK_OK", detail: { message: "GBG-18-01 available." } },
      { name: "site_date", passed: true, code: "DATE_OK", detail: { message: "ETA within window." } },
      { name: "safety", passed: true, code: "SAFETY_OK", detail: { message: "Driver hours OK." } },
    ],
    prep_by_day: { "2026-11-09": "10.15" },
  },
];

const REJECTED_CANDIDATES = [
  {
    warehouse_id: 2,
    warehouse_name: "Stockholm DC",
    vehicle_code: "STO-12-04",
    failed_check: "site_date",
    code: "OUTSIDE_RECEIVING_HOURS",
    detail: { message: "ETA 15:45 is outside site window 08:00–14:30." },
  },
  {
    warehouse_id: 1,
    warehouse_name: "Göteborg DC",
    vehicle_code: "GBG-03-02",
    failed_check: "truck",
    code: "NO_TRUCK_FIT",
    detail: { message: "Order weighs 4 120 kg; van GBG-03-02 carries 3 500 kg.", reason: "combined_capacity" },
  },
  {
    warehouse_id: 3,
    warehouse_name: "Malmö DC",
    vehicle_code: "MLM-12-02",
    failed_check: "truck",
    code: "TRUCK_BUSY",
    detail: { message: "MLM-12-02 is committed to SE-2026-000131 on Tue 10 Nov." },
  },
  {
    warehouse_id: 1,
    warehouse_name: "Göteborg DC",
    vehicle_code: "GBG-26-01",
    failed_check: "safety",
    code: "DRIVER_HOURS_EXCEEDED",
    detail: { message: "Return trip GBG→Kungsbacka→GBG exceeds 9 h driver limit." },
  },
  {
    warehouse_id: 2,
    warehouse_name: "Stockholm DC",
    vehicle_code: "STO-CR-01",
    failed_check: "safety",
    code: "DRIVER_HOURS_EXCEEDED",
    detail: { message: "Drive time exceeds 9 h limit for STO → Kungsbacka." },
  },
  {
    warehouse_id: 2,
    warehouse_name: "Stockholm DC",
    vehicle_code: "STO-12-04",
    failed_check: "truck",
    code: "TRUCK_BUSY",
    detail: { message: "STO-12-04 assigned to SE-2026-000141 on Tue 10 Nov." },
  },
];

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

import { authHandlers } from "./authHandlers"

export const handlers = [
  ...authHandlers,
  // Orders — chỉ đơn CFO (DEC-ROUTING-002). Đơn legacy (LEGACY_ORDERS) không có trong list/detail/counts;
  // GET /orders/:id của đơn legacy trả 404 NOT_FOUND.
  http.get(`${BASE}/orders`, ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    const q = url.searchParams.get("q")?.toLowerCase();
    let orders = [...ORDERS];
    if (status) orders = orders.filter((o) => o.status === status);
    if (q)
      orders = orders.filter(
        (o) =>
          o.order_no.toLowerCase().includes(q) ||
          o.customer_name.toLowerCase().includes(q),
      );
    return HttpResponse.json({ items: orders, total: orders.length, page: 1, page_size: 50 });
  }),

  http.get(`${BASE}/orders/counts`, () => {
    return HttpResponse.json(COUNTS);
  }),

  http.get(`${BASE}/orders/:id`, ({ params }) => {
    const order = ORDERS.find((o) => o.id === Number(params.id));
    if (!order) return HttpResponse.json({ error: { code: "NOT_FOUND", message: "Order not found." } }, { status: 404 });
    return HttpResponse.json(order);
  }),

  // Planning
  http.get(`${BASE}/planning-runs/:id`, () => {
    return HttpResponse.json({
      id: 412,
      order_id: 123,
      kind: "initial",
      duration_ms: 412,
      candidates: PLAN_CANDIDATES,
      rejected_candidates: REJECTED_CANDIDATES,
      hold_expires_at: new Date(Date.now() + 11 * 60 * 1000).toISOString(),
      hold_extensions_remaining: 2,
    });
  }),

  http.post(`${BASE}/orders/:id/plan`, () => {
    return HttpResponse.json({ run_id: 412, status: "planned" });
  }),

  // Approve
  http.post(`${BASE}/planning-runs/:runId/approve`, () => {
    return HttpResponse.json({ plan_id: 1, order_status: "APPROVED" });
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

  // GPS
  http.get(`${BASE}/gps/live`, () => {
    return HttpResponse.json({
      positions: [
        {
          trip_id: 1,
          vehicle_code: "MLM-12-02",
          lat: 55.605,
          lon: 13.003,
          recorded_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
          accuracy_m: 12,
          source: "simulator",
        },
      ],
    });
  }),

  // Revenue
  http.get(`${BASE}/revenue/summary`, () => {
    return HttpResponse.json(REVENUE_SUMMARY);
  }),

  http.get(`${BASE}/revenue/daily`, () => {
    return HttpResponse.json({ items: REVENUE_DAILY });
  }),

  http.get(`${BASE}/revenue/by-location`, () => {
    return HttpResponse.json({
      view: "store",
      items: [
        { location_id: 101, location_name: "Store Göteborg Väst", orders: 8, recognised_sek: "248000", booked_sek: "0", share_pct: "19.3" },
        { location_id: 102, location_name: "Store Uppsala", orders: 6, recognised_sek: "187500", booked_sek: "52000", share_pct: "14.6" },
        { location_id: 103, location_name: "Store Malmö City", orders: 5, recognised_sek: "156000", booked_sek: "31200", share_pct: "12.1" },
        { location_id: null, location_name: "Unassigned store", orders: 2, recognised_sek: "48000", booked_sek: "0", share_pct: "3.7" },
      ],
      total_recognised_sek: "1284500",
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
