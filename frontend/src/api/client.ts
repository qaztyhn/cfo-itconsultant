/**
 * Client API: fetch có Authorization Bearer, X-Correlation-ID, Idempotency-Key cho endpoint ghi (docs/06 mục 1).
 * Kiểu dữ liệu API sinh bằng `npm run gen:api` vào schema.d.ts — KHÔNG viết tay kiểu API (09 mục 9).
 * DEPENDENCY: schema.d.ts chưa có (chờ Dev 1/2 xuất OpenAPI); tới lúc đó apiFetch<T> nhận T do nơi gọi khai báo.
 * Lỗi chuẩn {error:{code,message,details,correlation_id}} → ApiError.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { useAuthStore } from "../app/store";

const DEFAULT_BASE_URL = "http://localhost:8000/api/v1";
const BASE_URL = ((import.meta.env.VITE_API_URL as string | undefined) ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
const LOGIN_PATH = "/auth/login";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public correlationId?: string,
    public details?: unknown,
    public status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue>;

/** Dựng query string; bỏ tham số undefined, null và chuỗi rỗng (vd. ô tìm kiếm trống). */
export function buildQuery(params?: QueryParams): string {
  if (!params) {
    return "";
  }
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.append(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/** Idempotency-Key cho các endpoint ghi nêu ở 06 mục 1 (approve, events, manual-plan, transfers, notifications/send). */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

interface ErrorBody {
  error?: { code?: string; message?: string; details?: unknown; correlation_id?: string };
}

function fallbackCode(status: number): string {
  switch (status) {
    case 401:
      return "AUTH_INVALID";
    case 403:
      return "FORBIDDEN";
    case 422:
      return "VALIDATION_ERROR";
    default:
      return "UNKNOWN_ERROR";
  }
}

async function toApiError(response: Response, fallbackCorrelationId: string): Promise<ApiError> {
  const body = (await response.json().catch(() => null)) as ErrorBody | null;
  const error = body?.error;
  return new ApiError(
    error?.code ?? fallbackCode(response.status),
    error?.message ?? `HTTP ${response.status}`,
    error?.correlation_id ?? response.headers.get("X-Correlation-ID") ?? fallbackCorrelationId,
    error?.details,
    response.status,
  );
}

export type ApiFetchInit = RequestInit & { idempotencyKey?: string };

export async function apiFetch<T>(path: string, init: ApiFetchInit = {}): Promise<T> {
  const { idempotencyKey, headers: extraHeaders, ...rest } = init;

  const token = useAuthStore.getState().token;
  const cid = crypto.randomUUID();

  const headers = new Headers(extraHeaders);
  headers.set("Accept", "application/json");
  headers.set("X-Correlation-ID", cid);
  if (rest.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (idempotencyKey) {
    headers.set("Idempotency-Key", idempotencyKey);
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...rest, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error; // TanStack Query hủy request: không phải lỗi API
    }
    throw new ApiError("NETWORK_ERROR", "Cannot reach the server. Check your connection and retry.", cid, undefined, 0);
  }

  if (!response.ok) {
    const apiError = await toApiError(response, cid);
    // Token hết hạn/bị thu hồi (8 giờ, 06 mục 4). Sai mật khẩu ở /auth/login KHÔNG làm mất phiên.
    if (response.status === 401 && token && !path.startsWith(LOGIN_PATH)) {
      useAuthStore.getState().clearAuth();
    }
    throw apiError;
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  return (await response.json()) as T;
}

export function apiGet<T>(path: string, params?: QueryParams, signal?: AbortSignal): Promise<T> {
  return apiFetch<T>(`${path}${buildQuery(params)}`, { method: "GET", signal });
}

export function apiPost<T>(path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
    idempotencyKey,
  });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export function apiDelete(path: string): Promise<void> {
  return apiFetch<void>(path, { method: "DELETE" });
}