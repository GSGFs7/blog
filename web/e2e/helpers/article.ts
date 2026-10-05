import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { expect, type Page } from "@playwright/test";

export async function installArticleFixture(page: Page): Promise<void> {
  const buildId = await page.locator('meta[name="app-build-id"]').getAttribute("content");
  const mode = await page.locator('meta[name="page-navigation-mode"]').getAttribute("content");
  const viteUrl = await page.locator('script[src*="/@vite/client"]').getAttribute("src");
  expect(buildId).toBeTruthy();
  expect(mode).toBeTruthy();
  expect(viteUrl).toBeTruthy();
  const { stdout: html } = await promisify(execFile)(
    "uv",
    ["run", "python", "-m", "web.e2e.fixtures.article", buildId!, new URL(viteUrl!).origin, mode!],
    { maxBuffer: 2 * 1024 * 1024 },
  );
  await page.route(/\/blog\/e2e-navigation(?:\?.*)?$/, (route) =>
    route.fulfill({ contentType: "text/html", body: html }),
  );
}
