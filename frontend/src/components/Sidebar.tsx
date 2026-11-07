/**
 * Sidebar — Logo, menu theo vai trò và kpi_scopes (buildMenu), huy hiệu từ /orders/counts, khối người dùng (03 mục 3.2).
 * Bộ chọn Market/Warehouse thêm ở bước 7.3b. Driver không có mục menu nên không dùng sidebar (PWA riêng).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useMemo } from "react";
import { NavLink } from "react-router-dom";
import { POS_URL } from "../api/config";
import type { AuthUser, UserRole } from "../api/contracts/auth";
import { fetchOrderCounts } from "../api/orders";
import { badgeValue, buildMenu } from "../app/menu";
import { signOut } from "../app/session";
import { useAuthStore } from "../app/store";
import { ScopePicker } from "./ScopePicker";

export interface SidebarProps {
  className?: string;
}

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Admin",
  dispatcher: "Dispatcher",
  warehouse: "Warehouse",
  sales: "Sales",
  driver: "Driver",
  customer_service: "Customer service",
  viewer: "Viewer",
};

function roleLabel(user: AuthUser): string {
  const labels = user.roles.filter((role) => role !== "viewer").map((role) => ROLE_LABEL[role]);
  if (user.roles.includes("viewer")) {
    if (user.kpi_scopes.includes("revenue_all")) labels.push("Business owner");
    else if (user.kpi_scopes.includes("ops")) labels.push("Project lead");
    else labels.push(ROLE_LABEL.viewer);
  }
  return labels.join(" · ");
}

// Chuỗi class viết đầy đủ để Tailwind quét được. Chữ apricot chỉ đặt trên nền deepPine; chữ trên nền apricot dùng deepPine (03 mục 10).
const ITEM =
  "flex items-center justify-between gap-2 rounded-control px-3 py-2 text-body focus-visible:outline focus-visible:outline-2 focus-visible:outline-apricot";
const ITEM_IDLE = "text-surface hover:bg-pine";
const ITEM_ACTIVE = "bg-navActive font-semibold text-deepPine";
const BADGE = "inline-flex min-w-6 justify-center rounded-full bg-apricot px-2 font-mono text-caption font-semibold text-deepPine";

export function Sidebar({ className }: SidebarProps) {
  const user = useAuthStore((s) => s.user);
  const email = useAuthStore((s) => s.email);
  const groups = useMemo(() => (user ? buildMenu(user) : []), [user]);
  const hasBadges = groups.some((group) => group.items.some((item) => item.badge));

  const { data: counts } = useQuery({
    queryKey: ["orders", "counts"],
    queryFn: ({ signal }) => fetchOrderCounts(signal),
    enabled: hasBadges,
  });

  if (!user) {
    return null;
  }

  return (
    <aside aria-label="Sidebar" data-component="Sidebar" className={["flex flex-col gap-6 text-surface", className].filter(Boolean).join(" ")}>
      <div className="px-6 pt-6">
        <span className="font-mono text-overline uppercase text-apricot">CFO</span>
        <p className="text-h3 text-surface">Central Fulfillment Orchestration</p>
      </div>

      <ScopePicker />
      
      <nav aria-label="Main" className="flex flex-1 flex-col gap-5 overflow-y-auto px-3">
        {groups.map((group) => (
          <div key={group.id}>
            <p className="px-3 pb-1 font-mono text-overline uppercase text-apricot">{group.label}</p>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const count = item.badge ? badgeValue(counts, item.badge) : undefined;
                return (
                  <li key={item.id}>
                    {item.to ? (
                      <NavLink to={item.to} className={({ isActive }) => `${ITEM} ${isActive ? ITEM_ACTIVE : ITEM_IDLE}`}>
                        <span>{item.label}</span>
                        {count ? <span className={BADGE}>{count}</span> : null}
                      </NavLink>
                    ) : item.external === "pos" ? (
                      <a href={POS_URL} target="_blank" rel="noreferrer" className={`${ITEM} ${ITEM_IDLE}`}>
                        <span>{item.label}</span>
                        <ExternalLink aria-hidden="true" className="h-4 w-4" />
                      </a>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="flex flex-col gap-1 border-t border-pine px-6 py-4">
        <p className="text-body font-semibold text-surface">{user.name}</p>
        <p className="text-caption text-surface">{roleLabel(user)}</p>
        {email && <p className="font-mono text-caption text-surface">{email}</p>}
        <button
          type="button"
          onClick={() => void signOut()}
          className="mt-2 self-start rounded-control border border-pine px-3 py-1 text-caption font-semibold text-surface hover:bg-pine focus-visible:outline focus-visible:outline-2 focus-visible:outline-apricot"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}