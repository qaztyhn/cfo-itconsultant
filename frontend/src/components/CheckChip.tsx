/**
 * CheckChip — Pass/fail chip for plan validation checks.
 * Owner: Dev 3 (luồng C).
 */

export interface CheckChipProps {
  name: string;
  passed: boolean;
  code: string;
  className?: string;
}

export function CheckChip({ name, passed, code, className }: CheckChipProps) {
  return (
    <div className={`flex flex-col gap-0.5 ${className ?? ""}`}>
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-mono ${
          passed
            ? "bg-risk-onTrack-bg text-risk-onTrack-fg"
            : "bg-risk-predictedLate-bg text-risk-predictedLate-fg"
        }`}
        aria-label={`${name}: ${passed ? "passed" : "failed"}`}
      >
        <span aria-hidden="true">{passed ? "✓" : "✕"}</span>
        {name}
      </span>
      {!passed && (
        <span className="text-[10px] font-mono text-inkMuted pl-1">{code}</span>
      )}
    </div>
  );
}
