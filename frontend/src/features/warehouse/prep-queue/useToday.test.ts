import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TODAY_CHECK_MS, useToday } from "./useToday";

const STOCKHOLM = "Europe/Stockholm";

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

beforeEach(() => {
  vi.useFakeTimers();
  setVisibility("visible");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useToday", () => {
  it("returns null without a time zone and never falls back to the browser time zone", () => {
    vi.setSystemTime(new Date("2026-11-12T10:00:00Z"));
    const { result } = renderHook(() => useToday(null));
    expect(result.current).toBeNull();
  });

  it("returns today's date in the warehouse time zone", () => {
    vi.setSystemTime(new Date("2026-11-12T10:00:00Z"));
    const { result } = renderHook(() => useToday(STOCKHOLM));
    expect(result.current).toBe("2026-11-12");
  });

  it("rolls over to the next day at local midnight without any other re-render", () => {
    // 23:59:30 in Stockholm (CET, UTC+1).
    vi.setSystemTime(new Date("2026-11-12T22:59:30Z"));
    const { result } = renderHook(() => useToday(STOCKHOLM));
    expect(result.current).toBe("2026-11-12");

    act(() => {
      vi.advanceTimersByTime(TODAY_CHECK_MS);
    });

    // 00:00:30 in Stockholm.
    expect(result.current).toBe("2026-11-13");
  });

  it("uses the correct offset on the day summer time ends (no early roll-over)", () => {
    // 2026-10-25: Stockholm goes back from CEST (UTC+2) to CET (UTC+1) at 01:00Z.
    // 21:59:30Z is 22:59:30 local. A fixed UTC+2 assumption would roll over one hour too early.
    vi.setSystemTime(new Date("2026-10-25T21:59:30Z"));
    const { result } = renderHook(() => useToday(STOCKHOLM));
    expect(result.current).toBe("2026-10-25");

    act(() => {
      vi.advanceTimersByTime(TODAY_CHECK_MS);
    });
    // 23:00:30 local: still the same day.
    expect(result.current).toBe("2026-10-25");

    act(() => {
      vi.advanceTimersByTime(60 * 60_000);
    });
    // 00:00:30 local on the 26th.
    expect(result.current).toBe("2026-10-26");
  });

  it("re-checks when the tab becomes visible again", () => {
    vi.setSystemTime(new Date("2026-11-12T22:00:00Z"));
    const { result } = renderHook(() => useToday(STOCKHOLM));
    expect(result.current).toBe("2026-11-12");

    // Clock jumps (e.g. the tab was frozen) without any timer firing.
    vi.setSystemTime(new Date("2026-11-13T07:00:00Z"));
    expect(result.current).toBe("2026-11-12");

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(result.current).toBe("2026-11-13");
  });

  it("does not return the previous time zone's date after the warehouse changes", () => {
    // Stockholm is already on the 13th, Chicago (UTC-6) is still on the 12th.
    vi.setSystemTime(new Date("2026-11-12T23:30:00Z"));
    const { result, rerender } = renderHook(({ tz }) => useToday(tz), { initialProps: { tz: STOCKHOLM } });
    expect(result.current).toBe("2026-11-13");

    rerender({ tz: "America/Chicago" });
    expect(result.current).toBe("2026-11-12");
  });

  it("clears its timer and listener on unmount", () => {
    vi.setSystemTime(new Date("2026-11-12T10:00:00Z"));
    const { unmount } = renderHook(() => useToday(STOCKHOLM));
    expect(vi.getTimerCount()).toBeGreaterThan(0);

    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});