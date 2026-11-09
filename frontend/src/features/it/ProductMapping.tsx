/** IT Product Mapping: explicit server-authorised decisions; no implicit legacy-order re-routing. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { isApiError } from "../../api/client";
import { useAuthStore } from "../../app/store";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import {
  candidateEvidence, confirmMapping, listLocalProducts, listMappingTasks,
  loadMappingTask, rejectMapping, validPositiveDecimal, validateGlobal,
  type Candidate, type ConfirmRequest, type MappingTask, type NewGlobal,
} from "./productMappingApi";

const field = "min-h-11 w-full rounded-control border border-border bg-surface px-3 py-2 text-body text-ink";
const button = "min-h-11 rounded-control border border-border bg-surface px-4 py-2 font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50";
const primary = "min-h-11 rounded-control bg-pine px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50";
const panel = "rounded-card border border-border bg-surface p-4 md:p-5";
type Mode = "suggested" | "other" | "new" | "reject";
const emptyGlobal: NewGlobal = {
  code: "", name: "", category: "", gtin: null, base_unit: "",
  weight_kg: "", volume_m3: "", handling_group_code: "N3",
  base_units_per_prep_unit: "", flags: [],
};
function presentAge(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Not resolved";
}
function MappingEditor({ task, onFinished }: { task: MappingTask; onFinished: (message: string) => void }) {
  const [mode, setMode] = useState<Mode>("suggested");
  const [chosen, setChosen] = useState<number | null>(null);
  const [otherId, setOtherId] = useState("");
  const [units, setUnits] = useState("");
  const [reason, setReason] = useState("");
  const [newGlobal, setNewGlobal] = useState<NewGlobal>(emptyGlobal);
  const [acknowledge, setAcknowledge] = useState(false);
  const [stale, setStale] = useState(false);
  const client = useQueryClient();

  const confirm = useMutation({
    mutationFn: (request: ConfirmRequest) => confirmMapping(task.id, request),
    onSuccess: response => {
      if (response.mapping_status !== "confirmed" || response.task_id !== task.id) {
        setStale(true); return;
      }
      void client.invalidateQueries({ queryKey: ["product-mapping"] });
      onFinished(`SKU ${response.local_sku} confirmed by server for future CFO-eligible orders only.`);
    },
    onError: error => {
      if (isApiError(error) && [404, 409, 412].includes(error.status ?? 0)) {
        setStale(true);
        void client.invalidateQueries({ queryKey: ["product-mapping"] });
      }
    },
  });
  const reject = useMutation({
    mutationFn: (value: string) => rejectMapping(task.id, value),
    onSuccess: response => {
      if (response.mapping_status !== "rejected" || response.task_id !== task.id) {
        setStale(true); return;
      }
      void client.invalidateQueries({ queryKey: ["product-mapping"] });
      onFinished(`SKU ${response.local_sku} rejection recorded by server. Existing order routing remains unchanged.`);
    },
    onError: error => {
      if (isApiError(error) && [404, 409, 412].includes(error.status ?? 0)) {
        setStale(true);
        void client.invalidateQueries({ queryKey: ["product-mapping"] });
      }
    },
  });
  const busy = confirm.isPending || reject.isPending;
  const candidate = task.candidates.find(c => c.global_product_id === chosen);
  const newErrors = mode === "new" ? validateGlobal(newGlobal) : [];
  const targetId = mode === "suggested" ? chosen : Number(otherId);
  const validTarget = Number.isSafeInteger(targetId) && targetId > 0;
  const validConfirm = validPositiveDecimal(units) && acknowledge &&
    (mode === "new" ? newErrors.length === 0 : validTarget);
  function decide() {
    if (busy || stale || task.status === "done") return;
    if (mode === "reject") {
      if (!reason.trim()) return;
      reject.mutate(reason.trim());
    } else if (validConfirm) {
      confirm.mutate(mode === "new"
        ? { units_to_base: units, create_global: {
            ...newGlobal, gtin: newGlobal.gtin?.trim() || null,
            base_units_per_prep_unit: newGlobal.base_units_per_prep_unit?.trim() || null,
          } }
        : { units_to_base: units, global_product_id: targetId });
    }
  }
  function changeMode(next: Mode) {
    if (busy) return;
    setMode(next); setAcknowledge(false); setStale(false);
    confirm.reset(); reject.reset();
  }
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-h2 font-semibold text-ink">SKU {task.local_sku}</h2>
      <span className="rounded-full bg-chip px-3 py-1 font-mono text-caption">{task.mapping_status ?? "pending"} · {task.status}</span>
    </div>
    <dl className="grid grid-cols-1 gap-3 text-body sm:grid-cols-2">
      <div><dt className="text-inkMuted">Market / product</dt><dd>{task.market} · {task.name ?? "Name unavailable"}</dd></div>
      <div><dt className="text-inkMuted">Category / sale unit</dt><dd>{task.category ?? "—"} · {task.sale_unit ?? "—"}</dd></div>
      <div><dt className="text-inkMuted">GTIN</dt><dd className="break-all font-mono">{task.gtin ?? "Unavailable"}</dd></div>
      <div><dt className="text-inkMuted">Suggested handling group</dt><dd>{task.suggested_handling_group ?? "Not established"}</dd></div>
      <div><dt className="text-inkMuted">Legacy affected-order count</dt><dd>{task.blocked_order_count} · not a CFO waiting queue</dd></div>
      <div><dt className="text-inkMuted">Resolved</dt><dd>{presentAge(task.resolved_at)}</dd></div>
    </dl>
    <p className="text-caption text-inkMuted">Suggestions come from GTIN, name, category and size rules—not AI. A suggestion is never automatically confirmed.</p>
    {task.status === "done" ? <p role="status">This task is resolved. Refresh the list to inspect pending work.</p> : <>
      <fieldset className="space-y-3">
        <legend className="font-semibold">IT decision</legend>
        <div className="flex flex-wrap gap-2">
          {(["suggested", "other", "new", "reject"] as const).map(value =>
            <button key={value} type="button" aria-pressed={mode === value} className={button + (mode === value ? " ring-2 ring-pine" : "")}
              disabled={busy} onClick={() => changeMode(value)}>
              {value === "suggested" ? "Approve suggestion" : value === "other" ? "Choose other" :
                value === "new" ? "Create global" : "Reject mapping"}
            </button>)}
        </div>
      </fieldset>
      {mode === "suggested" && <fieldset className="space-y-3" aria-label="Mapping candidates">
        <legend className="font-semibold">Rule-based candidates</legend>
        {task.candidates.length === 0 ? <p>No candidates returned. Choose another global ID or create a global product.</p> :
          task.candidates.map((item: Candidate) => <label key={item.global_product_id}
            className="flex cursor-pointer items-start gap-3 rounded-control border border-border p-3">
            <input type="radio" name={"candidate-" + task.id} className="mt-1"
              checked={chosen === item.global_product_id}
              onChange={() => { setChosen(item.global_product_id); setAcknowledge(false); }} />
            <span><strong>{item.code} · {item.name}</strong><span className="block text-caption text-inkMuted">
              {candidateEvidence(item)} · rule score {item.score} (not verified confidence)</span></span>
          </label>)}
      </fieldset>}
      {mode === "other" && <div className="space-y-2">
        <label className="block space-y-1 text-body">Existing global product ID
          <input inputMode="numeric" className={field} value={otherId}
            onChange={event => { setOtherId(event.target.value); setAcknowledge(false); }}
            aria-label="Existing global product ID" placeholder="Enter server global ID" />
        </label>
        <p className="text-caption text-inkMuted">Global catalogue search is unavailable: the server’s GET /products/global is a stub. Enter a verified ID; the server validates it on confirm.</p>
      </div>}
      {mode === "new" && <div className="grid grid-cols-1 gap-3 sm:grid-cols-2" aria-label="New global product">
        {([
          ["code", "Global code"], ["name", "Global name"], ["category", "Category"],
          ["gtin", "GTIN (optional)"], ["base_unit", "Base unit"],
          ["weight_kg", "Weight (kg)"], ["volume_m3", "Volume (m³)"],
          ["base_units_per_prep_unit", "Base units per prep unit"],
        ] as const).map(([name, label]) => <label key={name} className="space-y-1 text-body">{label}
          <input className={field} aria-label={label} value={newGlobal[name] ?? ""}
            onChange={event => setNewGlobal(v => ({ ...v, [name]: event.target.value }))} />
        </label>)}
        <label className="space-y-1 text-body">Handling group
          <select className={field} aria-label="Handling group" value={newGlobal.handling_group_code}
            onChange={event => setNewGlobal(v => ({ ...v, handling_group_code: event.target.value }))}>
            {["N1", "N2", "N3", "N4", "N5", "N6"].map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-body"><input type="checkbox"
          checked={newGlobal.flags.includes("FRAGILE")} onChange={event => setNewGlobal(v => ({
            ...v, flags: event.target.checked ? [...v.flags, "FRAGILE"] : v.flags.filter(flag => flag !== "FRAGILE"),
          }))} />FRAGILE</label>
        {newErrors.length > 0 && <ul className="col-span-full list-disc pl-5 text-risk-predictedLate-fg">
          {newErrors.map(error => <li key={error}>{error}</li>)}</ul>}
      </div>}
      {mode === "reject" ? <label className="block space-y-1 text-body">Reason for rejection (required)
        <textarea className={field} rows={3} maxLength={1000} aria-label="Reason for rejection"
          value={reason} onChange={event => setReason(event.target.value)} />
      </label> : <label className="block space-y-1 text-body">Units to base (positive; confirm fixed-unit SKU conversion)
        <input className={field} inputMode="decimal" aria-label="Units to base" value={units}
          onChange={event => { setUnits(event.target.value); setAcknowledge(false); }} />
      </label>}
      {mode !== "reject" && <label className="flex items-start gap-2 text-body">
        <input type="checkbox" className="mt-1" checked={acknowledge} onChange={event => setAcknowledge(event.target.checked)} />
        I verified this mapping and the fixed-unit conversion. Any other SKU sharing physical inventory requires independent stock evidence.
      </label>}
      {candidate && mode === "suggested" && <p className="text-caption">Selected: {candidate.code}. Server confirmation is required.</p>}
      <button type="button" className={primary} disabled={busy || stale ||
        (mode === "reject" ? !reason.trim() : !validConfirm)} onClick={decide}>
        {busy ? "Saving decision…" : mode === "reject" ? "Reject with reason" : "Confirm mapping on server"}
      </button>
      {stale && <div role="alert" className="space-y-2 rounded-card border border-risk-predictedLate-bg p-4">
        <p>This task may have changed concurrently or is no longer available. No decision is assumed saved.</p>
        <button type="button" className={button} onClick={() => {
          setStale(false); setAcknowledge(false); confirm.reset(); reject.reset();
          void client.invalidateQueries({ queryKey: ["product-mapping"] });
        }}>Reload server data</button>
      </div>}
      {confirm.isError && <ErrorState title="Confirmation was not accepted" error={confirm.error} />}
      {reject.isError && <ErrorState title="Rejection was not accepted" error={reject.error} />}
    </>}
    <p className="text-caption text-inkMuted">Every accepted IT confirmation or rejection is recorded by the server. Earlier legacy routing decisions remain immutable.</p>
  </div>;
}

function MappingWorkspace() {
  const client = useQueryClient();
  const [taskStatus, setTaskStatus] = useState("open");
  const [taskSearch, setTaskSearch] = useState("");
  const [market, setMarket] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [success, setSuccess] = useState("");
  const [localSearch, setLocalSearch] = useState("");
  const [localStatus, setLocalStatus] = useState("pending");
  const [localPage, setLocalPage] = useState(1);
  const tasks = useQuery({
    queryKey: ["product-mapping", "tasks", taskStatus, taskSearch, market, page],
    queryFn: ({ signal }) => listMappingTasks({ status: taskStatus, q: taskSearch, market, page }, signal),
    retry: false, staleTime: 0,
  });
  const detail = useQuery({
    queryKey: ["product-mapping", "task", selected],
    queryFn: ({ signal }) => loadMappingTask(selected as number, signal),
    enabled: selected !== null, retry: false, staleTime: 0,
  });
  const locals = useQuery({
    queryKey: ["product-mapping", "local", localSearch, localStatus, market, localPage],
    queryFn: ({ signal }) => listLocalProducts({
      q: localSearch, mapping_status: localStatus, market, page: localPage,
    }, signal),
    retry: false,
  });
  useEffect(() => { if (selected !== null && !tasks.isFetching && tasks.data &&
    !tasks.data.items.some(t => t.id === selected) && taskStatus === "open") setSelected(null);
  }, [selected, taskStatus, tasks.isFetching, tasks.data]);
  function finish(message: string) {
    setSuccess(message);
    setSelected(null);
    void client.invalidateQueries({ queryKey: ["product-mapping"] });
  }
  return <div className="space-y-6">
    <header className="space-y-2">
      <p className="text-overline font-semibold text-pine">ADMIN · PRODUCT MAPPING</p>
      <h1 className="text-h1 font-semibold">Product mapping</h1>
      <p className="text-body text-inkMuted">Review ERP SKUs and explicitly confirm their global mapping. Suggestions are rule-based, not AI approvals.</p>
    </header>
    <aside className={panel} role="note">
      <p className="text-body">One unconfirmed SKU makes the <strong>whole order ineligible</strong> for CFO planning.
        Such orders continue through the existing process. Confirming a SKU later does not reroute an immutable legacy order.</p>
      <p className="mt-2 text-caption text-inkMuted">Legacy affected/blocked counts are diagnostic only—not a backlog of orders waiting for Dispatcher.</p>
    </aside>
    {success && <div role="status" className="flex flex-wrap items-center justify-between gap-2 rounded-card border border-pine p-4">
      <span>{success}</span><button type="button" className={button} onClick={() => setSuccess("")}>Dismiss</button>
    </div>}
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(280px,2fr)_minmax(320px,3fr)]">
      <section className={panel + " space-y-4"} aria-label="Mapping task queue">
        <div className="flex items-center justify-between gap-2"><h2 className="text-h2 font-semibold">Mapping tasks</h2>
          <button className={button} type="button" onClick={() => void client.invalidateQueries({ queryKey: ["product-mapping"] })}>Refresh</button></div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-caption">Search tasks
            <input aria-label="Search tasks" className={field} value={taskSearch} onChange={event => {
              setTaskSearch(event.target.value); setPage(1); setSelected(null);
            }} placeholder="Local SKU, name…" /></label>
          <label className="space-y-1 text-caption">Status
            <select className={field} aria-label="Task status" value={taskStatus} onChange={event => {
              setTaskStatus(event.target.value); setPage(1); setSelected(null);
            }}><option value="open">Open</option><option value="in_progress">In progress</option><option value="done">Done</option></select>
          </label>
          <label className="space-y-1 text-caption sm:col-span-2">Market (optional)
            <input className={field} aria-label="Market filter" maxLength={2} value={market} onChange={event => {
              setMarket(event.target.value.toUpperCase()); setPage(1); setLocalPage(1); setSelected(null);
            }} placeholder="e.g. SE" /></label>
        </div>
        {tasks.isPending ? <LoadingState rows={4} /> : tasks.isError ?
          <ErrorState error={tasks.error} onRetry={() => void tasks.refetch()} /> :
          tasks.data?.items.length === 0 ? <EmptyState message="No mapping tasks match the selected filters."
            action={{ label: "Show open tasks", onClick: () => { setTaskStatus("open"); setTaskSearch(""); setPage(1); } }} /> :
          <div className="space-y-2">
            <p className="text-caption text-inkMuted">{tasks.data?.total ?? 0} tasks match these filters; sorted by server task order.</p>
            {tasks.data?.items.map(task => <button key={task.id} type="button"
              aria-pressed={selected === task.id} onClick={() => { setSelected(task.id); setSuccess(""); }}
              className={"w-full rounded-control border p-3 text-left hover:bg-rowHover " +
                (selected === task.id ? "border-pine bg-chip" : "border-border")}>
              <span className="block break-all font-mono text-body font-semibold">{task.local_sku} · {task.market}</span>
              <span className="block text-caption text-inkMuted">{task.name ?? "Unlabelled ERP SKU"} · {task.status}</span>
              <span className="block text-caption">Candidates: {task.candidates.length} · legacy affected: {task.blocked_order_count}</span>
            </button>)}
          </div>}
        <div className="flex items-center justify-between gap-2 text-body">
          <button type="button" className={button} disabled={page <= 1} onClick={() => { setPage(n => n - 1); setSelected(null); }}>Previous</button>
          <span>Page {page}</span>
          <button type="button" className={button}
            disabled={!tasks.data || page * tasks.data.page_size >= tasks.data.total}
            onClick={() => { setPage(n => n + 1); setSelected(null); }}>Next</button>
        </div>
      </section>
      <section className={panel} aria-label="Mapping task details">
        {selected === null ? <EmptyState message="Select a SKU mapping task to review its evidence." /> :
          detail.isPending ? <LoadingState rows={4} /> :
          detail.isError ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> :
          detail.data ? <MappingEditor key={detail.data.id + ":" + detail.data.status}
            task={detail.data} onFinished={finish} /> :
            <EmptyState message="Task no longer available. Refresh the queue." />}
      </section>
    </div>
    <section className={panel + " space-y-4"} aria-label="Local product catalogue">
      <div><h2 className="text-h2 font-semibold">Local products</h2>
        <p className="text-caption text-inkMuted">Server-scoped search and mapping-status filter; this table does not modify mappings.</p></div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="flex-1 space-y-1 text-caption">Search local products
          <input className={field} aria-label="Search local products" value={localSearch} onChange={event => {
            setLocalSearch(event.target.value); setLocalPage(1);
          }} /></label>
        <label className="space-y-1 text-caption">Mapping status
          <select className={field} aria-label="Local mapping status" value={localStatus}
            onChange={event => { setLocalStatus(event.target.value); setLocalPage(1); }}>
            <option value="">All</option><option value="pending">Pending</option>
            <option value="confirmed">Confirmed</option><option value="rejected">Rejected</option></select>
        </label>
      </div>
      {locals.isPending ? <LoadingState rows={2} /> : locals.isError ?
        <ErrorState error={locals.error} onRetry={() => void locals.refetch()} /> :
        locals.data?.items.length === 0 ? <EmptyState message="No local products match the filters." /> :
        <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-body">
          <thead><tr className="border-b border-border"><th className="p-3">SKU / market</th>
            <th className="p-3">Name</th><th className="p-3">Sale unit</th>
            <th className="p-3">Global ID</th><th className="p-3">Status</th></tr></thead>
          <tbody>{locals.data?.items.map(product => <tr className="border-b border-border"
            key={product.market + ":" + product.local_sku}>
            <td className="p-3 font-mono">{product.local_sku} · {product.market}</td>
            <td className="p-3">{product.name}</td><td className="p-3">{product.sale_unit}</td>
            <td className="p-3">{product.global_product_id ?? "—"}</td>
            <td className="p-3">{product.mapping_status}</td>
          </tr>)}</tbody>
        </table></div>}
      <div className="flex justify-between gap-2 text-body">
        <button className={button} type="button" disabled={localPage <= 1} onClick={() => setLocalPage(n => n - 1)}>Previous</button>
        <span>Page {localPage}</span>
        <button className={button} type="button"
          disabled={!locals.data || localPage * locals.data.page_size >= locals.data.total}
          onClick={() => setLocalPage(n => n + 1)}>Next</button>
      </div>
    </section>
  </div>;
}

export function ProductMapping() {
  const admin = useAuthStore(store => store.user?.roles.includes("admin") ?? false);
  return <section data-screen="ProductMapping" className="space-y-6">
    {!admin ? <p role="alert" className={panel}>You do not have permission to manage product mappings. IT administrator access is required.</p>
      : <MappingWorkspace />}
  </section>;
}
