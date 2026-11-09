/**
 * 5.2 Plan review & approval — GET /planning-runs/{id}. Thứ tự phương án theo rank API trả về (tối đa 3); không tự xếp lại.
 * Đặc tả: docs/03 mục 5.2 + điều chỉnh mục 7. Mọi màn có trạng thái tải/rỗng/lỗi.
 * Owner: Dev 3 (luồng C) — M4–M5.
 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { fetchIntegrationOverview, summariseFreshness } from "../../api/integration";
import type { PlanningRun } from "../../api/contracts/planning";
import { fetchPlanningRun, planningKeys } from "../../api/planning";
import { PATHS } from "../../app/access";
import { useAuthStore } from "../../app/store";
import { DataFreshness } from "../../components/DataFreshness";

import type { ApproveBlockReason } from "../../components/DecisionBar";

import { HoldCountdown } from "../../components/HoldCountdown";
import { PageHeader } from "../../components/PageHeader";
import { PlanCard } from "../../components/PlanCard";
import { RejectedCandidatesTable } from "../../components/RejectedCandidatesTable";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { gateLabel } from "../../lib/planFormat";
import { useHoldExpired } from "../../lib/useHoldExpired";
import { ApprovalFlow } from "./ApprovalFlow";
import { HoldActions } from "./HoldActions";

const MAX_PLANS = 3;

export function PlanReview() {
  const { runId } = useParams<{ runId: string }>();
  const id = Number(runId);
  const validId = Number.isInteger(id) && id > 0;
  const isDispatcher = useAuthStore((s) => s.user?.roles.includes("dispatcher") ?? false);

  const runQuery = useQuery({
    queryKey: planningKeys.run(id),
    queryFn: ({ signal }) => fetchPlanningRun(id, signal),
    enabled: validId,
  });
  const freshnessQuery = useQuery({
    queryKey: ["integration", "overview"],
    queryFn: ({ signal }) => fetchIntegrationOverview(signal),
    retry: false,
  });

  const run = runQuery.data;
  const freshness = freshnessQuery.data ? summariseFreshness(freshnessQuery.data) : { asOf: null, nextSyncAt: null, stale: true };

  return (
    <section data-screen="PlanReview" className="flex flex-col gap-6">
      <PageHeader
        overline={run ? `RUN ${run.run_no} · ${run.kind.toUpperCase()}` : "PLAN REVIEW"}
        title="Plan review"
        description={run ? `Order #${run.order_id} · plans ranked by score, lower is better.` : undefined}
        breadcrumbs={[{ label: "Plan review", href: PATHS.dispatcherPlanReview }]}
      />

      {!validId && <EmptyState message="Planning run not found." />}
      {validId && runQuery.isPending && <LoadingState rows={3} rowClassName="h-[220px]" />}
      {validId && runQuery.isError && <ErrorState error={runQuery.error} onRetry={() => void runQuery.refetch()} />}
      {run && (
        <RunBody
          key={run.id}
          run={run}
          showDriver={isDispatcher}
          canPlanAgain={isDispatcher}
          freshness={freshness}
          freshnessSettled={!freshnessQuery.isPending}
          onHoldExpire={() => void runQuery.refetch()}
        />
      )}
    </section>
  );
}

interface RunBodyProps {
  run: PlanningRun;
  showDriver: boolean;
  freshness: { asOf: string | null; nextSyncAt: string | null; stale: boolean };
  freshnessSettled: boolean;
  canPlanAgain: boolean;
  onHoldExpire: () => void;
}

function RunBody({ run, showDriver, freshness, freshnessSettled, canPlanAgain, onHoldExpire }: RunBodyProps) {
  const [selectedRank, setSelectedRank] = useState<number | null>(null);
  const [approved, setApproved] = useState(false);
  const expired = useHoldExpired(run.hold_expires_at);

  const plans = run.plans.slice(0, MAX_PLANS);
    const selected = plans.find((p) => p.rank === selectedRank) ?? plans[0] ?? null;

  const blockReason: ApproveBlockReason | null =
    run.kind === "replan_suggestion"
      ? "replan"
      : run.hold_expires_at === null
        ? "no_hold"
        : selected && selected.status !== "proposed"
          ? "not_proposed"
          : null;

  if (run.result === "infeasible" || plans.length === 0) {
    const gate = run.failed_check ? `Failed gate: ${gateLabel(run.failed_check)}.` : "";
    const earliest = run.earliest_feasible_date ? ` Earliest feasible date ${run.earliest_feasible_date}.` : "";
    return (
      <>
        <EmptyState message={`No feasible plan for this order. ${gate}${earliest}`.trim()} />
        <RejectedCandidatesTable candidates={run.rejected_candidates ?? []} />
        {canPlanAgain && (
          <div className="flex flex-wrap items-center gap-3">
            <HoldActions run={run} expired={false} planAgainOnly />
          </div>
        )}
      </>
    );
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        {freshnessSettled && <DataFreshness asOf={freshness.asOf} nextSyncAt={freshness.nextSyncAt} stale={freshness.stale} />}
        {run.hold_expires_at && (
          <HoldCountdown
            expiresAt={run.hold_expires_at}
            extensions={run.hold_extensions}
            onExpire={onHoldExpire}
            actions={({ expired: isExpired }) => <HoldActions run={run} expired={isExpired} />}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {plans.map((plan) => {
          const isSelected = selected?.id === plan.id;
          return (
            <PlanCard
              key={plan.id}
              plan={plan}
              reserveClass={run.reserve_class}
              showDriver={showDriver}
              className={isSelected ? "ring-2 ring-pine" : undefined}
              actions={
                <button
                  type="button"
                  aria-pressed={isSelected}
                  disabled={approved}
                  onClick={() => setSelectedRank(plan.rank)}
                  className="rounded-control border bg-surface px-3 py-1.5 text-body font-semibold text-ink disabled:opacity-50"
                >
                  {isSelected ? "✓ Selected" : `Select plan #${plan.rank}`}
                </button>
              }
            />
          );
        })}
      </div>

      <RejectedCandidatesTable candidates={run.rejected_candidates ?? []} />

      <ApprovalFlow run={run} plan={selected} showDriver={showDriver} expired={expired} blockReason={blockReason} onApproved={() => setApproved(true)} />
    </>
  );
}