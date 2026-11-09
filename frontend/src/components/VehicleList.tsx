/**
 * VehicleList — Danh sách xe của một phương án: mã xe, loại, tài xế, tải/capacity, ETA; '2 trucks · 24 t total' (03 mục 4, v1.2).
 * Tài xế chỉ hiện khi `showDriver` VÀ server có trả (server đã lược bỏ với vai trò không được phép).
 * Owner: Dev 3 (luồng C).
 */
import type { PlanVehicle } from "../api/contracts/planning";
import { formatKg, formatM3, formatTime, formatTonnes, toNumber } from "../lib/planFormat";

export interface VehicleListProps {
  vehicles: PlanVehicle[];
  showDriver?: boolean;
  className?: string;
}

export function VehicleList({ vehicles, showDriver = false, className }: VehicleListProps) {
  const totalKg = vehicles.reduce((sum, v) => sum + (toNumber(v.vehicle?.capacity_kg) ?? 0), 0);
  const summary = `${vehicles.length} ${vehicles.length === 1 ? "truck" : "trucks"} · ${formatTonnes(totalKg)} total`;

  return (
    <div className={className} data-component="VehicleList">
      <p className="font-mono text-caption text-inkMuted">{summary}</p>
      <ul className="mt-2 flex flex-col gap-2">
        {vehicles.map((v) => (
          <li key={v.seq} className="rounded-control border bg-rowHover px-3 py-2 text-body">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span>
                <span className="font-mono font-semibold text-ink">{v.vehicle?.code ?? (v.vehicle_id != null ? `#${v.vehicle_id}` : "—")}</span>{" "}
                <span className="text-inkMuted">{v.vehicle?.name}</span>
              </span>
              <span className="font-mono text-caption text-ink">ETA {formatTime(v.eta_at)}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 text-caption text-inkMuted">
            <span>
              Load {formatKg(v.load_kg)}{v.vehicle ? ` / ${formatKg(v.vehicle.capacity_kg)}` : ""}
            </span>
            <span>
              {formatM3(v.load_m3)}{v.vehicle ? ` / ${formatM3(v.vehicle.capacity_m3)}` : ""}
            </span>
            {showDriver && v.driver_employee_id != null && <span>Driver #{v.driver_employee_id}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}