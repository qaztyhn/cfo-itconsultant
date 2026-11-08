/**
 * RejectedCandidatesTable — Bảng 'Why other candidates were not ranked'.
 * Owner: Dev 3 (luồng C).
 */
import type { RejectedCandidate } from "../api/contracts/planning";
import { gateLabel } from "../lib/planFormat";
import { EmptyState } from "./StateViews";

export interface RejectedCandidatesTableProps {
  candidates: RejectedCandidate[];
  className?: string;
}

export function RejectedCandidatesTable({ candidates, className }: RejectedCandidatesTableProps) {
  if (candidates.length === 0) {
    return <EmptyState className={className} message="No other candidates were rejected for this run." />;
  }
  return (
    <div className={["overflow-x-auto rounded-card border bg-surface shadow-card", className].filter(Boolean).join(" ")} data-component="RejectedCandidatesTable">
      <table className="w-full text-left text-body">
        <caption className="px-4 pt-3 text-left text-h3 text-ink">Why other candidates were not ranked</caption>
        <thead className="text-overline uppercase text-inkMuted">
          <tr>
            <th scope="col" className="px-4 py-2">Warehouse</th>
            <th scope="col" className="px-4 py-2">Vehicle</th>
            <th scope="col" className="px-4 py-2">Failed gate</th>
            <th scope="col" className="px-4 py-2">Reason</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c, index) => (
                        <tr key={`${c.warehouse?.id ?? "w"}-${c.vehicle?.code ?? "v"}-${index}`} className="border-t hover:bg-rowHover">
              <td className="px-4 py-2">{c.warehouse?.name ?? "—"}</td>
              <td className="px-4 py-2 font-mono">{c.vehicle?.code ?? "—"}</td>
              <td className="px-4 py-2">
                <span className="rounded-full bg-risk-predictedLate-bg px-2 py-0.5 font-mono text-caption text-risk-predictedLate-fg">
                  <span aria-hidden="true">✕ </span>
                  {c.failed_check ? gateLabel(c.failed_check) : "—"}
                </span>
              </td>
              <td className="px-4 py-2">
                <span>{c.detail?.message ?? c.code ?? "—"}</span>
                {c.code && <span className="ml-2 font-mono text-caption text-inkMuted">{c.code}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}