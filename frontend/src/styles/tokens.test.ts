/**
 * Test design tokens (docs/03 mục 2, 10; docs/09 mục 9).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { describe, expect, it } from "vitest";
import config from "../../tailwind.config";

interface RiskPair {
  bg: string;
  fg: string;
}
interface Colors {
  deepPine: string;
  pine: string;
  apricot: string;
  stone: string;
  ink: string;
  inkMuted: string;
  surface: string;
  border: string;
  chip: string;
  navActive: string;
  rowHover: string;
  risk: { onTrack: RiskPair; atRisk: RiskPair; predictedLate: RiskPair; overdue: RiskPair; lateRow: string };
}

const extend = config.theme?.extend;
const colors = extend?.colors as unknown as Colors;

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("design tokens match docs/03 mục 2.1", () => {
  it("defines the brand palette", () => {
    expect(colors).toMatchObject({
      deepPine: "#0B2E2B",
      pine: "#0F4D47",
      apricot: "#E07B39",
      stone: "#F4F2ED",
      ink: "#14201F",
      inkMuted: "#56625F",
      surface: "#FFFFFF",
      border: "#E3DFD6",
      chip: "#ECE9E1",
    });
  });

  it("defines the four risk states with distinct backgrounds", () => {
    const { onTrack, atRisk, predictedLate, overdue, lateRow } = colors.risk;
    expect(onTrack).toEqual({ bg: "#E0EEEA", fg: "#0E4A44" });
    expect(atRisk).toEqual({ bg: "#FCE8CC", fg: "#7A4106" });
    expect(predictedLate).toEqual({ bg: "#F9DBD2", fg: "#8F2710" });
    expect(overdue).toEqual({ bg: "#7A1F10", fg: "#FFFFFF" });
    expect(lateRow).toBe("#FFF4EE");
    expect(new Set([onTrack.bg, atRisk.bg, predictedLate.bg, overdue.bg]).size).toBe(4);
  });

  it("uses the specified fonts with fallbacks and radii", () => {
    expect(extend?.fontFamily).toEqual({
      sans: ["Schibsted Grotesk", "Arial", "sans-serif"],
      mono: ["JetBrains Mono", "Courier New", "monospace"],
    });
    expect(extend?.borderRadius).toEqual({ card: "16px", control: "10px" });
  });

  it("defines the type scale from docs/03 mục 2.2", () => {
    const scale = extend?.fontSize as Record<string, [string, { lineHeight: string }]>;
    expect(scale.h1).toEqual(["36px", expect.objectContaining({ lineHeight: "40px" })]);
    expect(scale.h2).toEqual(["22px", expect.objectContaining({ lineHeight: "28px" })]);
    expect(scale.h3).toEqual(["16px", expect.objectContaining({ lineHeight: "22px" })]);
    expect(scale.body).toEqual(["14px", expect.objectContaining({ lineHeight: "20px" })]);
    expect(scale.caption).toEqual(["12px", expect.objectContaining({ lineHeight: "16px" })]);
    expect(scale.overline).toEqual(["11px", expect.objectContaining({ lineHeight: "14px", letterSpacing: "0.08em" })]);
  });
});

describe("WCAG AA contrast (docs/03 mục 10) for the colour pairs the UI uses", () => {
  const pairs: [string, string, string][] = [
    ["ink on stone", colors.ink, colors.stone],
    ["ink on surface", colors.ink, colors.surface],
    ["inkMuted on stone", colors.inkMuted, colors.stone],
    ["inkMuted on surface", colors.inkMuted, colors.surface],
    ["white on pine (primary button)", colors.surface, colors.pine],
    ["deepPine on apricot (action button, badge) — decision #4", colors.deepPine, colors.apricot],
    ["apricot on deepPine (accent on dark)", colors.apricot, colors.deepPine],
    ["deepPine on navActive", colors.deepPine, colors.navActive],
    ["onTrack", colors.risk.onTrack.fg, colors.risk.onTrack.bg],
    ["atRisk", colors.risk.atRisk.fg, colors.risk.atRisk.bg],
    ["predictedLate", colors.risk.predictedLate.fg, colors.risk.predictedLate.bg],
    ["overdue", colors.risk.overdue.fg, colors.risk.overdue.bg],
  ];

  it.each(pairs)("%s is at least 4.5:1", (_name, fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });

  it("documents why white text on apricot is not used", () => {
    expect(contrast(colors.surface, colors.apricot)).toBeLessThan(4.5);
  });
});

describe("no hard-coded hex colours in components (docs/09 mục 9)", () => {
  const files = import.meta.glob("../**/*.tsx", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
  const stripComments = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("scans at least one component file", () => {
    expect(Object.keys(files).length).toBeGreaterThan(0);
  });

  it.each(Object.entries(files).filter(([path]) => !path.includes(".test.")))("%s", (_path, source) => {
    expect(stripComments(source)).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});