/**
 * Cột "Open" của một đơn trong Order Queue.
 * PLANNED → vào Plan Review của run mới nhất; SUBMITTED → chạy planning rồi vào run vừa tạo.
 * Các trạng thái khác giữ link tới màn danh sách như cũ. Chỉ điều hướng sau khi server trả id thật.
 */
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { isApiError } from "../../../api/client";
import { PATHS } from "../../../app/access";
import type { QueueOrder } from "./model";
import { findLatestRunId, startPlanning } from "./planningActions";
import { destinationFor } from "./rowView";

const button = "inline-flex rounded-control border border-border px-3 py-1.5 text-sm font-semibold text-pine hover:bg-rowHover disabled:opacity-50";

function describeError(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 403 || error.code === "FORBIDDEN") return "You are not allowed to do this for this order.";
    return `${error.message} (${error.code})`;
  }
  if (error instanceof Error && error.message.startsWith("The newest")) return error.message;
  if (error instanceof Error && error.message.startsWith("Invalid planning history")) return error.message;
  return "Could not reach the server. Check the order status before retrying.";
}

export function OrderAction({ order }: { order: QueueOrder }) {
  const navigate = useNavigate();
  const busy = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (work: () => Promise<number | null>, missing: string) => {
    if (busy.current) return; // chặn bấm đúp: mỗi lần POST /plan tạo một run và một hold
    busy.current = true;
    setPending(true);
    setError(null);
    try {
      const runId = await work();
      if (runId === null) setError(missing);
      else navigate(`${PATHS.dispatcherPlanReview}/${runId}`);
    } catch (caught) {
      setError(describeError(caught));
    } finally {
      busy.current = false;
      setPending(false);
    }
  };

  if (order.status === "PLANNED" || order.status === "SUBMITTED") {
    const planned = order.status === "PLANNED";
    const label = planned ? "Plan review" : "Run planning";
    return (
      <div className="flex flex-col items-start gap-1">
        <button type="button" disabled={pending} aria-label={`${label} for order ${order.orderNo}`} className={button}
          onClick={() => void (planned
            ? run(() => findLatestRunId(order.id), "No planning run was found for this order. Refresh the queue and try again.")
            : run(() => startPlanning(order.id), "The server did not return a planning run. Refresh the queue to check the order."))}>
          {pending ? "Working…" : label}
        </button>
        {error && <span role="alert" className="max-w-[16rem] text-xs text-risk-predictedLate-fg">{error}</span>}
      </div>
    );
  }

  const destination = destinationFor(order);
  if (!destination) return <span className="text-xs text-inkMuted">—</span>;
  return (
    <Link to={destination.to} aria-label={`${destination.label} for order ${order.orderNo}`} className={button}>
      {destination.label}
    </Link>
  );
}