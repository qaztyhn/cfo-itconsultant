/**
 * PlanCard — Phương án: rank score lớn + km + Fill %, 5 check, Goods ready/Depart/ETA/Site closes, Slack, Planning reserve Safe/Tight; KHÔNG tiền (03 #1).
 * Owner: Dev 3 (luồng C).
 */
export interface PlanCardProps {
  className?: string;
}

export function PlanCard({ className }: PlanCardProps) {
  // TODO(#C-PlanCard)
  return <div className={className} data-component="PlanCard" />;
}
