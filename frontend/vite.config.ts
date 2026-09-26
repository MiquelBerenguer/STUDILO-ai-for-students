import { readFileSync } from "node:fs";
import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const brandFile = path.resolve(__dirname, "../config/brand.json");
// Ports come from the Makefile (per-worktree .worktree.mk), so parallel worktrees don't collide.
const backend = `http://127.0.0.1:${process.env.BACKEND_PORT ?? "8000"}`;
const frontendPort = Number(process.env.FRONTEND_PORT ?? 5173);

// Injects the product name from config/brand.json into index.html (%BRAND_NAME%, %BRAND_TAGLINE%).
function brandHtml(): Plugin {
  return {
    name: "brand-html",
    transformIndexHtml(html) {
      const brand = JSON.parse(readFileSync(brandFile, "utf-8"));
      return html.replaceAll("%BRAND_NAME%", brand.name).replaceAll("%BRAND_TAGLINE%", brand.tagline);
    },
  };
}

// The dev server proxies /api to FastAPI, so the session cookie is same-origin (no CORS).
// `npm run dev -- --host` exposes it on the LAN for phone uploads.
export default defineConfig({
  plugins: [react(), tailwindcss(), brandHtml()],
  build: { chunkSizeWarningLimit: 1200 },
  server: {
    port: frontendPort,
    fs: { allow: [__dirname, path.dirname(brandFile)] },
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
  preview: { proxy: { "/api": { target: backend } } },
});
