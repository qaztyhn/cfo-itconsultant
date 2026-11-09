/**
 * Read-only adapter for `GET /warehouses/{id}/prep-queue?date=YYYY-MM-DD` (contract agreed with Dev 1).
 * DEPENDENCY: backend must return 200 with the full payload (docs/06 Appendix A shape, `schedule_verified` required).
 * Numbers are JSON numbers (no decimal strings); `share` is 0–1; times are `HH:mm` or ISO 8601 with offset.
 * The parser checks every field the screen renders, so a wrong payload becomes an error state, never a render crash.
 * Owner: Dev 3 (stream C) — M6.
 */
import { ApiError, apiGet } from "../../../api/client";
import type { Capacity, CapacityShift, LoadingEntry, OrderStatus, PrepQueueOrder, PrepQueueParams, PrepQueueResponse } from "./types";

export const prepQueuePath = (warehouseId: number) => `/warehouses/${warehouseId}/prep-queue`;

export const prepQueueKey = (warehouseId: number | null, date: string | null) => ["prep-queue", warehouseId, date] as const;

type Json = Record<string, unknown>;

function invalid(field: string): never {
  throw new ApiError("INVALID_RESPONSE", "The server returned an unexpected prep queue response.", undefined, { field });
}

const isRecord = (value: unknown): value is Json => typeof value === "object" && value !== null && !Array.isArray(value);
const rec = (value: unknown, field: string): Json => (isRecord(value) ? value : invalid(field));
const arr = (value: unknown, field: string): unknown[] => (Array.isArray(value) ? value : invalid(field));
const str = (value: unknown, field: string): string => (typeof value === "string" ? value : invalid(field));
const num = (value: unknown, field: string): number => (typeof value === "number" && Number.isFinite(value) ? value : invalid(field));
const bool = (value: unknown, field: string): boolean => (typeof value === "boolean" ? value : invalid(field));

function parseShift(value: unknown, field: string): CapacityShift {
  const shift = rec(value, field);
  const share = num(shift.share, `${field}.share`);
  if (share < 0 || share > 1) invalid(`${field}.share`); // 0–1 ratio; 90 would mean a unit mismatch
  return {
    name: str(shift.name, `${field}.name`),
    start: str(shift.start, `${field}.start`),
    end: str(shift.end, `${field}.end`),
    present: num(shift.present, `${field}.present`),
    useful_hours: num(shift.useful_hours, `${field}.useful_hours`),
    share,
    minutes: num(shift.minutes, `${field}.minutes`),
    booked: num(shift.booked, `${field}.booked`),
  };
}

function parseCapacity(value: unknown): Capacity {
  const capacity = rec(value, "capacity");
  const cutoff = capacity.cutoff;
  if (cutoff !== null && typeof cutoff !== "string") invalid("capacity.cutoff");
  return {
    booked_min: num(capacity.booked_min, "capacity.booked_min"),
    total_min: num(capacity.total_min, "capacity.total_min"),
    free_min: num(capacity.free_min, "capacity.free_min"),
    shifts: arr(capacity.shifts, "capacity.shifts").map((item, index) => parseShift(item, `capacity.shifts[${index}]`)),
    cutoff,
    schedule_verified: bool(capacity.schedule_verified, "capacity.schedule_verified"),
  };
}

function parseLoading(value: unknown, field: string): LoadingEntry {
  const entry = rec(value, field);
  return {
    trip_id: num(entry.trip_id, `${field}.trip_id`),
    at: str(entry.at, `${field}.at`),
    vehicle_code: str(entry.vehicle_code, `${field}.vehicle_code`),
    after_cutoff: bool(entry.after_cutoff, `${field}.after_cutoff`),
    loaded: bool(entry.loaded, `${field}.loaded`),
  };
}

function parseOrder(value: unknown, field: string): PrepQueueOrder {
  const order = rec(value, field);
  const prepWindow = rec(order.prep_window, `${field}.prep_window`);
  const state = order.prep_state;
  if (state !== "running" && state !== "paused" && state !== null) invalid(`${field}.prep_state`);
  const nextAction = order.next_action;
  if (nextAction !== undefined && nextAction !== null && typeof nextAction !== "string") invalid(`${field}.next_action`);

  return {
    order_id: num(order.order_id, `${field}.order_id`),
    order_no: str(order.order_no, `${field}.order_no`),
    lines: num(order.lines, `${field}.lines`),
    weight_kg: num(order.weight_kg, `${field}.weight_kg`),
    handling_mix: arr(order.handling_mix, `${field}.handling_mix`).map((item, index) => {
      const group = rec(item, `${field}.handling_mix[${index}]`);
      return { code: str(group.code, `${field}.handling_mix[${index}].code`), name: str(group.name, `${field}.handling_mix[${index}].name`) };
    }),
    work_min: num(order.work_min, `${field}.work_min`),
    // Q7: `start` is the ACTUAL START_PREP instant or null before preparation starts (never synthesized).
    prep_window: {
      start: prepWindow.start === null ? null : str(prepWindow.start, `${field}.prep_window.start`),
      end: str(prepWindow.end, `${field}.prep_window.end`),
    },
    loading: arr(order.loading, `${field}.loading`).map((item, index) => parseLoading(item, `${field}.loading[${index}]`)),
    prep_state: state,
    // Unknown status strings are kept: StatusChip still renders them instead of breaking.
    status: str(order.status, `${field}.status`) as OrderStatus,
    next_action: nextAction ?? null,
  };
}

export function parsePrepQueueResponse(payload: unknown): PrepQueueResponse {
  const root = rec(payload, "response");
  return {
    capacity: parseCapacity(root.capacity),
    orders: arr(root.orders, "orders").map((item, index) => parseOrder(item, `orders[${index}]`)),
  };
}

export async function fetchPrepQueue(params: PrepQueueParams, signal?: AbortSignal): Promise<PrepQueueResponse> {
  const payload = await apiGet<unknown>(prepQueuePath(params.warehouse_id), { date: params.date }, signal);
  return parsePrepQueueResponse(payload);
}