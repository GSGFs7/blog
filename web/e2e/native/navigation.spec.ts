import { expect, test, type Page } from "@playwright/test";

import { installArticleFixture } from "../helpers/article";

interface NavigationProbeEvent {
  name: string;
  navigationId: number;
  navigationType?: NavigationType;
  outcome?: string;
  requestedUrl?: string;
  finalUrl?: string;
  reason?: string;
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
  "app:before-leave",
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
          reason: detail.reason,
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
      expect.objectContaining({ name: "app:before-leave" }),
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

test("navigates a regular page without replacing the document in native mode", async ({ page }) => {
  const requestPromise = page.waitForRequest(
    (request) => new URL(request.url()).pathname === "/about" && request.resourceType() === "fetch",
  );
  const initialDocumentId = await openNativeTestPage(page);

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

test("preserves a live Solid island across a native page swap", async ({ page }) => {
  const aboutPath = "/about?e2e=preserve-island";
  const initialDocumentId = await openNativeTestPage(page);
  const counter = page.locator('[data-solid-island="Counter"]');
  await expect(counter.getByText("Count: 1024", { exact: true })).toBeVisible();
  await counter.getByRole("button", { name: "+1" }).click();
  await counter.evaluate((element) => {
    element.id = "preserved-counter";
    element.setAttribute("data-app-preserve", "");
  });
  const original = await counter.elementHandle();

  await page.route(
    (url) => url.pathname + url.search === aboutPath,
    async (route) => {
      const response = await route.fetch();
      const html = await response.text();
      await route.fulfill({
        response,
        body: html.replace(
          "</body>",
          '<div id="preserved-counter" data-app-preserve data-solid-island="Counter"></div></body>',
        ),
      });
    },
  );
  await navigateByLink(page, aboutPath);
  await expectCompletedLifecycle(page, "push");
  expect((await probe(page)).documentId).toBe(initialDocumentId);
  expect(
    await original!.evaluate((element) => element === document.getElementById("preserved-counter")),
  ).toBe(true);
  await expect(counter.getByText("Count: 1025", { exact: true })).toBeVisible();
  await counter.getByRole("button", { name: "+1" }).click();
  await expect(counter.getByText("Count: 1026", { exact: true })).toBeVisible();

  await clearProbeEvents(page);
  await page.goBack({ waitUntil: "commit" });
  await expectCompletedLifecycle(page, "traverse");
  expect(await original!.evaluate((element) => element.isConnected)).toBe(false);
  await expect(counter.getByText("Count: 1024", { exact: true })).toBeVisible();
});

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function navigateByLink(page: Page, href: string): Promise<void> {
  await page.evaluate((url) => {
    const link = document.createElement("a");
    link.href = url;
    document.body.append(link);
    link.click();
    link.remove();
  }, href);
}

async function expectIdle(page: Page): Promise<void> {
  await expect(page.locator("body")).not.toHaveAttribute("aria-busy");
  await expect(page.locator("body")).not.toHaveAttribute("data-page-transition");
}

test("waits for article CSS before swapping and restores it without duplicates", async ({
  page,
}) => {
  const documentId = await openNativeTestPage(page, "/about");
  await installArticleFixture(page);

  const cssRequested = deferred();
  const releaseCss = deferred();
  await page.route("**/katex/katex.min.css*", async (route) => {
    cssRequested.resolve();
    await releaseCss.promise;
    await route.continue();
  });

  try {
    await navigateByLink(page, "/blog/e2e-navigation");
    await cssRequested.promise;
    await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
    await expect(page.locator(".katex")).toHaveCount(0);
    expect((await probe(page)).events.map((event) => event.name)).toEqual(["app:navigation-start"]);
    releaseCss.resolve();

    const expectArticle = async () => {
      await expect(page).toHaveTitle(/^Navigation fixture -/);
      await expect(page.locator("article.markdown-body .katex").first()).toHaveCSS(
        "font-family",
        /KaTeX_Main/,
      );
      await expect(page.locator("article.markdown-body pre")).toContainText("print('navigation')");
      await expect(page.locator('link[rel="stylesheet"][href*="katex.min.css"]')).toHaveCount(1);
      await expect(page.locator('link[rel="stylesheet"][href*="styles/markdown.css"]')).toHaveCount(
        1,
      );
      expect((await probe(page)).documentId).toBe(documentId);
      await expectIdle(page);
    };
    await expectCompletedLifecycle(page, "push");
    await expectArticle();

    await clearProbeEvents(page);
    await page.goBack({ waitUntil: "commit" });
    await expectCompletedLifecycle(page, "traverse");
    await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
    await expect(page.locator('link[rel="stylesheet"][href*="katex.min.css"]')).toHaveCount(0);

    await clearProbeEvents(page);
    await page.goForward({ waitUntil: "commit" });
    await expectCompletedLifecycle(page, "traverse");
    await expectArticle();
  } finally {
    releaseCss.resolve();
    await page.unrouteAll({ behavior: "wait" });
  }
});

test("cancels a slow navigation without committing its stale page", async ({ page }) => {
  const aboutPath = "/about?e2e=slow-navigation";
  const documentId = await openNativeTestPage(page);
  const aboutRequested = deferred();
  const releaseAbout = deferred();
  await page.route(
    (url) => url.pathname + url.search === aboutPath,
    async (route) => {
      aboutRequested.resolve();
      await releaseAbout.promise;
      await route.continue();
    },
  );
  const cancelledRequest = page.waitForEvent("requestfailed", {
    predicate: (request) => request.url().endsWith(aboutPath) && request.resourceType() === "fetch",
  });

  try {
    await navigateByLink(page, aboutPath);
    await aboutRequested.promise;
    await navigateByLink(page, "/privacy");
    await cancelledRequest;
    await expect
      .poll(async () => (await probe(page)).events.at(-1))
      .toMatchObject({
        name: "app:navigation-end",
        finalUrl: expect.stringMatching(/\/privacy$/),
        outcome: "completed",
      });
    releaseAbout.resolve();
    await page.unrouteAll({ behavior: "wait" });

    const state = await probe(page);
    const firstId = state.events[0].navigationId;
    expect(state.events.filter((event) => event.navigationId === firstId)).toEqual([
      expect.objectContaining({
        name: "app:navigation-start",
        requestedUrl: expect.stringContaining(aboutPath),
      }),
      expect.objectContaining({ name: "app:navigation-end", outcome: "cancelled" }),
    ]);
    expect(
      state.events.filter((event) => event.navigationId !== firstId).map((event) => event.name),
    ).toEqual([
      "app:navigation-start",
      "app:before-leave",
      "app:before-swap",
      "app:after-swap",
      "app:navigation-end",
    ]);
    expect(state.documentId).toBe(documentId);
    await expect(page).toHaveURL(/\/privacy$/);
    await expect(page).toHaveTitle(/^Privacy -/);
    await expect(page.locator('[data-solid-island="WIP"]')).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "关于我", exact: true })).toHaveCount(0);
    await expectIdle(page);
  } finally {
    releaseAbout.resolve();
    await page.unrouteAll({ behavior: "wait" });
  }
});

