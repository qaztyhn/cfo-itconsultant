/**
 * EventLog — Bảng TIME · EVENT · BY · EFFECT.
 * Owner: Dev 3 (luồng C).
 */
export interface EventLogProps {
  className?: string;
}

export function EventLog({ className }: EventLogProps) {
  // TODO(#C-EventLog)
  return <div className={className} data-component="EventLog" />;
}
