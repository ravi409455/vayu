import { defineConfig } from "@playwright/test";
import { API_PORT, WEB, WEB_PORT } from "./e2e/ports";

const LOGS = process.env.E2E_LOGS ? "pipe" : "ignore";   // E2E_LOGS=1 shows the servers' output

// Browser tests run against the real API (e2e settings: own database, fake S3, inline Celery).
export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: WEB, trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    { command: "uv run moto_server -p 5055", cwd: "../backend", port: 5055, reuseExistingServer: true, stdout: LOGS, stderr: LOGS },
    {
      command: `uv run python manage.py migrate -v0 && uv run python manage.py e2e_reset && uv run python manage.py runserver ${API_PORT} --noreload`,
      cwd: "../backend", port: API_PORT, reuseExistingServer: !process.env.CI, timeout: 120_000, stdout: LOGS, stderr: LOGS,
      env: { DJANGO_SETTINGS_MODULE: "vayu.settings.e2e", E2E_WEB: WEB },
    },
    { command: `npm run dev -- --host localhost --port ${WEB_PORT} --strictPort`, port: WEB_PORT, reuseExistingServer: true, stdout: LOGS, stderr: LOGS,
      env: { VAYU_API: `http://localhost:${API_PORT}` } },
  ],
});
