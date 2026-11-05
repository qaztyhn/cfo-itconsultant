/**
 * Route theo vai trò (docs/04 mục 11): /dispatcher/*, /warehouse/*, /store/*, /it/*, /cs/*, /kpi, /driver/*, /admin/*.
 * Mục menu lọc theo vai trò (docs/03 mục 3.2); máy chủ vẫn kiểm quyền.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { SignIn } from "../features/auth/SignIn";

export const router = createBrowserRouter([
  { path: "/login", element: <SignIn /> },
  { path: "/", element: <AppShell />, children: [] },
]);
