import type { PanelStateProps, RiskExplanationModel } from "./types";
import { Panel, ProvenanceNote, RiskBadge } from "./presentation";

export interface RiskExplanationProps extends PanelStateProps {
  model: RiskExplanationModel | null;
}

export function RiskExplanation({ model, loadState, errorReference, className }: RiskExplanationProps) {
  return (
    <Panel
      title="Risk explanation"
      loadState={loadState}
      errorReference={errorReference}
      className={className}
      isEmpty={!model}
      emptyMessage="No risk explanation available."
    >
      {model && (
        <div className="space-y-3">
          <RiskBadge status={model.risk.status} quality={model.risk.quality} />
          {model.explanation ? (
            <p className="whitespace-pre-wrap break-words text-body text-ink">{model.explanation}</p>
          ) : (
            <p className="text-body text-inkMuted">
              No rule-based explanation supplied. Risk cannot be inferred from the displayed ETA.
            </p>
          )}
          {model.reasonCodes.length > 0 && (
            <div>
              <h3 className="mb-1 text-caption font-semibold text-inkMuted">Upstream reason codes</h3>
              <ul className="flex flex-wrap gap-2" aria-label="Risk reason codes">
                {model.reasonCodes.map((code, i) => (
                  <li key={code + i} className="rounded-full bg-chip px-2 py-1 font-mono text-caption text-ink">
                    {code}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <ProvenanceNote value={model.provenance} />
        </div>
      )}
    </Panel>
  );
}
