import type { NotificationHistoryModel, NotificationStatus, PanelStateProps } from "./types";
import { Panel, TimeValue } from "./presentation";

export interface NotificationHistoryProps extends PanelStateProps {
  model: NotificationHistoryModel | null;
}

const STATUS_CLASSES: Record<NotificationStatus, string> = {
  draft: "bg-chip text-ink",
  queued: "bg-chip text-ink",
  sent: "bg-risk-onTrack-bg text-risk-onTrack-fg",
  failed: "bg-risk-predictedLate-bg text-risk-predictedLate-fg",
  suppressed: "bg-risk-atRisk-bg text-risk-atRisk-fg",
};

export function NotificationHistory({ model, loadState, errorReference, className }: NotificationHistoryProps) {
  return (
    <Panel
      title="Customer notification history"
      loadState={loadState}
      errorReference={errorReference}
      className={className}
      isEmpty={!model || model.notifications.length === 0}
      emptyMessage="No customer notifications recorded."
    >
      {model && (
        <div>
          <p className="mb-3 text-caption text-inkMuted">
            Read-only delivery status. No message bodies, recipient details or GPS information.
          </p>
          <ol className="divide-y divide-border">
            {model.notifications.map((item) => (
              <li key={item.notificationId} className="flex flex-wrap items-start justify-between gap-3 py-3">
                <div className="space-y-1">
                  <p className="font-mono text-body font-semibold text-ink">
                    {item.type} <span className="font-sans font-normal text-inkMuted">· {item.channel}</span>
                  </p>
                  <TimeValue datum={item.timestamp} timeZone={model.timeZone} />
                </div>
                <span className={["rounded-full px-3 py-1 text-caption font-semibold", STATUS_CLASSES[item.status]].join(" ")}>
                  {item.status}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Panel>
  );
}
