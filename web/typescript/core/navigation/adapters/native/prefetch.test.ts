import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { type FetchedPage, page, type PageLoadResult } from "./page";
import { setupNativePrefetch } from "./prefetch";

vi.mock("./page", () => ({ page: vi.fn() }));

let teardown: (() => void) | undefined;

beforeEach(() => {
  vi.mocked(page).mockReset();
  document.head.innerHTML = `
    <meta name="app-navigation-version" content="1">
    <meta name="app-build-id" content="test-build">
  `;
  document.body.innerHTML = "";
});

afterEach(() => {
  teardown?.();
  vi.restoreAllMocks();
  vi.useRealTimers();
  document.head.innerHTML = "";
  document.body.innerHTML = "";
});

function fetchedPage(html = "<main>About</main>"): FetchedPage {
  return {
    requestedUrl: new URL("/about", window.location.origin),
    finalUrl: new URL("/about", window.location.origin),
    document: new DOMParser().parseFromString(html, "text/html"),
    response: new Response(""),
    deliverySource: "origin",
    html,
  };
}

test("retains a pending prefetch after consumption and restores each navigation hash", async () => {
  let resolve!: (result: PageLoadResult) => void;
  vi.mocked(page).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const prefetch = setupNativePrefetch(document);
  teardown = prefetch.dispose;
  const url = new URL("/about#first", window.location.origin);
  const request = prefetch.refresh(url);
  const first = prefetch.take(url, new AbortController().signal);
  resolve({ kind: "swap", page: fetchedPage() });
  await request;
  expect((await first)?.page.finalUrl.hash).toBe("#first");

  url.hash = "#second";
  const second = await prefetch.take(url, new AbortController().signal);
  expect(second?.page.finalUrl.hash).toBe("#second");
  expect(second?.page.requestedUrl.hash).toBe("#second");
  expect(second?.stale).toBe(false);
  expect(page).toHaveBeenCalledOnce();
});

test("deduplicates refresh requests and renews stale cache even when HTML is unchanged", async () => {
  const now = vi.spyOn(Date, "now").mockReturnValue(1000);
  vi.mocked(page).mockResolvedValue({ kind: "swap", page: fetchedPage() });
  const prefetch = setupNativePrefetch(document);
  teardown = prefetch.dispose;
  const url = new URL("/about", window.location.origin);
  await prefetch.refresh(url);
  now.mockReturnValue(31000);
  expect((await prefetch.take(url, new AbortController().signal))?.stale).toBe(true);

  await Promise.all([prefetch.refresh(url), prefetch.refresh(url)]);

  expect(page).toHaveBeenCalledTimes(2);
  expect((await prefetch.take(url, new AbortController().signal))?.stale).toBe(false);
});

test("cancels one consumer without aborting the shared prefetch", async () => {
  let resolve!: (result: PageLoadResult) => void;
  vi.mocked(page).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const prefetch = setupNativePrefetch(document);
  teardown = prefetch.dispose;
  const url = new URL("/about", window.location.origin);
  const request = prefetch.refresh(url);
  const consumer = new AbortController();
  const hit = prefetch.take(url, consumer.signal);
  const rejected = expect(hit).rejects.toMatchObject({ name: "AbortError" });
  consumer.abort();
  await rejected;
  expect(vi.mocked(page).mock.calls[0][1].signal.aborted).toBe(false);

  resolve({ kind: "swap", page: fetchedPage() });
  await request;
  expect(await prefetch.take(url, new AbortController().signal)).toBeDefined();
});

test("keeps cached content on request failure and evicts invalid refreshed pages", async () => {
  vi.mocked(page)
    .mockResolvedValueOnce({ kind: "swap", page: fetchedPage() })
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({
      kind: "reload",
      url: new URL("/about", window.location.origin),
      reason: "protocol",
    });
  const prefetch = setupNativePrefetch(document);
  teardown = prefetch.dispose;
  const url = new URL("/about", window.location.origin);
  await prefetch.refresh(url);
  await expect(prefetch.refresh(url)).rejects.toThrow("offline");
  expect(await prefetch.take(url, new AbortController().signal)).toBeDefined();
  await prefetch.refresh(url);
  expect(await prefetch.take(url, new AbortController().signal)).toBeUndefined();
});

test("delays hover prefetch and cancels it when the pointer leaves", async () => {
  vi.useFakeTimers();
  vi.mocked(page).mockResolvedValue({ kind: "swap", page: fetchedPage() });
  document.body.innerHTML = '<a href="/about" data-nav-prefetch>About</a>';
  const prefetch = setupNativePrefetch(document);
  teardown = prefetch.dispose;
  const anchor = document.querySelector("a")!;
  const hover = () => {
    const event = new MouseEvent("pointerover", { bubbles: true });
    Object.defineProperty(event, "pointerType", { value: "mouse" });
    anchor.dispatchEvent(event);
  };
  hover();
  await vi.advanceTimersByTimeAsync(99);
  expect(page).not.toHaveBeenCalled();
  anchor.dispatchEvent(new MouseEvent("pointerout", { bubbles: true }));
  await vi.advanceTimersByTimeAsync(1);
  expect(page).not.toHaveBeenCalled();

  hover();
  await vi.advanceTimersByTimeAsync(100);
  expect(page).toHaveBeenCalledOnce();
  anchor.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
  expect(page).toHaveBeenCalledOnce();
});

