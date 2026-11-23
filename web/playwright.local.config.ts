import { defineConfig } from "@playwright/test";

// Checks a running local stack (scripts/local.sh up): real worker, real file store, demo data.
export default defineConfig({
  testDir: "e2e-local",
  timeout: 120_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure", screenshot: "only-on-failure",
         permissions: ["geolocation"], geolocation: { latitude: 28.6139, longitude: 77.209 } },
});
