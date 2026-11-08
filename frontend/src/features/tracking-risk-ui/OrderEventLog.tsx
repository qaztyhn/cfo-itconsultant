import type { OrderEventLogModel, PanelStateProps } from "./types";
import { Panel, TimeValue } from "./presentation";

export interface OrderEventLogProps extends PanelStateProps {
  model: OrderEventLogModel | null;
}

export function OrderEventLog({ model, loadState, errorReference, className }: OrderEventLogProps) {
  return (
    <Panel
      title="Order event log"
      loadState={loadState}
      errorReference={errorReference}
      className={className}
      isEmpty={!model || model.events.length === 0}
      emptyMessage="No order events recorded."
    >
      {model && (
        <div className="overflow-x-auto">
          <p className="mb-2 text-caption text-inkMuted">Times in {model.timeZone} · authorized event summaries only</p>
          <table className="min-w-full text-left text-body">
            <caption className="sr-only">Time, event, actor role and effect</caption>
            <thead className="border-b border-border text-overline uppercase text-inkMuted">
              <tr>
                <th scope="col" className="py-2 pr-4 font-semibold">Time</th>
                <th scope="col" className="py-2 pr-4 font-semibold">Event</th>
                <th scope="col" className="py-2 pr-4 font-semibold">By</th>
                <th scope="col" className="py-2 font-semibold">Effect</th>
              </tr>
            </thead>
            <tbody>
              {model.events.map((event) => (
                <tr key={event.eventId} className="border-b border-border last:border-0">
                  <td className="min-w-36 py-3 pr-4 align-top">
                    <TimeValue datum={event.eventAt} timeZone={model.timeZone} />
                  </td>
                  <td className="py-3 pr-4 align-top">
                    <span className="rounded-full bg-chip px-2 py-1 font-mono text-caption text-ink">
                      {event.eventType}
                    </span>
                  </td>
                  <td className="py-3 pr-4 align-top text-inkMuted">{event.actorRole ?? "Unknown actor"}</td>
                  <td className="min-w-40 py-3 align-top text-ink">{event.effect ?? "No effect summary supplied"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
