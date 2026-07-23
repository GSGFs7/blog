import { defineConfig, devices } from "@playwright/test";

import { createWebServers, sharedConfig } from "./playwright.shared.config";

export default defineConfig(sharedConfig, {
  testIgnore: ["**/ssr/**"],
  projects: [
    {
      name: "desktop-chromium",
      testIgnore: ["**/*.mobile.spec.ts", "**/ssr/**"],
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-chromium",
      testMatch: ["**/*.mobile.spec.ts"],
      use: { ...devices["Pixel 10"] },
    },
    {
      name: "firefox-smoke",
      testMatch: ["**/island-navigation.spec.ts"],
      use: { ...devices["Desktop Firefox"] },
    },
  ],
  webServer: createWebServers(),
});
