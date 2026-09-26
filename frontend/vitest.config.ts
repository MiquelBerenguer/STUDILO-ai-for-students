import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Component tests (jsdom + Testing Library). E2E uses @playwright/test separately (not run by `npm test`).
export default defineConfig({
  plugins: [react()],
  cacheDir: path.resolve(__dirname, ".vite-cache"),
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
