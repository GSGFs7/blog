import { expect, test, type Page } from "@playwright/test";

async function navigateToAbout(page: Page): Promise<void> {
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
  await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
}

async function observePageFade(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.body.dataset.historyFade = "not-fired";
    document.addEventListener(
      "app:before-swap",
      () => {
        document.body.dataset.historyFade =
          document.body.dataset.pageTransition === "leaving" ? "seen" : "missing";
      },
      { once: true },
    );
  });
}

test("fades HTMX history cache misses", async ({ page }) => {
  await page.goto("/test");
  await navigateToAbout(page);
  await page.evaluate(() => sessionStorage.removeItem("htmx-history-cache"));
  await observePageFade(page);

  const historyRequest = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/test" &&
      request.headers()["hx-history-restore-request"] === "true",
  );
  await page.goBack();
  await historyRequest;

  await expect.poll(() => page.locator("body").getAttribute("data-history-fade")).toBe("seen");
  await expect(page).toHaveURL(/\/test$/);
  await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toHaveAttribute("data-page-transition", /.+/);
});
