import type { Behavior, BehaviorContext } from "./types";

function isParentNode(value: unknown): value is ParentNode {
  return value instanceof Document || value instanceof DocumentFragment || value instanceof Element;
}

// find the subtree be replaced by HTMX. only mount the subtree
function getHtmxRoot(event: Event, fallback: Document): ParentNode {
  const element = (event as CustomEvent<{ elt?: unknown }>).detail?.elt;

  // case 1. that's it
  if (isParentNode(element)) {
    return element;
  }

  // case 2. target node for event bubbling
  if (isParentNode(event.target)) {
    return event.target;
  }

  // case 3. full mount
  return fallback;
}

export function startBehaviorRuntime(document: Document, behaviors: Behavior[]): () => void {
  const controller = new AbortController();
  const context: BehaviorContext = {
    document,
    signal: controller.signal,
  };
  let stopped = false;

  const mount = (root: ParentNode) => {
    for (const behavior of behaviors) {
      behavior.mount(root, context);
    }
  };

  // mount behaviors after htmx changed
  document.addEventListener(
    "htmx:load",
    (event) => {
      mount(getHtmxRoot(event, document));
    },
    { signal: controller.signal },
  );

  // mount behaviors after page load
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mount(document), {
      once: true,
      signal: controller.signal,
    });
  } else {
    mount(document);
  }

  // clean
  return () => {
    if (stopped) {
      return;
    }

    stopped = true;
    controller.abort();
    for (let index = behaviors.length - 1; index >= 0; index -= 1) {
      behaviors[index].destroy?.();
    }
  };
}
