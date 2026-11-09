import { APP_PAGE_EVENT } from "../contracts";
import { setupNavigationStatus } from "./navigation-status";

let teardown: (() => void) | undefined;

function emit(name: string, navigationId: number, detail = {}) {
  document.dispatchEvent(new CustomEvent(name, { detail: { navigationId, ...detail } }));
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  teardown?.();
  teardown = undefined;
  vi.useRealTimers();
});

test.each(["completed", "cancelled", "fallback"])("clears loading on %s", (outcome) => {
  teardown = setupNavigationStatus(document);
  emit(APP_PAGE_EVENT.navigationStart, 1);
  vi.advanceTimersByTime(150);
  expect(document.documentElement).toHaveAttribute("data-navigation-loading");

  emit(APP_PAGE_EVENT.navigationEnd, 1, { outcome });
  expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");
});

test("survives body replacement and clears loading on failure", () => {
  teardown = setupNavigationStatus(document);
  emit(APP_PAGE_EVENT.navigationStart, 1);
  document.body.replaceWith(document.createElement("body"));
  vi.advanceTimersByTime(150);
  expect(document.documentElement).toHaveAttribute("data-navigation-loading");

  emit(APP_PAGE_EVENT.navigationError, 1);
  expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");
});

test("ignores stale completion and failure events during a newer navigation", () => {
  teardown = setupNavigationStatus(document);
  emit(APP_PAGE_EVENT.navigationStart, 1);
  emit(APP_PAGE_EVENT.navigationStart, 2);
  emit(APP_PAGE_EVENT.navigationEnd, 1);
  emit(APP_PAGE_EVENT.navigationError, 1);
  vi.advanceTimersByTime(150);
  expect(document.documentElement).toHaveAttribute("data-navigation-loading");

  emit(APP_PAGE_EVENT.navigationEnd, 2);
  expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");
});

test("background revalidation does not start or interrupt loading", () => {
  teardown = setupNavigationStatus(document);
  emit(APP_PAGE_EVENT.navigationStart, 1, { reason: "revalidation" });
  expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");

  emit(APP_PAGE_EVENT.navigationStart, 2);
  emit(APP_PAGE_EVENT.navigationStart, 3, { reason: "revalidation" });
  emit(APP_PAGE_EVENT.navigationEnd, 3);
  vi.advanceTimersByTime(150);
  expect(document.documentElement).toHaveAttribute("data-navigation-loading");
});

test("teardown clears loading and removes listeners", () => {
  teardown = setupNavigationStatus(document);
  emit(APP_PAGE_EVENT.navigationStart, 1);
  teardown();
  emit(APP_PAGE_EVENT.navigationStart, 2);
  vi.runAllTimers();
  expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");
});

test.each([APP_PAGE_EVENT.navigationEnd, APP_PAGE_EVENT.navigationError])(
  "never shows loading when a fast navigation emits %s",
  (event) => {
    teardown = setupNavigationStatus(document);
    emit(APP_PAGE_EVENT.navigationStart, 1);
    vi.advanceTimersByTime(149);
    expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");

    emit(event, 1);
    vi.runAllTimers();
    expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");
  },
);

test("restarts the delay when a pending navigation is superseded", () => {
  teardown = setupNavigationStatus(document);
  emit(APP_PAGE_EVENT.navigationStart, 1);
  vi.advanceTimersByTime(100);
  emit(APP_PAGE_EVENT.navigationStart, 2);
  emit(APP_PAGE_EVENT.navigationEnd, 1);
  vi.advanceTimersByTime(50);
  expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");

  vi.advanceTimersByTime(100);
  expect(document.documentElement).toHaveAttribute("data-navigation-loading");
});

test("keeps a visible loader when a navigation is superseded", () => {
  teardown = setupNavigationStatus(document);
  emit(APP_PAGE_EVENT.navigationStart, 1);
  vi.advanceTimersByTime(150);
  emit(APP_PAGE_EVENT.navigationStart, 2);
  emit(APP_PAGE_EVENT.navigationEnd, 1);
  expect(document.documentElement).toHaveAttribute("data-navigation-loading");

  emit(APP_PAGE_EVENT.navigationEnd, 2);
  expect(document.documentElement).not.toHaveAttribute("data-navigation-loading");
});
