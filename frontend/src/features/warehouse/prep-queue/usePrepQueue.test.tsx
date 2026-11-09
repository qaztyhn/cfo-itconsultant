import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import type { ReactNode } from "react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import { FIXTURE_DATE, orderApproved } from "./fixtures";
import { prepQueueFailure, prepQueueSuccess } from "./mswHandlers";
import { PREP_QUEUE_POLL_MS, pollInterval, usePrepQueue } from "./usePrepQueue";
import { buildPrepQueueFixture } from "./fixtures";

const server = setupServer();

let mswFetch: typeof fetch;

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // Test-only workaround: jsdom's AbortSignal is not accepted by Node's fetch, which apiFetch reports as NETWORK_ERROR.
  // Production code still passes the signal so TanStack Query can cancel requests.
  mswFetch = globalThis.fetch;
  vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => mswFetch(input, { ...init, signal: undefined }));
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  vi.unstubAllGlobals();
  server.close();
});

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("usePrepQueue", () => {
  it("does not request anything without a warehouse", () => {
    const seen = vi.fn();
    server.use(prepQueueSuccess(undefined, seen));

    const { result } = renderHook(() => usePrepQueue(null, FIXTURE_DATE), { wrapper: createWrapper() });

    expect(result.current.fetchStatus).toBe("idle");
    expect(seen).not.toHaveBeenCalled();
  });

  it("loads the queue for a warehouse and date", async () => {
    server.use(prepQueueSuccess());

    const { result } = renderHook(() => usePrepQueue(1, FIXTURE_DATE), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.orders).toHaveLength(5);
  });

  it("exposes a 403 as an ApiError", async () => {
    server.use(prepQueueFailure(403, "FORBIDDEN", "Not allowed", "corr-403"));

    const { result } = renderHook(() => usePrepQueue(1, FIXTURE_DATE), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect(result.current.error).toMatchObject({ code: "FORBIDDEN", correlationId: "corr-403" });
  });

  it("never drops the data across a refetch, then shows the new data", async () => {
    server.use(prepQueueSuccess());
    const lengths: Array<number | undefined> = [];
    const { result } = renderHook(
      () => {
        const query = usePrepQueue(1, FIXTURE_DATE);
        lengths.push(query.data?.orders.length);
        return query;
      },
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const loadedAt = lengths.findIndex((length) => length !== undefined);

    const updated = buildPrepQueueFixture("verified");
    updated.orders.push({ ...orderApproved(), order_id: 170, order_no: "SE-2026-000170" });
    server.use(prepQueueSuccess(updated));
    await act(async () => {
      await result.current.refetch();
    });

    await waitFor(() => expect(result.current.data?.orders).toHaveLength(6));
    // From the first render that had data, no render may show "no data" (a form/dialog open on the screen stays mounted).
    expect(lengths.slice(loadedAt).every((length) => length !== undefined)).toBe(true);
  });

  it("never shows another warehouse's queue while the new one loads", async () => {
    server.use(prepQueueSuccess());
    const { result, rerender } = renderHook(({ id }: { id: number }) => usePrepQueue(id, FIXTURE_DATE), {
      wrapper: createWrapper(),
      initialProps: { id: 1 },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    rerender({ id: 2 });

    expect(result.current.data).toBeUndefined();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe("pollInterval", () => {
  it("polls every 20 seconds by default and after transient errors", () => {
    expect(PREP_QUEUE_POLL_MS).toBe(20_000);
    expect(pollInterval(null)).toBe(PREP_QUEUE_POLL_MS);
    expect(pollInterval(new ApiError("UNKNOWN_ERROR", "Server error", "c", undefined, 500))).toBe(PREP_QUEUE_POLL_MS);
    expect(pollInterval(new ApiError("NETWORK_ERROR", "Offline", "c", undefined, 0))).toBe(PREP_QUEUE_POLL_MS);
  });

  it("stops polling on 401, 403 and 404", () => {
    for (const status of [401, 403, 404]) {
      expect(pollInterval(new ApiError("X", "x", "c", undefined, status))).toBe(false);
    }
  });
});