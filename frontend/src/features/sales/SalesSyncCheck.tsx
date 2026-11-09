/** Sales · Sync & check routing after POS submit. No source writeback or implicit approval.
 * DEC-ROUTING-002, DEC-SALES-001; docs/03 A17; docs/06 §5.0.2 and §6.3a.
 */
import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, isApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { ErrorState, LoadingState } from "../../components/StateViews";
import {
  acknowledgeRouting, confirmStandardPlan, eligibleStandardPlan, isCfoRouting,
  newRetryKey, requestDefaultPlan, safeExternalRef, syncAndCheck,
  type SalesRun, type SyncResult,
} from "./salesSyncApi";

const panel = "rounded-card border border-border bg-surface p-5 space-y-4";
const button = "min-h-11 rounded-control bg-pine px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50";
const secondary = "min-h-11 rounded-control border border-border px-4 py-2 font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50";
const input = "min-h-11 w-full rounded-control border border-border bg-surface px-3 py-2 text-ink";
const code = "font-mono text-caption text-inkMuted";
const escalation = "Escalate this order to Dispatcher. Sales cannot override the checks, dates, vehicle count or routing decision.";

function StatusError({ error, retry }: { error: unknown; retry?: () => void }) {
  const api = isApiError(error) ? error : null;
  const status = api?.status;
  const label = status === 403 ? "Permission denied" :
    status === 404 ? "Order not found or outside your store" :
    status === 409 ? "Conflict — refresh before proceeding" :
    status === 422 ? "Invalid order or request" :
    status === 503 ? "Source or CFO unavailable" : "Request failed";
  const safeError = api ? new ApiError(api.code, label, api.correlationId, undefined, api.status) : error;
  return <section aria-label="Sync error" className="space-y-2">
    <ErrorState title={label} error={safeError} onRetry={status === 403 || status === 404 ? undefined : retry} />
    {(status === 409 || status === 503) && <p className="text-caption">{status === 503 ?
      "Nothing has been routed by this failed response. Retry only after the source is available." :
      "The server may have recorded a decision. Retry the same operation; do not start manual fulfilment without resolving the routing status."}</p>}
  </section>;
}
function MissingSkus({ result }: { result: SyncResult }) {
  const missing = result.missing_confirmed_skus ?? result.unmapped_skus ?? [];
  if (!missing.length) return <p className="text-caption">Some products may not have confirmed mapping; the API has not provided a safe SKU-level list.</p>;
  return <div className="space-y-2">
    <p className="font-semibold">Products without confirmed CFO mapping</p>
    <ul className="flex flex-wrap gap-2">{missing.map((sku, i) =>
      <li key={i} className="rounded-control border border-border px-3 py-2 font-mono text-caption">
        {sku.local_sku} · {sku.status ?? "Not confirmed"}
      </li>)}</ul>
  </div>;
}

