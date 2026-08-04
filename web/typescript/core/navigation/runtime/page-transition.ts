import { APP_PAGE_EVENT } from "../contracts";

export const PAGE_TRANSITION_TIMING = {
  swapDelay: 100,
  settleDelay: 20,
} as const;

type TransitionPhase = "leaving" | "entering";

interface ActiveTransition {
  navigationId: number;
  root: HTMLElement;
}

interface PageTransitionOptions {
  // re-query every time
  prefersReducedMotion?: () => boolean;
}

export function setupPageTransition(
  document: Document,
  options: PageTransitionOptions = {},
): () => void {
  let active: ActiveTransition | undefined = undefined;
  const prefersReducedMotion =
    options.prefersReducedMotion ??
    (() => document.defaultView?.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);

  const clear = (): void => {
    active?.root.removeAttribute("data-page-transition");
    active = undefined;
  };

  const beforeSwap = (event: DocumentEventMap["app:before-swap"]): void => {
    clear();

    if (prefersReducedMotion()) {
      return;
    }

    active = {
      navigationId: event.detail.navigationId,
      root: event.detail.root,
    };
    active.root.setAttribute("data-page-transition", "leaving" satisfies TransitionPhase);
  };

  const afterSwap = (event: DocumentEventMap["app:after-swap"]): void => {
    if (active?.navigationId !== event.detail.navigationId || active.root !== event.detail.root) {
      return;
    }

    active.root.setAttribute("data-page-transition", "entering" satisfies TransitionPhase);
  };

  // remove 'data-page-transition' make it 'opacity: 1'
  const finish = (navigationId: number): void => {
    if (active?.navigationId === navigationId) {
      clear();
    }
  };

  const navigationEnd = (event: DocumentEventMap["app:navigation-end"]): void => {
    finish(event.detail.navigationId);
  };

  const navigationError = (event: DocumentEventMap["app:navigation-error"]): void => {
    finish(event.detail.navigationId);
  };

  document.addEventListener(APP_PAGE_EVENT.beforeSwap, beforeSwap);
  document.addEventListener(APP_PAGE_EVENT.afterSwap, afterSwap);
  document.addEventListener(APP_PAGE_EVENT.navigationEnd, navigationEnd);
  document.addEventListener(APP_PAGE_EVENT.navigationError, navigationError);

  return () => {
    document.removeEventListener(APP_PAGE_EVENT.beforeSwap, beforeSwap);
    document.removeEventListener(APP_PAGE_EVENT.afterSwap, afterSwap);
    document.removeEventListener(APP_PAGE_EVENT.navigationEnd, navigationEnd);
    document.removeEventListener(APP_PAGE_EVENT.navigationError, navigationError);

    clear();
  };
}
