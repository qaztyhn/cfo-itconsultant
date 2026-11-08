import type { MilestoneKind, MilestoneTimelineModel, PanelStateProps } from "./types";
import { Panel, TimeValue } from "./presentation";

export interface MilestoneTimelineProps extends PanelStateProps {
  model: MilestoneTimelineModel | null;
}

const MILESTONES: ReadonlyArray<{ kind: MilestoneKind; label: string }> = [
  { kind: "APPROVED", label: "Approved" },
  { kind: "START_PREP", label: "Start prep" },
  { kind: "GOODS_READY", label: "Goods ready" },
  { kind: "LOADED", label: "Loaded" },
  { kind: "DISPATCHED", label: "Dispatched" },
  { kind: "DELIVERED", label: "Delivered" },
];

export function MilestoneTimeline({ model, loadState, errorReference, className }: MilestoneTimelineProps) {
  return (
    <Panel
      title="Milestones · planned vs actual vs forecast"
      loadState={loadState}
      errorReference={errorReference}
      className={className}
      isEmpty={!model || model.milestones.length === 0}
      emptyMessage="No execution milestones available."
    >
      {model && (
        <div>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-caption text-inkMuted">
            <span>Times in {model.timeZone}</span>
            {model.asOf && (
              <span>Data as of <TimeValue datum={model.asOf} timeZone={model.timeZone} /></span>
            )}
          </div>
          <ol className="space-y-2">
            {MILESTONES.map(({ kind, label }, index) => {
              const milestone = model.milestones.find((m) => m.kind === kind);
              return (
                <li
                  key={kind}
                  data-milestone={kind}
                  className="grid gap-3 rounded-control border border-border bg-surface p-3 md:grid-cols-[10rem_1fr]"
                >
                  <div className="flex items-start gap-3">
                    <span
                      aria-hidden="true"
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-chip font-mono text-caption text-ink"
                    >
                      {index + 1}
                    </span>
                    <h3 className="pt-1 text-body font-semibold text-ink">{label}</h3>
                  </div>
                  {!milestone ? (
                    <p className="text-body text-inkMuted">Milestone data missing — no recorded or forecast time.</p>
                  ) : (
                    <dl className="grid gap-2 sm:grid-cols-3">
                      {([
                        ["Planned", milestone.planned],
                        ["Actual", milestone.actual],
                        ["Forecast", milestone.forecast],
                      ] as const).map(([name, time]) => (
                        <div key={name}>
                          <dt className="text-overline uppercase text-inkMuted">{name}</dt>
                          <dd className="mt-1">
                            <TimeValue datum={time} timeZone={model.timeZone} />
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </Panel>
  );
}
