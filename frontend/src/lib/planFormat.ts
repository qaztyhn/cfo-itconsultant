/**
 * Định dạng hiển thị cho Plan Review. Giờ theo múi giờ market, không theo trình duyệt (docs/05 mục 1).
 * DEPENDENCY: MARKET_TIMEZONE cố định "Europe/Stockholm" đến khi lấy từ ref.market.timezone.
 * Không có hàm nào định dạng tiền: Plan Review không hiển thị tiền hoặc chi phí (03 #1, #37).
 */
import type { DecimalLike, GateKey, Plan } from "../api/contracts/planning";

export const MARKET_TIMEZONE = "Europe/Stockholm";

export const GATE_LABELS: Record<GateKey, string> = {
  stock: "Stock",
  preparation: "Preparation",
  truck: "Truck",
  site_date: "Site/Date",
  safety: "Safety",
};

export function gateLabel(key: string): string {
  return key in GATE_LABELS ? GATE_LABELS[key as GateKey] : key;
}

export function toNumber(value: DecimalLike | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "string" ? Number(value) : value;
  return Number.isFinite(n) ? n : null;
}

function validDate(iso?: string | null): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatTime(iso?: string | null, timeZone = MARKET_TIMEZONE): string {
  const d = validDate(iso);
  if (!d) return "—";
  return new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
}

/** "Tue 10 Nov, 12:38" */
export function formatDayTime(iso?: string | null, timeZone = MARKET_TIMEZONE): string {
  const d = validDate(iso);
  if (!d) return "—";
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone, weekday: "short", day: "numeric", month: "short" }).formatToParts(d);
  const pick = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${pick("weekday")} ${pick("day")} ${pick("month")}, ${formatTime(iso, timeZone)}`;
}

export function formatKm(value: DecimalLike | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : `${Math.round(n)} km`;
}

/** capacity_fill là tỉ lệ 0–1 → "60%". */
export function formatFill(value: DecimalLike | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

export function formatScore(value: DecimalLike | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : n.toFixed(2);
}

export function formatKg(value: DecimalLike | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : `${new Intl.NumberFormat("en-GB").format(n)} kg`;
}

export function formatM3(value: DecimalLike | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : `${n} m³`;
}

/** 30000 kg → "30 t"; 12500 kg → "12.5 t". */
export function formatTonnes(kg: number): string {
  const t = kg / 1000;
  return `${Number.isInteger(t) ? t : t.toFixed(1)} t`;
}

/** planning_reserve_min → "3.6 days". */
export function formatReserve(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  return `${(minutes / 1440).toFixed(1)} days`;
}

export function minutesBetween(fromIso?: string | null, toIso?: string | null): number | null {
  const a = validDate(fromIso);
  const b = validDate(toIso);
  return a && b ? Math.round((b.getTime() - a.getTime()) / 60000) : null;
}

export function formatDuration(minutes: number | null): string {
  if (minutes === null) return "—";
  const sign = minutes < 0 ? "-" : "";
  const abs = Math.abs(minutes);
  const h = Math.floor(abs / 60);
  const m = abs % 60;
  return `${sign}${h > 0 ? `${h}h ` : ""}${m}min`;
}

/** Tóm tắt nguồn lực dự kiến commit khi duyệt (chỉ dữ kiện vận hành, không tiền). */
export function describeCommit(plan: Plan, showDriver: boolean): string {
  const warehouse = plan.warehouse?.name ?? "the selected warehouse";
  const vehicles = plan.vehicles
    .map((v) => {
      const driver = showDriver && v.driver ? `, driver ${v.driver.name}` : "";
      return `${v.vehicle.code} (${formatKg(v.load_kg)}${driver})`;
    })
    .join("; ");
  const prep = toNumber(plan.prep_hours) !== null ? ` Preparation ${toNumber(plan.prep_hours)} h.` : "";
  const noun = plan.vehicle_count === 1 ? "vehicle" : "vehicles";
  return `This will commit ${warehouse}: ${plan.vehicle_count} ${noun} — ${vehicles}.${prep} Delivery ETA ${formatDayTime(plan.eta_at)}.`;
}