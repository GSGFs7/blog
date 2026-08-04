import { afterEach, beforeEach, expect, test, vi } from "vitest";

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

interface RecordedEvent {
  name: string;
  detail: PageNavigationDetail;
}

interface TestNavigateEvent {
  event: NavigateEvent;
  intercept: ReturnType<typeof vi.fn>;
  redirect: ReturnType<typeof vi.fn>;
  addHandler: ReturnType<typeof vi.fn>;
  run(): Promise<void>;
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
}

let navigation: EventTarget;
let teardown: (() => void) | undefined;
let recordingController: AbortController;
let recordedEvents: RecordedEvent[];
let originalNavigation: PropertyDescriptor | undefined;

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
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
  return {
    kind: "swap",
    page: {
      requestedUrl: destination(requestedPath),
      finalUrl: destination(finalPath),
      document: pageDocument(),
      response: new Response(""),
      deliverySource: "origin",
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
  });

  return {
    event,
    intercept,
    redirect,
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
  recordingController.abort();
  if (originalNavigation) {
    Object.defineProperty(window, "navigation", originalNavigation);
  } else {
    Reflect.deleteProperty(window, "navigation");
  }
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
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
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
