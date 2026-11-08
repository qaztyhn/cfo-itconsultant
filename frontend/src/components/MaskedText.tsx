/**
 * MaskedText — che email/điện thoại (u•••@takservice.demo, +46 •• ••• 12 34; docs/03 mục 4).
 * Che theo mặc định; chỉ hiện đủ khi nơi gọi truyền `revealed` (quyết định theo vai trò/quyền ở nơi gọi, không suy ra ở đây).
 * Khi che, giá trị gốc KHÔNG được đưa vào DOM. Dữ liệu server đã che sẵn (vd. recipient_masked) thì hiện thẳng chuỗi, không dùng component này.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { maskEmail, maskPhone } from "../lib/mask";

export interface MaskedTextProps {
  kind: "email" | "phone";
  value?: string | null;
  revealed?: boolean;
  className?: string;
}

export function MaskedText({ kind, value, revealed = false, className }: MaskedTextProps) {
  const classes = ["font-mono", className].filter(Boolean).join(" ");

  if (!value) {
    return <span className={classes}>—</span>;
  }
  if (revealed) {
    return <span className={classes}>{value}</span>;
  }

  return (
    <span className={classes} data-masked="true">
      <span aria-hidden="true">{kind === "email" ? maskEmail(value) : maskPhone(value)}</span>
      <span className="sr-only">{kind === "email" ? "Email address (hidden)" : "Phone number (hidden)"}</span>
    </span>
  );
}