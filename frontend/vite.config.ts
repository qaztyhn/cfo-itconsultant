/**
 * Vite config: React + PWA cho driver (manifest "CFO Driver", theme #0B2E2B, docs/03 mục 9).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: { name: "CFO Driver", short_name: "CFO Driver", display: "standalone", theme_color: "#0B2E2B", start_url: "/driver" },
    }),
  ],
  resolve: { alias: { "@": "/src" } },
  server: { port: 5173 },
});
