/**
 * Hàm che dữ liệu cá nhân (docs/03 mục 4). Mẫu cố định nên không lộ độ dài giá trị gốc.
 * Che ở giao diện chỉ là lớp trình bày; quyền xem đủ vẫn do backend quyết định (docs/09).
 * Owner: Dev 3 (luồng C) — M0.
 */
const DOT = "•";

/** user@takservice.demo → u•••@takservice.demo */
export function maskEmail(value: string): string {
  const at = value.lastIndexOf("@");
  if (at < 1) {
    return DOT.repeat(3);
  }
  const [first] = Array.from(value.slice(0, at));
  return `${first}${DOT.repeat(3)}${value.slice(at)}`;
}

/** +46 70 123 12 34 → +46 •• ••• 12 34 (số quốc gia: •• ••• 12 34). ASM-K: mã quốc gia = "+" và 2 chữ số đầu. */
export function maskPhone(value: string): string {
  const trimmed = value.trim();
  const digits = trimmed.replace(/\D/g, "");
  if (digits.length < 6) {
    return `${DOT.repeat(2)} ${DOT.repeat(3)}`;
  }
  const last = digits.slice(-4);
  const tail = `${last.slice(0, 2)} ${last.slice(2)}`;
  const middle = `${DOT.repeat(2)} ${DOT.repeat(3)}`;
  if (trimmed.startsWith("+") && digits.length >= 8) {
    return `+${digits.slice(0, 2)} ${middle} ${tail}`;
  }
  return `${middle} ${tail}`;
}