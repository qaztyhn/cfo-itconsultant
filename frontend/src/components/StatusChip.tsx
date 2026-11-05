/**
 * StatusChip — Pill mono theo enum trạng thái đơn (MANUAL_PLANNING, PREPARING… không viết tắt; 03 #35).
 * Owner: Dev 3 (luồng C).
 */
export interface StatusChipProps {
  className?: string;
}

export function StatusChip({ className }: StatusChipProps) {
  // TODO(#C-StatusChip)
  return <div className={className} data-component="StatusChip" />;
}
