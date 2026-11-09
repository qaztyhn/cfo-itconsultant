/**
 * Allowlist projection cho CS (DEC-CS-PRIVACY-20261109) — lớp phòng thủ phía UI, KHÔNG thay CS projection phía server.
 * Chỉ copy field được phép sang object mới; mọi field khác (lat/lon, receiving_restrictions, approved_plan_id,
 * latest_run_id, điểm số, phone/email thô…) không bao giờ vào state/props/DOM, kể cả khi server trả thừa.
 * Phone/email: chỉ nhận chuỗi `phone_masked` / `email_masked` trông giống đã mask; không hợp lệ → null (UI hiện "Contact hidden").
 * DEPENDENCY: schema.d.ts và DTO CS (tên field masked, shape /notifications, /eta-forecasts) chưa được Dev 1/Dev 3 chốt;
 * kiểu dưới đây là kiểu local của phần đã allowlist, thay bằng kiểu sinh từ OpenAPI khi có.
 * Owner: Dev 3 (luồng C).
 */

export const CONTACT_HIDDEN = "Contact hidden";

type Rec = Record<string, unknown>;

export function asRecord(value: unknown): Rec | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Rec) : null;
}

export function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 && value.length <= 200 ? value : null;
}

/** Mã ngắn (status, template, channel…): chỉ ký tự an toàn, chặn văn bản tự do. */
export function token(value: unknown): string | null {
  return typeof value === "string" && /^[A-Za-z0-9_.:-]{1,40}$/.test(value) ? value : null;
}

export function isoString(value: unknown): string | null {
  return typeof value === "string" && value.length <= 40 && !Number.isNaN(Date.parse(value)) ? value : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** `{items:[…]}` hoặc mảng trần; shape khác → []. */
export function itemsOf(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw;
  const rec = asRecord(raw);
  return rec && Array.isArray(rec.items) ? rec.items : [];
}

/** Ghi nhận vi phạm hợp đồng: chỉ tên field, KHÔNG BAO GIỜ ghi giá trị (tránh log PII). */
export function reportContractViolation(field: string): void {
  console.warn(`[cs] contract violation: ${field} is not a server-masked value`);
}

const MASK_CHARS = /[•*]/;

/** Phòng thủ tạm của UI: có ký tự mask, chỉ gồm ký tự điện thoại, tối đa 7 chữ số lộ ra. Không thay backend. */
export function isServerMaskedPhone(value: string): boolean {
  if (value.length > 40 || !MASK_CHARS.test(value)) return false;
  if (!/^[+\d\s()•*.-]+$/.test(value)) return false;
  return value.replace(/\D/g, "").length <= 7;
}

/** Phần trước "@" phải có ký tự mask; email đầy đủ bị loại. */
export function isServerMaskedEmail(value: string): boolean {
  if (value.length > 100 || /\s/.test(value)) return false;
  const at = value.indexOf("@");
  if (at < 1 || at !== value.lastIndexOf("@")) return false;
  return MASK_CHARS.test(value.slice(0, at));
}

function maskedField(raw: unknown, field: string, isValid: (v: string) => boolean): string | null {
  if (raw === undefined || raw === null) return null;
  if (typeof raw === "string" && isValid(raw)) return raw;
  reportContractViolation(field);
  return null;
}

// ---------- Kiểu đã allowlist ----------

export interface CsOrderListItem {
  id: number;
  orderNo: string;
  status: string | null;
  customerName: string | null;
  committedDate: string | null;
  promiseEnd: string | null;
  riskColor: string | null;
}

export interface CsOrderPage {
  items: CsOrderListItem[];
  page: number;
  pageSize: number;
  total: number;
}

export interface CsOrderDetail {
  id: number;
  orderNo: string;
  externalRef: string | null;
  status: string | null;
  submittedAt: string | null;
  customerName: string | null;
  /** phone/email: chuỗi đã mask từ server hoặc null → UI hiện CONTACT_HIDDEN. */
  contact: { name: string | null; phone: string | null; email: string | null };
  committed: { date: string | null; promiseStart: string | null; promiseEnd: string | null };
  risk: { status: string | null; color: string | null; forecastEta: string | null } | null;
}

export interface CsNotification {
  id: number | string;
  template: string | null;
  channel: string | null;
  status: string | null;
  at: string | null;
}

export interface CsEtaForecast {
  version: number | null;
  forecastEta: string | null;
  riskStatus: string | null;
}

// ---------- Projection ----------

export function projectCsOrderPage(raw: unknown): CsOrderPage | null {
  const rec = asRecord(raw);
  if (!rec || !Array.isArray(rec.items)) return null;
  const items: CsOrderListItem[] = [];
  for (const entry of rec.items) {
    const o = asRecord(entry);
    const id = o ? num(o.id) : null;
    const orderNo = o ? str(o.order_no) : null;
    if (!o || id === null || orderNo === null) continue;
    items.push({
      id,
      orderNo,
      status: token(o.status),
      customerName: str(o.customer_name),
      committedDate: str(o.committed_date),
      promiseEnd: str(o.promise_end),
      riskColor: token(o.risk_color),
    });
  }
  return { items, page: num(rec.page) ?? 1, pageSize: num(rec.page_size) ?? items.length, total: num(rec.total) ?? items.length };
}

export function projectCsOrderDetail(raw: unknown): CsOrderDetail | null {
  const rec = asRecord(raw);
  const id = rec ? num(rec.id) : null;
  const orderNo = rec ? str(rec.order_no) : null;
  if (!rec || id === null || orderNo === null) return null;

  const customer = asRecord(rec.customer);
  const contact = asRecord(rec.contact);
  const committed = asRecord(rec.committed);
  const risk = asRecord(rec.risk);

  return {
    id,
    orderNo,
    externalRef: str(rec.external_ref),
    status: token(rec.status),
    submittedAt: isoString(rec.submitted_at),
    customerName: str(customer?.name) ?? str(contact?.name),
    contact: {
      name: str(contact?.name),
      phone: maskedField(contact?.phone_masked, "contact.phone_masked", isServerMaskedPhone),
      email: maskedField(contact?.email_masked, "contact.email_masked", isServerMaskedEmail),
    },
    committed: {
      date: str(committed?.date),
      promiseStart: str(committed?.promise_start),
      promiseEnd: str(committed?.promise_end),
    },
    risk: risk ? { status: token(risk.status), color: token(risk.color), forecastEta: isoString(risk.forecast_eta) } : null,
  };
}

export function projectCsNotifications(raw: unknown): CsNotification[] {
  const out: CsNotification[] = [];
  for (const entry of itemsOf(raw)) {
    const n = asRecord(entry);
    if (!n) continue;
    const id = num(n.id) ?? str(n.id);
    if (id === null) continue;
    out.push({
      id,
      template: token(n.template),
      channel: token(n.channel),
      status: token(n.status),
      at: isoString(n.sent_at) ?? isoString(n.created_at) ?? isoString(n.at),
    });
  }
  return out;
}

export function projectCsEtaForecasts(raw: unknown): CsEtaForecast[] {
  const out: CsEtaForecast[] = [];
  for (const entry of itemsOf(raw)) {
    const e = asRecord(entry);
    if (!e) continue;
    out.push({ version: num(e.version), forecastEta: isoString(e.forecast_eta), riskStatus: token(e.risk_status) });
  }
  return out;
}