/**
 * AppShell — khung: Sidebar 262px deep-pine + DemoBanner + vùng nội dung (03 mục 3.1).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { Outlet } from "react-router-dom";
import { DemoBanner } from "./DemoBanner";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  return (
    <div className="flex min-h-screen">
      <Sidebar className="w-[262px] bg-deepPine" />
      <main className="flex-1">
        <DemoBanner />
        <Outlet />
      </main>
    </div>
  );
}
