/**
 * Thiết lập Vitest: matcher jest-dom, dọn DOM và localStorage giữa các test để không rò trạng thái đăng nhập.
 * Owner: Dev 3 (luồng C) — M0.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import { useAuthStore } from "../app/store";

afterEach(() => {
  cleanup();
  useAuthStore.getState().clearAuth();
  window.localStorage.clear();
});

declare global {
  interface Window {
    jsdom?: { window: Window };
  }
}

const jsdomWindow = window.jsdom?.window;
if (!jsdomWindow) {
  throw new Error("Vitest jsdom window is unavailable");
}

Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: jsdomWindow.localStorage,
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});