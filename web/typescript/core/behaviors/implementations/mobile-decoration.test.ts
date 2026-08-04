import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { setupBehaviors } from "../index";
import { runPageSwap } from "../../../test/page-lifecycle";
import { waitForBehaviorMount } from "../test-utils";

let teardown: (() => void) | undefined;
let matchMediaMock: ReturnType<typeof vi.fn>;
let mockMQL: {
  matches: boolean;
  listeners: Set<(event: { matches: boolean }) => void>;
  addEventListener: ReturnType<typeof vi.fn>;
  removeEventListener: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  mockMQL = {
    matches: false,
    listeners: new Set(),
    addEventListener: vi.fn((_type: string, listener: (event: { matches: boolean }) => void) => {
      mockMQL.listeners.add(listener);
    }),
    removeEventListener: vi.fn((_type: string, listener: (event: { matches: boolean }) => void) => {
      mockMQL.listeners.delete(listener);
    }),
  };
  matchMediaMock = vi.fn(() => mockMQL);
  vi.stubGlobal("matchMedia", matchMediaMock);
});

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

function changeMediaQuery(matches: boolean) {
  mockMQL.matches = matches;
  for (const listener of mockMQL.listeners) {
    listener({ matches });
  }
}

test("applies is-decorated on desktop", async () => {
  document.body.innerHTML = "<div data-mobile-undecorated>content</div>";
  teardown = setupBehaviors();
  await waitForBehaviorMount();
  expect(document.querySelector("[data-mobile-undecorated]")).toHaveClass("is-decorated");
});

test("removes is-decorated on mobile", async () => {
  mockMQL.matches = true;
  document.body.innerHTML = "<div data-mobile-undecorated>content</div>";
  teardown = setupBehaviors();
  await waitForBehaviorMount();
  expect(document.querySelector("[data-mobile-undecorated]")).not.toHaveClass("is-decorated");
});

test("toggles class when viewport crosses breakpoint", async () => {
  document.body.innerHTML = "<div data-mobile-undecorated>content</div>";
  teardown = setupBehaviors();
  await waitForBehaviorMount();
  const el = document.querySelector<HTMLElement>("[data-mobile-undecorated]")!;

  expect(el).toHaveClass("is-decorated");

  changeMediaQuery(true);
  expect(el).not.toHaveClass("is-decorated");

  changeMediaQuery(false);
  expect(el).toHaveClass("is-decorated");
});

test("destroys stops listener and sets desktop state", async () => {
  document.body.innerHTML = "<div data-mobile-undecorated>content</div>";
  teardown = setupBehaviors();
  await waitForBehaviorMount();
  expect(document.querySelector("[data-mobile-undecorated]")).toHaveClass("is-decorated");

  teardown();
  teardown = undefined;

  expect(document.querySelector("[data-mobile-undecorated]")).toHaveClass("is-decorated");
  expect(mockMQL.listeners.size).toBe(0);
});

test("applies current state to swapped content", async () => {
  teardown = setupBehaviors();

  runPageSwap(() => {
    document.body.innerHTML =
      '<main id="swap-target"><div data-mobile-undecorated>content</div></main>';
  });
  await waitForBehaviorMount();

  const target = document.getElementById("swap-target")!;
  expect(target.querySelector("[data-mobile-undecorated]")).toHaveClass("is-decorated");
});

test("skips media query listener when no elements on page", async () => {
  document.body.innerHTML = "<div>no decoration</div>";
  teardown = setupBehaviors();
  await waitForBehaviorMount();
  expect(matchMediaMock).not.toHaveBeenCalled();
});

test("stops listener when all elements are removed by a page swap", async () => {
  document.body.innerHTML =
    '<main id="swap-target"><div data-mobile-undecorated>content</div></main>';
  teardown = setupBehaviors();
  await waitForBehaviorMount();
  expect(matchMediaMock).toHaveBeenCalledTimes(1);

  runPageSwap(() => {
    document.body.innerHTML = "<main><div>no decoration</div></main>";
  });
  await waitForBehaviorMount();

  expect(mockMQL.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
});
