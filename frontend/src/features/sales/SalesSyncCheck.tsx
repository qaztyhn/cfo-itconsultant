/** Sales · Sync & check routing after POS submit. No source writeback or implicit approval.
 * DEC-ROUTING-002, DEC-SALES-001; docs/03 A17; docs/06 §5.0.2 and §6.3a.
 */
import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, isApiError } from "../../api/client";
import { planningNow } from "../../lib/useHoldExpired";
import { useAuthStore } from "../../app/store";
import { ErrorState, LoadingState } from "../../components/StateViews";
import {
  acknowledgeRouting, confirmStandardPlan, eligibleSalesPlan, isCfoRouting,
  listDateAgreements, newRetryKey, recordDateAgreement, requestDefaultPlan,
  safeExternalRef, syncAndCheck, validReasonCode,
  type NegotiationInput, type SalesPlanningParams, type SalesRun, type SyncResult,
} from "./salesSyncApi";

const panel = "rounded-card border border-border bg-surface p-5 space-y-4";
const button = "min-h-11 rounded-control bg-pine px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50";
const secondary = "min-h-11 rounded-control border border-border px-4 py-2 font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50";
const input = "min-h-11 w-full rounded-control border border-border bg-surface px-3 py-2 text-ink";
const code = "font-mono text-caption text-inkMuted";
const escalation = "Contact Dispatcher if shared pre-approval resources cannot be verified. Sales cannot override failed checks, routing or post-approval decisions.";

