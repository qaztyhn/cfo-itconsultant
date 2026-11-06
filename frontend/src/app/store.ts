/**
 * Auth store (Zustand). Lưu JWT token + user info.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { create } from "zustand";

export type Role = "admin" | "dispatcher" | "warehouse" | "sales" | "driver" | "customer_service" | "viewer";

export interface CurrentUser {
  employee_id: number;
  email: string;
  display_name: string;
  role: Role;
  kpi_scopes: string[];
  location_ids: number[];
  market_code: string;
  market_timezone: string;
  currency: string;
}

interface AuthState {
  token: string | null;
  user: CurrentUser | null;
  setAuth: (token: string, user: CurrentUser) => void;
  clearAuth: () => void;
}

const getStoredToken = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }

  return window.localStorage.getItem("cfo_token");
};

const getStoredUser = (): CurrentUser | null => {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const user = window.localStorage.getItem("cfo_user");
    return user ? (JSON.parse(user) as CurrentUser) : null;
  } catch {
    return null;
  }
};

export const useAuthStore = create<AuthState>((set) => ({
  token: getStoredToken(),
  user: getStoredUser(),
  setAuth: (token, user) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("cfo_token", token);
      window.localStorage.setItem("cfo_user", JSON.stringify(user));
    }

    set({ token, user });
  },
  clearAuth: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("cfo_token");
      window.localStorage.removeItem("cfo_user");
    }

    set({ token: null, user: null });
  },
}));
