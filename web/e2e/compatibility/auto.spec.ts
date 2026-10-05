import { expect, test } from "@playwright/test";

for (const disableNavigationAPI of [false, true]) {
  test(`auto mode navigates and restores islands (${disableNavigationAPI ? "forced HTMX fallback" : "browser capabilities"})`, async ({
    page,
    context,
    browserName,
  }) => {
    if (browserName === "chromium") await context.grantPermissions(["local-network-access"]);
    const errors: Error[] = [];
    page.on("pageerror", (error) => errors.push(error));
    if (disableNavigationAPI) {
      await page.addInitScript(() => {
        Reflect.deleteProperty(window, "navigation");
        Reflect.deleteProperty(window, "NavigateEvent");
      });
    }
    await page.goto("/test");
    await expect(page.locator('meta[name="page-navigation-mode"]')).toHaveAttribute(
      "content",
      "auto",
    );
    const counter = page.locator('[data-solid-island="Counter"]');
    await expect(counter.getByText("Count: 1024", { exact: true })).toBeVisible();
    await counter.getByRole("button", { name: "+1" }).click();
    const supportsNative = await page.evaluate(
      () =>
        "navigation" in window &&
        "NavigateEvent" in window &&
        typeof NavigateEvent.prototype.intercept === "function",
    );
    if (disableNavigationAPI) expect(supportsNative).toBe(false);
    const originalBody = await page.locator("body").elementHandle();
    const request = page.waitForRequest((request) => new URL(request.url()).pathname === "/about");
    await page
      .locator(".site-navbar__links")
      .getByRole("link", { name: "About", exact: true })
      .click();
    const navigationRequest = await request;
    expect(navigationRequest.isNavigationRequest()).toBe(false);
    expect(navigationRequest.headers()["hx-request"]).toBe(supportsNative ? undefined : "true");
    await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
    expect(await originalBody!.evaluate((node) => node === document.body)).toBe(true);
    await expect(counter).toHaveCount(0);
    await page.goBack();
    await expect(counter.getByText("Count: 1024", { exact: true })).toBeVisible();
    await counter.getByRole("button", { name: "+1" }).click();
    await expect(counter.getByText("Count: 1025", { exact: true })).toBeVisible();
    await page.goForward();
    await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
    await expect(page.locator("body")).not.toHaveAttribute("aria-busy");
    await expect(page.locator("body")).not.toHaveAttribute("data-page-transition");
    expect(errors).toEqual([]);
  });
}
