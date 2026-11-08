import type { PanelStateProps, RiskSummaryModel } from "./types";
import { Panel, ProvenanceNote, QualityBadge, RiskBadge, TimeValue } from "./presentation";

export interface RiskSummaryProps extends PanelStateProps {
  model: RiskSummaryModel | null;
}

export function RiskSummary({ model, loadState, errorReference, className }: RiskSummaryProps) {
  const reserve = model?.reserveConsumptionPct;
  const knownReserve =
    reserve != null &&
    reserve.value != null &&
    Number.isFinite(reserve.value) &&
    (reserve.quality === "verified" || reserve.quality === "stale");
  const reserveValue = knownReserve ? reserve.value : null;

  return (
    <Panel
      title="Delivery risk summary"
      loadState={loadState}
      errorReference={errorReference}
      className={className}
      isEmpty={!model}
      emptyMessage="No delivery risk summary available."
    >
      {model && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <RiskBadge status={model.risk.status} quality={model.risk.quality} />
            <span className="font-mono text-caption text-inkMuted">{model.timeZone}</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-control bg-stone p-4">
              <h3 className="mb-2 text-overline font-semibold uppercase text-inkMuted">Committed window</h3>
              <p className="text-caption text-inkMuted">Start</p>
              <TimeValue datum={model.committedWindow.start} timeZone={model.timeZone} />
              <p className="mt-2 text-caption text-inkMuted">End</p>
              <TimeValue datum={model.committedWindow.end} timeZone={model.timeZone} />
              {model.committedWindow.confirmedAt && (
                <div className="mt-2">
                  <p className="text-caption text-inkMuted">Confirmed at</p>
                  <TimeValue datum={model.committedWindow.confirmedAt} timeZone={model.timeZone} />
                </div>
              )}
            </div>
            <div className="rounded-control bg-stone p-4">
              <h3 className="mb-2 text-overline font-semibold uppercase text-inkMuted">Planned ETA</h3>
              <TimeValue datum={model.plannedEta} timeZone={model.timeZone} />
            </div>
            <div className="rounded-control bg-risk-lateRow p-4">
              <h3 className="mb-2 text-overline font-semibold uppercase text-inkMuted">Forecast ETA</h3>
              <TimeValue datum={model.forecastEta} timeZone={model.timeZone} />
            </div>
            <div className="rounded-control bg-stone p-4">
              <h3 className="mb-2 text-overline font-semibold uppercase text-inkMuted">Planning reserve used</h3>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-kpiSm text-ink">
                  {reserveValue === null ? "—" : String(reserveValue) + "%"}
                </span>
                <QualityBadge quality={reserve?.quality ?? "missing"} />
              </div>
              {reserveValue !== null && (
                <div
                  role="img"
                  aria-label={"Planning reserve consumed: " + reserveValue + " percent"}
                  className="mt-3 h-2 overflow-hidden rounded-full bg-chip"
                >
                  <div
                    aria-hidden="true"
                    className="h-full rounded-full bg-pine"
                    style={{ width: Math.max(0, Math.min(reserveValue, 100)) + "%" }}
                  />
                </div>
              )}
              {reserve?.source && <p className="mt-2 text-caption text-inkMuted">Source: {reserve.source}</p>}
            </div>
          </div>
          <ProvenanceNote value={model.forecastProvenance} />
        </div>
      )}
    </Panel>
  );
}
