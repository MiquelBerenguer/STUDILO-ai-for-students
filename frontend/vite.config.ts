import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to FastAPI, so the session cookie is same-origin (no CORS).
// `npm run dev -- --host` exposes it on the LAN for phone uploads.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { chunkSizeWarningLimit: 1200 },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  preview: { proxy: { "/api": { target: "http://127.0.0.1:8000" } } },
});
