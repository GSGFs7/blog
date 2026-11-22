import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { cleanup, type IslandElement } from "@/core/bootstrap";

import {
  APP_PAGE_EVENT,
  type PageNavigationDetail,
  type PageNavigationEndDetail,
  type PageNavigationErrorDetail,
} from "../../contracts";
import { PAGE_TRANSITION_TIMING } from "../../runtime";
import { setupNativePageNavigation } from "./adapter";
import type { preparePageHead } from "./head";
import { type page, PageLoadError, type PageLoadResult } from "./page";
import * as prefetchModule from "./prefetch";

interface RecordedEvent {
  name: string;
  detail: PageNavigationDetail;
}

interface TestNavigateEvent {
  event: NavigateEvent;
  intercept: ReturnType<typeof vi.fn>;
  redirect: ReturnType<typeof vi.fn>;
  scroll: ReturnType<typeof vi.fn>;
  addHandler: ReturnType<typeof vi.fn>;
  run(): Promise<void>;
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(reason: unknown): void;
}

let navigation: EventTarget;
let teardown: (() => void) | undefined;
let recordingController: AbortController;
let recordedEvents: RecordedEvent[];
let originalNavigation: PropertyDescriptor | undefined;

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, failed) => {
    resolve = done;
    reject = failed;
  });
  return { promise, resolve, reject };
}

function destination(path: string): URL {
  return new URL(path, window.location.origin);
}

function pageDocument(body = "<main>next page</main>"): Document {
  return new DOMParser().parseFromString(
    `<!doctype html><html><head><title>Next</title></head><body class="site-body">${body}</body></html>`,
    "text/html",
  );
}

function swapResult(requestedPath: string, finalPath = requestedPath): PageLoadResult {
  const document = pageDocument();
  return {
    kind: "swap",
    page: {
      requestedUrl: destination(requestedPath),
      finalUrl: destination(finalPath),
      document,
      response: new Response(""),
      deliverySource: "origin",
      html: "<!doctype html>" + document.documentElement.outerHTML,
    },
  };
}

function reloadResult(path: string): PageLoadResult {
  return {
    kind: "reload",
    url: destination(path),
    reason: "protocol",
  };
}

function navigateEvent(
  path: string,
  navigationType: NavigationType = "push",
  sameDocument = false,
): TestNavigateEvent {
  const signalController = new AbortController();
  let interceptOptions: NavigationInterceptOptions | undefined;
  const postCommitHandlers: NavigationInterceptHandler[] = [];
  const event = new Event("navigate", { cancelable: true }) as NavigateEvent;
  const intercept = vi.fn((options?: NavigationInterceptOptions) => {
    interceptOptions = options;
  });
  const redirect = vi.fn();
  const scroll = vi.fn();
  const addHandler = vi.fn((handler: NavigationInterceptHandler) => {
    postCommitHandlers.push(handler);
  });

  Object.defineProperties(event, {
    canIntercept: { value: true },
    destination: { value: { url: destination(path).href, sameDocument } },
    downloadRequest: { value: null },
    formData: { value: null },
    hashChange: { value: false },
    navigationType: { value: navigationType },
    signal: { value: signalController.signal },
    sourceElement: { value: null },
    intercept: { value: intercept },
    scroll: { value: scroll },
  });

  return {
    event,
    intercept,
    redirect,
    scroll,
    addHandler,
    async run() {
      const precommitHandler = interceptOptions?.precommitHandler;
      if (precommitHandler) {
        await precommitHandler({
          redirect,
          addHandler,
        } as unknown as NavigationPrecommitController);
      }
      const handler = interceptOptions?.handler;
      if (handler) {
        await handler();
      }
      for (const postCommitHandler of postCommitHandlers) {
        await postCommitHandler();
      }
    },
  };
}

function recordPageEvents(): void {
  recordedEvents = [];
  recordingController = new AbortController();
  for (const name of Object.values(APP_PAGE_EVENT)) {
    document.addEventListener(
      name,
      ((event: CustomEvent<PageNavigationDetail>) => {
        recordedEvents.push({ name, detail: event.detail });
      }) as EventListener,
      { signal: recordingController.signal },
    );
  }
}

