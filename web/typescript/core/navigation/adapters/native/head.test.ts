import { JSDOM } from "jsdom";
import { expect, test } from "vitest";

import { PageHeadError, preparePageHead, type PreparePageHeadOptions } from "./head";

const CURRENT_URL = new URL("https://example.com/post/1");
const NEXT_URL = new URL("https://example.com/about/");

function documentWithHead(headHtml: string): Document {
  return new DOMParser().parseFromString(
    `<!doctype html><html><head>${headHtml}</head><body class="site-body"></body></html>`,
    "text/html",
  );
}

function liveDocumentWithHead(headHtml: string): Document {
  return new JSDOM(
    `<!doctype html><html><head>${headHtml}</head><body class="site-body"></body></html>`,
    { runScripts: "dangerously" },
  ).window.document;
}

const CURRENT_HEAD = `
  <title>Current Page</title>
  <meta name="app-dynamic-head-start">
  <meta name="description" content="current description">
  <link rel="stylesheet" href="https://example.com/css/shared.css">
  <script>window.__oldScriptRan = true;</script>
  <meta name="app-dynamic-head-end">
`;

const SHARED_STYLESHEET = '<link rel="stylesheet" href="https://example.com/css/shared.css">';

function harness(
  nextHead: string,
  currentHead: string = CURRENT_HEAD,
): {
  currentDocument: Document;
  nextDocument: Document;
  controller: AbortController;
  options: PreparePageHeadOptions;
} {
  const currentDocument = liveDocumentWithHead(currentHead);
  const nextDocument = documentWithHead(nextHead);
  const controller = new AbortController();
  return {
    currentDocument,
    nextDocument,
    controller,
    options: {
      signal: controller.signal,
      currentUrl: CURRENT_URL,
      nextUrl: NEXT_URL,
      stylesheetTimeoutMs: 100,
    },
  };
}

function loadStylesheet(document: Document, href: string): void {
  document.head
    .querySelectorAll<HTMLLinkElement>(`link[href="${href}"]`)
    .forEach((link) => link.dispatchEvent(new Event("load")));
}

test("throws when the current document has no dynamic head range", async () => {
  const currentDocument = documentWithHead("<title>No Markers</title>");
  const nextDocument = documentWithHead(CURRENT_HEAD);
  const controller = new AbortController();

  const error = await preparePageHead(currentDocument, nextDocument, {
    signal: controller.signal,
    currentUrl: CURRENT_URL,
    nextUrl: NEXT_URL,
  }).catch((e) => e);

  expect(error).toBeInstanceOf(PageHeadError);
});

test("throws when the next document has no dynamic head range", async () => {
  const { currentDocument, controller } = harness("");
  const nextDocument = documentWithHead("<title>No Markers</title>");

  const error = await preparePageHead(currentDocument, nextDocument, {
    signal: controller.signal,
    currentUrl: CURRENT_URL,
    nextUrl: NEXT_URL,
  }).catch((e) => e);

  expect(error).toBeInstanceOf(PageHeadError);
});

test("commit replaces the dynamic head and keeps identical stylesheets", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <meta name="description" content="next description">
    ${SHARED_STYLESHEET}
    <link rel="stylesheet" href="https://example.com/css/new.css">
    <meta name="app-dynamic-head-end">
  `);

  const pending = preparePageHead(currentDocument, nextDocument, options);
  loadStylesheet(currentDocument, "https://example.com/css/new.css");
  const prepared = await pending;

  expect(currentDocument.head.querySelectorAll('meta[name="description"]')).toHaveLength(1);
  expect(
    currentDocument.head.querySelector<HTMLMetaElement>('meta[name="description"]')?.content,
  ).toBe("current description");
  expect(
    currentDocument.head.querySelector('link[href="https://example.com/css/new.css"]'),
  ).not.toBeNull();

  prepared.commit();

  const descriptions = currentDocument.head.querySelectorAll<HTMLMetaElement>(
    'meta[name="description"]',
  );
  expect(descriptions).toHaveLength(1);
  expect(descriptions[0].content).toBe("next description");
  expect(
    currentDocument.head.querySelectorAll('link[href="https://example.com/css/shared.css"]'),
  ).toHaveLength(1);
  expect(
    currentDocument.head.querySelectorAll('link[href="https://example.com/css/new.css"]'),
  ).toHaveLength(1);
  expect(currentDocument.head.querySelector("title")?.textContent).toBe("Next Page");
  expect(currentDocument.head.querySelectorAll('meta[name="app-dynamic-head-start"]')).toHaveLength(
    1,
  );
  expect(currentDocument.head.querySelectorAll('meta[name="app-dynamic-head-end"]')).toHaveLength(
    1,
  );
});

test("rollback leaves the current head untouched", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <meta name="description" content="next description">
    <link rel="stylesheet" href="https://example.com/css/new.css">
    <meta name="app-dynamic-head-end">
  `);

  const pending = preparePageHead(currentDocument, nextDocument, options);
  loadStylesheet(currentDocument, "https://example.com/css/new.css");
  const prepared = await pending;

  prepared.rollback();

  expect(
    currentDocument.head.querySelector<HTMLMetaElement>('meta[name="description"]')?.content,
  ).toBe("current description");
  expect(
    currentDocument.head.querySelectorAll('link[href="https://example.com/css/new.css"]'),
  ).toHaveLength(0);
  expect(currentDocument.head.querySelector("title")?.textContent).toBe("Current Page");
  expect(
    currentDocument.head.querySelectorAll('link[href="https://example.com/css/shared.css"]'),
  ).toHaveLength(1);
});

