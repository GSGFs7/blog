import { afterEach, expect, test, vi } from "vitest";

import { runPageSwap } from "../../test/page-lifecycle";
import { startBehaviorRuntime } from "./runtime";
import { waitForBehaviorMount } from "./test-utils";
import type { BehaviorFactory } from "./types";

let teardown: (() => void) | undefined;

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.body.innerHTML = "";
});

test("loads only behaviors matching the current root", async () => {
  document.body.innerHTML = "<main data-blog-header></main>";

  const blogMount = vi.fn();
  const markdownMount = vi.fn();
  const blogLoad = vi.fn<() => Promise<BehaviorFactory>>(async () => () => ({
    mount: blogMount,
  }));
  const markdownLoad = vi.fn<() => Promise<BehaviorFactory>>(async () => () => ({
    mount: markdownMount,
  }));

  teardown = startBehaviorRuntime(document, [
    { selector: "[data-blog-header]", load: blogLoad },
    { selector: ".markdown-body img", load: markdownLoad },
  ]);
  await waitForBehaviorMount();

  expect(blogLoad).toHaveBeenCalledOnce();
  expect(markdownLoad).not.toHaveBeenCalled();
  expect(blogMount).toHaveBeenCalledOnce();
  expect(markdownMount).not.toHaveBeenCalled();
});

test("mounts inline behaviors synchronously without waiting for lazy behaviors", async () => {
  const inlineMount = vi.fn();
  const lazyMount = vi.fn();
  let resolveLazy!: (factory: BehaviorFactory) => void;
  const lazyLoad = vi.fn(
    () =>
      new Promise<BehaviorFactory>((resolve) => {
        resolveLazy = resolve;
      }),
  );

  teardown = startBehaviorRuntime(document, [
    { selector: "[data-inline]", inline: () => ({ mount: inlineMount }) },
    { selector: "[data-lazy]", load: lazyLoad },
  ]);
  runPageSwap(() => {
    document.body.innerHTML = "<main data-inline data-lazy></main>";
  });

  expect(inlineMount).toHaveBeenCalledOnce();
  expect(lazyLoad).toHaveBeenCalledOnce();
  expect(lazyMount).not.toHaveBeenCalled();

  resolveLazy(() => ({ mount: lazyMount }));
  await waitForBehaviorMount();
  expect(lazyMount).toHaveBeenCalledOnce();
});

test("mounts each lazy behavior as soon as its own chunk loads", async () => {
  const fastMount = vi.fn();
  const slowMount = vi.fn();
  let resolveSlow!: (factory: BehaviorFactory) => void;
  const slowLoad = new Promise<BehaviorFactory>((resolve) => {
    resolveSlow = resolve;
  });

  teardown = startBehaviorRuntime(document, [
    { selector: "[data-fast]", load: async () => () => ({ mount: fastMount }) },
    { selector: "[data-slow]", load: () => slowLoad },
  ]);
  runPageSwap(() => {
    document.body.innerHTML = "<main data-fast data-slow></main>";
  });
  await waitForBehaviorMount();

  expect(fastMount).toHaveBeenCalledOnce();
  expect(slowMount).not.toHaveBeenCalled();

  resolveSlow(() => ({ mount: slowMount }));
  await waitForBehaviorMount();
  expect(slowMount).toHaveBeenCalledOnce();
});

test("does not mount a behavior after its page was replaced", async () => {
  document.body.innerHTML = "<main></main>";

  let resolveOld!: (factory: BehaviorFactory) => void;
  let resolveNew!: (factory: BehaviorFactory) => void;
  const oldLoad = new Promise<BehaviorFactory>((resolve) => {
    resolveOld = resolve;
  });
  const newLoad = new Promise<BehaviorFactory>((resolve) => {
    resolveNew = resolve;
  });
  const load = vi
    .fn<() => Promise<BehaviorFactory>>()
    .mockReturnValueOnce(oldLoad)
    .mockReturnValueOnce(newLoad);
  const oldMount = vi.fn();
  const newMount = vi.fn();

  teardown = startBehaviorRuntime(document, [{ selector: "[data-behavior]", load }]);
  runPageSwap(() => {
    document.body.innerHTML = '<main data-behavior="old"></main>';
  });
  runPageSwap(() => {
    document.body.innerHTML = '<main data-behavior="new"></main>';
  });

  resolveOld(() => ({ mount: oldMount }));
  resolveNew(() => ({ mount: newMount }));
  await new Promise((resolve) => setTimeout(resolve, 0));

  expect(oldMount).not.toHaveBeenCalled();
  expect(newMount).toHaveBeenCalledOnce();
});
