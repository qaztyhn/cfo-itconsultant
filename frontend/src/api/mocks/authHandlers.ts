/**
 * MSW handlers cho xác thực theo docs/06 mục 4. Owner: Dev 3 (luồng C) — M0.
 * Mock KHÔNG lưu mật khẩu nào (09 bất biến 25): email demo đã biết + mật khẩu không rỗng → 200.
 * Email lạ → 401 AUTH_INVALID. 5 lần sai liên tiếp trong 60 giây → 429 (06: "quá 5 lần/phút").
 * Mock PASS không chứng minh tích hợp thật PASS.
 */
import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "../config";
import type { AuthUser, LoginRequest, LoginResponse } from "../contracts/auth";

export const MOCK_TOKEN_PREFIX = "mock-jwt.";
const EXPIRES_IN_SECONDS = 28_800;
const MAX_FAILED_ATTEMPTS = 5;
const WINDOW_MS = 60_000;

export interface MockAccount {
  email: string;
  user: AuthUser;
}

const common = { market: "SE", locale: "en" };

/** Email theo docs/08 mục 5 (driver1@ chưa được xác nhận — chờ Dev 2). id/employee_id/location_ids chỉ là giá trị mock. */
export const MOCK_ACCOUNTS: MockAccount[] = [
  { email: "dispatcher@cfo.demo", user: { id: 1, employee_id: 101, name: "Anna Lindqvist", roles: ["dispatcher"], kpi_scopes: ["ops"], location_ids: [4], ...common } },
  { email: "wm.got@cfo.demo", user: { id: 2, employee_id: 102, name: "Lars Johansson", roles: ["warehouse"], kpi_scopes: ["ops"], location_ids: [1], ...common } },
  { email: "sales@cfo.demo", user: { id: 3, employee_id: 103, name: "Maria Nilsson", roles: ["sales"], kpi_scopes: [], location_ids: [101], ...common } },
  { email: "driver1@cfo.demo", user: { id: 4, employee_id: 104, name: "Björn Eriksson", roles: ["driver"], kpi_scopes: [], location_ids: [1], ...common } },
  { email: "admin@cfo.demo", user: { id: 5, employee_id: 105, name: "Erik Svensson", roles: ["admin"], kpi_scopes: [], location_ids: [], ...common } },
  { email: "cs@cfo.demo", user: { id: 6, employee_id: 106, name: "Sara Gustafsson", roles: ["customer_service"], kpi_scopes: [], location_ids: [], ...common } },
  { email: "owner@cfo.demo", user: { id: 7, employee_id: 107, name: "Henrik Andersson", roles: ["viewer"], kpi_scopes: ["revenue_all"], location_ids: [], ...common } },
  { email: "projectlead@cfo.demo", user: { id: 8, employee_id: 108, name: "Ingrid Larsson", roles: ["viewer"], kpi_scopes: ["ops"], location_ids: [], ...common } },
];

const failures = new Map<string, number[]>();

function recentFailureCount(email: string): number {
  const now = Date.now();
  const recent = (failures.get(email) ?? []).filter((t) => now - t < WINDOW_MS);
  failures.set(email, recent);
  return recent.length;
}

export function resetLoginRateLimit(): void {
  failures.clear();
}

function errorResponse(request: Request, status: number, code: string, message: string) {
  const cid = request.headers.get("X-Correlation-ID") ?? crypto.randomUUID();
  return HttpResponse.json({ error: { code, message, correlation_id: cid } }, { status, headers: { "X-Correlation-ID": cid } });
}

function accountFromRequest(request: Request): MockAccount | undefined {
  const header = request.headers.get("Authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice("Bearer ".length) : "";
  if (!token.startsWith(MOCK_TOKEN_PREFIX)) {
    return undefined;
  }
  const id = Number(token.slice(MOCK_TOKEN_PREFIX.length));
  return MOCK_ACCOUNTS.find((a) => a.user.id === id);
}

const url = (path: string) => `${API_BASE_URL}${path}`;

export const authHandlers = [
  http.post(url("/auth/login"), async ({ request }) => {
    const body = (await request.json().catch(() => null)) as Partial<LoginRequest> | null;
    const email = typeof body?.email === "string" ? body.email.trim().toLowerCase() : "";
    const secret = typeof body?.password === "string" ? body.password : "";

    if (!email || !secret) {
      return errorResponse(request, 422, "VALIDATION_ERROR", "Email and password are required.");
    }
    if (recentFailureCount(email) >= MAX_FAILED_ATTEMPTS) {
      return errorResponse(request, 429, "RATE_LIMITED", "Too many attempts, try again in a minute.");
    }

    const account = MOCK_ACCOUNTS.find((a) => a.email === email);
    if (!account) {
      failures.set(email, [...(failures.get(email) ?? []), Date.now()]);
      return errorResponse(request, 401, "AUTH_INVALID", "Invalid email or password.");
    }

    failures.delete(email);
    const response: LoginResponse = {
      access_token: `${MOCK_TOKEN_PREFIX}${account.user.id}`,
      token_type: "bearer",
      expires_in: EXPIRES_IN_SECONDS,
      user: account.user,
    };
    return HttpResponse.json(response);
  }),

  http.get(url("/auth/me"), ({ request }) => {
    const account = accountFromRequest(request);
    return account ? HttpResponse.json(account.user) : errorResponse(request, 401, "AUTH_INVALID", "Not signed in or token expired.");
  }),

  http.post(url("/auth/logout"), () => new HttpResponse(null, { status: 204 })),
];