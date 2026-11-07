/**
 * Route guard (chỉ điều khiển trải nghiệm; máy chủ vẫn kiểm quyền — docs/09).
 * RequireAuth: phiên hợp lệ + tự đăng xuất khi hết hạn. RequireAccess: chặn theo quy tắc access.ts. GuestOnly: trang /login.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { useEffect, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { NoAccess } from "./NoAccess";
import { PATHS, landingPath, resolvePostLoginPath, type AccessRule } from "./access";
import { isSessionValid, useAuthStore } from "./store";

const MAX_TIMEOUT_MS = 2_147_483_647;

export function RequireAuth() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const expiresAt = useAuthStore((s) => s.expiresAt);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const location = useLocation();
  const valid = isSessionValid({ token, user, email: null, expiresAt });

  useEffect(() => {
    if (!valid) {
      if (token) {
        clearAuth(); // phiên đã hết hạn
      }
      return;
    }
    const timer = setTimeout(clearAuth, Math.min(Math.max((expiresAt ?? 0) - Date.now(), 0), MAX_TIMEOUT_MS));
    return () => clearTimeout(timer);
  }, [valid, token, expiresAt, clearAuth]);

  if (!valid) {
    return <Navigate to={PATHS.login} replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  return <Outlet />;
}

export function RequireAccess({ allow, children }: { allow: AccessRule; children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (!user) {
    return <Navigate to={PATHS.login} replace />;
  }
  if (allow(user)) {
    return <>{children}</>;
  }
  const target = landingPath(user);
  if (!target || target === location.pathname) {
    return <NoAccess />;
  }
  return <Navigate to={target} replace state={{ denied: location.pathname }} />;
}

/** Trang /login: người đã đăng nhập được chuyển thẳng tới đích hợp lệ. */
export function GuestOnly({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const expiresAt = useAuthStore((s) => s.expiresAt);
  const location = useLocation();

  if (user && isSessionValid({ token, user, email: null, expiresAt })) {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={resolvePostLoginPath(user, from)} replace />;
  }
  return <>{children}</>;
}

export function LandingRedirect() {
  const user = useAuthStore((s) => s.user);
  const target = user ? landingPath(user) : null;
  return target ? <Navigate to={target} replace /> : <NoAccess />;
}