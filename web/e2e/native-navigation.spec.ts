import { expect, test, type Page } from "@playwright/test";

interface NavigationProbeEvent {
  name: string;
  navigationId: number;
  navigationType?: NavigationType;
  outcome?: string;
  requestedUrl?: string;
  finalUrl?: string;
}

interface NavigationProbe {
  documentId: string;
  events: NavigationProbeEvent[];
}

declare global {
  interface Window {
    __nativeNavigationProbe: NavigationProbe;
  }
}

const lifecycleEvents = [
  "app:navigation-start",
  "app:before-swap",
  "app:after-swap",
  "app:navigation-end",
  "app:navigation-error",
] as const;

async function installNavigationProbe(page: Page): Promise<void> {
  await page.addInitScript((eventNames) => {
    window.__nativeNavigationProbe = {
      documentId: crypto.randomUUID(),
      events: [],
    };

    for (const name of eventNames) {
      document.addEventListener(name, (event) => {
        const detail = (event as CustomEvent).detail;
        window.__nativeNavigationProbe.events.push({
          name,
          navigationId: detail.navigationId,
          navigationType: detail.navigationType,
          outcome: detail.outcome,
          requestedUrl: detail.requestedUrl?.href,
          finalUrl: detail.finalUrl?.href,
        });
      });
    }
  }, lifecycleEvents);
}

async function probe(page: Page): Promise<NavigationProbe> {
  return page.evaluate(() => window.__nativeNavigationProbe);
}

async function clearProbeEvents(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.__nativeNavigationProbe.events = [];
  });
}

async function expectCompletedLifecycle(page: Page, navigationType: NavigationType): Promise<void> {
  await expect
    .poll(async () => (await probe(page)).events)
    .toEqual([
      expect.objectContaining({
        name: "app:navigation-start",
        navigationType,
      }),
      expect.objectContaining({ name: "app:before-swap" }),
      expect.objectContaining({ name: "app:after-swap" }),
      expect.objectContaining({
        name: "app:navigation-end",
        navigationType,
        outcome: "completed",
      }),
    ]);
}

async function openNativeTestPage(page: Page, path = "/test"): Promise<string> {
  await installNavigationProbe(page);
  await page.goto(path);

  await expect(page.locator('meta[name="page-navigation-mode"]')).toHaveAttribute(
    "content",
    "native",
  );
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          "navigation" in window &&
          "NavigateEvent" in window &&
          typeof NavigateEvent.prototype.intercept === "function",
      ),
    )
    .toBe(true);

  return (await probe(page)).documentId;
}

test("navigates a regular page without replacing the document", async ({ page }) => {
  const initialDocumentId = await openNativeTestPage(page);
  const requestPromise = page.waitForRequest(
    (request) => new URL(request.url()).pathname === "/about" && request.resourceType() === "fetch",
  );

  await page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true })
    .click();
  const request = await requestPromise;

  await expect(page).toHaveURL(/\/about$/);
  await expect(page).toHaveTitle(/^About -/);
  await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toHaveAttribute("aria-busy");
  await expect(page.locator("body")).not.toHaveAttribute("data-page-transition");
  expect(request.headers()["hx-request"]).toBeUndefined();
  expect((await probe(page)).documentId).toBe(initialDocumentId);
  await expectCompletedLifecycle(page, "push");
});

test("restores pages through back and forward traversal", async ({ page }) => {
  const initialDocumentId = await openNativeTestPage(page, "/");
  await page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true })
    .click();
  await expect(page).toHaveURL(/\/about$/);
  await expectCompletedLifecycle(page, "push");

  await clearProbeEvents(page);
  await page.goBack({ waitUntil: "commit" });
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Hi!", exact: true })).toBeVisible();
  await expectCompletedLifecycle(page, "traverse");
  expect((await probe(page)).documentId).toBe(initialDocumentId);

  await clearProbeEvents(page);
  await page.goForward({ waitUntil: "commit" });
  await expect(page).toHaveURL(/\/about$/);
  await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
  await expectCompletedLifecycle(page, "traverse");
  expect((await probe(page)).documentId).toBe(initialDocumentId);
});

test("restores a private page through same-document history traversal", async ({ page }) => {
  const initialDocumentId = await openNativeTestPage(page);
  await page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true })
    .click();
  await expect(page).toHaveURL(/\/about$/);
  await expectCompletedLifecycle(page, "push");

  await clearProbeEvents(page);
  await page.goBack({ waitUntil: "commit" });

  await expect(page).toHaveURL(/\/test$/);
  await expect(page).toHaveTitle(/^Test page -/);
  await expect(page.locator('[data-solid-island="Counter"]')).toHaveAttribute(
    "data-props",
    /"initial":1024/,
  );
  expect((await probe(page)).documentId).toBe(initialDocumentId);
  await expectCompletedLifecycle(page, "traverse");
});

test("navigates to a private page without replacing the document", async ({ page }) => {
  const initialDocumentId = await openNativeTestPage(page);
  await page.evaluate(() => {
    const link = document.createElement("a");
    link.href = "/login";
    link.textContent = "Login E2E";
    document.body.append(link);
  });
  const fetchRequest = page.waitForRequest(
    (request) => new URL(request.url()).pathname === "/login" && request.resourceType() === "fetch",
  );

  await page.getByRole("link", { name: "Login E2E" }).click();
  await fetchRequest;

  await expect(page).toHaveURL(/\/login$/);
  await expect(page).toHaveTitle(/^Login -/);
  expect((await probe(page)).documentId).toBe(initialDocumentId);
  await expectCompletedLifecycle(page, "push");
});

test("commits and swaps the final URL from a redirect", async ({ page }) => {
  const initialDocumentId = await openNativeTestPage(page);
  const aboutRequestTypes: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/about") {
      aboutRequestTypes.push(request.resourceType());
    }
  });
  await page.route(/\/native-redirect$/, async (route) => {
    await route.fulfill({
      status: 302,
      headers: { location: "/about" },
      body: "",
    });
  });
  await page.evaluate(() => {
    const link = document.createElement("a");
    link.href = "/native-redirect";
    link.textContent = "Redirect E2E";
    document.body.append(link);
  });

  await page.getByRole("link", { name: "Redirect E2E" }).click();

  await expect(page).toHaveURL(/\/about$/);
  await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
  await expectCompletedLifecycle(page, "push");
  expect((await probe(page)).documentId).toBe(initialDocumentId);
  expect(aboutRequestTypes).toEqual(["fetch"]);
  expect((await probe(page)).events.at(-1)).toMatchObject({
    outcome: "completed",
    requestedUrl: expect.stringMatching(/\/native-redirect$/),
    finalUrl: expect.stringMatching(/\/about$/),
  });

  await clearProbeEvents(page);
  await page.goBack({ waitUntil: "commit" });
  await expect(page).toHaveURL(/\/test$/);
  await expectCompletedLifecycle(page, "traverse");
});
