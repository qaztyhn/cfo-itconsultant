/**
 * PlanCard — Phương án: rank + score lớn, km, Fill %, số xe (VehicleList), 5 check, Goods ready/Depart/ETA/Site closes/Slack,
 * Planning reserve Safe/Tight; KHÔNG tiền (03 #1, #37). Trạng thái luôn có chữ/ký hiệu, không chỉ màu.
 * Owner: Dev 3 (luồng C).
 */
import type { ReactNode } from "react";
import { GATE_KEYS, type Plan } from "../api/contracts/planning";
import {
  formatFill,
  formatKm,
  formatReserve,
  formatScore,
  formatTime,
  gateLabel,
} from "../lib/planFormat";
import { CheckChip } from "./CheckChip";
import { VehicleList } from "./VehicleList";

export interface PlanCardProps {
  plan: Plan;
  /** reserve_class của cả planning run. */
  reserveClass?: "safe" | "tight" | null;
  showDriver?: boolean;
  /** Vùng hành động (nút chọn phương án…) do nơi gọi truyền vào. */
  actions?: ReactNode;
  className?: string;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-overline uppercase text-inkMuted">{label}</dt>
      <dd className="font-mono text-body text-ink">{value}</dd>
    </div>
  );
}

export function PlanCard({ plan, reserveClass, showDriver = false, actions, className }: PlanCardProps) {
  const titleId = `plan-${plan.id}-title`;
  const tight = reserveClass === "tight";

  return (
    <article
      aria-labelledby={titleId}
      data-component="PlanCard"
      data-rank={plan.rank}
      className={["flex flex-col gap-4 rounded-card border bg-surface p-5 shadow-card", className].filter(Boolean).join(" ")}
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 id={titleId} className="text-h3 text-ink">
            Plan #{plan.rank}
            {plan.rank === 1 && <span className="ml-2 rounded-full bg-chip px-2 py-0.5 font-mono text-overline">RECOMMENDED</span>}
          </h3>
          {plan.warehouse && <p className="text-body text-inkMuted">{plan.warehouse.name}</p>}
        </div>
        {plan.score !== undefined && (
          <div className="text-right">
            <p className="font-mono text-kpiSm text-ink" aria-label={`Score ${formatScore(plan.score)}`}>
              {formatScore(plan.score)}
            </p>
            <p className="text-caption text-inkMuted">Score · lower is better</p>
          </div>
        )}
      </header>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Fact label="Distance" value={formatKm(plan.distance_km)} />
        <Fact label="Fill" value={formatFill(plan.capacity_fill)} />
        <Fact label="Vehicles" value={String(plan.vehicle_count)} />
        <Fact label="ETA" value={formatTime(plan.eta_at)} />
        {plan.goods_ready_at && <Fact label="Goods ready" value={formatTime(plan.goods_ready_at)} />}
        {plan.depart_at && <Fact label="Depart" value={formatTime(plan.depart_at)} />}
      </dl>

      <VehicleList vehicles={plan.vehicles} showDriver={showDriver} />

      <div className="flex flex-wrap gap-2" role="group" aria-label="Feasibility gates">
        {GATE_KEYS.map((key) => {
          const gate = plan.checks?.[key];
          return <CheckChip key={key} name={gateLabel(key)} passed={gate?.passed === true} code={gate?.code ?? "EVIDENCE_MISSING"} />;
        })}
      </div>

      {plan.planning_reserve_min !== undefined && (
        <p className="flex flex-wrap items-center gap-2 text-body text-ink">
          <span>Planning reserve {formatReserve(plan.planning_reserve_min)}</span>
          {reserveClass && (
            <span
              className={`rounded-full px-2 py-0.5 font-mono text-overline ${
                tight ? "bg-risk-atRisk-bg text-risk-atRisk-fg" : "bg-risk-onTrack-bg text-risk-onTrack-fg"
              }`}
            >
              <span aria-hidden="true">{tight ? "! " : "✓ "}</span>
              {tight ? "TIGHT" : "SAFE"}
            </span>
          )}
        </p>
      )}

      {plan.explanation && <p className="text-caption text-inkMuted">{plan.explanation}</p>}
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </article>
  );
}
