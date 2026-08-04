import { beforeEach, expect, test, vi } from "vitest";

import {
  parsePageProtocol,
  protocolsMatch,
  readPageProtocol,
  readSessionStorage,
  syncHtmxHistoryGeneration,
  type PageProtocol,
} from "./protocol";

const PROTOCOL: PageProtocol = {
  navigationVersion: "1",
  buildId: "test-build",
};

function pageHtml(protocol: PageProtocol = PROTOCOL, extraHead = ""): string {
  return `<!doctype html>
    <html>
      <head>
        <meta name="app-navigation-version" content="${protocol.navigationVersion}">
        <meta name="app-build-id" content="${protocol.buildId}">
        ${extraHead}
      </head>
      <body></body>
    </html>`;
}

beforeEach(() => {
  sessionStorage.clear();
});

test("reads a complete page protocol", () => {
  const parsed = new DOMParser().parseFromString(pageHtml(), "text/html");

  expect(readPageProtocol(parsed)).toEqual(PROTOCOL);
  expect(parsePageProtocol(pageHtml())).toEqual(PROTOCOL);
});

test.each([
  ["missing navigation version", '<meta name="app-build-id" content="test-build">'],
  ["missing build id", '<meta name="app-navigation-version" content="1">'],
  [
    "blank build id",
    '<meta name="app-navigation-version" content="1"><meta name="app-build-id" content=" ">',
  ],
  [
    "duplicate build id",
    '<meta name="app-navigation-version" content="1"><meta name="app-build-id" content="a"><meta name="app-build-id" content="b">',
  ],
])("rejects %s", (_name, head) => {
  expect(parsePageProtocol(`<html><head>${head}</head><body></body></html>`)).toBeNull();
});

test("matches only identical protocols", () => {
  expect(protocolsMatch(PROTOCOL, { ...PROTOCOL })).toBe(true);
  expect(protocolsMatch(PROTOCOL, { ...PROTOCOL, navigationVersion: "2" })).toBe(false);
  expect(protocolsMatch(PROTOCOL, { ...PROTOCOL, buildId: "next" })).toBe(false);
  expect(protocolsMatch(PROTOCOL, null)).toBe(false);
  expect(protocolsMatch(null, PROTOCOL)).toBe(false);
});

test("reads session storage from the current window", () => {
  expect(readSessionStorage(window)).toBe(window.sessionStorage);
});

test("returns null when the session storage getter throws", () => {
  const view = {
    get sessionStorage(): Storage {
      throw new DOMException("denied", "SecurityError");
    },
  } as Window;

  expect(readSessionStorage(view)).toBeNull();
});

test("clears history when the generation changes", () => {
  sessionStorage.setItem("htmx-history-cache", "old-cache");
  sessionStorage.setItem("app-navigation-generation", "1:old-build");

  syncHtmxHistoryGeneration(sessionStorage, PROTOCOL);

  expect(sessionStorage.getItem("htmx-history-cache")).toBeNull();
  expect(sessionStorage.getItem("app-navigation-generation")).toBe("1:test-build");
});

test("preserves history when the generation matches", () => {
  sessionStorage.setItem("htmx-history-cache", "current-cache");
  sessionStorage.setItem("app-navigation-generation", "1:test-build");

  syncHtmxHistoryGeneration(sessionStorage, PROTOCOL);

  expect(sessionStorage.getItem("htmx-history-cache")).toBe("current-cache");
});

test("clears history and the marker for a missing current protocol", () => {
  sessionStorage.setItem("htmx-history-cache", "old-cache");
  sessionStorage.setItem("app-navigation-generation", "1:old-build");

  syncHtmxHistoryGeneration(sessionStorage, null);

  expect(sessionStorage.getItem("htmx-history-cache")).toBeNull();
  expect(sessionStorage.getItem("app-navigation-generation")).toBeNull();
});

test("tolerates unavailable storage", () => {
  const storage = {
    getItem: vi.fn(() => {
      throw new DOMException("denied");
    }),
  } as unknown as Storage;

  expect(() => syncHtmxHistoryGeneration(storage, PROTOCOL)).not.toThrow();
});
