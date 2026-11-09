import { readPageProtocol } from "../../contracts";
import { isPageNavigationSource, isPageNavigationUrl } from "../../policy";
import { createPageCache, type PageCacheHit } from "./cache";
import { type PageLoadResult, page } from "./page";

const PREFETCH_ATTRIBUTE = "data-nav-prefetch";
const PREFETCH_SELECTOR = `a[${PREFETCH_ATTRIBUTE}][href]`;
const VIEWPORT_MARGIN = "200px 0px";
const INTENT_DELAY = 100;

// - intent: over 100ms
// - load: after page load
// - viewport: 200px from viewport
type PrefetchStrategy = "intent" | "load" | "viewport";

interface NativePrefetchOptions {
  loadPage?: typeof page;
}

interface NativePrefetch {
  take(url: URL, signal: AbortSignal): Promise<PageCacheHit | undefined>;
  refresh(url: URL): Promise<PageLoadResult>;
  dispose(): void;
}

type AnchorHandler = (anchor: HTMLAnchorElement) => void;
type PrefetchWindow = NonNullable<Document["defaultView"]>;

function readPrefetchStrategy(anchor: HTMLAnchorElement): PrefetchStrategy | undefined {
  switch (anchor.getAttribute(PREFETCH_ATTRIBUTE)) {
    case "":
    case "intent":
      return "intent";
    case "load":
      return "load";
    case "viewport":
      return "viewport";
    default:
      return;
  }
}

function findPrefetchAnchor(target: EventTarget | null): HTMLAnchorElement | null {
  return target instanceof Element ? target.closest<HTMLAnchorElement>(PREFETCH_SELECTOR) : null;
}

function resolvePrefetchUrl(anchor: HTMLAnchorElement, location: Location): URL | undefined {
  if (!readPrefetchStrategy(anchor) || !isPageNavigationSource(anchor)) {
    return;
  }

  const url = new URL(anchor.href);
  const currentUrl = new URL(location.href);
  url.hash = "";
  currentUrl.hash = "";
  if (url.href === currentUrl.href || !isPageNavigationUrl(url, location.origin)) {
    return;
  }

  return url;
}

function staysInsideAnchor(anchor: HTMLAnchorElement, event: PointerEvent): boolean {
  return event.relatedTarget instanceof Node && anchor.contains(event.relatedTarget);
}

function setupIntentPrefetch(
  document: Document,
  signal: AbortSignal,
  prefetch: AnchorHandler,
  canPrefetch: (anchor: HTMLAnchorElement) => boolean,
): void {
  const timers = new Map<HTMLAnchorElement, ReturnType<typeof setTimeout>>();

  const isIntent = (anchor: HTMLAnchorElement) => readPrefetchStrategy(anchor) === "intent";

  const cancelTimer = (anchor: HTMLAnchorElement) => {
    const timer = timers.get(anchor);
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.delete(anchor);
    }
  };

  const prefetchIntent = (anchor: HTMLAnchorElement) => {
    if (isIntent(anchor)) {
      cancelTimer(anchor);
      prefetch(anchor);
    }
  };

  document.addEventListener(
    "pointerdown",
    (event) => {
      const anchor = findPrefetchAnchor(event.target);
      if (anchor) {
        prefetchIntent(anchor);
      }
    },
    { signal },
  );

  document.addEventListener(
    "pointerover",
    (event) => {
      if (event.pointerType !== "mouse") {
        return;
      }

      const anchor = findPrefetchAnchor(event.target);
      if (
        !anchor ||
        !isIntent(anchor) ||
        staysInsideAnchor(anchor, event) ||
        timers.has(anchor) ||
        !canPrefetch(anchor)
      ) {
        return;
      }

      timers.set(
        anchor,
        setTimeout(() => {
          timers.delete(anchor);
          prefetch(anchor);
        }, INTENT_DELAY),
      );
    },
    { signal },
  );

  document.addEventListener(
    "pointerout",
    (event) => {
      const anchor = findPrefetchAnchor(event.target);
      if (anchor && !staysInsideAnchor(anchor, event)) {
        cancelTimer(anchor);
      }
    },
    { signal },
  );

  document.addEventListener(
    "focusin",
    (event) => {
      const anchor = findPrefetchAnchor(event.target);
      if (anchor) {
        prefetchIntent(anchor);
      }
    },
    { signal },
  );

  signal.addEventListener(
    "abort",
    () => {
      for (const timer of timers.values()) {
        clearTimeout(timer);
      }
      timers.clear();
    },
    { once: true },
  );
}

