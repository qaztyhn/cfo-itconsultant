/**
 * CheckChip — ✓/✕ + mã lỗi mono (STOCK_SHORT, NO_TRUCK_FIT…).
 * Owner: Dev 3 (luồng C).
 */
export interface CheckChipProps {
  className?: string;
}

export function CheckChip({ className }: CheckChipProps) {
  // TODO(#C-CheckChip)
  return <div className={className} data-component="CheckChip" />;
}
