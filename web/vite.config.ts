import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // VAYU_API: another API to proxy to (e.g. a second backend on 8001); ../shared holds the rule vectors
  server: { port: 5173, proxy: { "^/api/": process.env.VAYU_API ?? "http://localhost:8000" }, fs: { allow: [".."] } },
  build: { sourcemap: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    exclude: ["e2e/**", "e2e-local/**", "node_modules/**"],
  },
});
