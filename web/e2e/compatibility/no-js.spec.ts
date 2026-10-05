import { expect, test } from "@playwright/test";

import { installArticleFixture } from "../helpers/article";

test("reads an article and follows links with JavaScript disabled", async ({ page }) => {
  await page.goto("/about");
  await installArticleFixture(page);
  await page.goto("/blog/e2e-navigation");
  await expect(page.getByRole("heading", { name: /Navigation fixture$/ })).toBeVisible();
  await expect(page.locator("article .katex").first()).toBeVisible();
  await expect(page.locator("article pre")).toContainText("print('navigation')");
  await expect(page.locator("html")).toHaveClass(/no-js/);
  const request = page.waitForRequest((request) => new URL(request.url()).search === "?visit=2");
  await page.getByRole("link", { name: /Read again/ }).click();
  expect((await request).isNavigationRequest()).toBe(true);
  await expect(page).toHaveURL(/\?visit=2$/);
  await expect(page.getByRole("heading", { name: /Navigation fixture$/ })).toBeVisible();
  const aboutRequest = page.waitForRequest(
    (request) => new URL(request.url()).pathname === "/about",
  );
  await page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true })
    .click();
  expect((await aboutRequest).isNavigationRequest()).toBe(true);
  await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\?visit=2$/);
  await expect(page.getByRole("heading", { name: /Navigation fixture$/ })).toBeVisible();
});
