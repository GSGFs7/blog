import { defineConfig, type PlaywrightTestConfig } from "@playwright/test";

export const sharedConfig = defineConfig({
  testDir: "./web/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});

export function createWebServers(ssr = false): PlaywrightTestConfig["webServer"] {
  const reuseExistingServer = !process.env.CI && !ssr;

  return [
    {
      name: "vite",
      command: "pnpm dev",
      url: "http://localhost:5173/@vite/client",
      reuseExistingServer,
    },
    {
      name: "django",
      command: "uv run manage.py runasgi 127.0.0.1:8000 --no-reload",
      url: "http://127.0.0.1:8000",
      env: ssr
        ? {
            DEBUG: "True",
            SOLID_ISLANDS_SSR: "True",
          }
        : undefined,
      reuseExistingServer,
    },
  ];
}
