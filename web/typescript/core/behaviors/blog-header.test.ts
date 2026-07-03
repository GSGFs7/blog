import { fireEvent } from "@solidjs/testing-library";
import { afterEach, expect, test, vi } from "vitest";

import { setupBehaviors } from ".";

let teardown: (() => void) | undefined;

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.body.innerHTML = "";
});

test("mounts a blog header loaded by htmx", () => {
  teardown = setupBehaviors();
  document.body.innerHTML = `
    <main id="swap-target">
      <div data-blog-header>
        <img data-blog-header-image>
        <span data-blog-pointer-x></span>
        <span data-blog-pointer-y></span>
      </div>
    </main>
  `;

  const target = document.getElementById("swap-target")!;
  const card = target.querySelector<HTMLElement>("[data-blog-header]")!;
  vi.spyOn(card, "getBoundingClientRect").mockReturnValue({
    bottom: 100,
    height: 100,
    left: 0,
    right: 200,
    top: 0,
    width: 200,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });

  target.dispatchEvent(
    new CustomEvent("htmx:load", {
      bubbles: true,
      detail: { elt: target },
    }),
  );
  fireEvent.mouseMove(card, { clientX: 150, clientY: 25 });

  expect(card.querySelector("img")?.style.transform).toBe("scale(1.1) translateX(12.5px)");
  expect(card.querySelector("[data-blog-pointer-x]")).toHaveTextContent("0.50");
  expect(card.querySelector("[data-blog-pointer-y]")).toHaveTextContent("-0.50");
});

test("does not bind a blog header more than once", () => {
  document.body.innerHTML = `
    <div data-blog-header>
      <img data-blog-header-image>
    </div>
  `;
  const card = document.querySelector<HTMLElement>("[data-blog-header]")!;
  const getBoundingClientRect = vi.spyOn(card, "getBoundingClientRect").mockReturnValue({
    bottom: 100,
    height: 100,
    left: 0,
    right: 100,
    top: 0,
    width: 100,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });

  teardown = setupBehaviors();
  card.dispatchEvent(new CustomEvent("htmx:load", { bubbles: true, detail: { elt: card } }));
  fireEvent.mouseMove(card, { clientX: 50, clientY: 50 });

  expect(getBoundingClientRect).toHaveBeenCalledOnce();
});

test("teardown removes behavior listeners", () => {
  document.body.innerHTML = `
    <div data-blog-header>
      <img data-blog-header-image>
    </div>
  `;
  const card = document.querySelector<HTMLElement>("[data-blog-header]")!;
  const getBoundingClientRect = vi.spyOn(card, "getBoundingClientRect");
  teardown = setupBehaviors();

  teardown();
  teardown = undefined;
  fireEvent.mouseMove(card, { clientX: 50, clientY: 50 });

  expect(getBoundingClientRect).not.toHaveBeenCalled();
});
