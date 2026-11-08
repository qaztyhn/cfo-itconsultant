/**
 * Cấu hình API phía client. Owner: Dev 3 (luồng C) — M0.
 * VITE_API_URL đã gồm /api/v1 (khớp .env.example). USE_MOCKS chỉ bật ở dev, không bao giờ trong bản build production.
 */
export const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");

/** true khi chạy `npm run dev:mock`. Dùng để DemoBanner cảnh báo "mock API, chưa tích hợp thật" (T7). */
export const USE_MOCKS = import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true";

/** URL ứng dụng POS giả lập (03 mục 6) mở từ mục menu "New order". ASM-G: mặc định cổng 8100, cần Dev 2 xác nhận. */
export const POS_URL = (import.meta.env.VITE_POS_URL ?? "http://localhost:8100").replace(/\/+$/, "");

/** Giá trị VITE_APP_ENV được phép bật chế độ demo trong bản build production. */
const DEMO_ENVS = ["demo", "local", "staging"];

/**
 * Xác định môi trường chạy (APP_ENV, docs/09).
 * - Build production (isProd): mặc định "production"; chỉ ra demo khi VITE_APP_ENV là một trong DEMO_ENVS.
 *   Giá trị lạ/gõ sai → vẫn "production" (an toàn: không lộ thẻ demo).
 * - Dev/test: không đặt → "demo".
 */
export function resolveAppEnv(raw: string | undefined, isProd: boolean): string {
  const v = raw?.trim().toLowerCase();
  if (isProd) return v && DEMO_ENVS.includes(v) ? v : "production";
  return v || "demo";
}

export const APP_ENV = resolveAppEnv(import.meta.env.VITE_APP_ENV, import.meta.env.PROD);

/** Banner DEMO hiện ở mọi môi trường trừ production. Nhận env làm tham số để test được. */
export const isDemoEnv = (env: string = APP_ENV): boolean => env !== "production";