function eventNames(): string[] {
  return recordedEvents.map(({ name }) => name);
}

function setup(
  overrides: {
    loadPage?: ReturnType<typeof vi.fn<typeof page>>;
    prepareHead?: ReturnType<typeof vi.fn<typeof preparePageHead>>;
    navigate?: ReturnType<typeof vi.fn<(url: URL) => void>>;
    reload?: ReturnType<typeof vi.fn<() => void>>;
    wait?: ReturnType<typeof vi.fn<(duration: number, signal: AbortSignal) => Promise<void>>>;
    prefersReducedMotion?: () => boolean;
    supportsPrecommitRedirect?: () => boolean;
  } = {},
) {
  const loadPage = overrides.loadPage ?? vi.fn<typeof page>();
  const commit = vi.fn();
  const rollback = vi.fn();
  const prepareHead =
    overrides.prepareHead ??
    vi.fn<typeof preparePageHead>().mockResolvedValue({ commit, rollback });
  const navigate = overrides.navigate ?? vi.fn<(url: URL) => void>();
  const reload = overrides.reload ?? vi.fn<() => void>();
  const wait =
    overrides.wait ??
    vi.fn<(duration: number, signal: AbortSignal) => Promise<void>>(async () => undefined);

  teardown = setupNativePageNavigation(document, {
    loadPage,
    prepareHead,
    navigate,
    reload,
    wait,
    prefersReducedMotion: overrides.prefersReducedMotion ?? (() => false),
    supportsPrecommitRedirect: overrides.supportsPrecommitRedirect ?? (() => false),
  });

  return { loadPage, prepareHead, commit, rollback, navigate, reload, wait };
}

beforeEach(() => {
  window.history.replaceState(null, "", "/current");
  document.head.innerHTML = `
    <title>Current</title>
    <meta name="app-navigation-version" content="1">
    <meta name="app-build-id" content="test-build">
  `;
  window.history.scrollRestoration = "auto";
  document.body.removeAttribute("style");
  document.body.className = "site-body";
  document.body.innerHTML = "<main>current page</main>";

  originalNavigation = Object.getOwnPropertyDescriptor(window, "navigation");
  navigation = new EventTarget();
  Object.defineProperty(window, "navigation", {
    configurable: true,
    value: navigation,
  });
  recordPageEvents();
});

afterEach(() => {
  teardown?.();
  teardown = undefined;
  vi.restoreAllMocks();
  recordingController.abort();
  if (originalNavigation) {
    Object.defineProperty(window, "navigation", originalNavigation);
  } else {
    Reflect.deleteProperty(window, "navigation");
  }
});

function cachedNavigation(stale = true, requestedPath = "/about", finalPath = requestedPath) {
  const cached = swapResult(requestedPath, finalPath);
  if (cached.kind !== "swap") throw new Error("Expected page");
  const refreshed = deferred<PageLoadResult>();
  const take = vi.fn().mockResolvedValue({ page: cached.page, stale });
  const refresh = vi.fn(() => refreshed.promise);
  vi.spyOn(prefetchModule, "setupNativePrefetch").mockReturnValue({
    take,
    refresh,
    dispose: vi.fn(),
  });
  return { cached, refreshed, take, refresh };
}

test("uses fresh cached content without fetching or revalidating", async () => {
  const cache = cachedNavigation(false);
  const harness = setup();
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();

  expect(document.body).toHaveTextContent("next page");
  expect(harness.loadPage).not.toHaveBeenCalled();
  expect(cache.refresh).not.toHaveBeenCalled();
  expect(request.scroll).toHaveBeenCalledOnce();
});

