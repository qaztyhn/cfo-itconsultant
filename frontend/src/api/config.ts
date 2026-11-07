/**
 * Cấu hình API phía client. Owner: Dev 3 (luồng C) — M0.
 * VITE_API_URL đã gồm /api/v1 (khớp .env.example). USE_MOCKS chỉ bật ở dev, không bao giờ trong bản build production.
 */
export const API_BASE_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1").replace(/\/+$/, "");

/** true khi chạy `npm run dev:mock`. Dùng để DemoBanner cảnh báo "mock API, chưa tích hợp thật" (T7). */
export const USE_MOCKS = import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true";