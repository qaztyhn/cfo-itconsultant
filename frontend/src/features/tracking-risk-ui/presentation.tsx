/** Reusable formatting, evidence labels and panel states; never calculates ETA/risk. */
import type { ReactNode } from "react";
import type { EvidenceQuality, PanelStateProps, Provenance, RiskStatus, TimeDatum } from "./types";
import { timeText } from "./format";

const RISK_LABELS: Record<RiskStatus, string> = {
  ON_TRACK: "On track",
  AT_RISK: "At risk",
  PREDICTED_LATE: "Predicted late",
  OVERDUE: "Overdue",
};

const RISK_CLASS: Record<RiskStatus, string> = {
  ON_TRACK: "bg-risk-onTrack-bg text-risk-onTrack-fg",
  AT_RISK: "bg-risk-atRisk-bg text-risk-atRisk-fg",
  PREDICTED_LATE: "bg-risk-predictedLate-bg text-risk-predictedLate-fg",
  OVERDUE: "bg-risk-overdue-bg text-risk-overdue-fg",
};

const QUALITY_CLASS: Record<EvidenceQuality, string> = {
  verified: "bg-risk-onTrack-bg text-risk-onTrack-fg",
  stale: "bg-risk-atRisk-bg text-risk-atRisk-fg",
  missing: "bg-chip text-ink",
  unknown: "bg-chip text-ink",
  unavailable: "bg-chip text-inkMuted",
};

const QUALITY_LABEL: Record<EvidenceQuality, string> = {
  verified: "Verified",
  stale: "Stale",
  missing: "Missing",
  unknown: "Unknown",
  unavailable: "Unavailable",
};

/** Explicit evidence quality; color never carries meaning alone. */
export function QualityBadge({ quality }: { quality: EvidenceQuality }) {
  return (
    <span
      data-evidence={quality}
      className={["inline-flex rounded-full px-2 py-0.5 text-overline font-mono", QUALITY_CLASS[quality]].join(" ")}
    >
      {QUALITY_LABEL[quality]}
    </span>
  );
}

export function RiskBadge({ status, quality }: { status: RiskStatus | null; quality: EvidenceQuality }) {
  if (!status || quality === "missing" || quality === "unknown" || quality === "unavailable") {
    return <QualityBadge quality={quality === "verified" ? "unknown" : quality} />;
  }
  return (
    <span
      role="status"
      aria-label={"Risk: " + RISK_LABELS[status] + (quality === "stale" ? " (stale)" : "")}
      className={["inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-caption font-semibold", RISK_CLASS[status]].join(" ")}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
      {RISK_LABELS[status]}
      {quality === "stale" ? " · Stale" : ""}
    </span>
  );
}

export function TimeValue({
  datum,
  timeZone,
  label,
}: {
  datum?: TimeDatum | null;
  timeZone: string;
  label?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-body">
      <span className="font-mono text-ink">{timeText(datum, timeZone)}</span>
      {datum && <QualityBadge quality={datum.quality} />}
      {label && <span className="sr-only">{label}</span>}
      {datum?.source && <span className="text-caption text-inkMuted">Source: {datum.source}</span>}
    </div>
  );
}

export function ProvenanceNote({ value }: { value?: Provenance | null }) {
  if (!value) return null;
  const route =
    value.routeQuality === "verified_ors"
      ? "Verified ORS route"
      : value.routeQuality === "estimated_fallback"
        ? "Estimated fallback route — not verified ORS"
        : value.routeQuality === "unknown"
          ? "Route source unknown"
          : null;
  if (!route && !value.source && !value.asOf) return null;
  return (
    <p className="text-caption text-inkMuted" data-route-quality={value.routeQuality ?? "unspecified"}>
      {[route, value.source ? "Source: " + value.source : null, value.asOf ? "As of: " + value.asOf : null]
        .filter(Boolean)
        .join(" · ")}
    </p>
  );
}

export interface PanelProps extends PanelStateProps {
  title: string;
  children: ReactNode;
  isEmpty?: boolean;
  emptyMessage?: string;
}

/** A fixed presentation state with no network side effects or unauthorized raw error body. */
export function Panel({
  title,
  children,
  loadState = "ready",
  errorReference,
  className,
  isEmpty = false,
  emptyMessage = "No records available.",
}: PanelProps) {
  return (
    <section
      aria-label={title}
      className={["rounded-card border border-border bg-surface p-5 shadow-card", className].filter(Boolean).join(" ")}
    >
      <h2 className="mb-4 text-h3 text-ink">{title}</h2>
      {loadState === "loading" ? (
        <div role="status" aria-busy="true" className="space-y-3">
          <span className="sr-only">Loading {title}</span>
          <div aria-hidden="true" className="h-10 animate-pulse rounded-control bg-chip" />
          <div aria-hidden="true" className="h-10 animate-pulse rounded-control bg-chip" />
        </div>
      ) : loadState === "error" ? (
        <div role="alert" className="rounded-control bg-risk-lateRow p-3 text-body text-risk-predictedLate-fg">
          Unable to load {title.toLowerCase()}.
          {errorReference && (
            <p className="mt-1 text-caption">Reference: <code className="font-mono">{errorReference}</code></p>
          )}
        </div>
      ) : isEmpty ? (
        <p role="status" className="rounded-control bg-stone p-4 text-body text-inkMuted">{emptyMessage}</p>
      ) : (
        children
      )}
    </section>
  );
}
