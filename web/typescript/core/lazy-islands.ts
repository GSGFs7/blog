import { APP_PAGE_EVENT, type PageSwapDetail } from "./navigation/events";

const ISLAND_SELECTOR = "[data-solid-island]";

let setupPromise: Promise<void> | undefined = undefined;

function containsIsland(root: ParentNode): boolean {
  if (root instanceof Element && root.matches(ISLAND_SELECTOR)) {
    return true;
  }

  return root.querySelector(ISLAND_SELECTOR) !== null;
}

function loadRuntime(): Promise<void> {
  setupPromise ??= Promise.all([import("./bootstrap"), import("../islands")])
    .then(([{ setupIslands }, { COMPONENTS }]) => {
      setupIslands(COMPONENTS);
    })
    .catch((error: unknown) => {
      setupPromise = undefined;
      throw error;
    });
  return setupPromise;
}

// why this wrapper is necessary?
// even though `bootstrap` & `island` files is dynamic import,
// but `island` file has been static imported.
// it will be put into dependency graph.
// dynamic import just split the bundle, the solid runtime still will enter first screen.
// this wrapper is makesure every thing is dynamic import.
export function setupLazyIsland(): void {
  const scan = (root: ParentNode) => {
    if (!containsIsland(root)) {
      return;
    }

    void loadRuntime().catch((error: unknown) => {
      console.error("Failed to load Solid island runtime:", error);
    });
  };

  const handleAfterSwap = (event: CustomEvent<PageSwapDetail>) => {
    scan(event.detail.root);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => scan(document), { once: true });
  } else {
    scan(document);
  }

  document.addEventListener(APP_PAGE_EVENT.afterSwap, handleAfterSwap);
}
