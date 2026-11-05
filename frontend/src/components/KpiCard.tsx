/**
 * KpiCard — Thẻ KPI: nhãn mono, chip lower/higher is better, số lớn, thanh so baseline.
 * Owner: Dev 3 (luồng C).
 */
export interface KpiCardProps {
  className?: string;
}

export function KpiCard({ className }: KpiCardProps) {
  // TODO(#C-KpiCard)
  return <div className={className} data-component="KpiCard" />;
}
