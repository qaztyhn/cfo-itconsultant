/**
 * Local types for the Warehouse Prep Queue (docs/06 Appendix A payload, `GET /warehouses/{id}/prep-queue?date=` agreed with Dev 1)`.
 * DEPENDENCY: hand-written because `schema.d.ts` is not generated yet (docs/09 §9). Replace with generated
 * types once Dev 1/2 export OpenAPI, then delete this file.
 * Owner: Dev 3 (stream C) — M6.
 */

/** `customer_order.status` (docs/09 §17). */
export type OrderStatus =
  | "SUBMITTED"
  | "BLOCKED_UNMAPPED_SKU"
  | "PLANNED"
  | "NO_FEASIBLE_DATE"
  | "APPROVED"
  | "PREPARING"
  | "GOODS_READY"
  | "LOADED"
  | "DISPATCHED"
  | "DELIVERED"
  | "FAILED"
  | "CANCELLED";

/** `running` = crew is working, `paused` = PREP_PAUSED recorded, `null` = not in preparation (Appendix A). */
export type PrepState = "running" | "paused" | null;

export interface HandlingMixItem {
  /** N1…N6 (docs/05 §11). */
  code: string;
  name: string;
}

/**
 * One row per shift. Units follow Appendix A: `minutes` and `booked` are minutes.
 * ASSUMPTION (to confirm with Dev 1): `share` is a 0–1 ratio (0.9 = 90%) and `booked` is minutes booked in the shift.
 */
export interface CapacityShift {
  name: string;
  /** Actual START_PREP instant (ISO 8601 with offset) or `null` before preparation starts (Q7). */
  start: string | null;
  end: string;
  present: number;
  useful_hours: number;
  share: number;
  minutes: number;
  booked: number;
}

export interface Capacity {
  booked_min: number;
  total_min: number;
  free_min: number;
  shifts: CapacityShift[];
  /** Loading cut-off, `hh:mm` local time or ISO 8601 with offset. */
  cutoff: string | null;
  /**
   * Required boolean (contract agreed with Dev 1; ASM-007, BR-PRP-06). `true` only for the official schedule entered by the
   * Warehouse Manager. Capacity counts as verified ONLY when exactly `true`.
   * `present`, `expected_staff` and `shifts` must never be used to infer verification.
   */
  schedule_verified: boolean;
}

export interface PrepWindow {
  /** Actual START_PREP instant (ISO 8601 with offset) or `null` before preparation starts (Q7). */
  start: string | null;
  end: string;
}

/** One entry per vehicle; an order with several vehicles has several entries. */
export interface LoadingEntry {
  trip_id: number;
  /** ID of the vehicle assigned to this trip by the approved plan. */
  vehicle_id?: number;
  /** Planned loading time: `hh:mm` or ISO 8601 with offset. */
  at: string;
  vehicle_code: string;
  after_cutoff: boolean;
  loaded: boolean;
}

export interface PrepQueueOrder {
  order_id: number;
  order_no: string;
  lines: number;
  weight_kg: number;
  handling_mix: HandlingMixItem[];
  work_min: number;
  prep_window: PrepWindow;
  loading: LoadingEntry[];
  prep_state: PrepState;
  status: OrderStatus;
  /**
   * Server hint, display only. Docs do not define its values, so no logic may depend on it:
   * row actions are derived from `status` and `prep_state` (docs/03 §5.6).
   */
  next_action?: string | null;
}

export interface PrepQueueResponse {
  /** Business day selected by the server, when returned by the API. */
  date?: string;
  capacity: Capacity;
  orders: PrepQueueOrder[];
}

export interface PrepQueueParams {
  warehouse_id: number;
  /** `YYYY-MM-DD` in the market time zone. Omit to use the server's current market day. */
  date?: string;
}