test("reloads once when the fetched page has a different build", async ({ page }) => {
  const aboutPath = "/about?e2e=different-build";
  const documentId = await openNativeTestPage(page);
  const requestTypes: string[] = [];
  await page.route(
    (url) => url.pathname + url.search === aboutPath,
    async (route) => {
      const type = route.request().resourceType();
      requestTypes.push(type);
      if (type !== "fetch") {
        await route.continue();
        return;
      }
      const response = await route.fetch();
      const html = await response.text();
      const changed = html.replace(
        /(<meta\b[^>]*name="app-build-id"[^>]*content=")[^"]*(")/,
        "$1e2e-different-build$2",
      );
      expect(changed).not.toBe(html);
      await route.fulfill({ response, body: changed });
    },
  );

  await navigateByLink(page, aboutPath);
  await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
  await expect.poll(async () => (await probe(page)).documentId).not.toBe(documentId);
  await expect(page).toHaveURL(new URL(aboutPath, page.url()).href);
  await expect(page).toHaveTitle(/^About -/);
  expect(requestTypes).toEqual(["fetch", "document"]);
  await expectIdle(page);
});

test("uses same-page anchors without fetching or swapping", async ({ page }) => {
  const documentId = await openNativeTestPage(page, "/about");
  await installArticleFixture(page);
  await navigateByLink(page, "/blog/e2e-navigation");
  await expectCompletedLifecycle(page, "push");
  await clearProbeEvents(page);
  const article = await page.locator("article").elementHandle();
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.resourceType() === "fetch" || request.isNavigationRequest()) {
      requests.push(request.url());
    }
  });

  await navigateByLink(page, "#reading-target");
  await expect(page).toHaveURL(/#reading-target$/);
  await expect(page.getByRole("heading", { name: /Reading target$/ })).toBeInViewport();
  expect(await article!.evaluate((node) => node === document.querySelector("article"))).toBe(true);
  expect((await probe(page)).documentId).toBe(documentId);
  expect((await probe(page)).events).toEqual([]);
  expect(requests).toEqual([]);
  await expectIdle(page);
});

test("positions a cross-page anchor after the body swap", async ({ page }) => {
  const documentId = await openNativeTestPage(page, "/about");
  await installArticleFixture(page);
  await navigateByLink(page, "/blog/e2e-navigation#reading-target");
  await expectCompletedLifecycle(page, "push");
  await expect(page).toHaveURL(/\/blog\/e2e-navigation#reading-target$/);
  await expect(page.getByRole("heading", { name: /Reading target$/ })).toBeInViewport();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(500);
  expect((await probe(page)).documentId).toBe(documentId);
  await expectIdle(page);
});

test("restores article scroll position through back and forward", async ({ page }) => {
  const documentId = await openNativeTestPage(page, "/about");
  await installArticleFixture(page);
  await navigateByLink(page, "/blog/e2e-navigation");
  await expectCompletedLifecycle(page, "push");
  await page.evaluate(async () => {
    await window.navigation.transition?.finished;
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  });
  await page.evaluate(async () => {
    await document.fonts.ready;
    window.scrollTo({ top: 900, behavior: "instant" });
  });
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(900);
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
  await clearProbeEvents(page);
  await navigateByLink(page, "/about");
  await expectCompletedLifecycle(page, "push");
  await page.evaluate(async () => {
    await window.navigation.transition?.finished;
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  });
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);

  await clearProbeEvents(page);
  await page.goBack({ waitUntil: "commit" });
  await expectCompletedLifecycle(page, "traverse");
  await expect.poll(() => page.evaluate(() => Math.abs(window.scrollY - 900))).toBeLessThan(3);
  await clearProbeEvents(page);
  await page.goForward({ waitUntil: "commit" });
  await expectCompletedLifecycle(page, "traverse");
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  expect((await probe(page)).documentId).toBe(documentId);
  await expectIdle(page);
});