export function SalesSyncCheck() {
  const authorized = useAuthStore(s => s.user?.roles.includes("sales") ?? false);
  const [reference, setReference] = useState("");
  const [eligibilityCheckedAt] = useState(() => Date.now());
  const [decision, setDecision] = useState<SyncResult | null>(null);
  const [activeRef, setActiveRef] = useState("");
  const [run, setRun] = useState<SalesRun | null>(null);
  const [approved, setApproved] = useState(false);
  const [manualReason, setManualReason] = useState("");
  const [manualStarted, setManualStarted] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const syncKeys = useRef(new Map<string, string>());
  const confirmKeys = useRef(new Map<number, string>());
  const sync = useMutation({ mutationFn: ({ ref, key }: { ref: string; key: string }) => syncAndCheck(ref, key),
    onSuccess: (result, variables) => {
      // Never derive routing from sync_status or missing SKUs; use authoritative decision.
      setDecision(result);
      setActiveRef(variables.ref);
      setRun(null);
      setApproved(false);
      setManualStarted(false);
      setAcknowledged(false);
    },
  });
  const planning = useMutation({ mutationFn: requestDefaultPlan,
    onSuccess: result => { setRun(result); setApproved(false); confirmKeys.current.clear(); },
  });
  const confirm = useMutation({ mutationFn: ({ id, key }: { id: number; key: string }) => confirmStandardPlan(id, key),
    onSuccess: (result, variables) => {
      if (result.order?.status === "APPROVED" && result.plan?.status === "approved" &&
          result.plan.id === variables.id) {
        setApproved(true);
      }
    },
  });
  const routingAck = useMutation({
    mutationFn: ({ choice, reason }: { choice: "legacy_acknowledged" | "manual_started"; reason?: string }) =>
      acknowledgeRouting(activeRef, choice, reason),
    onSuccess: (_, args) => {
      if (args.choice === "legacy_acknowledged") setAcknowledged(true);
      else setManualStarted(true);
    },
  });
  const ref = safeExternalRef(reference);
  const selectedPlan = run?.plans[0];
  const eligible = isCfoRouting(decision) && eligibleStandardPlan(run, eligibilityCheckedAt) && !approved;
  function startSync(event: React.FormEvent) {
    event.preventDefault();
    if (!authorized || !ref || sync.isPending) return;
    // Same external reference + same POST body = same key on retries.
    const key = syncKeys.current.get(ref) ?? newRetryKey();
    syncKeys.current.set(ref, key);
    setDecision(null); setRun(null); setApproved(false);
    sync.mutate({ ref, key });
  }
  function confirmClick() {
    if (!authorized || !eligible || !eligibleStandardPlan(run, Date.now()) || !selectedPlan || confirm.isPending) return;
    const key = confirmKeys.current.get(selectedPlan.id) ?? newRetryKey();
    confirmKeys.current.set(selectedPlan.id, key);
    confirm.mutate({ id: selectedPlan.id, key });
  }
  if (!authorized) return <section data-screen="SalesSyncCheck" role="alert">Sales access required.</section>;
  return <section data-screen="SalesSyncCheck" className="mx-auto max-w-5xl space-y-6">
    <header className="space-y-2">
      <p className="font-mono text-overline text-pine">SALES · CFO CHECK</p>
      <h1 className="text-h1 font-semibold text-ink">Sync & confirm delivery</h1>
      <p className="text-body text-inkMuted">First submit your order in the existing POS. Then check its fulfilment route here. CFO never edits POS orders.</p>
    </header>
    <form onSubmit={startSync} className={panel} aria-label="Search POS order">
      <h2 className="text-h2 font-semibold">01 · Find a submitted POS order</h2>
      <label className="block space-y-2">External POS order reference
        <input className={input} aria-label="External POS order reference" value={reference}
          onChange={e => setReference(e.target.value)} autoComplete="off"
          maxLength={100} placeholder="Enter the reference from POS" required />
      </label>
      {reference.trim() && !ref && <p role="alert" className="text-caption">Enter a valid order reference using letters, digits, dots, underscores, slashes or hyphens.</p>}
      <button type="submit" className={button} disabled={!ref || sync.isPending}>
        {sync.isPending ? "Syncing and checking…" : "Sync & check routing"}</button>
      {sync.isPending && <LoadingState rows={2} />}
      {sync.isError && <StatusError error={sync.error} retry={() => {
        const original = sync.variables;
        if (original) sync.mutate(original);
      }} />}
    </form>
    {decision && !sync.isPending && <section className={panel} aria-label="Routing decision">
      <h2 className="text-h2 font-semibold">02 · Routing decision</h2>
      <p className={code}>POS reference: {activeRef}</p>
      {decision.already_decided && <p role="status" className="rounded-control bg-chip p-3">Already decided · Original routing decision is immutable.</p>}
      {decision.routing_status === "unresolved" ? <>
        <p role="status" className="font-semibold">Unresolved — no routing decision recorded.</p>
        <p>The source data or SKU eligibility cannot be verified. Do not begin CFO planning or assume legacy routing.</p>
        {decision.retry_after_s !== undefined && <p>Server retry guidance: {decision.retry_after_s} seconds</p>}
        <button className={secondary} type="button" onClick={() => {
          const key = syncKeys.current.get(activeRef) ?? newRetryKey();
          syncKeys.current.set(activeRef, key);
          sync.mutate({ ref: activeRef, key });
        }}>Retry sync & check</button>
      </> : decision.routing_status === "legacy" ? <>
        <p role="status" className="font-semibold">Legacy routing — this entire order remains in the existing manual process.</p>
        <p>This is an immutable decision. Later product mapping will not move this order into CFO planning.</p>
        <MissingSkus result={decision} />
        <button type="button" className={secondary} disabled={acknowledged || routingAck.isPending}
          onClick={() => routingAck.mutate({ choice: "legacy_acknowledged" })}>
          {acknowledged ? "Legacy handover acknowledged" : "Acknowledge legacy handover"}</button>
      </> : isCfoRouting(decision) ? <>
        <p role="status" className="font-semibold">Synced · CFO routing confirmed.</p>
        <p>Source version {decision.source_version ?? "unknown"}. No delivery commitment exists until the server successfully approves a standard plan.</p>
        {decision.order_id && <button type="button" className={button}
          disabled={planning.isPending || approved}
          onClick={() => { setRun(null); planning.mutate(decision.order_id as number); }}>
          {planning.isPending ? "Checking feasibility…" : "Check feasibility"}</button>}
        {planning.isPending && <LoadingState rows={2} />}
        {planning.isError && <StatusError error={planning.error} retry={() => {
          if (planning.variables) planning.mutate(planning.variables);
        }} />}
        {run && <section className="space-y-3 border-t border-border pt-4" aria-label="Sales planning result">
          <h3 className="text-h3 font-semibold">{run.result === "feasible" ? "Feasible — not confirmed" : "No feasible standard plan"}</h3>
          {selectedPlan && <dl className="grid gap-3 sm:grid-cols-2">
            <div><dt className={code}>Warehouse</dt><dd>{selectedPlan.warehouse?.name ?? "Warehouse not disclosed"}</dd></div>
            <div><dt className={code}>Proposed delivery date</dt><dd>{selectedPlan.target_date ?? "Not verified"}</dd></div>
            <div><dt className={code}>Estimated arrival</dt><dd>{selectedPlan.eta_at ?? "Not verified"}</dd></div>
            <div><dt className={code}>Hold expires</dt><dd>{run.hold_expires_at ?? "Not verified"}</dd></div>
          </dl>}
          {!eligibleStandardPlan(run, eligibilityCheckedAt) && <p role="status" className="rounded-control bg-risk-lateRow p-3">
            Not eligible for Sales confirmation. {run.sales_block_reason ?? "Eligibility or the five verified checks are incomplete."} {escalation}
          </p>}
          {eligible && <div className="space-y-2">
            <p>Standard rank-1 plan, one truck, safe reserve, five server-confirmed gates and valid hold. Approval still requires a fresh server check.</p>
            <button className={button} type="button" disabled={confirm.isPending} onClick={confirmClick}>
              {confirm.isPending ? "Requesting confirmation…" : "Confirm standard delivery plan"}</button>
          </div>}
          {confirm.isError && <StatusError error={confirm.error} retry={() => {
            if (confirm.variables) confirm.mutate(confirm.variables);
          }} />}
          {confirm.isSuccess && !approved && <p role="alert">Confirmation response was not an approved-plan commit. {escalation}</p>}
          {approved && <p role="status" className="rounded-control bg-navActive p-3 font-semibold">
            CFO approval recorded by the server. Authoritative WMS reservation ACK and refreshed stock are not yet verified in this UI. Do not represent stock as guaranteed.
          </p>}
        </section>}
      </> : <p role="alert">Unknown routing status. No fulfilment action available.</p>}
      {routingAck.isError && <StatusError error={routingAck.error} retry={() => {
        if (routingAck.variables) routingAck.mutate(routingAck.variables);
      }} />}
    </section>}
    <section className={panel} aria-label="Manual fulfilment exception">
      <h2 className="text-h2 font-semibold">Already started manual fulfilment?</h2>
      <p>If manual work started before checking CFO, record the exception and reason. A CFO decision will not be flipped to legacy; any conflict is escalated to Dispatcher.</p>
      <label className="block space-y-2">Reason (required)
        <textarea className={input} aria-label="Manual fulfilment reason" rows={3} value={manualReason}
          maxLength={1000} onChange={e => setManualReason(e.target.value)}
          placeholder="Describe when manual fulfilment started…" /></label>
      <button type="button" className={secondary}
        disabled={!activeRef || !manualReason.trim() || manualStarted || routingAck.isPending}
        onClick={() => routingAck.mutate({ choice: "manual_started", reason: manualReason.trim() })}>
        {manualStarted ? "Exception recorded" : "Report manual fulfilment started"}</button>
      <p className="text-caption">For unresolved routing or server errors, contact Dispatcher before any further fulfilment steps.</p>
    </section>
    <p className="text-caption text-inkMuted">Only Sales for the originating store can act. The backend independently enforces store scope and plan-approval restrictions. No GPS, driver identity, or private customer contact data is displayed.</p>
    <Link to="/store/orders" className="inline-flex min-h-11 items-center text-pine underline">My store orders</Link>
  </section>;
}
