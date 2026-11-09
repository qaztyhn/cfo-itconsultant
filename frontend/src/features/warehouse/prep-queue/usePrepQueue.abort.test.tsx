import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { fetchPrepQueue } from "./api";
import { buildPrepQueueFixture, FIXTURE_DATE } from "./fixtures";
import { usePrepQueue } from "./usePrepQueue";

// Only fetchPrepQueue is replaced: the query key helper stays real.
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, fetchPrepQueue: vi.fn() };
});

const fetchMock = fetchPrepQueue as unknown as Mock;
const NEXT_DATE = "2026-11-13";

/** The signal that TanStack Query passed to the n-th call of fetchPrepQueue. */
const signalOf = (call: number): AbortSignal => fetchMock.mock.calls[call][1] as AbortSignal;

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  fetchMock.mockReset();
});

describe("usePrepQueue request cancellation", () => {
  it("passes an AbortSignal to fetchPrepQueue", async () => {
    fetchMock.mockImplementation(() => new Promise(() => {}));

    renderHook(() => usePrepQueue(1, FIXTURE_DATE), { wrapper: createWrapper() });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0][0]).toEqual({ warehouse_id: 1, date: FIXTURE_DATE });
    expect(signalOf(0)).toBeInstanceOf(AbortSignal);
    expect(signalOf(0).aborted).toBe(false);
  });

  it("aborts the in-flight request when the warehouse changes", async () => {
    fetchMock.mockImplementation(() => new Promise(() => {}));

    const { rerender } = renderHook(({ warehouseId }) => usePrepQueue(warehouseId, FIXTURE_DATE), {
      wrapper: createWrapper(),
      initialProps: { warehouseId: 1 },
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    rerender({ warehouseId: 2 });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toEqual({ warehouse_id: 2, date: FIXTURE_DATE });
    expect(signalOf(0).aborted).toBe(true);
    expect(signalOf(1).aborted).toBe(false);
  });

  it("aborts the in-flight request on unmount", async () => {
    fetchMock.mockImplementation(() => new Promise(() => {}));

    const { unmount } = renderHook(() => usePrepQueue(1, FIXTURE_DATE), { wrapper: createWrapper() });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    unmount();

    await waitFor(() => expect(signalOf(0).aborted).toBe(true));
  });
});

describe("usePrepQueue date change", () => {
  it("does not show the previous date's queue while the new date is loading", async () => {
    fetchMock.mockImplementationOnce(async () => buildPrepQueueFixture("verified"));
    fetchMock.mockImplementationOnce(() => new Promise(() => {}));

    const { result, rerender } = renderHook(({ date }) => usePrepQueue(1, date), {
      wrapper: createWrapper(),
      initialProps: { date: FIXTURE_DATE },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeDefined();

    // Local midnight passed: the date (and with it the query key) changes.
    rerender({ date: NEXT_DATE });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][0]).toEqual({ warehouse_id: 1, date: NEXT_DATE });
    expect(result.current.data).toBeUndefined();
    expect(result.current.isPending).toBe(true);
  });
});