test("disposal aborts requests and prevents late cache writes", async () => {
  let resolve!: (result: PageLoadResult) => void;
  vi.mocked(page).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const prefetch = setupNativePrefetch(document);
  const url = new URL("/about", window.location.origin);
  const request = prefetch.refresh(url);
  const rejected = expect(request).rejects.toMatchObject({ name: "AbortError" });
  prefetch.dispose();
  expect(vi.mocked(page).mock.calls[0][1].signal.aborted).toBe(true);
  resolve({ kind: "swap", page: fetchedPage() });
  await rejected;
  await expect(prefetch.take(url, new AbortController().signal)).rejects.toMatchObject({
    name: "AbortError",
  });
});

test.each(["pending", "fresh", "stale"])(
  "returns a consistent prefetch hit for a %s page",
  async (state) => {
    const now = vi.spyOn(Date, "now").mockReturnValue(1000);
    const requestedUrl = new URL("/about#intro", window.location.origin);
    const fetchedPage: FetchedPage = {
      requestedUrl: new URL("/about", window.location.origin),
      finalUrl: new URL("/about", window.location.origin),
      document: new DOMParser().parseFromString("<main>About</main>", "text/html"),
      response: new Response(""),
      deliverySource: "origin",
      html: "<main>About</main>",
    };
    vi.mocked(page).mockResolvedValueOnce({ kind: "swap", page: fetchedPage });
    const prefetch = setupNativePrefetch(document);
    teardown = prefetch.dispose;
    const refresh = prefetch.refresh(requestedUrl);
    if (state !== "pending") {
      await refresh;
    }
    if (state === "stale") {
      now.mockReturnValue(31000);
    }

    const hit = await prefetch.take(requestedUrl, new AbortController().signal);

    expect(hit).toEqual({
      page: { ...fetchedPage, requestedUrl, finalUrl: requestedUrl },
      stale: state === "stale",
    });
    await refresh;
  },
);

test("prefetches an eligible focused link using the page protocol", () => {
  document.body.innerHTML = '<a href="/about#intro" data-nav-prefetch>About</a>';
  teardown = setupNativePrefetch(document).dispose;

  document.querySelector("a")!.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));

  expect(page).toHaveBeenCalledExactlyOnceWith(new URL("/about", window.location.origin), {
    signal: expect.any(AbortSignal),
    expectedOrigin: window.location.origin,
    currentProtocol: { navigationVersion: "1", buildId: "test-build" },
  });
});

test.each([
  "download",
  'target="_blank"',
  'rel="nofollow EXTERNAL"',
  "data-nav-ignore",
  "data-nav-reload",
  'data-nav-prefetch="false"',
])("does not prefetch an ineligible focused link: %s", (attributes) => {
  document.body.innerHTML = `<a href="/about" ${attributes}>About</a>`;
  const anchor = document.querySelector("a")!;
  if (!anchor.hasAttribute("data-nav-prefetch")) {
    anchor.setAttribute("data-nav-prefetch", "");
  }
  teardown = setupNativePrefetch(document).dispose;

  anchor.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));

  expect(page).not.toHaveBeenCalled();
});

test("prefetches load-strategy links immediately when the page is already loaded", () => {
  vi.mocked(page).mockResolvedValue({ kind: "swap", page: fetchedPage() });
  document.body.innerHTML = '<a href="/about" data-nav-prefetch="load">About</a>';
  teardown = setupNativePrefetch(document).dispose;

  expect(page).toHaveBeenCalledOnce();
});

test("prefetches load-strategy links after the page load event", () => {
  vi.mocked(page).mockResolvedValue({ kind: "swap", page: fetchedPage() });
  vi.spyOn(document, "readyState", "get").mockReturnValue("loading");
  document.body.innerHTML = '<a href="/about" data-nav-prefetch="load">About</a>';
  teardown = setupNativePrefetch(document).dispose;
  expect(page).not.toHaveBeenCalled();

  window.dispatchEvent(new Event("load"));

  expect(page).toHaveBeenCalledOnce();
});

test("prefetches viewport-strategy links when they intersect and stops observing", () => {
  vi.mocked(page).mockResolvedValue({ kind: "swap", page: fetchedPage() });
  const observed: Element[] = [];
  const unobserved: Element[] = [];
  let trigger: (entries: IntersectionObserverEntry[]) => void = () => undefined;
  class FakeIntersectionObserver {
    constructor(callback: IntersectionObserverCallback) {
      trigger = callback as unknown as (entries: IntersectionObserverEntry[]) => void;
    }
    observe(target: Element) {
      observed.push(target);
    }
    unobserve(target: Element) {
      unobserved.push(target);
    }
    disconnect() {}
  }
  Object.defineProperty(window, "IntersectionObserver", {
    value: FakeIntersectionObserver,
    configurable: true,
  });
  document.body.innerHTML = '<a href="/about" data-nav-prefetch="viewport">About</a>';
  const anchor = document.querySelector("a")!;

  try {
    teardown = setupNativePrefetch(document).dispose;
    expect(observed).toEqual([anchor]);
    expect(page).not.toHaveBeenCalled();

    trigger([{ target: anchor, isIntersecting: true } as unknown as IntersectionObserverEntry]);

    expect(unobserved).toEqual([anchor]);
    expect(page).toHaveBeenCalledOnce();
  } finally {
    delete (window as { IntersectionObserver?: unknown }).IntersectionObserver;
  }
});
