import { APP_PAGE_EVENT } from "../navigation";
import type { Behavior, BehaviorContext, BehaviorFactory, LazyBehavior } from "./types";

const rootContainsSelector = (root: ParentNode, selector: string): boolean => {
  return (
    (root instanceof Element && root.matches(selector)) || root.querySelector(selector) !== null
  );
};

export function startBehaviorRuntime(document: Document, definitions: LazyBehavior[]): () => void {
  // Controller 0: control current runtime lifecycle
  const runtimeController = new AbortController();
  let stopped = false;
  let activePageBehaviors:
    | {
        controller: AbortController;
        behaviors: Behavior[];
      }
    | undefined;

  const destroyPage = () => {
    const pageBehaviors = activePageBehaviors;
    if (!pageBehaviors) {
      return;
    }

    activePageBehaviors = undefined;
    pageBehaviors.controller.abort();

    for (let i = pageBehaviors.behaviors.length - 1; i >= 0; i--) {
      try {
        pageBehaviors.behaviors[i].destroy?.();
      } catch (e) {
        console.error("[Behavior] Failed to destroy behavior:", e);
      }
    }
  };

  const mountPage = (root: ParentNode) => {
    destroyPage();

    const pageBehaviors = {
      controller: new AbortController(),
      behaviors: [] as Behavior[],
    };
    activePageBehaviors = pageBehaviors;

    // finding marks
    const matchingDefinitions = definitions.filter(({ selector }) =>
      rootContainsSelector(root, selector),
    );

    // load the behaviors
    void Promise.all(
      matchingDefinitions.map(async (definition): Promise<BehaviorFactory | undefined> => {
        try {
          return await definition.load();
        } catch (e) {
          console.error(`[Behavior] Failed to load behavior for ${definition.selector}:`, e);
          return undefined;
        }
      }),
    ).then((factories) => {
      if (
        stopped ||
        activePageBehaviors !== pageBehaviors ||
        pageBehaviors.controller.signal.aborted
      ) {
        return;
      }

      // add to list
      for (const factory of factories) {
        if (!factory) {
          continue;
        }

        try {
          pageBehaviors.behaviors.push(factory());
        } catch (e) {
          console.error("[Behavior] Failed to create behavior:", e);
        }
      }

      const context: BehaviorContext = {
        document,
        signal: pageBehaviors.controller.signal,
      };

      // mount the behaviors
      for (const behavior of pageBehaviors.behaviors) {
        try {
          behavior.mount(root, context);
        } catch (e) {
          console.error("[Behavior] Failed to mount behavior:", e);
        }
      }
    });
  };

  document.addEventListener(APP_PAGE_EVENT.beforeSwap, destroyPage, {
    signal: runtimeController.signal,
  });
  document.addEventListener(APP_PAGE_EVENT.afterSwap, (event) => mountPage(event.detail.root), {
    signal: runtimeController.signal,
  });

  // first exec
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountPage(document.body), {
      once: true,
      signal: runtimeController.signal,
    });
  } else {
    mountPage(document.body);
  }

  return () => {
    stopped = true;
    runtimeController.abort();
    destroyPage();
  };
}
