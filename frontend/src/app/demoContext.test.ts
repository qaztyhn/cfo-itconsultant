import { describe, expect, it } from "vitest";
import { isDemoEnv } from "../api/config";
import { DEFAULT_DEMO_CONTEXT, demoContextFor } from "./demoContext";

describe("demoContextFor", () => {
  it("picks the sentence by top-level section, including child routes", () => {
    expect(demoContextFor("/dispatcher/orders")).toMatch(/synthetic/i);
    expect(demoContextFor("/notifications")).toMatch(/simulated/i);
    expect(demoContextFor("/it/users?tab=1")).toMatch(/Integrations are simulated/);
  });

  it("matches whole path segments only, so /csv does not match /cs", () => {
    expect(demoContextFor("/csv")).toBe(DEFAULT_DEMO_CONTEXT);
  });

  it("falls back to the default sentence for unknown paths and the root", () => {
    expect(demoContextFor("/")).toBe(DEFAULT_DEMO_CONTEXT);
    expect(demoContextFor("/whatever")).toBe(DEFAULT_DEMO_CONTEXT);
  });
});

describe("isDemoEnv", () => {
  it("is false only for production", () => {
    expect(isDemoEnv("production")).toBe(false);
    expect(isDemoEnv("demo")).toBe(true);
    expect(isDemoEnv("staging")).toBe(true);
  });
});