/**
 * DataFreshness — 'Data as of 10:05 · next sync 10:10'; cờ cảnh báo khi dữ liệu cũ (stale).
 * `stale` do nơi gọi quyết định (từ /integration/overview hoặc ngưỡng stale_stock_min); thiếu asOf coi là chưa rõ độ mới.
 * Owner: Dev 3 (luồng C).
 */
import { formatTime } from "../lib/planFormat";

export interface DataFreshnessProps {
  asOf?: string | null;
  nextSyncAt?: string | null;
  stale?: boolean;
  className?: string;
}

export function DataFreshness({ asOf, nextSyncAt, stale = false, className }: DataFreshnessProps) {
  const unknown = !asOf;
  const warn = stale || unknown;
  return (
    <p
      role="status"
      data-component="DataFreshness"
      data-stale={warn ? "true" : "false"}
      className={[
        "inline-flex flex-wrap items-center gap-2 rounded-control border px-3 py-1 text-caption",
        warn ? "border-risk-atRisk-bg bg-risk-atRisk-bg text-risk-atRisk-fg" : "bg-chip text-ink",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {warn && <span aria-hidden="true">⚠</span>}
      <span className="font-mono">
        {unknown ? "Data freshness unknown" : `Data as of ${formatTime(asOf)}`}
        {nextSyncAt ? ` · next sync ${formatTime(nextSyncAt)}` : ""}
      </span>
      {warn && <span className="font-semibold">{unknown ? "Verify before approving." : "Stale data: stock and availability may have changed."}</span>}
    </p>
  );
}