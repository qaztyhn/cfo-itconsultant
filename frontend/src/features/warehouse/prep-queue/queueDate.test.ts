import { describe, expect, it } from "vitest";
import { formatQueueDate } from "./queueDate";

describe("formatQueueDate", () => {
  it("formats the short label used in empty states", () => {
    expect(formatQueueDate("2026-11-12")).toBe("Thu 12 Nov");
  });

  it("formats the long label used in the header overline", () => {
    expect(formatQueueDate("2026-11-04", "long")).toBe("Wednesday 4 November");
  });

  it("returns invalid input unchanged instead of guessing", () => {
    expect(formatQueueDate("12/11/2026")).toBe("12/11/2026");
    expect(formatQueueDate("2026-13-45")).toBe("2026-13-45");
  });
});