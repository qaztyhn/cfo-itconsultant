/** No feasible date · dispatcher-only, server-evidence-first (03 §5.3; 06 §6/Appendix A). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { fetchIntegrationOverview, summariseFreshness } from "../../api/integration";
import { isApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import {
  GATES, GATE_LABELS, fetchInfeasibleRun, fetchNegotiations, fetchVerifiedTransfers,
  gateStatus, readableNumber, recordNegotiation, replanAgreedDate, validIsoDate,
  type GateEvidence, type NegotiationInput, type NegotiationOutcome, type WarehouseChecks,
} from "./noFeasibleDateApi";

const panel = "rounded-card border border-border bg-surface p-4 md:p-6";
const field = "min-h-11 w-full rounded-control border border-border bg-surface px-3 py-2 text-body text-ink";
const action = "min-h-11 rounded-control bg-pine px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50";
const outline = "min-h-11 rounded-control border border-border px-4 py-2 font-semibold text-ink disabled:opacity-50";
const dateLabel = (date: string) => validIsoDate(date) ? date : "Unknown";

function GateCell({ gate }: { gate: GateEvidence | undefined }) {
  const state = gateStatus(gate);
  return <span aria-label={`${state}: ${gate?.code ?? "no verified result"}`}
    className="inline-flex flex-col gap-1 text-caption">
    <span className="font-semibold">{state === "passed" ? "✓ PASS" : state === "failed" ? "✕ FAIL" : "— UNKNOWN"}</span>
    {state !== "unknown" && gate?.code && <code className="font-mono text-inkMuted">{gate.code}</code>}
    {state === "failed" && gate?.detail?.inbound_available_on && validIsoDate(gate.detail.inbound_available_on) &&
      <span>Inbound available on {gate.detail.inbound_available_on}</span>}
  </span>;
}
function ChecksTable({ checks, rejected }: {
  checks?: WarehouseChecks[];
  rejected?: { warehouse_id?: number; failed_check?: string; code?: string; detail?: { message?: string } }[];
}) {
  // Flat rejected_candidates are a first-failure explanation, NOT evidence that earlier gates passed.
  const rows = checks?.length ? checks : rejected?.map(item => ({
    warehouse_id: item.warehouse_id,
    ...(GATES.includes(item.failed_check as typeof GATES[number])
      ? { [item.failed_check as string]: { passed: false, code: item.code, detail: item.detail } }
      : {}),
  })) ?? [];
  return <section className={panel + " space-y-3"} aria-label="Warehouse feasibility checks">
    <h2 className="text-h2 font-semibold">Five feasibility checks by warehouse</h2>
    <p className="text-caption text-inkMuted">Only checks explicitly returned by the API are PASS/FAIL. Missing or untested checks are UNKNOWN.</p>
    {!rows.length ? <EmptyState message="Per-warehouse feasibility evidence is unavailable." /> :
      <div className="overflow-x-auto">
        <table className="w-full min-w-[850px] text-left text-body">
          <caption className="sr-only">Five feasibility gates for each warehouse</caption>
          <thead><tr className="border-b border-border">
            <th className="p-3">Warehouse</th>{GATES.map(g => <th key={g} className="p-3">{GATE_LABELS[g]}</th>)}
          </tr></thead>
          <tbody>{rows.map((row, index) => <tr className="border-b border-border align-top" key={index}>
            <th scope="row" className="p-3 font-semibold">{typeof row.warehouse === "string" ? row.warehouse :
              row.warehouse?.name ?? (row.warehouse_id ? `Warehouse #${row.warehouse_id}` : "Unknown warehouse")}</th>
            {GATES.map(g => <td className="p-3" key={g}><GateCell gate={row[g]} /></td>)}
          </tr>)}</tbody>
        </table>
      </div>}
  </section>;
}
function NegotiationForm({ orderId, suggestedDate, onRecorded }: {
  orderId: number; suggestedDate?: string | null;
  onRecorded: (outcome: NegotiationOutcome, date: string) => void;
}) {
  const [date, setDate] = useState(suggestedDate && validIsoDate(suggestedDate) ? suggestedDate : "");
  const [outcome, setOutcome] = useState<NegotiationOutcome>("agreed");
  const [channel, setChannel] = useState<NegotiationInput["channel"]>("phone");
  const [contacted, setContacted] = useState("");
  const [note, setNote] = useState("");
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (value: NegotiationInput) => recordNegotiation(orderId, value),
    onSuccess: response => {
      if (!Number.isSafeInteger(response.id) || response.id <= 0) return;
      void client.invalidateQueries({ queryKey: ["no-feasible", "negotiations", orderId] });
      onRecorded(outcome, date);
    },
  });
  const contactTime = contacted ? new Date(contacted) : null;
  const hasValidContact = !!contactTime && Number.isFinite(contactTime.getTime()) && contactTime.getTime() <= Date.now();
  const canSubmit = validIsoDate(date) && hasValidContact && note.trim().length > 0 && !mutation.isPending;
  function save(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit || !contactTime) return;
    mutation.mutate({
      proposed_date: date, outcome, channel,
      contacted_at: contactTime.toISOString(), note: note.trim(),
    });
  }
  return <form onSubmit={save} className={panel + " space-y-4"} aria-label="Customer date negotiation">
    <h2 className="text-h2 font-semibold">Record customer date negotiation</h2>
    <p className="text-caption text-inkMuted">Recording an agreement does not approve a plan. No delivery date changes automatically.</p>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <label className="space-y-1 text-body">Proposed delivery date
        <input className={field} aria-label="Proposed delivery date" type="date" value={date}
          onChange={e => setDate(e.target.value)} required />
      </label>
      <label className="space-y-1 text-body">Customer outcome
        <select className={field} aria-label="Customer outcome" value={outcome}
          onChange={e => setOutcome(e.target.value as NegotiationOutcome)}>
          <option value="agreed">Agreed</option><option value="declined">Declined</option>
          <option value="unreachable">Unreachable</option>
        </select>
      </label>
      <label className="space-y-1 text-body">Contact channel
        <select className={field} aria-label="Contact channel" value={channel}
          onChange={e => setChannel(e.target.value as NegotiationInput["channel"])}>
          <option value="phone">Phone</option><option value="email">Email</option>
          <option value="in_person">In person</option>
        </select>
      </label>
      <label className="space-y-1 text-body">Actual contact time
        <input className={field} aria-label="Actual contact time" type="datetime-local" value={contacted}
          onChange={e => setContacted(e.target.value)} required />
      </label>
    </div>
    <label className="block space-y-1 text-body">Negotiation reason / contact note
      <textarea aria-label="Negotiation reason / contact note" className={field} rows={3}
        maxLength={1000} value={note} onChange={e => setNote(e.target.value)}
        placeholder="Record the customer's response and reason…" required />
    </label>
    <button type="submit" disabled={!canSubmit} className={action}> {mutation.isPending ? "Recording…" : "Record customer outcome"} </button>
    {mutation.isError && <ErrorState title="Negotiation not recorded" error={mutation.error}
      onRetry={() => mutation.reset()} />}
  </form>;
}

export function NoFeasibleDate({ runId: explicitRunId }: { runId?: number }) {
  const { runId: routeId } = useParams<{ runId: string }>();
  const id = explicitRunId ?? Number(routeId);
  const valid = Number.isSafeInteger(id) && id > 0;
  const authorized = useAuthStore(s => s.user?.roles.includes("dispatcher") ?? false);
  const [recorded, setRecorded] = useState<{ outcome: NegotiationOutcome; date: string } | null>(null);
  const [replanReason, setReplanReason] = useState("");
  const client = useQueryClient();
  const run = useQuery({
    queryKey: ["no-feasible", "run", id],
    queryFn: ({ signal }) => fetchInfeasibleRun(id, signal),
    enabled: authorized && valid, retry: false,
  });
  const orderId = run.data?.order_id;
  const transfers = useQuery({
    queryKey: ["no-feasible", "transfers", orderId],
    queryFn: ({ signal }) => fetchVerifiedTransfers(orderId as number, signal),
    enabled: authorized && !!orderId && run.data?.result === "infeasible", retry: false,
  });
  const history = useQuery({
    queryKey: ["no-feasible", "negotiations", orderId],
    queryFn: ({ signal }) => fetchNegotiations(orderId as number, signal),
    enabled: authorized && !!orderId && run.data?.result === "infeasible", retry: false,
  });
  const freshness = useQuery({
    queryKey: ["no-feasible", "freshness"],
    queryFn: ({ signal }) => fetchIntegrationOverview(signal),
    enabled: authorized && valid, retry: false,
  });
  const replan = useMutation({
    mutationFn: () => replanAgreedDate(orderId as number, recorded?.date ?? "", replanReason.trim()),
    onSuccess: result => {
      if (result.order_id === orderId && Number.isSafeInteger(result.id)) {
        void client.invalidateQueries({ queryKey: ["no-feasible"] });
      }
    },
  });
  const stale = !freshness.data || summariseFreshness(freshness.data).stale;
  if (!authorized) return <section data-screen="NoFeasibleDate" role="alert">Dispatcher access required.</section>;
  if (!valid) return <section data-screen="NoFeasibleDate"><EmptyState message="Select a valid planning run to inspect." /></section>;
  return <section data-screen="NoFeasibleDate" className="space-y-6">
    <header className="space-y-2">
      <p className="text-overline font-semibold text-pine">DISPATCHER · EXCEPTIONS</p>
      <h1 className="text-h1 font-semibold">No feasible date</h1>
      <p className="text-body text-inkMuted">Planning run #{id}. One warehouse must fulfil the whole order; no automatic customer-date changes.</p>
    </header>
    {run.isPending ? <LoadingState rows={5} /> : run.isError ?
      <ErrorState error={run.error} onRetry={() => void run.refetch()} /> :
      run.data?.result !== "infeasible" ? <EmptyState message="This planning run is not an infeasible result." /> :
      <>
        <div className="flex flex-wrap gap-2 text-caption">
          <span className="rounded-full bg-chip px-3 py-1 font-mono">NO_FEASIBLE_DATE</span>
          <span className="rounded-full bg-chip px-3 py-1 font-mono">ORDER #{run.data.order_id} · RUN {run.data.run_no}</span>
          <button className={outline} onClick={() => { void run.refetch(); void freshness.refetch(); void transfers.refetch(); }}
            type="button">Refresh evidence</button>
        </div>
        {stale && <div role="alert" className="rounded-card border border-risk-predictedLate-bg bg-risk-lateRow p-4">
          <strong>Data freshness unknown or stale.</strong> Verify stock and planning evidence before any new plan.
          {freshness.isError && <span className="block text-caption">Integration overview unavailable.</span>}
        </div>}
        <section className={panel + " space-y-2"}>
          <h2 className="text-overline font-semibold">Earliest feasible date</h2>
          {run.data.earliest_feasible_date && validIsoDate(run.data.earliest_feasible_date) ?
            <p className="text-h1 font-semibold">{run.data.earliest_feasible_date}</p> :
            <p className="text-body font-semibold">Not verified within the search horizon</p>}
          <p className="text-body text-inkMuted">Failed check: {run.data.failed_check ?? "Unknown"}. This is a proposal, not an agreed date or approved plan.</p>
        </section>
        <section className={panel + " space-y-3"} aria-label="Dates searched">
          <h2 className="text-h2 font-semibold">Dates searched</h2>
          {run.data.dates_searched?.length ?
            <div className="flex flex-wrap gap-2">{run.data.dates_searched.map((day, i) =>
              <div key={i} className="min-w-28 rounded-control border border-border px-3 py-2">
                <strong className="block font-mono">{dateLabel(day.date)}</strong>
                <span className="text-caption">{day.result === "first_feasible" ? "First feasible" :
                  day.result === "requested" ? "Requested" : day.result === "fail" ? `Failed: ${day.check ?? "unknown"}` : "Unknown"}</span>
              </div>)}</div> : <EmptyState message="The API has not supplied the dates searched. Search horizon cannot be verified." />}
        </section>
        <ChecksTable checks={run.data.per_warehouse_checks} rejected={run.data.rejected_candidates} />
        <section className={panel + " space-y-3"} aria-label="Usable stock evidence">
          <h2 className="text-h2 font-semibold">Usable stock and shortages</h2>
          {run.data.stock_matrix?.lines?.length ? <>
            <p className="text-caption">Server evidence as of planning date {dateLabel(run.data.stock_matrix.date)}. Missing values are unknown.</p>
            <div className="overflow-x-auto"><table className="w-full min-w-[580px] text-left text-body">
              <thead><tr className="border-b border-border"><th className="p-3">SKU / line</th>
                <th className="p-3">Needed</th><th className="p-3">Usable by warehouse (verified)</th></tr></thead>
              <tbody>{run.data.stock_matrix.lines.map((line, i) => <tr className="border-b border-border align-top" key={i}>
                <th scope="row" className="p-3">{line.name ?? "Product"}<span className="block font-mono text-caption">{line.local_sku} · {line.unit ?? "unit unknown"}</span></th>
                <td className="p-3">{readableNumber(line.needed)}</td>
                <td className="p-3"><div className="flex flex-wrap gap-2">
                  {Object.keys(line.usable ?? {}).length ? Object.entries(line.usable ?? {}).map(([warehouse, qty]) => {
                    const need = Number(line.needed);
                    const usable = qty === null ? NaN : Number(qty);
                    return <div key={warehouse} className="rounded-control border border-border p-2">
                      <strong>{warehouse}: {readableNumber(qty)}</strong>
                      {Number.isFinite(need) && Number.isFinite(usable) && need > usable &&
                        <span className="block text-caption text-risk-predictedLate-fg">Short {readableNumber(need - usable)}</span>}
                      {(line.inbound?.[warehouse] ?? []).map((inb, n) => <span key={n} className="block text-caption">
                        Inbound {readableNumber(inb.qty)} on {dateLabel(inb.eta)}</span>)}
                    </div>;
                  }) : <span>Warehouse availability unknown</span>}
                </div></td></tr>)}</tbody>
            </table></div></> : <EmptyState message="Verified stock matrix is unavailable. Stock and shortage are UNKNOWN, not zero." />}
        </section>
        <section className={panel + " space-y-3"} aria-label="Transfer suggestions">
          <h2 className="text-h2 font-semibold">Transfer suggestions</h2>
          <p className="text-caption text-inkMuted">Read-only evidence. WMS owns physical transfers; this screen never approves or executes a transfer.</p>
          {transfers.isPending ? <LoadingState rows={2} /> : transfers.isError ?
            <ErrorState error={transfers.error} onRetry={() => void transfers.refetch()} /> :
            transfers.data?.items.length ? <ul className="space-y-2">{transfers.data.items.map((s, i) =>
              <li key={i} className="rounded-control border border-border p-3">
                Source: {s.from_warehouse ?? (s.from_warehouse_id ? `Warehouse #${s.from_warehouse_id}` : "Unknown")}
                {" · "}Destination: {s.to_warehouse ?? (s.to_warehouse_id ? `Warehouse #${s.to_warehouse_id}` : "Unknown")}
                {" · "}Lead: {s.lead_days ?? "Unknown"} days · Distance: {s.distance_km ?? "Unknown"} km
                {s.lines?.map((line, n) => <p key={n} className="font-mono text-caption">Global #{line.global_product_id} · qty {readableNumber(line.qty)}</p>)}
              </li>)}</ul> : <EmptyState message="No verified transfer suggestions returned by the API." />}
        </section>
        {orderId && <NegotiationForm key={orderId} orderId={orderId} suggestedDate={run.data.earliest_feasible_date}
          onRecorded={(outcome, date) => setRecorded({ outcome, date })} />}
        {recorded && <section role="status" className={panel + " space-y-3"}>
          <h2 className="font-semibold">Customer outcome recorded by server: {recorded.outcome}</h2>
          {recorded.outcome === "agreed" ? <>
            <p>The agreement is recorded. Replanning requires a separate explicit action and fresh server checks.</p>
            <label className="block space-y-1">Reason for replanning
              <textarea className={field} aria-label="Reason for replanning" value={replanReason}
                onChange={e => setReplanReason(e.target.value)} rows={2} />
            </label>
            <button className={action} type="button" disabled={!replanReason.trim() || replan.isPending}
              onClick={() => replan.mutate()}>Run new plan for agreed date</button>
            {replan.isSuccess && <p>New planning run #{replan.data.id} returned by server. Review its feasibility before approval.</p>}
            {replan.isError && <ErrorState title="Replanning failed" error={replan.error} />}
          </> : <p>{recorded.outcome === "unreachable" ? "Follow-up reminder is server-managed; check the negotiation history." :
            "Customer declined. Any cancellation requires its own authorized, reasoned action."}</p>}
        </section>}
        <section className={panel + " space-y-2"} aria-label="Negotiation history">
          <h2 className="text-h2 font-semibold">Negotiation history</h2>
          {history.isPending ? <LoadingState rows={2} /> : history.isError ?
            <ErrorState error={history.error} onRetry={() => void history.refetch()} /> :
            !history.data?.items.length ? <EmptyState message="No customer date negotiations recorded." /> :
              <ul className="space-y-2">{history.data.items.map(row => <li key={row.id} className="border-b border-border pb-2 text-body">
                {dateLabel(row.proposed_date)} · {row.outcome} · {row.channel}
                {row.remind_at && <span className="block text-caption">Reminder: {row.remind_at}</span>}
              </li>)}</ul>}
        </section>
      </>}
    {run.isError && isApiError(run.error) && run.error.code === "STALE_DATA" &&
      <p role="status">No outdated stock has been treated as available.</p>}
  </section>;
}
