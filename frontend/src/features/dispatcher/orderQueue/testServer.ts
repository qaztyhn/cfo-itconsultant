/**
 * Helper MSW cục bộ cho các test render màn Order queue. Cố ý KHÔNG thêm vào api/mocks/handlers.ts dùng chung.
 */
import { http, HttpResponse, type RequestHandler } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { API_BASE_URL } from "../../../api/config";

export const ORDERS_URL = `${API_BASE_URL}/orders`;
export const COUNTS_URL = `${API_BASE_URL}/orders/counts`;
export const OVERVIEW_URL = `${API_BASE_URL}/integration/overview`;

export const emptyQueueHandlers: RequestHandler[] = [
  http.get(ORDERS_URL, () => HttpResponse.json({ items: [], page: 1, page_size: 50, total: 0 })),
  http.get(COUNTS_URL, () =>
    HttpResponse.json({
      all: 0, needs_plan: 0, awaiting_approval: 0, no_feasible_date: 0, in_execution: 0,
      replan_suggested: 0, delivered_today: 0, nav: { order_queue: 0, exceptions: 0, tracking_risk: 0 },
    }),
  ),
  http.get(OVERVIEW_URL, () => HttpResponse.json({ sources: [], stale: false })),
];

/** Gọi ở top-level của file test. Trả về server để test có thể server.use(...) ghi đè handler. */
export function useOrderQueueMsw(...extra: RequestHandler[]) {
  const server = setupServer(...emptyQueueHandlers, ...extra);
  let mswFetch: typeof fetch;

  beforeAll(() => {
    server.listen({ onUnhandledRequest: "error" });
    // Workaround chỉ dùng cho test (giống PrepQueue.test.tsx): Node fetch từ chối AbortSignal của jsdom.
    mswFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => mswFetch(input, { ...init, signal: undefined }));
  });
  afterEach(() => server.resetHandlers());
  afterAll(() => {
    vi.unstubAllGlobals();
    server.close();
  });

  return server;
}