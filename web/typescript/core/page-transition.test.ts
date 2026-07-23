import type { HtmxBeforeSwapDetails } from "htmx.org";

import {
  applyHistoryPageTransition,
  applyPageTransition,
  type HtmxHistorySwapDetails,
  PAGE_TRANSITION_SWAP,
} from "./page-transition";

type SwapDetail = Pick<HtmxBeforeSwapDetails, "boosted" | "shouldSwap" | "target" | "swapOverride">;

function detail(overrides: Partial<SwapDetail> & { target?: Element } = {}): HtmxBeforeSwapDetails {
  return {
    ...overrides,
  } as unknown as HtmxBeforeSwapDetails;
}

function historyDetail(overrides: Partial<HtmxHistorySwapDetails> = {}): HtmxHistorySwapDetails {
  return {
    historyElt: document.body,
    swapSpec: { swapDelay: 0, settleDelay: 0 },
    ...overrides,
  };
}

afterEach(() => {
  document.body.classList.remove("htmx-swapping");
});

test("adds fade timing to boosted page swaps", () => {
  const d = detail({ boosted: true, shouldSwap: true, target: document.body });

  applyPageTransition(d, document.body, false);

  expect(d.swapOverride).toBe(PAGE_TRANSITION_SWAP);
});

const unchangedSwapCases: Array<[HtmxBeforeSwapDetails, boolean]> = [
  [detail({ boosted: false, shouldSwap: true }), false],
  [detail({ boosted: true, shouldSwap: false }), false],
  [detail({ boosted: true, shouldSwap: true, target: document.createElement("main") }), false],
  [detail({ boosted: true, shouldSwap: true, target: document.body }), true],
  [
    detail({ boosted: true, shouldSwap: true, target: document.body, swapOverride: "outerHTML" }),
    false,
  ],
];

test.each(unchangedSwapCases)("leaves non-page swaps unchanged", (d, reducedMotion) => {
  applyPageTransition(d, document.body, reducedMotion);

  expect(d.swapOverride).not.toBe(PAGE_TRANSITION_SWAP);
});

test("adds fade timing to history page swaps", () => {
  const d = historyDetail();

  applyHistoryPageTransition(d, document.body, false);

  expect(d.swapSpec).toEqual({ swapDelay: 100, settleDelay: 20 });
  expect(document.body).toHaveClass("htmx-swapping");
});

test.each([
  [historyDetail({ historyElt: document.createElement("main") }), false],
  [historyDetail(), true],
])("leaves unsupported history swaps unchanged", (d, reducedMotion) => {
  applyHistoryPageTransition(d, document.body, reducedMotion);

  expect(d.swapSpec).toEqual({ swapDelay: 0, settleDelay: 0 });
  expect(document.body).not.toHaveClass("htmx-swapping");
});
