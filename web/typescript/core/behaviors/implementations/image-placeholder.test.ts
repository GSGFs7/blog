import { fireEvent } from "@solidjs/testing-library";
import { afterEach, expect, test } from "vitest";

import { runPageSwap } from "../../../test/page-lifecycle";
import { setupBehaviors } from "../manager";
import { waitForBehaviorMount } from "../test-utils";

let teardown: (() => void) | undefined;

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.body.innerHTML = "";
});

test("removes the placeholder blur marker after the image loads", async () => {
  document.body.innerHTML = '<img class="image-placeholder" src="/pending.jpg" alt="test">';
  const image = document.querySelector("img")!;
  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(image).toHaveClass("image-placeholder");
  fireEvent.load(image);

  expect(image).not.toHaveClass("image-placeholder");
});

test("removes the marker from an image loaded before mount", async () => {
  document.body.innerHTML = '<img class="image-placeholder" src="/cached.jpg" alt="test">';
  const image = document.querySelector("img")!;
  Object.defineProperties(image, {
    complete: { configurable: true, value: true },
    naturalWidth: { configurable: true, value: 100 },
  });

  teardown = setupBehaviors();
  await waitForBehaviorMount();

  expect(image).not.toHaveClass("image-placeholder");
});

test("handles placeholder images mounted after a page swap", async () => {
  teardown = setupBehaviors();
  runPageSwap(() => {
    document.body.innerHTML =
      '<main id="swap-target"><img class="image-placeholder" src="/next.jpg" alt="test"></main>';
  });
  await waitForBehaviorMount();

  const image = document.querySelector("img")!;
  fireEvent.load(image);

  expect(image).not.toHaveClass("image-placeholder");
});
