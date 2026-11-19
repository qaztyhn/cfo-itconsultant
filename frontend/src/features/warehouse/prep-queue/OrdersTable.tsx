/** Preparation orders, with actions granted by backend next_action (Round 3 E3). */
import { StatusChip } from "../../../components/StatusChip";
import { ACTION_NAMES, canPerform, type PrepEventType } from "./executionActions";
import { formatLinesWeight, formatLoadingTime, formatMinutes, formatWindow } from "./format";
import type { LoadingEntry, PrepQueueOrder } from "./types";

export interface OrdersTableProps {
  orders: PrepQueueOrder[];
  /** IANA time zone of the warehouse, used only to read ISO times. */
  timeZone: string;
  /** Queue date `YYYY-MM-DD`; a loading time on another day shows its weekday. */
  queueDate: string;
  className?: string;
  onAction?: (order: PrepQueueOrder, type: PrepEventType, tripId?: number, vehicleCode?: string) => void;
  actionPending?: boolean;
  canWrite?: boolean;
}

const COLUMNS = ["Order", "Handling mix", "Work", "Prep window", "Loading", "Status"] as const;

const CELL =
  "block px-3 py-1 lg:table-cell lg:py-3 lg:align-top before:block before:font-mono before:text-overline before:uppercase before:text-inkMuted before:content-[attr(data-label)] lg:before:hidden";

function loadingLabel(entry: LoadingEntry, timeZone: string, queueDate: string): string {
  const time = formatLoadingTime(entry.at, timeZone, queueDate);
  return entry.after_cutoff ? `${time} after cut-off · ${entry.vehicle_code}` : `${time} · ${entry.vehicle_code}`;
}

export function OrdersTable({ orders, timeZone, queueDate, className, onAction, actionPending, canWrite = false }: OrdersTableProps) {
  return (
    <div aria-live="polite" className={["rounded-card border bg-surface shadow-card", className].filter(Boolean).join(" ")}>
      <table className="block w-full text-body text-ink lg:table">
        <caption className="sr-only">Orders to prepare</caption>
        <thead className="sr-only lg:not-sr-only lg:table-header-group">
          <tr className="lg:table-row">
            {COLUMNS.map((name) => (
              <th key={name} scope="col" className="px-3 py-2 text-left font-mono text-overline uppercase text-inkMuted">
                {name}
              </th>
            ))}
            {onAction && <th scope="col" className="px-3 py-2 text-left font-mono text-overline uppercase text-inkMuted">Actions</th>}
          </tr>
        </thead>
        <tbody className="block lg:table-row-group">
          {orders.map((order) => (
            <tr key={order.order_id} className="block border-t py-3 lg:table-row lg:py-0 hover:bg-rowHover">
              <td data-label="Order" className={CELL}>
                <span className="block font-mono font-semibold">{order.order_no}</span>
                <span className="block text-caption text-inkMuted">{formatLinesWeight(order.lines, order.weight_kg)}</span>
              </td>

              <td data-label="Handling mix" className={CELL}>
                <ul className="flex flex-wrap gap-1">
                  {order.handling_mix.map((item) => (
                    <li key={item.code} className="rounded-full bg-chip px-2 py-0.5 text-caption text-ink">
                      {item.code} · {item.name}
                    </li>
                  ))}
                </ul>
              </td>

              <td data-label="Work" className={`${CELL} font-mono`}>
                {formatMinutes(order.work_min)}
              </td>

              <td data-label="Prep window" className={`${CELL} font-mono`}>
                {formatWindow(order.prep_window.start, order.prep_window.end, timeZone)}
              </td>

              <td data-label="Loading" className={CELL}>
                <ul className="flex flex-col gap-1">
                  {order.loading.map((entry) => (
                    <li key={entry.trip_id} className="flex flex-wrap items-center gap-x-2">
                      <span className={entry.after_cutoff ? "font-mono text-risk-atRisk-fg" : "font-mono"}>{loadingLabel(entry, timeZone, queueDate)}</span>
                      {entry.loaded && <span className="rounded-full bg-risk-onTrack-bg px-2 py-0.5 font-mono text-overline uppercase text-risk-onTrack-fg">Loaded</span>}
                    </li>
                  ))}
                </ul>
              </td>

              <td data-label="Status" className={CELL}>
                <span className="flex flex-wrap items-center gap-1">
                  <StatusChip status={order.status} />
                </span>
              </td>
              {onAction && (
                <td data-label="Actions" className={CELL}>
                  <div className="flex flex-col gap-2">
                    {(["START_PREP", "GOODS_READY"] as PrepEventType[])
                      .filter((type) => canPerform(order, type)).map((type) => (
                        <button type="button" key={type}
                          disabled={!canWrite || actionPending}
                          onClick={() => onAction(order, type)}
                          className="min-h-[48px] rounded-control bg-pine px-3 py-2 font-semibold text-white disabled:opacity-50">
                          {ACTION_NAMES[type]}
                        </button>
                      ))}
                    {order.loading.filter((entry) => canPerform(order, "LOADED", entry.trip_id)).map((entry) => (
                      <button type="button" key={entry.trip_id}
                        disabled={!canWrite || actionPending}
                        onClick={() => onAction(order, "LOADED", entry.trip_id, entry.vehicle_code)}
                        className="min-h-[48px] rounded-control border border-border bg-surface px-3 py-2 font-semibold text-ink disabled:opacity-50">
                        Mark loaded · {entry.vehicle_code}
                      </button>
                    ))}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}