/**
 * Đăng xuất: gọi POST /auth/logout (MVP chỉ ghi log, 06 mục 4) rồi xóa phiên ở client.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { logout } from "../api/auth";
import { useAuthStore } from "./store";

export async function signOut(): Promise<void> {
  // logout() đọc token đồng bộ trước khi gửi, nên xóa phiên ngay sau đó vẫn gửi đúng Authorization.
  const request = logout().catch(() => undefined);
  useAuthStore.getState().clearAuth();
  await request;
}