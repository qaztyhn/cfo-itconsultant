/**
 * Client API: fetch có Authorization Bearer, X-Correlation-ID, Idempotency-Key cho endpoint ghi (docs/06 mục 1).
 * Kiểu dữ liệu sinh tự động bằng `npm run gen:api` vào schema.d.ts — KHÔNG viết tay kiểu API (09 mục 9).
 * Lỗi chuẩn {error:{code,message,details,correlation_id}} → ApiError.
 * Owner: Dev 3 (luồng C) — M0.
 */
export class ApiError extends Error {
  constructor(public code: string, message: string, public correlationId?: string, public details?: unknown) {
    super(message);
  }
}

export async function apiFetch<T>(path: string, init: RequestInit & { idempotencyKey?: string } = {}): Promise<T> {
  // TODO(#M0-api-client): base URL từ VITE_API_URL, token từ store, ánh xạ lỗi.
  void path;
  void init;
  throw new Error("not implemented");
}
