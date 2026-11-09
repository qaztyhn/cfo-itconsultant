/**
 * Timeline cho CS (docs/06 §5.5): chỉ order_submitted, milestone (không toạ độ), notification, eta (forecast_eta, risk_status).
 * planning_run, decision và mọi kind lạ bị loại. Không render title/actor/detail tự do của server:
 * nhãn hiển thị do UI tự dựng từ kind; các mã (type/template/channel/status) phải qua token().
 * Owner: Dev 3 (luồng C).
 */
import { asRecord, isoString, itemsOf, token } from "./allowlist";

export const CS_TIMELINE_KINDS = ["order_submitted", "milestone", "notification", "eta"] as const;

export type CsTimelineItem =
  | { kind: "order_submitted"; at: string }
  | { kind: "milestone"; at: string; milestoneType: string | null }
  | { kind: "notification"; at: string; template: string | null; channel: string | null; status: string | null }
  | { kind: "eta"; at: string; forecastEta: string | null; riskStatus: string | null };

export function projectCsTimeline(raw: unknown): CsTimelineItem[] {
  const out: CsTimelineItem[] = [];
  for (const entry of itemsOf(raw)) {
    const rec = asRecord(entry);
    if (!rec) continue;
    const at = isoString(rec.at);
    if (!at) continue;
    const detail = asRecord(rec.detail) ?? {};
    switch (rec.kind) {
      case "order_submitted":
        out.push({ kind: "order_submitted", at });
        break;
      case "milestone":
        out.push({ kind: "milestone", at, milestoneType: token(detail.type) });
        break;
      case "notification":
        out.push({
          kind: "notification",
          at,
          template: token(detail.template ?? detail.type),
          channel: token(detail.channel),
          status: token(detail.status),
        });
        break;
      case "eta":
        out.push({ kind: "eta", at, forecastEta: isoString(detail.forecast_eta), riskStatus: token(detail.risk_status) });
        break;
      default:
        break; // planning_run, decision, kind lạ: không bao giờ vào state/DOM
    }
  }
  return out;
}
