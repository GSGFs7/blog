import { defineConfig, devices } from "@playwright/test";

import { createWebServers, sharedConfig } from "./playwright.shared.config";

export default defineConfig(sharedConfig, {
  testDir: "./web/e2e/ssr",
  projects: [
    {
      name: "ssr-chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: createWebServers(true),
});
