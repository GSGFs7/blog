import type { HtmxBeforeSwapDetails, HtmxResponseInfo } from "htmx.org";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  APP_PAGE_EVENT,
  type PageNavigationDetail,
  type PageNavigationEndDetail,
  type PageNavigationErrorDetail,
} from "../../contracts";
import type { PageProtocol } from "../../contracts";
import {
  applyHtmxHistoryPageTransition,
  applyHtmxPageTransition,
  HTMX_PAGE_TRANSITION_SWAP,
  setupHtmxPageLifecycle,
} from "./adapter";

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
    swapOverride: undefined as unknown as string,
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
  const swap = beforeSwapDetail(request);

  notify("htmx:beforeRequest", request, request.requestConfig.elt);
  notify("htmx:beforeSwap", swap);
  notify("htmx:afterSwap", request);
  notify("htmx:afterSettle", request);

  expect(swap.swapOverride).toBe(HTMX_PAGE_TRANSITION_SWAP);
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
  const detail = {
    historyElt: document.body,
    path: "/cached",
    item: { content: "<main>cached</main>" },
    swapSpec: { swapDelay: 0, settleDelay: 0 },
  };

  notify("htmx:historyCacheHit", detail);
  notify("htmx:afterSwap", {});
  notify("htmx:afterSettle", {});

  expect(detail.swapSpec).toEqual({ swapDelay: 100, settleDelay: 20 });
  expect(eventNames()).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
    APP_PAGE_EVENT.navigationEnd,
  ]);
  expect(recordedEvents[0].detail).toMatchObject({
    navigationType: "traverse",
    source: "cache",
  });
});

test("bridges a history cache miss", () => {
  const xhr = new XMLHttpRequest();
  const detail = {
    historyElt: document.body,
    path: "/restored",
    swapSpec: { swapDelay: 0, settleDelay: 0 },
    xhr,
  };

  notify("htmx:historyCacheMiss", detail);
  setXhrResponse(xhr, pageHtml());
  xhr.dispatchEvent(new ProgressEvent("load"));
  notify("htmx:historyCacheMissLoad", detail);
  notify("htmx:afterSwap", {});
  notify("htmx:afterSettle", {});

  expect(detail.swapSpec).toEqual({ swapDelay: 100, settleDelay: 20 });
  expect(eventNames()).toEqual([
    APP_PAGE_EVENT.navigationStart,
    APP_PAGE_EVENT.beforeSwap,
    APP_PAGE_EVENT.afterSwap,
    APP_PAGE_EVENT.navigationEnd,
  ]);
  expect(recordedEvents[0].detail).toMatchObject({
    navigationType: "traverse",
    source: "fetch",
  });
});

test("leaves explicit and reduced-motion page transitions unchanged", () => {
  const request = requestDetail("/about");
  const explicit = beforeSwapDetail(request);
  explicit.swapOverride = "outerHTML";
  const reduced = beforeSwapDetail(request);

  applyHtmxPageTransition(explicit, document.body, false);
  applyHtmxPageTransition(reduced, document.body, true);

  expect(explicit.swapOverride).toBe("outerHTML");
  expect(reduced.swapOverride).toBeUndefined();
});

test("leaves unsupported history transitions unchanged", () => {
  const nested = {
    historyElt: document.createElement("main"),
    swapSpec: { swapDelay: 0, settleDelay: 0 },
  };
  const reduced = {
    historyElt: document.body,
    swapSpec: { swapDelay: 0, settleDelay: 0 },
  };

  applyHtmxHistoryPageTransition(nested, document.body, false);
  applyHtmxHistoryPageTransition(reduced, document.body, true);

  expect(nested.swapSpec).toEqual({ swapDelay: 0, settleDelay: 0 });
  expect(reduced.swapSpec).toEqual({ swapDelay: 0, settleDelay: 0 });
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

test("maps compatible preserved roots into HTMX markup before island cleanup", () => {
  document.body.innerHTML = '<div id="dock" data-app-preserve><audio></audio></div>';
  const dock = document.getElementById("dock");
  const request = requestDetail("/about");
  const swap = beforeSwapDetail(
    request,
    true,
    pageHtml().replace("<body></body>", '<body><div id="dock" data-app-preserve></div></body>'),
  );
  notify("htmx:beforeRequest", request);
  notify("htmx:beforeSwap", swap);
  const incoming = new DOMParser().parseFromString(swap.serverResponse, "text/html");
  expect(incoming.getElementById("dock")?.getAttribute("hx-preserve")).toBe("true");
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ preservedRoots: [dock] });
  expect(dock?.isConnected).toBe(true);
});

