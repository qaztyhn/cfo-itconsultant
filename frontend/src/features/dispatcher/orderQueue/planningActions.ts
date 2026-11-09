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

/** Run mới nhất (run_no lớn nhất) của đơn, bỏ qua replan_suggestion. null nếu không có run hợp lệ. */
export async function findLatestRunId(orderId: number): Promise<number | null> {
  const items = record(await apiGet<unknown>(`/orders/${orderId}/planning-runs`)).items;
  if (!Array.isArray(items)) return null;
  let best: { id: number; runNo: number } | null = null;
  for (const item of items) {
    const entry = record(item);
    const id = positiveId(entry.id);
    const runNo = typeof entry.run_no === "number" ? entry.run_no : null;
    if (id === null || runNo === null || entry.kind === "replan_suggestion") continue;
    if (best === null || runNo > best.runNo) best = { id, runNo };
  }
  return best ? best.id : null;
}

/** Tạo planning run mới (hành động nghiệp vụ thật, giữ chỗ 15 phút). Trả id run do server cấp. */
export async function startPlanning(orderId: number): Promise<number | null> {
  return positiveId(record(await apiPost<unknown>(`/orders/${orderId}/plan`, {})).id);
}