function StatusError({ error, retry }: { error: unknown; retry?: () => void }) {
  const api = isApiError(error) ? error : null;
  const status = api?.status;
  const networkUnavailable = api?.code === "NETWORK_ERROR" || status === 0;
  // A FastAPI 404 with no standard CFO error body means the requested route
  // was not found. A structured CFO 404 still means order-not-found/scope.
  const endpointUnavailable = (status === 404 || status === 405) && api?.code === "UNKNOWN_ERROR";
  const label = api?.code === "HOLD_EXPIRED" ? "Planning hold expired — Plan Again" :
    api?.code === "DATE_AGREEMENT_REQUIRED" ? "Customer date agreement required" :
    api?.code === "REASON_REQUIRED" ? "A valid reason code is required" :
    api?.code === "PLAN_NOT_APPROVABLE" ? "This plan cannot be approved — contact Dispatcher" :
    networkUnavailable ? "Cannot reach CFO API" :
    endpointUnavailable ? "Sync & check endpoint unavailable" :
    status === 401 ? "Session expired or invalid" :
    status === 403 ? "Permission denied" :
    status === 404 ? "Order not found or outside your store" :
    status === 409 ? "Conflict — refresh before proceeding" :
    status === 422 ? "Invalid order or request" :
    status === 503 ? "Source or CFO unavailable" : "Request failed";
  const safeError = api ? new ApiError(api.code, label, api.correlationId, undefined, api.status) : error;
  return <section aria-label="Sync error" className="space-y-2">
    <ErrorState title={label} error={safeError} onRetry={status === 401 || status === 403 || status === 404 || status === 405 ||
      ["HOLD_EXPIRED", "PLAN_NOT_APPROVABLE", "DATE_AGREEMENT_REQUIRED", "REASON_REQUIRED"].includes(api?.code ?? "")
      ? undefined : retry} />
    {networkUnavailable && <p className="text-caption">
      The browser could not connect to the configured CFO API. Check that the backend is running,
      VITE_API_URL points to its /api/v1 endpoint, and the backend permits this local frontend origin
      (for example localhost:5174). No routing decision has been verified.
    </p>}
    {endpointUnavailable && <p className="text-caption">
      This CFO API does not expose POST /integration/orders/sync-now. Deploy the reviewed backend
      Sync &amp; Check endpoint before retrying. No routing decision has been verified.
    </p>}
    {(status === 409 || status === 503) && <p className="text-caption">{api?.code === "HOLD_EXPIRED" ?
      "The hold is no longer valid. Use Plan Again to obtain a new feasibility run." :
      api?.code === "PLAN_NOT_APPROVABLE" ?
      "No delivery has been committed. Contact Dispatcher for unverified competing orders or WMS evidence." :
      status === 503 ?
      "No routing result was verified. The server may have recorded a decision; retry the same operation before proceeding." :
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
  const [decision, setDecision] = useState<SyncResult | null>(null);
  const [activeRef, setActiveRef] = useState("");
  const [run, setRun] = useState<SalesRun | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [reasonCode, setReasonCode] = useState("");
  const [reasonText, setReasonText] = useState("");
  const [rerunTargetDate, setRerunTargetDate] = useState("");
  const [agreementChannel, setAgreementChannel] = useState<NegotiationInput["channel"]>("phone");
  const [agreementFor, setAgreementFor] = useState<{ planId: number; date: string; id: number } | null>(null);
  const [approved, setApproved] = useState(false);
  const [manualReason, setManualReason] = useState("");
  const [manualStarted, setManualStarted] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const syncKeys = useRef(new Map<string, string>());
  // Never mutate a submitted approval body during an uncertain retry.
  const confirmKeys = useRef(new Map<string, string>());
  const history = useMutation({ mutationFn: listDateAgreements });
  const sync = useMutation({
    mutationFn: ({ ref, key }: { ref: string; key: string }) => syncAndCheck(ref, key),
    onSuccess: (result, variables) => {
      setDecision(result); setActiveRef(variables.ref);
      setRun(null); setSelectedId(null); setAgreementFor(null);
      history.reset(); setApproved(false); setManualStarted(false); setAcknowledged(false);
    },
  });
  const planning = useMutation({
    mutationFn: ({ orderId, params }: { orderId: number; params: SalesPlanningParams }) =>
      requestDefaultPlan(orderId, params),
    onSuccess: result => {
      if (result.order_id !== decision?.order_id || !["initial", "rerun"].includes(result.kind)) {
        setRun(null); return;
      }
      setRun(result); setSelectedId(result.plans[0]?.id ?? null);
      setApproved(false); setAgreementFor(null); setReasonCode(""); setReasonText("");
      confirmKeys.current.clear();
      history.mutate(result.order_id);
    },
  });
  const negotiation = useMutation({
    mutationFn: ({ orderId, body }: { orderId: number; planId: number; body: NegotiationInput }) =>
      recordDateAgreement(orderId, body),
    onSuccess: (result, variables) => {
      if (variables.orderId === decision?.order_id) {
        setAgreementFor({ planId: variables.planId, date: variables.body.proposed_date, id: result.id });
        history.mutate(variables.orderId);
      }
    },
  });
  const confirm = useMutation({
    mutationFn: ({ id, key, body }: { id: number; key: string; body: {
      reason_code?: string; reason_text?: string; date_negotiation_id?: number;
    } }) => confirmStandardPlan(id, key, body),
    onSuccess: (result, variables) => {
      if (result.order?.status === "APPROVED" &&
          result.order.id === decision?.order_id &&
          result.plan?.status === "approved" && result.plan.id === variables.id) {
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
  const selectedPlan = run?.plans.find(p => p.id === selectedId);
  const eligible = isCfoRouting(decision) && selectedPlan !== undefined &&
    eligibleSalesPlan(run, selectedPlan.id, planningNow()) && !approved;
  const needsDateAgreement = Boolean(selectedPlan && (
    selectedPlan.requires_date_agreement === true ||
    (run?.requested_date && selectedPlan.target_date !== run.requested_date)
  ));
  const agreedId = selectedPlan && (
    agreementFor?.planId === selectedPlan.id && agreementFor.date === selectedPlan.target_date
      ? agreementFor.id
      : history.data?.items.find(item =>
          item.outcome === "agreed" && item.proposed_date === selectedPlan.target_date)?.id
  );
  const reasonValid = !selectedPlan || selectedPlan.rank === 1 || validReasonCode(reasonCode.trim());
  function startSync(event: React.FormEvent) {
    event.preventDefault();
    if (!authorized || !ref || sync.isPending) return;
    const key = syncKeys.current.get(ref) ?? newRetryKey();
    syncKeys.current.set(ref, key);
    setDecision(null); setRun(null); setSelectedId(null); setApproved(false);
    sync.mutate({ ref, key });
  }
  function planClick() {
    if (!authorized || !isCfoRouting(decision) || planning.isPending || approved) return;
    const params: SalesPlanningParams = {
      ...(rerunTargetDate ? { target_date: rerunTargetDate } : {}),
      ...(run ? { reason_code: "criteria_change", reason_text: "Sales requested new feasible options" } : {}),
    };
    planning.mutate({ orderId: decision.order_id, params });
  }
  function confirmClick() {
    if (!authorized || !eligible || !selectedPlan || !run || confirm.isPending ||
        !reasonValid || (needsDateAgreement && !agreedId)) return;
    const body = {
      ...(selectedPlan.rank > 1 ? { reason_code: reasonCode.trim() } : {}),
      ...(reasonText.trim() ? { reason_text: reasonText.trim() } : {}),
      ...(needsDateAgreement && agreedId ? { date_negotiation_id: agreedId } : {}),
    };
    const signature = JSON.stringify({ plan_id: selectedPlan.id, body });
    const key = confirmKeys.current.get(signature) ?? newRetryKey();
    confirmKeys.current.set(signature, key);
    confirm.mutate({ id: selectedPlan.id, key, body });
  }
  if (!authorized) return <section data-screen="SalesSyncCheck" role="alert">Sales access required.</section>;
  return <section data-screen="SalesSyncCheck" className="mx-auto max-w-5xl space-y-6">
    <header className="space-y-2">
      <p className="font-mono text-overline text-pine">SALES · CFO CHECK</p>
      <h1 className="text-h1 font-semibold text-ink">Sync & Check</h1>
      <p className="text-body text-inkMuted">First submit your order in the existing POS. Then check its fulfilment route here. CFO never edits POS orders.</p>
    </header>
    <form onSubmit={startSync} className={panel} aria-label="Search POS order">
      <h2 className="text-h2 font-semibold">01 · Find a submitted POS order</h2>
      <label className="block space-y-2">External POS order reference
        <input className={input} aria-label="External POS order reference" value={reference}
          onChange={e => {
            setReference(e.target.value);
            if (e.target.value.trim() !== activeRef) {
              setDecision(null); setRun(null); setSelectedId(null);
              setAgreementFor(null); setApproved(false); setActiveRef("");
            }
          }} autoComplete="off"
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
        <p>Source version {decision.source_version ?? "unknown"}. Delivery is not committed until the selected proposal is approved by the server.</p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="block space-y-1">Target date preference (optional)
            <input type="date" className={input} aria-label="Target date preference" value={rerunTargetDate}
              onChange={e => setRerunTargetDate(e.target.value)} disabled={approved} />
          </label>
          <button type="button" className={button} disabled={planning.isPending || approved}
            onClick={planClick}>{planning.isPending ? "Checking feasibility…" :
            run ? "Plan Again" : "Check feasibility"}</button>
        </div>
        {planning.isPending && <LoadingState rows={2} />}
        {planning.isError && <StatusError error={planning.error} retry={() => {
          if (planning.variables) planning.mutate(planning.variables);
        }} />}
        {run && <section className="space-y-4 border-t border-border pt-4" aria-label="Sales planning result">
          <h3 className="text-h3 font-semibold">{run.result === "feasible" ?
            "Feasible — not confirmed" : "No feasible plans"}</h3>
          <p className={code}>Planning run #{run.run_no} · Hold expires: {run.hold_expires_at ?? "Unavailable"}
            {run.requested_date && ` · Requested date: ${run.requested_date}`}</p>
          <fieldset className="space-y-3" disabled={approved || planning.isPending}>
            <legend className="font-semibold">Choose one server-ranked proposal</legend>
            {run.plans.map(plan => <label key={plan.id} className="block rounded-control border border-border p-3 space-y-2">
              <span className="flex items-center gap-3">
                <input type="radio" name="sales-plan" aria-label={`Rank ${plan.rank}`}
                  checked={selectedId === plan.id}
                  onChange={() => { setSelectedId(plan.id); setAgreementFor(null); confirm.reset(); }} />
                <strong>Rank {plan.rank}</strong>
                <span className={code}>Plan #{plan.id} · {plan.status}</span>
              </span>
              <span className="block">Warehouse: {plan.warehouse?.name ?? "Not verified"} ·
                {plan.vehicle_count} vehicle{plan.vehicle_count === 1 ? "" : "s"} ·
                Delivery: {plan.target_date} · ETA: {plan.eta_at}</span>
              <span className="block text-caption">
                Five gates: {(["stock", "preparation", "truck", "site_date", "safety"] as const)
                  .map(g => `${g} ${plan.checks?.[g]?.passed === true ? "✓" : "UNKNOWN"}`).join(" · ")}
              </span>
              {plan.requires_date_agreement && <span className="block text-caption">Customer date agreement required</span>}
            </label>)}
            {run.plans.length === 0 && <p>No server-verified option is available. Try Plan Again or contact Dispatcher.</p>}
          </fieldset>
          {selectedPlan && !eligible && !approved && <p role="status" className="rounded-control bg-risk-lateRow p-3">
            This proposal cannot currently be approved. {run.sales_block_reason ?? "Hold or five-gate evidence unavailable."}
            {" "}Use Plan Again if the hold has expired. {escalation}
          </p>}
          {eligible && selectedPlan && <div className="space-y-3 border-t border-border pt-3">
            {selectedPlan.rank > 1 && <label className="block space-y-1">Reason code (required for ranks 2–3)
              <input className={input} aria-label="Alternative reason code" value={reasonCode}
                onChange={e => setReasonCode(e.target.value)} maxLength={64}
                placeholder="e.g. closest_to_customer" />
              {!reasonValid && <span role="alert" className="block text-caption">
                Use lowercase letters, numbers and underscores; start with a letter.
              </span>}
            </label>}
            <label className="block space-y-1">Additional reason (optional)
              <textarea className={input} aria-label="Approval reason note" rows={2} maxLength={1000}
                value={reasonText} onChange={e => setReasonText(e.target.value)} />
            </label>
            {needsDateAgreement && <section className="space-y-2 rounded-control border border-border p-3"
              aria-label="Customer date agreement">
              <h4 className="font-semibold">Agree a different delivery date before approval</h4>
              <p>Selected date: {selectedPlan.target_date}. Original requested date: {run.requested_date ?? "Not provided"}.</p>
              <label className="block space-y-1">Customer contact channel
                <select className={input} aria-label="Customer contact channel" value={agreementChannel}
                  onChange={e => setAgreementChannel(e.target.value as NegotiationInput["channel"])}>
                  <option value="phone">Phone</option><option value="email">Email</option>
                  <option value="in_person">In person</option>
                </select>
              </label>
              <button className={secondary} type="button" disabled={negotiation.isPending || Boolean(agreedId)}
                onClick={() => negotiation.mutate({
                  orderId: run.order_id, planId: selectedPlan.id,
                  body: { proposed_date: selectedPlan.target_date, outcome: "agreed",
                    channel: agreementChannel, contacted_at: new Date().toISOString() },
                })}>{agreedId ? "Agreed date recorded" :
                  negotiation.isPending ? "Recording agreement…" : "Record customer agreement"}</button>
              {negotiation.isError && <StatusError error={negotiation.error} />}
              {history.isError && <p className="text-caption">Existing agreement history could not be loaded.</p>}
              <p className="text-caption">Record agreement only after the customer has confirmed the date.
                This action does not change the committed delivery date.</p>
            </section>}
            <button className={button} type="button"
              disabled={confirm.isPending || !reasonValid || (needsDateAgreement && !agreedId)}
              onClick={confirmClick}>
              {confirm.isPending ? "Approving…" : `Approve rank ${selectedPlan.rank}`}</button>
            <p className="text-caption">A fresh server-side five-gate and WMS check still applies to each plan,
              including tight or multi-vehicle options.</p>
          </div>}
          {confirm.isError && <StatusError error={confirm.error} retry={() => {
            if (confirm.variables) confirm.mutate(confirm.variables);
          }} />}
          {confirm.isSuccess && !approved && <p role="alert">The API did not confirm this plan and order as APPROVED. {escalation}</p>}
          {approved && <p role="status" className="rounded-control bg-navActive p-3 font-semibold">
            CFO approval recorded by the server for plan #{selectedId}. Trip assignment and CONFIRMED notification
            follow the authoritative approval transaction.
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
