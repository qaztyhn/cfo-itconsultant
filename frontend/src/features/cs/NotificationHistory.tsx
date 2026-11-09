/**
 * Lịch sử thông báo của đơn (GET /orders/{id}/notifications). Chỉ template, channel, status, thời điểm:
 * không subject, không nội dung thư, không người nhận.
 * DEPENDENCY: endpoint hiện là stub phía backend; lỗi hiện như "unavailable", không dựng dữ liệu giả.
 */
import { useQuery } from "@tanstack/react-query";
import { ErrorState, LoadingState } from "../../components/StateViews";
import { csKeys, fetchNotifications } from "./api";
import { CsSection } from "./CsSection";
import { formatUtc } from "./format";

export function NotificationHistory({ orderId }: { orderId: number }) {
  const notifications = useQuery({
    queryKey: csKeys.notifications(orderId),
    queryFn: ({ signal }) => fetchNotifications(orderId, signal),
    retry: false,
  });

  function body() {
    if (notifications.isPending) return <LoadingState rows={2} rowClassName="h-10" />;
    if (notifications.isError) {
      return (
        <ErrorState
          error={notifications.error}
          title="Notification history unavailable"
          onRetry={() => void notifications.refetch()}
        />
      );
    }
    if (notifications.data.length === 0) {
      return <p className="text-body text-inkMuted">No notifications recorded for this order.</p>;
    }
    return (
      <ul className="flex flex-col gap-2">
        {notifications.data.map((item) => (
          <li key={item.id} className="flex flex-wrap items-center gap-3 rounded-card border bg-surface px-4 py-2">
            <span className="font-mono text-body text-ink">{item.template ?? "—"}</span>
            <span className="text-body text-inkMuted">{item.channel ?? "—"}</span>
            <span className="rounded-full bg-chip px-2 py-0.5 font-mono text-overline uppercase text-ink">{item.status ?? "—"}</span>
            <span className="text-body text-inkMuted">{formatUtc(item.at)}</span>
          </li>
        ))}
      </ul>
    );
  }

  return <CsSection title="Notification history">{body()}</CsSection>;
}