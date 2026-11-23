import { defineConfig } from "@playwright/test";

// Browser tests run against the real API (e2e settings: own database, fake S3, inline Celery).
export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [
    { command: "uv run moto_server -p 5055", cwd: "../backend", port: 5055, reuseExistingServer: true, stdout: "ignore", stderr: "ignore" },
    {
      command: "uv run python manage.py migrate -v0 && uv run python manage.py e2e_reset && uv run python manage.py runserver 8000 --noreload",
      cwd: "../backend", port: 8000, reuseExistingServer: !process.env.CI, timeout: 120_000, stdout: "ignore", stderr: "ignore",
      env: { DJANGO_SETTINGS_MODULE: "vayu.settings.e2e" },
    },
    { command: "npm run dev -- --host localhost", port: 5173, reuseExistingServer: true, stdout: "ignore", stderr: "ignore" },
  ],
});
