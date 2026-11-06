/**
 * ReasonModal — Modal lý do bắt buộc (chọn khác, chạy lại, kế hoạch tay, hủy/lập lại, bỏ nháp, từ chối ánh xạ, giữ kế hoạch cũ khi có gợi ý lập lại).
 * Owner: Dev 3 (luồng C).
 */
export interface ReasonModalProps {
  className?: string;
}

export function ReasonModal({ className }: ReasonModalProps) {
  // TODO(#C-ReasonModal)
  return <div className={className} data-component="ReasonModal" />;
}
