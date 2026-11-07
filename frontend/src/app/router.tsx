/**
 * Router trình duyệt. Bảng route nằm ở routes.tsx để test được bằng memory router.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { createBrowserRouter } from "react-router-dom";
import { appRoutes } from "./routes";

export const router = createBrowserRouter(appRoutes);