/**
 * Synthetic scenarios for the Prep Queue (docs/06 Appendix A shape). Fictional data only: no PII, no GPS.
 * Used by local MSW handlers and tests; NOT registered in the shared mock handlers (`api/mocks/handlers.ts`).
 * Each builder returns a fresh object so tests can mutate it safely.
 * Owner: Dev 3 (stream C) — M6.
 */
import type { Capacity, PrepQueueOrder, PrepQueueResponse } from "./types";

export const FIXTURE_WAREHOUSE_ID = 1;
export const FIXTURE_DATE = "2026-11-12";

/** Approved plan, prep not started. */
export function orderApproved(): PrepQueueOrder {
  return {
    order_id: 137,
    order_no: "SE-2026-000137",
    lines: 6,
    weight_kg: 3340,
    handling_mix: [
      { code: "N2", name: "Boards, sheets & tiles" },
      { code: "N1", name: "Small items & accessories" },
    ],
    work_min: 130,
    prep_window: { start: "06:00", end: "08:10" },
    loading: [{ trip_id: 930, at: "08:30", vehicle_code: "GBG-12-03", after_cutoff: false, loaded: false }],
    prep_state: null,
    status: "APPROVED",
    next_action: null,
  };
}

/** PREPARING and the crew is working. */
export function orderRunning(): PrepQueueOrder {
  return {
    order_id: 141,
    order_no: "SE-2026-000141",
    lines: 3,
    weight_kg: 2800,
    handling_mix: [{ code: "N3", name: "Bagged cement & mortar" }],
    work_min: 195,
    prep_window: { start: "07:00", end: "10:15" },
    loading: [{ trip_id: 931, at: "11:00", vehicle_code: "GBG-18-01", after_cutoff: false, loaded: false }],
    prep_state: "running",
    status: "PREPARING",
    next_action: null,
  };
}

/** PREPARING but PREP_PAUSED was recorded (order status does not change while paused). */
export function orderPaused(): PrepQueueOrder {
  return {
    order_id: 152,
    order_no: "SE-2026-000152",
    lines: 4,
    weight_kg: 1960,
    handling_mix: [{ code: "N5", name: "Long goods" }],
    work_min: 90,
    prep_window: { start: "08:00", end: "09:30" },
    loading: [{ trip_id: 932, at: "10:30", vehicle_code: "GBG-03-02", after_cutoff: false, loaded: false }],
    prep_state: "paused",
    status: "PREPARING",
    next_action: null,
  };
}

/** GOODS_READY with two vehicles; the first is already loaded, the second is not. */
export function orderMultiVehicle(): PrepQueueOrder {
  return {
    order_id: 158,
    order_no: "SE-2026-000158",
    lines: 9,
    weight_kg: 24000,
    handling_mix: [
      { code: "N4", name: "Bulk materials" },
      { code: "N2", name: "Boards, sheets & tiles" },
    ],
    work_min: 320,
    prep_window: { start: "06:00", end: "11:20" },
    loading: [
      { trip_id: 941, at: "12:00", vehicle_code: "GBG-18-04", after_cutoff: false, loaded: true },
      { trip_id: 942, at: "12:15", vehicle_code: "GBG-18-05", after_cutoff: false, loaded: false },
    ],
    prep_state: null,
    status: "GOODS_READY",
    next_action: null,
  };
}

/** GOODS_READY whose loading falls after the cut-off, on the next day (ISO 8601 with offset). */
export function orderAfterCutoff(): PrepQueueOrder {
  return {
    order_id: 163,
    order_no: "SE-2026-000163",
    lines: 2,
    weight_kg: 640,
    handling_mix: [{ code: "N1", name: "Small items & accessories" }],
    work_min: 45,
    prep_window: { start: "13:00", end: "13:45" },
    loading: [{ trip_id: 950, at: "2026-11-13T05:00:00Z", vehicle_code: "GBG-12-02", after_cutoff: true, loaded: false }],
    prep_state: null,
    status: "GOODS_READY",
    next_action: null,
  };
}

/** Official schedule: Shift 1 (8 present) fully booked, Shift 2 (6 present) partly booked. Totals are consistent. */
export function capacityVerified(): Capacity {
  return {
    booked_min: 4524,
    total_min: 5292,
    free_min: 768,
    shifts: [
      { name: "Shift 1", start: "06:00", end: "14:00", present: 8, useful_hours: 7, share: 0.9, minutes: 3024, booked: 3024 },
      { name: "Shift 2", start: "14:00", end: "22:00", present: 6, useful_hours: 7, share: 0.9, minutes: 2268, booked: 1500 },
    ],
    cutoff: "15:00",
    schedule_verified: true,
  };
}

/** Same people present, but the API does NOT say the schedule is verified (`schedule_verified` absent). */
export function capacityUnverified(): Capacity {
  const { schedule_verified: _omitted, ...rest } = capacityVerified();
  void _omitted;
  return rest;
}

/** No official schedule: nothing counts as capacity. */
export function capacityNoSchedule(): Capacity {
  return { booked_min: 0, total_min: 0, free_min: 0, shifts: [], cutoff: "15:00", schedule_verified: false };
}

export type PrepQueueScenario = "verified" | "unverified" | "noSchedule" | "empty";

export function buildPrepQueueFixture(scenario: PrepQueueScenario = "verified"): PrepQueueResponse {
  switch (scenario) {
    case "verified":
      return {
        capacity: capacityVerified(),
        orders: [orderApproved(), orderRunning(), orderPaused(), orderMultiVehicle(), orderAfterCutoff()],
      };
    case "unverified":
      return { capacity: capacityUnverified(), orders: [orderApproved(), orderRunning()] };
    case "noSchedule":
      return { capacity: capacityNoSchedule(), orders: [orderApproved()] };
    case "empty":
      return { capacity: capacityVerified(), orders: [] };
  }
}