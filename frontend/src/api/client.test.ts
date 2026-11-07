import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../app/store";
import { ApiError, apiFetch, apiGet, apiPost, buildQuery, isApiError, newIdempotencyKey } from "./client";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" }, ...init });
}

function lastCall(): { url: string; headers: Headers; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1];
  return { url: String(url), headers: new Headers(init?.headers), init: init ?? {} };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  useAuthStore.setState({ token: null, user: null });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ApiError", () => {
  it("preserves the API error data needed by the UI", () => {
    const details = { field: "date_from", reason: "invalid" };
    const error = new ApiError("VALIDATION_ERROR", "Invalid delivery date", "corr-123", details);

    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe("Invalid delivery date");
    expect(error.code).toBe("VALIDATION_ERROR");
    expect(error.correlationId).toBe("corr-123");
    expect(error.details).toBe(details);
  });
});

describe("buildQuery", () => {
  it("skips undefined, null and empty values and encodes the rest", () => {
    expect(buildQuery({ status: "PLANNED", q: "", page: 2, blocked: false, x: undefined, y: null, name: "a b&c" })).toBe(
      "?status=PLANNED&page=2&blocked=false&name=a+b%26c",
    );
  });

  it("returns an empty string when nothing is set", () => {
    expect(buildQuery()).toBe("");
    expect(buildQuery({ q: "" })).toBe("");
  });
});

describe("apiFetch requests (docs/06 mục 1)", () => {
  it("builds the URL under /api/v1 without a double slash", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }));
    await apiGet("/orders", { status: "PLANNED" });

    const { url } = lastCall();
    expect(url).toMatch(/\/orders\?status=PLANNED$/);
    expect(url).not.toMatch(/[^:]\/\/orders/);
  });

  it("sends a Bearer token and a fresh X-Correlation-ID, and no Content-Type on GET", async () => {
    useAuthStore.setState({ token: "jwt-123" });
    fetchMock.mockResolvedValue(jsonResponse({}));
    await apiGet("/orders");

    const { headers } = lastCall();
    expect(headers.get("Authorization")).toBe("Bearer jwt-123");
    expect(headers.get("X-Correlation-ID")).toMatch(/^[0-9a-f-]{36}$/);
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("omits Authorization when signed out", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await apiGet("/orders");
    expect(lastCall().headers.has("Authorization")).toBe(false);
  });

  it("sends JSON body, Content-Type and Idempotency-Key on writes", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    const key = newIdempotencyKey();
    await apiPost("/orders/1/events", { type: "START_PREP" }, key);

    const { headers, init } = lastCall();
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ type: "START_PREP" }));
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("Idempotency-Key")).toBe(key);
  });

  it("returns undefined for 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiFetch("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });
});

describe("apiFetch errors (docs/06 mục 1.1)", () => {
  it("maps the standard error body to ApiError", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "HOLD_EXPIRED", message: "Planning hold expired. Re-run planning.", details: { run_id: 812 }, correlation_id: "srv-1" } },
        { status: 409 },
      ),
    );

    const error = await apiGet("/planning-runs/812").catch((e: unknown) => e);
    expect(isApiError(error)).toBe(true);
    expect(error).toMatchObject({
      code: "HOLD_EXPIRED",
      message: "Planning hold expired. Re-run planning.",
      details: { run_id: 812 },
      correlationId: "srv-1",
      status: 409,
    });
  });

  it("falls back to the response header and a status-based code when the body is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("Bad gateway", { status: 403, headers: { "X-Correlation-ID": "hdr-9" } }));

    await expect(apiGet("/kpi/summary")).rejects.toMatchObject({ code: "FORBIDDEN", correlationId: "hdr-9", status: 403 });
  });

  it("keeps 429 so the sign-in form can show the rate-limit message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: "RATE_LIMITED", message: "Too many attempts" } }, { status: 429 }));

    await expect(apiPost("/auth/login", { email: "a@b.c", password: "x" })).rejects.toMatchObject({ status: 429 });
  });

  it("turns a network failure into NETWORK_ERROR with a correlation id", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(apiGet("/orders")).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0, correlationId: expect.any(String) });
  });

  it("rethrows AbortError untouched", async () => {
    fetchMock.mockRejectedValue(new DOMException("Aborted", "AbortError"));

    await expect(apiGet("/orders")).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("session expiry on 401", () => {
  it("clears the stored session when a token was sent and the API answers 401", async () => {
    useAuthStore.setState({ token: "expired" });
    window.localStorage.setItem("cfo_token", "expired");
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: "AUTH_INVALID", message: "Token expired" } }, { status: 401 }));

    await expect(apiGet("/auth/me")).rejects.toMatchObject({ code: "AUTH_INVALID", status: 401 });
    expect(useAuthStore.getState().token).toBeNull();
    expect(window.localStorage.getItem("cfo_token")).toBeNull();
  });

  it("does not treat a wrong password on /auth/login as an expired session", async () => {
    useAuthStore.setState({ token: "still-valid" });
    fetchMock.mockResolvedValue(jsonResponse({ error: { code: "AUTH_INVALID", message: "Invalid email or password." } }, { status: 401 }));

    await expect(apiPost("/auth/login", { email: "a@b.c", password: "x" })).rejects.toMatchObject({ code: "AUTH_INVALID" });
    expect(useAuthStore.getState().token).toBe("still-valid");
  });
});