/**
 * StatusChip — Pill mono theo enum trạng thái đơn (PREPARING… không viết tắt; không còn MANUAL_PLANNING; kế hoạch tay là nhãn phụ; 03 #35).
 * Owner: Dev 3 (luồng C).
 */
export interface StatusChipProps {
  className?: string;
}

export function StatusChip({ className }: StatusChipProps) {
  // TODO(#C-StatusChip)
  return <div className={className} data-component="StatusChip" />;
}
