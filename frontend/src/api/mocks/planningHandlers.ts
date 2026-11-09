/**
 * MSW handlers cho Planning theo hợp đồng docs/06 mục 6. Owner: Dev 3 (luồng C) — M4–M5.
 * CHỈ phục vụ demo/test: mock KHÔNG chứng minh backend thật đã duyệt được (T16 vẫn fail-closed khi thiếu recheck adapter).
 * Kịch bản theo run id: 412 bình thường · 413 nhiều xe · 414 hold đã hết hạn · 415 không khả thi.
 * Vai trò dispatcher/admin thấy đầy đủ; vai trò khác (sales) chỉ thấy rank 1 rút gọn, không tài xế/score.
 */
import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "../config";
import type { UserRole } from "../contracts/auth";
import type {
  ApprovePlanResponse,
  Plan,
  PlanChecks,
  PlanVehicle,
  PlanningRun,
  RejectedCandidate,
} from "../contracts/planning";
import { errorResponse } from "./authHandlers";
import { authorize } from "./authorization";

const BASE = API_BASE_URL;
const PLANNING_ROLES: readonly UserRole[] = ["admin", "dispatcher", "sales"];
const HOLD_MS = 15 * 60 * 1000;
const MAX_EXTENSIONS = 2;

export const MOCK_RUN_IDS = { normal: 412, multiVehicle: 413, expired: 414, infeasible: 415 } as const;
/** plan id = run id * 10 + rank (chỉ là quy ước của mock). */
export const mockPlanId = (runId: number, rank: number): number => runId * 10 + rank;

type Scenario = "normal" | "multi" | "infeasible";
interface RunMeta {
  orderId: number;
  runNo: number;
  kind: PlanningRun["kind"];
  scenario: Scenario;
}
interface HoldState {
  expiresAt: number;
  extensions: number;
}

const SEED_RUNS: [number, RunMeta][] = [
  [412, { orderId: 123, runNo: 1, kind: "initial", scenario: "normal" }],
  [413, { orderId: 160, runNo: 1, kind: "initial", scenario: "multi" }],
  [414, { orderId: 161, runNo: 1, kind: "initial", scenario: "normal" }],
  [415, { orderId: 137, runNo: 1, kind: "initial", scenario: "infeasible" }],
];

let runs = new Map<number, RunMeta>();
let latestRunByOrder = new Map<number, number>();
let holds = new Map<number, HoldState>();
let approvedOrders = new Set<number>();
let approvals = new Map<string, { fingerprint: string; response: ApprovePlanResponse }>();
let nextRunId = 500;

export function resetPlanningMock(): void {
  runs = new Map(SEED_RUNS);
  latestRunByOrder = new Map(SEED_RUNS.map(([runId, meta]) => [meta.orderId, runId]));
  holds = new Map();
  approvedOrders = new Set();
  approvals = new Map();
  nextRunId = 500;
}
resetPlanningMock();

function holdFor(runId: number): HoldState {
  let hold = holds.get(runId);
  if (!hold) {
    const offsetMs = runId === MOCK_RUN_IDS.expired ? -3 * 60 * 1000 : 11 * 60 * 1000;
    hold = { expiresAt: Date.now() + offsetMs, extensions: 0 };
    holds.set(runId, hold);
  }
  return hold;
}

const ALL_PASS: PlanChecks = {
  stock: { passed: true, code: "STOCK_OK" },
  preparation: { passed: true, code: "PREP_OK" },
  truck: { passed: true, code: "TRUCK_OK" },
  site_date: { passed: true, code: "DATE_OK" },
  safety: { passed: true, code: "SAFETY_OK" },
};

interface VehicleSeed {
  seq: number;
  id: number;
  code: string;
  name: string;
  capKg: string;
  capM3: string;
  driverId: number;
  loadKg: string;
  loadM3: string;
  departAt: string;
  etaAt: string;
}

