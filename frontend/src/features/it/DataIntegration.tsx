/**
 * M2 IT Data Integration — docs/03 §5.9, docs/06 §15/Appendix A, US-INT-01..05,
 * US-ADM-01. Read-only monitoring plus documented admin-only order sync request.
 * Production never falls back to mock data when backend endpoints are incomplete.
 */
import { useState } from "react";
import { Activity, ArrowRight, RefreshCcw, ShieldAlert } from "lucide-react";
import { isApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { EmptyState } from "../../components/StateViews";
import {
  RecentRuns, RejectedRecords, SafeError, SourceCards, SystemPanels, WorkflowSteps,
} from "./integration/IntegrationPanels";
import { useIntegrationDashboard } from "./integration/useIntegrationDashboard";

const REF_PATTERN = /^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$/;

function requestRef(error: unknown): string | null {
  return isApiError(error) && error.correlationId && REF_PATTERN.test(error.correlationId)
    ? error.correlationId : null;
}

function safeErrorHeading(error: unknown, label: string): string {
  if (!isApiError(error)) return `${label} unavailable`;
  if (error.code === "STOCK_UNAVAILABLE" || error.status === 503) return "Source snapshot unavailable (not zero)";
  if (error.status === 403) return "Access denied";
  if (error.status === 409 && error.code === "SYNC_IN_PROGRESS") return "A sync run is already in progress";
  return `${label} unavailable`;
}

export function DataIntegration() {
  const user = useAuthStore((store) => store.user);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const dashboard = useIntegrationDashboard(selectedRunId);
  const {
    allowed, isPreview, overviewQuery, runsQuery, rejectsQuery, manualSync,
    sources, runs, rejects, matrix, scheduler,
  } = dashboard;
  const activeRunId = selectedRunId ?? runs.find((run) => (run.rowsRejected ?? 0) > 0)?.id ?? null;

  // Selecting the initial incomplete run must also enable its reject request:
  // the query hook below is keyed by the same resolved ID, not an unrelated state.
  // Until a user selects a run, explicitly invite inspection rather than infer
  // that rejected data has been fetched.
  const shownRunId = selectedRunId;

  if (!allowed) {
    return (
      <section data-screen="DataIntegration" role="alert" className="rounded-card border border-border bg-surface p-8">
        <h1 className="text-2xl font-bold text-ink">Data integration</h1>
        <p className="mt-3 text-inkMuted">Admin access is required. No source data was loaded.</p>
      </section>
    );
  }

  const loading = overviewQuery.isPending || runsQuery.isPending;
  const refreshing = overviewQuery.isFetching || runsQuery.isFetching;

  const syncMessage = manualSync.isSuccess
    ? "Sync request accepted. Check a subsequent run for its actual outcome."
    : manualSync.isError && isApiError(manualSync.error) && manualSync.error.code === "SYNC_IN_PROGRESS"
      ? "Orders sync is already running. No second run was started."
      : manualSync.isError
        ? "Sync request could not be confirmed. Check backend availability and retry only after verification."
        : null;

  return (
    <section data-screen="DataIntegration" className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-5">
        <div className="min-w-0">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-apricot">
            Admin · Market adapters · {user?.market ?? "Market not assigned"}
          </p>
          <h1 className="mt-2 text-4xl font-bold tracking-tight text-ink">Data integration</h1>
          <p className="mt-2 max-w-2xl text-sm text-inkMuted">
            Inspect source freshness, completed and partial runs, rejected records and verified route coverage.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => {
              void overviewQuery.refetch();
              void runsQuery.refetch();
              if (shownRunId !== null) void rejectsQuery.refetch();
            }}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-control border border-border bg-surface px-4 py-2.5 text-sm font-semibold text-pine disabled:opacity-50"
          >
            <RefreshCcw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} aria-hidden="true" />
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button
            type="button"
            disabled={isPreview || manualSync.isPending}
            onClick={() => manualSync.mutate()}
            className="inline-flex items-center gap-2 rounded-control bg-pine px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Activity className="h-4 w-4" aria-hidden="true" />
            {manualSync.isPending ? "Requesting…" : "Run POS orders sync"}
          </button>
        </div>
      </header>

      {isPreview && (
        <div role="status" className="rounded-card border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950" data-testid="integration-contract-preview">
          <strong>CONTRACT PREVIEW · NOT LIVE DATA.</strong> Synthetic responses demonstrate the dashboard.
          No scheduler or source worker is confirmed, and manual sync is unavailable in preview mode.
        </div>
      )}
      <div className="rounded-card border border-border bg-surface p-4 text-sm text-inkMuted">
        This dashboard makes no routing decision, does not write to POS/WMS/ERP and cannot use an unavailable stock feed for a delivery promise.
        <span className="ml-1 font-semibold text-ink">A failed or partial run is never presented as a completed sync.</span>
      </div>

      {syncMessage && (
        <div role="status" className="rounded-card border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          {syncMessage}
        </div>
      )}
      {manualSync.isError && <p className="text-xs text-inkMuted">Sync request reference: {requestRef(manualSync.error) ?? "Not provided"}</p>}

      {overviewQuery.isError && (
        <SafeError kind={safeErrorHeading(overviewQuery.error, "Source overview")}
          correlation={requestRef(overviewQuery.error)} retry={() => void overviewQuery.refetch()} />
      )}
      {runsQuery.isError && (
        <SafeError kind={safeErrorHeading(runsQuery.error, "Integration history")}
          correlation={requestRef(runsQuery.error)} retry={() => void runsQuery.refetch()} />
      )}

      <SourceCards sources={sources} loading={loading && !overviewQuery.isError && !runsQuery.isError} />

      <WorkflowSteps />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-5">
          <RecentRuns runs={runs} loading={runsQuery.isPending && !runsQuery.isError} onSelect={setSelectedRunId} />
          {shownRunId !== null && rejectsQuery.isError && (
            <SafeError kind={safeErrorHeading(rejectsQuery.error, "Rejected records")}
              correlation={requestRef(rejectsQuery.error)} retry={() => void rejectsQuery.refetch()} />
          )}
          <RejectedRecords
            runId={shownRunId} rejects={rejects}
            loading={shownRunId !== null && rejectsQuery.isPending && !rejectsQuery.isError}
          />
          {activeRunId !== null && shownRunId === null && (
            <div className="rounded-control border border-border bg-stone p-4 text-sm text-inkMuted">
              Run {activeRunId} reports rejected records. Select <strong>Inspect rejects</strong> in the table to retrieve safe details.
            </div>
          )}
        </div>
        <aside className="space-y-5" aria-label="Integration diagnostics">
          <SystemPanels matrix={matrix} scheduler={scheduler} />
          <div className="rounded-card border border-border bg-deepPine p-5 text-white">
            <ShieldAlert className="h-5 w-5 text-apricot" aria-hidden="true" />
            <h2 className="mt-3 font-bold">Restricted operations</h2>
            <p className="mt-2 text-sm text-white/80">
              Only an admin can request a documented orders sync. Stock sync, CSV upload and
              “run all” are not offered without verified runtime contracts.
            </p>
            <p className="mt-3 text-xs text-white/70">A 503 STOCK_UNAVAILABLE means unknown stock, not an empty batch.</p>
          </div>
        </aside>
      </div>
      {!loading && runs.length === 0 && !runsQuery.isError && (
        <EmptyState message="No runs are available. This is not evidence of successful or completed ingestion." />
      )}
      <footer className="flex items-center gap-2 border-t border-border pt-5 text-xs text-inkMuted">
        <span>US-INT-01..05 · US-ADM-01/02</span><ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Operational facts only where the source contract is verified.</span>
      </footer>
    </section>
  );
}