test("shows stale content before revalidation and updates without a second navigation or animation", async () => {
  const cache = cachedNavigation();
  cache.cached.page.document.body.insertAdjacentHTML(
    "beforeend",
    '<div id="dock" data-app-preserve data-solid-island="MusicDock"><audio></audio></div><div id="removed" data-solid-island="Example"></div>',
  );
  const harness = setup();
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();

  expect(document.body).toHaveTextContent("next page");
  expect(cache.refresh).toHaveBeenCalledExactlyOnceWith(destination("/about"));
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ outcome: "completed" });
  expect(harness.loadPage).not.toHaveBeenCalled();
  const dock = document.getElementById("dock") as IslandElement;
  const audio = dock.firstElementChild;
  const disposeDock = vi.fn();
  const disposeRemoved = vi.fn();
  dock.__solidDispose__ = disposeDock;
  (document.getElementById("removed") as IslandElement).__solidDispose__ = disposeRemoved;
  document.addEventListener(
    APP_PAGE_EVENT.beforeSwap,
    (event) => cleanup(event.detail.root, event.detail.preservedRoots),
    { signal: recordingController.signal },
  );
  const updated = swapResult("/about");
  if (updated.kind !== "swap") throw new Error("Expected page");
  updated.page.document.body.innerHTML =
    '<main>updated content</main><div id="dock" data-app-preserve data-solid-island="MusicDock"></div>';
  cache.refreshed.resolve({
    kind: "swap",
    page: { ...updated.page, html: updated.page.document.documentElement.outerHTML },
  });
  await vi.waitFor(() => expect(document.body).toHaveTextContent("updated content"));

  expect(harness.commit).toHaveBeenCalledTimes(2);
  expect(request.scroll).toHaveBeenCalledOnce();
  expect(harness.wait).toHaveBeenCalledTimes(2);
  expect(eventNames()).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.beforeLeave,
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
    APP_PAGE_EVENT.navigationEnd,
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
  ]);
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ reason: "revalidation" });
  expect(document.body).not.toHaveAttribute("data-page-transition");
  expect(document.body).not.toHaveAttribute("aria-busy");
  expect(harness.navigate).not.toHaveBeenCalled();
  expect(document.getElementById("dock")).toBe(dock);
  expect(dock.firstElementChild).toBe(audio);
  expect(disposeDock).not.toHaveBeenCalled();
  expect(disposeRemoved).toHaveBeenCalledOnce();
});

test.each(["unchanged", "invalid", "redirected", "offline"])(
  "keeps displayed stale content when revalidation is %s",
  async (state) => {
    const cache = cachedNavigation();
    const harness = setup();
    const request = navigateEvent("/about");
    navigation.dispatchEvent(request.event);
    await request.run();
    if (state === "offline") {
      cache.refreshed.reject(new Error("offline"));
      await cache.refreshed.promise.catch(() => undefined);
    } else {
      cache.refreshed.resolve(
        state === "invalid"
          ? reloadResult("/about")
          : state === "redirected"
            ? swapResult("/about", "/elsewhere")
            : cache.cached,
      );
      await cache.refreshed.promise;
    }
    await Promise.resolve();

    expect(harness.prepareHead).toHaveBeenCalledOnce();
    expect(harness.navigate).not.toHaveBeenCalled();
    expect(document.body).toHaveTextContent("next page");
    expect(eventNames()).toHaveLength(5);
  },
);

test("keeps displayed stale content while the user is editing", async () => {
  const cache = cachedNavigation();
  const harness = setup();
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();

  const input = document.createElement("input");
  input.value = "draft";
  document.body.append(input);
  input.focus();

  const updated = swapResult("/about");
  if (updated.kind !== "swap") throw new Error("Expected page");
  updated.page.document.body.innerHTML = "<main>updated content</main>";
  cache.refreshed.resolve({
    kind: "swap",
    page: { ...updated.page, html: updated.page.document.documentElement.outerHTML },
  });
  await vi.waitFor(() => expect(harness.rollback).toHaveBeenCalledOnce());

  expect(document.body).toHaveTextContent("next page");
  expect(document.body).not.toHaveTextContent("updated content");
  expect(document.activeElement).toBe(input);
  expect(input.value).toBe("draft");
});

test("keeps displayed stale content when a form control is dirty", async () => {
  const cache = cachedNavigation();
  const harness = setup();
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();

  const input = document.createElement("input");
  input.value = "edited";
  document.body.append(input);
  input.blur();

  const updated = swapResult("/about");
  if (updated.kind !== "swap") throw new Error("Expected page");
  updated.page.document.body.innerHTML = "<main>updated content</main>";
  cache.refreshed.resolve({
    kind: "swap",
    page: { ...updated.page, html: updated.page.document.documentElement.outerHTML },
  });
  await vi.waitFor(() => expect(harness.rollback).toHaveBeenCalledOnce());

  expect(document.body).toHaveTextContent("next page");
  expect(document.body).not.toHaveTextContent("updated content");
});

