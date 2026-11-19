/**
 * 5.6 Preparation queue (docs/03 §5.6) — approved, server-validated milestones and exception reports.
 * Role access: the route guard (app/access.ts) lets only the warehouse role in; 403/404 from the API shows a denied state.
 * The warehouse comes from the sidebar scope and the business date comes from the API. Polling every 20 s keeps
 * the current data on screen, so nothing is reset while the queue refreshes.
 * Owner: Dev 3 (stream C) — M6.
 */
import { useState } from "react";
import { isApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { PageHeader } from "../../components/PageHeader";
import { EmptyState, ErrorState, LoadingState, Skeleton } from "../../components/StateViews";
import i18n from "../../i18n";
import { CapacityCard } from "./prep-queue/CapacityCard";
import { formatClock } from "./prep-queue/format";
import { OrdersTable } from "./prep-queue/OrdersTable";
import { PrepActionDialog, type ActionChoice } from "./prep-queue/PrepActionDialog";
import { ACTION_NAMES, EXCEPTION_ACTIONS, canPerform, type PrepEventType } from "./prep-queue/executionActions";
import type { PrepQueueOrder } from "./prep-queue/types";
import { formatQueueDate } from "./prep-queue/queueDate";
import { usePrepQueue, PREP_QUEUE_POLL_MS } from "./prep-queue/usePrepQueue";
import { useWarehouseSelection, type PrepQueueScope } from "./prep-queue/useWarehouseSelection";

const DESCRIPTION = "Record preparation and loading milestones. CFO confirms each event before the queue changes.";

type ReadyScope = Extract<PrepQueueScope, { status: "ready" }>;

function Header({ overline }: { overline?: string }) {
  return <PageHeader overline={overline} title="Preparation queue" description={DESCRIPTION} />;
}

/** 403 = no permission, 404 = outside the user's warehouse scope (docs/06 §3). Both hide the data. */
function isAccessDenied(error: unknown): boolean {
  return isApiError(error) && (error.status === 403 || error.status === 404);
}

function AccessDenied({ error }: { error: unknown }) {
  const reference = isApiError(error) ? error.correlationId : undefined;
  return (
    <div role="alert" className="flex flex-col gap-2 rounded-card border bg-surface p-6 shadow-card">
      <h2 className="text-h3 text-ink">No access to this queue</h2>
      <p className="text-body text-inkMuted">
        Your account cannot view the preparation queue for this warehouse, or the warehouse was not found. If you expect access, contact your administrator and quote the reference.
      </p>
      {reference && (
        <p className="flex items-center gap-2 text-caption text-inkMuted">
          <span>Reference</span>
          <code className="select-all font-mono text-ink">{reference}</code>
        </p>
      )}
    </div>
  );
}

function ScopeNotice({ scope }: { scope: Exclude<PrepQueueScope, { status: "ready" }> }) {
  switch (scope.status) {
    case "loading":
      return <LoadingState rows={3} />;
    case "error":
      return <ErrorState error={scope.error} onRetry={scope.retry} title="Warehouses could not be loaded" />;
    case "no-warehouse":
      return <EmptyState message="No warehouse is assigned to your account." />;
    case "choose-warehouse":
      return <EmptyState message="Select a warehouse in the sidebar to see its preparation queue." />;
    case "no-timezone":
      return <EmptyState message={`The time zone of ${scope.warehouse.name} is not available, so the queue for today cannot be shown. Contact your administrator.`} />;
  }
}

function PrepQueueBody({ scope, query }: { scope: ReadyScope; query: ReturnType<typeof usePrepQueue> }) {
  const { data, error } = query;
  const [choice, setChoice] = useState<ActionChoice | null>(null);
  const [reportOrderId, setReportOrderId] = useState("");
  const [acknowledged, setAcknowledged] = useState<string | null>(null);
  const user = useAuthStore((state) => state.user);
  const canWrite = user?.roles.includes("warehouse") === true && user.location_ids.includes(scope.warehouseId);
  function chooseAction(order: PrepQueueOrder, type: PrepEventType, tripId?: number, vehicleCode?: string) {
    if (!canWrite || !canPerform(order, type, tripId)) return;
    setAcknowledged(null);
    setChoice({ order, type, tripId, vehicleCode });
  }

  if (isAccessDenied(error)) {
    return <AccessDenied error={error} />;
  }
  if (data === undefined && error) {
    return <ErrorState error={error} onRetry={() => void query.refetch()} title="The preparation queue could not be loaded" />;
  }
  if (data === undefined) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-40" />
        <LoadingState rows={4} />
      </div>
    );
  }

  const queueDate = data.date ?? scope.date;
  const updated = query.dataUpdatedAt > 0 ? formatClock(new Date(query.dataUpdatedAt).toISOString(), scope.timeZone) : null;

  return (
    <div className="flex flex-col gap-6">
      {error ? (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-control bg-risk-atRisk-bg px-3 py-2 text-body text-risk-atRisk-fg">
          <p>
            Could not refresh the queue. {updated ? `Showing data from ${updated}.` : "Showing the last data received."}
          </p>
          <button type="button" onClick={() => void query.refetch()} className="min-h-[48px] rounded-control border bg-surface px-4 py-2 font-semibold text-ink hover:bg-rowHover">
            Retry
          </button>
        </div>
      ) : (
        <p className="flex items-center gap-2 text-caption text-inkMuted">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-pine" />
          <span>
            Live · refreshes every {PREP_QUEUE_POLL_MS / 1000} s{updated ? ` · last refreshed ${updated}` : ""}
          </span>
        </p>
      )}

      <CapacityCard capacity={data.capacity} timeZone={scope.timeZone} />
      {acknowledged && <p role="status" className="rounded-control bg-risk-onTrack-bg px-3 py-2 text-body text-risk-onTrack-fg">{acknowledged}</p>}

      <section aria-labelledby="orders-heading" className="flex flex-col gap-3">
        <div>
          <h2 id="orders-heading" className="text-h3 text-ink">
            Orders to prepare
          </h2>
          <p className="text-caption text-inkMuted">Approved plans only · in planned order</p>
        </div>
        {data.orders.length === 0 ? (
          <EmptyState message={`No approved orders to prepare for ${formatQueueDate(queueDate)}.`} />
        ) : (
          <OrdersTable orders={data.orders} timeZone={scope.timeZone} queueDate={queueDate}
            onAction={chooseAction} canWrite={canWrite} actionPending={choice !== null} />
        )}
      </section>
      <section aria-labelledby="warehouse-reports" className="space-y-3 rounded-card border bg-surface p-5 shadow-card">
        <h2 id="warehouse-reports" className="text-h3 text-ink">Report an exception</h2>
        <p className="text-caption text-inkMuted">
          {i18n.t("prepQueue.reportHelp")}
        </p>
        <label className="block max-w-md text-body font-semibold">
          Affected approved order
          <select className="mt-2 min-h-[48px] w-full rounded-control border border-border bg-surface px-3"
            value={reportOrderId} onChange={(event) => setReportOrderId(event.target.value)} aria-label="Affected approved order">
            <option value="">Choose an order</option>
            {data.orders.map((order) => <option key={order.order_id} value={order.order_id}>{order.order_no}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {EXCEPTION_ACTIONS.map((type) => {
            const order = data.orders.find((item) => String(item.order_id) === reportOrderId);
            return (
              <button key={type} type="button"
                disabled={!canWrite || !order || !canPerform(order, type) || choice !== null}
                className="min-h-[48px] rounded-control border border-border bg-surface px-4 py-3 text-left font-semibold text-ink disabled:opacity-50"
                onClick={() => { if (order) chooseAction(order, type); }}>
                {ACTION_NAMES[type]}
              </button>
            );
          })}
        </div>
      </section>
      {choice && <PrepActionDialog key={scope.warehouseId + ":" + queueDate + ":" + choice.order.order_id + ":" + choice.type + ":" + (choice.tripId ?? 0)}
        choice={choice} warehouseId={scope.warehouseId} onClose={() => setChoice(null)}
        onAcknowledged={async () => {
          const refreshed = await query.refetch();
          if (refreshed.error || !refreshed.data) throw new Error("Queue refresh failed.");
          setAcknowledged(ACTION_NAMES[choice.type] + " recorded for " + choice.order.order_no + ". The queue was refreshed.");
        }}
        onReload={async () => {
          const refreshed = await query.refetch();
          if (refreshed.error || !refreshed.data) throw new Error("Queue refresh failed.");
          setChoice(null);
        }} />}
    </div>
  );
}

export function PrepQueue() {
  const scope = useWarehouseSelection();
  // The backend interprets omitted date as today in the market, including with APP_NOW.
  const query = usePrepQueue(scope.status === "ready" ? scope.warehouseId : null);
  const queueDate = scope.status === "ready" ? query.data?.date ?? scope.date : undefined;

  return (
    <section data-screen="PrepQueue" className="flex flex-col gap-6">
      <Header overline={scope.status === "ready" && queueDate ? `${scope.warehouse.name} · ${formatQueueDate(queueDate, "long")}` : undefined} />
      {scope.status === "ready" ? <PrepQueueBody key={`${scope.warehouseId}:${queueDate}`} scope={scope} query={query} /> : <ScopeNotice scope={scope} />}
    </section>
  );
}
