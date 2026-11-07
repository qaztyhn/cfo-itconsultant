/**
 * Phạm vi làm việc: kho đang chọn ở sidebar (null = tất cả kho trong quyền). Owner: Dev 3 (luồng C) — M0.
 * Chỉ điều khiển trải nghiệm; backend vẫn lọc theo location_ids của token (docs/06 mục 3).
 */
import { create } from "zustand";
import type { AuthUser } from "../api/contracts/auth";
import type { WorkLocation } from "../api/locations";
import { anyRole } from "./access";
import { useAuthStore } from "./store";

export const usesWarehouseScope = anyRole("dispatcher", "warehouse");

/**
 * Kho user được chọn.
 * - Dispatcher: backend đã lọc /locations theo market, nên dùng nguyên danh sách kho trả về.
 *   location_ids của dispatcher là nơi được phân công (vd DC), KHÔNG phải danh sách kho được điều phối.
 * - Warehouse Manager: chỉ các kho trong location_ids.
 */
export function selectableWarehouses(user: AuthUser, locations: WorkLocation[]): WorkLocation[] {
  if (!usesWarehouseScope(user)) {
    return [];
  }
  const warehouses = locations.filter((l) => l.type === "warehouse");
  if (user.roles.includes("dispatcher")) {
    return warehouses;
  }
  return warehouses.filter((l) => user.location_ids.includes(l.id));
}

interface ScopeState {
  warehouseId: number | null;
  setWarehouse: (id: number | null) => void;
}

export const useScopeStore = create<ScopeState>((set) => ({
  warehouseId: null,
  setWarehouse: (id) => set({ warehouseId: id }),
}));

// Đăng xuất thì quên kho đã chọn, để người đăng nhập sau không thừa hưởng.
useAuthStore.subscribe((state, previous) => {
  if (previous.user && !state.user) {
    useScopeStore.setState({ warehouseId: null });
  }
});