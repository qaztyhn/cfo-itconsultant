/**
 * FilterChips — Hàng chip lọc có đếm: All · Needs plan · Awaiting approval · No feasible date · In execution · Manual · Delivered today.
 * Owner: Dev 3 (luồng C).
 */
export interface FilterChipsProps {
  className?: string;
}

export function FilterChips({ className }: FilterChipsProps) {
  // TODO(#C-FilterChips)
  return <div className={className} data-component="FilterChips" />;
}