function vehicle(v: VehicleSeed): PlanVehicle {
  return {
    seq: v.seq,
    vehicle_id: v.id,
    driver_employee_id: v.driverId,
    vehicle: { id: v.id, code: v.code, name: v.name, capacity_kg: v.capKg, capacity_m3: v.capM3 },
    load_kg: v.loadKg,
    load_m3: v.loadM3,
    load_lines: [{ line_no: v.seq, qty_base: "100" }],
    loading_start_at: "2026-11-10T09:30:00+01:00",
    depart_at: v.departAt,
    eta_at: v.etaAt,
    trip_end_at: "2026-11-10T13:40:00+01:00",
  };
}

interface PlanSeed {
  rank: number;
  warehouse: { id: number; name: string };
  km: string;
  fill: string;
  score: string;
  reserveMin: number;
  reasons: string[];
  explanation: string;
  vehicles: PlanVehicle[];
}

function fullPlan(runId: number, s: PlanSeed): Plan {
  const last = s.vehicles[s.vehicles.length - 1];
  const sum = (pick: (v: PlanVehicle) => number) => String(s.vehicles.reduce((acc, v) => acc + pick(v), 0));
  return {
    id: mockPlanId(runId, s.rank),
    rank: s.rank,
    status: "proposed",
    target_date: "2026-11-10",
    eta_at: last.eta_at,
    vehicle_count: s.vehicles.length,
    vehicles: s.vehicles,
    warehouse: s.warehouse,
    total_capacity_kg: sum((v) => Number(v.vehicle?.capacity_kg)),
    total_capacity_m3: sum((v) => Number(v.vehicle?.capacity_m3)),
    goods_ready_at: "2026-11-10T09:30:00+01:00",
    loading_start_at: "2026-11-10T09:30:00+01:00",
    depart_at: s.vehicles[0].depart_at,
    trip_end_at: "2026-11-10T13:40:00+01:00",
    distance_km: s.km,
    drive_min: 110,
    prep_hours: "10.15",
    capacity_fill: s.fill,
    score: s.score,
    score_breakdown: { n_km: 0.07, n_fill: 0.44, w_km: 0.5, w_fill: 0.5 },
    complexity_points: s.vehicles.length > 1 ? 1 : 0,
    planning_reserve_min: s.reserveMin,
    route_provenance: "ors",
    checks: { ...ALL_PASS },
    reason_codes: s.reasons,
    explanation: s.explanation,
  };
}

/** Bản rút gọn cho vai trò không phải Dispatcher: không tài xế, không score, không chẩn đoán. */
function compactPlan(p: Plan): Plan {
  return {
    id: p.id,
    rank: p.rank,
    status: p.status,
    target_date: p.target_date,
    eta_at: p.eta_at,
    vehicle_count: p.vehicle_count,
    vehicles: p.vehicles.map((v) => ({ seq: v.seq, eta_at: v.eta_at })),
  };
}

const GBG = { id: 1, name: "Göteborg DC" };
const MLM = { id: 3, name: "Malmö DC" };

function normalPlans(runId: number): Plan[] {
  return [
    fullPlan(runId, {
      rank: 1, warehouse: GBG, km: "48", fill: "0.60", score: "0.26", reserveMin: 5220,
      reasons: ["LOWEST_SCORE_OF_3", "STOCK_OK", "TRUCK_OK", "RESERVE_SAFE"],
      explanation: "Lowest score of 3 feasible plans. Göteborg DC has stock, capacity fill 60%, 48 km, reserve 3.6 days (safe).",
      vehicles: [vehicle({ seq: 1, id: 15, code: "GBG-12-03", name: "Truck 12 t", capKg: "12000", capM3: "40", driverId: 71, loadKg: "4120", loadM3: "9.6", departAt: "2026-11-10T10:48:00+01:00", etaAt: "2026-11-10T12:38:00+01:00" })],
    }),
    fullPlan(runId, {
      rank: 2, warehouse: MLM, km: "262", fill: "0.50", score: "0.50", reserveMin: 2400,
      reasons: ["STOCK_OK", "TRUCK_OK"],
      explanation: "Malmö DC has full stock but a 262 km drive increases the distance score. Reserve 1.7 days.",
      vehicles: [vehicle({ seq: 1, id: 21, code: "MLM-18-01", name: "Truck 18 t", capKg: "18000", capM3: "60", driverId: 72, loadKg: "4120", loadM3: "9.6", departAt: "2026-11-10T10:48:00+01:00", etaAt: "2026-11-10T14:38:00+01:00" })],
    }),
    fullPlan(runId, {
      rank: 3, warehouse: GBG, km: "48", fill: "0.60", score: "0.50", reserveMin: 3800,
      reasons: ["STOCK_OK", "TRUCK_OK"],
      explanation: "Same Göteborg DC with the larger truck GBG-18-01. Same distance score; tie-break on total capacity.",
      vehicles: [vehicle({ seq: 1, id: 16, code: "GBG-18-01", name: "Truck 18 t", capKg: "18000", capM3: "60", driverId: 73, loadKg: "4120", loadM3: "9.6", departAt: "2026-11-10T11:30:00+01:00", etaAt: "2026-11-10T13:20:00+01:00" })],
    }),
  ];
}

