/**
 * StatePanel — one place for loading / empty / error / unavailable / ready (09 §9, docs/03 §4).
 * Self-contained on purpose: it does not import shared StateViews or ApiError, so this feature
 * can be merged and tested on its own. `unavailable` means the data source cannot supply
 * the data yet, which is different from an error.
 */
import { CloudOff, Inbox, AlertCircle } from "lucide-react";
import type { ReactNode } from "react";
import { mergeLabels, type ShiftAvailabilityLabelOverrides } from "../labels";
import type { PanelState } from "../types";

export interface StatePanelProps<T> {
  state: PanelState<T>;
  /** Renders the panel body once data is ready. */
  children: (data: T) => ReactNode;
  labels?: ShiftAvailabilityLabelOverrides;
  /** Number of skeleton rows while loading. */
  skeletonRows?: number;
  className?: string;
}

function Message({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span aria-hidden="true" className="text-inkMuted">
        {icon}
      </span>
      {children}
    </div>
  );
}

export function StatePanel<T>({ state, children, labels, skeletonRows = 4, className }: StatePanelProps<T>) {
  const text = mergeLabels(labels);
  let body: ReactNode;

  switch (state.status) {
    case "loading":
      body = (
        <div role="status" aria-busy="true" className="flex flex-col gap-2">
          <span className="sr-only">{text.loading}</span>
          {Array.from({ length: skeletonRows }, (_, i) => (
            <div key={i} aria-hidden="true" className="h-12 animate-pulse rounded-control bg-chip" />
          ))}
        </div>
      );
      break;
    case "empty":
      body = (
        <Message icon={<Inbox className="h-8 w-8" />}>
          <p className="text-body text-inkMuted">{state.message ?? text.emptyDefault}</p>
        </Message>
      );
      break;
    case "unavailable":
      body = (
        <div role="status">
          <Message icon={<CloudOff className="h-8 w-8" />}>
            <p className="text-body text-inkMuted">{state.message ?? text.unavailableDefault}</p>
          </Message>
        </div>
      );
      break;
    case "error":
      body = (
        <div role="alert" className="flex flex-col items-start gap-2 rounded-card bg-risk-lateRow p-5">
          <p className="flex items-center gap-2 text-body font-semibold text-risk-predictedLate-fg">
            <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0" />
            {state.error.message || text.errorDefault}
          </p>
          {state.error.correlationId && (
            <p className="text-caption text-inkMuted">
              {text.correlationId}: <span className="select-all font-mono">{state.error.correlationId}</span>
            </p>
          )}
          {state.onRetry && (
            <button
              type="button"
              onClick={state.onRetry}
              className="rounded-control border bg-surface px-4 py-2 text-body font-semibold text-ink hover:bg-rowHover"
            >
              {text.retry}
            </button>
          )}
        </div>
      );
      break;
    case "ready":
      body = children(state.data);
      break;
  }

  return <div className={className}>{body}</div>;
}