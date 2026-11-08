import type { PanelStateProps, VehicleExecutionState, VehicleStatusModel } from "./types";
import { Panel, ProvenanceNote, QualityBadge, TimeValue } from "./presentation";

export interface VehicleStatusListProps extends PanelStateProps {
  model: VehicleStatusModel | null;
}

const VEHICLE_CLASS: Record<VehicleExecutionState, string> = {
  LOADED: "bg-chip text-ink",
  DISPATCHED: "bg-risk-atRisk-bg text-risk-atRisk-fg",
  DELIVERED: "bg-risk-onTrack-bg text-risk-onTrack-fg",
  FAILED: "bg-risk-predictedLate-bg text-risk-predictedLate-fg",
  UNKNOWN: "bg-chip text-inkMuted",
};

export function VehicleStatusList({ model, loadState, errorReference, className }: VehicleStatusListProps) {
  return (
    <Panel
      title="Vehicle execution status"
      loadState={loadState}
      errorReference={errorReference}
      className={className}
      isEmpty={!model || model.vehicles.length === 0}
      emptyMessage="No vehicle execution records available."
    >
      {model && (
        <div className="space-y-4">
          <div className="rounded-control bg-stone p-3">
            <h3 className="text-overline font-semibold uppercase text-inkMuted">Overall order forecast ETA · supplied</h3>
            <TimeValue datum={model.overallForecastEta} timeZone={model.timeZone} />
            <ProvenanceNote value={model.forecastProvenance} />
          </div>
          <ul className="divide-y divide-border" aria-label="Vehicles assigned to this order">
            {model.vehicles.map((vehicle) => {
              const known = vehicle.stateQuality === "verified" || vehicle.stateQuality === "stale";
              return (
                <li key={vehicle.tripReference} className="grid gap-2 py-3 sm:grid-cols-[1fr_auto]">
                  <div className="min-w-0">
                    <p className="break-words font-mono text-body font-semibold text-ink">{vehicle.vehicleCode}</p>
                    <p className="text-caption text-inkMuted">Trip {vehicle.tripReference}</p>
                    {vehicle.latestEventAt && (
                      <div className="mt-1">
                        <span className="text-caption text-inkMuted">Last execution event · </span>
                        <TimeValue datum={vehicle.latestEventAt} timeZone={model.timeZone} />
                      </div>
                    )}
                    {vehicle.forecastEta && (
                      <div className="mt-1">
                        <span className="text-caption text-inkMuted">Vehicle forecast · </span>
                        <TimeValue datum={vehicle.forecastEta} timeZone={model.timeZone} />
                      </div>
                    )}
                  </div>
                  <div className="flex items-start gap-2 sm:justify-end">
                    {known ? (
                      <span
                        className={["rounded-full px-3 py-1 font-mono text-caption", VEHICLE_CLASS[vehicle.state]].join(" ")}
                      >
                        {vehicle.state === "UNKNOWN" ? "Unknown" : vehicle.state.charAt(0) + vehicle.state.slice(1).toLowerCase()}
                      </span>
                    ) : (
                      <span className="text-caption text-inkMuted">Execution status not verified</span>
                    )}
                    <QualityBadge quality={vehicle.stateQuality} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </Panel>
  );
}
