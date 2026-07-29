import { expect, test, type Page } from "@playwright/test";

async function navigateToAbout(page: Page): Promise<void> {
  const aboutLink = page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true });
  const htmxRequest = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/about" && request.headers()["hx-request"] === "true",
  );

  await aboutLink.click();
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

async function historyFadeState(page: Page): Promise<string | null> {
  return page.locator("body").getAttribute("data-history-fade");
}

test.describe("page transitions", () => {
  test("fades boosted page navigation", async ({ page }) => {
    await page.goto("/test");

    const transitionDuration = await page
      .locator(".site-main")
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).transitionDuration));
    expect(transitionDuration).toBeGreaterThan(0);

    const fadeOut = page.waitForFunction(() => document.body.dataset.pageTransition === "leaving");
    await navigateToAbout(page);
    await fadeOut;
    await expect(page.locator("body")).not.toHaveAttribute("data-page-transition", /.+/);
  });

  test("fades cached back and forward navigation", async ({ page }) => {
    await page.goto("/test");
    await navigateToAbout(page);

    await observePageFade(page);
    await page.goBack();
    await expect.poll(() => historyFadeState(page)).toBe("seen");
    await expect(page).toHaveURL(/\/test$/);
    await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toHaveAttribute("data-page-transition", /.+/);

    await observePageFade(page);
    await page.goForward();
    await expect.poll(() => historyFadeState(page)).toBe("seen");
    await expect(page).toHaveURL(/\/about$/);
    await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
    await expect(page.locator("body")).not.toHaveAttribute("data-page-transition", /.+/);
  });

  test("fades history cache misses", async ({ page }) => {
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
    await expect.poll(() => historyFadeState(page)).toBe("seen");
    await expect(page).toHaveURL(/\/test$/);
    await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toHaveAttribute("data-page-transition", /.+/);
  });

  test("skips history fades when reduced motion is requested", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/test");
    await navigateToAbout(page);
    await observePageFade(page);

    const transitionDuration = await page
      .locator(".site-main")
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).transitionDuration));
    expect(transitionDuration).toBe(0);

    await page.goBack();
    await expect.poll(() => historyFadeState(page)).toBe("missing");
    await expect(page).toHaveURL(/\/test$/);
    await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
  });
});
