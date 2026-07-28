import type { HtmxBeforeSwapDetails, HtmxResponseInfo } from "htmx.org";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  APP_PAGE_EVENT,
  type PageNavigationDetail,
  type PageNavigationEndDetail,
  type PageNavigationErrorDetail,
} from "./events";
import { setupHtmxPageLifecycle } from "./htmx-adapter";

const htmxMock = vi.hoisted(() => ({
  defineExtension: vi.fn(),
  removeExtension: vi.fn(),
}));

vi.mock("htmx.org", () => ({
  default: htmxMock,
}));

interface LifecycleExtension {
  onEvent(name: string, event: CustomEvent): boolean;
}

interface RecordedEvent {
  name: string;
  detail: unknown;
}

let extension: LifecycleExtension;
let recordedEvents: RecordedEvent[];
let recordingController: AbortController;
let teardown: (() => void) | undefined;

function createNavigateMock() {
  return vi.fn((_url: URL) => undefined);
}

let navigate: ReturnType<typeof createNavigateMock>;

function requestDetail(
  path: string,
  xhr = new XMLHttpRequest(),
  source = document.createElement("a"),
): HtmxResponseInfo {
  return {
    boosted: true,
    etc: {},
    pathInfo: {
      anchor: "",
      finalRequestPath: path,
      requestPath: path,
      responsePath: null,
    },
    requestConfig: { elt: source },
    target: document.body,
    xhr,
  } as unknown as HtmxResponseInfo;
}

function beforeSwapDetail(request: HtmxResponseInfo, shouldSwap = true): HtmxBeforeSwapDetails {
  return {
    ...request,
    ignoreTitle: false,
    isError: false,
    selectOverride: "",
    serverResponse: "<body></body>",
    shouldSwap,
    swapOverride: "",
  };
}

function notify(name: string, detail: unknown, target: EventTarget = document.body): boolean {
  const event = new CustomEvent(name, {
    bubbles: true,
    cancelable: true,
    detail,
  });
  target.dispatchEvent(event);
  return extension.onEvent(name, event);
}

function eventNames(): string[] {
  return recordedEvents.map(({ name }) => name);
}

beforeEach(() => {
  document.body.replaceChildren();
  htmxMock.defineExtension.mockClear();
  htmxMock.removeExtension.mockClear();
  navigate = createNavigateMock();
  recordedEvents = [];
  recordingController = new AbortController();

  for (const name of Object.values(APP_PAGE_EVENT)) {
    document.addEventListener(
      name,
      (event) => {
        recordedEvents.push({
          name,
          detail: (event as CustomEvent).detail,
        });
      },
      { signal: recordingController.signal },
    );
  }

  teardown = setupHtmxPageLifecycle(document, { navigate });
  extension = htmxMock.defineExtension.mock.calls.at(-1)?.[1] as LifecycleExtension;
});

afterEach(() => {
  recordingController.abort();
  teardown?.();
  teardown = undefined;
  document.body.replaceChildren();
});

test("emits one complete lifecycle for a boosted body navigation", () => {
  const request = requestDetail("/about");

  notify("htmx:beforeRequest", request, request.requestConfig.elt);
  notify("htmx:beforeSwap", beforeSwapDetail(request));
  notify("htmx:afterSwap", request);
  notify("htmx:afterSettle", request);

  expect(eventNames()).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
    APP_PAGE_EVENT.navigationEnd,
  ]);
  const navigationIds = recordedEvents.map(
    ({ detail }) => (detail as PageNavigationDetail).navigationId,
  );
  expect(new Set(navigationIds).size).toBe(1);
  expect(recordedEvents.at(-1)?.detail).toMatchObject({
    outcome: "completed",
  });
});

test("does not emit swap events when HTMX declines the swap", () => {
  const request = requestDetail("/no-content");

  notify("htmx:beforeRequest", request, request.requestConfig.elt);
  notify("htmx:beforeSwap", beforeSwapDetail(request, false));
  notify("htmx:afterRequest", request, request.requestConfig.elt);

  expect(eventNames()).toEqual([APP_PAGE_EVENT.navigationStart, APP_PAGE_EVENT.navigationEnd]);
  expect(recordedEvents.at(-1)?.detail).toMatchObject({
    outcome: "cancelled",
  });
});

