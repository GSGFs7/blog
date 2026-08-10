import { expect, test } from "@playwright/test";

test("uses HTMX for boosted page navigation", async ({ page }) => {
  await page.goto("/test");
  await expect(page.locator('meta[name="page-navigation-mode"]')).toHaveAttribute(
    "content",
    "htmx",
  );

  const htmxRequest = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/about" && request.headers()["hx-request"] === "true",
  );

  await page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true })
    .click();
  await htmxRequest;

  await expect(page).toHaveURL(/\/about$/);
  await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
});