test.each(["contenteditable", "component"])(
  "keeps the displayed page when %s has unsaved state after losing focus",
  async (kind) => {
    const cache = cachedNavigation();
    const harness = setup();
    const request = navigateEvent("/about");
    navigation.dispatchEvent(request.event);
    await request.run();

    const editor = document.createElement("div");
    document.body.append(editor);
    if (kind === "contenteditable") {
      editor.setAttribute("contenteditable", "true");
      editor.tabIndex = 0;
      editor.focus();
      editor.textContent = "unsaved edits";
      editor.dispatchEvent(new InputEvent("input", { bubbles: true }));
      editor.blur();
    } else {
      editor.setAttribute("data-nav-dirty", "");
    }

    cache.refreshed.resolve({
      kind: "swap",
      page: { ...cache.cached.page, html: "changed" },
    });
    await vi.waitFor(() => expect(harness.rollback).toHaveBeenCalledOnce());

    expect(editor.isConnected).toBe(true);
    expect(harness.commit).toHaveBeenCalledOnce();
    expect(eventNames().filter((name) => name === APP_PAGE_EVENT.afterSwap)).toHaveLength(1);
  },
);

test("revalidates the original requested URL after a redirect", async () => {
  const cache = cachedNavigation(true, "/alias", "/about");
  setup({ supportsPrecommitRedirect: () => true });
  const request = navigateEvent("/alias");
  navigation.dispatchEvent(request.event);
  await request.run();

  expect(request.redirect).toHaveBeenCalledWith(destination("/about"));
  expect(cache.refresh).toHaveBeenCalledExactlyOnceWith(destination("/alias"));
  expect(document.body).toHaveTextContent("next page");
});

test.each(["navigation", "teardown"])("ignores a late refreshed page after %s", async (action) => {
  const cache = cachedNavigation();
  const harness = setup();
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();

  if (action === "navigation") {
    cache.take.mockResolvedValue(undefined);
    harness.loadPage.mockResolvedValue(swapResult("/second"));
    const second = navigateEvent("/second");
    navigation.dispatchEvent(second.event);
    await second.run();
  } else {
    teardown?.();
    teardown = undefined;
  }
  const content = document.body.innerHTML;
  const changed = swapResult("/about");
  if (changed.kind !== "swap") throw new Error("Expected page");
  cache.refreshed.resolve({ kind: "swap", page: { ...changed.page, html: "changed" } });
  await cache.refreshed.promise;
  await Promise.resolve();

  expect(document.body.innerHTML).toBe(content);
  expect(harness.prepareHead).toHaveBeenCalledTimes(action === "navigation" ? 2 : 1);
});

test("rolls back refresh stylesheets when navigation changes during head preparation", async () => {
  const cache = cachedNavigation();
  const harness = setup();
  const prepared = deferred<Awaited<ReturnType<typeof preparePageHead>>>();
  const rollback = vi.fn();
  const commit = vi.fn();
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();
  harness.prepareHead.mockImplementationOnce(() => prepared.promise);
  cache.refreshed.resolve({
    kind: "swap",
    page: { ...cache.cached.page, html: "changed" },
  });
  await vi.waitFor(() => expect(harness.prepareHead).toHaveBeenCalledTimes(2));

  navigation.dispatchEvent(navigateEvent("/account/login").event);
  prepared.resolve({ commit, rollback });
  await vi.waitFor(() => expect(rollback).toHaveBeenCalledOnce());
  expect(commit).not.toHaveBeenCalled();
  expect(document.body).toHaveTextContent("next page");
});

