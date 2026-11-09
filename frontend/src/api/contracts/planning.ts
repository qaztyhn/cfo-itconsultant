/**
 * Hợp đồng Planning (docs/06 mục 6.2–6.3).
 * DEPENDENCY: viết tay tạm thời đến khi có schema.d.ts sinh từ OpenAPI.
 * Backend trả một số trường Decimal dưới dạng chuỗi, nên dùng DecimalLike.
 */
export type DecimalLike = number | string;

export const GATE_KEYS = ["stock", "preparation", "truck", "site_date", "safety"] as const;
export type GateKey = (typeof GATE_KEYS)[number];

export interface GateResult {
  pass: boolean;
  code: string;
  detail?: { message?: string; [key: string]: unknown };
}
export type PlanChecks = Record<GateKey, GateResult>;

export interface PlanVehicleRef {
  id: number;
  code: string;
  name: string;
  capacity_kg: DecimalLike;
  capacity_m3: DecimalLike;
}

export interface PlanVehicle {
  seq: number;
  vehicle: PlanVehicleRef;
  /** Chỉ Dispatcher nhận được; vai trò khác bị backend lược bỏ. */
  driver?: { employee_id: number; name: string } | null;
  load_kg: DecimalLike;
  load_m3: DecimalLike;
  load_lines?: { line_no: number; qty_base: DecimalLike }[];
  loading_start_at: string;
  depart_at: string;
  eta_at: string;
}

export interface Plan {
  id: number;
  rank: number;
  status: string;
  target_date: string;
  eta_at: string;
  vehicle_count: number;
  vehicles: PlanVehicle[];
  // Các trường dưới đây chỉ có với Dispatcher (bản rút gọn của Sales không có).
  warehouse?: { id: number; name: string };
  total_capacity_kg?: DecimalLike;
  total_capacity_m3?: DecimalLike;
  goods_ready_at?: string;
  loading_start_at?: string;
  depart_at?: string;
  trip_end_at?: string;
  promise_window_preview?: { start: string; end: string };
  distance_km?: DecimalLike;
  drive_min?: number;
  prep_hours?: DecimalLike;
  capacity_fill?: DecimalLike;
  score?: DecimalLike;
  score_breakdown?: Record<string, number>;
  complexity_points?: number;
  planning_reserve_min?: number;
  route_provenance?: string;
  checks?: PlanChecks;
  reason_codes?: string[];
  explanation?: string;
}

export interface RejectedCandidate {
  warehouse?: { id: number; name: string } | null;
  vehicle?: { code: string } | null;
  failed_check?: GateKey | string;
  code?: string;
  detail?: { message?: string; [key: string]: unknown };
}

export interface PlanningRun {
  id: number;
  order_id: number;
  run_no: number;
  kind: "initial" | "rerun" | "replan_suggestion";
  result: "feasible" | "infeasible";
  reserve_class: "safe" | "tight" | null;
  hold_expires_at: string | null;
  hold_extensions: number;
  plans: Plan[];
  // Dispatcher only
  failed_check?: string | null;
  earliest_feasible_date?: string | null;
  planning_reserve_min?: number | null;
  workload?: Record<string, unknown>;
  rejected_candidates?: RejectedCandidate[];
  transfer_suggestions?: unknown[];
  // Sales only
  sales_approvable?: boolean;
  sales_block_reason?: string | null;
}

export interface PlanAgainInput {
  reason_code: string;
  reason_text: string;
}

export interface ApprovePlanInput {
  /** Bắt buộc khi plan.rank > 1 (chọn phương án khác). */
  reason_code?: string;
  reason_text?: string;
  note?: string;
  date_negotiation_id?: number;
  drivers?: { seq: number; driver_employee_id: number }[];
}

export interface ApprovePlanResponse {
  order: {
    status: string;
    committed?: { date: string; promise_start: string; promise_end: string };
  };
  plan: { id: number; status: string };
  trip_ids: number[];
  notifications: { id: number; template: string; status: string }[];
}