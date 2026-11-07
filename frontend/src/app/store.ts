/**
 * Auth store (Zustand): JWT + user theo docs/06 mục 4, lưu localStorage.
 * Phiên hết hạn sau expires_in (8 giờ); dữ liệu cũ sai hình dạng (vd. scaffold trước dùng `role` đơn) bị xóa khi nạp lại.
 * `email` lấy từ form đăng nhập vì `user` của 06 không có email (xem ghi chú T3).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { create } from "zustand";
import { USER_ROLES, type AuthUser, type LoginResponse } from "../api/contracts/auth";

export interface SessionState {
  token: string | null;
  user: AuthUser | null;
  email: string | null;
  /** Mốc hết hạn (epoch ms). */
  expiresAt: number | null;
}

interface AuthState extends SessionState {
  setAuth: (login: LoginResponse, email: string) => void;
  clearAuth: () => void;
}

const KEYS = { token: "cfo_token", user: "cfo_user", email: "cfo_email", expiresAt: "cfo_expires_at" } as const;
const EMPTY: SessionState = { token: null, user: null, email: null, expiresAt: null };
const KPI_SCOPES = ["revenue_all", "ops"];

export function isAuthUser(value: unknown): value is AuthUser {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const v = value as Record<string, unknown>;
  return (
    typeof v.id === "number" &&
    (v.employee_id === null || typeof v.employee_id === "number") &&
    (v.name === null || typeof v.name === "string") &&
    Array.isArray(v.roles) &&
    v.roles.every((role) => (USER_ROLES as readonly string[]).includes(role)) &&
    (v.market === null || typeof v.market === "string") &&
    typeof v.locale === "string" &&
    Array.isArray(v.location_ids) &&
    v.location_ids.every((id) => typeof id === "number") &&
    Array.isArray(v.kpi_scopes) &&
    v.kpi_scopes.every((scope) => KPI_SCOPES.includes(scope))
  );
}

export function isSessionValid(session: SessionState, now: number = Date.now()): boolean {
  return session.token !== null && session.user !== null && session.expiresAt !== null && session.expiresAt > now;
}

function removeStored(): void {
  try {
    Object.values(KEYS).forEach((key) => window.localStorage.removeItem(key));
  } catch {
    /* localStorage không khả dụng (vd. chế độ riêng tư): bỏ qua */
  }
}

export function readStoredSession(now: number = Date.now()): SessionState {
  try {
    const token = window.localStorage.getItem(KEYS.token);
    const rawUser = window.localStorage.getItem(KEYS.user);
    const email = window.localStorage.getItem(KEYS.email);
    const expiresAt = Number(window.localStorage.getItem(KEYS.expiresAt));
    const user: unknown = rawUser ? JSON.parse(rawUser) : null;

    if (token && email && isAuthUser(user) && Number.isFinite(expiresAt) && expiresAt > now) {
      return { token, user, email, expiresAt };
    }
  } catch {
    /* JSON hỏng hoặc không có storage: coi như chưa đăng nhập */
  }
  removeStored();
  return EMPTY;
}

export const useAuthStore = create<AuthState>((set) => ({
  ...readStoredSession(),
  setAuth: (login, email) => {
    const session: SessionState = {
      token: login.access_token,
      user: login.user,
      email,
      expiresAt: Date.now() + login.expires_in * 1000,
    };
    try {
      window.localStorage.setItem(KEYS.token, session.token ?? "");
      window.localStorage.setItem(KEYS.user, JSON.stringify(login.user));
      window.localStorage.setItem(KEYS.email, email);
      window.localStorage.setItem(KEYS.expiresAt, String(session.expiresAt));
    } catch {
      /* phiên vẫn hoạt động trong bộ nhớ */
    }
    set(session);
  },
  clearAuth: () => {
    removeStored();
    set(EMPTY);
  },
}));