function multiVehiclePlans(runId: number): Plan[] {
  return [
    fullPlan(runId, {
      rank: 1, warehouse: GBG, km: "48", fill: "0.56", score: "0.31", reserveMin: 4300,
      reasons: ["FEWEST_VEHICLES", "STOCK_OK", "TRUCK_OK"],
      explanation: "Order of 20 000 kg needs two vehicles; both leave Göteborg DC and arrive together.",
      vehicles: [
        vehicle({ seq: 1, id: 15, code: "GBG-12-03", name: "Truck 12 t", capKg: "12000", capM3: "40", driverId: 71, loadKg: "12000", loadM3: "20.0", departAt: "2026-11-10T10:48:00+01:00", etaAt: "2026-11-10T12:38:00+01:00" }),
        vehicle({ seq: 2, id: 16, code: "GBG-18-01", name: "Truck 18 t", capKg: "18000", capM3: "60", driverId: 73, loadKg: "8000", loadM3: "18.5", departAt: "2026-11-10T10:55:00+01:00", etaAt: "2026-11-10T12:45:00+01:00" }),
      ],
    }),
    fullPlan(runId, {
      rank: 2, warehouse: MLM, km: "262", fill: "0.48", score: "0.55", reserveMin: 2100,
      reasons: ["STOCK_OK", "TRUCK_OK"],
      explanation: "Malmö DC can also serve the order with two trucks but the route is much longer.",
      vehicles: [
        vehicle({ seq: 1, id: 21, code: "MLM-18-01", name: "Truck 18 t", capKg: "18000", capM3: "60", driverId: 72, loadKg: "12000", loadM3: "20.0", departAt: "2026-11-10T10:48:00+01:00", etaAt: "2026-11-10T14:38:00+01:00" }),
        vehicle({ seq: 2, id: 22, code: "MLM-12-02", name: "Truck 12 t", capKg: "12000", capM3: "40", driverId: 74, loadKg: "8000", loadM3: "18.5", departAt: "2026-11-10T10:55:00+01:00", etaAt: "2026-11-10T14:45:00+01:00" }),
      ],
    }),
  ];
}

const REJECTED: RejectedCandidate[] = [
  { warehouse_id: 2, vehicle_code: "STO-12-04", failed_check: "site_date", code: "OUTSIDE_RECEIVING_HOURS", detail: { message: "ETA 15:45 is outside site window 08:00–14:30." } },
  { warehouse_id: 1, vehicle_code: "GBG-03-02", failed_check: "truck", code: "NO_TRUCK_FIT", detail: { message: "Order weighs 4 120 kg; van GBG-03-02 carries 3 500 kg." } },
  { warehouse_id: 3, vehicle_code: "MLM-12-02", failed_check: "truck", code: "TRUCK_BUSY", detail: { message: "MLM-12-02 is committed to SE-2026-000131 on Tue 10 Nov." } },
  { warehouse_id: 2, vehicle_code: null, failed_check: "safety", code: "DRIVER_HOURS_EXCEEDED", detail: { message: "Drive time exceeds the 9 h limit for STO → Kungsbacka." } },
];

