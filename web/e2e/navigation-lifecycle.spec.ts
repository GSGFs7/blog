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

async function observeHistoryFade(page: Page, eventName: string): Promise<void> {
  await page.evaluate((name) => {
    document.body.dataset.historyFade = "not-fired";
    document.body.addEventListener(
      name,
      () => {
        document.body.dataset.historyFade = document.body.classList.contains("htmx-swapping")
          ? "seen"
          : "missing";
      },
      { once: true },
    );
  }, eventName);
}

async function historyFadeState(page: Page): Promise<string | null> {
  return page.locator("body").getAttribute("data-history-fade");
}

test.describe("HTMX and Solid island navigation", () => {
  test("cleans up and remounts Counter after navigating back", async ({ page }) => {
    const pageErrors: Error[] = [];
    page.on("pageerror", (error) => pageErrors.push(error));

    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/test");

    const initialCounter = page.locator('[data-solid-island="Counter"]');
    const initialIncrement = initialCounter.getByRole("button", { name: "+1" });

    await expect(initialCounter.getByText("Count: 1024", { exact: true })).toBeVisible();
    await expect(initialIncrement).toHaveCount(1);
    await initialIncrement.click();
    await expect(initialCounter.getByText("Count: 1025", { exact: true })).toBeVisible();

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
    await expect(page.locator('[data-solid-island="Counter"]')).toHaveCount(0);

    await page.goBack();
    await expect(page).toHaveURL(/\/test$/);

    const restoredCounter = page.locator('[data-solid-island="Counter"]');
    const restoredIncrement = restoredCounter.getByRole("button", { name: "+1" });
    await expect(restoredCounter.getByText("Count: 1024", { exact: true })).toBeVisible();
    await expect(restoredIncrement).toHaveCount(1);
    await restoredIncrement.click();
    await expect(restoredCounter.getByText("Count: 1025", { exact: true })).toBeVisible();

    expect(pageErrors).toEqual([]);
  });
});

test.describe("page transitions", () => {
  test("fades boosted page navigation", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/test");

    const transitionDuration = await page
      .locator(".site-main")
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).transitionDuration));
    expect(transitionDuration).toBeGreaterThan(0);

    const fadeOut = page.waitForFunction(() => document.body.classList.contains("htmx-swapping"));
    await navigateToAbout(page);
    await fadeOut;
    await expect(page.locator("body")).not.toHaveClass(/htmx-(swapping|settling)/);
  });

  test("fades cached back and forward navigation", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/test");
    await navigateToAbout(page);

    await observeHistoryFade(page, "htmx:historyCacheHit");
    await page.goBack();
    await expect.poll(() => historyFadeState(page)).toBe("seen");
    await expect(page).toHaveURL(/\/test$/);
    await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toHaveClass(/htmx-(swapping|settling)/);

    await observeHistoryFade(page, "htmx:historyCacheHit");
    await page.goForward();
    await expect.poll(() => historyFadeState(page)).toBe("seen");
    await expect(page).toHaveURL(/\/about$/);
    await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
    await expect(page.locator("body")).not.toHaveClass(/htmx-(swapping|settling)/);
  });

  test("fades history cache misses", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/test");
    await navigateToAbout(page);
    await page.evaluate(() => sessionStorage.removeItem("htmx-history-cache"));
    await observeHistoryFade(page, "htmx:historyCacheMissLoad");

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
    await expect(page.locator("body")).not.toHaveClass(/htmx-(swapping|settling)/);
  });

  test("skips history fades when reduced motion is requested", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/test");
    await navigateToAbout(page);
    await observeHistoryFade(page, "htmx:historyCacheHit");

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
