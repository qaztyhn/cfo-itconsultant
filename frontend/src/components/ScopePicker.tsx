/**
 * ScopePicker — nhãn Market + bộ chọn Warehouse trong Sidebar (03 mục 3.2).
 * Một Market/tài khoản nên chỉ là nhãn; nhiều kho → dropdown "All warehouses"; một kho → nhãn cố định.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { useQuery } from "@tanstack/react-query";
import { fetchLocations } from "../api/locations";
import { selectableWarehouses, useScopeStore, usesWarehouseScope } from "../app/scope";
import { useAuthStore } from "../app/store";

export function ScopePicker() {
  const user = useAuthStore((s) => s.user);
  const warehouseId = useScopeStore((s) => s.warehouseId);
  const setWarehouse = useScopeStore((s) => s.setWarehouse);
  const wanted = user ? usesWarehouseScope(user) : false;

  const { data: locations } = useQuery({
    queryKey: ["locations"],
    queryFn: ({ signal }) => fetchLocations(signal),
    enabled: wanted,
    staleTime: 5 * 60_000,
  });

  if (!user) {
    return null;
  }
  const warehouses = selectableWarehouses(user, locations ?? []);

  return (
    <div className="flex flex-col gap-3 px-6">
      <div>
        <span className="font-mono text-overline uppercase text-apricot">Market</span>
        <p className="font-mono text-body text-surface">{user.market ?? "—"}</p>
      </div>

      {warehouses.length === 1 && (
        <div>
          <span className="font-mono text-overline uppercase text-apricot">Warehouse</span>
          <p className="text-body text-surface">{warehouses[0].name}</p>
        </div>
      )}

      {warehouses.length > 1 && (
        <div className="flex flex-col gap-1">
          <label htmlFor="scope-warehouse" className="font-mono text-overline uppercase text-apricot">
            Warehouse
          </label>
          <select
            id="scope-warehouse"
            value={warehouseId ?? ""}
            onChange={(event) => setWarehouse(event.target.value === "" ? null : Number(event.target.value))}
            className="rounded-control border border-pine bg-pine px-2 py-1 text-body text-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-apricot"
          >
            <option value="">All warehouses</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}