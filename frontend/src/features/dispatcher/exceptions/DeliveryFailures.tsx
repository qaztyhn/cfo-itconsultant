import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../../../api/client";
import { EmptyState, ErrorState, LoadingState } from "../../../components/StateViews";

type FailureAlert = {
  id: number;
  order_id: number;
  type: string;
  acknowledged_at: string | null;
};

export function DeliveryFailures({ userId, market }: { userId: number; market: string | null }) {
  const failures = useQuery({
    queryKey: ["dispatcher-delivery-failures", userId, market],
    queryFn: ({ signal }) => apiGet<{ items: FailureAlert[] }>(
      "/alerts", { type: "DELIVERY_FAILED", resolved: false }, signal,
    ),
    refetchInterval: 30_000,
    retry: false,
  });
  const acknowledge = useMutation({
    mutationFn: (id: number) => apiPost<{
      id: number; acknowledged_at: string | null;
    }>(`/alerts/${id}/ack`, {}),
    onSuccess: async () => { await failures.refetch(); },
  });

  if (failures.isPending) return <LoadingState rows={3} />;
  if (failures.isError) return <ErrorState error={failures.error}
    title="Delivery failures unavailable" onRetry={() => void failures.refetch()} />;

  const items = failures.data.items.filter(item => item.type === "DELIVERY_FAILED");
  if (!items.length) return <EmptyState message="No open delivery failures." />;

  return <section aria-label="Delivery failure alerts" className="space-y-3">
    {acknowledge.isError && <ErrorState error={acknowledge.error} title="Acknowledgment failed" />}
    {items.map(item => <article key={item.id} className="rounded-card border border-border bg-surface p-5">
      <h2 className="font-semibold text-ink">Delivery failed · Order #{item.order_id}</h2>
      <p className="mt-1 text-sm text-inkMuted">Alert #{item.id} · critical</p>
      {item.acknowledged_at
        ? <p role="status" className="mt-3 text-sm text-pine">Acknowledged</p>
        : <button type="button" className="mt-3 rounded-control border border-border px-4 py-2 text-sm"
          disabled={acknowledge.isPending} onClick={() => acknowledge.mutate(item.id)}>
          Acknowledge delivery failure
        </button>}
    </article>)}
  </section>;
}
