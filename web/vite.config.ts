import { sentryVitePlugin } from "@sentry/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Web Sentry (R-36): with SENTRY_AUTH_TOKEN set at build time, source maps are made, uploaded to
// Sentry and deleted from dist, so they are never served (R-21). Without it: no maps at all.
const upload = !!process.env.SENTRY_AUTH_TOKEN;

export default defineConfig({
  plugins: [react(), ...(upload ? [sentryVitePlugin({ org: process.env.SENTRY_ORG, project: process.env.SENTRY_PROJECT ?? "web",
    authToken: process.env.SENTRY_AUTH_TOKEN, release: { name: process.env.VITE_RELEASE },
    sourcemaps: { filesToDeleteAfterUpload: ["./dist/**/*.map"] } })] : [])],
  // VAYU_API: another API to proxy to (e.g. a second backend on 8001); ../shared holds the rule vectors
  server: { port: 5173, proxy: { "^/api/": process.env.VAYU_API ?? "http://localhost:8000" }, fs: { allow: [".."] } },
  // no source maps in what is served: the full source would be downloadable (R-21)
  build: { sourcemap: upload ? "hidden" : false },
  test: {
    environment: "jsdom",
    env: { TZ: "Asia/Kolkata" },        // tests that build local dates mean India time, as the app does
    setupFiles: ["./src/test-setup.ts"],
    exclude: ["e2e/**", "e2e-local/**", "node_modules/**"],
  },
});