test("completes a page navigation with transition timing and lifecycle events", async () => {
  const harness = setup();
  harness.loadPage.mockResolvedValue(swapResult("/about"));
  const request = navigateEvent("/about");

  navigation.dispatchEvent(request.event);

  expect(request.intercept).toHaveBeenCalledWith(
    expect.objectContaining({
      focusReset: "after-transition",
      scroll: "after-transition",
      handler: expect.any(Function),
    }),
  );
  expect(document.body).toHaveAttribute("aria-busy", "true");

  await request.run();

  expect(document.body).toHaveTextContent("next page");
  expect(document.body).not.toHaveAttribute("aria-busy");
  expect(harness.commit).toHaveBeenCalledOnce();
  expect(harness.rollback).not.toHaveBeenCalled();
  expect(harness.wait.mock.calls.map(([duration]) => duration)).toEqual([
    PAGE_TRANSITION_TIMING.swapDelay,
    PAGE_TRANSITION_TIMING.settleDelay,
  ]);
  expect(eventNames()).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.beforeLeave,
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
    APP_PAGE_EVENT.navigationEnd,
  ]);
  expect(recordedEvents.at(-1)?.detail as PageNavigationEndDetail).toMatchObject({
    outcome: "completed",
    deliverySource: "origin",
  });
});

test("skips transition waits when reduced motion is requested", async () => {
  const harness = setup({ prefersReducedMotion: () => true });
  harness.loadPage.mockResolvedValue(swapResult("/about"));
  const request = navigateEvent("/about");

  navigation.dispatchEvent(request.event);
  await request.run();

  expect(harness.wait).not.toHaveBeenCalled();
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ outcome: "completed" });
});

test("reports a validation reload as a fallback", async () => {
  const harness = setup();
  harness.loadPage.mockResolvedValue(reloadResult("/login"));
  const request = navigateEvent("/about");

  navigation.dispatchEvent(request.event);
  await request.run();

  expect(eventNames()).toEqual([APP_PAGE_EVENT.navigationStart, APP_PAGE_EVENT.navigationEnd]);
  expect(recordedEvents.at(-1)?.detail as PageNavigationEndDetail).toMatchObject({
    outcome: "fallback",
  });
  expect(harness.navigate).toHaveBeenCalledOnce();
  expect(harness.navigate.mock.calls[0][0].pathname).toBe("/login");
});

test("reloads the requested page after a request error", async () => {
  const harness = setup();
  const error = new PageLoadError("request", new Error("offline"));
  harness.loadPage.mockRejectedValue(error);
  const request = navigateEvent("/about");

  navigation.dispatchEvent(request.event);
  await request.run();

  expect(eventNames()).toEqual([APP_PAGE_EVENT.navigationStart, APP_PAGE_EVENT.navigationError]);
  expect(recordedEvents.at(-1)?.detail as PageNavigationErrorDetail).toMatchObject({
    phase: "request",
    error,
  });
  expect(harness.navigate.mock.calls[0][0].pathname).toBe("/about");
});

test("rolls back the prepared head before reloading after a swap error", async () => {
  const error = new Error("head changed");
  const commit = vi.fn(() => {
    throw error;
  });
  const rollback = vi.fn();
  const prepareHead = vi.fn<typeof preparePageHead>().mockResolvedValue({ commit, rollback });
  const harness = setup({ prepareHead });
  harness.loadPage.mockResolvedValue(swapResult("/about"));
  const request = navigateEvent("/about");

  navigation.dispatchEvent(request.event);
  await request.run();

  expect(rollback).toHaveBeenCalledOnce();
  expect(document.body).toHaveTextContent("current page");
  expect(recordedEvents.at(-1)?.detail as PageNavigationErrorDetail).toMatchObject({
    phase: "swap",
    error,
  });
  expect(harness.navigate.mock.calls[0][0].pathname).toBe("/about");
});

test("falls back to the final URL after a server redirect without precommit support", async () => {
  const harness = setup();
  harness.loadPage.mockResolvedValue(swapResult("/old", "/new"));
  const request = navigateEvent("/old");

  navigation.dispatchEvent(request.event);
  await request.run();

  expect(harness.prepareHead).not.toHaveBeenCalled();
  expect(harness.navigate.mock.calls[0][0].pathname).toBe("/new");
  expect(recordedEvents.at(-1)?.detail as PageNavigationEndDetail).toMatchObject({
    outcome: "fallback",
    finalUrl: destination("/new"),
  });
});

