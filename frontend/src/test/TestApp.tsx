/**
 * Khung render cho test: MemoryRouter + bảng route thật (appRoutes) + bộ dò vị trí hiện tại.
 * Dùng MemoryRouter + useRoutes thay cho createMemoryRouter vì data router không điều hướng được trong jsdom.
 * Tách riêng khỏi utils.tsx để file này chỉ export component (react-refresh/only-export-components).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { MemoryRouter, useLocation, useRoutes } from "react-router-dom";
import { appRoutes } from "../app/routes";

function AppRoutes() {
  return useRoutes(appRoutes);
}

/** Hiển thị vị trí hiện tại để test đọc được. */
function LocationProbe() {
  const location = useLocation();
  return (
    <>
      <div data-testid="pathname">{location.pathname}</div>
      <output data-testid="location-state">{JSON.stringify(location.state)}</output>
    </>
  );
}

export function TestApp({ path }: { path: string }) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <LocationProbe />
      <AppRoutes />
    </MemoryRouter>
  );
}