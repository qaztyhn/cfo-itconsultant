import { describe, expect, it } from "vitest";
import { ApiError } from "./client";

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
