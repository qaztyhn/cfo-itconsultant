/**
 * Design tokens (docs/03 mục 2, 11). KHÔNG hard-code hex trong component — chỉ dùng token ở đây (09 mục 9).
 * Owner: Dev 3 (luồng C) — M0.
 */
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        deepPine: "#0B2E2B",
        pine: "#0F4D47",
        apricot: "#E07B39",
        stone: "#F4F2ED",
        ink: "#14201F",
        inkMuted: "#56625F",
        surface: "#FFFFFF",
        border: "#E3DFD6",
        chip: "#ECE9E1",
        risk: {
          onTrack: { bg: "#E0EEEA", fg: "#0E4A44" },
          atRisk: { bg: "#FCE8CC", fg: "#7A4106" },
          predictedLate: { bg: "#F9DBD2", fg: "#8F2710" },
          overdue: { bg: "#7A1F10", fg: "#FFFFFF" },
          lateRow: "#FFF4EE",
        },
      },
      fontFamily: {
        sans: ["Schibsted Grotesk", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "Courier New", "monospace"],
      },
      borderRadius: { card: "16px", control: "10px" },
    },
  },
  plugins: [],
} satisfies Config;
