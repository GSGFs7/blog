import { expect, test, vi } from "vitest";

import { createPageCache } from "./cache";
import type { FetchedPage, PageLoadResult } from "./page";

function fetchedPage(path = "/about"): FetchedPage {
  const url = new URL(path, window.location.origin);
  const document = new DOMParser().parseFromString(
    `<!doctype html><html><head><title>About</title></head><body>${path}</body></html>`,
    "text/html",
  );
  return {
    requestedUrl: url,
    finalUrl: url,
    document,
    response: new Response(""),
    deliverySource: "origin",
    html: document.documentElement.outerHTML,
  };
}

function swapped(path = "/about"): PageLoadResult {
  return { kind: "swap", page: fetchedPage(path) };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, failed) => {
    resolve = done;
    reject = failed;
  });
  return { promise, resolve, reject };
}

test("caches a fresh page and restores the consumer hash", async () => {
  const loadPage = vi.fn(async (url: URL) => swapped(url.pathname));
  const cache = createPageCache({ loadPage, now: () => 1000 });

  await cache.refresh(new URL("/about", window.location.origin));
  const hit = await cache.take(
    new URL("/about#intro", window.location.origin),
    new AbortController().signal,
  );

  expect(loadPage).toHaveBeenCalledOnce();
  expect(loadPage.mock.calls[0][0].hash).toBe("");
  expect(hit).toMatchObject({ stale: false });
  expect(hit?.page.finalUrl.hash).toBe("#intro");
  expect(hit?.page.requestedUrl.hash).toBe("#intro");
});

test("reports stale entries and renews them on refresh", async () => {
  let now = 1000;
  const loadPage = vi.fn(async () => swapped());
  const cache = createPageCache({ loadPage, now: () => now, ttl: 1000 });
  const url = new URL("/about", window.location.origin);

  await cache.refresh(url);
  now = 2000;

  expect((await cache.take(url, new AbortController().signal))?.stale).toBe(true);

  await cache.refresh(url);

  expect(loadPage).toHaveBeenCalledTimes(2);
  expect((await cache.take(url, new AbortController().signal))?.stale).toBe(false);
});

test("uses a clock installed after the cache was created", async () => {
  const cache = createPageCache({ loadPage: async () => swapped(), ttl: 1000 });
  const url = new URL("/about", window.location.origin);
  vi.useFakeTimers();
  try {
    vi.setSystemTime(1000);
    await cache.refresh(url);
    vi.setSystemTime(2000);

    expect((await cache.take(url, new AbortController().signal))?.stale).toBe(true);
  } finally {
    cache.dispose();
    vi.useRealTimers();
  }
});

test("deduplicates prefetch and skips a fresh entry", async () => {
  const pending = deferred<PageLoadResult>();
  const loadPage = vi.fn(() => pending.promise);
  const cache = createPageCache({ loadPage, now: () => 1000 });
  const url = new URL("/about", window.location.origin);

  const first = cache.prefetch(url);
  const second = cache.prefetch(url);
  expect(loadPage).toHaveBeenCalledOnce();

  pending.resolve(swapped());
  await Promise.all([first, second]);

  await cache.prefetch(url);
  expect(loadPage).toHaveBeenCalledOnce();
});

test("removes the cached entry when a refresh is not a page swap", async () => {
  const loadPage = vi
    .fn<() => Promise<PageLoadResult>>()
    .mockResolvedValueOnce(swapped())
    .mockResolvedValueOnce({
      kind: "reload",
      url: new URL("/about", window.location.origin),
      reason: "protocol",
    });
  const cache = createPageCache({ loadPage, now: () => 1000 });
  const url = new URL("/about", window.location.origin);

  await cache.refresh(url);
  await cache.refresh(url);

  expect(await cache.take(url, new AbortController().signal)).toBeUndefined();
});

test("cancels one consumer without aborting the shared request", async () => {
  const pending = deferred<PageLoadResult>();
  const loadPage = vi.fn((_url: URL, _signal: AbortSignal) => pending.promise);
  const cache = createPageCache({ loadPage });
  const url = new URL("/about", window.location.origin);

  const refresh = cache.refresh(url);
  const consumer = new AbortController();
  const hit = cache.take(url, consumer.signal);
  const rejected = expect(hit).rejects.toMatchObject({ name: "AbortError" });
  consumer.abort();
  await rejected;
  expect(loadPage.mock.calls[0][1].aborted).toBe(false);

  pending.resolve(swapped());
  await refresh;

  expect(await cache.take(url, new AbortController().signal)).toBeDefined();
});

test("disposal aborts in-flight requests and rejects later consumers", async () => {
  const pending = deferred<PageLoadResult>();
  const loadPage = vi.fn((_url: URL, _signal: AbortSignal) => pending.promise);
  const cache = createPageCache({ loadPage });
  const url = new URL("/about", window.location.origin);

  const refresh = cache.refresh(url);
  cache.dispose();

  expect(loadPage.mock.calls[0][1].aborted).toBe(true);
  await expect(cache.take(url, new AbortController().signal)).rejects.toMatchObject({
    name: "AbortError",
  });

  pending.resolve(swapped());
  await expect(refresh).rejects.toMatchObject({ name: "AbortError" });
});