test("redirects before commit and swaps the final page", async () => {
  const harness = setup({ supportsPrecommitRedirect: () => true });
  harness.loadPage.mockResolvedValue(swapResult("/old", "/new"));
  const request = navigateEvent("/old");

  navigation.dispatchEvent(request.event);
  await request.run();

  expect(request.redirect).toHaveBeenCalledOnce();
  expect((request.redirect.mock.calls[0][0] as URL).pathname).toBe("/new");
  expect(request.addHandler).toHaveBeenCalledOnce();
  expect(harness.navigate).not.toHaveBeenCalled();
  expect(harness.prepareHead).toHaveBeenCalledOnce();
  expect(harness.commit).toHaveBeenCalledOnce();
  expect(document.body).toHaveTextContent("next page");
  expect(recordedEvents.at(-1)?.detail as PageNavigationEndDetail).toMatchObject({
    outcome: "completed",
    requestedUrl: destination("/old"),
    finalUrl: destination("/new"),
  });
});

test("falls back when a redirect ends at an excluded route", async () => {
  const harness = setup({ supportsPrecommitRedirect: () => true });
  harness.loadPage.mockResolvedValue(swapResult("/old", "/api/private"));
  const request = navigateEvent("/old");

  navigation.dispatchEvent(request.event);

  await expect(request.run()).rejects.toMatchObject({ name: "AbortError" });
  expect(request.redirect).not.toHaveBeenCalled();
  expect(harness.prepareHead).not.toHaveBeenCalled();
  expect(harness.navigate).toHaveBeenCalledOnce();
  expect(harness.navigate.mock.calls[0][0].pathname).toBe("/api/private");
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ outcome: "fallback" });
});

test("falls back for a redirect discovered during history traversal", async () => {
  const harness = setup({ supportsPrecommitRedirect: () => true });
  harness.loadPage.mockResolvedValue(swapResult("/old", "/new"));
  const request = navigateEvent("/old", "traverse", true);

  navigation.dispatchEvent(request.event);
  await request.run();

  expect(request.redirect).not.toHaveBeenCalled();
  expect(harness.prepareHead).not.toHaveBeenCalled();
  expect(harness.navigate.mock.calls[0][0].pathname).toBe("/new");
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ outcome: "fallback" });
});

test("cancels a superseded loading transaction exactly once", async () => {
  const firstPage = deferred<PageLoadResult>();
  let firstSignal: AbortSignal | undefined;
  const loadPage = vi
    .fn<typeof page>()
    .mockImplementationOnce((_url, options) => {
      firstSignal = options.signal;
      return firstPage.promise;
    })
    .mockResolvedValueOnce(swapResult("/second"));
  setup({ loadPage });
  const first = navigateEvent("/first");
  const second = navigateEvent("/second");

  navigation.dispatchEvent(first.event);
  const firstRun = first.run();
  await vi.waitFor(() => expect(loadPage).toHaveBeenCalledOnce());
  navigation.dispatchEvent(second.event);

  expect(firstSignal?.aborted).toBe(true);
  expect(recordedEvents.slice(0, 3).map(({ name }) => name)).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.navigationEnd,
    APP_PAGE_EVENT.navigationStart,
  ]);
  expect(recordedEvents[1].detail).toMatchObject({ outcome: "cancelled" });

  await second.run();
  firstPage.resolve(swapResult("/first"));
  await firstRun;

  const firstNavigationId = recordedEvents[0].detail.navigationId;
  const firstTerminalEvents = recordedEvents.filter(
    ({ detail, name }) =>
      detail.navigationId === firstNavigationId &&
      (name === APP_PAGE_EVENT.navigationEnd || name === APP_PAGE_EVENT.navigationError),
  );
  expect(firstTerminalEvents).toHaveLength(1);
  expect(document.body).toHaveTextContent("next page");
});

