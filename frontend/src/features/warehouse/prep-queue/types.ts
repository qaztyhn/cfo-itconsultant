/**
 * Local types for the Warehouse Prep Queue (docs/06 Appendix A / A.1, `GET /warehouses/{id}/prep-queue?date=`).
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
  /** ISO 8601 with offset (overnight shifts and DST aware); `hh:mm` is also tolerated. */
  start: string;
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
   * Required boolean (A.1, ASM-007/Q12d). Capacity counts as verified ONLY when exactly `true`; `false` means the
   * official schedule is missing/unverified: totals are 0 and the UI must say "Capacity not verified".
   */
  schedule_verified: boolean;
}

export interface PrepWindow {
  /** ISO 8601 with offset; `null` until preparation actually starts (planned start is not persisted). */
  start: string | null;
  /** ISO 8601 with offset (actual GOODS_READY, else planned). */
  end: string;
}

/** One entry per vehicle; an order with several vehicles has several entries. */
export interface LoadingEntry {
  trip_id: number;
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
  next_action: string | null;
}

export interface PrepQueueResponse {
  capacity: Capacity;
  orders: PrepQueueOrder[];
}

export interface PrepQueueParams {
  warehouse_id: number;
  /** `YYYY-MM-DD` in the market time zone. */
  date: string;
}