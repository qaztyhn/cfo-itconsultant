/** Dispatcher manual-plan contract boundary: no client-computed feasibility or safety verdicts. */
export interface ManualOrder {
  id: number;
  order_no: string;
  status: string;
  date_request: { mode: "exact" | "range" | "latest"; date_from: string | null; date_to: string };
  lines: { line_no: number; name: string; qty_base: number | string; sale_unit?: string }[];
}
export interface LoadDraft { line_no: number; qty: string }
export interface VehicleDraft {
  key: number;
  vehicleId: string;
  driverId: string;
  departAt: string;
  etaAt: string;
  loads: LoadDraft[];
}
export interface ManualDraft {
  warehouseId: string;
  targetDate: string;
  goodsReadyAt: string;
  reasonCode: string;
  reasonText: string;
  vehicles: VehicleDraft[];
}
export interface ManualPayload {
  warehouse_id: number;
  target_date: string;
  goods_ready_at: string;
  vehicles: {
    vehicle_id: number;
    driver_employee_id: number;
    load_lines: { line_no: number; qty_base: number }[];
    depart_at: string;
    eta_at: string;
  }[];
  manual_reason_code: string;
  manual_reason_text: string;
}
export const MANUAL_GATES = ["stock", "preparation", "truck", "site_date", "safety"] as const;
export const MANUAL_GATE_LABELS: Record<(typeof MANUAL_GATES)[number], string> = {
  stock: "Stock / ATP",
  preparation: "Warehouse labour and cutoff",
  truck: "Vehicle and driver capacity",
  site_date: "Site and agreed date",
  safety: "Driver hours, mandatory rest and safety",
};
export function validId(value: string): boolean {
  return /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value));
}
export function validInstant(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}
export function allowedDeliveryDate(order: ManualOrder, day: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || (!Number.isFinite(Date.parse(day + "T00:00:00Z")) || new Date(day + "T00:00:00Z").toISOString().slice(0, 10) !== day)) return false;
  const request = order.date_request;
  if (request.mode === "exact") return day === request.date_to;
  if (day > request.date_to) return false;
  return request.date_from === null || day >= request.date_from;
}
export function totalsFor(order: ManualOrder, vehicles: VehicleDraft[]): { lineNo: number; name: string; allocated: number; required: number }[] {
  return order.lines.map(line => ({
    lineNo: line.line_no,
    name: line.name,
    required: Number(line.qty_base),
    allocated: vehicles.reduce((sum, vehicle) => sum + Number(vehicle.loads.find(load => load.line_no === line.line_no)?.qty || 0), 0),
  }));
}
export function validateManualDraft(order: ManualOrder, draft: ManualDraft): string[] {
  const errors: string[] = [];
  if (!["PLANNED", "NO_FEASIBLE_DATE"].includes(order.status)) errors.push("This order is not eligible for manual planning.");
  if (!validId(draft.warehouseId)) errors.push("Select a valid warehouse ID.");
  if (!allowedDeliveryDate(order, draft.targetDate)) errors.push("Delivery date must stay within the customer's agreed request.");
  if (!validInstant(draft.goodsReadyAt)) errors.push("Goods-ready time must include a time zone.");
  if (!draft.reasonCode.trim() || !draft.reasonText.trim()) errors.push("Provide a manual planning reason code and explanation.");
  if (!draft.vehicles.length) errors.push("Add at least one vehicle.");
  const vehicleIds = new Set<string>(), driverIds = new Set<string>();
  draft.vehicles.forEach((vehicle, index) => {
    const label = `Vehicle ${index + 1}`;
    if (!validId(vehicle.vehicleId) || !validId(vehicle.driverId)) errors.push(`${label}: enter valid vehicle and driver IDs.`);
    if (vehicleIds.has(vehicle.vehicleId) || driverIds.has(vehicle.driverId)) errors.push(`${label}: each vehicle and driver must be unique.`);
    vehicleIds.add(vehicle.vehicleId); driverIds.add(vehicle.driverId);
    if (!validInstant(vehicle.departAt) || !validInstant(vehicle.etaAt) ||
        (validInstant(vehicle.departAt) && validInstant(vehicle.etaAt) && Date.parse(vehicle.departAt) >= Date.parse(vehicle.etaAt)) ||
        (validInstant(draft.goodsReadyAt) && validInstant(vehicle.departAt) && Date.parse(draft.goodsReadyAt) > Date.parse(vehicle.departAt))) {
      errors.push(`${label}: provide valid zoned depart/ETA times after goods are ready.`);
    }
    vehicle.loads.forEach(load => {
      const value = Number(load.qty);
      if (load.qty.trim() === "" || !Number.isFinite(value) || value < 0) errors.push(`${label}: invalid quantity for line ${load.line_no}.`);
    });
  });
  for (const total of totalsFor(order, draft.vehicles)) {
    if (!Number.isFinite(total.required) || total.required <= 0 || !Number.isFinite(total.allocated) ||
        Math.abs(total.allocated - total.required) > 0.000001) {
      errors.push(`Line ${total.lineNo}: allocated ${total.allocated} / required ${total.required} (must match exactly).`);
    }
  }
  return errors;
}
export function manualPayload(draft: ManualDraft): ManualPayload {
  return {
    warehouse_id: Number(draft.warehouseId),
    target_date: draft.targetDate,
    goods_ready_at: draft.goodsReadyAt,
    vehicles: draft.vehicles.map(vehicle => ({
      vehicle_id: Number(vehicle.vehicleId),
      driver_employee_id: Number(vehicle.driverId),
      load_lines: vehicle.loads.filter(load => Number(load.qty) > 0).map(load => ({ line_no: load.line_no, qty_base: Number(load.qty) })),
      depart_at: vehicle.departAt,
      eta_at: vehicle.etaAt,
    })),
    manual_reason_code: draft.reasonCode.trim(),
    manual_reason_text: draft.reasonText.trim(),
  };
}