test("does not preserve incompatible component types even with a cached hx-preserve", () => {
  document.body.innerHTML = '<div id="same" data-app-preserve data-solid-island="Counter"></div>';
  const detail = {
    path: "/cached",
    historyElt: document.body,
    swapSpec: { swapDelay: 0, settleDelay: 0 },
    item: {
      content: '<div id="same" data-app-preserve data-solid-island="MusicDock" hx-preserve></div>',
    },
  };
  expect(notify("htmx:historyCacheHit", detail)).toBe(true);
  expect(detail.item.content).not.toContain("hx-preserve");
  expect(recordedEvents.at(-1)?.detail).toMatchObject({ preservedRoots: [] });
});

test("maps preserved roots in a history cache hit", () => {
  document.body.innerHTML = '<div id="dock" data-app-preserve></div>';
  const detail = {
    path: "/cached",
    historyElt: document.body,
    swapSpec: { swapDelay: 0, settleDelay: 0 },
    item: { content: '<div id="dock" data-app-preserve></div>' },
  };
  expect(notify("htmx:historyCacheHit", detail)).toBe(true);
  expect(detail.item.content).toContain('hx-preserve="true"');
  expect(recordedEvents.at(-1)?.detail).toMatchObject({
    preservedRoots: [document.getElementById("dock")],
  });
});

test("maps preserved roots in a history cache miss response", () => {
  document.body.innerHTML = '<div id="dock" data-app-preserve></div>';
  const xhr = new XMLHttpRequest();
  const html = pageHtml().replace(
    "<body></body>",
    '<body><div id="dock" data-app-preserve></div></body>',
  );
  const detail = {
    path: "/restored",
    historyElt: document.body,
    swapSpec: { swapDelay: 0, settleDelay: 0 },
    xhr,
    response: html,
  };
  notify("htmx:historyCacheMiss", detail);
  setXhrResponse(xhr, html);
  xhr.dispatchEvent(new ProgressEvent("load"));
  notify("htmx:historyCacheMissLoad", detail);
  expect(detail.response).toContain('hx-preserve="true"');
  expect(recordedEvents.at(-1)?.detail).toMatchObject({
    preservedRoots: [document.getElementById("dock")],
  });
});

test.each(["response", "cache", "history-response"])(
  "rejects duplicate preservation IDs in %s before cleanup",
  (source) => {
    const invalid = '<div id="dock" data-app-preserve></div><div id="dock"></div>';
    const html = pageHtml().replace("<body></body>", `<body>${invalid}</body>`);
    if (source === "response") {
      const request = requestDetail("/about");
      const swap = beforeSwapDetail(request, true, html);
      notify("htmx:beforeRequest", request);
      expect(notify("htmx:beforeSwap", swap)).toBe(false);
      expect(swap.shouldSwap).toBe(false);
    } else if (source === "cache") {
      expect(
        notify("htmx:historyCacheHit", {
          path: "/cached",
          historyElt: document.body,
          swapSpec: {},
          item: { content: invalid },
        }),
      ).toBe(false);
    } else {
      const xhr = new XMLHttpRequest();
      notify("htmx:historyCacheMiss", {
        path: "/restored",
        historyElt: document.body,
        swapSpec: {},
        xhr,
      });
      setXhrResponse(xhr, html);
      const downstream = vi.fn();
      xhr.addEventListener("load", downstream);
      xhr.dispatchEvent(new ProgressEvent("load"));
      expect(downstream).not.toHaveBeenCalled();
    }
    expect(navigate).toHaveBeenCalledOnce();
    expect(eventNames()).not.toContain(APP_PAGE_EVENT.beforeSwap);
    expect(recordedEvents.at(-1)?.detail).toMatchObject({ outcome: "fallback" });
  },
);

test("validates history before HTMX's already registered onload handler", () => {
  const xhr = new XMLHttpRequest();
  const htmxLoad = vi.fn();
  xhr.onload = htmxLoad;
  notify("htmx:historyCacheMiss", {
    path: "/restored",
    historyElt: document.body,
    swapSpec: {},
    xhr,
  });
  setXhrResponse(xhr, pageHtml({ ...CURRENT_PROTOCOL, buildId: "next" }));
  xhr.dispatchEvent(new ProgressEvent("load"));
  expect(htmxLoad).not.toHaveBeenCalled();
  expect(navigate).toHaveBeenCalledOnce();
});

test("delegates a valid history response to the original handler and restores it", () => {
  const xhr = new XMLHttpRequest();
  const htmxLoad = vi.fn();
  xhr.onload = htmxLoad;
  notify("htmx:historyCacheMiss", {
    path: "/restored",
    historyElt: document.body,
    swapSpec: {},
    xhr,
  });
  setXhrResponse(xhr, pageHtml());
  xhr.dispatchEvent(new ProgressEvent("load"));
  expect(htmxLoad).toHaveBeenCalledOnce();
  expect(xhr.onload).toBe(htmxLoad);
  expect(navigate).not.toHaveBeenCalled();
});
