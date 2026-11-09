/**
 * Hằng số UI của CS Order Lookup.
 * SEARCH_PLACEHOLDER không nhắc số điện thoại: GET /orders?q= chưa tìm theo phone (DEC-CS-SEARCH-20261109 chưa có ở backend).
 * Khi backend ship và có test thật, đổi copy ở đây và thêm test.
 */
export const SEARCH_PLACEHOLDER = "Order no., external ref or customer name";


/** Nhãn bắt buộc của form contact-log: chưa có POST/GET /orders/{id}/contact-logs (F3), nên chỉ là demo cục bộ. */
export const DEMO_LABEL = "Demo only — not saved to backend";

/** Giá trị theo ops.customer_contact_log (docs/05; F5). Server là nơi quyết định giới hạn khác (vd. độ dài note). */
export const CONTACT_CHANNELS = [
  { value: "phone", label: "Phone" },
  { value: "email", label: "Email" },
  { value: "chat", label: "Chat" },
] as const;

export const CONTACT_REASONS = [
  { value: "where_is_my_order", label: "Where is my order" },
  { value: "change_request", label: "Change request" },
  { value: "complaint", label: "Complaint" },
  { value: "delay_inquiry", label: "Delay inquiry" },
  { value: "other", label: "Other" },
] as const;