/**
 * Hành động điều hướng vào luồng lập kế hoạch từ Order Queue.
 * Dùng API thật (docs/06 mục 6): GET /orders/{id}/planning-runs, POST /orders/{id}/plan.
 * Không đoán runId: thiếu id hợp lệ thì trả null để UI báo lỗi thật.
 */
import { apiGet, apiPost } from "../../../api/client";

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
function positiveId(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null;
}

/**
 * Return only the ABSOLUTE latest run (same run_no / id tie-break as backend).
 * Never skip a newer replan_suggestion to expose an older approvable plan.
 * An expired hold may still be opened for truthful diagnostics / Plan Again.
 */
export async function findLatestRunId(orderId: number): Promise<number | null> {
  const items = record(await apiGet<unknown>(`/orders/${orderId}/planning-runs`)).items;
  if (!Array.isArray(items)) throw new Error("Invalid planning history. Refresh the order queue.");
  if (items.length === 0) return null;

  let latest: { id: number; runNo: number; kind: string; result: string; hold: string | null } | null = null;
  for (const item of items) {
    const entry = record(item);
    const id = positiveId(entry.id);
    const runNo = positiveId(entry.run_no);
    if (id === null || runNo === null || entry.order_id !== orderId
      || typeof entry.kind !== "string" || typeof entry.result !== "string"
      || !(entry.hold_expires_at === null || typeof entry.hold_expires_at === "string")) {
      throw new Error("Invalid planning history. Refresh the order queue.");
    }
    if (latest === null || runNo > latest.runNo || (runNo === latest.runNo && id > latest.id)) {
      latest = { id, runNo, kind: entry.kind, result: entry.result, hold: entry.hold_expires_at };
    }
  }
  if (!latest) return null;
  if (latest.kind === "replan_suggestion") {
    throw new Error("The newest run is a replan suggestion, not an approvable plan. Refresh the queue and review Exceptions.");
  }
  if (latest.result !== "feasible") {
    throw new Error("The newest planning run is not feasible. Refresh the queue and review Exceptions or use Plan Again.");
  }
  if (latest.hold === null || !Number.isFinite(Date.parse(latest.hold))) {
    throw new Error("The newest planning run has no valid hold. Refresh the queue and use Plan Again.");
  }
  // Let Plan Review show the actual expired hold and offer Plan Again; never revive it.
  return latest.id;
}

/** Tạo planning run mới (hành động nghiệp vụ thật, giữ chỗ 15 phút). Trả id run do server cấp. */
export async function startPlanning(orderId: number): Promise<number | null> {
  return positiveId(record(await apiPost<unknown>(`/orders/${orderId}/plan`, {})).id);
}