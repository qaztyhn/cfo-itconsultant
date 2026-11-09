/**
 * Định dạng hiển thị cho CS. Thời gian luôn hiện theo UTC kèm nhãn: DTO CS chưa có timezone của market
 * (DEPENDENCY) và UI không đoán timezone từ trình duyệt.
 */
import type { RiskColor, RiskLevel } from "../../components/RiskChip";
import type { OrderStatus } from "../../components/StatusChip";

const RISK_LEVELS: readonly RiskLevel[] = ["ON_TRACK", "AT_RISK", "PREDICTED_LATE", "OVERDUE"];
const RISK_COLORS: readonly RiskColor[] = ["green", "yellow", "orange", "red"];

export function toRiskLevel(value: string | null): RiskLevel | undefined {
  return RISK_LEVELS.find((level) => level === value);
}

export function toRiskColor(value: string | null): RiskColor | undefined {
  return RISK_COLORS.find((color) => color === value);
}

/** StatusChip chịu được giá trị lạ (enum mới ở backend), nên chỉ ép kiểu. */
export function toOrderStatus(value: string): OrderStatus {
  return value as OrderStatus;
}

export function formatUtc(iso: string | null): string {
  if (!iso) return "—";
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return "—";
  return `${new Date(time).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

export function orDash(value: string | null): string {
  return value ?? "—";
}