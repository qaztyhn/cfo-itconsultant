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
 * Select the absolute latest backend planning run for INSPECTION, not approval.
 * Backend approval checks run_no/id again and requires current feasible hold.
 * Never skip a newer infeasible run or replan_suggestion to show an older
 * approvable candidate. Unheld/expired runs are still useful diagnostics.
 */
export async function findLatestRunId(orderId: number): Promise<number | null> {
  const items = record(await apiGet<unknown>(`/orders/${orderId}/planning-runs`)).items;
  if (!Array.isArray(items)) throw new Error("Invalid planning history. Refresh the order queue.");
  if (items.length === 0) return null;

  let latest: { id: number; runNo: number } | null = null;
  for (const item of items) {
    const entry = record(item);
    const id = positiveId(entry.id);
    const runNo = positiveId(entry.run_no);
    if (id === null || runNo === null || entry.order_id !== orderId
      || !["initial", "rerun", "replan_suggestion"].includes(String(entry.kind))
      || !["feasible", "infeasible"].includes(String(entry.result))
      || !(entry.hold_expires_at === null || (
        typeof entry.hold_expires_at === "string"
        && /(?:Z|[+-]\\d\\d:\\d\\d)$/.test(entry.hold_expires_at)
        && Number.isFinite(Date.parse(entry.hold_expires_at))
      ))) {
      throw new Error("Invalid planning history. Refresh the order queue.");
    }
    if (latest === null || runNo > latest.runNo || (runNo === latest.runNo && id > latest.id)) {
      latest = { id, runNo };
    }
  }
  return latest?.id ?? null;
}

/** Tạo planning run mới (hành động nghiệp vụ thật, giữ chỗ 15 phút). Trả id run do server cấp. */
export async function startPlanning(orderId: number): Promise<number | null> {
  return positiveId(record(await apiPost<unknown>(`/orders/${orderId}/plan`, {})).id);
}