test("teardown aborts active work and prevents a late swap", async () => {
  const pendingPage = deferred<PageLoadResult>();
  let signal: AbortSignal | undefined;
  const loadPage = vi.fn<typeof page>().mockImplementation((_url, options) => {
    signal = options.signal;
    return pendingPage.promise;
  });
  const harness = setup({ loadPage });
  const request = navigateEvent("/about");

  navigation.dispatchEvent(request.event);
  const running = request.run();
  await vi.waitFor(() => expect(loadPage).toHaveBeenCalledOnce());
  teardown?.();
  teardown = undefined;

  expect(signal?.aborted).toBe(true);
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ outcome: "cancelled" });
  pendingPage.resolve(swapResult("/about"));
  await running;

  expect(document.body).toHaveTextContent("current page");
  expect(harness.prepareHead).not.toHaveBeenCalled();
});

test("leaves a navigation during the swap phase to the browser", async () => {
  const swapDelay = deferred<void>();
  const wait = vi
    .fn<(duration: number, signal: AbortSignal) => Promise<void>>()
    .mockImplementationOnce(() => swapDelay.promise)
    .mockResolvedValue(undefined);
  const harness = setup({ wait });
  harness.loadPage.mockResolvedValue(swapResult("/first"));
  const first = navigateEvent("/first");
  const second = navigateEvent("/second");

  navigation.dispatchEvent(first.event);
  const running = first.run();
  await vi.waitFor(() => expect(wait).toHaveBeenCalledOnce());
  navigation.dispatchEvent(second.event);

  expect(second.intercept).not.toHaveBeenCalled();
  expect(harness.rollback).not.toHaveBeenCalled();
  swapDelay.resolve();
  await running;

  expect(harness.rollback).toHaveBeenCalledOnce();
  expect(document.body).toHaveTextContent("current page");
  expect(eventNames()).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.beforeLeave,
    APP_PAGE_EVENT.navigationEnd,
  ]);
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ outcome: "cancelled" });
});

test("does not start a transaction when intercept throws", () => {
  setup();
  const request = navigateEvent("/about");
  request.intercept.mockImplementation(() => {
    throw new DOMException("inactive document", "InvalidStateError");
  });

  navigation.dispatchEvent(request.event);

  expect(recordedEvents).toEqual([]);
  expect(document.body).not.toHaveAttribute("aria-busy");
});

test("fully reloads an excluded same-document history entry", async () => {
  const harness = setup();
  const request = navigateEvent("/api/private", "traverse", true);

  navigation.dispatchEvent(request.event);
  await request.run();

  expect(request.intercept).toHaveBeenCalledOnce();
  expect(harness.loadPage).not.toHaveBeenCalled();
  expect(harness.navigate).not.toHaveBeenCalled();
  expect(harness.reload).toHaveBeenCalledOnce();
  expect(recordedEvents).toEqual([]);
});

test("reuses preserved islands and disposes only removed islands at commit", async () => {
  document.body.innerHTML =
    '<div id="dock" data-app-preserve data-solid-island="MusicDock"><audio></audio></div><div id="removed" data-solid-island="Example"></div>';
  const dock = document.getElementById("dock") as IslandElement;
  const audio = dock.firstElementChild;
  const disposeDock = vi.fn();
  const disposeRemoved = vi.fn();
  dock.__solidDispose__ = disposeDock;
  (document.getElementById("removed") as IslandElement).__solidDispose__ = disposeRemoved;
  document.addEventListener(
    APP_PAGE_EVENT.beforeSwap,
    (event) => {
      cleanup(event.detail.root, event.detail.preservedRoots);
    },
    { signal: recordingController.signal },
  );
  const wait = vi.fn(async () => {
    expect(disposeDock).not.toHaveBeenCalled();
    if (document.getElementById("removed")) {
      expect(disposeRemoved).not.toHaveBeenCalled();
      expect(document.body).toHaveAttribute("data-page-transition", "leaving");
    }
  });
  const harness = setup({ wait });
  const result = swapResult("/about");
  if (result.kind !== "swap") throw new Error("Expected page");
  result.page.document.body.innerHTML =
    '<main>new content</main><div id="dock" data-app-preserve data-solid-island="MusicDock"></div>';
  harness.loadPage.mockResolvedValue(result);
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();

  expect(document.getElementById("dock")).toBe(dock);
  expect(dock.firstElementChild).toBe(audio);
  expect(dock.__solidDispose__).toBe(disposeDock);
  expect(disposeDock).not.toHaveBeenCalled();
  expect(disposeRemoved).toHaveBeenCalledOnce();
  expect(document.querySelector("main")).toHaveTextContent("new content");
  for (const event of recordedEvents.filter(
    ({ name }) => name === APP_PAGE_EVENT.beforeSwap || name === APP_PAGE_EVENT.afterSwap,
  )) {
    expect(event.detail.preservedRoots).toEqual([dock]);
  }
});

