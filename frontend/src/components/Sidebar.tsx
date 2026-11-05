/**
 * Sidebar — Logo, bộ chọn Market/Warehouse, menu theo vai trò có huy hiệu từ /orders/counts, khối người dùng (03 mục 3.2).
 * Owner: Dev 3 (luồng C).
 */
export interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  // TODO(#C-Sidebar)
  return <div className={className} data-component="Sidebar" />;
}
