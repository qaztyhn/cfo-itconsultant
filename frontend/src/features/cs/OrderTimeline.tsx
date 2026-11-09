/**
 * Timeline cho CS (docs/06 §5.5), đã lọc allowlist trong timeline.ts. Nhãn do UI tự dựng từ kind;
 * không render title/actor/detail tự do của server.
 * DEPENDENCY: backend timeline chưa được xác minh bằng response thật.
 */
import { useQuery } from "@tanstack/react-query";
import { RiskChip } from "../../components/RiskChip";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { csKeys, fetchTimeline } from "./api";
import { CsSection } from "./CsSection";
import { formatUtc, toRiskLevel } from "./format";
import type { CsTimelineItem } from "./timeline";

function TimelineEntry({ item }: { item: CsTimelineItem }) {
  switch (item.kind) {
    case "order_submitted":
      return <span className="text-body text-ink">Order submitted</span>;
    case "milestone":
      return <span className="text-body text-ink">Milestone{item.milestoneType ? `: ${item.milestoneType}` : ""}</span>;
    case "notification":
      return (
        <span className="text-body text-ink">
          Notification
          {[item.template, item.channel, item.status].filter(Boolean).length > 0
            ? `: ${[item.template, item.channel, item.status].filter(Boolean).join(" · ")}`
            : ""}
        </span>
      );
    case "eta":
      return (
        <span className="flex flex-wrap items-center gap-2 text-body text-ink">
          <span>ETA update: {formatUtc(item.forecastEta)}</span>
          <RiskChip level={toRiskLevel(item.riskStatus)} />
        </span>
      );
  }
}

export function OrderTimeline({ orderId }: { orderId: number }) {
  const timeline = useQuery({
    queryKey: csKeys.timeline(orderId),
    queryFn: ({ signal }) => fetchTimeline(orderId, signal),
    retry: false,
  });

  function body() {
    if (timeline.isPending) return <LoadingState rows={3} rowClassName="h-10" />;
    if (timeline.isError) {
      return <ErrorState error={timeline.error} title="Timeline unavailable" onRetry={() => void timeline.refetch()} />;
    }
    if (timeline.data.length === 0) return <p className="text-body text-inkMuted">No timeline events to show.</p>;
    return (
      <ol className="flex flex-col gap-2">
        {timeline.data.map((item, index) => (
          <li key={`${item.at}-${item.kind}-${index}`} className="flex flex-col gap-0.5 rounded-card border bg-surface px-4 py-2 sm:flex-row sm:items-center sm:gap-4">
            <time dateTime={item.at} className="font-mono text-caption text-inkMuted">
              {formatUtc(item.at)}
            </time>
            <TimelineEntry item={item} />
          </li>
        ))}
      </ol>
    );
  }

  return <CsSection title="Timeline">{body()}</CsSection>;
}