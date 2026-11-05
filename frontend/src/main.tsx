/**
 * Điểm vào SPA: QueryClient (polling 15–30 giây, không WebSocket), i18n, router theo vai trò.
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
);
