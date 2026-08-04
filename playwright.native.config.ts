import { defineConfig, devices } from "@playwright/test";

import { sharedConfig } from "./playwright.shared.config";

export default defineConfig(sharedConfig, {
  testMatch: ["**/native-navigation.spec.ts"],
  workers: 1,
  projects: [
    {
      name: "native-firefox",
      use: { ...devices["Desktop Firefox"] },
    },
  ],
  use: {
    baseURL: "http://127.0.0.1:8001",
  },
  webServer: [
    {
      name: "vite",
      command: "pnpm dev",
      url: "http://localhost:5173/@vite/client",
      reuseExistingServer: !process.env.CI,
    },
    {
      name: "django-native",
      command: "uv run manage.py runasgi 127.0.0.1:8001 --no-reload",
      url: "http://127.0.0.1:8001",
      env: {
        DEBUG: "True",
        PAGE_NAVIGATION_MODE: "native",
      },
      reuseExistingServer: false,
    },
  ],
});