test("reuses an already-loaded stylesheet without waiting", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    ${SHARED_STYLESHEET}
    <meta name="app-dynamic-head-end">
  `);

  const prepared = await preparePageHead(currentDocument, nextDocument, options);

  prepared.commit();

  expect(
    currentDocument.head.querySelectorAll('link[href="https://example.com/css/shared.css"]'),
  ).toHaveLength(1);
});

test("preserves duplicate stylesheets required by the next page", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    ${SHARED_STYLESHEET}
    ${SHARED_STYLESHEET}
    <meta name="app-dynamic-head-end">
  `);

  const pending = preparePageHead(currentDocument, nextDocument, options);
  loadStylesheet(currentDocument, "https://example.com/css/shared.css");
  const prepared = await pending;

  prepared.commit();

  expect(
    currentDocument.head.querySelectorAll('link[href="https://example.com/css/shared.css"]'),
  ).toHaveLength(2);
});

test("resolves relative stylesheet hrefs against the next URL", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <link rel="stylesheet" href="css/page.css">
    <meta name="app-dynamic-head-end">
  `);

  const pending = preparePageHead(currentDocument, nextDocument, options);
  loadStylesheet(currentDocument, "https://example.com/about/css/page.css");
  await pending;

  expect(
    currentDocument.head.querySelector('link[href="https://example.com/about/css/page.css"]'),
  ).not.toBeNull();
});

test("rejects when a stylesheet times out and removes the inserted link", async () => {
  const { currentDocument, nextDocument, controller } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <link rel="stylesheet" href="https://example.com/css/slow.css">
    <meta name="app-dynamic-head-end">
  `);

  const error = await preparePageHead(currentDocument, nextDocument, {
    signal: controller.signal,
    currentUrl: CURRENT_URL,
    nextUrl: NEXT_URL,
    stylesheetTimeoutMs: 20,
  }).catch((e) => e);

  expect(error).toBeInstanceOf(PageHeadError);
  expect(
    currentDocument.head.querySelector('link[href="https://example.com/css/slow.css"]'),
  ).toBeNull();
  expect(
    currentDocument.head.querySelector<HTMLMetaElement>('meta[name="description"]')?.content,
  ).toBe("current description");
  expect(
    currentDocument.head.querySelectorAll('link[href="https://example.com/css/shared.css"]'),
  ).toHaveLength(1);
});

test("rejects with the abort reason and removes the inserted link", async () => {
  const { currentDocument, nextDocument, controller, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <link rel="stylesheet" href="https://example.com/css/slow.css">
    <meta name="app-dynamic-head-end">
  `);

  const pending = preparePageHead(currentDocument, nextDocument, options);
  controller.abort();

  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  expect(
    currentDocument.head.querySelector('link[href="https://example.com/css/slow.css"]'),
  ).toBeNull();
});

test("does not execute new scripts and removes old script nodes", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <script>window.__dynamicScriptRan = true;</script>
    <meta name="app-dynamic-head-end">
  `);
  const view = currentDocument.defaultView as unknown as { __dynamicScriptRan?: boolean };

  const prepared = await preparePageHead(currentDocument, nextDocument, options);

  expect(view.__dynamicScriptRan).toBeUndefined();

  prepared.commit();

  expect(view.__dynamicScriptRan).toBeUndefined();
  expect(currentDocument.head.textContent).not.toContain("__dynamicScriptRan");
  expect(currentDocument.head.textContent).not.toContain("__oldScriptRan");
});

test("does not re-execute a script that already exists", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <script>window.__scriptRuns = (window.__scriptRuns ?? 0) + 1;</script>
    <meta name="app-dynamic-head-end">
  `);
  const view = currentDocument.defaultView as unknown as { __scriptRuns?: number };

  const script = currentDocument.createElement("script");
  script.textContent = "window.__scriptRuns = (window.__scriptRuns ?? 0) + 1;";
  currentDocument.head.querySelector('meta[name="app-dynamic-head-end"]')!.before(script);
  expect(view.__scriptRuns).toBe(1);

  const prepared = await preparePageHead(currentDocument, nextDocument, options);
  prepared.commit();

  expect(view.__scriptRuns).toBe(1);
  expect(currentDocument.head.textContent).not.toContain("__scriptRuns");
});

test("moves JSON-LD data without executing it", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <script type="application/ld+json">{"@type": "BreadcrumbList"}</script>
    <meta name="app-dynamic-head-end">
  `);

  const prepared = await preparePageHead(currentDocument, nextDocument, options);

  expect(currentDocument.head.querySelector('script[type="application/ld+json"]')).toBeNull();

  prepared.commit();

  const jsonLd = currentDocument.head.querySelector('script[type="application/ld+json"]');
  expect(jsonLd?.textContent).toBe('{"@type": "BreadcrumbList"}');
});

test("commit is idempotent and rollback is a no-op after commit", async () => {
  const { currentDocument, nextDocument, options } = harness(`
    <title>Next Page</title>
    <meta name="app-dynamic-head-start">
    <meta name="description" content="next description">
    <meta name="app-dynamic-head-end">
  `);

  const prepared = await preparePageHead(currentDocument, nextDocument, options);
  prepared.commit();
  prepared.commit();
  prepared.rollback();

  expect(
    currentDocument.head.querySelector<HTMLMetaElement>('meta[name="description"]')?.content,
  ).toBe("next description");
  expect(currentDocument.head.querySelector("title")?.textContent).toBe("Next Page");
});