function buildRun(runId: number, full: boolean): PlanningRun | undefined {
  const meta = runs.get(runId);
  if (!meta) return undefined;
  const infeasible = meta.scenario === "infeasible";
  const allPlans = infeasible ? [] : meta.scenario === "multi" ? multiVehiclePlans(runId) : normalPlans(runId);
  const hold = infeasible ? null : holdFor(runId);
  const base = {
    id: runId,
    order_id: meta.orderId,
    run_no: meta.runNo,
    kind: meta.kind,
    result: infeasible ? ("infeasible" as const) : ("feasible" as const),
    reserve_class: infeasible ? null : ("safe" as const),
    hold_expires_at: hold ? new Date(hold.expiresAt).toISOString() : null,
    hold_extensions: hold?.extensions ?? 0,
  };
  if (!full) {
    const plans = allPlans.slice(0, 1).map(compactPlan);
    const approvable =
      plans.length > 0 &&
      plans[0].vehicle_count === 1 &&
      hold !== null &&
      hold.expiresAt > Date.now() &&
      latestRunByOrder.get(meta.orderId) === runId;
    return { ...base, plans, sales_approvable: approvable, sales_block_reason: approvable ? null : "PLAN_NOT_APPROVABLE" };
  }
  return {
    ...base,
    plans: allPlans,
    failed_check: infeasible ? "truck" : null,
    earliest_feasible_date: infeasible ? "2026-11-12" : null,
    planning_reserve_min: allPlans[0]?.planning_reserve_min ?? null,
    workload: { labour_hours: 10.15 },
    rejected_candidates: infeasible ? [] : REJECTED,
    transfer_suggestions: [],
  };
}

const isFullView = (roles: readonly UserRole[]) => roles.includes("dispatcher");