test("resets focus after keyboard navigation and keeps Tab navigation usable", async ({ page }) => {
  const documentId = await openNativeTestPage(page);
  const link = page
    .locator(".site-navbar__links")
    .getByRole("link", { name: "About", exact: true });
  await link.focus();
  await expect(link).toBeFocused();
  const original = await link.elementHandle();
  await page.keyboard.press("Enter");
  await expectCompletedLifecycle(page, "push");
  expect(await original!.evaluate((node) => node.isConnected)).toBe(false);
  await expect.poll(() => page.evaluate(() => document.activeElement === document.body)).toBe(true);
  await page.keyboard.press("Tab");
  await expect(page.locator(".site-navbar__inner .site-navbar__brand")).toBeFocused();
  expect((await probe(page)).documentId).toBe(documentId);
  await expectIdle(page);
});

test("reuses a hovered page without a second fetch", async ({ page }) => {
  const aboutPath = "/about?e2e=hover-prefetch";
  const documentId = await openNativeTestPage(page);
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith(aboutPath)) {
      requests.push(request.resourceType());
    }
  });
  await page.evaluate((href) => {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = "Prefetch E2E";
    link.setAttribute("data-nav-prefetch", "");
    document.querySelector("main")!.prepend(link);
  }, aboutPath);
  const link = page.getByRole("link", { name: "Prefetch E2E", exact: true });
  const response = page.waitForResponse((response) => response.url().endsWith(aboutPath));
  await link.hover();
  await (await response).finished();
  await link.click();

  await expectCompletedLifecycle(page, "push");
  await expect(page).toHaveURL(new URL(aboutPath, page.url()).href);
  await expect(page.getByRole("heading", { name: "关于我", exact: true })).toBeVisible();
  expect(requests).toEqual(["fetch"]);
  expect((await probe(page)).documentId).toBe(documentId);
  await expectIdle(page);
});

test("shows expired prefetch content before updating it in the same document", async ({ page }) => {
  const aboutPath = "/about?e2e=stale-prefetch";
  const documentId = await openNativeTestPage(page);
  const initialTime = Date.now();
  await page.clock.setFixedTime(initialTime);
  let requests = 0;
  const refreshRequested = deferred();
  const releaseRefresh = deferred();
  await page.route(
    (url) => url.pathname + url.search === aboutPath,
    async (route) => {
      requests++;
      const version = requests === 1 ? "cached" : "refreshed";
      if (version === "refreshed") {
        refreshRequested.resolve();
        await releaseRefresh.promise;
      }
      const response = await route.fetch();
      const html = await response.text();
      await route.fulfill({
        response,
        body: html.replace("</body>", `<div id="prefetch-version">${version}</div></body>`),
      });
    },
  );

  try {
    await page.evaluate((href) => {
      const link = document.createElement("a");
      link.href = href;
      link.textContent = "Stale prefetch E2E";
      link.setAttribute("data-nav-prefetch", "");
      document.querySelector("main")!.prepend(link);
    }, aboutPath);
    const response = page.waitForResponse((response) => response.url().endsWith(aboutPath));
    const link = page.getByRole("link", { name: "Stale prefetch E2E", exact: true });
    await link.hover();
    await (await response).finished();
    await page.clock.setFixedTime(initialTime + 31_000);
    await link.evaluate((element: HTMLAnchorElement) => element.click());
    await expectCompletedLifecycle(page, "push");
    await refreshRequested.promise;
    await expect(page.locator("#prefetch-version")).toHaveText("cached");
    await expectIdle(page);
    const historyLength = await page.evaluate(() => history.length);

    releaseRefresh.resolve();
    await expect(page.locator("#prefetch-version")).toHaveText("refreshed");
    await expectIdle(page);
    expect(requests).toBe(2);
    expect(await page.evaluate(() => history.length)).toBe(historyLength);
    await expect(page).toHaveURL(new URL(aboutPath, page.url()).href);
    const state = await probe(page);
    expect(state.documentId).toBe(documentId);
    expect(state.events.filter((event) => event.name === "app:navigation-end")).toHaveLength(1);
    expect(state.events.slice(-2)).toMatchObject([
      { name: "app:before-swap", reason: "revalidation" },
      { name: "app:after-swap", reason: "revalidation" },
    ]);
  } finally {
    releaseRefresh.resolve();
    await page.unrouteAll({ behavior: "wait" });
  }
});
