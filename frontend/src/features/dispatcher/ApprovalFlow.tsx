/**
 * Luồng duyệt phương án (docs/06 mục 6.3). Owner: Dev 3 (luồng C) — M5.
 * - Idempotency-Key gắn với (plan, nội dung gửi): thử lại cùng nội dung dùng lại key, đổi nội dung thì tạo key mới.
 * - Chỉ báo thành công khi backend trả order.status === "APPROVED". Không bypass 409 nào.
 * - T16 backend hiện fail-closed khi chưa có recheck adapter: lỗi PLAN_NOT_APPROVABLE được hiển thị nguyên văn, không giả thành công.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { ApiError, isApiError, newIdempotencyKey } from "../../api/client";
import { USE_MOCKS } from "../../api/config";
import type { ApprovePlanInput, ApprovePlanResponse, Plan, PlanningRun } from "../../api/contracts/planning";
import { approvePlan, planningKeys } from "../../api/planning";
import { DecisionBar } from "../../components/DecisionBar";
import { ReasonModal, type ReasonOption, type ReasonResult } from "../../components/ReasonModal";
import { describeCommit, formatDayTime, formatTime } from "../../lib/planFormat";

// docs/06 chưa định nghĩa danh mục mã lý do chọn phương án khác (ví dụ mẫu: closest_to_customer).
const ALT_REASONS: ReasonOption[] = [
  { code: "closest_to_customer", label: "Closer or better for the customer" },
  { code: "stock_preference", label: "Better stock position" },
  { code: "resource_preference", label: "Better vehicle or driver fit" },
  { code: "other", label: "Other" },
];

/** Lỗi được hiển thị thành khung cố định (không có nút bỏ qua); lỗi khác ném lại để modal hiện và cho thử lại. */
const PANEL_CODES = new Set(["RESOURCE_CONFLICT", "PLAN_NOT_APPROVABLE", "HOLD_EXPIRED", "FORBIDDEN", "APPROVAL_NOT_CONFIRMED"]);

const CONFLICT_CAUSE: Record<string, string> = {
  vehicle: "A selected vehicle is no longer available.",
  driver: "A selected driver is no longer available.",
  stock: "Stock is no longer sufficient.",
  labour: "Warehouse preparation capacity is no longer sufficient.",
  five_gates: "The five-gate recheck failed against current data.",
};

export interface ApprovalFlowProps {
  run: PlanningRun;
  plan: Plan | null;
  showDriver: boolean;
  expired: boolean;
  onApproved: () => void;
  /** Mặc định theo chế độ chạy; tách ra để test. */
  mock?: boolean;
}

export function ApprovalFlow({ run, plan, showDriver, expired, onApproved, mock = USE_MOCKS }: ApprovalFlowProps) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [problem, setProblem] = useState<ApiError | null>(null);
  const [result, setResult] = useState<ApprovePlanResponse | null>(null);
  const keyRef = useRef<{ fingerprint: string; key: string } | null>(null);

  async function handleConfirm({ reasonCode, reasonText }: ReasonResult) {
    if (!plan || expired) return;
    const body: ApprovePlanInput = plan.rank > 1 ? { reason_code: reasonCode, reason_text: reasonText } : reasonText ? { note: reasonText } : {};
    const fingerprint = `${plan.id}:${JSON.stringify(body)}`;
    if (keyRef.current?.fingerprint !== fingerprint) keyRef.current = { fingerprint, key: newIdempotencyKey() };

    try {
      const response = await approvePlan(plan.id, body, keyRef.current.key);
      if (response.order?.status !== "APPROVED") {
        throw new ApiError("APPROVAL_NOT_CONFIRMED", "The backend did not return APPROVED, so the plan was not approved.");
      }
      setResult(response);
      setProblem(null);
      setOpen(false);
      onApproved();
      void queryClient.invalidateQueries({ queryKey: planningKeys.run(run.id) });
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
    } catch (error) {
      if (isApiError(error) && PANEL_CODES.has(error.code)) {
        setProblem(error);
        setOpen(false);
        if (error.code === "HOLD_EXPIRED") void queryClient.invalidateQueries({ queryKey: planningKeys.run(run.id) });
        return;
      }
      throw error;
    }
  }

  return (
    <>
      {result && <SuccessPanel result={result} mock={mock} />}
      {problem && <ProblemPanel error={problem} />}
      <DecisionBar
        plan={plan}
        expired={expired}
        approved={result !== null}
        onApprove={() => {
          setProblem(null);
          setOpen(true);
        }}
      />
      {plan && (
        <ReasonModal
          open={open && !expired && result === null}
          title={`Approve plan #${plan.rank}`}
          description={describeCommit(plan, showDriver)}
          reasons={plan.rank > 1 ? ALT_REASONS : undefined}
          requireNote={plan.rank > 1}
          noteLabel={plan.rank > 1 ? "Why this plan instead of #1?" : "Notes (optional)"}
          confirmLabel={`Approve #${plan.rank}`}
          onConfirm={handleConfirm}
          onCancel={() => setOpen(false)}
        />
      )}
    </>
  );
}

