import { APP_PAGE_EVENT } from "../index";
import { setupPageTransition } from "./page-transition";

let teardown: (() => void) | undefined;

function emit(name: string, detail: unknown): void {
  document.dispatchEvent(new CustomEvent(name, { detail }));
}

function swapDetail(navigationId: number, root = document.body) {
  return { navigationId, root };
}

afterEach(() => {
  teardown?.();
  teardown = undefined;
  document.body.removeAttribute("data-page-transition");
});

test("tracks leaving and entering phases until navigation completes", () => {
  teardown = setupPageTransition(document, { prefersReducedMotion: () => false });

  emit(APP_PAGE_EVENT.beforeSwap, swapDetail(1));
  expect(document.body).toHaveAttribute("data-page-transition", "leaving");

  emit(APP_PAGE_EVENT.afterSwap, swapDetail(1));
  expect(document.body).toHaveAttribute("data-page-transition", "entering");

  emit(APP_PAGE_EVENT.navigationEnd, { navigationId: 1 });
  expect(document.body).not.toHaveAttribute("data-page-transition");
});

test("clears the active phase when navigation fails", () => {
  teardown = setupPageTransition(document, { prefersReducedMotion: () => false });

  emit(APP_PAGE_EVENT.beforeSwap, swapDetail(1));
  emit(APP_PAGE_EVENT.navigationError, { navigationId: 1 });

  expect(document.body).not.toHaveAttribute("data-page-transition");
});

test("does not let stale navigation events modify the active phase", () => {
  teardown = setupPageTransition(document, { prefersReducedMotion: () => false });

  emit(APP_PAGE_EVENT.beforeSwap, swapDetail(1));
  emit(APP_PAGE_EVENT.beforeSwap, swapDetail(2));
  emit(APP_PAGE_EVENT.afterSwap, swapDetail(1));
  emit(APP_PAGE_EVENT.navigationEnd, { navigationId: 1 });

  expect(document.body).toHaveAttribute("data-page-transition", "leaving");

  emit(APP_PAGE_EVENT.afterSwap, swapDetail(2));
  expect(document.body).toHaveAttribute("data-page-transition", "entering");
});

test("reads reduced motion preference for each navigation", () => {
  let reducedMotion = true;
  teardown = setupPageTransition(document, {
    prefersReducedMotion: () => reducedMotion,
  });

  emit(APP_PAGE_EVENT.beforeSwap, swapDetail(1));
  expect(document.body).not.toHaveAttribute("data-page-transition");

  reducedMotion = false;
  emit(APP_PAGE_EVENT.beforeSwap, swapDetail(2));
  expect(document.body).toHaveAttribute("data-page-transition", "leaving");
});

test("teardown clears state and removes listeners", () => {
  teardown = setupPageTransition(document, { prefersReducedMotion: () => false });
  emit(APP_PAGE_EVENT.beforeSwap, swapDetail(1));

  teardown();
  teardown = undefined;
  emit(APP_PAGE_EVENT.beforeSwap, swapDetail(2));

  expect(document.body).not.toHaveAttribute("data-page-transition");
});
