import { fireEvent } from "@solidjs/testing-library";
import { afterEach, expect, test, vi } from "vitest";

import { runPageSwap } from "../../../test/page-lifecycle";
import { setupBehaviors } from "../manager";
import { waitForBehaviorMount } from "../test-utils";

let teardown: (() => void) | undefined;

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.body.innerHTML = "";
});

test("mounts a blog header after a page swap", async () => {
  teardown = setupBehaviors();
  runPageSwap(() => {
    document.body.innerHTML = `
      <main id="swap-target">
        <div data-blog-header>
          <img data-blog-header-image>
          <span data-blog-pointer-x></span>
          <span data-blog-pointer-y></span>
        </div>
      </main>
    `;
  });
  await waitForBehaviorMount();

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

  fireEvent.mouseMove(card, { clientX: 150, clientY: 25 });

  expect(card.querySelector("img")?.style.transform).toBe("scale(1.1) translateX(12.5px)");
  expect(card.querySelector("[data-blog-pointer-x]")).toHaveTextContent("0.50");
  expect(card.querySelector("[data-blog-pointer-y]")).toHaveTextContent("-0.50");
});

test("does not retain blog header listeners from the previous page", async () => {
  document.body.innerHTML = `
    <div data-blog-header>
      <img data-blog-header-image>
    </div>
  `;
  const previousCard = document.querySelector<HTMLElement>("[data-blog-header]")!;
  const previousRect = vi.spyOn(previousCard, "getBoundingClientRect");

  teardown = setupBehaviors();
  runPageSwap(() => {
    document.body.innerHTML = `
      <div data-blog-header>
        <img data-blog-header-image>
      </div>
    `;
  });
  await waitForBehaviorMount();

  const card = document.querySelector<HTMLElement>("[data-blog-header]")!;
  const currentRect = vi.spyOn(card, "getBoundingClientRect").mockReturnValue({
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

  fireEvent.mouseMove(previousCard, { clientX: 50, clientY: 50 });
  fireEvent.mouseMove(card, { clientX: 50, clientY: 50 });

  expect(previousRect).not.toHaveBeenCalled();
  expect(currentRect).toHaveBeenCalledOnce();
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
