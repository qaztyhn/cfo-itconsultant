/**
 * Design tokens (docs/03 mục 2, 11). KHÔNG hard-code hex trong component — chỉ dùng token ở đây (09 mục 9).
 * Owner: Dev 3 (luồng C) — M0.
 *
 * Quy ước a11y (03 mục 10): chữ trên nền `apricot` dùng `deepPine` (4.90:1), KHÔNG dùng chữ trắng (2.97:1).
 * Chữ `apricot` chỉ đặt trên nền `deepPine` (sidebar, thanh quyết định, banner demo).
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
        navActive: "#E8F1EF", // mục menu đang chọn (03 mục 3.2)
        rowHover: "#FAF8F4", // hover hàng bảng (03 mục 4)
        risk: {
          onTrack: { bg: "#E0EEEA", fg: "#0E4A44" },
          atRisk: { bg: "#FCE8CC", fg: "#7A4106" },
          predictedLate: { bg: "#F9DBD2", fg: "#8F2710" },
          overdue: { bg: "#7A1F10", fg: "#FFFFFF" },
          // Nền hàng Predicted late; cũng dùng cho "Your decision", banner gợi ý lập lại, thẻ nháp DELAY
          lateRow: "#FFF4EE",
        },
      },
      fontFamily: {
        sans: ["Schibsted Grotesk", "Arial", "sans-serif"],
        mono: ["JetBrains Mono", "Courier New", "monospace"],
      },
      // Thang chữ 03 mục 2.2: [cỡ, { lineHeight, fontWeight, letterSpacing }]
      fontSize: {
        h1: ["36px", { lineHeight: "40px", fontWeight: "700" }],
        h2: ["22px", { lineHeight: "28px", fontWeight: "700" }],
        h3: ["16px", { lineHeight: "22px", fontWeight: "600" }],
        body: ["14px", { lineHeight: "20px" }],
        caption: ["12px", { lineHeight: "16px" }],
        overline: ["11px", { lineHeight: "14px", letterSpacing: "0.08em" }],
        kpi: ["48px", { lineHeight: "1", fontWeight: "700" }], // số liệu lớn, dùng với font-mono
        kpiSm: ["32px", { lineHeight: "1", fontWeight: "700" }],
      },
      borderRadius: { card: "16px", control: "10px" }, // chip trạng thái: rounded-full (pill)
      borderColor: ({ theme }) => ({ DEFAULT: theme("colors.border") }), // viền mặc định 1px #E3DFD6
      boxShadow: { card: "0 1px 2px rgba(20, 32, 31, 0.06)" }, // tối đa theo 03 mục 2.3
      maxWidth: { content: "1440px" },
      spacing: { sidebar: "262px" }, // w-sidebar, pl-sidebar
    },
  },
  plugins: [],
} satisfies Config;