function setupDeferredPrefetch(
  document: Document,
  view: Window,
  signal: AbortSignal,
  prefetch: AnchorHandler,
): AnchorHandler {
  const anchors = new Set<HTMLAnchorElement>();
  let ready = document.readyState === "complete";

  const flush = () => {
    ready = true;
    for (const anchor of anchors) {
      prefetch(anchor);
    }
    anchors.clear();
  };

  if (!ready) {
    view.addEventListener("load", flush, { once: true, signal });
  }

  signal.addEventListener("abort", () => anchors.clear(), { once: true });

  return (anchor) => {
    if (ready) {
      prefetch(anchor);
    } else {
      anchors.add(anchor);
    }
  };
}

function setupViewportPrefetch(
  view: PrefetchWindow,
  signal: AbortSignal,
  prefetch: AnchorHandler,
): AnchorHandler | undefined {
  if (typeof view.IntersectionObserver !== "function") {
    return;
  }

  const observer = new view.IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) {
          continue;
        }

        const anchor = entry.target as HTMLAnchorElement;
        observer.unobserve(anchor);
        prefetch(anchor);
      }
    },
    { rootMargin: VIEWPORT_MARGIN },
  );

  signal.addEventListener("abort", () => observer.disconnect(), { once: true });

  return (anchor) => observer.observe(anchor);
}

function setupAnchorScanning(
  document: Document,
  signal: AbortSignal,
  register: AnchorHandler,
): void {
  const scan = (root: ParentNode) => {
    for (const anchor of root.querySelectorAll<HTMLAnchorElement>(PREFETCH_SELECTOR)) {
      register(anchor);
    }
  };

  const mutations = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (!(node instanceof Element)) {
          continue;
        }

        if (node.matches(PREFETCH_SELECTOR)) {
          register(node as HTMLAnchorElement);
        }
        scan(node);
      }
    }
  });
  mutations.observe(document.documentElement, { childList: true, subtree: true });
  signal.addEventListener("abort", () => mutations.disconnect(), { once: true });

  scan(document);
}

function inertPrefetch(): NativePrefetch {
  return {
    take: async () => undefined,
    refresh: async (url) => ({ kind: "reload", url: new URL(url), reason: "protocol" }),
    dispose: () => undefined,
  };
}

export function setupNativePrefetch(
  document: Document,
  options: NativePrefetchOptions = {},
): NativePrefetch {
  const view = document.defaultView;
  const currentProtocol = readPageProtocol(document);
  if (!view || !currentProtocol) {
    return inertPrefetch();
  }

  const loadPage = options.loadPage ?? page;
  const controller = new AbortController();
  const { signal } = controller;
  const cache = createPageCache({
    loadPage: (url, requestSignal) =>
      loadPage(url, {
        signal: requestSignal,
        expectedOrigin: view.location.origin,
        currentProtocol,
      }),
  });
  signal.addEventListener("abort", () => cache.dispose(), { once: true });

  const prefetch: AnchorHandler = (anchor) => {
    const url = resolvePrefetchUrl(anchor, view.location);
    if (url) {
      void cache.prefetch(url);
    }
  };
  const canPrefetch = (anchor: HTMLAnchorElement) =>
    resolvePrefetchUrl(anchor, view.location) !== undefined;

  const prefetchAfterLoad = setupDeferredPrefetch(document, view, signal, prefetch);
  const observeViewport = setupViewportPrefetch(view, signal, prefetch);

  const register = (anchor: HTMLAnchorElement) => {
    switch (readPrefetchStrategy(anchor)) {
      case "viewport":
        if (observeViewport) {
          observeViewport(anchor);
        } else {
          prefetchAfterLoad(anchor);
        }
        return;
      case "load":
        prefetchAfterLoad(anchor);
        return;
      default:
        return;
    }
  };

  setupIntentPrefetch(document, signal, prefetch, canPrefetch);
  setupAnchorScanning(document, signal, register);

  return {
    take: cache.take,
    refresh: cache.refresh,
    dispose: () => controller.abort(),
  };
}
