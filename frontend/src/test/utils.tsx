/**
 * Tiện ích test: đăng nhập bằng tài khoản mock và render bảng route thật (qua TestApp).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { AuthUser } from "../api/contracts/auth";
import { MOCK_ACCOUNTS } from "../api/mocks/authHandlers";
import { useAuthStore } from "../app/store";
import { TestApp } from "./TestApp";

export function userByEmail(email: string): AuthUser {
  const account = MOCK_ACCOUNTS.find((a) => a.email === email);
  if (!account) {
    throw new Error(`Unknown mock account ${email}`);
  }
  return account.user;
}

export function signInAs(user: AuthUser, expiresInSeconds = 28_800): void {
  useAuthStore.getState().setAuth({ access_token: "test-token", token_type: "bearer", expires_in: expiresInSeconds, user }, "test@cfo.demo");
}

export function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TestApp path={path} />
    </QueryClientProvider>,
  );
}

export const currentPath = (): string => screen.getByTestId("pathname").textContent ?? "";

export function currentState(): unknown {
  return JSON.parse(screen.getByTestId("location-state").textContent || "null");
}
