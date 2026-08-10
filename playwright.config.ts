import { defineConfig, devices, type PlaywrightTestConfig } from "@playwright/test";
import { loadEnv } from "vite";

type E2ESuite = "base" | "htmx" | "native" | "ssr";
type NavigationMode = "auto" | "htmx" | "native";

type WebServerOptions = {
  pageNavigationMode?: NavigationMode;
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

function getE2ESuite(): E2ESuite {
  const suite = process.env.E2E_SUITE ?? "base";

  if (suite === "base" || suite === "htmx" || suite === "native" || suite === "ssr") {
    return suite;
  }

  throw new Error(`Unsupported E2E_SUITE: ${suite}`);
}

function getNavigationMode(suite: E2ESuite): NavigationMode {
  const defaultMode = suite === "base" ? "auto" : suite === "native" ? "native" : "htmx";
  const mode = process.env.E2E_NAVIGATION_MODE ?? defaultMode;

  if (mode !== "auto" && mode !== "htmx" && mode !== "native") {
    throw new Error(`Unsupported E2E_NAVIGATION_MODE: ${mode}`);
  }
  if (suite === "htmx" && mode !== "htmx") {
    throw new Error("The HTMX E2E suite requires E2E_NAVIGATION_MODE=htmx");
  }
  if (suite === "native" && mode !== "native") {
    throw new Error("The native E2E suite requires E2E_NAVIGATION_MODE=native");
  }

  return mode;
}

function createWebServers({
  pageNavigationMode = "auto",
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

function createSuiteConfig(suite: E2ESuite, navigationMode: NavigationMode): PlaywrightTestConfig {
  switch (suite) {
    case "base":
      return {
        testDir: "./web/e2e/base",
        projects: [
          {
            name: "desktop-chromium",
            testIgnore: ["**/*.mobile.spec.ts"],
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
        webServer: createWebServers({
          pageNavigationMode: navigationMode,
          reuseDjangoServer: false,
        }),
      };
    case "htmx":
      return {
        testDir: "./web/e2e/htmx",
        projects: [
          {
            name: "htmx-chromium",
            use: { ...devices["Desktop Chrome"] },
          },
        ],
        webServer: createWebServers({
          pageNavigationMode: navigationMode,
          reuseDjangoServer: false,
        }),
      };
    case "native":
      return {
        testDir: "./web/e2e/native",
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
          pageNavigationMode: navigationMode,
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
          pageNavigationMode: navigationMode,
          debug: true,
          solidIslandsSsr: true,
          reuseViteServer: false,
          reuseDjangoServer: false,
        }),
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

const suite = getE2ESuite();

export default defineConfig(sharedConfig, createSuiteConfig(suite, getNavigationMode(suite)));
