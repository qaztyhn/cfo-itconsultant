/**
 * ExternalHandoffForm — Khối 'Handled outside CFO' khi MANUAL_PLANNING và gate trả hint EXTERNAL_HANDOFF (03 mục 5.2, v1.1).
 * Owner: Dev 3 (luồng C).
 */
export interface ExternalHandoffFormProps {
  className?: string;
}

export function ExternalHandoffForm({ className }: ExternalHandoffFormProps) {
  // TODO(#C-ExternalHandoffForm)
  return <div className={className} data-component="ExternalHandoffForm" />;
}
