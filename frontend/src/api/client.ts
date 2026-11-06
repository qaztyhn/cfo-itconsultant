/**
 * Client API: fetch có Authorization Bearer, X-Correlation-ID, Idempotency-Key cho endpoint ghi (docs/06 mục 1).
 * Kiểu dữ liệu sinh tự động bằng `npm run gen:api` vào schema.d.ts — KHÔNG viết tay kiểu API (09 mục 9).
 * Lỗi chuẩn {error:{code,message,details,correlation_id}} → ApiError.
 * Owner: Dev 3 (luồng C) — M0.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public correlationId?: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getToken(): string | null {
  return localStorage.getItem("cfo_token");
}

function correlationId(): string {
  return crypto.randomUUID();
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { idempotencyKey?: string } = {},
): Promise<T> {
  const { idempotencyKey, headers: extraHeaders, ...rest } = init;

  const token = getToken();
  const cid = correlationId();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Correlation-ID": cid,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    ...(extraHeaders as Record<string, string> | undefined),
  };

  const response = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers,
  });

  if (!response.ok) {
    let code = "UNKNOWN_ERROR";
    let message = `HTTP ${response.status}`;
    let details: unknown;
    let correlationIdFromResponse: string | undefined;

    try {
      const body = (await response.json()) as {
        error?: { code: string; message: string; details?: unknown; correlation_id?: string };
      };
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
        details = body.error.details;
        correlationIdFromResponse = body.error.correlation_id;
      }
    } catch {
      // non-JSON body
    }

    throw new ApiError(code, message, correlationIdFromResponse ?? cid, details);
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return response.json() as Promise<T>;
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "GET" });
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  idempotencyKey?: string,
): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    idempotencyKey,
  });
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function apiDelete(path: string): Promise<void> {
  return apiFetch<void>(path, { method: "DELETE" });
}
