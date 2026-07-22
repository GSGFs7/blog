import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./web/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      name: "vite",
      command: "pnpm dev",
      url: "http://localhost:5173/@vite/client",
      reuseExistingServer: !process.env.CI,
    },
    {
      name: "django",
      command: "uv run manage.py runasgi 127.0.0.1:8000 --no-reload",
      url: "http://127.0.0.1:8000",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
