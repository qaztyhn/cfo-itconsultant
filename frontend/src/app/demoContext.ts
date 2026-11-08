/**
 * Câu ngữ cảnh dưới banner DEMO theo màn (docs/03 mục 3.1). Hàm thuần, khớp theo tiền tố đường dẫn.
 * Owner: Dev 3 (luồng C) — M0.
 */
export const DEFAULT_DEMO_CONTEXT = "All data on this site is synthetic.";

const CONTEXT: readonly { prefix: string; text: string }[] = [
  { prefix: "/dispatcher", text: "Orders, stock and trucks are synthetic seed data." },
  { prefix: "/warehouse", text: "Shifts and preparation times are synthetic." },
  { prefix: "/store", text: "Store orders come from the simulated POS." },
  { prefix: "/cs", text: "Customer data is fictitious and masked." },
  { prefix: "/it", text: "Integrations are simulated; nothing connects to a real ERP, WMS or POS." },
  { prefix: "/kpi", text: "Figures are computed from the demo week, not real operations." },
  { prefix: "/revenue", text: "Revenue figures are synthetic, not real financial data." },
  { prefix: "/notifications", text: "Emails and SMS are simulated; nothing reaches real customers." },
];

export function demoContextFor(pathname: string): string {
  const clean = pathname.split(/[?#]/)[0].replace(/\/+$/, "") || "/";
  const match = CONTEXT.find((c) => clean === c.prefix || clean.startsWith(`${c.prefix}/`));
  return match?.text ?? DEFAULT_DEMO_CONTEXT;
}