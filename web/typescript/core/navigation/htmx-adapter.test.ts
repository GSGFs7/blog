import type { HtmxBeforeSwapDetails, HtmxResponseInfo } from "htmx.org";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  APP_PAGE_EVENT,
  type PageNavigationDetail,
  type PageNavigationEndDetail,
  type PageNavigationErrorDetail,
} from "./events";
import { setupHtmxPageLifecycle } from "./htmx-adapter";
import type { PageProtocol } from "./protocol";

const CURRENT_PROTOCOL: PageProtocol = {
  navigationVersion: "1",
  buildId: "test-build",
};

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

function pageHtml(protocol: PageProtocol = CURRENT_PROTOCOL): string {
  return `<!doctype html>
    <html>
      <head>
        <meta name="app-navigation-version" content="${protocol.navigationVersion}">
        <meta name="app-build-id" content="${protocol.buildId}">
      </head>
      <body></body>
    </html>`;
}

function beforeSwapDetail(
  request: HtmxResponseInfo,
  shouldSwap = true,
  serverResponse = pageHtml(),
): HtmxBeforeSwapDetails {
  return {
    ...request,
    ignoreTitle: false,
    isError: false,
    selectOverride: "",
    serverResponse,
    shouldSwap,
    swapOverride: "",
  };
}

function setXhrResponse(
  xhr: XMLHttpRequest,
  responseText: string,
  responseURL = "http://localhost/restored",
): void {
  Object.defineProperties(xhr, {
    responseText: {
      configurable: true,
      value: responseText,
    },
    responseURL: {
      configurable: true,
      value: responseURL,
    },
    status: {
      configurable: true,
      value: 200,
    },
  });
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

  teardown = setupHtmxPageLifecycle(document, {
    currentProtocol: CURRENT_PROTOCOL,
    navigate,
  });
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

test("falls back when the response build does not match", () => {
  const request = requestDetail("/new-build");
  const detail = beforeSwapDetail(
    request,
    true,
    pageHtml({ ...CURRENT_PROTOCOL, buildId: "next" }),
  );

  notify("htmx:beforeRequest", request, request.requestConfig.elt);
  const accepted = notify("htmx:beforeSwap", detail);

  expect(accepted).toBe(false);
  expect(detail.shouldSwap).toBe(false);
  expect(eventNames()).toEqual([APP_PAGE_EVENT.navigationStart, APP_PAGE_EVENT.navigationEnd]);
  expect(recordedEvents.at(-1)?.detail).toMatchObject({
    outcome: "fallback",
  });
  expect(navigate).toHaveBeenCalledOnce();
  expect((navigate.mock.calls[0][0] as URL).pathname).toBe("/new-build");
});

test("falls back when the response protocol is missing", () => {
  const request = requestDetail("/invalid");
  const detail = beforeSwapDetail(request, true, "<html><body></body></html>");

  notify("htmx:beforeRequest", request, request.requestConfig.elt);
  const accepted = notify("htmx:beforeSwap", detail);

  expect(accepted).toBe(false);
  expect(detail.shouldSwap).toBe(false);
  expect(navigate).toHaveBeenCalledOnce();
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

test("allows a matching history cache miss response", () => {
  const xhr = new XMLHttpRequest();
  const detail = {
    historyElt: document.body,
    path: "/restored",
    swapSpec: {},
    xhr,
  };
  const downstreamLoad = vi.fn();

  notify("htmx:historyCacheMiss", detail);
  setXhrResponse(xhr, pageHtml());
  xhr.addEventListener("load", downstreamLoad);
  xhr.dispatchEvent(new ProgressEvent("load"));

  expect(downstreamLoad).toHaveBeenCalledOnce();
  expect(navigate).not.toHaveBeenCalled();
});

test("blocks a mismatched history cache miss response", () => {
  const xhr = new XMLHttpRequest();
  const detail = {
    historyElt: document.body,
    path: "/restored",
    swapSpec: {},
    xhr,
  };
  const downstreamLoad = vi.fn();

  notify("htmx:historyCacheMiss", detail);
  setXhrResponse(xhr, pageHtml({ ...CURRENT_PROTOCOL, buildId: "next" }));
  xhr.addEventListener("load", downstreamLoad);
  xhr.dispatchEvent(new ProgressEvent("load"));

  expect(downstreamLoad).not.toHaveBeenCalled();
  expect(eventNames()).toEqual([APP_PAGE_EVENT.navigationStart, APP_PAGE_EVENT.navigationEnd]);
  expect(recordedEvents.at(-1)?.detail).toMatchObject({
    outcome: "fallback",
  });
  expect(navigate).toHaveBeenCalledOnce();
  expect((navigate.mock.calls[0][0] as URL).pathname).toBe("/restored");
});

test("removes history response guards during teardown", () => {
  const xhr = new XMLHttpRequest();

  notify("htmx:historyCacheMiss", {
    historyElt: document.body,
    path: "/restored",
    swapSpec: {},
    xhr,
  });
  teardown?.();
  teardown = undefined;

  setXhrResponse(xhr, pageHtml({ ...CURRENT_PROTOCOL, buildId: "next" }));
  xhr.dispatchEvent(new ProgressEvent("load"));

  expect(navigate).not.toHaveBeenCalled();
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
