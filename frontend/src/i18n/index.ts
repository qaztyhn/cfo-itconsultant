/**
 * i18next, mặc định tiếng Anh; định dạng ngày "Wed 4 Nov", giờ 24h theo múi giờ market (docs/03 mục 8).
 * Owner: Dev 3 (luồng C) — M0.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";

void i18n.use(initReactI18next).init({ resources: { en: { translation: en } }, lng: "en", fallbackLng: "en" });

export default i18n;

/** Format date: "Wed 4 Nov" or "Today" */
export function fmtDate(isoDate: string, tz = "Europe/Stockholm"): string {
  const d = new Date(isoDate);
  const today = new Date();
  const dStr = d.toLocaleDateString("en-SE", { timeZone: tz, day: "numeric", month: "short", year: "numeric" });
  const todayStr = today.toLocaleDateString("en-SE", { timeZone: tz, day: "numeric", month: "short", year: "numeric" });
  if (dStr === todayStr) return "Today";
  return d.toLocaleDateString("en-GB", { timeZone: tz, weekday: "short", day: "numeric", month: "short" });
}

/** Format time HH:MM in market timezone */
export function fmtTime(isoDatetime: string, tz = "Europe/Stockholm"): string {
  return new Date(isoDatetime).toLocaleTimeString("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false });
}

/** Format duration from minutes */
export function fmtDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}

/** Format kg with narrow space: "4 120 kg" */
export function fmtKg(kg: number): string {
  return `${kg.toLocaleString("sv-SE")} kg`;
}

/** Format SEK with narrow space and currency code */
export function fmtSEK(amount: string | number): string {
  const n = typeof amount === "string" ? parseFloat(amount) : amount;
  return `${n.toLocaleString("sv-SE")} SEK`;
}
