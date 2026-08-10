import { expect, test, type Page } from "@playwright/test";

declare global {
  interface Window {
    __e2eNavigationEnded: boolean;
    __recordPageFade(state: "seen" | "missing"): void;
  }
}

async function observeNextNavigationEnd(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.__e2eNavigationEnded = false;
    document.addEventListener(
      "app:navigation-end",
      () => {
        window.__e2eNavigationEnded = true;
      },
      { once: true },
    );
  });
}

async function waitForNavigationEnd(page: Page): Promise<void> {
  await expect.poll(() => page.evaluate(() => window.__e2eNavigationEnded)).toBe(true);
}

async function navigateToAbout(page: Page): Promise<void> {
  const aboutLink = page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true });

  await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
  await observeNextNavigationEnd(page);
  await aboutLink.click();
  await waitForNavigationEnd(page);
  await expect(page).toHaveURL(/\/about$/);
  await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
}

async function installPageFadeProbe(page: Page): Promise<Array<"seen" | "missing">> {
  const states: Array<"seen" | "missing"> = [];
  await page.exposeFunction("__recordPageFade", (state: "seen" | "missing") => {
    states.push(state);
  });
  return states;
}

async function observeNextPageFade(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.addEventListener(
      "app:before-swap",
      () => {
        window.__recordPageFade(
          document.body.dataset.pageTransition === "leaving" ? "seen" : "missing",
        );
      },
      { once: true },
    );
  });
}

test.describe("page transitions", () => {
  test("fades enhanced page navigation", async ({ page }) => {
    await page.goto("/test");
    await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
    const fadeStates = await installPageFadeProbe(page);

    const transitionDuration = await page
      .locator(".site-main")
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).transitionDuration));
    expect(transitionDuration).toBeGreaterThan(0);

    await observeNextPageFade(page);
    await navigateToAbout(page);
    await expect.poll(() => [...fadeStates]).toEqual(["seen"]);
    await expect(page.locator("body")).not.toHaveAttribute("data-page-transition", /.+/);
  });

  test("fades back and forward navigation", async ({ page }) => {
    await page.goto("/test");
    await navigateToAbout(page);
    const fadeStates = await installPageFadeProbe(page);

    await observeNextPageFade(page);
    await observeNextNavigationEnd(page);
    await page.goBack();
    await waitForNavigationEnd(page);
    await expect.poll(() => [...fadeStates]).toEqual(["seen"]);
    await expect(page).toHaveURL(/\/test$/);
    await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toHaveAttribute("data-page-transition", /.+/);

    await observeNextPageFade(page);
    await observeNextNavigationEnd(page);
    await page.goForward();
    await waitForNavigationEnd(page);
    await expect.poll(() => [...fadeStates]).toEqual(["seen", "seen"]);
    await expect(page).toHaveURL(/\/about$/);
    await expect(page.getByRole("heading", { name: "关于我" })).toBeVisible();
    await expect(page.locator("body")).not.toHaveAttribute("data-page-transition", /.+/);
  });

  test("skips history fades when reduced motion is requested", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/test");
    await navigateToAbout(page);
    const fadeStates = await installPageFadeProbe(page);
    await observeNextPageFade(page);

    const transitionDuration = await page
      .locator(".site-main")
      .evaluate((element) => Number.parseFloat(getComputedStyle(element).transitionDuration));
    expect(transitionDuration).toBe(0);

    await observeNextNavigationEnd(page);
    await page.goBack();
    await waitForNavigationEnd(page);
    await expect.poll(() => [...fadeStates]).toEqual(["missing"]);
    await expect(page).toHaveURL(/\/test$/);
    await expect(page.getByText("Count: 1024", { exact: true })).toBeVisible();
  });
});