export const planningHandlers = [
  http.get(`${BASE}/orders/:id`, ({ params, request }) => {
    const id = Number(params.id);
    if (id !== 161) return undefined;
    const auth = authorize(request, PLANNING_ROLES);
    if (!auth.ok) return auth.response;
    return HttpResponse.json({ id, date_request: { date_to: "2026-11-10" } });
  }),

  http.get(`${BASE}/orders/:id/date-negotiations`, ({ params, request }) => {
    const auth = authorize(request, ["dispatcher"]);
    if (!auth.ok) return auth.response;
    const items = Number(params.id) === 160
      ? [{ id: 1601, proposed_date: "2026-11-10", outcome: "agreed", channel: "phone", contacted_at: "2026-11-04T12:00:00Z", remind_at: null }]
      : [];
    return HttpResponse.json({ items });
  }),

  http.get(`${BASE}/planning-runs/:id`, ({ params, request }) => {
    const auth = authorize(request, PLANNING_ROLES);
    if (!auth.ok) return auth.response;
    const run = buildRun(Number(params.id), isFullView(auth.account.user.roles));
    return run ? HttpResponse.json(run) : errorResponse(request, 404, "NOT_FOUND", "Planning run not found.");
  }),

  http.get(`${BASE}/orders/:id/planning-runs`, ({ params, request }) => {
    const auth = authorize(request, PLANNING_ROLES);
    if (!auth.ok) return auth.response;
    const orderId = Number(params.id);
    const items = [...runs.entries()]
      .filter(([, m]) => m.orderId === orderId)
      .sort((a, b) => b[1].runNo - a[1].runNo)
      .map(([id, m]) => ({
        id,
        order_id: m.orderId,
        run_no: m.runNo,
        result: m.scenario === "infeasible" ? "infeasible" : "feasible",
        hold_expires_at: m.scenario === "infeasible" ? null : new Date(holdFor(id).expiresAt).toISOString(),
      }));
    return HttpResponse.json({ items });
  }),

  // Plan Again (DEC-HOLD-001): luôn tạo planning_run MỚI trên cùng order; lần chạy lại bắt buộc có lý do.
  http.post(`${BASE}/orders/:id/plan`, async ({ params, request }) => {
    const auth = authorize(request, PLANNING_ROLES);
    if (!auth.ok) return auth.response;
    const orderId = Number(params.id);
    const body = (await request.json().catch(() => ({}))) as { reason_text?: string };
    const previousId = latestRunByOrder.get(orderId);
    const previous = previousId !== undefined ? runs.get(previousId) : undefined;
    if (previous && !body.reason_text?.trim()) {
      return errorResponse(request, 422, "REASON_REQUIRED", "A reason is required to plan again.");
    }
    const runId = nextRunId++;
    runs.set(runId, {
      orderId,
      runNo: (previous?.runNo ?? 0) + 1,
      kind: previous ? "rerun" : "initial",
      scenario: previous?.scenario === "multi" ? "multi" : "normal",
    });
    latestRunByOrder.set(orderId, runId);
    holds.set(runId, { expiresAt: Date.now() + HOLD_MS, extensions: 0 });
    return HttpResponse.json(buildRun(runId, isFullView(auth.account.user.roles)));
  }),

  http.post(`${BASE}/planning-runs/:id/extend`, ({ params, request }) => {
    const auth = authorize(request, PLANNING_ROLES);
    if (!auth.ok) return auth.response;
    const runId = Number(params.id);
    const meta = runs.get(runId);
    if (!meta || meta.scenario === "infeasible") return errorResponse(request, 404, "NOT_FOUND", "Planning run not found.");
    const hold = holdFor(runId);
    if (hold.expiresAt <= Date.now()) return errorResponse(request, 409, "HOLD_EXPIRED", "Planning hold expired. Plan Again.");
    if (hold.extensions >= MAX_EXTENSIONS) return errorResponse(request, 409, "HOLD_EXTENSION_LIMIT", "Hold can be extended at most twice.");
    hold.extensions += 1;
    hold.expiresAt += HOLD_MS;
    return HttpResponse.json(buildRun(runId, isFullView(auth.account.user.roles)));
  }),

  http.post(`${BASE}/plans/:id/approve`, async ({ params, request }) => {
    const auth = authorize(request, PLANNING_ROLES);
    if (!auth.ok) return auth.response;
    const key = request.headers.get("Idempotency-Key");
    if (!key) return errorResponse(request, 422, "VALIDATION_ERROR", "Idempotency-Key header is required.");
    const planId = Number(params.id);
    const runId = Math.floor(planId / 10);
    const rank = planId % 10;
    const meta = runs.get(runId);
    if (!meta || meta.scenario === "infeasible" || rank < 1) return errorResponse(request, 404, "NOT_FOUND", "Plan not found.");

    const body = (await request.json().catch(() => ({}))) as { reason_text?: string };
    const fingerprint = `${planId}:${JSON.stringify(body)}`;
    const cached = approvals.get(key);
    if (cached) {
      return cached.fingerprint === fingerprint
        ? HttpResponse.json(cached.response)
        : errorResponse(request, 409, "IDEMPOTENCY_CONFLICT", "Same Idempotency-Key with a different request.");
    }
    if (latestRunByOrder.get(meta.orderId) !== runId || approvedOrders.has(meta.orderId)) {
      return errorResponse(request, 409, "PLAN_NOT_APPROVABLE", "Only the latest planning run may be approved.");
    }
    if (holdFor(runId).expiresAt <= Date.now()) {
      return errorResponse(request, 409, "HOLD_EXPIRED", "Planning hold expired. Plan Again.");
    }
    if (!isFullView(auth.account.user.roles) && rank !== 1) {
      return errorResponse(request, 409, "PLAN_NOT_APPROVABLE", "Sales can only confirm an unchanged safe rank-1 plan.");
    }
    if (rank > 1 && !body.reason_text?.trim()) {
      return errorResponse(request, 422, "REASON_REQUIRED", "A reason is required when selecting a non-rank-1 plan.");
    }

    approvedOrders.add(meta.orderId);
    const response: ApprovePlanResponse = {
      order: { status: "APPROVED", committed: { date: "2026-11-10", promise_start: "2026-11-10T08:00:00+01:00", promise_end: "2026-11-10T14:30:00+01:00" } },
      plan: { id: planId, status: "approved" },
      trip_ids: [930],
      notifications: [{ id: 77, template: "CONFIRMED", status: "queued" }],
    };
    approvals.set(key, { fingerprint, response });
    return HttpResponse.json(response);
  }),
];