test("disposes a marked island when the next page has no matching slot", async () => {
  document.body.innerHTML = '<div id="dock" data-app-preserve data-solid-island="MusicDock"></div>';
  const dock = document.getElementById("dock") as IslandElement;
  const dispose = vi.fn();
  dock.__solidDispose__ = dispose;
  document.addEventListener(
    APP_PAGE_EVENT.beforeSwap,
    (event) => {
      cleanup(event.detail.root, event.detail.preservedRoots);
    },
    { signal: recordingController.signal },
  );
  const harness = setup();
  harness.loadPage.mockResolvedValue(swapResult("/about"));
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();
  expect(dispose).toHaveBeenCalledOnce();
  expect(dock.isConnected).toBe(false);
});

test("invalid preservation declarations fall back before cleanup or head commit", async () => {
  const harness = setup();
  const result = swapResult("/about");
  if (result.kind !== "swap") throw new Error("Expected page");
  result.page.document.body.innerHTML =
    '<div id="same" data-app-preserve></div><div id="same"></div>';
  harness.loadPage.mockResolvedValue(result);
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();
  expect(harness.commit).not.toHaveBeenCalled();
  expect(harness.rollback).toHaveBeenCalledOnce();
  expect(eventNames()).not.toContain(APP_PAGE_EVENT.beforeSwap);
  expect(document.body).toHaveTextContent("current page");
  expect(harness.navigate.mock.calls[0][0].pathname).toBe("/about");
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ phase: "swap" });
});

test("keeps scroll extent through the swap and restores inline height and history ownership", async () => {
  document.body.style.setProperty("min-height", "120px", "important");
  const height = vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(2400);
  const harness = setup();
  harness.loadPage.mockResolvedValue(swapResult("/about"));
  const request = navigateEvent("/about");
  request.scroll.mockImplementation(() => {
    expect(document.body).toHaveTextContent("next page");
    expect(document.body.style.minHeight).toBe("2400px");
    expect(window.history.scrollRestoration).toBe("manual");
  });
  try {
    navigation.dispatchEvent(request.event);
    await request.run();
    expect(request.scroll).toHaveBeenCalledOnce();
    expect(document.body.style.minHeight).toBe("120px");
    expect(document.body.style.getPropertyPriority("min-height")).toBe("important");
    teardown?.();
    expect(window.history.scrollRestoration).toBe("auto");
  } finally {
    height.mockRestore();
  }
});

test("restores scroll state before falling back after a swap failure", async () => {
  const prepareHead = vi.fn<typeof preparePageHead>().mockResolvedValue({
    commit: () => {
      throw new Error("head commit failed");
    },
    rollback: vi.fn(),
  });
  const navigate = vi.fn(() => {
    expect(window.history.scrollRestoration).toBe("auto");
    expect(document.body.style.minHeight).toBe("");
  });
  const harness = setup({ prepareHead, navigate });
  harness.loadPage.mockResolvedValue(swapResult("/about"));
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();
  expect(navigate).toHaveBeenCalledOnce();
  expect(request.scroll).not.toHaveBeenCalled();
});

test("returns scroll restoration to the browser for excluded navigations", async () => {
  const harness = setup();
  harness.loadPage.mockResolvedValue(swapResult("/about"));
  const request = navigateEvent("/about");
  navigation.dispatchEvent(request.event);
  await request.run();
  expect(window.history.scrollRestoration).toBe("manual");
  const excluded = navigateEvent("/account/login");
  navigation.dispatchEvent(excluded.event);
  expect(excluded.intercept).not.toHaveBeenCalled();
  expect(window.history.scrollRestoration).toBe("auto");
});
