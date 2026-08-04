import { startBehaviorRuntime } from "./runtime";
import type { LazyBehavior } from "./types";

// weak ref. the fn's lifecycle follow Document
const activeSetups = new WeakMap<Document, () => void>();

const behaviors = [
  {
    selector: "[data-blog-header]",
    load: async () => (await import("./blog-header")).createBlogHeaderBehavior,
  },
  {
    selector: ".markdown-body pre, .markdown-body .terminal",
    load: async () => (await import("./code-expander")).createCodeExpanderBehavior,
  },
  {
    selector: "[data-mobile-undecorated]",
    load: async () => (await import("./mobile-decoration")).createMobileDecorationBehavior,
  },
  {
    selector: ".markdown-body img",
    load: async () => (await import("./zoom")).createZoomBehavior,
  },
] satisfies LazyBehavior[];

// makesure init only once
export function setupBehaviors(document: Document = window.document): () => void {
  // call clean fn
  activeSetups.get(document)?.();

  let stopped = false;
  const stopRuntime = startBehaviorRuntime(document, behaviors);
  // tell caller how to clean this
  const teardown = () => {
    if (stopped) {
      return;
    }

    stopped = true;
    stopRuntime();
    if (activeSetups.get(document) === teardown) {
      activeSetups.delete(document);
    }
  };

  // registry this behavior
  activeSetups.set(document, teardown);
  return teardown;
}
