import { APP_PAGE_EVENT } from "../navigation";
import type { Behavior, BehaviorContext } from "./types";

export function startBehaviorRuntime(document: Document, behaviors: Behavior[]): () => void {
  // Controller 0: control current runtime lifecycle
  const runtimeController = new AbortController();
  // Controller 1: control page behavior lifecycle
  let pageController: AbortController | undefined = undefined;

  const destroyPage = () => {
    if (!pageController) {
      return;
    }

    pageController.abort();
    pageController = undefined;

    for (let i = behaviors.length - 1; i >= 0; i--) {
      try {
        behaviors[i].destroy?.();
      } catch (e) {
        console.error("[Behavior] Failed to destroy behavior:", e);
      }
    }
  };

  const mountPage = (root: ParentNode) => {
    destroyPage();

    pageController = new AbortController();
    const context: BehaviorContext = {
      document,
      signal: pageController.signal,
    };

    for (const behavior of behaviors) {
      try {
        behavior.mount(root, context);
      } catch (e) {
        console.error("[Behavior] Failed to mount behavior:", e);
      }
    }
  };

  document.addEventListener(APP_PAGE_EVENT.beforeSwap, destroyPage, {
    signal: runtimeController.signal,
  });
  document.addEventListener(APP_PAGE_EVENT.afterSwap, (event) => mountPage(event.detail.root), {
    signal: runtimeController.signal,
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountPage(document.body), {
      once: true,
      signal: runtimeController.signal,
    });
  } else {
    mountPage(document.body);
  }

  return () => {
    runtimeController.abort();
    destroyPage();
  };
}
