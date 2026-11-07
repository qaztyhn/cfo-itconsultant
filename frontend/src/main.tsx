/**
 * Điểm vào SPA: QueryClient (polling 15–30 giây, không WebSocket), i18n, router theo vai trò.
 * MSW chỉ chạy khi `npm run dev:mock` (DEV + VITE_USE_MOCKS=true); điều kiện viết trực tiếp để bản production loại bỏ mã mock.
 * Owner: Dev 3 (luồng C) — M0.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import "./i18n";
import "./styles/index.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchInterval: 20_000 } } });

async function enableMocking(): Promise<void> {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true") {
    const { worker } = await import("./api/mocks/browser");
    await worker.start({ onUnhandledRequest: "bypass" });
  }
}

void enableMocking().then(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </React.StrictMode>,
  );
});