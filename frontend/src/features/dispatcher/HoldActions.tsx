/**
 * Hành động trên hold (docs/06 mục 6, DEC-HOLD-001): gia hạn tối đa 2 lần (server quyết định) và Plan Again.
 * Plan Again tạo planning_run MỚI cho cùng order, bắt buộc lý do; không hồi sinh hay duyệt run cũ.
 * Owner: Dev 3 (luồng C) — M4–M5.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { isApiError } from "../../api/client";
import type { PlanningRun } from "../../api/contracts/planning";
import { extendHold, planAgain, planningKeys } from "../../api/planning";
import { PATHS } from "../../app/access";
import { ReasonModal, type ReasonOption, type ReasonResult } from "../../components/ReasonModal";

export const MAX_HOLD_EXTENSIONS = 2;

// docs/06 chưa định nghĩa danh mục mã lý do lập lại (ReasonModal: do nơi gọi truyền vào).
const PLAN_AGAIN_REASONS: ReasonOption[] = [
  { code: "hold_expired", label: "Hold expired" },
  { code: "criteria_change", label: "Planning criteria changed" },
  { code: "resource_change", label: "Vehicle, driver or stock changed" },
  { code: "other", label: "Other" },
];

function extendErrorMessage(error: unknown): string {
  if (!isApiError(error)) return "Could not extend the hold. Try again.";
  if (error.code === "HOLD_EXTENSION_LIMIT") return "The hold was already extended twice. Use Plan Again if this order still needs a plan.";
  if (error.code === "HOLD_EXPIRED") return "The hold has expired. Use Plan Again.";
  return error.message;
}

export interface HoldActionsProps {
  run: PlanningRun;
  expired: boolean;
}

export function HoldActions({ run, expired }: HoldActionsProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [modalOpen, setModalOpen] = useState(false);

  const extension = useMutation({
    mutationFn: () => extendHold(run.id),
    onSuccess: (updated) => queryClient.setQueryData(planningKeys.run(run.id), updated),
    onError: (error) => {
      // Server nói hold đã hết hạn: lấy lại trạng thái thật thay vì tin đồng hồ máy khách.
      if (isApiError(error) && error.code === "HOLD_EXPIRED") {
        void queryClient.invalidateQueries({ queryKey: planningKeys.run(run.id) });
      }
    },
  });

  const left = Math.max(0, MAX_HOLD_EXTENSIONS - run.hold_extensions);
  const canExtend = !expired && left > 0 && !extension.isPending;

  async function handlePlanAgain(result: ReasonResult) {
    // Lỗi (409/422…) được ném lại để ReasonModal hiện trong modal và giữ modal mở.
    const next = await planAgain(run.order_id, { reason_code: result.reasonCode ?? "other", reason_text: result.reasonText });
    queryClient.setQueryData(planningKeys.run(next.id), next);
    void queryClient.invalidateQueries({ queryKey: planningKeys.runs(run.order_id) });
    setModalOpen(false);
    navigate(`${PATHS.dispatcherPlanReview}/${next.id}`);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => extension.mutate()}
        disabled={!canExtend}
        className="rounded-control border bg-surface px-3 py-1.5 text-body font-semibold text-ink disabled:opacity-50"
      >
        {extension.isPending ? "Extending…" : "Extend hold +15 min"}
        {!expired && <span className="ml-2 font-mono text-caption text-inkMuted">{left > 0 ? `${left} left` : "No extensions left"}</span>}
      </button>
      <button
        type="button"
        onClick={() => setModalOpen(true)}
        className={
          expired
            ? "rounded-control bg-apricot px-3 py-1.5 text-body font-semibold text-deepPine"
            : "rounded-control border bg-surface px-3 py-1.5 text-body font-semibold text-ink"
        }
      >
        Plan Again
      </button>

      {extension.isError && (
        <p role="alert" className="basis-full text-caption text-risk-predictedLate-fg">
          {extendErrorMessage(extension.error)}
          {isApiError(extension.error) && extension.error.correlationId && (
            <span className="ml-2 font-mono">Ref {extension.error.correlationId}</span>
          )}
        </p>
      )}

      <ReasonModal
        open={modalOpen}
        title="Plan Again"
        description="This creates a new planning run for the same order and a new hold. The previous plans cannot be approved afterwards."
        reasons={PLAN_AGAIN_REASONS}
        noteLabel="Why are you planning again?"
        confirmLabel="Plan Again"
        onConfirm={handlePlanAgain}
        onCancel={() => setModalOpen(false)}
      />
    </>
  );
}