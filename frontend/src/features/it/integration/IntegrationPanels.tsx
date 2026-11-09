/** Read-only M2 dashboard sections. Only allowlisted projections from model.ts reach JSX. */
import {
  AlertCircle,
  ArrowUpRight,
  Clock3,
  Database,
  FileWarning,
  Route,
  ShieldAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PATHS } from "../../../app/access";
import { EmptyState, LoadingState } from "../../../components/StateViews";
import { FEEDS } from "./contracts";
import type { DisplayStatus, MatrixView, RejectView, RunView, SchedulerView, SourceView } from "./model";
import { readableNumber, summarizeRun } from "./model";

export function StatusTag({ status }: { status: DisplayStatus }) {
  const styles: Record<DisplayStatus, string> = {
    ok: "bg-emerald-100 text-emerald-900",
    partial: "bg-amber-100 text-amber-900",
    failed: "bg-rose-100 text-rose-900",
    running: "bg-sky-100 text-sky-900",
    blocked: "bg-stone-200 text-stone-800",
    unknown: "bg-slate-100 text-slate-700",
  };
  const names: Record<DisplayStatus, string> = {
    ok: "OK",
    partial: "PARTIAL · incomplete",
    failed: "FAILED",
    running: "RUNNING · incomplete",
    blocked: "BLOCKED",
    unknown: "UNVERIFIED",
  };
  return <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${styles[status]}`}>{names[status]}</span>;
}

export function SafeError({
  kind, correlation, retry,
}: { kind: string; correlation?: string | null; retry?: () => void }) {
  return (
    <div role="alert" className="rounded-card border border-rose-200 bg-rose-50 p-5">
      <p className="flex items-center gap-2 font-semibold text-rose-900">
        <AlertCircle className="h-5 w-5" aria-hidden="true" /> {kind}
      </p>
      <p className="mt-1 text-sm text-rose-900">Data is unavailable. Previous results cannot be treated as a current successful sync.</p>
      {correlation && <p className="mt-2 text-xs text-rose-800">Request reference: <code>{correlation}</code></p>}
      {retry && <button type="button" onClick={retry} className="mt-3 rounded-control border border-rose-300 bg-white px-4 py-2 text-sm font-semibold text-rose-900">Retry</button>}
    </div>
  );
}

export function SourceCards({ sources, loading }: { sources: SourceView[]; loading: boolean }) {
  return (
    <section aria-labelledby="sources-title">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 id="sources-title" className="text-xl font-bold text-ink">Source status</h2>
        <span className="font-mono text-xs uppercase tracking-wider text-inkMuted">5 defined adapters · status ≠ readiness</span>
      </div>
      {loading ? <LoadingState rows={2} /> : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {sources.map((source) => (
            <article key={source.entity} data-testid={`feed-${source.entity}`} className="flex min-h-[234px] flex-col rounded-card border border-border bg-surface p-5">
              <div className="mb-3 flex items-start justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-inkMuted">{source.source}</span>
                <Database className="h-4 w-4 text-inkMuted" aria-hidden="true" />
              </div>
              <h3 className="mb-3 font-semibold text-ink">{source.title}</h3>
              <div><StatusTag status={source.status} /></div>
              {source.entity === "stock" ? (
                <div className="mt-4 text-sm text-rose-900">
                  {source.availability === "unconfigured" ? "Stock ingestion is not configured. Historical runs cannot establish availability."
                    : "Stock availability has not been verified from a complete fresh batch."}
                  <p className="mt-2 font-semibold">Stock availability: unknown, never zero.</p>
                </div>
              ) : (
                <>
                  <p className="mt-4 font-mono text-2xl font-bold text-ink">{readableNumber(source.rows)}</p>
                  <p className="text-xs text-inkMuted">rows reported · {readableNumber(source.rejected)} rejected</p>
                  {source.entity === "products" && (
                    <p className="mt-2 text-xs text-ink">
                      {readableNumber(source.unmapped)} unmapped SKUs · <Link to={PATHS.itMapping} className="underline underline-offset-2">Product mapping <ArrowUpRight className="inline h-3 w-3" /></Link>
                    </p>
                  )}
                  <p className="mt-2 text-xs text-inkMuted">
                    Latest run: {source.latestStatus === "unknown" ? "unverified" : source.latestStatus}
                  </p>
                </>
              )}
              <div className="mt-auto border-t border-border pt-3 text-xs text-inkMuted">
                <p>Last run: {source.lastRunAt ?? "Not reported"}</p>
                {source.entity === "stock" && <p className="mt-1">Last run result: {source.latestStatus === "unknown" ? "Unverified" : source.latestStatus}</p>}
                <p className="mt-1">Last known success: {source.lastSuccessfulAt ?? "Not verified"}</p>
                <p className="mt-1">Data as of: {source.dataAsOf ?? "Unknown"}</p>
                <p className="mt-1">Freshness: {source.status === "failed" || source.status === "partial" ? "Latest sync incomplete; prior data may be stale" : "Not verified by this monitor"}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

const STEPS = [
  ["01", "FETCH", "Read source updates since last checkpoint"],
  ["02", "STAGE", "Keep raw records in restricted staging"],
  ["03", "NORMALISE", "Resolve canonical SKU and units"],
  ["04", "VALIDATE", "Reject invalid records without hiding partial runs"],
  ["05", "UPSERT", "Use source natural key and version"],
] as const;

export function WorkflowSteps() {
  return (
    <section aria-label="Documented sync pipeline" className="rounded-card border border-border bg-surface p-5">
      <h2 className="mb-4 font-semibold text-ink">Documented ingestion flow <span className="text-xs font-normal text-inkMuted">· not a live execution trace</span></h2>
      <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {STEPS.map(([n, title, detail]) => (
          <li key={n} className="rounded-control bg-stone p-4">
            <span className="font-mono text-xs font-semibold text-pine">{n} / {title}</span>
            <p className="mt-1 text-xs text-inkMuted">{detail}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function RecentRuns({
  runs, loading, onSelect,
}: { runs: RunView[]; loading: boolean; onSelect: (id: number) => void }) {
  return (
    <section aria-labelledby="runs-title" className="overflow-hidden rounded-card border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 p-5">
        <div>
          <h2 id="runs-title" className="text-xl font-bold text-ink">Recent integration runs</h2>
          <p className="mt-1 text-xs text-inkMuted">Loaded history only · partial/failed runs are not successful checkpoints</p>
        </div>
        <span className="font-mono text-xs text-inkMuted">{runs.length} loaded</span>
      </div>
      {loading ? <LoadingState rows={4} className="p-5" /> : runs.length === 0 ?
        <EmptyState message="No integration run history is available." /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[850px] text-left text-sm">
              <thead className="bg-stone text-xs uppercase tracking-wider text-inkMuted">
                <tr>{["Time (UTC)", "Source", "Checkpoint / file", "Status", "In", "OK", "Rejected", "Details"].map((head) =>
                  <th key={head} scope="col" className="px-4 py-3 font-semibold">{head}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-border">
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td className="px-4 py-3 font-mono text-xs">{run.startedAt ?? "Unknown"}</td>
                    <td className="px-4 py-3 font-semibold">{FEEDS.find((feed) => feed.entity === run.entity)?.title}</td>
                    <td className="max-w-[280px] px-4 py-3 text-xs text-inkMuted">{summarizeRun(run)}</td>
                    <td className="px-4 py-3"><StatusTag status={run.status} /></td>
                    <td className="px-4 py-3 font-mono">{readableNumber(run.rowsIn)}</td>
                    <td className="px-4 py-3 font-mono">{readableNumber(run.rowsOk)}</td>
                    <td className="px-4 py-3 font-mono">{readableNumber(run.rowsRejected)}</td>
                    <td className="px-4 py-3">
                      <button type="button" onClick={() => onSelect(run.id)} className="rounded-control border border-border px-3 py-2 text-xs font-semibold text-pine hover:bg-stone">
                        Inspect rejects <span className="sr-only">for run {run.id}</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </section>
  );
}

export function RejectedRecords({
  rejects, runId, loading,
}: { rejects: RejectView[]; runId: number | null; loading: boolean }) {
  return (
    <section aria-labelledby="rejects-title" className="rounded-card border border-border bg-surface p-5">
      <h2 id="rejects-title" className="text-xl font-bold text-ink">Rejected source records</h2>
      <p className="mt-1 text-xs text-inkMuted">
        Only approved reason-code explanations are displayed. Source keys, raw payloads, addresses and customer details are hidden.
      </p>
      {runId === null ? <EmptyState message="Select a run to inspect its rejected records." /> :
        loading ? <LoadingState rows={2} className="mt-5" /> :
          rejects.length === 0 ? <EmptyState message={`No rejected records returned for run ${runId}.`} /> :
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-stone text-xs uppercase text-inkMuted">
                  <tr><th className="p-3">Run</th><th className="p-3">Reject ID</th><th className="p-3">Reason</th><th className="p-3">Safe detail</th></tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rejects.map((reject, i) => (
                    <tr key={`${reject.id ?? "unknown"}-${i}`}>
                      <td className="p-3 font-mono">{runId}</td>
                      <td className="p-3 font-mono">{reject.id ?? "Unknown"}</td>
                      <td className="p-3"><code className="rounded bg-amber-100 px-2 py-1 text-xs text-amber-900">{reject.reasonCode}</code></td>
                      <td className="p-3 text-inkMuted">{reject.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>}
      <p className="mt-3 text-xs text-inkMuted">
        Unmapped catalogue SKUs are handled in Product mapping, not in this reject table.
      </p>
    </section>
  );
}

export function SystemPanels({ matrix, scheduler }: { matrix: MatrixView; scheduler: SchedulerView }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
      <section className="rounded-card border border-border bg-surface p-5" aria-labelledby="matrix-title">
        <div className="mb-3 flex items-center gap-2"><Route className="h-5 w-5 text-pine" /><h2 id="matrix-title" className="font-bold">Route matrix</h2></div>
        <p className="font-mono text-2xl font-bold">{readableNumber(matrix.pairs)}</p>
        <p className="text-xs text-inkMuted">Warehouse → site pairs reported</p>
        <div className="mt-3 space-y-1 text-sm">
          <p>Fallback pairs: <strong>{readableNumber(matrix.fallbackPairs)}</strong></p>
          <p>Provider: {matrix.provider ?? "Unverified"}</p>
          <p className="text-xs text-inkMuted">Fetched: {matrix.fetchedAt ?? "Not reported"}</p>
        </div>
        <p className="mt-3 text-xs text-inkMuted">Planning reads the cached matrix, not an engine-side live API. Missing coverage is not a valid zero.</p>
      </section>
      <section className="rounded-card border border-border bg-surface p-5" aria-labelledby="scheduler-title">
        <div className="mb-3 flex items-center gap-2"><Clock3 className="h-5 w-5 text-pine" /><h2 id="scheduler-title" className="font-bold">Scheduler health</h2></div>
        <div className="mb-3"><StatusTag status="unknown" /></div>
        <p className="text-sm text-ink">Active background worker is not verified. The D8 schedule and job contract are pending approval.</p>
        <p className="mt-3 text-xs text-inkMuted">Last reported tick: {scheduler.lastTickAt ?? "Not reported"}</p>
        <p className="mt-1 text-xs text-inkMuted">Reported status: {scheduler.lastTickStatus ?? "Unverified"}</p>
        <p className="mt-1 text-xs text-inkMuted">Reported interval: {scheduler.reportedIntervalMin === null ? "Unverified" : `${scheduler.reportedIntervalMin} min (unconfirmed)`}</p>
        <p className="mt-1 text-xs text-inkMuted">Reported job identifiers: {scheduler.jobs.length ? scheduler.jobs.join(", ") : "Not reported"}</p>
      </section>
      <section className="rounded-card border border-amber-200 bg-amber-50 p-5" aria-labelledby="feeds-title">
        <div className="mb-3 flex items-center gap-2"><ShieldAlert className="h-5 w-5 text-amber-900" /><h2 id="feeds-title" className="font-bold text-amber-950">Feed support ≠ live enablement</h2></div>
        <p className="text-sm text-amber-950">Documented source types: orders, customers, products, inbound, fleet and stock. Runtime availability must be verified per feed.</p>
        <div className="mt-3 flex items-start gap-2 text-sm text-amber-950">
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Stock feed remains blocked: scope, independent SKU evidence and atomic snapshot completeness have not been signed off.</span>
        </div>
      </section>
    </div>
  );
}