function SuccessPanel({ result, mock }: { result: ApprovePlanResponse; mock: boolean }) {
  const committed = result.order.committed;
  return (
    <div role="status" className="flex flex-col gap-1 rounded-card border border-risk-onTrack-bg bg-risk-onTrack-bg p-4 text-risk-onTrack-fg">
      <p className="text-h3">
        <span aria-hidden="true">✓ </span>Approved · order status {result.order.status}
      </p>
      {committed && (
        <p className="text-body">
          Committed delivery {formatDayTime(committed.promise_start)}–{formatTime(committed.promise_end)}.
        </p>
      )}
      {result.trip_ids.length > 0 && <p className="font-mono text-caption">Trips {result.trip_ids.join(", ")}</p>}
      {mock && <p className="font-mono text-caption">MOCK API · simulated approval, nothing was committed to a real backend.</p>}
    </div>
  );
}

function ProblemPanel({ error }: { error: ApiError }) {
  const conflict = (error.details as { conflict?: unknown } | undefined)?.conflict;
  let title = "Approval failed";
  let cause = error.message;
  let guidance = "";

  switch (error.code) {
    case "RESOURCE_CONFLICT":
      title = "Resource conflict: this plan can no longer be committed";
      cause = typeof conflict === "string" && CONFLICT_CAUSE[conflict] ? CONFLICT_CAUSE[conflict] : error.message;
      guidance = "Another order took these resources or the data changed. Use Plan Again to build a new plan from current data.";
      break;
    case "PLAN_NOT_APPROVABLE":
      title = "This plan cannot be approved";
      guidance = "Approval cannot be bypassed. If the order or source data changed, use Plan Again.";
      break;
    case "HOLD_EXPIRED":
      title = "Hold expired";
      guidance = "Use Plan Again to create a new plan. The old plan cannot be approved.";
      break;
    case "FORBIDDEN":
      title = "Permission denied";
      cause = "Your role is not allowed to approve this plan.";
      break;
    case "APPROVAL_NOT_CONFIRMED":
      title = "Approval not confirmed";
      guidance = "The order was not approved. Check the order status before trying again.";
      break;
  }

  return (
    <div role="alert" className="flex flex-col gap-1 rounded-card border border-risk-predictedLate-bg bg-risk-lateRow p-4 text-risk-predictedLate-fg">
      <p className="text-h3">
        <span aria-hidden="true">✕ </span>
        {title}
      </p>
      <p className="text-body text-ink">{cause}</p>
      {guidance && <p className="text-body text-ink">{guidance}</p>}
      <p className="font-mono text-caption">
        {error.code}
        {error.correlationId ? ` · Ref ${error.correlationId}` : ""}
      </p>
    </div>
  );
}