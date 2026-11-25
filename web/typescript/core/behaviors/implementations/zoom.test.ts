import { fireEvent } from "@solidjs/testing-library";
import { afterEach, expect, test, vi } from "vitest";

import { runPageSwap } from "@/test/page-lifecycle";

import { setupBehaviors } from "../manager";
import { waitForBehaviorMount } from "../test-utils";

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
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

test("zooms an image in a body clone and closes it with Escape", async () => {
  vi.useFakeTimers();
  document.body.innerHTML =
    '<article class="markdown-body"><img src="https://example.invalid/pic.png" alt="test"></article>';
  const image = document.querySelector("img")!;
  prepareImage(image);
  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(image).toHaveClass("is-zoomable");
  fireEvent.click(image);
  const clone = document.querySelector<HTMLImageElement>("img.zoom-image");
  expect(clone).not.toBeNull();
  expect(clone?.parentElement).toBe(document.body);
  expect(clone?.src).toBe("https://example.invalid/pic.png");
  expect(clone?.alt).toBe("test");
  expect(image).toHaveClass("is-zoomed");
  expect(document.getElementById("zoom-overlay")).toHaveClass("is-visible");

  fireEvent.keyDown(window, { key: "Escape" });
  expect(document.getElementById("zoom-overlay")).not.toHaveClass("is-visible");
  expect(clone?.style.transform).toBe("");
  vi.advanceTimersByTime(300);
  expect(document.querySelector("img.zoom-image")).toBeNull();
  expect(image).not.toHaveClass("is-zoomed");
});

test("uses the available screen width when zooming on mobile", async () => {
  vi.spyOn(window, "innerWidth", "get").mockReturnValue(375);
  vi.spyOn(window, "innerHeight", "get").mockReturnValue(667);
  document.body.innerHTML = '<article class="markdown-body"><img alt="test"></article>';
  const image = document.querySelector("img")!;
  Object.defineProperties(image, {
    naturalHeight: { configurable: true, value: 800 },
    naturalWidth: { configurable: true, value: 1600 },
  });
  vi.spyOn(image, "getBoundingClientRect").mockReturnValue({
    bottom: 255.5,
    height: 155.5,
    left: 32,
    right: 343,
    top: 100,
    width: 311,
    x: 32,
    y: 100,
    toJSON: () => ({}),
  });
  teardown = setupBehaviors();
  await waitForBehaviorMount();

  fireEvent.click(image);

  const clone = document.querySelector<HTMLImageElement>("img.zoom-image")!;
  const scale = Number(clone.style.transform.match(/scale\(([^)]+)\)/)?.[1]);
  expect(scale).toBeCloseTo(343 / 311);
  expect(scale).toBeGreaterThan(1);
});

test("closes the zoomed image when clicking the clone", async () => {
  vi.useFakeTimers();
  document.body.innerHTML =
    '<article class="markdown-body"><details class="spoiler" open><summary>spoiler</summary><img alt="hidden"></details></article>';
  const image = document.querySelector("img")!;
  prepareImage(image);
  teardown = setupBehaviors();
  await waitForBehaviorMount();

  fireEvent.click(image);
  const clone = document.querySelector<HTMLImageElement>("img.zoom-image")!;
  expect(clone.parentElement).toBe(document.body);

  fireEvent.click(clone);
  expect(document.getElementById("zoom-overlay")).not.toHaveClass("is-visible");
  vi.advanceTimersByTime(300);
  expect(document.querySelector("img.zoom-image")).toBeNull();
  expect(image).not.toHaveClass("is-zoomed");
});

test("tracks document coordinates across scroll and cleans up pending clones on quick reopen", async () => {
  vi.useFakeTimers();
  let scrollY = 200;
  vi.spyOn(window, "scrollY", "get").mockImplementation(() => scrollY);
  document.body.innerHTML = '<article class="markdown-body"><img alt="test"></article>';
  const image = document.querySelector("img")!;
  prepareImage(image);
  const rectSpy = vi.spyOn(image, "getBoundingClientRect");
  teardown = setupBehaviors();
  await waitForBehaviorMount();

  fireEvent.click(image);
  const firstClone = document.querySelector<HTMLImageElement>("img.zoom-image")!;
  expect(firstClone.style.top).toBe("300px");

  scrollY = 260;
  rectSpy.mockReturnValue({
    bottom: 240,
    height: 200,
    left: 100,
    right: 500,
    top: 40,
    width: 400,
    x: 100,
    y: 40,
    toJSON: () => ({}),
  });
  fireEvent.scroll(window);
  expect(firstClone.style.transform).toBe("");
  expect(firstClone.style.pointerEvents).toBe("none");

  fireEvent.click(image);
  const clones = document.querySelectorAll("img.zoom-image");
  expect(clones).toHaveLength(1);
  expect(clones[0]).not.toBe(firstClone);
  expect(firstClone).not.toBeInTheDocument();
});

test("ignores images inside Solid islands", async () => {
  document.body.innerHTML =
    '<article class="markdown-body"><div data-solid-island="MusicTrack"><img alt="cover"></div></article>';
  const image = document.querySelector("img")!;
  prepareImage(image);
  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(image).not.toHaveClass("is-zoomable");
  fireEvent.click(image);
  expect(document.querySelector("img.zoom-image")).toBeNull();
});

test("mounts swapped images once", async () => {
  teardown = setupBehaviors();
  runPageSwap(() => {
    document.body.innerHTML =
      '<main id="swap-target"><article class="markdown-body"><img alt="test"></article></main>';
  });
  await waitForBehaviorMount();

  const target = document.getElementById("swap-target")!;
  const image = target.querySelector("img")!;
  prepareImage(image);

  fireEvent.click(image);

  expect(image).toHaveClass("is-zoomed");
  expect(document.querySelector("img.zoom-image")).not.toBeNull();
  expect(document.getElementById("zoom-overlay")).toHaveClass("is-visible");
});

test("recreates the overlay after page navigation", async () => {
  document.body.innerHTML = '<article class="markdown-body"><img alt="first"></article>';
  teardown = setupBehaviors();
  const initialOverlay = document.getElementById("zoom-overlay");

  runPageSwap(() => {
    document.body.innerHTML = '<article class="markdown-body"><img alt="second"></article>';
  });
  await waitForBehaviorMount();

  const image = document.querySelector("img")!;
  prepareImage(image);

  const replacementOverlay = document.getElementById("zoom-overlay");
  expect(initialOverlay).not.toBeInTheDocument();
  expect(replacementOverlay).not.toBe(initialOverlay);

  fireEvent.click(image);
  expect(replacementOverlay).toHaveClass("is-visible");
});

test("teardown restores the zoomed image and removes the clone and overlay", async () => {
  document.body.innerHTML = '<article class="markdown-body"><img alt="test"></article>';
  const image = document.querySelector("img")!;
  prepareImage(image);
  teardown = setupBehaviors();
  await waitForBehaviorMount();
  expect(image).toHaveClass("is-zoomable");
  fireEvent.click(image);
  expect(document.querySelector("img.zoom-image")).not.toBeNull();

  teardown();
  teardown = undefined;

  expect(image).not.toHaveClass("is-zoomed");
  expect(image).not.toHaveClass("is-zoomable");
  expect(document.querySelector("img.zoom-image")).toBeNull();
  expect(document.getElementById("zoom-overlay")).not.toBeInTheDocument();
});
