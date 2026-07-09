import { createBlogHeaderBehavior } from "./blog-header";
import { startBehaviorRuntime } from "./runtime";
import { createZoomBehavior } from "./zoom";

// weak ref. the fn's lifecycle follow Document
const activeSetups = new WeakMap<Document, () => void>();

// makesure init only once
export function setupBehaviors(document: Document = window.document): () => void {
  // call clean fn
  activeSetups.get(document)?.();

  let stopped = false;
  const stopRuntime = startBehaviorRuntime(document, [
    createBlogHeaderBehavior(),
    createZoomBehavior(),
  ]);
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
