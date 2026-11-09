/**
 * 5.6 Preparation queue (docs/03 §5.6) — PR 1: READ-ONLY (capacity card + orders table). No action buttons yet.
 * Role access: the route guard (app/access.ts) lets only the warehouse role in; 403/404 from the API shows a denied state.
 * Warehouse and date come from useWarehouseSelection (sidebar scope + warehouse time zone). Polling every 20 s keeps
 * the current data on screen, so nothing is reset while the queue refreshes.
 * Owner: Dev 3 (stream C) — M6.
 */
import { Link } from "react-router-dom";
import { isApiError } from "../../api/client";
import { PATHS } from "../../app/access";
import { PageHeader } from "../../components/PageHeader";
import { EmptyState, ErrorState, LoadingState, Skeleton } from "../../components/StateViews";
import { CapacityCard } from "./prep-queue/CapacityCard";
import { formatClock } from "./prep-queue/format";
import { OrdersTable } from "./prep-queue/OrdersTable";
import { formatQueueDate } from "./prep-queue/queueDate";
import { usePrepQueue, PREP_QUEUE_POLL_MS } from "./prep-queue/usePrepQueue";
import { useWarehouseSelection, type PrepQueueScope } from "./prep-queue/useWarehouseSelection";

const DESCRIPTION = "Record what really happens. Each milestone updates the ETA immediately — no approval step.";

type ReadyScope = Extract<PrepQueueScope, { status: "ready" }>;

function Header({ overline }: { overline?: string }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <PageHeader overline={overline} title="Preparation queue" description={DESCRIPTION} />
      <Link
        to={PATHS.warehouseAttendance}
        className="inline-flex min-h-[48px] items-center rounded-control border bg-surface px-4 py-2 text-body font-semibold text-ink hover:bg-rowHover"
      >
        Edit shifts &amp; staff
      </Link>
    </div>
  );
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

function PrepQueueBody({ scope }: { scope: ReadyScope }) {
  const query = usePrepQueue(scope.warehouseId, scope.date);
  const { data, error } = query;

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

      <section aria-labelledby="orders-heading" className="flex flex-col gap-3">
        <div>
          <h2 id="orders-heading" className="text-h3 text-ink">
            Orders to prepare
          </h2>
          <p className="text-caption text-inkMuted">Approved plans only · in planned order</p>
        </div>
        {data.orders.length === 0 ? (
          <EmptyState message={`No approved orders to prepare for ${formatQueueDate(scope.date)}.`} />
        ) : (
          <OrdersTable orders={data.orders} timeZone={scope.timeZone} queueDate={scope.date} />
        )}
      </section>
    </div>
  );
}

export function PrepQueue() {
  const scope = useWarehouseSelection();

  return (
    <section data-screen="PrepQueue" className="flex flex-col gap-6">
      <Header overline={scope.status === "ready" ? `${scope.warehouse.name} · ${formatQueueDate(scope.date, "long")}` : undefined} />
      {scope.status === "ready" ? <PrepQueueBody scope={scope} /> : <ScopeNotice scope={scope} />}
    </section>
  );
}