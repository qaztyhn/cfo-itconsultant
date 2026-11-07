/**
 * Lời gọi xác thực (docs/06 mục 4). Owner: Dev 3 (luồng C) — M0.
 * Đã xác nhận với backend thật: GET /auth/me trả cùng object `user` như trong login.
 */
import { apiGet, apiPost } from "./client";
import type { AuthUser, LoginRequest, LoginResponse } from "./contracts/auth";

export function login(credentials: LoginRequest): Promise<LoginResponse> {
  return apiPost<LoginResponse>("/auth/login", credentials);
}

export function fetchMe(signal?: AbortSignal): Promise<AuthUser> {
  return apiGet<AuthUser>("/auth/me", undefined, signal);
}

/** MVP: no-op phía server, chỉ ghi log (06 mục 4). Phiên thật được xóa ở client. */
export function logout(): Promise<void> {
  return apiPost<void>("/auth/logout");
}