test("waits for the specific network error after an error afterRequest", () => {
  const request = requestDetail("/offline");

  notify("htmx:beforeRequest", request, request.requestConfig.elt);
  notify(
    "htmx:afterRequest",
    { ...request, error: "htmx:afterRequest" },
    request.requestConfig.elt,
  );
  expect(eventNames()).toEqual([APP_PAGE_EVENT.navigationStart]);

  notify("htmx:sendError", { ...request, error: "htmx:sendError" }, request.requestConfig.elt);

  expect(eventNames()).toEqual([APP_PAGE_EVENT.navigationStart, APP_PAGE_EVENT.navigationError]);
  expect(recordedEvents.at(-1)?.detail as PageNavigationErrorDetail).toMatchObject({
    phase: "request",
  });
});

test("treats an aborted request as cancellation", () => {
  const request = requestDetail("/cancelled");

  notify("htmx:beforeRequest", request, request.requestConfig.elt);
  notify(
    "htmx:afterRequest",
    { ...request, error: "htmx:afterRequest" },
    request.requestConfig.elt,
  );
  notify("htmx:sendAbort", { ...request, error: "htmx:sendAbort" }, request.requestConfig.elt);

  expect(eventNames()).toEqual([APP_PAGE_EVENT.navigationStart, APP_PAGE_EVENT.navigationEnd]);
  expect(recordedEvents.at(-1)?.detail as PageNavigationEndDetail).toMatchObject({
    outcome: "cancelled",
  });
});

test("aborts a superseded request and rejects its late response", () => {
  const firstXhr = new XMLHttpRequest();
  const abort = vi.spyOn(firstXhr, "abort").mockImplementation(() => undefined);
  const first = requestDetail("/first", firstXhr);
  const second = requestDetail("/second");

  notify("htmx:beforeRequest", first, first.requestConfig.elt);
  const firstNavigationId = (recordedEvents[0].detail as PageNavigationDetail).navigationId;
  notify("htmx:beforeRequest", second, second.requestConfig.elt);

  const staleSwap = beforeSwapDetail(first);
  notify("htmx:beforeSwap", staleSwap);
  expect(staleSwap.shouldSwap).toBe(false);
  expect(abort).toHaveBeenCalledOnce();

  notify("htmx:beforeSwap", beforeSwapDetail(second));
  notify("htmx:afterSwap", second);
  notify("htmx:afterSettle", second);

  const firstTerminalEvents = recordedEvents.filter(
    ({ detail, name }) =>
      (detail as PageNavigationDetail).navigationId === firstNavigationId &&
      (name === APP_PAGE_EVENT.navigationEnd || name === APP_PAGE_EVENT.navigationError),
  );
  expect(firstTerminalEvents).toHaveLength(1);
  expect(firstTerminalEvents[0].detail).toMatchObject({
    outcome: "cancelled",
  });
});

test("falls back to a full navigation while another swap is pending", () => {
  const first = requestDetail("/first");
  const second = requestDetail("/second");

  notify("htmx:beforeRequest", first, first.requestConfig.elt);
  notify("htmx:beforeSwap", beforeSwapDetail(first));
  const accepted = notify("htmx:beforeRequest", second, second.requestConfig.elt);

  expect(accepted).toBe(false);
  expect(navigate).toHaveBeenCalledOnce();
  expect((navigate.mock.calls[0][0] as URL).pathname).toBe("/second");
  expect(recordedEvents.at(-1)?.detail).toMatchObject({
    outcome: "fallback",
  });
});

test("bridges a history cache hit", () => {
  notify("htmx:historyCacheHit", {
    historyElt: document.body,
    path: "/cached",
    swapSpec: {},
  });
  notify("htmx:afterSwap", {});
  notify("htmx:afterSettle", {});

  expect(eventNames()).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
    APP_PAGE_EVENT.navigationEnd,
  ]);
  expect(recordedEvents[0].detail).toMatchObject({
    navigationType: "pop",
    source: "memory",
  });
});

test("bridges a history cache miss", () => {
  const xhr = new XMLHttpRequest();
  const detail = {
    historyElt: document.body,
    path: "/restored",
    swapSpec: {},
    xhr,
  };

  notify("htmx:historyCacheMiss", detail);
  notify("htmx:historyCacheMissLoad", detail);
  notify("htmx:afterSwap", {});
  notify("htmx:afterSettle", {});

  expect(eventNames()).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
    APP_PAGE_EVENT.navigationEnd,
  ]);
  expect(recordedEvents[0].detail).toMatchObject({
    navigationType: "pop",
    source: "fetch",
  });
});

test("recognizes inherited hx-replace-url navigation", () => {
  const container = document.createElement("div");
  const source = document.createElement("a");
  container.setAttribute("hx-replace-url", "true");
  container.append(source);
  document.body.append(container);
  const request = requestDetail("/replace", new XMLHttpRequest(), source);

  notify("htmx:beforeRequest", request, source);

  expect(recordedEvents[0].detail).toMatchObject({
    navigationType: "replace",
  });
});
