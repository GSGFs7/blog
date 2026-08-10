import { defineConfig, devices, type PlaywrightTestConfig } from "@playwright/test";
import { loadEnv } from "vite";

type E2EMode = "htmx" | "native" | "ssr";

type WebServerOptions = {
  pageNavigationMode?: "htmx" | "native";
  debug?: boolean;
  solidIslandsSsr?: boolean;
  reuseViteServer?: boolean;
  reuseDjangoServer?: boolean;
};

const environment = loadEnv("development", process.cwd(), "");

function getPort(name: string, defaultPort: number): number {
  const value = process.env[name] ?? environment[name];
  const port = value ? Number(value) : defaultPort;

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`${name} must be a valid port`);
  }

  return port;
}

const djangoPort = getPort("DJANGO_PORT", 8001);
const vitePort = getPort("VITE_PORT", 5174);
const djangoBaseUrl = `http://127.0.0.1:${djangoPort}`;

function getE2EMode(): E2EMode {
  const mode = process.env.E2E_MODE ?? "htmx";

  if (mode === "htmx" || mode === "native" || mode === "ssr") {
    return mode;
  }

  throw new Error(`Unsupported E2E_MODE: ${mode}`);
}

function createWebServers({
  pageNavigationMode = "htmx",
  debug = false,
  solidIslandsSsr = false,
  reuseViteServer = !process.env.CI,
  reuseDjangoServer = !process.env.CI,
}: WebServerOptions = {}): PlaywrightTestConfig["webServer"] {
  return [
    {
      name: "vite",
      command: `pnpm dev --port ${vitePort}`,
      url: `http://localhost:${vitePort}/@vite/client`,
      env: {
        VITE_PORT: String(vitePort),
      },
      reuseExistingServer: reuseViteServer,
    },
    {
      name: "django",
      command: `uv run manage.py runasgi 127.0.0.1:${djangoPort} --no-reload`,
      url: djangoBaseUrl,
      env: {
        VITE_PORT: String(vitePort),
        PAGE_NAVIGATION_MODE: pageNavigationMode,
        ...(debug ? { DEBUG: "True" } : {}),
        ...(solidIslandsSsr ? { SOLID_ISLANDS_SSR: "True" } : {}),
      },
      reuseExistingServer: reuseDjangoServer,
    },
  ];
}

function createModeConfig(mode: E2EMode): PlaywrightTestConfig {
  switch (mode) {
    case "native":
      return {
        testMatch: ["**/native-navigation.spec.ts"],
        workers: 1,
        projects: [
          {
            name: "native-firefox",
            use: { ...devices["Desktop Firefox"] },
          },
        ],
        use: {
          baseURL: djangoBaseUrl,
        },
        webServer: createWebServers({
          pageNavigationMode: "native",
          debug: true,
          reuseDjangoServer: false,
        }),
      };
    case "ssr":
      return {
        testDir: "./web/e2e/ssr",
        projects: [
          {
            name: "ssr-chromium",
            use: { ...devices["Desktop Chrome"] },
          },
        ],
        webServer: createWebServers({
          debug: true,
          solidIslandsSsr: true,
          reuseViteServer: false,
          reuseDjangoServer: false,
        }),
      };
    case "htmx":
      return {
        testIgnore: ["**/native-navigation.spec.ts", "**/ssr/**"],
        projects: [
          {
            name: "desktop-chromium",
            testIgnore: ["**/*.mobile.spec.ts", "**/native-navigation.spec.ts", "**/ssr/**"],
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
      };
  }
}

const sharedConfig: PlaywrightTestConfig = {
  testDir: "./web/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: djangoBaseUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
};

export default defineConfig(sharedConfig, createModeConfig(getE2EMode()));
