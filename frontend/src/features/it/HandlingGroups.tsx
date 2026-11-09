/** A8 read-only view. The handling configuration API has no published response DTO yet. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, ApiError } from "../../api/client";
import { isAdmin } from "../../app/access";
import { useAuthStore } from "../../app/store";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { PageHeader } from "../../components/PageHeader";

// Read projections from docs/05 §2 and docs/06 §12; numeric SQL values can be strings.
type Group = { id: number; code: string; name: string; description?: string | null; prep_unit: string; fixed_hours: string | number; labour_hours_per_unit: string | number; min_crew: number; vehicle_requirement: string[] };
type Flag = { code: string; name: string; multiplier: string | number };
type Rule = { id: number; priority: number; category_like: string; min_weight_kg: string | number | null; max_weight_kg: string | number | null; handling_group_id: number; flags: string[] };

function rows<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object" && "items" in value && Array.isArray(value.items)) return value.items as T[];
  throw new Error("The handling configuration response is not a list.");
}

async function loadConfiguration(signal?: AbortSignal) {
  const [groups, flags, rules] = await Promise.all([
    apiGet<unknown>("/handling-groups", undefined, signal),
    apiGet<unknown>("/special-flags", undefined, signal),
    apiGet<unknown>("/handling-group-rules", undefined, signal),
  ]);
  return { groups: rows<Group>(groups).sort((a, b) => a.code.localeCompare(b.code)), flags: rows<Flag>(flags), rules: rows<Rule>(rules).sort((a, b) => a.priority - b.priority || a.id - b.id) };
}

const number = (value: string | number) => new Intl.NumberFormat("en", { maximumFractionDigits: 3 }).format(Number(value));
const minutes = (hours: string | number) => new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(Number(hours) * 60);
const listing = (values: string[]) => values.length ? values.join(", ") : "None";

export function HandlingGroups() {
  const user = useAuthStore((state) => state.user);
  const [tab, setTab] = useState<"norms" | "rules">("norms");
  const allowed = user !== null && isAdmin(user);
  const query = useQuery({ queryKey: ["handling-configuration"], queryFn: ({ signal }) => loadConfiguration(signal), enabled: allowed, retry: false });

  return <section data-screen="HandlingGroups" className="mx-auto flex max-w-content flex-col gap-6 p-4 sm:p-6 lg:p-8">
    <PageHeader overline="IT · Product configuration" title="Handling groups & norms" description="One norm set for all warehouses." />
    {!allowed ? <ErrorState error={new ApiError("FORBIDDEN", "Access denied.", undefined, undefined, 403)} title="Permission denied" />
      : query.isPending ? <LoadingState rows={6} />
      : query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} title="Handling configuration unavailable" />
      : <>
        <div role="tablist" aria-label="Handling configuration" className="flex flex-wrap gap-2 border-b pb-3">
          <button type="button" role="tab" aria-selected={tab === "norms"} onClick={() => setTab("norms")} className={`rounded-control px-4 py-2 text-body font-semibold ${tab === "norms" ? "bg-pine text-white" : "bg-chip text-ink"}`}>Norms & flags</button>
          <button type="button" role="tab" aria-selected={tab === "rules"} onClick={() => setTab("rules")} className={`rounded-control px-4 py-2 text-body font-semibold ${tab === "rules" ? "bg-pine text-white" : "bg-chip text-ink"}`}>Group rules</button>
        </div>
        {tab === "norms" ? <div role="tabpanel" className="space-y-6">
          <section aria-labelledby="norms-heading" className="space-y-3">
            <div><h2 id="norms-heading" className="text-h2 text-ink">Preparation norms</h2><p className="text-body text-inkMuted">Product groups determine the preparation workload for each order. Warehouse capacity uses that workload; these norms are shared by every warehouse.</p></div>
            {query.data.groups.length === 0 ? <EmptyState message="No handling groups are configured." /> : <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
              {query.data.groups.map((group) => <article key={group.id} className="rounded-card border bg-surface p-5 shadow-card">
                <h3 className="text-h3 text-ink"><span className="font-mono">{group.code}</span> · {group.name}</h3>
                {group.description && <p className="mt-1 text-caption text-inkMuted">{group.description}</p>}
                <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-body">
                  <div><dt className="text-inkMuted">Preparation unit</dt><dd className="font-semibold text-ink">{group.prep_unit}</dd></div>
                  <div><dt className="text-inkMuted">Fixed hours / line</dt><dd className="font-mono text-ink">{number(group.fixed_hours)} h</dd></div>
                  <div><dt className="text-inkMuted">Hours / unit</dt><dd className="font-mono text-ink">{number(group.labour_hours_per_unit)} h</dd></div>
                  <div><dt className="text-inkMuted">Minutes / unit</dt><dd className="font-mono text-ink">≈ {minutes(group.labour_hours_per_unit)} min</dd></div>
                  <div><dt className="text-inkMuted">Minimum crew</dt><dd className="text-ink">{group.min_crew} <span className="text-caption text-inkMuted">(display only)</span></dd></div>
                  <div><dt className="text-inkMuted">Vehicle requirement</dt><dd className="text-ink">{listing(group.vehicle_requirement)}</dd></div>
                </dl>
              </article>)}
            </div>}
          </section>
          <section aria-labelledby="flags-heading" className="rounded-card border bg-surface p-5">
            <h2 id="flags-heading" className="text-h2 text-ink">Special handling flags</h2>
            <p className="mt-1 text-body text-inkMuted">N6 never carries the FRAGILE flag; its handling is already included in the norm.</p>
            {query.data.flags.length === 0 ? <EmptyState message="No special handling flags are configured." /> : <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {query.data.flags.map((flag) => <li key={flag.code} className="rounded-control bg-stone p-3 text-body text-ink"><span className="block font-semibold">{flag.name}</span><span className="font-mono text-caption">{flag.code} · ×{number(flag.multiplier)}</span></li>)}
            </ul>}
          </section>
        </div> : <section role="tabpanel" aria-labelledby="rules-heading" className="rounded-card border bg-surface p-5">
          <h2 id="rules-heading" className="text-h2 text-ink">Group rules</h2>
          <p className="mt-1 text-body text-inkMuted">Category and weight rules suggest a handling group for IT review.</p>
          {query.data.rules.length === 0 ? <EmptyState message="No group rules are configured." /> : <ul className="mt-4 grid gap-3 md:grid-cols-2">
            {query.data.rules.map((rule) => <li key={rule.id} className="rounded-control border p-4 text-body text-ink">
              <p className="font-semibold">{rule.category_like} → {query.data.groups.find((group) => group.id === rule.handling_group_id)?.code ?? "Unknown group"}</p>
              <p className="mt-1 text-caption text-inkMuted">Priority {rule.priority} · Weight {rule.min_weight_kg == null ? "Any" : `${number(rule.min_weight_kg)} kg`} to {rule.max_weight_kg == null ? "Any" : `${number(rule.max_weight_kg)} kg`}</p>
              <p className="mt-1 text-caption text-inkMuted">Flags: {listing(rule.flags)}</p>
            </li>)}
          </ul>}
        </section>}
        <p className="text-caption text-inkMuted">Configuration is read-only while the write API is unavailable.</p>
      </>}
  </section>;
}
