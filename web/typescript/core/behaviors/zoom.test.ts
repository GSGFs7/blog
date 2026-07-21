import { fireEvent } from "@solidjs/testing-library";
import { afterEach, expect, test, vi } from "vitest";

import { setupBehaviors } from ".";

let teardown: (() => void) | undefined;

function prepareImage(image: HTMLImageElement) {
  Object.defineProperties(image, {
    naturalHeight: { configurable: true, value: 400 },
    naturalWidth: { configurable: true, value: 800 },
  });
  vi.spyOn(image, "getBoundingClientRect").mockReturnValue({
    bottom: 300,
    height: 200,
    left: 100,
    right: 500,
    top: 100,
    width: 400,
    x: 100,
    y: 100,
    toJSON: () => ({}),
  });
}

afterEach(() => {
  teardown?.();
  teardown = undefined;
  vi.useRealTimers();
  document.body.innerHTML = "";
});

test("zooms an image and closes it with Escape", () => {
  vi.useFakeTimers();
  document.body.innerHTML = '<article class="markdown-body"><img alt="test"></article>';
  const image = document.querySelector("img")!;
  prepareImage(image);
  teardown = setupBehaviors();

  fireEvent.click(image);
  expect(image).toHaveClass("is-zoomed");
  expect(document.getElementById("zoom-overlay")).toHaveClass("is-visible");

  fireEvent.keyDown(window, { key: "Escape" });
  expect(document.getElementById("zoom-overlay")).not.toHaveClass("is-visible");
  vi.advanceTimersByTime(300);
  expect(image).not.toHaveClass("is-zoomed");
});

test("mounts swapped images once", () => {
  document.body.innerHTML = '<main id="swap-target"></main>';
  teardown = setupBehaviors();
  const target = document.getElementById("swap-target")!;
  target.innerHTML = '<article class="markdown-body"><img alt="test"></article>';
  const image = target.querySelector("img")!;
  prepareImage(image);

  for (let index = 0; index < 2; index += 1) {
    target.dispatchEvent(
      new CustomEvent("htmx:load", {
        bubbles: true,
        detail: { elt: target },
      }),
    );
  }
  fireEvent.click(image);

  expect(image).toHaveClass("is-zoomed");
  expect(document.getElementById("zoom-overlay")).toHaveClass("is-visible");
});

test("recreates the overlay after htmx page navigation", () => {
  document.body.innerHTML = '<article class="markdown-body"><img alt="first"></article>';
  teardown = setupBehaviors();
  const initialOverlay = document.getElementById("zoom-overlay");

  document.body.innerHTML = '<article class="markdown-body"><img alt="second"></article>';
  const image = document.querySelector("img")!;
  prepareImage(image);
  document.body.dispatchEvent(
    new CustomEvent("htmx:load", {
      bubbles: true,
      detail: { elt: document.body },
    }),
  );

  const replacementOverlay = document.getElementById("zoom-overlay");
  expect(initialOverlay).not.toBeInTheDocument();
  expect(replacementOverlay).not.toBe(initialOverlay);

  fireEvent.click(image);
  expect(replacementOverlay).toHaveClass("is-visible");
});

test("teardown restores the zoomed image and removes the overlay", () => {
  document.body.innerHTML = '<article class="markdown-body"><img alt="test"></article>';
  const image = document.querySelector("img")!;
  prepareImage(image);
  teardown = setupBehaviors();
  fireEvent.click(image);

  teardown();
  teardown = undefined;

  expect(image).not.toHaveClass("is-zoomed");
  expect(image.style.transform).toBe("");
  expect(document.getElementById("zoom-overlay")).not.toBeInTheDocument();
});
