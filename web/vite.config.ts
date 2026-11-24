import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // VAYU_API: another API to proxy to (e.g. a second backend on 8001); ../shared holds the rule vectors
  server: { port: 5173, proxy: { "^/api/": process.env.VAYU_API ?? "http://localhost:8000" }, fs: { allow: [".."] } },
  // no source maps in what is served: the full source would be downloadable (R-21). Web Sentry
  // (batch 7) makes them for its upload only.
  build: { sourcemap: false },
  test: {
    environment: "jsdom",
    env: { TZ: "Asia/Kolkata" },        // tests that build local dates mean India time, as the app does
    setupFiles: ["./src/test-setup.ts"],
    exclude: ["e2e/**", "e2e-local/**", "node_modules/**"],
  },
});
