import type { FetchedPage, PageLoadResult } from "./page";

const DEFAULT_TTL = 30_000; // ms

interface CacheEntry {
  page: FetchedPage;
  expiresAt: number;
}

export interface PageCacheHit {
  page: FetchedPage;
  stale: boolean;
}

export interface PageCacheOptions {
  loadPage(url: URL, signal: AbortSignal): Promise<PageLoadResult>;
  now?: () => number;
  ttl?: number;
}

export interface PageCache {
  prefetch(url: URL): Promise<void>;
  refresh(url: URL): Promise<PageLoadResult>;
  take(url: URL, signal: AbortSignal): Promise<PageCacheHit | undefined>;
  dispose(): void;
}

function cacheKey(url: URL): string {
  const key = new URL(url);
  key.hash = "";
  return key.href;
}

function restoreHash(url: URL, hash: string): URL {
  const next = new URL(url);
  next.hash = hash;
  return next;
}

// store caches & return cache control closure
export function createPageCache({
  loadPage,
  now = () => Date.now(),
  ttl = DEFAULT_TTL,
}: PageCacheOptions): PageCache {
  const controller = new AbortController();
  const pending = new Map<string, Promise<PageLoadResult>>();
  const entries = new Map<string, CacheEntry>();

  const request = (url: URL): Promise<PageLoadResult> => {
    controller.signal.throwIfAborted();

    const key = cacheKey(url);
    const existing = pending.get(key);
    if (existing) {
      return existing;
    }

    const promise = loadPage(new URL(key), controller.signal)
      .then((result) => {
        controller.signal.throwIfAborted();

        if (result.kind === "swap") {
          entries.set(key, { page: result.page, expiresAt: now() + ttl });
        } else {
          entries.delete(key);
        }

        return result;
      })
      .finally(() => {
        pending.delete(key);
      });

    pending.set(key, promise);
    return promise;
  };

  const prefetch = async (url: URL): Promise<void> => {
    if (controller.signal.aborted) {
      return;
    }

    const key = cacheKey(url);
    if (pending.has(key)) {
      return;
    }

    const entry = entries.get(key);
    if (entry && entry.expiresAt > now()) {
      return;
    }

    try {
      await request(url);
    } catch {}
  };

  const take = async (url: URL, signal: AbortSignal): Promise<PageCacheHit | undefined> => {
    signal.throwIfAborted();
    controller.signal.throwIfAborted();

    const key = cacheKey(url);
    const entry = entries.get(key);
    if (entry) {
      return {
        page: {
          ...entry.page,
          requestedUrl: new URL(url),
          finalUrl: restoreHash(entry.page.finalUrl, url.hash),
        },
        stale: entry.expiresAt <= now(),
      };
    }

    const promise = pending.get(key);
    if (!promise) {
      return;
    }

    let onAbort: () => void = () => undefined;
    const aborted = new Promise<never>((_, reject) => {
      onAbort = () => reject(signal.reason);
      signal.addEventListener("abort", onAbort, { once: true });
    });

    let fetchedPage: FetchedPage | undefined;
    try {
      const result = await Promise.race([promise, aborted]);
      if (result.kind === "swap") {
        fetchedPage = result.page;
      }
    } catch {
      signal.throwIfAborted();
      return;
    } finally {
      signal.removeEventListener("abort", onAbort);
    }

    signal.throwIfAborted();
    if (!fetchedPage) {
      return;
    }

    return {
      page: {
        ...fetchedPage,
        requestedUrl: new URL(url),
        finalUrl: restoreHash(fetchedPage.finalUrl, url.hash),
      },
      stale: false,
    };
  };

  const dispose = (): void => {
    controller.abort();
    pending.clear();
    entries.clear();
  };

  return { prefetch, refresh: request, take, dispose };
}
