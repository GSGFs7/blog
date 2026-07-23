import type { HtmxBeforeSwapDetails } from "htmx.org";

const PAGE_TRANSITION_SWAP_DELAY = 100;
const PAGE_TRANSITION_SETTLE_DELAY = 20;

export const PAGE_TRANSITION_SWAP = `innerHTML swap:${PAGE_TRANSITION_SWAP_DELAY}ms settle:${PAGE_TRANSITION_SETTLE_DELAY}ms`;

export type HtmxHistorySwapDetails = {
  historyElt: Element;
  swapSpec: {
    swapDelay: number;
    settleDelay: number;
  };
};

export function applyPageTransition(
  detail: HtmxBeforeSwapDetails,
  body: HTMLElement,
  reducedMotion: boolean,
): void {
  if (
    !detail.boosted ||
    !detail.shouldSwap ||
    detail.target !== body ||
    reducedMotion ||
    detail.swapOverride != null
  ) {
    return;
  }

  // ? why string??
  detail.swapOverride = PAGE_TRANSITION_SWAP;
}

export function applyHistoryPageTransition(
  detail: HtmxHistorySwapDetails,
  body: HTMLElement,
  reducedMotion: boolean,
): void {
  if (detail.historyElt !== body || reducedMotion) {
    return;
  }

  detail.swapSpec.swapDelay = PAGE_TRANSITION_SWAP_DELAY;
  detail.swapSpec.settleDelay = PAGE_TRANSITION_SETTLE_DELAY;
  body.classList.add("htmx-swapping");
}
