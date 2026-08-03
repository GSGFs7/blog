import { describe, expect, test } from "vitest";

import {
  isPageNavigationSource,
  isPageNavigationUrl,
  shouldInterceptNavigation,
} from "./route-policy";

const ORIGIN = "https://example.com";
const CURRENT_URL = new URL(`${ORIGIN}/current`);

function sourceFrom(html: string): Element {
  const template = document.createElement("template");
  template.innerHTML = html;
  return template.content.querySelector("[data-source]")!;
}

interface NavigateEventOptions {
  canIntercept: boolean;
  defaultPrevented: boolean;
  hashChange: boolean;
  downloadRequest: string | null;
  formData: FormData | null;
  navigationType: NavigationType;
  sourceElement: Element | null;
  destinationUrl: string;
}

function navigateEvent(overrides: Partial<NavigateEventOptions> = {}): NavigateEvent {
  const options: NavigateEventOptions = {
    canIntercept: true,
    defaultPrevented: false,
    hashChange: false,
    downloadRequest: null,
    formData: null,
    navigationType: "push",
    sourceElement: null,
    destinationUrl: `${ORIGIN}/about`,
    ...overrides,
  };

  return {
    canIntercept: options.canIntercept,
    defaultPrevented: options.defaultPrevented,
    hashChange: options.hashChange,
    downloadRequest: options.downloadRequest,
    formData: options.formData,
    navigationType: options.navigationType,
    sourceElement: options.sourceElement,
    destination: { url: options.destinationUrl },
  } as unknown as NavigateEvent;
}

describe("isPageNavigationUrl", () => {
  test.each([
    "/",
    "/about",
    "/about/",
    "/blog/post-slug",
    "/blog/123/comments",
    "/search?q=django#results",
  ])("allows a regular same-origin page URL: %s", (path) => {
    expect(isPageNavigationUrl(new URL(path, ORIGIN), ORIGIN)).toBe(true);
  });

  test("rejects non-HTTP and cross-origin URLs", () => {
    expect(isPageNavigationUrl(new URL("ftp://example.com/file"), "ftp://example.com")).toBe(false);
    expect(isPageNavigationUrl(new URL("https://other.example/about"), ORIGIN)).toBe(false);
    expect(isPageNavigationUrl(new URL("http://example.com/about"), ORIGIN)).toBe(false);
  });

  test.each([
    "/blog/feed.atom",
    "/blog/latest",
    "/blog/random",
    "/favicon.ico",
    "/llms.txt",
    "/login",
    "/robots.txt",
    "/sitemap.xml",
    "/test",
    "/user",
  ])("requires a full reload for an exact path: %s", (path) => {
    expect(isPageNavigationUrl(new URL(path, ORIGIN), ORIGIN)).toBe(false);
    expect(isPageNavigationUrl(new URL(`${path}/`, ORIGIN), ORIGIN)).toBe(false);
  });

  test.each(["/account/settings", "/api/posts", "/not-admin/login", "/prometheus/metrics"])(
    "requires a full reload below a reserved prefix: %s",
    (path) => {
      expect(isPageNavigationUrl(new URL(path, ORIGIN), ORIGIN)).toBe(false);
    },
  );

  test.each(["/blog/1", "/blog/123/", "/feed.atom", "/post/readme.md/"])(
    "requires a full reload for an excluded page shape: %s",
    (path) => {
      expect(isPageNavigationUrl(new URL(path, ORIGIN), ORIGIN)).toBe(false);
    },
  );
});

describe("isPageNavigationSource", () => {
  test("allows navigations without a source element", () => {
    expect(isPageNavigationSource(null)).toBe(true);
  });

  test.each([
    "<span data-nav-ignore><button data-source></button></span>",
    "<span data-nav-reload><button data-source></button></span>",
    "<div contenteditable><span data-source></span></div>",
    "<form><button data-source></button></form>",
  ])("rejects a source in an excluded context", (html) => {
    expect(isPageNavigationSource(sourceFrom(html))).toBe(false);
  });

  test.each([
    "<button data-source></button>",
    '<div contenteditable="false"><span data-source></span></div>',
    '<a href="/about"><span data-source></span></a>',
    '<a href="/file" download target="_self"><span data-source></span></a>',
  ])("allows a source in a page-navigation context", (html) => {
    expect(isPageNavigationSource(sourceFrom(html))).toBe(true);
  });

  test.each([
    '<a href="/file" download target="_blank"><span data-source></span></a>',
    '<a href="/file" download rel="nofollow external"><span data-source></span></a>',
    '<map><area href="/file" download target="named-frame" data-source></map>',
  ])("rejects a download source that leaves the current context", (html) => {
    expect(isPageNavigationSource(sourceFrom(html))).toBe(false);
  });
});

describe("shouldInterceptNavigation", () => {
  test("intercepts an eligible same-origin page navigation", () => {
    expect(shouldInterceptNavigation(navigateEvent(), CURRENT_URL)).toBe(true);
  });

  test.each([
    ["cannot be intercepted", { canIntercept: false }],
    ["was prevented", { defaultPrevented: true }],
    ["only changes the hash", { hashChange: true }],
    ["is a download", { downloadRequest: "article.pdf" }],
    ["submits form data", { formData: new FormData() }],
    ["reloads the document", { navigationType: "reload" as const }],
    [
      "comes from an excluded element",
      { sourceElement: sourceFrom("<span data-nav-reload data-source></span>") },
    ],
  ])("does not intercept a navigation that %s", (_name, overrides) => {
    expect(shouldInterceptNavigation(navigateEvent(overrides), CURRENT_URL)).toBe(false);
  });

  test.each([
    "https://other.example/about",
    `${ORIGIN}/login`,
    `${ORIGIN}/blog/123`,
    `${ORIGIN}/article.md`,
  ])("does not intercept an ineligible destination: %s", (destinationUrl) => {
    expect(shouldInterceptNavigation(navigateEvent({ destinationUrl }), CURRENT_URL)).toBe(false);
  });
});
