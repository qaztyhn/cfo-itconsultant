import { describe, expect, it } from "vitest";
import { isAuthUser, isSessionValid, readStoredSession, useAuthStore } from "./store";
import { userByEmail } from "../test/utils";

const user = userByEmail("dispatcher@cfo.demo");

describe("auth store", () => {
  it("test_US_EMP_03_AC1_setAuth keeps token, user, email and an 8h expiry, and persists them", () => {
    const before = Date.now();
    useAuthStore.getState().setAuth({ access_token: "t1", token_type: "bearer", expires_in: 28_800, user }, "a@cfo.demo");

    const state = useAuthStore.getState();
    expect(state).toMatchObject({ token: "t1", user, email: "a@cfo.demo" });
    expect(state.expiresAt).toBeGreaterThanOrEqual(before + 28_800_000);
    expect(readStoredSession()).toMatchObject({ token: "t1", email: "a@cfo.demo", user });
  });

  it("clearAuth removes the session from memory and storage (client.ts relies on cfo_token)", () => {
    useAuthStore.getState().setAuth({ access_token: "t1", token_type: "bearer", expires_in: 60, user }, "a@cfo.demo");
    useAuthStore.getState().clearAuth();

    expect(useAuthStore.getState()).toMatchObject({ token: null, user: null, email: null, expiresAt: null });
    expect(window.localStorage.getItem("cfo_token")).toBeNull();
    expect(window.localStorage.getItem("cfo_user")).toBeNull();
  });

  it("discards an expired stored session", () => {
    useAuthStore.getState().setAuth({ access_token: "t1", token_type: "bearer", expires_in: 60, user }, "a@cfo.demo");

    expect(readStoredSession(Date.now() + 61_000).token).toBeNull();
    expect(window.localStorage.getItem("cfo_token")).toBeNull();
  });

  it("discards a stored user with the old scaffold shape (single `role`)", () => {
    window.localStorage.setItem("cfo_token", "t");
    window.localStorage.setItem("cfo_email", "a@cfo.demo");
    window.localStorage.setItem("cfo_expires_at", String(Date.now() + 60_000));
    window.localStorage.setItem("cfo_user", JSON.stringify({ employee_id: 1, role: "dispatcher", display_name: "X" }));

    expect(readStoredSession()).toMatchObject({ token: null, user: null });
  });

  it("survives corrupted JSON in storage", () => {
    window.localStorage.setItem("cfo_token", "t");
    window.localStorage.setItem("cfo_user", "{not json");

    expect(readStoredSession().user).toBeNull();
  });

  it("validates the docs/06 user shape", () => {
    expect(isAuthUser(user)).toBe(true);
    expect(isAuthUser({ ...user, roles: ["root"] })).toBe(false);
    expect(isAuthUser({ ...user, kpi_scopes: ["everything"] })).toBe(false);
    expect(isAuthUser(null)).toBe(false);
  });

  it("accepts nullable employee_id, name and market like backend UserOut", () => {
    expect(isAuthUser({ ...user, employee_id: null, name: null, market: null })).toBe(true);
    expect(isAuthUser({ ...user, employee_id: "55" })).toBe(false);
    expect(isAuthUser({ ...user, name: 123 })).toBe(false);
    expect(isAuthUser({ ...user, market: undefined })).toBe(false);
  });

  it("keeps the session after reload when employee_id, name and market are null", () => {
    const nullableUser = { ...user, employee_id: null, name: null, market: null };
    useAuthStore.getState().setAuth(
      { access_token: "t-null", token_type: "bearer", expires_in: 28_800, user: nullableUser },
      "nullable@cfo.demo",
    );

    const restored = readStoredSession();

    expect(restored.token).toBe("t-null");
    expect(restored.user).toEqual(nullableUser);
    useAuthStore.getState().clearAuth();
  });

  it("isSessionValid requires token, user and an unexpired timestamp", () => {
    const now = 1_000;
    expect(isSessionValid({ token: "t", user, email: "a", expiresAt: now + 1 }, now)).toBe(true);
    expect(isSessionValid({ token: "t", user, email: "a", expiresAt: now }, now)).toBe(false);
    expect(isSessionValid({ token: null, user, email: "a", expiresAt: now + 1 }, now)).toBe(false);
  });
});