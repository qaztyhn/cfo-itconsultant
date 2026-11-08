/**
 * JourneyBar — 6-segment horizontal progress bar for order fulfilment steps.
 * Owner: Dev 3 (luồng C).
 */

import type { OrderStatus } from "./StatusChip";

export interface JourneyBarProps {
  status: OrderStatus;
  milestoneOverdue?: string; // which segment is overdue
  className?: string;
}

const SEGMENTS = [
  { key: "approved", label: "Approved" },
  { key: "prep", label: "Prep" },
  { key: "goods_ready", label: "Goods ready" },
  { key: "loaded", label: "Loaded" },
  { key: "dispatched", label: "Dispatched" },
  { key: "delivered", label: "Delivered" },
] as const;

type SegmentKey = (typeof SEGMENTS)[number]["key"];

function getCompletedSegments(status: OrderStatus): SegmentKey[] {
  switch (status) {
    case "SUBMITTED":
    case "BLOCKED_UNMAPPED_SKU":
    case "PLANNED":
    case "NO_FEASIBLE_DATE":
      return [];
    case "APPROVED":
      return ["approved"];
    case "PREPARING":
      return ["approved", "prep"];
    case "GOODS_READY":
      return ["approved", "prep", "goods_ready"];
    case "LOADED":
      return ["approved", "prep", "goods_ready", "loaded"];
    case "DISPATCHED":
      return ["approved", "prep", "goods_ready", "loaded", "dispatched"];
    case "DELIVERED":
      return ["approved", "prep", "goods_ready", "loaded", "dispatched", "delivered"];
    case "FAILED":
    case "CANCELLED":
      return [];
    default:
      return [];
  }
}

export function JourneyBar({ status, milestoneOverdue, className }: JourneyBarProps) {
  const completed = getCompletedSegments(status);

  return (
    <div className={`flex gap-0.5 ${className ?? ""}`} aria-label="Order journey progress">
      {SEGMENTS.map((seg, i) => {
        const isDone = completed.includes(seg.key);
        const isOverdue = milestoneOverdue === seg.key;

        return (
          <div key={seg.key} className="flex-1 flex flex-col gap-1">
            <div
              className={`h-1.5 rounded-full transition-colors ${
                isOverdue
                  ? "bg-apricot"
                  : isDone
                  ? "bg-pine"
                  : "bg-border"
              }`}
              title={seg.label}
              aria-label={`${seg.label}: ${isDone ? "complete" : isOverdue ? "overdue" : "pending"}`}
            />
            {i === 0 || i === SEGMENTS.length - 1 ? (
              <span className="text-[9px] font-mono text-inkMuted uppercase tracking-wide">
                {seg.label}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
