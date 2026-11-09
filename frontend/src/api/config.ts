/**
 * Cấu hình API phía client. Owner: Dev 3 (luồng C) — M0.
 * VITE_API_URL đã gồm /api/v1 (khớp .env.example). USE_MOCKS chỉ bật ở dev, không bao giờ trong bản build production.
 */
export const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");

/** true khi chạy `npm run dev:mock`. Dùng để DemoBanner cảnh báo "mock API, chưa tích hợp thật" (T7). */
export const USE_MOCKS = import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true";

/** POS is a separate web application, not the source-system API on port 8100.
 * Unconfigured or unsafe URLs must never redirect a deployed CFO client to localhost.
 */
export function resolvePosUrl(raw: string | undefined, isProd: boolean): string | null {
  if (!raw?.trim()) return null;
  try {
    const url = new URL(raw.trim());
    if (url.username || url.password) return null;
    if (url.protocol !== "https:" && !(url.protocol === "http:" && !isProd)) return null;
    const host = url.hostname.toLowerCase();
    if (isProd && (host === "localhost" || host === "localhost." ||
      host.endsWith(".localhost") || host.startsWith("127.") ||
      host === "[::1]" || host === "0.0.0.0")) return null;
    return url.href.replace(/\/+$/, "");
  } catch {
    return null;
  }
}

/** Configured POS web UI, or null when no usable POS deployment is available. */
export const POS_URL = resolvePosUrl(import.meta.env.VITE_POS_URL, import.meta.env.PROD);

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