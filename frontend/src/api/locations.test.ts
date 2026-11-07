import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { API_BASE_URL } from "./config";
import { fetchLocations } from "./locations";

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const makeItems = (firstId: number, count: number) =>
  Array.from({ length: count }, (_, i) => ({
    id: firstId + i,
    code: `L${firstId + i}`,
    name: `Location ${firstId + i}`,
    type: "warehouse",
  }));

/** Giả lập backend phân trang như GET /locations (06 mục 1): { items, page, page_size, total }. */
function servePaged(total: number, requested: URLSearchParams[]) {
  server.use(
    http.get(`${API_BASE_URL}/locations`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      requested.push(params);
      const page = Number(params.get("page"));
      const pageSize = Number(params.get("page_size"));
      const start = (page - 1) * pageSize;
      const count = Math.max(0, Math.min(pageSize, total - start));
      return HttpResponse.json({ items: makeItems(start + 1, count), page, page_size: pageSize, total });
    }),
  );
}

describe("fetchLocations", () => {
  it("reads every page, not just the first one (more than 200 locations)", async () => {
    const requested: URLSearchParams[] = [];
    servePaged(450, requested);

    const result = await fetchLocations();

    expect(result).toHaveLength(450);
    expect(new Set(result.map((l) => l.id)).size).toBe(450);
    expect(requested.map((p) => p.get("page"))).toEqual(["1", "2", "3"]);
    expect(requested.every((p) => p.get("page_size") === "200")).toBe(true);
  });

  it("stops after one request when the total fits exactly in a full page", async () => {
    const requested: URLSearchParams[] = [];
    servePaged(200, requested);

    expect(await fetchLocations()).toHaveLength(200);
    expect(requested).toHaveLength(1);
  });

  it("handles a response without total or page_size (MSW demo shape)", async () => {
    server.use(http.get(`${API_BASE_URL}/locations`, () => HttpResponse.json({ items: makeItems(1, 3) })));

    expect(await fetchLocations()).toHaveLength(3);
  });

  it("returns an empty list when there are no locations", async () => {
    const requested: URLSearchParams[] = [];
    servePaged(0, requested);

    expect(await fetchLocations()).toEqual([]);
    expect(requested).toHaveLength(1);
  });
});
