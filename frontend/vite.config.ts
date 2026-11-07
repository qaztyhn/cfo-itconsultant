/**
 * Vite config: React + PWA cho driver (manifest "CFO Driver", theme #0B2E2B, docs/03 mục 9) + Vitest (jsdom).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: { name: "CFO Driver", short_name: "CFO Driver", display: "standalone", theme_color: "#0B2E2B", start_url: "/driver" },
      workbox: { globIgnores: ["**/mockServiceWorker.js"] },
    }),
  ],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 5173 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});