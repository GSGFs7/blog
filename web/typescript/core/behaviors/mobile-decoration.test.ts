import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { setupBehaviors } from ".";

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

test("applies is-decorated on desktop", () => {
  document.body.innerHTML = "<div data-mobile-undecorated>content</div>";
  teardown = setupBehaviors();
  expect(document.querySelector("[data-mobile-undecorated]")).toHaveClass("is-decorated");
});

test("removes is-decorated on mobile", () => {
  mockMQL.matches = true;
  document.body.innerHTML = "<div data-mobile-undecorated>content</div>";
  teardown = setupBehaviors();
  expect(document.querySelector("[data-mobile-undecorated]")).not.toHaveClass("is-decorated");
});

test("toggles class when viewport crosses breakpoint", () => {
  document.body.innerHTML = "<div data-mobile-undecorated>content</div>";
  teardown = setupBehaviors();
  const el = document.querySelector<HTMLElement>("[data-mobile-undecorated]")!;

  expect(el).toHaveClass("is-decorated");

  changeMediaQuery(true);
  expect(el).not.toHaveClass("is-decorated");

  changeMediaQuery(false);
  expect(el).toHaveClass("is-decorated");
});

test("destroys stops listener and sets desktop state", () => {
  document.body.innerHTML = "<div data-mobile-undecorated>content</div>";
  teardown = setupBehaviors();
  expect(document.querySelector("[data-mobile-undecorated]")).toHaveClass("is-decorated");

  teardown();
  teardown = undefined;

  expect(document.querySelector("[data-mobile-undecorated]")).toHaveClass("is-decorated");
  expect(mockMQL.listeners.size).toBe(0);
});

test("applies current state to htmx-swapped content", () => {
  document.body.innerHTML = '<main id="swap-target"></main>';
  teardown = setupBehaviors();

  const target = document.getElementById("swap-target")!;
  target.innerHTML = "<div data-mobile-undecorated>content</div>";

  target.dispatchEvent(
    new CustomEvent("htmx:load", {
      bubbles: true,
      detail: { elt: target },
    }),
  );

  expect(target.querySelector("[data-mobile-undecorated]")).toHaveClass("is-decorated");
});

test("skips media query listener when no elements on page", () => {
  document.body.innerHTML = "<div>no decoration</div>";
  teardown = setupBehaviors();
  expect(matchMediaMock).not.toHaveBeenCalled();
});

test("stops listener when all elements are removed via htmx", () => {
  document.body.innerHTML =
    '<main id="swap-target"><div data-mobile-undecorated>content</div></main>';
  teardown = setupBehaviors();
  expect(matchMediaMock).toHaveBeenCalledTimes(1);

  const target = document.getElementById("swap-target")!;
  target.innerHTML = "<div>no decoration</div>";

  target.dispatchEvent(
    new CustomEvent("htmx:load", {
      bubbles: true,
      detail: { elt: target },
    }),
  );

  expect(mockMQL.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
});
