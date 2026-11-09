/** Dispatcher-only manual planning. The server alone may certify all five feasibility gates. */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { apiGet, apiPost, isApiError, newIdempotencyKey } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import {
  MANUAL_GATES, MANUAL_GATE_LABELS, allowedDeliveryDate, manualPayload, totalsFor,
  validateManualDraft, type ManualDraft, type ManualOrder, type VehicleDraft,
} from "./manualPlanModel";

const field = "w-full min-h-11 rounded-control border border-line bg-surface px-3 py-2 text-body text-ink";
const action = "min-h-11 rounded-control bg-pine px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50";
type ManualResult = { plan?: { id?: number; status?: string }; order?: { status?: string } };

function newVehicle(key: number, order: ManualOrder): VehicleDraft {
  return {
    key, vehicleId: "", driverId: "", departAt: "", etaAt: "",
    loads: order.lines.map(line => ({ line_no: line.line_no, qty: "" })),
  };
}
function newDraft(order: ManualOrder): ManualDraft {
  return { warehouseId: "", targetDate: "", goodsReadyAt: "", reasonCode: "",
    reasonText: "", vehicles: [newVehicle(1, order)] };
}

function Workspace({ order }: { order: ManualOrder }) {
  const [draft, setDraft] = useState<ManualDraft>(() => newDraft(order));
  const [nextKey, setNextKey] = useState(2);
  const [preview, setPreview] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [requestKey, setRequestKey] = useState<string | null>(null);

  const errors = validateManualDraft(order, draft);
  const allocations = totalsFor(order, draft.vehicles);
  const mutation = useMutation({
    mutationFn: ({ body, key }: { body: ReturnType<typeof manualPayload>; key: string }) =>
      apiPost<ManualResult>("/orders/" + order.id + "/manual-plan", body, key),
  });
  const result = mutation.data;
  const cfoApproved = result?.plan?.status === "manual" && result?.order?.status === "APPROVED";

  function change(patch: Partial<ManualDraft>) {
    setDraft(prev => ({ ...prev, ...patch }));
    setPreview(false);
    setAcknowledged(false);
    setRequestKey(null);
    mutation.reset();
  }
  function changeVehicle(key: number, patch: Partial<VehicleDraft>) {
    change({ vehicles: draft.vehicles.map(v => v.key === key ? { ...v, ...patch } : v) });
  }
  function send() {
    if (errors.length || !acknowledged || mutation.isPending || result) return;
    const key = requestKey ?? newIdempotencyKey();
    setRequestKey(key); // same key for retrying an ambiguous response with the same payload
    mutation.mutate({ key, body: manualPayload(draft) });
  }

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <p className="text-overline text-inkMuted">DISPATCHER · MANUAL PLANNING</p>
        <h1 className="text-h1 font-semibold text-ink">Manual plan · {order.order_no}</h1>
        <p className="text-body text-inkMuted">Build a proposal, review allocations, then request server validation. A local preview is not an approval.</p>
      </header>

      <aside role="note" className="rounded-card border border-line bg-surface p-4 text-body">
        <strong>Resource availability not verified</strong>
        <p>Warehouse stock/ATP, labour shifts, vehicle availability, driver assignment and licence, official working hours, mandatory rest, route and safety must be checked by the server. No locally entered value proves feasibility.</p>
        <p>Current backend manual-plan creation is fail-closed until its trusted five-gate engine adapter is connected.</p>
      </aside>

      <section aria-label="Warehouse and date" className="grid grid-cols-1 gap-4 rounded-card border border-line p-4 md:grid-cols-2">
        <label className="space-y-1 text-body font-medium">Warehouse ID
          <input className={field} aria-label="Warehouse ID" inputMode="numeric" placeholder="Server warehouse ID"
            value={draft.warehouseId} onChange={e => change({ warehouseId: e.target.value })} />
        </label>
        <label className="space-y-1 text-body font-medium">Proposed delivery date
          <input className={field} aria-label="Proposed delivery date" type="date"
            value={draft.targetDate} onChange={e => change({ targetDate: e.target.value })} />
        </label>
        <label className="space-y-1 text-body font-medium">Goods ready (ISO 8601 with zone)
          <input className={field} aria-label="Goods ready" placeholder="2026-11-12T11:20:00+01:00"
            value={draft.goodsReadyAt} onChange={e => change({ goodsReadyAt: e.target.value })} />
        </label>
        <div className="text-body text-inkMuted">
          <p>Customer date request: <strong>{order.date_request.mode}</strong></p>
          <p>{order.date_request.date_from ?? "Earliest feasible"} to {order.date_request.date_to}</p>
          {draft.targetDate && !allowedDeliveryDate(order, draft.targetDate) && (
            <p role="alert">This date is outside the agreed request. A separate, recorded customer negotiation is required; this form cannot change it.</p>
          )}
        </div>
      </section>

      <section aria-label="Vehicle allocations" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-h2 font-semibold">Vehicle allocations</h2>
          <button type="button" className={action} onClick={() => {
            change({ vehicles: [...draft.vehicles, newVehicle(nextKey, order)] });
            setNextKey(n => n + 1);
          }}>Add vehicle</button>
        </div>
        {draft.vehicles.map((vehicle, index) => (
          <fieldset key={vehicle.key} className="rounded-card border border-line p-4">
            <legend className="px-2 text-body font-semibold">Vehicle {index + 1}</legend>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <label className="space-y-1 text-body">Vehicle ID
                <input className={field} inputMode="numeric" aria-label={"Vehicle " + (index + 1) + " ID"}
                  value={vehicle.vehicleId} onChange={e => changeVehicle(vehicle.key, { vehicleId: e.target.value })} />
              </label>
              <label className="space-y-1 text-body">Driver employee ID
                <input className={field} inputMode="numeric" aria-label={"Vehicle " + (index + 1) + " driver ID"}
                  value={vehicle.driverId} onChange={e => changeVehicle(vehicle.key, { driverId: e.target.value })} />
              </label>
              <label className="space-y-1 text-body">Departure (ISO 8601 with zone)
                <input className={field} aria-label={"Vehicle " + (index + 1) + " departure"}
                  placeholder="2026-11-13T05:10:00+01:00" value={vehicle.departAt}
                  onChange={e => changeVehicle(vehicle.key, { departAt: e.target.value })} />
              </label>
              <label className="space-y-1 text-body">ETA (ISO 8601 with zone)
                <input className={field} aria-label={"Vehicle " + (index + 1) + " ETA"}
                  placeholder="2026-11-13T07:00:00+01:00" value={vehicle.etaAt}
                  onChange={e => changeVehicle(vehicle.key, { etaAt: e.target.value })} />
              </label>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {vehicle.loads.map(load => {
                const line = order.lines.find(item => item.line_no === load.line_no);
                return (
                  <label key={load.line_no} className="space-y-1 text-body">
                    {line?.name ?? ("Line " + load.line_no)} · line {load.line_no} · quantity (base units)
                    <input className={field} type="number" min="0" step="any"
                      aria-label={"Vehicle " + (index + 1) + " line " + load.line_no + " quantity"}
                      value={load.qty} onChange={e => changeVehicle(vehicle.key, {
                        loads: vehicle.loads.map(item => item.line_no === load.line_no ? { ...item, qty: e.target.value } : item),
                      })} />
                  </label>
                );
              })}
            </div>
            {draft.vehicles.length > 1 && (
              <button type="button" className="mt-3 min-h-11 rounded-control border px-4"
                onClick={() => change({ vehicles: draft.vehicles.filter(item => item.key !== vehicle.key) })}>
                Remove vehicle {index + 1}
              </button>
            )}
          </fieldset>
        ))}
      </section>

      <section aria-label="Allocation totals" className="rounded-card border border-line p-4">
        <h2 className="mb-3 text-h2 font-semibold">Allocated / Required</h2>
        <div className="space-y-3" aria-live="polite">
          {allocations.map(line => (
            <div key={line.lineNo}>
              <div className="flex flex-wrap justify-between gap-2 text-body">
                <span>{line.name} · line {line.lineNo}</span>
                <strong>{line.allocated} / {line.required} base units</strong>
              </div>
              <progress className="mt-1 h-3 w-full" max={line.required > 0 ? line.required : 1}
                value={Math.max(0, Math.min(line.allocated, line.required))} aria-label={"Line " + line.lineNo + " allocated"} />
              {line.allocated > line.required && <p className="text-body text-risk-predictedLate-fg">Overallocated — reduce quantity.</p>}
            </div>
          ))}
        </div>
      </section>

      <section aria-label="Manual plan justification" className="grid grid-cols-1 gap-4 rounded-card border border-line p-4 md:grid-cols-2">
        <label className="space-y-1 text-body">Manual reason code
          <input className={field} aria-label="Manual reason code" value={draft.reasonCode}
            onChange={e => change({ reasonCode: e.target.value })} placeholder="e.g. special_vehicle" />
        </label>
        <label className="space-y-1 text-body">Auditable explanation
          <textarea className={field} aria-label="Auditable explanation" rows={3} value={draft.reasonText}
            onChange={e => change({ reasonText: e.target.value })} />
        </label>
      </section>
      {errors.length > 0 && (
        <div role="alert" className="rounded-card border border-risk-predictedLate-bg bg-risk-lateRow p-4">
          <h2 className="font-semibold">Complete the draft before preview</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">{errors.map(error => <li key={error}>{error}</li>)}</ul>
        </div>
      )}
      <button type="button" className={action} disabled={errors.length > 0} onClick={() => setPreview(true)}>
        Preview proposal
      </button>
      {preview && errors.length === 0 && (
        <section aria-label="Manual plan preview" className="space-y-4 rounded-card border border-line p-4">
          <h2 className="text-h2 font-semibold">Draft preview · not server-verified</h2>
          <p>Warehouse #{draft.warehouseId} · {draft.targetDate} · {draft.vehicles.length} vehicle(s)</p>
          <ul className="space-y-2">{draft.vehicles.map((vehicle, index) => (
            <li key={vehicle.key}>Vehicle {index + 1}: #{vehicle.vehicleId} · Driver #{vehicle.driverId} · {vehicle.departAt} → {vehicle.etaAt}</li>
          ))}</ul>
          <h3 className="font-semibold">Five feasibility gates</h3>
          <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">{MANUAL_GATES.map(gate => (
            <li key={gate} className="rounded-control border p-3">
              <strong>{MANUAL_GATE_LABELS[gate]}</strong> · Unverified
            </li>
          ))}</ul>
          <p>Conflicts, rejected candidates, labour availability, licence and regulated driving/rest compliance cannot be established from draft input. The backend must return authoritative results.</p>
          <label className="flex items-start gap-3 text-body">
            <input type="checkbox" className="mt-1" checked={acknowledged}
              onChange={e => setAcknowledged(e.target.checked)} />
            I understand this submits a request to the server; local preview does not override any failed or unknown gate.
          </label>
          <button type="button" className={action} disabled={!acknowledged || mutation.isPending || Boolean(result)}
            onClick={send}>{mutation.isPending ? "Submitting…" : "Submit manual plan for server checks"}</button>
        </section>
      )}
      {mutation.isError && (
        <div role="alert" className="space-y-2">
          <ErrorState error={mutation.error} title="Manual plan not accepted" />
          {isApiError(mutation.error) && (
            <p>Server code: <strong>{mutation.error.code}</strong>. Conflicts and failed feasibility gates cannot be bypassed.</p>
          )}
          <button type="button" className={action} onClick={send}
            disabled={!acknowledged || errors.length > 0}>Retry the same request</button>
        </div>
      )}
      {result && (cfoApproved ? (
        <p role="alert">CFO reports manual plan #{result.plan?.id} and order APPROVED. WMS reservation remains unverified; do not treat this as stock held or dispatch-ready.</p>
      ) : (
        <p role="alert">Server response did not confirm approval. Do not dispatch or treat this plan as approved.</p>
      ))}
    </div>
  );
}

export function ManualPlan() {
  const { orderId } = useParams<{ orderId: string }>();
  const id = Number(orderId);
  const valid = typeof orderId === "string" && /^[1-9]\d*$/.test(orderId) && Number.isSafeInteger(id);
  const dispatcher = useAuthStore(s => s.user?.roles.includes("dispatcher") ?? false);
  const query = useQuery({
    queryKey: ["manual-plan", "order", id],
    queryFn: ({ signal }) => apiGet<ManualOrder>("/orders/" + id, undefined, signal),
    enabled: valid && dispatcher,
    retry: false,
  });
  return (
    <section data-screen="ManualPlan" className="space-y-6">
      {!dispatcher ? <p role="alert">Permission denied. Only a Dispatcher may create a manual plan.</p> :
        !valid ? <EmptyState message="Select a valid order to plan." /> :
        query.isPending ? <LoadingState rows={4} /> :
        query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> :
        query.data && !["PLANNED", "NO_FEASIBLE_DATE"].includes(query.data.status) ?
          <EmptyState message="This order is not in a state that permits manual planning." /> :
        query.data ? <Workspace key={query.data.id} order={query.data} /> : <EmptyState message="Order not found." />}
    </section>
  );
}
