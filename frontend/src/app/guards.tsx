/**
 * Route guard (chỉ điều khiển trải nghiệm; máy chủ vẫn kiểm quyền — docs/09).
 * RequireAuth: phiên hợp lệ + tự đăng xuất khi hết hạn. RequireAccess: chặn theo quy tắc access.ts. GuestOnly: trang /login.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { useEffect, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { NoAccess } from "./NoAccess";
import { PATHS, landingPath, resolvePostLoginPath, type AccessRule } from "./access";
import { fetchMe } from "../api/auth";
import { isAuthUser, isSessionValid, useAuthStore } from "./store";
import { isApiError } from "../api/client";
import { ErrorState, LoadingState } from "../components/StateViews";

const MAX_TIMEOUT_MS = 2_147_483_647;

export function RequireAuth() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const expiresAt = useAuthStore((s) => s.expiresAt);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const location = useLocation();
  const valid = isSessionValid({ token, user, email: null, expiresAt });

  const verified = useAuthStore((s) => s.verified);
  const setUser = useAuthStore((s) => s.setUser);

  const [verifyError, setVerifyError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!valid || verified) return;
    const controller = new AbortController();
    fetchMe(controller.signal)
      .then((me) => {
        if (isAuthUser(me)) setUser(me);
        else clearAuth();
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (isApiError(error) && error.status === 401) return; // client.ts đã clearAuth()
        setVerifyError(error ?? new Error("Session check failed"));
      });
    return () => controller.abort();
  }, [valid, verified, token, attempt, setUser, clearAuth]);

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
  if (!verified) {
    if (verifyError) {
      return (
        <div className="mx-auto max-w-lg p-8">
          <ErrorState
            error={verifyError}
            title="Couldn't verify your session"
            onRetry={() => {
              setVerifyError(null);
              setAttempt((n) => n + 1);
            }}
          />
          <button type="button" onClick={clearAuth} className="mt-4 text-body underline">
            Sign out
          </button>
        </div>
      );
    }
    return <LoadingState rows={3} className="p-8" />;
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