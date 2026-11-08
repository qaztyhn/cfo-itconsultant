/**
 * AppShell — khung: Sidebar 262px deep-pine + DemoBanner + vùng nội dung (03 mục 3.1).
 * Driver không đi qua AppShell (PWA riêng, xem routes.tsx).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { Outlet, useLocation } from "react-router-dom";
import { demoContextFor } from "../app/demoContext";
import { DemoBanner } from "./DemoBanner";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const { pathname } = useLocation();

  return (
    <div className="flex min-h-screen bg-stone">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-control focus:bg-apricot focus:px-3 focus:py-1 focus:text-deepPine"
      >
        Skip to content
      </a>
      <Sidebar className="sticky top-0 h-screen w-sidebar shrink-0 bg-deepPine" />
      <div className="flex min-w-0 flex-1 flex-col">
        <DemoBanner context={demoContextFor(pathname)} />
        <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-content flex-1 p-8 focus:outline-none">
          <Outlet />
        </main>
      </div>
    </div>
  );
}